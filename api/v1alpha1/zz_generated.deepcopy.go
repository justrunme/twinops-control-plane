package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	runtime "k8s.io/apimachinery/pkg/runtime"
)

func (in *DigitalTwin) DeepCopyInto(out *DigitalTwin) {
	*out = *in
	out.TypeMeta = in.TypeMeta
	in.ObjectMeta.DeepCopyInto(&out.ObjectMeta)
	in.Spec.DeepCopyInto(&out.Spec)
	in.Status.DeepCopyInto(&out.Status)
}

func (in *DigitalTwinSpec) DeepCopyInto(out *DigitalTwinSpec) {
	*out = *in
	if in.ArtifactSource != nil {
		in, out := &in.ArtifactSource, &out.ArtifactSource
		*out = new(ArtifactSource)
		**out = **in
	}
	if in.OutputPublish != nil {
		in, out := &in.OutputPublish, &out.OutputPublish
		*out = new(OutputPublish)
		(*in).DeepCopyInto(*out)
	}
	if in.Build != nil {
		in, out := &in.Build, &out.Build
		*out = new(BuildIsolation)
		**out = **in
	}
	if in.LiveAPITokenSecretRef != nil {
		in, out := &in.LiveAPITokenSecretRef, &out.LiveAPITokenSecretRef
		*out = new(SecretKeyRef)
		**out = **in
	}
}

func (in *OutputPublish) DeepCopyInto(out *OutputPublish) {
	*out = *in
	if in.Enabled != nil {
		in, out := &in.Enabled, &out.Enabled
		*out = new(bool)
		**out = **in
	}
	if in.RegistrySecretRef != nil {
		in, out := &in.RegistrySecretRef, &out.RegistrySecretRef
		*out = new(SecretKeyRef)
		**out = **in
	}
	if in.S3SecretRef != nil {
		in, out := &in.S3SecretRef, &out.S3SecretRef
		*out = new(SecretKeyRef)
		**out = **in
	}
}

func (in *OutputPublish) DeepCopy() *OutputPublish {
	if in == nil {
		return nil
	}
	out := new(OutputPublish)
	in.DeepCopyInto(out)
	return out
}

func (in *BuildIsolation) DeepCopyInto(out *BuildIsolation) {
	*out = *in
}

func (in *BuildIsolation) DeepCopy() *BuildIsolation {
	if in == nil {
		return nil
	}
	out := new(BuildIsolation)
	in.DeepCopyInto(out)
	return out
}

func (in *OutputRevision) DeepCopyInto(out *OutputRevision) {
	*out = *in
	if in.PublishedAt != nil {
		in, out := &in.PublishedAt, &out.PublishedAt
		*out = (*in).DeepCopy()
	}
}

func (in *OutputRevision) DeepCopy() *OutputRevision {
	if in == nil {
		return nil
	}
	out := new(OutputRevision)
	in.DeepCopyInto(out)
	return out
}

func (in *OutputArtifact) DeepCopyInto(out *OutputArtifact) {
	*out = *in
	if in.PublishedAt != nil {
		in, out := &in.PublishedAt, &out.PublishedAt
		*out = (*in).DeepCopy()
	}
	if in.History != nil {
		in, out := &in.History, &out.History
		*out = make([]OutputRevision, len(*in))
		for i := range *in {
			(*in)[i].DeepCopyInto(&(*out)[i])
		}
	}
}

func (in *OutputArtifact) DeepCopy() *OutputArtifact {
	if in == nil {
		return nil
	}
	out := new(OutputArtifact)
	in.DeepCopyInto(out)
	return out
}

func (in *BuildStatus) DeepCopyInto(out *BuildStatus) {
	*out = *in
}

func (in *BuildStatus) DeepCopy() *BuildStatus {
	if in == nil {
		return nil
	}
	out := new(BuildStatus)
	in.DeepCopyInto(out)
	return out
}

func (in *DigitalTwinSpec) DeepCopy() *DigitalTwinSpec {
	if in == nil {
		return nil
	}
	out := new(DigitalTwinSpec)
	in.DeepCopyInto(out)
	return out
}

func (in *ArtifactSource) DeepCopyInto(out *ArtifactSource) {
	*out = *in
}

func (in *ArtifactSource) DeepCopy() *ArtifactSource {
	if in == nil {
		return nil
	}
	out := new(ArtifactSource)
	in.DeepCopyInto(out)
	return out
}

func (in *SecretKeyRef) DeepCopyInto(out *SecretKeyRef) {
	*out = *in
}

func (in *SecretKeyRef) DeepCopy() *SecretKeyRef {
	if in == nil {
		return nil
	}
	out := new(SecretKeyRef)
	in.DeepCopyInto(out)
	return out
}

func (in *DigitalTwin) DeepCopy() *DigitalTwin {
	if in == nil {
		return nil
	}
	out := new(DigitalTwin)
	in.DeepCopyInto(out)
	return out
}

func (in *DigitalTwin) DeepCopyObject() runtime.Object {
	return in.DeepCopy()
}

func (in *DigitalTwinList) DeepCopyInto(out *DigitalTwinList) {
	*out = *in
	out.TypeMeta = in.TypeMeta
	in.ListMeta.DeepCopyInto(&out.ListMeta)
	if in.Items != nil {
		in, out := &in.Items, &out.Items
		*out = make([]DigitalTwin, len(*in))
		for i := range *in {
			(*in)[i].DeepCopyInto(&(*out)[i])
		}
	}
}

func (in *DigitalTwinList) DeepCopy() *DigitalTwinList {
	if in == nil {
		return nil
	}
	out := new(DigitalTwinList)
	in.DeepCopyInto(out)
	return out
}

func (in *DigitalTwinList) DeepCopyObject() runtime.Object {
	return in.DeepCopy()
}

func (in *DigitalTwinStatus) DeepCopyInto(out *DigitalTwinStatus) {
	*out = *in
	in.Output.DeepCopyInto(&out.Output)
	out.Build = in.Build
	in.Drift.DeepCopyInto(&out.Drift)
	in.Live.DeepCopyInto(&out.Live)
	if in.Conditions != nil {
		in, out := &in.Conditions, &out.Conditions
		*out = make([]metav1.Condition, len(*in))
		for i := range *in {
			(*in)[i].DeepCopyInto(&(*out)[i])
		}
	}
}

func (in *DriftStatus) DeepCopyInto(out *DriftStatus) {
	*out = *in
	if in.LastChecked != nil {
		in, out := &in.LastChecked, &out.LastChecked
		*out = (*in).DeepCopy()
	}
}

func (in *LiveStatus) DeepCopyInto(out *LiveStatus) {
	*out = *in
	if in.LastSynced != nil {
		in, out := &in.LastSynced, &out.LastSynced
		*out = (*in).DeepCopy()
	}
}
