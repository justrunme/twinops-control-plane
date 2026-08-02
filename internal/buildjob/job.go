// Package buildjob creates and watches Kubernetes Jobs for isolated twin builds.
package buildjob

import (
	"context"
	"fmt"
	"os"
	"strconv"
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
	labelTwin       = "twinops.io/twin"
	labelBuild      = "twinops.io/build"
	labelGeneration = "twinops.io/generation"
)

// Spec describes a build Job request.
type Spec struct {
	InputConfigMap             string
	Image                      string
	DeadlineSeconds            int64
	CPURequest, CPULimit       string
	MemoryRequest, MemoryLimit string
	ServiceAccountName         string
}

// JobName returns a stable Job name for the twin generation.
func JobName(twin *twinopsv1alpha1.DigitalTwin) string {
	return fmt.Sprintf("%s-build-%d", twin.Name, twin.Generation)
}

// ResultConfigMapName is where the Job writes the composed bundle + result.
func ResultConfigMapName(twin *twinopsv1alpha1.DigitalTwin) string {
	return fmt.Sprintf("%s-build-result-%d", twin.Name, twin.Generation)
}

// Ensure creates the Job if missing.
func Ensure(ctx context.Context, c client.Client, twin *twinopsv1alpha1.DigitalTwin, spec Spec) (*batchv1.Job, error) {
	name := JobName(twin)
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
		return nil, fmt.Errorf("build job image not configured (set spec.build.image or TWINOPS_BUILD_IMAGE)")
	}
	if spec.DeadlineSeconds <= 0 {
		spec.DeadlineSeconds = 300
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

	backoff := int32(1)
	ttl := int32(600)
	parallelism := int32(1)
	completions := int32(1)
	ctrl := true

	job = batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: twin.Namespace,
			Labels: map[string]string{
				labelTwin:       twin.Name,
				labelBuild:      "true",
				labelGeneration: strconv.FormatInt(twin.Generation, 10),
			},
			OwnerReferences: []metav1.OwnerReference{{
				APIVersion: twinopsv1alpha1.GroupVersion.String(),
				Kind:       "DigitalTwin",
				Name:       twin.Name,
				UID:        twin.UID,
				Controller: &ctrl,
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
						labelTwin:  twin.Name,
						labelBuild: "true",
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
						// Override operator ENTRYPOINT.
						Command: []string{"/usr/local/bin/twinops-job"},
						Args: []string{
							"--input=/input",
							"--out=/work/out",
							"--result-cm=" + ResultConfigMapName(twin),
							"--namespace=$(POD_NAMESPACE)",
							"--timeout=" + strconv.FormatInt(spec.DeadlineSeconds, 10) + "s",
						},
						Env: []corev1.EnvVar{
							{
								Name: "POD_NAMESPACE",
								ValueFrom: &corev1.EnvVarSource{
									FieldRef: &corev1.ObjectFieldSelector{FieldPath: "metadata.namespace"},
								},
							},
						},
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
						VolumeMounts: []corev1.VolumeMount{
							{Name: "work", MountPath: "/work"},
							{Name: "input", MountPath: "/input", ReadOnly: true},
							{Name: "tmp", MountPath: "/tmp"},
						},
					}},
					Volumes: []corev1.Volume{
						{Name: "work", VolumeSource: corev1.VolumeSource{EmptyDir: &corev1.EmptyDirVolumeSource{}}},
						{Name: "tmp", VolumeSource: corev1.VolumeSource{EmptyDir: &corev1.EmptyDirVolumeSource{}}},
						{Name: "input", VolumeSource: corev1.VolumeSource{
							ConfigMap: &corev1.ConfigMapVolumeSource{
								LocalObjectReference: corev1.LocalObjectReference{Name: spec.InputConfigMap},
							},
						}},
					},
				},
			},
		},
	}

	// Fix namespace arg — shell env substitution doesn't work in Args without shell.
	// Use env expansion via command wrapper.
	job.Spec.Template.Spec.Containers[0].Command = []string{"/bin/sh", "-c"}
	job.Spec.Template.Spec.Containers[0].Args = []string{
		fmt.Sprintf(
			`exec /usr/local/bin/twinops-job --input=/input --out=/work/out --result-cm=%s --namespace="$POD_NAMESPACE" --timeout=%ds`,
			ResultConfigMapName(twin),
			spec.DeadlineSeconds,
		),
	}

	if err := c.Create(ctx, &job); err != nil {
		return nil, err
	}
	return &job, nil
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
