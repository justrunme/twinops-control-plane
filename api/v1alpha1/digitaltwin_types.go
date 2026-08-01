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
	// StagePath is the composed root.usda path.
	StagePath string `json:"stagePath,omitempty"`
	// ArtifactDigest is sha256 of materialized artifact inputs when artifactSource is used.
	// +optional
	ArtifactDigest string `json:"artifactDigest,omitempty"`
	// WorkspacePath is the materialized input directory when artifactSource is used.
	// +optional
	WorkspacePath string `json:"workspacePath,omitempty"`
	// Message is a human-readable status detail.
	Message string `json:"message,omitempty"`
	// Drift summarizes the latest drift evaluation.
	Drift DriftStatus `json:"drift,omitempty"`
	// Live summarizes an optional live API probe when spec.liveAPIURL is set.
	// +optional
	Live LiveStatus `json:"live,omitempty"`
	// ObservedGeneration is the last reconciled generation.
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`
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
