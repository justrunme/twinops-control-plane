package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// DigitalTwinSpec defines the desired state of a digital twin.
type DigitalTwinSpec struct {
	// ManifestPath is a filesystem path to twin.yaml (dev / sidecar layout).
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
}

// DriftStatus summarizes three-way drift detection.
type DriftStatus struct {
	// Status is Detected, Synced, or Unknown.
	Status string `json:"status,omitempty"`
	// Findings is the number of non-SYNCED findings.
	Findings int `json:"findings,omitempty"`
	// Summary is a compact counter map encoded as string for CR readability.
	Summary string `json:"summary,omitempty"`
	// LastChecked is the last successful drift evaluation time.
	LastChecked *metav1.Time `json:"lastChecked,omitempty"`
}

// DigitalTwinStatus defines the observed state of a digital twin.
type DigitalTwinStatus struct {
	// Phase is Pending, Composing, Ready, DriftDetected, or Error.
	Phase string `json:"phase,omitempty"`
	// StagePath is the composed root.usda path.
	StagePath string `json:"stagePath,omitempty"`
	// Message is a human-readable status detail.
	Message string `json:"message,omitempty"`
	// Drift summarizes the latest drift evaluation.
	Drift DriftStatus `json:"drift,omitempty"`
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
