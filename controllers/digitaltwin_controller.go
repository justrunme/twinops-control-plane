package controllers

import (
	"context"
	"fmt"
	"path/filepath"
	"time"

	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
	"github.com/justrunme/twinops-control-plane/internal/livesync"
	"github.com/justrunme/twinops-control-plane/internal/twinbuild"
)

const finalizerName = "twinops.io/finalizer"

// DigitalTwinReconciler reconciles DigitalTwin objects.
type DigitalTwinReconciler struct {
	client.Client
	Scheme *runtime.Scheme
	Runner twinbuild.Runner
}

// +kubebuilder:rbac:groups=twinops.io,resources=digitaltwins,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=twinops.io,resources=digitaltwins/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=twinops.io,resources=digitaltwins/finalizers,verbs=update

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

	if twin.Spec.ManifestPath == "" {
		return r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
			status.Phase = "Error"
			status.Message = "spec.manifestPath is required"
			status.ObservedGeneration = twin.Generation
		})
	}

	outputDir := twin.Spec.OutputDir
	if outputDir == "" {
		outputDir = filepath.Join("/tmp/twinops", twin.Namespace, twin.Name)
	}

	interval := twin.Spec.IntervalSeconds
	if interval <= 0 {
		interval = 30
	}

	runner := r.Runner
	if twin.Spec.TwinOpsCtl != "" {
		runner.Binary = twin.Spec.TwinOpsCtl
	}

	_, _ = r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
		status.Phase = "Composing"
		status.Message = "composing OpenUSD stage"
		status.ObservedGeneration = twin.Generation
	})

	stagePath, err := runner.Build(ctx, twin.Spec.ManifestPath, outputDir)
	if err != nil {
		logger.Error(err, "compose failed")
		_, _ = r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
			status.Phase = "Error"
			status.Message = err.Error()
			status.ObservedGeneration = twin.Generation
			setCondition(status, "Ready", metav1.ConditionFalse, "ComposeFailed", err.Error())
		})
		return ctrl.Result{RequeueAfter: time.Duration(interval) * time.Second}, nil
	}

	phase := "Ready"
	message := "stage composed"
	driftStatus := twinopsv1alpha1.DriftStatus{Status: "Unknown"}

	if twin.Spec.DesiredPath != "" && twin.Spec.ObservedPath != "" {
		driftOut := filepath.Join(outputDir, "drift")
		result, driftErr := runner.Drift(
			ctx,
			twin.Spec.DesiredPath,
			stagePath,
			twin.Spec.ObservedPath,
			twin.Spec.ManifestPath,
			driftOut,
		)
		if driftErr != nil {
			logger.Error(driftErr, "drift failed")
			phase = "Error"
			message = driftErr.Error()
			setReady := func(status *twinopsv1alpha1.DigitalTwinStatus) {
				status.Phase = phase
				status.Message = message
				status.StagePath = stagePath
				status.ObservedGeneration = twin.Generation
				setCondition(status, "Ready", metav1.ConditionFalse, "DriftFailed", driftErr.Error())
			}
			_, _ = r.patchStatus(ctx, &twin, setReady)
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
		snap, liveErr := livesync.Fetch(ctx, twin.Spec.LiveAPIURL, twin.Spec.LiveAPIToken)
		now := metav1.Now()
		if liveErr != nil {
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

	_, err = r.patchStatus(ctx, &twin, func(status *twinopsv1alpha1.DigitalTwinStatus) {
		status.Phase = phase
		status.Message = message
		status.StagePath = stagePath
		status.Drift = driftStatus
		status.Live = liveStatus
		status.ObservedGeneration = twin.Generation
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

	return ctrl.Result{RequeueAfter: time.Duration(interval) * time.Second}, nil
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
	return ctrl.NewControllerManagedBy(mgr).
		For(&twinopsv1alpha1.DigitalTwin{}).
		Complete(r)
}
