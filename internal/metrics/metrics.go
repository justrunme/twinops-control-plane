// Package metrics registers TwinOps operator Prometheus metrics.
package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"sigs.k8s.io/controller-runtime/pkg/metrics"
)

var (
	// ReconcileTotal counts reconcile outcomes by phase.
	ReconcileTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "twinops_reconcile_total",
		Help: "Total DigitalTwin reconciles by result phase",
	}, []string{"phase"})

	// ComposeSeconds is the compose duration histogram.
	ComposeSeconds = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "twinops_compose_duration_seconds",
		Help:    "Duration of twinopsctl build",
		Buckets: prometheus.DefBuckets,
	})

	// DriftFindings gauges latest drift finding count.
	DriftFindings = prometheus.NewGaugeVec(prometheus.GaugeOpts{
		Name: "twinops_drift_findings",
		Help: "Latest non-SYNCED drift findings by twin",
	}, []string{"namespace", "name"})
)

func init() {
	metrics.Registry.MustRegister(ReconcileTotal, ComposeSeconds, DriftFindings)
}
