// Package output publishes composed twin stages to durable cluster references.
package output

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

const (
	// BundleKey is the ConfigMap binaryData key for the published tarball.
	BundleKey = "bundle.tar.gz"
	// MediaType identifies TwinOps v1 tar+gzip stage bundles.
	MediaType = "application/vnd.twinops.bundle.v1+tar+gzip"
	// StageEntry is the primary stage path inside the bundle.
	StageEntry = "root.usda"
	// MaxBundleBytes soft-cap for ConfigMap-hosted bundles (~900 KiB).
	MaxBundleBytes = 900 * 1024
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
	Digest    string
	URI       string
	StageKey  string
	Name      string
	MediaType string
	BundleKey string
}

// PublishDir builds a deterministic tar.gz of USD content under dir and stores
// it as ConfigMap binaryData[bundle.tar.gz]. Volatile paths (inputs/, drift/,
// reconciliation-report.json) are excluded so digests stay stable across rebuilds.
func PublishDir(
	ctx context.Context,
	c client.Client,
	twin *twinopsv1alpha1.DigitalTwin,
	dir string,
	inputDigest string,
) (*Result, error) {
	files, err := collectContentFiles(dir)
	if err != nil {
		return nil, err
	}
	if len(files) == 0 {
		return nil, fmt.Errorf("output publish: no content files under %s", dir)
	}
	if _, ok := files[StageEntry]; !ok {
		return nil, fmt.Errorf("output publish: missing %s in composed stage", StageEntry)
	}

	contentDigest := HashFiles(files)
	bundle, err := packTarGz(files)
	if err != nil {
		return nil, err
	}
	if len(bundle) > MaxBundleBytes {
		return nil, fmt.Errorf("output bundle exceeds ConfigMap size budget (%d > %d bytes)", len(bundle), MaxBundleBytes)
	}

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
		cm.Annotations["twinops.io/output-digest"] = contentDigest
		cm.Annotations["twinops.io/input-digest"] = inputDigest
		cm.Annotations["twinops.io/media-type"] = MediaType
		cm.Annotations["twinops.io/bundle-key"] = BundleKey
		cm.Annotations["twinops.io/stage-path"] = StageEntry
		cm.BinaryData = map[string][]byte{BundleKey: bundle}
		cm.Data = nil
		return setOwner(twin, cm)
	})
	if err != nil {
		return nil, fmt.Errorf("publish output configmap: %w", err)
	}

	return &Result{
		Digest:    contentDigest,
		URI:       URI(twin.Namespace, cmName),
		StageKey:  StageEntry,
		Name:      cmName,
		MediaType: MediaType,
		BundleKey: BundleKey,
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

// collectContentFiles walks dir and returns relative path → payload for durable USD content.
func collectContentFiles(dir string) (map[string][]byte, error) {
	out := map[string][]byte{}
	var total int
	err := filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, relErr := filepath.Rel(dir, path)
		if relErr != nil {
			return relErr
		}
		rel = filepath.ToSlash(rel)
		if rel == "." {
			return nil
		}
		// Skip operator-managed side trees and volatile reports.
		top := strings.SplitN(rel, "/", 2)[0]
		switch top {
		case "inputs", "drift":
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		base := filepath.Base(rel)
		if strings.HasPrefix(base, ".") {
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if base == "reconciliation-report.json" || strings.HasSuffix(base, "-report.json") {
			return nil
		}
		if d.IsDir() {
			return nil
		}
		// Content: USDA/USD and co-located assets only.
		lower := strings.ToLower(rel)
		if !(strings.HasSuffix(lower, ".usda") ||
			strings.HasSuffix(lower, ".usd") ||
			strings.HasSuffix(lower, ".usdc") ||
			strings.Contains(rel, "assets/")) {
			return nil
		}
		info, err := d.Info()
		if err != nil {
			return err
		}
		if info.Size() > MaxBundleBytes {
			return fmt.Errorf("output file %q too large (%d bytes)", rel, info.Size())
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		total += len(data)
		if total > MaxBundleBytes {
			return fmt.Errorf("output content exceeds size budget (%d bytes)", MaxBundleBytes)
		}
		out[rel] = data
		return nil
	})
	if err != nil {
		return nil, err
	}
	return out, nil
}

// packTarGz builds a deterministic gzipped tar of files (sorted paths, zero mtime).
func packTarGz(files map[string][]byte) ([]byte, error) {
	keys := make([]string, 0, len(files))
	for k := range files {
		keys = append(keys, k)
	}
	slices.Sort(keys)

	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	// Fixed header for deterministic gzip (no timestamp/hostname).
	gz.Name = ""
	gz.ModTime = time.Time{}
	tw := tar.NewWriter(gz)

	for _, name := range keys {
		payload := files[name]
		hdr := &tar.Header{
			Name:    name,
			Mode:    0o644,
			Size:    int64(len(payload)),
			ModTime: time.Unix(0, 0).UTC(),
			Uid:     0,
			Gid:     0,
			Uname:   "",
			Gname:   "",
		}
		if err := tw.WriteHeader(hdr); err != nil {
			return nil, err
		}
		if _, err := tw.Write(payload); err != nil {
			return nil, err
		}
	}
	if err := tw.Close(); err != nil {
		return nil, err
	}
	if err := gz.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// UnpackBundle extracts a TwinOps bundle tar.gz into destDir.
func UnpackBundle(r io.Reader, destDir string) error {
	gz, err := gzip.NewReader(r)
	if err != nil {
		return err
	}
	defer gz.Close()
	tr := tar.NewReader(gz)
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}
		if hdr.Typeflag != tar.TypeReg && hdr.Typeflag != 0 {
			continue
		}
		name := filepath.Clean(hdr.Name)
		if strings.HasPrefix(name, "..") || filepath.IsAbs(name) {
			return fmt.Errorf("unsafe path in bundle: %q", hdr.Name)
		}
		target := filepath.Join(destDir, name)
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}
		f, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
		if err != nil {
			return err
		}
		if _, err := io.Copy(f, io.LimitReader(tr, MaxBundleBytes)); err != nil {
			_ = f.Close()
			return err
		}
		_ = f.Close()
	}
}

// HashFiles returns sha256:<hex> of sorted name+payload pairs (content digest).
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
