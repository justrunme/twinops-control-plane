package output

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
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

// Bundle is a deterministic content-addressed stage archive.
type Bundle struct {
	Files  map[string][]byte
	Bytes  []byte
	Digest string // sha256 of content files (not gzip wrapper)
}

// BuildBundle walks dir and builds a deterministic tar.gz of USD content.
func BuildBundle(dir string) (*Bundle, error) {
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
	digest := HashFiles(files)
	raw, err := packTarGz(files)
	if err != nil {
		return nil, err
	}
	return &Bundle{Files: files, Bytes: raw, Digest: digest}, nil
}

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

func packTarGz(files map[string][]byte) ([]byte, error) {
	keys := make([]string, 0, len(files))
	for k := range files {
		keys = append(keys, k)
	}
	slices.Sort(keys)

	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
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
