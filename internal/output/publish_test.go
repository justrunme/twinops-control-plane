package output

import (
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

func TestPublishDirConfigMap(t *testing.T) {
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
	if err := os.WriteFile(filepath.Join(dir, "root.usda"), []byte("#usda 1.0\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "overlay.usda"), []byte("#usda overlay\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	_ = os.Mkdir(filepath.Join(dir, "inputs"), 0o755)

	res, err := PublishDir(context.Background(), c, twin, dir, "sha256:input")
	if err != nil {
		t.Fatal(err)
	}
	if res.URI != "configmap://twinops-system/assembly-line-a-output" {
		t.Fatalf("uri: %s", res.URI)
	}
	if res.StageKey != "root.usda" {
		t.Fatalf("stageKey: %s", res.StageKey)
	}
	if res.Digest == "" {
		t.Fatal("empty digest")
	}

	var cm corev1.ConfigMap
	if err := c.Get(context.Background(), types.NamespacedName{
		Namespace: "twinops-system",
		Name:      "assembly-line-a-output",
	}, &cm); err != nil {
		t.Fatal(err)
	}
	if cm.Annotations["twinops.io/output-digest"] != res.Digest {
		t.Fatalf("annotation mismatch")
	}
	if string(cm.BinaryData["root.usda"]) != "#usda 1.0\n" {
		t.Fatalf("payload: %q", cm.BinaryData["root.usda"])
	}
}

func TestHashFilesStable(t *testing.T) {
	a := HashFiles(map[string][]byte{"b": []byte("2"), "a": []byte("1")})
	b := HashFiles(map[string][]byte{"a": []byte("1"), "b": []byte("2")})
	if a != b {
		t.Fatalf("%s vs %s", a, b)
	}
}
