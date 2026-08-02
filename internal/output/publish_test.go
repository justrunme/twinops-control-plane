package output

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

func TestPublishImmutableRevisions(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = corev1.AddToScheme(scheme)
	_ = twinopsv1alpha1.AddToScheme(scheme)

	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "assembly-line-a",
			Namespace: "twinops-system",
			UID:       "uid-1",
		},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			OutputPublish: &twinopsv1alpha1.OutputPublish{
				Mode:          "configmap",
				KeepRevisions: 3,
			},
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(twin).Build()

	dir := t.TempDir()
	_ = os.MkdirAll(filepath.Join(dir, "assets"), 0o755)
	_ = os.WriteFile(filepath.Join(dir, "root.usda"), []byte("#usda 1.0\n(\n    subLayers = [@./assets/root.usda@]\n)\n"), 0o644)
	_ = os.WriteFile(filepath.Join(dir, "assets", "root.usda"), []byte("#usda 1.0\ndef Xform \"World\" {}\n"), 0o644)

	res1, err := PublishDir(context.Background(), c, twin, dir, "sha256:in1")
	if err != nil {
		t.Fatal(err)
	}
	if res1.Revision != 1 || !res1.Created {
		t.Fatalf("rev1: %+v", res1)
	}
	var cm corev1.ConfigMap
	if err := c.Get(context.Background(), types.NamespacedName{
		Namespace: "twinops-system",
		Name:      "assembly-line-a-output-r1",
	}, &cm); err != nil {
		t.Fatal(err)
	}
	if cm.Immutable == nil || !*cm.Immutable {
		t.Fatal("revision configmap should be immutable")
	}

	// Same content → no new revision
	twin.Status.Output.Digest = res1.Digest
	twin.Status.Output.URI = res1.URI
	twin.Status.Output.Revision = res1.Revision
	twin.Status.Output.History = res1.History
	res2, err := PublishDir(context.Background(), c, twin, dir, "sha256:in1")
	if err != nil {
		t.Fatal(err)
	}
	if res2.Created || res2.Revision != 1 {
		t.Fatalf("expected idempotent publish: %+v", res2)
	}

	// Change content → rev 2
	_ = os.WriteFile(filepath.Join(dir, "variant-overlay.usda"), []byte("#usda 1.0\n# v2\n"), 0o644)
	twin.Status.Output = twinopsv1alpha1.OutputArtifact{
		Digest: res1.Digest, URI: res1.URI, Revision: 1, History: res1.History,
	}
	res3, err := PublishDir(context.Background(), c, twin, dir, "sha256:in2")
	if err != nil {
		t.Fatal(err)
	}
	if res3.Revision != 2 || !res3.Created {
		t.Fatalf("rev2: %+v", res3)
	}
	if len(res3.History) != 2 {
		t.Fatalf("history: %+v", res3.History)
	}

	// Unpack still works
	extract := t.TempDir()
	if err := UnpackBundle(bytes.NewReader(cm.BinaryData[BundleKey]), extract); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(extract, "assets", "root.usda")); err != nil {
		t.Fatal(err)
	}
}

func TestPackTarGzDeterministic(t *testing.T) {
	files := map[string][]byte{"b.usda": []byte("b"), "a.usda": []byte("a")}
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

func TestParseOrasDigest(t *testing.T) {
	out := "Uploading ...\nPushed [registry] ghcr.io/org/repo:rev-1\nDigest: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
	got := parseOrasDigest(out)
	if got != "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" {
		t.Fatalf("got %q", got)
	}
	if parseOrasDigest("no digest here") != "" {
		t.Fatal("expected empty")
	}
}

func TestOCIS3FailClosedWithoutFallback(t *testing.T) {
	// Unset lab fallback env so fail-closed is enforced.
	t.Setenv("TWINOPS_ALLOW_LAB_FALLBACK", "0")
	t.Setenv("TWINOPS_OCI_PUSH_CMD", "false") // force push failure

	scheme := runtime.NewScheme()
	_ = corev1.AddToScheme(scheme)
	_ = twinopsv1alpha1.AddToScheme(scheme)

	dir := t.TempDir()
	_ = os.WriteFile(filepath.Join(dir, "root.usda"), []byte("#usda 1.0\ndef Xform \"World\" {}\n"), 0o644)
	bundle, err := BuildBundle(dir)
	if err != nil {
		t.Fatal(err)
	}

	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "t", Namespace: "ns", UID: "u1"},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			OutputPublish: &twinopsv1alpha1.OutputPublish{
				Mode:       "oci",
				Repository: "localhost:5000/twinops-artifacts",
				// AllowLabFallback intentionally nil/false
			},
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(twin).Build()
	_, _, err = publishOCI(context.Background(), c, twin, bundle, 1, "sha256:in")
	if err == nil {
		t.Fatal("expected fail-closed oci error")
	}
	if !strings.Contains(err.Error(), "fail-closed") {
		t.Fatalf("expected fail-closed message, got %v", err)
	}

	twin.Spec.OutputPublish = &twinopsv1alpha1.OutputPublish{
		Mode:     "s3",
		S3Bucket: "twinops",
	}
	// aws will fail (no credentials / no server)
	_, _, err = publishS3(context.Background(), c, twin, bundle, 1, "sha256:in")
	if err == nil {
		t.Fatal("expected fail-closed s3 error")
	}
	if !strings.Contains(err.Error(), "fail-closed") {
		t.Fatalf("expected fail-closed message, got %v", err)
	}
}

func TestOCILabFallbackWhenAllowed(t *testing.T) {
	t.Setenv("TWINOPS_ALLOW_LAB_FALLBACK", "0")
	t.Setenv("TWINOPS_OCI_PUSH_CMD", "false")

	scheme := runtime.NewScheme()
	_ = corev1.AddToScheme(scheme)
	_ = twinopsv1alpha1.AddToScheme(scheme)

	dir := t.TempDir()
	_ = os.WriteFile(filepath.Join(dir, "root.usda"), []byte("#usda 1.0\ndef Xform \"World\" {}\n"), 0o644)
	bundle, err := BuildBundle(dir)
	if err != nil {
		t.Fatal(err)
	}
	allow := true
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "t", Namespace: "ns", UID: "u1"},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			OutputPublish: &twinopsv1alpha1.OutputPublish{
				Mode:             "oci",
				Repository:       "localhost:5000/twinops-artifacts",
				AllowLabFallback: &allow,
			},
		},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(twin).Build()
	uri, name, err := publishOCI(context.Background(), c, twin, bundle, 1, "sha256:in")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(uri, "configmap://") || !strings.Contains(uri, "labFallback=1") {
		t.Fatalf("expected configmap lab fallback uri, got %s", uri)
	}
	if name == "" {
		t.Fatal("expected revision configmap name")
	}
}
