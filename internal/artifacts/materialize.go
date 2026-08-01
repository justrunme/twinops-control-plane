// Package artifacts materializes twin inputs into an atomic workspace.
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
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

const (
	// MaxDownloadBytes is the hard cap for a single HTTP artifact fetch.
	MaxDownloadBytes = 32 << 20 // 32 MiB
	// MaxFileBytes is the hard cap per archive entry or ConfigMap value.
	MaxFileBytes = 8 << 20 // 8 MiB
	// MaxFiles is the maximum number of files in one artifact bundle.
	MaxFiles = 64
	// MaxDecompressedBytes is the total decompressed payload budget.
	MaxDecompressedBytes = 48 << 20 // 48 MiB
)

// Source describes where twin inputs come from.
type Source struct {
	ConfigMapName  string
	URL            string
	Namespace      string
	ExpectedDigest string // optional sha256:<hex>
	// AllowPrivateURL permits loopback/private HTTP(S) fetches (tests / lab only).
	AllowPrivateURL bool
	// RequireExpectedDigest fails closed when URL is used without ExpectedDigest.
	// ConfigMap sources never require it (cluster-local trust boundary).
	RequireExpectedDigest bool
}

// Result is a materialized workspace with resolved paths and content digest.
type Result struct {
	Workspace    string
	ManifestPath string
	DesiredPath  string
	ObservedPath string
	Digest       string // sha256:<hex> of concatenated key payloads
}

// Materialize writes inputs into a staging dir, verifies digest, then atomically
// replaces workspaceDir so stale files from prior bundles cannot linger.
func Materialize(ctx context.Context, c client.Client, src Source, workspaceDir string) (*Result, error) {
	if err := validateSource(src); err != nil {
		return nil, err
	}
	parent := filepath.Dir(workspaceDir)
	if err := os.MkdirAll(parent, 0o755); err != nil {
		return nil, err
	}

	stage, err := os.MkdirTemp(parent, ".twinops-inputs-*")
	if err != nil {
		return nil, err
	}
	committed := false
	defer func() {
		if !committed {
			_ = os.RemoveAll(stage)
		}
	}()

	if src.URL != "" && src.ExpectedDigest == "" && src.RequireExpectedDigest {
		return nil, fmt.Errorf("artifact url requires expectedDigest (fail-closed)")
	}

	var files map[string][]byte
	switch {
	case src.ConfigMapName != "":
		files, err = fromConfigMap(ctx, c, src.Namespace, src.ConfigMapName)
	default:
		files, err = fromURL(ctx, src.URL, src.AllowPrivateURL)
	}
	if err != nil {
		return nil, err
	}
	if err := validateFileSet(files); err != nil {
		return nil, err
	}

	digest := hashFiles(files)
	if src.ExpectedDigest != "" && !digestsEqual(src.ExpectedDigest, digest) {
		return nil, fmt.Errorf("artifact digest mismatch: expected %s got %s", src.ExpectedDigest, digest)
	}

	for name, data := range files {
		path := filepath.Join(stage, name)
		if err := os.WriteFile(path, data, 0o644); err != nil {
			return nil, err
		}
	}

	manifest := firstExisting(stage, "twin.yaml", "manifest.yaml")
	if manifest == "" {
		return nil, fmt.Errorf("artifact missing twin.yaml (or manifest.yaml)")
	}

	if err := atomicReplace(workspaceDir, stage); err != nil {
		return nil, err
	}
	committed = true

	return &Result{
		Workspace:    workspaceDir,
		ManifestPath: filepath.Join(workspaceDir, filepath.Base(manifest)),
		DesiredPath:  firstExisting(workspaceDir, "desired.yaml"),
		ObservedPath: firstExisting(workspaceDir, "telemetry.json", "observed.json"),
		Digest:       digest,
	}, nil
}

func validateSource(src Source) error {
	hasCM := src.ConfigMapName != ""
	hasURL := src.URL != ""
	switch {
	case hasCM && hasURL:
		return fmt.Errorf("artifactSource: set exactly one of configMapName or url")
	case !hasCM && !hasURL:
		return fmt.Errorf("artifactSource requires configMapName or url")
	default:
		return nil
	}
}

func digestsEqual(expected, actual string) bool {
	return strings.EqualFold(strings.TrimSpace(expected), strings.TrimSpace(actual))
}

// atomicReplace replaces dst with srcDir via rename, removing any previous dst.
func atomicReplace(dst, srcDir string) error {
	backup := dst + ".bak-" + fmt.Sprintf("%d", time.Now().UnixNano())
	_ = os.RemoveAll(backup)
	if _, err := os.Stat(dst); err == nil {
		if err := os.Rename(dst, backup); err != nil {
			if rmErr := os.RemoveAll(dst); rmErr != nil {
				return rmErr
			}
		}
	}
	if err := os.Rename(srcDir, dst); err != nil {
		_ = os.Rename(backup, dst)
		return err
	}
	_ = os.RemoveAll(backup)
	return nil
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

func fromURL(ctx context.Context, rawURL string, allowPrivate bool) (map[string][]byte, error) {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return nil, err
	}
	scheme := strings.ToLower(parsed.Scheme)
	if scheme != "https" && scheme != "http" {
		return nil, fmt.Errorf("artifact url scheme must be http or https")
	}
	if scheme == "http" && !allowPrivate {
		return nil, fmt.Errorf("artifact url must use https (or enable AllowPrivateURL for lab/http)")
	}
	host := parsed.Hostname()
	if err := checkHostSSRF(host, allowPrivate); err != nil {
		return nil, err
	}

	httpClient := &http.Client{
		Timeout: 60 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) >= 5 {
				return fmt.Errorf("too many redirects")
			}
			return checkHostSSRF(req.URL.Hostname(), allowPrivate)
		},
	}
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
	body, err := readLimited(resp.Body, MaxDownloadBytes)
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

func checkHostSSRF(host string, allowPrivate bool) error {
	host = strings.TrimSpace(strings.ToLower(host))
	if host == "" {
		return fmt.Errorf("artifact url missing host")
	}
	if allowPrivate {
		return nil
	}
	blockedNames := []string{
		"metadata.google.internal",
		"metadata",
		"localhost",
		"127.0.0.1",
		"0.0.0.0",
		"::1",
	}
	for _, name := range blockedNames {
		if host == name {
			return fmt.Errorf("artifact url host %q blocked (SSRF policy)", host)
		}
	}
	if ip := net.ParseIP(host); ip != nil {
		if isPrivateIP(ip) {
			return fmt.Errorf("artifact url resolves to private IP (SSRF policy)")
		}
		return nil
	}
	// Fail closed when DNS fails — avoids treating lookup errors as "allow".
	ips, err := net.LookupIP(host)
	if err != nil {
		return fmt.Errorf("artifact url DNS lookup failed for %q: %w", host, err)
	}
	if len(ips) == 0 {
		return fmt.Errorf("artifact url host %q resolved to no addresses", host)
	}
	for _, ip := range ips {
		if isPrivateIP(ip) {
			return fmt.Errorf("artifact url host %q resolves to private IP %s (SSRF policy)", host, ip)
		}
	}
	return nil
}

// readLimited reads up to limit bytes and errors if more data is available.
func readLimited(r io.Reader, limit int64) ([]byte, error) {
	lr := io.LimitReader(r, limit+1)
	data, err := io.ReadAll(lr)
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > limit {
		return nil, fmt.Errorf("artifact exceeds size limit (%d bytes)", limit)
	}
	return data, nil
}

func validateFileSet(files map[string][]byte) error {
	if len(files) == 0 {
		return fmt.Errorf("artifact is empty")
	}
	if len(files) > MaxFiles {
		return fmt.Errorf("artifact has %d files (max %d)", len(files), MaxFiles)
	}
	var total int
	seen := map[string]struct{}{}
	for name, data := range files {
		base := filepath.Base(name)
		if base == "." || base == ".." || base == "" || strings.Contains(name, "..") {
			return fmt.Errorf("artifact file name rejected: %q", name)
		}
		if _, ok := seen[base]; ok {
			return fmt.Errorf("artifact has duplicate basename %q", base)
		}
		seen[base] = struct{}{}
		if len(data) > MaxFileBytes {
			return fmt.Errorf("artifact file %q exceeds per-file limit (%d bytes)", base, MaxFileBytes)
		}
		total += len(data)
		if total > MaxDecompressedBytes {
			return fmt.Errorf("artifact total size exceeds limit (%d bytes)", MaxDecompressedBytes)
		}
	}
	return nil
}

func isPrivateIP(ip net.IP) bool {
	if ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsPrivate() {
		return true
	}
	if ip4 := ip.To4(); ip4 != nil {
		if ip4[0] == 169 && ip4[1] == 254 {
			return true
		}
	}
	return false
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
		if _, exists := out[name]; exists {
			return nil, fmt.Errorf("zip has duplicate basename %q", name)
		}
		rc, err := f.Open()
		if err != nil {
			return nil, err
		}
		payload, err := readLimited(rc, MaxFileBytes)
		_ = rc.Close()
		if err != nil {
			return nil, fmt.Errorf("zip entry %q: %w", name, err)
		}
		out[name] = payload
		if len(out) > MaxFiles {
			return nil, fmt.Errorf("zip has more than %d files", MaxFiles)
		}
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
		name := filepath.Base(hdr.Name)
		if _, exists := out[name]; exists {
			return nil, fmt.Errorf("tar has duplicate basename %q", name)
		}
		payload, err := readLimited(tr, MaxFileBytes)
		if err != nil {
			return nil, fmt.Errorf("tar entry %q: %w", name, err)
		}
		out[name] = payload
		if len(out) > MaxFiles {
			return nil, fmt.Errorf("tar has more than %d files", MaxFiles)
		}
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
