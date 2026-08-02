// Package buildjob creates and watches Kubernetes Jobs for isolated twin builds.
package buildjob

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

const (
	labelTwin        = "twinops.io/twin"
	labelBuild       = "twinops.io/build"
	labelGeneration  = "twinops.io/generation"
	labelInputDigest = "twinops.io/input-digest"
	labelBuildResult = "twinops.io/build-result"
)

// Spec describes a build Job request.
type Spec struct {
	InputConfigMap             string
	InputDigest                string
	// Image is operator-configured only (env / Helm). Never taken from CR.
	Image string
	// ServiceAccountName is operator-configured only (env / Helm).
	ServiceAccountName         string
	DeadlineSeconds            int64
	CPURequest, CPULimit       string
	MemoryRequest, MemoryLimit string
	// PublishMode is configmap (default), oci, or s3.
	// When oci/s3, the Job publishes the bundle itself and only returns metadata.
	PublishMode string
	// OCI/S3 settings passed into the Job as env (controller materializes secrets).
	OCIRepository     string
	S3Bucket          string
	S3Prefix          string
	S3Endpoint        string
	S3Region          string
	S3PathStyle       bool
	RegistrySecretRef string // Secret name for dockerconfigjson
	S3SecretName      string // Secret with access-key-id / secret-access-key
	Revision          int64
	AllowLabFallback  bool
	// TwinUID for owner references on result ConfigMap.
	TwinUID types.UID
}

// DigestKey returns a short, name-safe key from an input digest (sha256:hex → first 12 hex).
func DigestKey(inputDigest string) string {
	d := strings.ToLower(strings.TrimSpace(inputDigest))
	d = strings.TrimPrefix(d, "sha256:")
	// Keep only hex for DNS-1123 safety.
	var b strings.Builder
	for _, r := range d {
		if (r >= '0' && r <= '9') || (r >= 'a' && r <= 'f') {
			b.WriteRune(r)
		}
	}
	d = b.String()
	// Require a real digest-like payload (at least 8 hex chars).
	if len(d) < 8 {
		return "unknown"
	}
	if len(d) > 12 {
		d = d[:12]
	}
	return d
}

// JobName returns a stable Job name keyed by twin + input digest (not generation).
// Changing the input ConfigMap content produces a new Job even when generation is unchanged.
func JobName(twin *twinopsv1alpha1.DigitalTwin, inputDigest string) string {
	return truncateName(fmt.Sprintf("%s-build-%s", twin.Name, DigestKey(inputDigest)), 63)
}

// ResultConfigMapName is where the Job writes compose result metadata (+ optional bundle for configmap mode).
func ResultConfigMapName(twin *twinopsv1alpha1.DigitalTwin, inputDigest string) string {
	return truncateName(fmt.Sprintf("%s-build-result-%s", twin.Name, DigestKey(inputDigest)), 63)
}

func truncateName(name string, max int) string {
	if len(name) <= max {
		return name
	}
	return name[:max]
}

// Ensure creates the Job if missing. Existing finished Jobs for a different digest are left
// for TTL/GC; callers must use JobName for the current inputDigest.
func Ensure(ctx context.Context, c client.Client, twin *twinopsv1alpha1.DigitalTwin, spec Spec) (*batchv1.Job, error) {
	if spec.InputDigest == "" {
		return nil, fmt.Errorf("build job requires input digest")
	}
	name := JobName(twin, spec.InputDigest)
	var job batchv1.Job
	key := types.NamespacedName{Namespace: twin.Namespace, Name: name}
	err := c.Get(ctx, key, &job)
	if err == nil {
		return &job, nil
	}
	if !apierrors.IsNotFound(err) {
		return nil, err
	}

	if spec.Image == "" {
		spec.Image = os.Getenv("TWINOPS_BUILD_IMAGE")
	}
	if spec.Image == "" {
		spec.Image = os.Getenv("TWINOPS_OPERATOR_IMAGE")
	}
	if spec.Image == "" {
		return nil, fmt.Errorf("build job image not configured (set TWINOPS_BUILD_IMAGE / Helm buildImage)")
	}
	if spec.DeadlineSeconds <= 0 {
		spec.DeadlineSeconds = 300
	}
	if spec.ServiceAccountName == "" {
		spec.ServiceAccountName = os.Getenv("TWINOPS_BUILD_SERVICE_ACCOUNT")
	}
	if spec.ServiceAccountName == "" {
		spec.ServiceAccountName = "twinops-build"
	}
	if spec.CPURequest == "" {
		spec.CPURequest = "100m"
	}
	if spec.CPULimit == "" {
		spec.CPULimit = "1"
	}
	if spec.MemoryRequest == "" {
		spec.MemoryRequest = "128Mi"
	}
	if spec.MemoryLimit == "" {
		spec.MemoryLimit = "512Mi"
	}
	if spec.InputConfigMap == "" {
		return nil, fmt.Errorf("build job requires input ConfigMap")
	}
	if spec.PublishMode == "" {
		spec.PublishMode = "configmap"
	}

	resultCM := ResultConfigMapName(twin, spec.InputDigest)
	backoff := int32(1)
	ttl := int32(600)
	parallelism := int32(1)
	completions := int32(1)
	ctrl := true
	blockOwner := true

	env := []corev1.EnvVar{
		{
			Name: "POD_NAMESPACE",
			ValueFrom: &corev1.EnvVarSource{
				FieldRef: &corev1.ObjectFieldSelector{FieldPath: "metadata.namespace"},
			},
		},
		// Writable home for aws/oras under readOnlyRootFilesystem.
		{Name: "HOME", Value: "/tmp"},
		{Name: "TWINOPS_PUBLISH_MODE", Value: strings.ToLower(spec.PublishMode)},
		{Name: "TWINOPS_TWIN_NAME", Value: twin.Name},
		{Name: "TWINOPS_INPUT_DIGEST", Value: spec.InputDigest},
		{Name: "TWINOPS_OUTPUT_REVISION", Value: strconv.FormatInt(spec.Revision, 10)},
	}
	if spec.AllowLabFallback {
		env = append(env, corev1.EnvVar{Name: "TWINOPS_ALLOW_LAB_FALLBACK", Value: "1"})
	}
	// Propagate operator-level ORAS/S3 flags into the Job.
	for _, key := range []string{"TWINOPS_OCI_PLAIN_HTTP", "TWINOPS_OCI_INSECURE", "TWINOPS_OCI_PUSH_CMD"} {
		if v := os.Getenv(key); v != "" {
			env = append(env, corev1.EnvVar{Name: key, Value: v})
		}
	}
	if spec.OCIRepository != "" {
		env = append(env, corev1.EnvVar{Name: "TWINOPS_OCI_REPOSITORY", Value: spec.OCIRepository})
	}
	if spec.S3Bucket != "" {
		env = append(env, corev1.EnvVar{Name: "TWINOPS_S3_BUCKET", Value: spec.S3Bucket})
	}
	if spec.S3Prefix != "" {
		env = append(env, corev1.EnvVar{Name: "TWINOPS_S3_PREFIX", Value: spec.S3Prefix})
	}
	if spec.S3Endpoint != "" {
		env = append(env, corev1.EnvVar{Name: "TWINOPS_S3_ENDPOINT", Value: spec.S3Endpoint})
	}
	if spec.S3Region != "" {
		env = append(env, corev1.EnvVar{Name: "TWINOPS_S3_REGION", Value: spec.S3Region})
	}
	if spec.S3PathStyle {
		env = append(env, corev1.EnvVar{Name: "TWINOPS_S3_PATH_STYLE", Value: "1"})
	}

	volumeMounts := []corev1.VolumeMount{
		{Name: "work", MountPath: "/work"},
		{Name: "input", MountPath: "/input", ReadOnly: true},
		{Name: "tmp", MountPath: "/tmp"},
	}
	volumes := []corev1.Volume{
		{Name: "work", VolumeSource: corev1.VolumeSource{EmptyDir: &corev1.EmptyDirVolumeSource{}}},
		{Name: "tmp", VolumeSource: corev1.VolumeSource{EmptyDir: &corev1.EmptyDirVolumeSource{}}},
		{Name: "input", VolumeSource: corev1.VolumeSource{
			ConfigMap: &corev1.ConfigMapVolumeSource{
				LocalObjectReference: corev1.LocalObjectReference{Name: spec.InputConfigMap},
			},
		}},
	}

	// Registry credentials for ORAS (DOCKER_CONFIG).
	if spec.RegistrySecretRef != "" {
		volumes = append(volumes, corev1.Volume{
			Name: "docker-config",
			VolumeSource: corev1.VolumeSource{
				Secret: &corev1.SecretVolumeSource{
					SecretName: spec.RegistrySecretRef,
					Items: []corev1.KeyToPath{
						{Key: ".dockerconfigjson", Path: "config.json"},
					},
					Optional: boolPtr(true),
				},
			},
		})
		volumeMounts = append(volumeMounts, corev1.VolumeMount{
			Name: "docker-config", MountPath: "/var/run/secrets/twinops/docker", ReadOnly: true,
		})
		env = append(env, corev1.EnvVar{Name: "DOCKER_CONFIG", Value: "/var/run/secrets/twinops/docker"})
	}

	// S3 static credentials as env from Secret keys.
	if spec.S3SecretName != "" {
		env = append(env,
			corev1.EnvVar{
				Name: "AWS_ACCESS_KEY_ID",
				ValueFrom: &corev1.EnvVarSource{
					SecretKeyRef: &corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{Name: spec.S3SecretName},
						Key:                  "access-key-id",
						Optional:             boolPtr(true),
					},
				},
			},
			corev1.EnvVar{
				Name: "AWS_SECRET_ACCESS_KEY",
				ValueFrom: &corev1.EnvVarSource{
					SecretKeyRef: &corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{Name: spec.S3SecretName},
						Key:                  "secret-access-key",
						Optional:             boolPtr(true),
					},
				},
			},
		)
	}

	job = batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: twin.Namespace,
			Labels: map[string]string{
				labelTwin:        twin.Name,
				labelBuild:       "true",
				labelGeneration:  strconv.FormatInt(twin.Generation, 10),
				labelInputDigest: DigestKey(spec.InputDigest),
			},
			OwnerReferences: []metav1.OwnerReference{{
				APIVersion:         twinopsv1alpha1.GroupVersion.String(),
				Kind:               "DigitalTwin",
				Name:               twin.Name,
				UID:                twin.UID,
				Controller:         &ctrl,
				BlockOwnerDeletion: &blockOwner,
			}},
		},
		Spec: batchv1.JobSpec{
			BackoffLimit:            &backoff,
			TTLSecondsAfterFinished: &ttl,
			Parallelism:             &parallelism,
			Completions:             &completions,
			ActiveDeadlineSeconds:   &spec.DeadlineSeconds,
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						labelTwin:        twin.Name,
						labelBuild:       "true",
						labelInputDigest: DigestKey(spec.InputDigest),
					},
				},
				Spec: corev1.PodSpec{
					ServiceAccountName: spec.ServiceAccountName,
					RestartPolicy:      corev1.RestartPolicyNever,
					SecurityContext: &corev1.PodSecurityContext{
						RunAsNonRoot: boolPtr(true),
						RunAsUser:    int64Ptr(65532),
						RunAsGroup:   int64Ptr(65532),
						FSGroup:      int64Ptr(65532),
						SeccompProfile: &corev1.SeccompProfile{
							Type: corev1.SeccompProfileTypeRuntimeDefault,
						},
					},
					Containers: []corev1.Container{{
						Name:            "build",
						Image:           spec.Image,
						ImagePullPolicy: corev1.PullIfNotPresent,
						// Use shell so $POD_NAMESPACE expands.
						Command: []string{"/bin/sh", "-c"},
						Args: []string{
							fmt.Sprintf(
								`exec /usr/local/bin/twinops-job --input=/input --out=/work/out --result-cm=%s --namespace="$POD_NAMESPACE" --timeout=%ds`,
								resultCM,
								spec.DeadlineSeconds,
							),
						},
						Env: env,
						Resources: corev1.ResourceRequirements{
							Requests: corev1.ResourceList{
								corev1.ResourceCPU:    resource.MustParse(spec.CPURequest),
								corev1.ResourceMemory: resource.MustParse(spec.MemoryRequest),
							},
							Limits: corev1.ResourceList{
								corev1.ResourceCPU:    resource.MustParse(spec.CPULimit),
								corev1.ResourceMemory: resource.MustParse(spec.MemoryLimit),
							},
						},
						SecurityContext: &corev1.SecurityContext{
							AllowPrivilegeEscalation: boolPtr(false),
							ReadOnlyRootFilesystem:   boolPtr(true),
							RunAsNonRoot:             boolPtr(true),
							RunAsUser:                int64Ptr(65532),
							Capabilities:             &corev1.Capabilities{Drop: []corev1.Capability{"ALL"}},
							SeccompProfile:           &corev1.SeccompProfile{Type: corev1.SeccompProfileTypeRuntimeDefault},
						},
						VolumeMounts: volumeMounts,
					}},
					Volumes: volumes,
				},
			},
		},
	}

	if err := c.Create(ctx, &job); err != nil {
		return nil, err
	}
	return &job, nil
}

// DeleteResultConfigMap removes a single build-result ConfigMap.
func DeleteResultConfigMap(ctx context.Context, c client.Client, namespace, name string) error {
	cm := &corev1.ConfigMap{ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: namespace}}
	err := c.Delete(ctx, cm)
	if apierrors.IsNotFound(err) {
		return nil
	}
	return err
}

// CleanupResults deletes all build-result ConfigMaps for a twin.
func CleanupResults(ctx context.Context, c client.Client, namespace, twinName string) error {
	var list corev1.ConfigMapList
	if err := c.List(ctx, &list, client.InNamespace(namespace), client.MatchingLabels{
		labelTwin:        twinName,
		labelBuildResult: "true",
	}); err != nil {
		return err
	}
	for i := range list.Items {
		_ = c.Delete(ctx, &list.Items[i])
	}
	return nil
}

// Phase maps Job status to a simple string.
func Phase(job *batchv1.Job) string {
	if job == nil {
		return "Pending"
	}
	for _, c := range job.Status.Conditions {
		if c.Type == batchv1.JobComplete && c.Status == corev1.ConditionTrue {
			return "Succeeded"
		}
		if c.Type == batchv1.JobFailed && c.Status == corev1.ConditionTrue {
			return "Failed"
		}
	}
	if job.Status.Active > 0 {
		return "Running"
	}
	return "Pending"
}

// RequeueAfter suggests how long to wait for Job progress.
func RequeueAfter(job *batchv1.Job) time.Duration {
	switch Phase(job) {
	case "Succeeded", "Failed":
		return 0
	default:
		return 5 * time.Second
	}
}

func boolPtr(v bool) *bool    { return &v }
func int64Ptr(v int64) *int64 { return &v }
