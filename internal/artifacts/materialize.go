// Package artifacts materializes immutable DigitalTwin inputs into a workspace.
package artifacts

import (
	"archive/tar"
	"archive/zip"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

// Source describes where twin inputs come from.
type Source struct {
	ConfigMapName string
	URL           string
	Namespace     string
}

// Result is a materialized workspace with resolved paths and content digest.
type Result struct {
	Workspace    string
	ManifestPath string
	DesiredPath  string
	ObservedPath string
	Digest       string // sha256:<hex> of concatenated key payloads
}

// Materialize writes inputs into workspaceDir and returns resolved paths.
func Materialize(ctx context.Context, c client.Client, src Source, workspaceDir string) (*Result, error) {
	if src.ConfigMapName == "" && src.URL == "" {
		return nil, fmt.Errorf("artifactSource requires configMapName or url")
	}
	if err := os.MkdirAll(workspaceDir, 0o755); err != nil {
		return nil, err
	}

	var files map[string][]byte
	var err error
	switch {
	case src.ConfigMapName != "":
		files, err = fromConfigMap(ctx, c, src.Namespace, src.ConfigMapName)
	default:
		files, err = fromURL(ctx, src.URL)
	}
	if err != nil {
		return nil, err
	}

	digest := hashFiles(files)
	for name, data := range files {
		path := filepath.Join(workspaceDir, name)
		if err := os.WriteFile(path, data, 0o644); err != nil {
			return nil, err
		}
	}

	manifest := firstExisting(workspaceDir, "twin.yaml", "manifest.yaml")
	if manifest == "" {
		return nil, fmt.Errorf("artifact missing twin.yaml (or manifest.yaml)")
	}
	return &Result{
		Workspace:    workspaceDir,
		ManifestPath: manifest,
		DesiredPath:  firstExisting(workspaceDir, "desired.yaml"),
		ObservedPath: firstExisting(workspaceDir, "telemetry.json", "observed.json"),
		Digest:       digest,
	}, nil
}

func fromConfigMap(ctx context.Context, c client.Client, namespace, name string) (map[string][]byte, error) {
	var cm corev1.ConfigMap
	if err := c.Get(ctx, types.NamespacedName{Namespace: namespace, Name: name}, &cm); err != nil {
		return nil, fmt.Errorf("get configmap %s/%s: %w", namespace, name, err)
	}
	out := map[string][]byte{}
	for k, v := range cm.Data {
		out[k] = []byte(v)
	}
	for k, v := range cm.BinaryData {
		out[k] = v
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("configmap %s/%s is empty", namespace, name)
	}
	return out, nil
}

func fromURL(ctx context.Context, rawURL string) (map[string][]byte, error) {
	httpClient := &http.Client{Timeout: 60 * time.Second}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, err
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("artifact url HTTP %d", resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 32<<20))
	if err != nil {
		return nil, err
	}
	lower := strings.ToLower(rawURL)
	switch {
	case strings.HasSuffix(lower, ".zip"):
		return unzipBytes(body)
	case strings.HasSuffix(lower, ".tgz"), strings.HasSuffix(lower, ".tar.gz"):
		return untarGzBytes(body)
	case strings.HasSuffix(lower, ".yaml"), strings.HasSuffix(lower, ".yml"):
		return map[string][]byte{"twin.yaml": body}, nil
	default:
		if files, err := untarGzBytes(body); err == nil {
			return files, nil
		}
		return unzipBytes(body)
	}
}

func unzipBytes(data []byte) (map[string][]byte, error) {
	r, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, err
	}
	out := map[string][]byte{}
	for _, f := range r.File {
		if f.FileInfo().IsDir() {
			continue
		}
		name := filepath.Base(f.Name)
		rc, err := f.Open()
		if err != nil {
			return nil, err
		}
		payload, err := io.ReadAll(io.LimitReader(rc, 8<<20))
		_ = rc.Close()
		if err != nil {
			return nil, err
		}
		out[name] = payload
	}
	return out, nil
}

func untarGzBytes(data []byte) (map[string][]byte, error) {
	gz, err := gzip.NewReader(bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	defer gz.Close()
	tr := tar.NewReader(gz)
	out := map[string][]byte{}
	for {
		hdr, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		if hdr.Typeflag != tar.TypeReg {
			continue
		}
		payload, err := io.ReadAll(io.LimitReader(tr, 8<<20))
		if err != nil {
			return nil, err
		}
		out[filepath.Base(hdr.Name)] = payload
	}
	return out, nil
}

func hashFiles(files map[string][]byte) string {
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

func firstExisting(dir string, names ...string) string {
	for _, name := range names {
		path := filepath.Join(dir, name)
		if _, err := os.Stat(path); err == nil {
			return path
		}
	}
	return ""
}
