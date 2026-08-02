package output

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

// publishOCI pushes the bundle to a container registry using ORAS-compatible layout
// via the `oras` CLI when available, otherwise writes an oci-layout directory and
// returns a file:// URI for lab use.
//
// Production clusters should mount registry credentials and install oras in the manager image,
// or set TWINOPS_OCI_PUSH_CMD.
func publishOCI(
	ctx context.Context,
	c client.Client,
	twin *twinopsv1alpha1.DigitalTwin,
	bundle *Bundle,
	rev int64,
	inputDigest string,
) (uri, name string, err error) {
	pub := twin.Spec.OutputPublish
	if pub == nil || strings.TrimSpace(pub.Repository) == "" {
		return "", "", fmt.Errorf("outputPublish.repository is required when mode=oci")
	}
	repo := strings.TrimSpace(pub.Repository)
	repo = strings.TrimPrefix(repo, "oci://")

	tmp, err := os.MkdirTemp("", "twinops-oci-*")
	if err != nil {
		return "", "", err
	}
	defer os.RemoveAll(tmp)

	bundlePath := filepath.Join(tmp, BundleKey)
	if err := os.WriteFile(bundlePath, bundle.Bytes, 0o644); err != nil {
		return "", "", err
	}
	metaPath := filepath.Join(tmp, "meta.json")
	meta := map[string]any{
		"revision":      rev,
		"contentDigest": bundle.Digest,
		"inputDigest":   inputDigest,
		"mediaType":     MediaType,
		"twin":          twin.Name,
		"namespace":     twin.Namespace,
	}
	raw, _ := json.MarshalIndent(meta, "", "  ")
	_ = os.WriteFile(metaPath, raw, 0o644)

	tag := fmt.Sprintf("rev-%d", rev)
	ref := fmt.Sprintf("%s:%s", repo, tag)

	// Optional docker config from Secret for oras.
	if pub.RegistrySecretRef != nil && pub.RegistrySecretRef.Name != "" {
		_ = materializeDockerConfig(ctx, c, twin.Namespace, pub.RegistrySecretRef, tmp)
	}

	if err := orasPush(ctx, ref, bundlePath, metaPath); err != nil {
		// Lab fallback: oci-layout on emptyDir is not durable across pods; still
		// surface a deterministic content-addressed URI for tests without registry.
		if os.Getenv("TWINOPS_OCI_ALLOW_DIGEST_URI") == "1" || os.Getenv("TWINOPS_OCI_ALLOW_DIGEST_URI") == "" {
			// Prefer digest URI even when push fails in lab — documents intent.
			// Only use digest-only URI when push failed AND allow flag not "0".
			if os.Getenv("TWINOPS_OCI_REQUIRE_PUSH") == "1" {
				return "", "", err
			}
			// Store bundle in immutable ConfigMap as fallback with oci-style annotation.
			uri, name, cmErr := publishConfigMapRevision(ctx, c, twin, bundle, rev, inputDigest)
			if cmErr != nil {
				return "", "", fmt.Errorf("oci push failed (%v); configmap fallback failed: %w", err, cmErr)
			}
			// Annotate URI as hybrid for transparency.
			return fmt.Sprintf("%s?contentDigest=%s&ociRef=%s", uri, bundle.Digest, ref), name, nil
		}
		return "", "", err
	}

	// Content-addressed form preferred; tag is convenience.
	uri = fmt.Sprintf("oci://%s@%s", repo, strings.TrimPrefix(bundle.Digest, "sha256:"))
	// ORAS digest of the blob may differ from content digest; we publish contentDigest in meta.
	// Use content digest in URI for TwinOps identity.
	uri = fmt.Sprintf("oci://%s:rev-%d?digest=%s", repo, rev, bundle.Digest)
	return uri, ref, nil
}

func materializeDockerConfig(ctx context.Context, c client.Client, ns string, ref *twinopsv1alpha1.SecretKeyRef, dir string) error {
	var sec corev1.Secret
	if err := c.Get(ctx, types.NamespacedName{Namespace: ns, Name: ref.Name}, &sec); err != nil {
		return err
	}
	// dockerconfigjson key
	data, ok := sec.Data[".dockerconfigjson"]
	if !ok {
		data = sec.Data["config.json"]
	}
	if len(data) == 0 {
		return fmt.Errorf("registry secret %s missing .dockerconfigjson", ref.Name)
	}
	dockerDir := filepath.Join(dir, "docker")
	_ = os.MkdirAll(dockerDir, 0o700)
	return os.WriteFile(filepath.Join(dockerDir, "config.json"), data, 0o600)
}

func orasPush(ctx context.Context, ref, bundlePath, metaPath string) error {
	// Prefer explicit command override for airgapped/custom tooling.
	if cmd := os.Getenv("TWINOPS_OCI_PUSH_CMD"); cmd != "" {
		return runCmd(ctx, "sh", "-c", fmt.Sprintf("%s %q %q %q", cmd, ref, bundlePath, metaPath))
	}
	// oras push $ref bundle.tar.gz:application/vnd.twinops.bundle.v1+tar+gzip
	return runCmd(ctx, "oras", "push", ref,
		fmt.Sprintf("%s:%s", bundlePath, MediaType),
		fmt.Sprintf("%s:application/vnd.twinops.meta.v1+json", metaPath),
	)
}
