// Package output publishes composed twin stages to durable cluster references.
package output

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strconv"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
	"github.com/justrunme/twinops-control-plane/internal/buildjob"
)

// Result of a successful publish.
type Result struct {
	Digest             string
	URI                string
	StageKey           string
	Name               string
	MediaType          string
	BundleKey          string
	Revision           int64
	History            []twinopsv1alpha1.OutputRevision
	PublishFingerprint string
	// Created is false when content digest + fingerprint matched latest (no new revision).
	Created bool
}

// ConfigMapName returns the mutable index ConfigMap name (latest pointer).
func ConfigMapName(twinName string) string {
	return twinName + "-output"
}

// RevisionConfigMapName returns an immutable revision ConfigMap name.
func RevisionConfigMapName(twinName string, rev int64) string {
	return fmt.Sprintf("%s-output-r%d", twinName, rev)
}

// URI formats a configmap:// reference.
func URI(namespace, name string) string {
	return fmt.Sprintf("configmap://%s/%s", namespace, name)
}

// PublishDir builds a bundle from dir and publishes according to OutputPublish.mode.
func PublishDir(
	ctx context.Context,
	c client.Client,
	twin *twinopsv1alpha1.DigitalTwin,
	dir string,
	inputDigest string,
) (*Result, error) {
	bundle, err := BuildBundle(dir)
	if err != nil {
		return nil, err
	}
	return PublishBundle(ctx, c, twin, bundle, inputDigest)
}

// PublishBundle publishes an already-built bundle.
func PublishBundle(
	ctx context.Context,
	c client.Client,
	twin *twinopsv1alpha1.DigitalTwin,
	bundle *Bundle,
	inputDigest string,
) (*Result, error) {
	fp := buildjob.PublishFingerprint(twin.Spec.OutputPublish)
	mode := buildjob.EffectivePublishMode(twin.Spec.OutputPublish)

	if mode == "none" {
		return &Result{
			Digest:             bundle.Digest,
			URI:                "",
			StageKey:           StageEntry,
			MediaType:          MediaType,
			BundleKey:          BundleKey,
			Revision:           twin.Status.Output.Revision,
			History:            twin.Status.Output.History,
			PublishFingerprint: fp,
			Created:            false,
		}, nil
	}

	// Idempotent only when content digest AND publish destination match.
	// Changing OCI repo / S3 bucket with the same bundle must re-publish.
	if twin.Status.Output.Digest == bundle.Digest &&
		twin.Status.Output.URI != "" &&
		twin.Status.Output.PublishFingerprint == fp {
		return &Result{
			Digest:             bundle.Digest,
			URI:                twin.Status.Output.URI,
			StageKey:           StageEntry,
			Name:               ConfigMapName(twin.Name),
			MediaType:          MediaType,
			BundleKey:          BundleKey,
			Revision:           twin.Status.Output.Revision,
			History:            twin.Status.Output.History,
			PublishFingerprint: fp,
			Created:            false,
		}, nil
	}
	// Legacy status without fingerprint: if digest matches, still re-publish when
	// fingerprint is empty so destination changes take effect once.
	if twin.Status.Output.Digest == bundle.Digest &&
		twin.Status.Output.URI != "" &&
		twin.Status.Output.PublishFingerprint == "" &&
		mode == "configmap" {
		// ConfigMap URI is namespace-local and not destination-keyed; safe to keep.
		return &Result{
			Digest:             bundle.Digest,
			URI:                twin.Status.Output.URI,
			StageKey:           StageEntry,
			Name:               ConfigMapName(twin.Name),
			MediaType:          MediaType,
			BundleKey:          BundleKey,
			Revision:           twin.Status.Output.Revision,
			History:            twin.Status.Output.History,
			PublishFingerprint: fp,
			Created:            false,
		}, nil
	}

	rev := twin.Status.Output.Revision + 1
	if rev <= 0 {
		rev = 1
	}
	now := metav1.Now()

	var (
		uri  string
		name string
		err  error
	)
	switch mode {
	case "oci":
		uri, name, err = publishOCI(ctx, c, twin, bundle, rev, inputDigest)
	case "s3":
		uri, name, err = publishS3(ctx, c, twin, bundle, rev, inputDigest)
	default:
		uri, name, err = publishConfigMapRevision(ctx, c, twin, bundle, rev, inputDigest)
	}
	if err != nil {
		return nil, err
	}

	hist := append([]twinopsv1alpha1.OutputRevision{}, twin.Status.Output.History...)
	hist = append(hist, twinopsv1alpha1.OutputRevision{
		Revision:    rev,
		Digest:      bundle.Digest,
		URI:         uri,
		InputDigest: inputDigest,
		PublishedAt: &now,
	})
	keep := keepRevisions(twin.Spec.OutputPublish)
	if len(hist) > keep {
		// GC oldest configmap revisions when in configmap mode.
		if mode == "configmap" || mode == "" {
			for _, old := range hist[:len(hist)-keep] {
				_ = deleteRevisionConfigMap(ctx, c, twin.Namespace, twin.Name, old.Revision)
			}
		}
		hist = hist[len(hist)-keep:]
	}

	return &Result{
		Digest:             bundle.Digest,
		URI:                uri,
		StageKey:           StageEntry,
		Name:               name,
		MediaType:          MediaType,
		BundleKey:          BundleKey,
		Revision:           rev,
		History:            hist,
		PublishFingerprint: fp,
		Created:            true,
	}, nil
}

func keepRevisions(pub *twinopsv1alpha1.OutputPublish) int {
	if pub == nil || pub.KeepRevisions <= 0 {
		return 5
	}
	return int(pub.KeepRevisions)
}

func publishConfigMapRevision(
	ctx context.Context,
	c client.Client,
	twin *twinopsv1alpha1.DigitalTwin,
	bundle *Bundle,
	rev int64,
	inputDigest string,
) (uri, name string, err error) {
	if len(bundle.Bytes) > MaxBundleBytes {
		return "", "", fmt.Errorf("output bundle exceeds ConfigMap size budget (%d > %d bytes)", len(bundle.Bytes), MaxBundleBytes)
	}
	name = RevisionConfigMapName(twin.Name, rev)
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: twin.Namespace,
			Labels: map[string]string{
				"twinops.io/twin":     twin.Name,
				"twinops.io/output":   "true",
				"twinops.io/revision": strconv.FormatInt(rev, 10),
			},
			Annotations: map[string]string{
				"twinops.io/output-digest": bundle.Digest,
				"twinops.io/input-digest":  inputDigest,
				"twinops.io/media-type":    MediaType,
				"twinops.io/bundle-key":    BundleKey,
				"twinops.io/stage-path":    StageEntry,
				"twinops.io/revision":      strconv.FormatInt(rev, 10),
			},
			OwnerReferences: ownerRefs(twin),
		},
		Immutable: boolPtr(true),
		BinaryData: map[string][]byte{
			BundleKey: bundle.Bytes,
		},
	}
	if err := c.Create(ctx, cm); err != nil {
		if !apierrors.IsAlreadyExists(err) {
			return "", "", fmt.Errorf("create immutable output configmap: %w", err)
		}
		// Already exists with same name — treat as success if digest matches.
		var existing corev1.ConfigMap
		if getErr := c.Get(ctx, types.NamespacedName{Namespace: twin.Namespace, Name: name}, &existing); getErr != nil {
			return "", "", getErr
		}
		if existing.Annotations["twinops.io/output-digest"] != bundle.Digest {
			return "", "", fmt.Errorf("revision configmap %s exists with different digest", name)
		}
	}

	// Mutable index ConfigMap for convenience (latest pointer only).
	_ = upsertLatestIndex(ctx, c, twin, rev, bundle.Digest, inputDigest, URI(twin.Namespace, name))
	return URI(twin.Namespace, name), name, nil
}

func upsertLatestIndex(
	ctx context.Context,
	c client.Client,
	twin *twinopsv1alpha1.DigitalTwin,
	rev int64,
	digest, inputDigest, revURI string,
) error {
	name := ConfigMapName(twin.Name)
	var cm corev1.ConfigMap
	key := types.NamespacedName{Namespace: twin.Namespace, Name: name}
	err := c.Get(ctx, key, &cm)
	if apierrors.IsNotFound(err) {
		cm = corev1.ConfigMap{
			ObjectMeta: metav1.ObjectMeta{
				Name:      name,
				Namespace: twin.Namespace,
				Labels: map[string]string{
					"twinops.io/twin":   twin.Name,
					"twinops.io/output": "index",
				},
				OwnerReferences: ownerRefs(twin),
			},
		}
		cm.Data = map[string]string{
			"latestRevision": strconv.FormatInt(rev, 10),
			"latestURI":      revURI,
			"latestDigest":   digest,
			"inputDigest":    inputDigest,
		}
		return c.Create(ctx, &cm)
	}
	if err != nil {
		return err
	}
	if cm.Data == nil {
		cm.Data = map[string]string{}
	}
	cm.Data["latestRevision"] = strconv.FormatInt(rev, 10)
	cm.Data["latestURI"] = revURI
	cm.Data["latestDigest"] = digest
	cm.Data["inputDigest"] = inputDigest
	return c.Update(ctx, &cm)
}

func deleteRevisionConfigMap(ctx context.Context, c client.Client, ns, twinName string, rev int64) error {
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      RevisionConfigMapName(twinName, rev),
			Namespace: ns,
		},
	}
	err := c.Delete(ctx, cm)
	if apierrors.IsNotFound(err) {
		return nil
	}
	return err
}

// DeleteConfigMap removes index + all revision ConfigMaps for a twin.
func DeleteConfigMap(ctx context.Context, c client.Client, namespace, twinName string) error {
	var list corev1.ConfigMapList
	if err := c.List(ctx, &list, client.InNamespace(namespace), client.MatchingLabels{
		"twinops.io/twin": twinName,
	}); err != nil {
		return err
	}
	for i := range list.Items {
		cm := &list.Items[i]
		if cm.Labels["twinops.io/output"] == "true" || cm.Labels["twinops.io/output"] == "index" {
			_ = c.Delete(ctx, cm)
		}
	}
	// Legacy single-output name.
	legacy := &corev1.ConfigMap{ObjectMeta: metav1.ObjectMeta{Name: ConfigMapName(twinName), Namespace: namespace}}
	_ = c.Delete(ctx, legacy)
	return nil
}

func ownerRefs(twin *twinopsv1alpha1.DigitalTwin) []metav1.OwnerReference {
	apiVersion := twinopsv1alpha1.GroupVersion.String()
	block := true
	ctrl := true
	return []metav1.OwnerReference{{
		APIVersion:         apiVersion,
		Kind:               "DigitalTwin",
		Name:               twin.Name,
		UID:                twin.UID,
		Controller:         &ctrl,
		BlockOwnerDeletion: &block,
	}}
}

func boolPtr(v bool) *bool { return &v }

// WriteBundleFile writes bundle bytes to path (job helper).
func WriteBundleFile(path string, bundle *Bundle) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, bundle.Bytes, 0o644)
}
