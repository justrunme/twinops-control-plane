package controllers

import (
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

func TestValidateRejectsTwinOpsCtlStylePathsAndSSRF(t *testing.T) {
	t.Parallel()
	r := &DigitalTwinReconciler{ManifestBaseDir: "/examples"}

	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "t", Namespace: "ns"},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ManifestPath: "/etc/passwd",
		},
	}
	_, _, _, err := r.validateAndResolvePaths(twin)
	if err == nil {
		t.Fatal("expected path rejection")
	}
	if _, ok := asPermanent(err); !ok {
		t.Fatalf("expected permanent error, got %T", err)
	}

	twin2 := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "t", Namespace: "ns"},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ArtifactSource: &twinopsv1alpha1.ArtifactSource{ConfigMapName: "cm"},
			LiveAPIURL:     "http://169.254.169.254/",
		},
	}
	_, _, _, err = r.validateAndResolvePaths(twin2)
	if err == nil {
		t.Fatal("expected liveAPIURL SSRF rejection")
	}

	twin3 := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "t", Namespace: "ns"},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ManifestPath: "/examples/assembly-line/twin.yaml",
		},
	}
	m, _, _, err := r.validateAndResolvePaths(twin3)
	if err != nil {
		t.Fatal(err)
	}
	if m != "/examples/assembly-line/twin.yaml" {
		t.Fatalf("got %s", m)
	}
}

func TestValidateRequiresBaseDir(t *testing.T) {
	t.Parallel()
	r := &DigitalTwinReconciler{}
	twin := &twinopsv1alpha1.DigitalTwin{
		Spec: twinopsv1alpha1.DigitalTwinSpec{ManifestPath: "/examples/x"},
	}
	_, _, _, err := r.validateAndResolvePaths(twin)
	if err == nil {
		t.Fatal("expected base dir requirement")
	}
}
