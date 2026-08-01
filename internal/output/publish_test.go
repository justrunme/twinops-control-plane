package output

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

func TestPublishDirBundleIncludesAssets(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = corev1.AddToScheme(scheme)
	_ = twinopsv1alpha1.AddToScheme(scheme)

	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "assembly-line-a",
			Namespace: "twinops-system",
			UID:       "uid-1",
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(twin).Build()

	dir := t.TempDir()
	_ = os.MkdirAll(filepath.Join(dir, "assets"), 0o755)
	_ = os.MkdirAll(filepath.Join(dir, "inputs"), 0o755)
	_ = os.MkdirAll(filepath.Join(dir, "drift"), 0o755)
	if err := os.WriteFile(filepath.Join(dir, "root.usda"), []byte("#usda 1.0\n(\n    subLayers = [@./assets/root.usda@]\n)\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "variant-overlay.usda"), []byte("#usda 1.0\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "assets", "root.usda"), []byte("#usda 1.0\ndef Xform \"World\" {}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	// Volatile / excluded
	if err := os.WriteFile(filepath.Join(dir, "reconciliation-report.json"), []byte(`{"generatedAt":"now"}`), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "inputs", "twin.yaml"), []byte("x: 1\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "drift", "drift-report.json"), []byte(`{}`), 0o644); err != nil {
		t.Fatal(err)
	}

	res, err := PublishDir(context.Background(), c, twin, dir, "sha256:input")
	if err != nil {
		t.Fatal(err)
	}
	if res.URI != "configmap://twinops-system/assembly-line-a-output" {
		t.Fatalf("uri: %s", res.URI)
	}
	if res.BundleKey != BundleKey || res.MediaType != MediaType {
		t.Fatalf("bundle meta: %+v", res)
	}
	if res.StageKey != StageEntry {
		t.Fatalf("stageKey: %s", res.StageKey)
	}

	var cm corev1.ConfigMap
	if err := c.Get(context.Background(), types.NamespacedName{
		Namespace: "twinops-system",
		Name:      "assembly-line-a-output",
	}, &cm); err != nil {
		t.Fatal(err)
	}
	bundle := cm.BinaryData[BundleKey]
	if len(bundle) == 0 {
		t.Fatal("missing bundle.tar.gz")
	}

	extract := t.TempDir()
	if err := UnpackBundle(bytes.NewReader(bundle), extract); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(extract, "assets", "root.usda")); err != nil {
		t.Fatalf("assets/root.usda missing from bundle: %v", err)
	}
	if _, err := os.Stat(filepath.Join(extract, "root.usda")); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(extract, "reconciliation-report.json")); !os.IsNotExist(err) {
		t.Fatal("report should not be in content bundle")
	}
	if _, err := os.Stat(filepath.Join(extract, "inputs")); !os.IsNotExist(err) {
		t.Fatal("inputs/ should not be in content bundle")
	}

	// Deterministic: same content → same digest even if report changes on disk.
	_ = os.WriteFile(filepath.Join(dir, "reconciliation-report.json"), []byte(`{"generatedAt":"later"}`), 0o644)
	res2, err := PublishDir(context.Background(), c, twin, dir, "sha256:input")
	if err != nil {
		t.Fatal(err)
	}
	if res2.Digest != res.Digest {
		t.Fatalf("content digest not stable: %s vs %s", res.Digest, res2.Digest)
	}
}

func TestPackTarGzDeterministic(t *testing.T) {
	files := map[string][]byte{
		"b.usda": []byte("b"),
		"a.usda": []byte("a"),
	}
	a, err := packTarGz(files)
	if err != nil {
		t.Fatal(err)
	}
	b, err := packTarGz(files)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(a, b) {
		t.Fatal("tar.gz not deterministic")
	}
}

func TestHashFilesStable(t *testing.T) {
	a := HashFiles(map[string][]byte{"b": []byte("2"), "a": []byte("1")})
	b := HashFiles(map[string][]byte{"a": []byte("1"), "b": []byte("2")})
	if a != b {
		t.Fatalf("%s vs %s", a, b)
	}
}
