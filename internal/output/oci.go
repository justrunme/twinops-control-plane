package output

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

var orasDigestRE = regexp.MustCompile(`(?i)Digest:\s*(sha256:[a-f0-9]{64})`)

// publishOCI pushes the bundle to a container registry using the `oras` CLI.
// Fail-closed by default: ConfigMap fallback only when AllowLabFallback is set.
// Returns an immutable content-addressed URI: oci://repo@sha256:<registry-manifest-digest>
// TwinOps content digest is recorded in meta.json and status.output.digest separately.
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

	env := os.Environ()
	if pub.RegistrySecretRef != nil && pub.RegistrySecretRef.Name != "" {
		dockerDir, derr := materializeDockerConfig(ctx, c, twin.Namespace, pub.RegistrySecretRef, tmp)
		if derr != nil {
			return "", "", fmt.Errorf("registry credentials: %w", derr)
		}
		env = append(env, "DOCKER_CONFIG="+dockerDir)
	}

	manifestDigest, pushErr := orasPush(ctx, env, ref, bundlePath, metaPath)
	if pushErr != nil {
		if allowLabFallback(pub) {
			uri, name, cmErr := publishConfigMapRevision(ctx, c, twin, bundle, rev, inputDigest)
			if cmErr != nil {
				return "", "", fmt.Errorf("oci push failed (%v); configmap fallback failed: %w", pushErr, cmErr)
			}
			return fmt.Sprintf("%s?contentDigest=%s&ociRef=%s&labFallback=1", uri, bundle.Digest, ref), name, nil
		}
		return "", "", fmt.Errorf("oci push failed (fail-closed; set allowLabFallback=true for lab only): %w", pushErr)
	}

	if manifestDigest == "" {
		// Prefer registry digest; fall back to content digest form if ORAS omitted it.
		manifestDigest = bundle.Digest
	}
	// Immutable form: repository@sha256:<registry-manifest-digest>
	digestOnly := strings.TrimPrefix(manifestDigest, "sha256:")
	if !strings.HasPrefix(manifestDigest, "sha256:") {
		manifestDigest = "sha256:" + digestOnly
	}
	uri = fmt.Sprintf("oci://%s@%s", repo, manifestDigest)
	return uri, ref, nil
}

// PublishOCIStandalone is used by twinops-job (no k8s client for CM fallback path preferred).
func PublishOCIStandalone(
	ctx context.Context,
	repository string,
	bundle *Bundle,
	rev int64,
	inputDigest, twinName, namespace string,
	env []string,
) (uri, ref string, err error) {
	repo := strings.TrimSpace(repository)
	repo = strings.TrimPrefix(repo, "oci://")
	if repo == "" {
		return "", "", fmt.Errorf("oci repository is required")
	}
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
		"twin":          twinName,
		"namespace":     namespace,
	}
	raw, _ := json.MarshalIndent(meta, "", "  ")
	_ = os.WriteFile(metaPath, raw, 0o644)

	tag := fmt.Sprintf("rev-%d", rev)
	ref = fmt.Sprintf("%s:%s", repo, tag)
	if env == nil {
		env = os.Environ()
	}
	manifestDigest, pushErr := orasPush(ctx, env, ref, bundlePath, metaPath)
	if pushErr != nil {
		return "", "", pushErr
	}
	if manifestDigest == "" {
		manifestDigest = bundle.Digest
	}
	if !strings.HasPrefix(manifestDigest, "sha256:") {
		manifestDigest = "sha256:" + strings.TrimPrefix(manifestDigest, "sha256:")
	}
	uri = fmt.Sprintf("oci://%s@%s", repo, manifestDigest)
	return uri, ref, nil
}

func materializeDockerConfig(ctx context.Context, c client.Client, ns string, ref *twinopsv1alpha1.SecretKeyRef, dir string) (dockerConfigDir string, err error) {
	var sec corev1.Secret
	if err := c.Get(ctx, types.NamespacedName{Namespace: ns, Name: ref.Name}, &sec); err != nil {
		return "", err
	}
	data, ok := sec.Data[".dockerconfigjson"]
	if !ok {
		data = sec.Data["config.json"]
	}
	if len(data) == 0 {
		return "", fmt.Errorf("registry secret %s missing .dockerconfigjson", ref.Name)
	}
	dockerDir := filepath.Join(dir, "docker")
	if err := os.MkdirAll(dockerDir, 0o700); err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(dockerDir, "config.json"), data, 0o600); err != nil {
		return "", err
	}
	return dockerDir, nil
}

func orasPush(ctx context.Context, env []string, ref, bundlePath, metaPath string) (manifestDigest string, err error) {
	if cmd := os.Getenv("TWINOPS_OCI_PUSH_CMD"); cmd != "" {
		// Custom push: receives $1=ref $2=bundlePath $3=metaPath
		script := fmt.Sprintf(`%s "$1" "$2:%s" "$3:application/vnd.twinops.meta.v1+json"`, cmd, MediaType)
		out, err := runCmdOut(ctx, env, "sh", "-c", script, "_", ref, bundlePath, metaPath)
		if err != nil {
			return "", err
		}
		return parseOrasDigest(out), nil
	}
	args := []string{"push"}
	// Local/kind registries without TLS (set TWINOPS_OCI_PLAIN_HTTP=1).
	if os.Getenv("TWINOPS_OCI_PLAIN_HTTP") == "1" || os.Getenv("TWINOPS_OCI_INSECURE") == "1" {
		args = append(args, "--plain-http")
	}
	args = append(args, ref,
		fmt.Sprintf("%s:%s", bundlePath, MediaType),
		fmt.Sprintf("%s:application/vnd.twinops.meta.v1+json", metaPath),
	)
	out, err := runCmdOut(ctx, env, "oras", args...)
	if err != nil {
		return "", err
	}
	return parseOrasDigest(out), nil
}

func parseOrasDigest(out string) string {
	m := orasDigestRE.FindStringSubmatch(out)
	if len(m) >= 2 {
		return m[1]
	}
	return ""
}

func allowLabFallback(pub *twinopsv1alpha1.OutputPublish) bool {
	if os.Getenv("TWINOPS_ALLOW_LAB_FALLBACK") == "1" {
		return true
	}
	return pub != nil && pub.AllowLabFallback != nil && *pub.AllowLabFallback
}
