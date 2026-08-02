package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// ArtifactSource references twin inputs (preferred over hostPath).
// Set exactly one of ConfigMapName or URL. Prefer ExpectedDigest for immutability.
type ArtifactSource struct {
	// ConfigMapName loads twin.yaml (+ optional desired.yaml / telemetry.json) keys.
	// +optional
	ConfigMapName string `json:"configMapName,omitempty"`

	// URL fetches a .tar.gz / .zip bundle or a bare twin.yaml over HTTPS.
	// Private/loopback hosts are blocked unless the operator enables lab mode.
	// +optional
	URL string `json:"url,omitempty"`

	// ExpectedDigest is an optional sha256:<hex> of the materialized file set.
	// Reconcile fails closed on mismatch.
	// +optional
	ExpectedDigest string `json:"expectedDigest,omitempty"`
}

// OutputPublish controls durable publish of composed twin outputs.
type OutputPublish struct {
	// Enabled publishes composed stage files after a successful build.
	// +optional
	// +kubebuilder:default=true
	Enabled *bool `json:"enabled,omitempty"`

	// Mode selects the durable backend.
	// configmap — immutable ConfigMap revisions (lab/kind default)
	// oci — ORAS push to a container registry
	// s3 — object storage (S3 / MinIO compatible)
	// +optional
	// +kubebuilder:default=configmap
	// +kubebuilder:validation:Enum=configmap;oci;s3
	Mode string `json:"mode,omitempty"`

	// KeepRevisions is how many immutable revisions to retain (configmap mode).
	// +optional
	// +kubebuilder:default=5
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=50
	KeepRevisions int32 `json:"keepRevisions,omitempty"`

	// Repository is the OCI repository (e.g. ghcr.io/org/twinops-artifacts).
	// Required when mode=oci.
	// +optional
	Repository string `json:"repository,omitempty"`

	// RegistrySecretRef is a dockerconfigjson Secret for OCI push.
	// +optional
	RegistrySecretRef *SecretKeyRef `json:"registrySecretRef,omitempty"`

	// S3Bucket is required when mode=s3.
	// +optional
	S3Bucket string `json:"s3Bucket,omitempty"`

	// S3Prefix is an optional key prefix (default twinops/).
	// +optional
	S3Prefix string `json:"s3Prefix,omitempty"`

	// S3Endpoint overrides the AWS endpoint (MinIO / custom).
	// +optional
	S3Endpoint string `json:"s3Endpoint,omitempty"`

	// S3Region defaults to us-east-1 when empty.
	// +optional
	S3Region string `json:"s3Region,omitempty"`

	// S3SecretRef points to a Secret with access-key-id and secret-access-key.
	// +optional
	S3SecretRef *SecretKeyRef `json:"s3SecretRef,omitempty"`

	// S3PathStyle forces path-style addressing (MinIO).
	// +optional
	S3PathStyle bool `json:"s3PathStyle,omitempty"`
}

// BuildIsolation controls where twinopsctl build/drift executes.
type BuildIsolation struct {
	// Mode is inline (controller process, default) or job (Kubernetes Job).
	// +optional
	// +kubebuilder:default=inline
	// +kubebuilder:validation:Enum=inline;job
	Mode string `json:"mode,omitempty"`

	// ActiveDeadlineSeconds is Job timeout (default 300).
	// +optional
	ActiveDeadlineSeconds int64 `json:"activeDeadlineSeconds,omitempty"`

	// CPU request/limit for the Job container (e.g. 100m / 1).
	// +optional
	CPURequest string `json:"cpuRequest,omitempty"`
	// +optional
	CPULimit string `json:"cpuLimit,omitempty"`

	// Memory request/limit for the Job container (e.g. 128Mi / 512Mi).
	// +optional
	MemoryRequest string `json:"memoryRequest,omitempty"`
	// +optional
	MemoryLimit string `json:"memoryLimit,omitempty"`

	// Image overrides the worker image (defaults to operator image / env).
	// +optional
	Image string `json:"image,omitempty"`

	// ServiceAccountName for the Job Pod (defaults to twinops-build).
	// +optional
	ServiceAccountName string `json:"serviceAccountName,omitempty"`
}

// DigitalTwinSpec defines the desired state of a digital twin.
type DigitalTwinSpec struct {
	// ArtifactSource materializes twin inputs into the operator workspace.
	// When set, it takes precedence over filesystem manifestPath/desiredPath/observedPath.
	// +optional
	ArtifactSource *ArtifactSource `json:"artifactSource,omitempty"`

	// ManifestPath is a filesystem path to twin.yaml (legacy / hostPath demos).
	// +optional
	ManifestPath string `json:"manifestPath,omitempty"`

	// DesiredPath is a filesystem path to desired state YAML.
	// +optional
	DesiredPath string `json:"desiredPath,omitempty"`

	// ObservedPath is a filesystem path to observed telemetry JSON.
	// +optional
	ObservedPath string `json:"observedPath,omitempty"`

	// OutputDir is where composed USDA artifacts are written.
	// +optional
	OutputDir string `json:"outputDir,omitempty"`

	// OutputPublish publishes composed artifacts to a durable cluster reference.
	// Default: immutable ConfigMap revisions with digest + configmap:// URI.
	// +optional
	OutputPublish *OutputPublish `json:"outputPublish,omitempty"`

	// Build controls isolation of twinopsctl compose/drift (inline vs Job).
	// +optional
	Build *BuildIsolation `json:"build,omitempty"`

	// IntervalSeconds controls requeue period for continuous drift checks.
	// +optional
	// +kubebuilder:default=30
	IntervalSeconds int64 `json:"intervalSeconds,omitempty"`

	// TwinOpsCtl is an optional override for the twinopsctl binary path.
	// +optional
	TwinOpsCtl string `json:"twinopsctl,omitempty"`

	// LiveAPIURL is an optional TwinOps live API base URL for status sync.
	// +optional
	LiveAPIURL string `json:"liveAPIURL,omitempty"`

	// LiveAPIToken is an optional bearer token for the live API (demo auth).
	// Prefer LiveAPITokenSecretRef for anything beyond local demos.
	// +optional
	LiveAPIToken string `json:"liveAPIToken,omitempty"`

	// LiveAPITokenSecretRef loads the bearer token from a Secret in the same
	// namespace. When set, it takes precedence over liveAPIToken.
	// +optional
	LiveAPITokenSecretRef *SecretKeyRef `json:"liveAPITokenSecretRef,omitempty"`
}

// OutputRevision is one immutable published composition.
type OutputRevision struct {
	// Revision is the monotonic revision number.
	Revision int64 `json:"revision,omitempty"`
	// Digest is the content digest of the bundle.
	Digest string `json:"digest,omitempty"`
	// URI is the immutable reference (configmap://, oci://, s3://).
	URI string `json:"uri,omitempty"`
	// InputDigest is the input artifact digest that produced this revision.
	// +optional
	InputDigest string `json:"inputDigest,omitempty"`
	// PublishedAt is when this revision was written.
	// +optional
	PublishedAt *metav1.Time `json:"publishedAt,omitempty"`
}

// OutputArtifact is a durable reference to the last published composition.
type OutputArtifact struct {
	// Digest is sha256 of durable content files (sorted path+payload; excludes reports).
	// +optional
	Digest string `json:"digest,omitempty"`
	// URI is a cluster-stable reference, e.g. configmap://ns/name-output-r3 or oci://…@sha256:….
	// +optional
	URI string `json:"uri,omitempty"`
	// Revision increments when the published content digest changes.
	// +optional
	Revision int64 `json:"revision,omitempty"`
	// StageKey / StagePath is the primary stage entry inside the bundle (root.usda).
	// +optional
	StageKey string `json:"stageKey,omitempty"`
	// MediaType of the published blob (tar+gzip bundle).
	// +optional
	MediaType string `json:"mediaType,omitempty"`
	// BundleKey is the ConfigMap binaryData key (bundle.tar.gz).
	// +optional
	BundleKey string `json:"bundleKey,omitempty"`
	// PublishedAt is the last successful publish time.
	// +optional
	PublishedAt *metav1.Time `json:"publishedAt,omitempty"`
	// History is recent immutable revisions (newest last).
	// +optional
	History []OutputRevision `json:"history,omitempty"`
}

// BuildStatus reports isolated Job progress when spec.build.mode=job.
type BuildStatus struct {
	// Mode echoes the effective build isolation mode.
	// +optional
	Mode string `json:"mode,omitempty"`
	// JobName is the active or last Job for this generation.
	// +optional
	JobName string `json:"jobName,omitempty"`
	// Phase is Pending, Running, Succeeded, or Failed.
	// +optional
	Phase string `json:"phase,omitempty"`
	// Message is a human-readable build detail.
	// +optional
	Message string `json:"message,omitempty"`
}

// SecretKeyRef selects a key from a namespaced Secret.
type SecretKeyRef struct {
	// Name of the Secret.
	Name string `json:"name"`
	// Key within the Secret data map (default: api-token when empty at resolve time).
	// +optional
	Key string `json:"key,omitempty"`
}

// DriftStatus summarizes three-way drift detection.
type DriftStatus struct {
	// Status is Detected, Synced, or Unknown.
	Status string `json:"status,omitempty"`
	// Findings is the number of non-SYNCED findings.
	Findings int `json:"findings,omitempty"`
	// Critical is the CRITICAL finding count from the drift summary.
	// +optional
	Critical int `json:"critical,omitempty"`
	// Warning is the WARNING finding count from the drift summary.
	// +optional
	Warning int `json:"warning,omitempty"`
	// Summary is a compact counter map encoded as string for CR readability.
	Summary string `json:"summary,omitempty"`
	// ReportPath is the filesystem path to drift-report.json when available.
	// +optional
	ReportPath string `json:"reportPath,omitempty"`
	// LastChecked is the last successful drift evaluation time.
	LastChecked *metav1.Time `json:"lastChecked,omitempty"`
}

// LiveStatus summarizes the optional TwinOps live API probe.
type LiveStatus struct {
	// Ready is true when /api/ready reports ready.
	Ready bool `json:"ready,omitempty"`
	// Version is the twinopsctl/live API version string.
	Version string `json:"version,omitempty"`
	// Twin is the live twin name.
	Twin string `json:"twin,omitempty"`
	// HasDrift mirrors live /api/metrics hasDrift.
	HasDrift bool `json:"hasDrift,omitempty"`
	// HighlightedPrims is the count of highlighted OpenUSD prims.
	HighlightedPrims int `json:"highlightedPrims,omitempty"`
	// TimelineEvents is the live timeline length hint.
	TimelineEvents int `json:"timelineEvents,omitempty"`
	// LastSynced is the last successful live probe time.
	LastSynced *metav1.Time `json:"lastSynced,omitempty"`
	// Message is a probe error or status detail.
	Message string `json:"message,omitempty"`
}

// DigitalTwinStatus defines the observed state of a digital twin.
type DigitalTwinStatus struct {
	// Phase is Pending, Composing, Ready, DriftDetected, or Error.
	Phase string `json:"phase,omitempty"`
	// StagePath is the composed root.usda path (local to the operator pod).
	StagePath string `json:"stagePath,omitempty"`
	// ArtifactDigest is sha256 of materialized artifact inputs when artifactSource is used.
	// Deprecated alias of InputDigest — kept for 1.2 clients.
	// +optional
	ArtifactDigest string `json:"artifactDigest,omitempty"`
	// InputDigest is sha256 of materialized artifact inputs (preferred).
	// +optional
	InputDigest string `json:"inputDigest,omitempty"`
	// WorkspacePath is the materialized input directory when artifactSource is used.
	// +optional
	WorkspacePath string `json:"workspacePath,omitempty"`
	// Output is the durable published composition (URI + digest + history).
	// +optional
	Output OutputArtifact `json:"output,omitempty"`
	// Build reports Job isolation status when mode=job.
	// +optional
	Build BuildStatus `json:"build,omitempty"`
	// Message is a human-readable status detail.
	Message string `json:"message,omitempty"`
	// Drift summarizes the latest drift evaluation.
	Drift DriftStatus `json:"drift,omitempty"`
	// Live summarizes an optional live API probe when spec.liveAPIURL is set.
	// +optional
	Live LiveStatus `json:"live,omitempty"`
	// ObservedGeneration is the last reconciled generation.
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`
	// LastComposeGeneration is the generation for which compose+publish last succeeded.
	// +optional
	LastComposeGeneration int64 `json:"lastComposeGeneration,omitempty"`
	// LastComposeInputDigest is the input digest for the last successful compose.
	// +optional
	LastComposeInputDigest string `json:"lastComposeInputDigest,omitempty"`
	// Conditions mirror Kubernetes conventional status signals.
	Conditions []metav1.Condition `json:"conditions,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:shortName=dtwin
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="Drift",type=string,JSONPath=`.status.drift.status`
// +kubebuilder:printcolumn:name="Live",type=boolean,JSONPath=`.status.live.ready`
// +kubebuilder:printcolumn:name="Critical",type=integer,JSONPath=`.status.drift.critical`
// +kubebuilder:printcolumn:name="Findings",type=integer,JSONPath=`.status.drift.findings`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// DigitalTwin is the Schema for industrial digital twin reconciliation.
type DigitalTwin struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   DigitalTwinSpec   `json:"spec,omitempty"`
	Status DigitalTwinStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// DigitalTwinList contains a list of DigitalTwin.
type DigitalTwinList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []DigitalTwin `json:"items"`
}

func init() {
	SchemeBuilder.Register(&DigitalTwin{}, &DigitalTwinList{})
}
