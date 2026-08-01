package artifacts

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
)

func TestMaterializeConfigMapAtomicStaleRemoval(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = corev1.AddToScheme(scheme)
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "twin-inputs", Namespace: "ns"},
		Data: map[string]string{
			"twin.yaml":      "apiVersion: twinops.io/v1\nkind: Twin\n",
			"desired.yaml":   "motors:\n  - id: m1\n",
			"telemetry.json": `{"motors":[]}`,
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(cm).Build()
	dir := filepath.Join(t.TempDir(), "inputs")

	res, err := Materialize(context.Background(), c, Source{
		Namespace:     "ns",
		ConfigMapName: "twin-inputs",
	}, dir)
	if err != nil {
		t.Fatal(err)
	}
	if res.DesiredPath == "" {
		t.Fatal("expected desired path")
	}

	// Second materialize without desired.yaml must drop the stale file.
	cm2 := cm.DeepCopy()
	cm2.Data = map[string]string{
		"twin.yaml":      "apiVersion: twinops.io/v1\nkind: Twin\nrev: 2\n",
		"telemetry.json": `{"motors":[{"id":"m1"}]}`,
	}
	if err := c.Update(context.Background(), cm2); err != nil {
		t.Fatal(err)
	}
	res2, err := Materialize(context.Background(), c, Source{
		Namespace:     "ns",
		ConfigMapName: "twin-inputs",
	}, dir)
	if err != nil {
		t.Fatal(err)
	}
	if res2.DesiredPath != "" {
		t.Fatalf("stale desired.yaml survived atomic replace: %s", res2.DesiredPath)
	}
	if _, err := os.Stat(filepath.Join(dir, "desired.yaml")); !os.IsNotExist(err) {
		t.Fatalf("desired.yaml should be gone, err=%v", err)
	}
	if res2.Digest == res.Digest {
		t.Fatal("digest should change when ConfigMap changes")
	}
}

func TestExpectedDigest(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = corev1.AddToScheme(scheme)
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "twin-inputs", Namespace: "ns"},
		Data:       map[string]string{"twin.yaml": "x: 1\n"},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(cm).Build()
	dir := filepath.Join(t.TempDir(), "inputs")
	digest := hashFiles(map[string][]byte{"twin.yaml": []byte("x: 1\n")})
	if _, err := Materialize(context.Background(), c, Source{
		Namespace:      "ns",
		ConfigMapName:  "twin-inputs",
		ExpectedDigest: digest,
	}, dir); err != nil {
		t.Fatal(err)
	}
	if _, err := Materialize(context.Background(), c, Source{
		Namespace:      "ns",
		ConfigMapName:  "twin-inputs",
		ExpectedDigest: "sha256:deadbeef",
	}, dir); err == nil {
		t.Fatal("expected digest mismatch error")
	}
}

func TestXORSource(t *testing.T) {
	err := validateSource(Source{ConfigMapName: "a", URL: "https://example.com/x"})
	if err == nil {
		t.Fatal("expected XOR error")
	}
}

func TestSSRFBlocksLocalhost(t *testing.T) {
	err := checkHostSSRF("127.0.0.1", false)
	if err == nil {
		t.Fatal("expected SSRF block")
	}
	if err := checkHostSSRF("127.0.0.1", true); err != nil {
		t.Fatal(err)
	}
}

func TestMaterializeTarGzURLPrivateAllowed(t *testing.T) {
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	content := []byte("apiVersion: twinops.io/v1\nkind: Twin\n")
	hdr := &tar.Header{Name: "twin.yaml", Mode: 0o644, Size: int64(len(content))}
	if err := tw.WriteHeader(hdr); err != nil {
		t.Fatal(err)
	}
	if _, err := tw.Write(content); err != nil {
		t.Fatal(err)
	}
	_ = tw.Close()
	_ = gz.Close()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(buf.Bytes())
	}))
	defer srv.Close()

	dir := filepath.Join(t.TempDir(), "inputs")
	res, err := Materialize(context.Background(), nil, Source{
		URL:             srv.URL + "/bundle.tar.gz",
		AllowPrivateURL: true,
	}, dir)
	if err != nil {
		t.Fatal(err)
	}
	if res.ManifestPath == "" {
		t.Fatalf("missing manifest: %+v", res)
	}
}

func TestHashStable(t *testing.T) {
	a := hashFiles(map[string][]byte{"b": []byte("2"), "a": []byte("1")})
	b := hashFiles(map[string][]byte{"a": []byte("1"), "b": []byte("2")})
	if a != b {
		t.Fatalf("hash not stable: %s vs %s", a, b)
	}
}
