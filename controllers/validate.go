package controllers

import (
	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
	"github.com/justrunme/twinops-control-plane/internal/livesync"
	"github.com/justrunme/twinops-control-plane/internal/workspace"
)

// permanentError marks a Spec problem that should not hot-loop (wait for generation change).
type permanentError struct {
	reason string
	msg    string
}

func (e *permanentError) Error() string { return e.msg }

func permanent(reason, msg string) error {
	return &permanentError{reason: reason, msg: msg}
}

func asPermanent(err error) (*permanentError, bool) {
	pe, ok := err.(*permanentError)
	return pe, ok
}

// validateAndResolvePaths checks host filesystem paths against the operator allowlist
// and validates liveAPIURL. Returns resolved absolute paths (may be empty when using artifacts).
func (r *DigitalTwinReconciler) validateAndResolvePaths(twin *twinopsv1alpha1.DigitalTwin) (manifest, desired, observed string, err error) {
	hasArtifact := twin.Spec.ArtifactSource != nil &&
		(twin.Spec.ArtifactSource.ConfigMapName != "" || twin.Spec.ArtifactSource.URL != "")

	if !hasArtifact && twin.Spec.ManifestPath == "" {
		return "", "", "", permanent("InvalidSpec", "spec.artifactSource or spec.manifestPath is required")
	}

	resolve := func(field, path string) (string, error) {
		if path == "" {
			return "", nil
		}
		if r.ManifestBaseDir == "" {
			return "", permanent("InvalidSpec", "host filesystem paths require operator --manifest-base-dir")
		}
		abs, vErr := workspace.ValidateAllowlistedPath(r.ManifestBaseDir, path)
		if vErr != nil {
			return "", permanent("InvalidSpec", field+": "+vErr.Error())
		}
		return abs, nil
	}

	if twin.Spec.ManifestPath != "" {
		manifest, err = resolve("spec.manifestPath", twin.Spec.ManifestPath)
		if err != nil {
			return "", "", "", err
		}
	}
	if twin.Spec.DesiredPath != "" {
		desired, err = resolve("spec.desiredPath", twin.Spec.DesiredPath)
		if err != nil {
			return "", "", "", err
		}
	}
	if twin.Spec.ObservedPath != "" {
		observed, err = resolve("spec.observedPath", twin.Spec.ObservedPath)
		if err != nil {
			return "", "", "", err
		}
	}

	if twin.Spec.LiveAPIURL != "" {
		if vErr := livesync.ValidateURL(twin.Spec.LiveAPIURL, r.LiveAPIAllowPrivate, r.LiveAPIHostAllowlist); vErr != nil {
			return "", "", "", permanent("InvalidSpec", vErr.Error())
		}
	}
	return manifest, desired, observed, nil
}
