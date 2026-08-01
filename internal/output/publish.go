// Package output publishes composed twin stages to durable cluster references.
package output

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

// ConfigMapName returns the default published output ConfigMap name for a twin.
func ConfigMapName(twinName string) string {
	return twinName + "-output"
}

// URI formats a configmap:// reference.
func URI(namespace, name string) string {
	return fmt.Sprintf("configmap://%s/%s", namespace, name)
}

// Result of a successful publish.
type Result struct {
	Digest   string
	URI      string
	StageKey string
	Name     string
}

// PublishDir uploads regular files from dir into a ConfigMap owned by the twin.
func PublishDir(
	ctx context.Context,
	c client.Client,
	twin *twinopsv1alpha1.DigitalTwin,
	dir string,
	inputDigest string,
) (*Result, error) {
	files, err := readDirFiles(dir)
	if err != nil {
		return nil, err
	}
	if len(files) == 0 {
		return nil, fmt.Errorf("output publish: no files in %s", dir)
	}
	digest := HashFiles(files)
	cmName := ConfigMapName(twin.Name)

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      cmName,
			Namespace: twin.Namespace,
		},
	}
	_, err = controllerutil.CreateOrUpdate(ctx, c, cm, func() error {
		if cm.Labels == nil {
			cm.Labels = map[string]string{}
		}
		cm.Labels["twinops.io/twin"] = twin.Name
		cm.Labels["twinops.io/output"] = "true"
		if cm.Annotations == nil {
			cm.Annotations = map[string]string{}
		}
		cm.Annotations["twinops.io/output-digest"] = digest
		cm.Annotations["twinops.io/input-digest"] = inputDigest
		cm.BinaryData = files
		cm.Data = nil
		return setOwner(twin, cm)
	})
	if err != nil {
		return nil, fmt.Errorf("publish output configmap: %w", err)
	}

	stageKey := "root.usda"
	if _, ok := files[stageKey]; !ok {
		keys := make([]string, 0, len(files))
		for k := range files {
			keys = append(keys, k)
		}
		slices.Sort(keys)
		for _, k := range keys {
			if strings.HasSuffix(k, ".usda") || strings.HasSuffix(k, ".usd") {
				stageKey = k
				break
			}
		}
		if _, ok := files[stageKey]; !ok && len(keys) > 0 {
			stageKey = keys[0]
		}
	}

	return &Result{
		Digest:   digest,
		URI:      URI(twin.Namespace, cmName),
		StageKey: stageKey,
		Name:     cmName,
	}, nil
}

// DeleteConfigMap removes a published output ConfigMap if present.
func DeleteConfigMap(ctx context.Context, c client.Client, namespace, twinName string) error {
	cm := &corev1.ConfigMap{}
	key := types.NamespacedName{Namespace: namespace, Name: ConfigMapName(twinName)}
	if err := c.Get(ctx, key, cm); err != nil {
		if apierrors.IsNotFound(err) {
			return nil
		}
		return err
	}
	return c.Delete(ctx, cm)
}

func setOwner(twin *twinopsv1alpha1.DigitalTwin, cm *corev1.ConfigMap) error {
	apiVersion := twinopsv1alpha1.GroupVersion.String()
	block := true
	ctrl := true
	cm.OwnerReferences = []metav1.OwnerReference{{
		APIVersion:         apiVersion,
		Kind:               "DigitalTwin",
		Name:               twin.Name,
		UID:                twin.UID,
		Controller:         &ctrl,
		BlockOwnerDeletion: &block,
	}}
	return nil
}

func readDirFiles(dir string) (map[string][]byte, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := map[string][]byte{}
	var total int
	for _, e := range entries {
		if e.IsDir() {
			// Skip nested dirs (inputs/, drift/).
			continue
		}
		name := e.Name()
		if strings.HasPrefix(name, ".") {
			continue
		}
		path := filepath.Join(dir, name)
		info, err := e.Info()
		if err != nil {
			return nil, err
		}
		// ConfigMap soft limit ~1MiB; keep pilot bundles small.
		if info.Size() > 900*1024 {
			return nil, fmt.Errorf("output file %q too large for ConfigMap publish (%d bytes)", name, info.Size())
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		total += len(data)
		if total > 900*1024 {
			return nil, fmt.Errorf("output bundle exceeds ConfigMap size budget")
		}
		out[name] = data
	}
	return out, nil
}

// HashFiles returns sha256:<hex> of sorted name+payload pairs.
func HashFiles(files map[string][]byte) string {
	keys := make([]string, 0, len(files))
	for k := range files {
		keys = append(keys, k)
	}
	slices.Sort(keys)
	h := sha256.New()
	for _, k := range keys {
		h.Write([]byte(k))
		h.Write([]byte{0})
		h.Write(files[k])
		h.Write([]byte{0})
	}
	return "sha256:" + hex.EncodeToString(h.Sum(nil))
}
