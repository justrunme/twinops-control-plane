package artifacts

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
)

func TestMaterializeConfigMap(t *testing.T) {
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
	dir := t.TempDir()
	res, err := Materialize(context.Background(), c, Source{
		Namespace:     "ns",
		ConfigMapName: "twin-inputs",
	}, dir)
	if err != nil {
		t.Fatal(err)
	}
	if res.ManifestPath == "" || res.DesiredPath == "" || res.ObservedPath == "" {
		t.Fatalf("missing paths: %+v", res)
	}
	if res.Digest == "" || res.Digest[:7] != "sha256:" {
		t.Fatalf("bad digest: %s", res.Digest)
	}
	if _, err := os.Stat(res.ManifestPath); err != nil {
		t.Fatal(err)
	}
}

func TestMaterializeTarGzURL(t *testing.T) {
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
		w.Header().Set("Content-Type", "application/gzip")
		_, _ = w.Write(buf.Bytes())
	}))
	defer srv.Close()

	dir := t.TempDir()
	res, err := Materialize(context.Background(), nil, Source{URL: srv.URL + "/bundle.tar.gz"}, dir)
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
