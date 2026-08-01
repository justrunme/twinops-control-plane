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
	if in.LiveAPITokenSecretRef != nil {
		in, out := &in.LiveAPITokenSecretRef, &out.LiveAPITokenSecretRef
		*out = new(SecretKeyRef)
		**out = **in
	}
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
