package controllers

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
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

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
	"github.com/justrunme/twinops-control-plane/internal/artifacts"
	"github.com/justrunme/twinops-control-plane/internal/livesync"
	twinmetrics "github.com/justrunme/twinops-control-plane/internal/metrics"
	"github.com/justrunme/twinops-control-plane/internal/output"
	"github.com/justrunme/twinops-control-plane/internal/twinbuild"
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
			outputDir := twin.Spec.OutputDir
			if outputDir == "" {
				outputDir = filepath.Join("/tmp/twinops", twin.Namespace, twin.Name)
			}
			if err := os.RemoveAll(outputDir); err != nil {
				logger.Error(err, "workspace cleanup failed", "path", outputDir)
			}
			if err := output.DeleteConfigMap(ctx, r.Client, twin.Namespace, twin.Name); err != nil {
				logger.Error(err, "output configmap cleanup failed")
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

	outputDir := twin.Spec.OutputDir
	if outputDir == "" {
		outputDir = filepath.Join("/tmp/twinops", twin.Namespace, twin.Name)
	}

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

	// Build idempotency: skip compose when generation+input digest match and stage exists.
	skipCompose := twin.Status.LastComposeGeneration == twin.Generation &&
		inputDigest != "" &&
		(twin.Status.InputDigest == inputDigest || twin.Status.ArtifactDigest == inputDigest) &&
		twin.Status.StagePath != ""
	if skipCompose {
		if _, err := os.Stat(twin.Status.StagePath); err != nil {
			skipCompose = false
		}
	}

	stagePath := twin.Status.StagePath
	outArtifact := twin.Status.Output

	if !skipCompose {
		_, _ = r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
			status.Phase = "Composing"
			status.Message = "composing OpenUSD stage"
			status.ArtifactDigest = inputDigest
			status.InputDigest = inputDigest
			status.WorkspacePath = workspacePath
			status.ObservedGeneration = twin.Generation
		})

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
			rev := twin.Status.Output.Revision
			if twin.Status.Output.Digest != pub.Digest {
				rev++
			}
			if rev == 0 {
				rev = 1
			}
			outArtifact = twinopsv1alpha1.OutputArtifact{
				Digest:      pub.Digest,
				URI:         pub.URI,
				Revision:    rev,
				StageKey:    pub.StageKey,
				PublishedAt: &now,
			}
			r.event(&twin, corev1.EventTypeNormal, "OutputPublished",
				fmt.Sprintf("published %s digest=%s rev=%d", pub.URI, pub.Digest, rev))
		}
	}

	phase := "Ready"
	message := "stage composed"
	driftStatus := twinopsv1alpha1.DriftStatus{Status: "Unknown"}

	if desiredPath != "" && observedPath != "" {
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
			r.event(&twin, corev1.EventTypeWarning, "DriftDetected", message)
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
		if !skipCompose {
			status.LastComposeGeneration = twin.Generation
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

	if phase == "Ready" {
		r.event(&twin, corev1.EventTypeNormal, "Reconciled", message)
	}
	twinmetrics.ReconcileTotal.WithLabelValues(phase).Inc()
	return ctrl.Result{RequeueAfter: time.Duration(interval) * time.Second}, nil
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
		if status.Conditions[i].Type == ctype {
			status.Conditions[i].Status = condStatus
			status.Conditions[i].Reason = reason
			status.Conditions[i].Message = message
			status.Conditions[i].LastTransitionTime = now
			status.Conditions[i].ObservedGeneration = status.ObservedGeneration
			return
		}
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
		WithOptions(controller.Options{MaxConcurrentReconciles: maxConc}).
		Complete(r)
}

// mapConfigMapToTwins enqueues DigitalTwins whose artifactSource.configMapName matches.
func (r *DigitalTwinReconciler) mapConfigMapToTwins(ctx context.Context, obj client.Object) []reconcile.Request {
	cm, ok := obj.(*corev1.ConfigMap)
	if !ok || cm == nil {
		return nil
	}
	// Ignore self-published output ConfigMaps to avoid reconcile storms.
	if cm.Labels["twinops.io/output"] == "true" {
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
