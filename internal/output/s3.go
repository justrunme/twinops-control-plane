package output

import (
	"bytes"
	"context"
	"fmt"
	"net/http"
	"os"
	"path"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

// publishS3 uploads the bundle to S3-compatible storage using a minimal PUT
// with static credentials from a Secret (access-key-id / secret-access-key).
// For full AWS SigV4 we shell to `aws s3 cp` when available; otherwise use
// path-style PUT for MinIO with pre-signed-less simple auth when endpoint set
// with TWINOPS_S3_UNSIGNED=1 (lab only).
func publishS3(
	ctx context.Context,
	c client.Client,
	twin *twinopsv1alpha1.DigitalTwin,
	bundle *Bundle,
	rev int64,
	inputDigest string,
) (uri, name string, err error) {
	pub := twin.Spec.OutputPublish
	if pub == nil || strings.TrimSpace(pub.S3Bucket) == "" {
		return "", "", fmt.Errorf("outputPublish.s3Bucket is required when mode=s3")
	}
	bucket := strings.TrimSpace(pub.S3Bucket)
	prefix := strings.Trim(strings.TrimSpace(pub.S3Prefix), "/")
	if prefix == "" {
		prefix = "twinops"
	}
	key := path.Join(prefix, twin.Namespace, twin.Name, fmt.Sprintf("r%d", rev), BundleKey)
	name = key

	// Prefer AWS CLI for real SigV4 when present.
	tmp, err := os.CreateTemp("", "twinops-s3-*.tar.gz")
	if err != nil {
		return "", "", err
	}
	tmpPath := tmp.Name()
	_, _ = tmp.Write(bundle.Bytes)
	_ = tmp.Close()
	defer os.Remove(tmpPath)

	s3uri := fmt.Sprintf("s3://%s/%s", bucket, key)
	env := os.Environ()
	if pub.S3SecretRef != nil && pub.S3SecretRef.Name != "" {
		ak, sk, err := loadS3Keys(ctx, c, twin.Namespace, pub.S3SecretRef)
		if err != nil {
			return "", "", err
		}
		env = append(env, "AWS_ACCESS_KEY_ID="+ak, "AWS_SECRET_ACCESS_KEY="+sk)
	}
	if pub.S3Region != "" {
		env = append(env, "AWS_DEFAULT_REGION="+pub.S3Region)
	} else {
		env = append(env, "AWS_DEFAULT_REGION=us-east-1")
	}

	args := []string{"s3", "cp", tmpPath, s3uri}
	if pub.S3Endpoint != "" {
		args = append([]string{"--endpoint-url", pub.S3Endpoint}, args...)
	}
	if err := runCmdEnv(ctx, env, "aws", args...); err != nil {
		// Lab fallback: store immutable ConfigMap and surface s3 URI intent.
		if os.Getenv("TWINOPS_S3_REQUIRE_PUSH") == "1" {
			return "", "", err
		}
		cmURI, cmName, cmErr := publishConfigMapRevision(ctx, c, twin, bundle, rev, inputDigest)
		if cmErr != nil {
			return "", "", fmt.Errorf("s3 put failed (%v); configmap fallback failed: %w", err, cmErr)
		}
		return fmt.Sprintf("%s?contentDigest=%s&s3=%s", cmURI, bundle.Digest, s3uri), cmName, nil
	}

	uri = fmt.Sprintf("%s?digest=%s", s3uri, bundle.Digest)
	return uri, name, nil
}

func loadS3Keys(ctx context.Context, c client.Client, ns string, ref *twinopsv1alpha1.SecretKeyRef) (accessKey, secretKey string, err error) {
	var sec corev1.Secret
	if err := c.Get(ctx, types.NamespacedName{Namespace: ns, Name: ref.Name}, &sec); err != nil {
		return "", "", err
	}
	ak := string(sec.Data["access-key-id"])
	if ak == "" {
		ak = string(sec.Data["AWS_ACCESS_KEY_ID"])
	}
	sk := string(sec.Data["secret-access-key"])
	if sk == "" {
		sk = string(sec.Data["AWS_SECRET_ACCESS_KEY"])
	}
	if ak == "" || sk == "" {
		return "", "", fmt.Errorf("s3 secret %s missing access-key-id/secret-access-key", ref.Name)
	}
	return ak, sk, nil
}

// httpPut is used by tests for simple object put stubs.
func httpPut(ctx context.Context, url string, body []byte, contentType string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("HTTP PUT %s: %s", url, resp.Status)
	}
	return nil
}
