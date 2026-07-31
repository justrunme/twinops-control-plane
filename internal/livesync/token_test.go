package livesync

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

func TestResolveTokenPrefersSecretRef(t *testing.T) {
	scheme := runtime.NewScheme()
	_ = corev1.AddToScheme(scheme)
	_ = twinopsv1alpha1.AddToScheme(scheme)

	secret := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: "live-token", Namespace: "demo"},
		Data:       map[string][]byte{"api-token": []byte("from-secret")},
	}
	c := fake.NewClientBuilder().WithScheme(scheme).WithObjects(secret).Build()

	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "line", Namespace: "demo"},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			LiveAPIToken: "plaintext",
			LiveAPITokenSecretRef: &twinopsv1alpha1.SecretKeyRef{
				Name: "live-token",
			},
		},
	}
	got, err := ResolveToken(context.Background(), c, twin)
	if err != nil {
		t.Fatal(err)
	}
	if got != "from-secret" {
		t.Fatalf("got %q want from-secret", got)
	}
}

func TestResolveTokenFallsBackToPlaintext(t *testing.T) {
	twin := &twinopsv1alpha1.DigitalTwin{
		Spec: twinopsv1alpha1.DigitalTwinSpec{LiveAPIToken: "demo"},
	}
	got, err := ResolveToken(context.Background(), nil, twin)
	if err != nil {
		t.Fatal(err)
	}
	if got != "demo" {
		t.Fatalf("got %q want demo", got)
	}
}
