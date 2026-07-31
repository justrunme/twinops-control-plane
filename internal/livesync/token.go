package livesync

import (
	"context"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

// ResolveToken returns the live API bearer token for a DigitalTwin.
// SecretRef takes precedence over the plaintext liveAPIToken field.
func ResolveToken(ctx context.Context, c client.Client, twin *twinopsv1alpha1.DigitalTwin) (string, error) {
	if twin == nil {
		return "", nil
	}
	ref := twin.Spec.LiveAPITokenSecretRef
	if ref == nil || ref.Name == "" {
		return twin.Spec.LiveAPIToken, nil
	}
	if c == nil {
		return "", fmt.Errorf("client required to resolve liveAPITokenSecretRef")
	}
	var secret corev1.Secret
	key := client.ObjectKey{Namespace: twin.Namespace, Name: ref.Name}
	if err := c.Get(ctx, key, &secret); err != nil {
		return "", fmt.Errorf("read live API token secret %s/%s: %w", twin.Namespace, ref.Name, err)
	}
	secretKey := ref.Key
	if secretKey == "" {
		secretKey = "api-token"
	}
	raw, ok := secret.Data[secretKey]
	if !ok {
		return "", fmt.Errorf("secret %s/%s missing key %q", twin.Namespace, ref.Name, secretKey)
	}
	return string(raw), nil
}
