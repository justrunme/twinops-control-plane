package workspace

import (
	"strings"
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

func TestManagedUsesUID(t *testing.T) {
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "assembly-line-a",
			Namespace: "twinops-system",
			UID:       "abc-123",
		},
	}
	path := Managed(twin)
	if !strings.HasPrefix(path, Root+"/") {
		t.Fatalf("path %s not under root", path)
	}
	if !strings.Contains(path, "abc-123") {
		t.Fatalf("expected uid in path: %s", path)
	}
	if strings.Contains(path, "assembly-line-a") {
		// Name is only used when UID empty — prefer UID isolation.
		t.Fatalf("expected uid-based path without name: %s", path)
	}
	if !IsManaged(twin, path) {
		t.Fatal("IsManaged should accept managed path")
	}
	if IsManaged(twin, "/tmp/twinops") {
		t.Fatal("parent root is not twin-owned")
	}
	if IsManaged(twin, "/var/lib/twinops/other") {
		t.Fatal("user path must not be managed")
	}
	if CleanupPath(twin) != path {
		t.Fatal("cleanup path mismatch")
	}
}
