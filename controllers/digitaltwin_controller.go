package controllers

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/tools/record"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/builder"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/handler"
	"sigs.k8s.io/controller-runtime/pkg/log"
	"sigs.k8s.io/controller-runtime/pkg/predicate"
	"sigs.k8s.io/controller-runtime/pkg/reconcile"

	batchv1 "k8s.io/api/batch/v1"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
	"github.com/justrunme/twinops-control-plane/internal/artifacts"
	"github.com/justrunme/twinops-control-plane/internal/buildjob"
	"github.com/justrunme/twinops-control-plane/internal/livesync"
	twinmetrics "github.com/justrunme/twinops-control-plane/internal/metrics"
	"github.com/justrunme/twinops-control-plane/internal/output"
	"github.com/justrunme/twinops-control-plane/internal/twinbuild"
	"github.com/justrunme/twinops-control-plane/internal/workspace"
)

const finalizerName = "twinops.io/finalizer"

// DigitalTwinReconciler reconciles DigitalTwin objects.
type DigitalTwinReconciler struct {
	client.Client
	Scheme   *runtime.Scheme
	Runner   twinbuild.Runner
	Recorder record.EventRecorder
	// BuildTimeout bounds twinopsctl build/drift subprocesses (default 120s).
	BuildTimeout time.Duration
	// MaxConcurrent is passed to controller options (default 2).
	MaxConcurrent int
}

// +kubebuilder:rbac:groups=twinops.io,resources=digitaltwins,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=twinops.io,resources=digitaltwins/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=twinops.io,resources=digitaltwins/finalizers,verbs=update
// +kubebuilder:rbac:groups="",resources=secrets,verbs=get;list;watch
// +kubebuilder:rbac:groups="",resources=configmaps,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=events,verbs=create;patch
// +kubebuilder:rbac:groups=batch,resources=jobs,verbs=get;list;watch;create;update;patch;delete

func (r *DigitalTwinReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	var twin twinopsv1alpha1.DigitalTwin
	if err := r.Get(ctx, req.NamespacedName, &twin); err != nil {
		if apierrors.IsNotFound(err) {
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	if !twin.DeletionTimestamp.IsZero() {
		if controllerutil.ContainsFinalizer(&twin, finalizerName) {
			// Only delete controller-owned workspace — never Spec.OutputDir (user path).
			managed := workspace.CleanupPath(&twin)
			if managed != "" {
				if err := os.RemoveAll(managed); err != nil {
					logger.Error(err, "workspace cleanup failed", "path", managed)
				}
			}
			if err := output.DeleteConfigMap(ctx, r.Client, twin.Namespace, twin.Name); err != nil {
				logger.Error(err, "output configmap cleanup failed")
			}
			if err := buildjob.CleanupResults(ctx, r.Client, twin.Namespace, twin.Name); err != nil {
				logger.Error(err, "build-result configmap cleanup failed")
			}
			controllerutil.RemoveFinalizer(&twin, finalizerName)
			if err := r.Update(ctx, &twin); err != nil {
				return ctrl.Result{}, err
			}
		}
		return ctrl.Result{}, nil
	}

	if !controllerutil.ContainsFinalizer(&twin, finalizerName) {
		controllerutil.AddFinalizer(&twin, finalizerName)
		if err := r.Update(ctx, &twin); err != nil {
			return ctrl.Result{}, err
		}
		return ctrl.Result{Requeue: true}, nil
	}

	// Always use managed workspace under /tmp/twinops/<ns>/<uid>.
	// Spec.OutputDir is legacy and ignored for write/cleanup safety.
	outputDir := workspace.Managed(&twin)
	prevPhase := twin.Status.Phase

	interval := twin.Spec.IntervalSeconds
	if interval <= 0 {
		interval = 30
	}

	timeout := r.BuildTimeout
	if timeout <= 0 {
		timeout = 120 * time.Second
	}
	buildCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	manifestPath := twin.Spec.ManifestPath
	desiredPath := twin.Spec.DesiredPath
	observedPath := twin.Spec.ObservedPath
	inputDigest := ""
	workspacePath := ""

	if twin.Spec.ArtifactSource != nil &&
		(twin.Spec.ArtifactSource.ConfigMapName != "" || twin.Spec.ArtifactSource.URL != "") {
		workspacePath = filepath.Join(outputDir, "inputs")
		allowPrivate := os.Getenv("TWINOPS_ARTIFACT_ALLOW_PRIVATE") == "1"
		requireDigest := os.Getenv("TWINOPS_ARTIFACT_REQUIRE_URL_DIGEST") == "1"
		res, matErr := artifacts.Materialize(buildCtx, r.Client, artifacts.Source{
			Namespace:             twin.Namespace,
			ConfigMapName:         twin.Spec.ArtifactSource.ConfigMapName,
			URL:                   twin.Spec.ArtifactSource.URL,
			ExpectedDigest:        twin.Spec.ArtifactSource.ExpectedDigest,
			AllowPrivateURL:       allowPrivate,
			RequireExpectedDigest: requireDigest,
		}, workspacePath)
		if matErr != nil {
			logger.Error(matErr, "artifact materialize failed")
			r.event(&twin, corev1.EventTypeWarning, "ArtifactFailed", matErr.Error())
			twinmetrics.ReconcileTotal.WithLabelValues("Error").Inc()
			return r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
				status.Phase = "Error"
				status.Message = matErr.Error()
				status.ObservedGeneration = twin.Generation
				setCondition(status, "Ready", metav1.ConditionFalse, "ArtifactFailed", matErr.Error())
			})
		}
		manifestPath = res.ManifestPath
		if res.DesiredPath != "" {
			desiredPath = res.DesiredPath
		} else {
			desiredPath = twin.Spec.DesiredPath
		}
		if res.ObservedPath != "" {
			observedPath = res.ObservedPath
		} else {
			observedPath = twin.Spec.ObservedPath
		}
		inputDigest = res.Digest
	}

	if manifestPath == "" {
		return r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
			status.Phase = "Error"
			status.Message = "spec.artifactSource or spec.manifestPath is required"
			status.ObservedGeneration = twin.Generation
		})
	}

	runner := r.Runner
	if twin.Spec.TwinOpsCtl != "" {
		runner.Binary = twin.Spec.TwinOpsCtl
	}

	buildMode := "inline"
	if twin.Spec.Build != nil && twin.Spec.Build.Mode != "" {
		buildMode = twin.Spec.Build.Mode
	}

	// Execution key: input digest + publish-spec fingerprint (mode/repo/bucket…).
	execKey := buildjob.ExecutionKey(inputDigest, twin.Spec.OutputPublish)

	// Build idempotency: skip when generation+input+publish-spec match and we already composed.
	skipCompose := twin.Status.LastComposeGeneration == twin.Generation &&
		inputDigest != "" &&
		twin.Status.LastComposeInputDigest == inputDigest &&
		(twin.Status.LastComposeExecKey == "" || twin.Status.LastComposeExecKey == execKey) &&
		twin.Status.Output.Digest != ""
	// If publish destination changed, force recompose even when input is unchanged.
	if twin.Status.LastComposeExecKey != "" && twin.Status.LastComposeExecKey != execKey {
		skipCompose = false
	}
	if !skipCompose && twin.Status.LastComposeGeneration == twin.Generation &&
		inputDigest != "" &&
		(twin.Status.InputDigest == inputDigest || twin.Status.ArtifactDigest == inputDigest) &&
		(twin.Status.LastComposeExecKey == "" || twin.Status.LastComposeExecKey == execKey) &&
		twin.Status.StagePath != "" {
		if _, err := os.Stat(twin.Status.StagePath); err == nil {
			skipCompose = true
		}
	}

	stagePath := twin.Status.StagePath
	outArtifact := twin.Status.Output
	// Job path may return structured drift (especially OCI/S3 without local stage).
	var jobDrift *twinopsv1alpha1.DriftStatus

	if !skipCompose {
		_, _ = r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
			status.Phase = "Composing"
			status.Message = "composing OpenUSD stage"
			status.ArtifactDigest = inputDigest
			status.InputDigest = inputDigest
			status.WorkspacePath = workspacePath
			status.ObservedGeneration = twin.Generation
			status.Build = twinopsv1alpha1.BuildStatus{Mode: buildMode, Phase: "Pending"}
		})

		if buildMode == "job" {
			res, requeue, err := r.composeViaJob(buildCtx, &twin, inputDigest, execKey, workspacePath)
			if err != nil {
				logger.Error(err, "job compose failed")
				r.event(&twin, corev1.EventTypeWarning, "ComposeFailed", err.Error())
				twinmetrics.ReconcileTotal.WithLabelValues("Error").Inc()
				_, _ = r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
					status.Phase = "Error"
					status.Message = err.Error()
					status.Build.Phase = "Failed"
					status.Build.Message = err.Error()
					status.ObservedGeneration = twin.Generation
					setCondition(status, "Ready", metav1.ConditionFalse, "ComposeFailed", err.Error())
				})
				return ctrl.Result{RequeueAfter: time.Duration(interval) * time.Second}, nil
			}
			if requeue > 0 {
				return ctrl.Result{RequeueAfter: requeue}, nil
			}
			stagePath = res.stagePath
			outArtifact = res.output
			if res.drift != nil {
				jobDrift = res.drift
			}
		} else {
			start := time.Now()
			var err error
			stagePath, err = runner.Build(buildCtx, manifestPath, outputDir)
			twinmetrics.ComposeSeconds.Observe(time.Since(start).Seconds())
			if err != nil {
				logger.Error(err, "compose failed")
				r.event(&twin, corev1.EventTypeWarning, "ComposeFailed", err.Error())
				twinmetrics.ReconcileTotal.WithLabelValues("Error").Inc()
				_, _ = r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
					status.Phase = "Error"
					status.Message = err.Error()
					status.ObservedGeneration = twin.Generation
					setCondition(status, "Ready", metav1.ConditionFalse, "ComposeFailed", err.Error())
				})
				return ctrl.Result{RequeueAfter: time.Duration(interval) * time.Second}, nil
			}

			if publishEnabled(twin.Spec.OutputPublish) {
				pub, pubErr := output.PublishDir(buildCtx, r.Client, &twin, outputDir, inputDigest)
				if pubErr != nil {
					logger.Error(pubErr, "output publish failed")
					r.event(&twin, corev1.EventTypeWarning, "PublishFailed", pubErr.Error())
					twinmetrics.ReconcileTotal.WithLabelValues("Error").Inc()
					_, _ = r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
						status.Phase = "Error"
						status.Message = pubErr.Error()
						status.StagePath = stagePath
						status.ObservedGeneration = twin.Generation
						setCondition(status, "Ready", metav1.ConditionFalse, "PublishFailed", pubErr.Error())
					})
					return ctrl.Result{RequeueAfter: time.Duration(interval) * time.Second}, nil
				}
				now := metav1.Now()
				outArtifact = twinopsv1alpha1.OutputArtifact{
					Digest:      pub.Digest,
					URI:         pub.URI,
					Revision:    pub.Revision,
					StageKey:    pub.StageKey,
					MediaType:   pub.MediaType,
					BundleKey:   pub.BundleKey,
					PublishedAt: &now,
					History:     pub.History,
				}
				if pub.Created {
					r.event(&twin, corev1.EventTypeNormal, "OutputPublished",
						fmt.Sprintf("published %s digest=%s rev=%d", pub.URI, pub.Digest, pub.Revision))
				}
			}
		}
	}

	phase := "Ready"
	message := "stage composed"
	// Preserve prior drift on skipCompose / OCI job paths without a local stage.
	// Otherwise interval requeues rewrite status.drift back to Unknown.
	driftStatus := twin.Status.Drift
	if driftStatus.Status == "" {
		driftStatus = twinopsv1alpha1.DriftStatus{Status: "Unknown"}
	}

	// Prefer structured drift returned from Job (incl. OCI/S3 remote path).
	if jobDrift != nil {
		driftStatus = *jobDrift
	}

	// Apply phase/message from effective drift status.
	switch driftStatus.Status {
	case "Detected":
		phase = "DriftDetected"
		if driftStatus.Summary != "" {
			message = fmt.Sprintf("drift detected (%s)", driftStatus.Summary)
		} else {
			message = "drift detected"
		}
	case "Synced":
		if driftStatus.Summary != "" {
			message = fmt.Sprintf("synced (%s)", driftStatus.Summary)
		} else {
			message = "synced"
		}
	case "Error":
		phase = "Error"
		message = driftStatus.Summary
		if message == "" {
			message = "drift evaluation failed"
		}
	}

	// Local drift needs a stage on disk. Job+OCI/S3 paths publish remotely and may
	// leave stagePath empty — use Job drift (and preserve above) instead of re-running.
	canDriftLocally := jobDrift == nil && desiredPath != "" && observedPath != "" && stagePath != ""
	if canDriftLocally {
		if _, err := os.Stat(stagePath); err != nil {
			canDriftLocally = false
		}
	}
	if canDriftLocally {
		driftOut := filepath.Join(outputDir, "drift")
		result, driftErr := runner.Drift(
			buildCtx,
			desiredPath,
			stagePath,
			observedPath,
			manifestPath,
			driftOut,
		)
		if driftErr != nil {
			logger.Error(driftErr, "drift failed")
			r.event(&twin, corev1.EventTypeWarning, "DriftFailed", driftErr.Error())
			phase = "Error"
			message = driftErr.Error()
			twinmetrics.ReconcileTotal.WithLabelValues("Error").Inc()
			_, _ = r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
				status.Phase = phase
				status.Message = message
				status.StagePath = stagePath
				status.ArtifactDigest = inputDigest
				status.InputDigest = inputDigest
				status.WorkspacePath = workspacePath
				status.Output = outArtifact
				status.ObservedGeneration = twin.Generation
				setCondition(status, "Ready", metav1.ConditionFalse, "DriftFailed", driftErr.Error())
			})
			return ctrl.Result{RequeueAfter: time.Duration(interval) * time.Second}, nil
		}

		now := metav1.Now()
		driftStatus = twinopsv1alpha1.DriftStatus{
			Status:      "Synced",
			Findings:    result.Findings,
			Critical:    result.Critical,
			Warning:     result.Warning,
			Summary:     result.Summary,
			ReportPath:  result.ReportPath,
			LastChecked: &now,
		}
		twinmetrics.DriftFindings.WithLabelValues(twin.Namespace, twin.Name).Set(float64(result.Findings))
		if result.HasDrift {
			driftStatus.Status = "Detected"
			phase = "DriftDetected"
			message = fmt.Sprintf("drift detected (%s)", result.Summary)
		} else {
			message = fmt.Sprintf("synced (%s)", result.Summary)
		}
	}

	liveStatus := twin.Status.Live
	if twin.Spec.LiveAPIURL != "" {
		token, tokenErr := livesync.ResolveToken(ctx, r.Client, &twin)
		now := metav1.Now()
		if tokenErr != nil {
			logger.Error(tokenErr, "live API token resolve failed")
			liveStatus = twinopsv1alpha1.LiveStatus{
				Ready:      false,
				Message:    tokenErr.Error(),
				LastSynced: &now,
			}
		} else if snap, liveErr := livesync.Fetch(ctx, twin.Spec.LiveAPIURL, token); liveErr != nil {
			logger.Error(liveErr, "live API probe failed")
			liveStatus = twinopsv1alpha1.LiveStatus{
				Ready:      false,
				Message:    liveErr.Error(),
				LastSynced: &now,
			}
		} else {
			liveStatus = twinopsv1alpha1.LiveStatus{
				Ready:            snap.Ready,
				Version:          snap.Version,
				Twin:             snap.Twin,
				HasDrift:         snap.HasDrift,
				HighlightedPrims: snap.HighlightedPrims,
				TimelineEvents:   snap.TimelineEvents,
				LastSynced:       &now,
				Message:          "live API probe ok",
			}
			if snap.HasDrift && phase == "Ready" {
				phase = "DriftDetected"
				message = fmt.Sprintf("%s; live hasDrift=true", message)
			}
		}
	}

	// Preserve / recompute Job identity so status.build.jobName stays populated.
	prevBuild := twin.Status.Build
	jobName := prevBuild.JobName
	if buildMode == "job" && jobName == "" && execKey != "" {
		jobName = buildjob.JobName(&twin, execKey)
	}
	_, err := r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
		status.Phase = phase
		status.Message = message
		status.StagePath = stagePath
		status.ArtifactDigest = inputDigest
		status.InputDigest = inputDigest
		status.WorkspacePath = workspacePath
		status.Output = outArtifact
		status.Drift = driftStatus
		status.Live = liveStatus
		status.ObservedGeneration = twin.Generation
		status.Build.Mode = buildMode
		if jobName != "" {
			status.Build.JobName = jobName
		}
		if !skipCompose {
			status.LastComposeGeneration = twin.Generation
			status.LastComposeInputDigest = inputDigest
			status.LastComposeExecKey = execKey
			status.Build.Phase = "Succeeded"
			if buildMode != "job" {
				status.Build.Mode = "inline"
			}
		}
		ready := metav1.ConditionTrue
		reason := "Reconciled"
		if phase == "DriftDetected" {
			reason = "DriftDetected"
		}
		if phase == "Error" {
			ready = metav1.ConditionFalse
			reason = "Error"
		}
		setCondition(status, "Ready", ready, reason, message)
	})
	if err != nil {
		return ctrl.Result{}, err
	}

	// Events only on phase transitions (avoid spam every interval).
	if phase != prevPhase {
		switch phase {
		case "Ready":
			r.event(&twin, corev1.EventTypeNormal, "Reconciled", message)
		case "DriftDetected":
			r.event(&twin, corev1.EventTypeWarning, "DriftDetected", message)
		case "Error":
			r.event(&twin, corev1.EventTypeWarning, "Error", message)
		}
	}
	twinmetrics.ReconcileTotal.WithLabelValues(phase).Inc()
	return ctrl.Result{RequeueAfter: time.Duration(interval) * time.Second}, nil
}

type jobComposeResult struct {
	stagePath string
	output    twinopsv1alpha1.OutputArtifact
	drift     *twinopsv1alpha1.DriftStatus
}

// composeViaJob ensures a build Job keyed by execution key (input + publish-spec),
// waits for success, then publishes durable output (or accepts Job-side OCI/S3 metadata).
func (r *DigitalTwinReconciler) composeViaJob(
	ctx context.Context,
	twin *twinopsv1alpha1.DigitalTwin,
	inputDigest, execKey, workspacePath string,
) (jobComposeResult, time.Duration, error) {
	var zero jobComposeResult
	inputCM := ""
	if twin.Spec.ArtifactSource != nil {
		inputCM = twin.Spec.ArtifactSource.ConfigMapName
	}
	if inputCM == "" {
		return zero, 0, fmt.Errorf("spec.build.mode=job requires artifactSource.configMapName")
	}
	if inputDigest == "" {
		return zero, 0, fmt.Errorf("spec.build.mode=job requires a materialized input digest")
	}
	if execKey == "" {
		execKey = buildjob.ExecutionKey(inputDigest, twin.Spec.OutputPublish)
	}

	// Image / SA are operator-configured only (env from Helm) — never from CR.
	spec := buildjob.Spec{
		InputConfigMap: inputCM,
		InputDigest:    inputDigest,
		ExecKey:        execKey,
		TwinUID:        twin.UID,
		Revision:       twin.Status.Output.Revision + 1,
	}
	if spec.Revision <= 0 {
		spec.Revision = 1
	}
	if twin.Spec.Build != nil {
		spec.DeadlineSeconds = twin.Spec.Build.ActiveDeadlineSeconds
		spec.CPURequest = twin.Spec.Build.CPURequest
		spec.CPULimit = twin.Spec.Build.CPULimit
		spec.MemoryRequest = twin.Spec.Build.MemoryRequest
		spec.MemoryLimit = twin.Spec.Build.MemoryLimit
	}
	pubMode := "configmap"
	if twin.Spec.OutputPublish != nil && twin.Spec.OutputPublish.Mode != "" {
		pubMode = twin.Spec.OutputPublish.Mode
	}
	spec.PublishMode = pubMode
	if twin.Spec.OutputPublish != nil {
		if twin.Spec.OutputPublish.AllowLabFallback != nil && *twin.Spec.OutputPublish.AllowLabFallback {
			spec.AllowLabFallback = true
		}
		if twin.Spec.OutputPublish.Repository != "" {
			spec.OCIRepository = twin.Spec.OutputPublish.Repository
		}
		if twin.Spec.OutputPublish.RegistrySecretRef != nil {
			spec.RegistrySecretRef = twin.Spec.OutputPublish.RegistrySecretRef.Name
		}
		if twin.Spec.OutputPublish.S3Bucket != "" {
			spec.S3Bucket = twin.Spec.OutputPublish.S3Bucket
			spec.S3Prefix = twin.Spec.OutputPublish.S3Prefix
			spec.S3Endpoint = twin.Spec.OutputPublish.S3Endpoint
			spec.S3Region = twin.Spec.OutputPublish.S3Region
			spec.S3PathStyle = twin.Spec.OutputPublish.S3PathStyle
		}
		if twin.Spec.OutputPublish.S3SecretRef != nil {
			spec.S3SecretName = twin.Spec.OutputPublish.S3SecretRef.Name
		}
	}

	job, err := buildjob.Ensure(ctx, r.Client, twin, spec)
	if err != nil {
		return zero, 0, err
	}
	phase := buildjob.Phase(job)
	_, _ = r.patchStatus(ctx, twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
		status.Build = twinopsv1alpha1.BuildStatus{
			Mode:    "job",
			JobName: job.Name,
			Phase:   phase,
		}
		status.Phase = "Composing"
		status.Message = "waiting for build Job " + job.Name
	})
	if phase == "Pending" || phase == "Running" {
		return zero, buildjob.RequeueAfter(job), nil
	}
	if phase == "Failed" {
		return zero, 0, fmt.Errorf("build Job %s failed", job.Name)
	}

	// Succeeded: read result ConfigMap.
	var cm corev1.ConfigMap
	cmName := buildjob.ResultConfigMapName(twin, execKey)
	if err := r.Get(ctx, types.NamespacedName{Namespace: twin.Namespace, Name: cmName}, &cm); err != nil {
		return zero, 5 * time.Second, nil // result may lag Job completion
	}
	// Ensure result ConfigMap is owned by the twin for GC (Jobs already have ownerRefs).
	if err := r.ensureResultOwner(ctx, twin, &cm); err != nil {
		return zero, 0, err
	}

	digest := cm.Annotations["twinops.io/output-digest"]
	if digest == "" {
		return zero, 0, fmt.Errorf("build result missing content digest annotation")
	}

	// Parse result.json for Job-side publish metadata + structured drift.
	var resultMeta struct {
		Published    bool   `json:"published"`
		URI          string `json:"uri"`
		PublishName  string `json:"publishName"`
		Revision     int64  `json:"revision"`
		PublishMode  string `json:"publishMode"`
		Drift        json.RawMessage `json:"drift"`
		DriftSummary string          `json:"driftSummary"`
	}
	if rawJSON, ok := cm.Data["result.json"]; ok && rawJSON != "" {
		_ = json.Unmarshal([]byte(rawJSON), &resultMeta)
	}

	// Apply Job drift into status (do not drop to Unknown on OCI/S3 path).
	var jobDrift *twinopsv1alpha1.DriftStatus
	if len(resultMeta.Drift) > 0 && string(resultMeta.Drift) != "null" {
		var dr struct {
			Ran      bool   `json:"ran"`
			OK       bool   `json:"ok"`
			Error    string `json:"error"`
			HasDrift bool   `json:"hasDrift"`
			Findings int    `json:"findings"`
			Critical int    `json:"critical"`
			Warning  int    `json:"warning"`
			Summary  string `json:"summary"`
			Status   string `json:"status"`
		}
		if err := json.Unmarshal(resultMeta.Drift, &dr); err == nil && (dr.Ran || dr.Status != "" || dr.Summary != "") {
			nowDrift := metav1.Now()
			ds := twinopsv1alpha1.DriftStatus{
				Findings:    dr.Findings,
				Critical:    dr.Critical,
				Warning:     dr.Warning,
				Summary:     dr.Summary,
				LastChecked: &nowDrift,
			}
			switch {
			case dr.Status != "":
				ds.Status = dr.Status
			case dr.HasDrift:
				ds.Status = "Detected"
			case dr.Ran:
				ds.Status = "Synced"
			default:
				ds.Status = "Unknown"
			}
			if dr.Error != "" && !dr.OK {
				ds.Status = "Error"
				ds.Summary = dr.Error
			}
			jobDrift = &ds
		}
	}
	if jobDrift == nil && resultMeta.DriftSummary != "" {
		nowDrift := metav1.Now()
		// Legacy string only — still better than Unknown with no detail.
		st := "Unknown"
		if strings.Contains(strings.ToUpper(resultMeta.DriftSummary), "CRITICAL") ||
			strings.Contains(strings.ToLower(resultMeta.DriftSummary), "drift") {
			st = "Detected"
		}
		jobDrift = &twinopsv1alpha1.DriftStatus{
			Status:      st,
			Summary:     resultMeta.DriftSummary,
			LastChecked: &nowDrift,
		}
	}
	// Annotations are a durable fallback when result.json parsing lags older jobs.
	if jobDrift == nil {
		if st := cm.Annotations["twinops.io/drift-status"]; st != "" && st != "Unknown" {
			nowDrift := metav1.Now()
			jobDrift = &twinopsv1alpha1.DriftStatus{
				Status:      st,
				Summary:     cm.Annotations["twinops.io/drift-summary"],
				LastChecked: &nowDrift,
			}
		}
	}

	stagePath := ""
	raw := cm.BinaryData[output.BundleKey]
	if len(raw) > 0 {
		// Materialize stage into managed workspace for subsequent drift.
		stageDir := filepath.Join(workspace.Managed(twin), "out")
		_ = os.RemoveAll(stageDir)
		if err := os.MkdirAll(stageDir, 0o755); err != nil {
			return zero, 0, err
		}
		if err := output.UnpackBundle(bytes.NewReader(raw), stageDir); err != nil {
			return zero, 0, fmt.Errorf("unpack job result: %w", err)
		}
		stagePath = filepath.Join(stageDir, "root.usda")
	}
	// OCI/S3 path: no ConfigMap bundle bridge — stage stays remote; drift is jobDrift.

	outArtifact := twin.Status.Output
	now := metav1.Now()

	if resultMeta.Published && resultMeta.URI != "" {
		// Job already published to OCI/S3 — record status only (no ConfigMap re-bridge).
		rev := resultMeta.Revision
		if rev <= 0 {
			rev = twin.Status.Output.Revision + 1
			if rev <= 0 {
				rev = 1
			}
		}
		// Idempotent: same content digest + URI → keep existing revision.
		if twin.Status.Output.Digest == digest && twin.Status.Output.URI == resultMeta.URI {
			outArtifact = twin.Status.Output
		} else {
			hist := append([]twinopsv1alpha1.OutputRevision{}, twin.Status.Output.History...)
			hist = append(hist, twinopsv1alpha1.OutputRevision{
				Revision:    rev,
				Digest:      digest,
				URI:         resultMeta.URI,
				InputDigest: inputDigest,
				PublishedAt: &now,
			})
			keep := 5
			if twin.Spec.OutputPublish != nil && twin.Spec.OutputPublish.KeepRevisions > 0 {
				keep = int(twin.Spec.OutputPublish.KeepRevisions)
			}
			if len(hist) > keep {
				hist = hist[len(hist)-keep:]
			}
			outArtifact = twinopsv1alpha1.OutputArtifact{
				Digest:      digest,
				URI:         resultMeta.URI,
				Revision:    rev,
				StageKey:    output.StageEntry,
				MediaType:   output.MediaType,
				BundleKey:   output.BundleKey,
				PublishedAt: &now,
				History:     hist,
			}
			r.event(twin, corev1.EventTypeNormal, "OutputPublished",
				fmt.Sprintf("published %s digest=%s rev=%d (job)", resultMeta.URI, digest, rev))
		}
	} else if publishEnabled(twin.Spec.OutputPublish) {
		if len(raw) == 0 {
			return zero, 0, fmt.Errorf("build result ConfigMap %s missing bundle for configmap publish", cmName)
		}
		bundle := &output.Bundle{Bytes: raw, Digest: digest}
		pub, pubErr := output.PublishBundle(ctx, r.Client, twin, bundle, inputDigest)
		if pubErr != nil {
			return zero, 0, pubErr
		}
		outArtifact = twinopsv1alpha1.OutputArtifact{
			Digest:      pub.Digest,
			URI:         pub.URI,
			Revision:    pub.Revision,
			StageKey:    pub.StageKey,
			MediaType:   pub.MediaType,
			BundleKey:   pub.BundleKey,
			PublishedAt: &now,
			History:     pub.History,
		}
		if pub.Created {
			r.event(twin, corev1.EventTypeNormal, "OutputPublished",
				fmt.Sprintf("published %s digest=%s rev=%d", pub.URI, pub.Digest, pub.Revision))
		}
	}
	_ = workspacePath
	return jobComposeResult{stagePath: stagePath, output: outArtifact, drift: jobDrift}, 0, nil
}

func (r *DigitalTwinReconciler) ensureResultOwner(ctx context.Context, twin *twinopsv1alpha1.DigitalTwin, cm *corev1.ConfigMap) error {
	for _, o := range cm.OwnerReferences {
		if o.UID == twin.UID {
			return nil
		}
	}
	ctrl := true
	block := true
	cm.OwnerReferences = append(cm.OwnerReferences, metav1.OwnerReference{
		APIVersion:         twinopsv1alpha1.GroupVersion.String(),
		Kind:               "DigitalTwin",
		Name:               twin.Name,
		UID:                twin.UID,
		Controller:         &ctrl,
		BlockOwnerDeletion: &block,
	})
	if cm.Labels == nil {
		cm.Labels = map[string]string{}
	}
	cm.Labels["twinops.io/twin"] = twin.Name
	cm.Labels["twinops.io/build-result"] = "true"
	return r.Update(ctx, cm)
}

func publishEnabled(pub *twinopsv1alpha1.OutputPublish) bool {
	if pub == nil {
		return true // default on for pilot durability
	}
	if pub.Enabled == nil {
		return true
	}
	return *pub.Enabled
}

func (r *DigitalTwinReconciler) event(twin *twinopsv1alpha1.DigitalTwin, typ, reason, msg string) {
	if r.Recorder == nil {
		return
	}
	r.Recorder.Event(twin, typ, reason, msg)
}

func (r *DigitalTwinReconciler) patchStatus(
	ctx context.Context,
	twin *twinopsv1alpha1.DigitalTwin,
	mutate func(*twinopsv1alpha1.DigitalTwinStatus),
) (ctrl.Result, error) {
	latest := twin.DeepCopy()
	if err := r.Get(ctx, client.ObjectKeyFromObject(twin), latest); err != nil {
		return ctrl.Result{}, err
	}
	mutate(&latest.Status)
	if err := r.Status().Update(ctx, latest); err != nil {
		return ctrl.Result{}, err
	}
	twin.Status = latest.Status
	return ctrl.Result{}, nil
}

func setCondition(status *twinopsv1alpha1.DigitalTwinStatus, ctype string, condStatus metav1.ConditionStatus, reason, message string) {
	now := metav1.Now()
	for i := range status.Conditions {
		if status.Conditions[i].Type != ctype {
			continue
		}
		changed := status.Conditions[i].Status != condStatus ||
			status.Conditions[i].Reason != reason ||
			status.Conditions[i].Message != message
		status.Conditions[i].Status = condStatus
		status.Conditions[i].Reason = reason
		status.Conditions[i].Message = message
		status.Conditions[i].ObservedGeneration = status.ObservedGeneration
		// LastTransitionTime only when the condition actually changes.
		if changed {
			status.Conditions[i].LastTransitionTime = now
		}
		return
	}
	status.Conditions = append(status.Conditions, metav1.Condition{
		Type:               ctype,
		Status:             condStatus,
		Reason:             reason,
		Message:            message,
		LastTransitionTime: now,
		ObservedGeneration: status.ObservedGeneration,
	})
}

func (r *DigitalTwinReconciler) SetupWithManager(mgr ctrl.Manager) error {
	maxConc := r.MaxConcurrent
	if maxConc <= 0 {
		maxConc = 2
	}
	return ctrl.NewControllerManagedBy(mgr).
		For(&twinopsv1alpha1.DigitalTwin{}).
		Watches(
			&corev1.ConfigMap{},
			handler.EnqueueRequestsFromMapFunc(r.mapConfigMapToTwins),
			builder.WithPredicates(predicate.ResourceVersionChangedPredicate{}),
		).
		Watches(
			&batchv1.Job{},
			handler.EnqueueRequestsFromMapFunc(r.mapJobToTwin),
			builder.WithPredicates(predicate.ResourceVersionChangedPredicate{}),
		).
		WithOptions(controller.Options{MaxConcurrentReconciles: maxConc}).
		Complete(r)
}

func (r *DigitalTwinReconciler) mapJobToTwin(ctx context.Context, obj client.Object) []reconcile.Request {
	job, ok := obj.(*batchv1.Job)
	if !ok || job == nil {
		return nil
	}
	if job.Labels["twinops.io/build"] != "true" {
		return nil
	}
	name := job.Labels["twinops.io/twin"]
	if name == "" {
		return nil
	}
	return []reconcile.Request{{
		NamespacedName: types.NamespacedName{Namespace: job.Namespace, Name: name},
	}}
}

// mapConfigMapToTwins enqueues DigitalTwins whose artifactSource.configMapName matches.
func (r *DigitalTwinReconciler) mapConfigMapToTwins(ctx context.Context, obj client.Object) []reconcile.Request {
	cm, ok := obj.(*corev1.ConfigMap)
	if !ok || cm == nil {
		return nil
	}
	// Ignore self-published output / build-result ConfigMaps to avoid reconcile storms.
	if cm.Labels["twinops.io/output"] == "true" || cm.Labels["twinops.io/output"] == "index" || cm.Labels["twinops.io/build-result"] == "true" {
		return nil
	}
	var list twinopsv1alpha1.DigitalTwinList
	if err := r.List(ctx, &list, client.InNamespace(cm.Namespace)); err != nil {
		return nil
	}
	var reqs []reconcile.Request
	for i := range list.Items {
		twin := &list.Items[i]
		src := twin.Spec.ArtifactSource
		if src == nil || src.ConfigMapName == "" || src.ConfigMapName != cm.Name {
			continue
		}
		reqs = append(reqs, reconcile.Request{
			NamespacedName: types.NamespacedName{
				Namespace: twin.Namespace,
				Name:      twin.Name,
			},
		})
	}
	return reqs
}
