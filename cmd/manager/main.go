package main

import (
	"flag"
	"os"
	"strings"
	"time"

	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/cache"
	"sigs.k8s.io/controller-runtime/pkg/healthz"
	"sigs.k8s.io/controller-runtime/pkg/log/zap"
	metricsserver "sigs.k8s.io/controller-runtime/pkg/metrics/server"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
	"github.com/justrunme/twinops-control-plane/controllers"
	"github.com/justrunme/twinops-control-plane/internal/twinbuild"
)

var scheme = runtime.NewScheme()

func init() {
	utilruntime.Must(clientgoscheme.AddToScheme(scheme))
	utilruntime.Must(twinopsv1alpha1.AddToScheme(scheme))
}

func main() {
	var metricsAddr string
	var probeAddr string
	var enableLeaderElection bool
	var twinopsctl string
	var buildTimeout time.Duration
	var maxConcurrent int
	var watchNamespaces string

	flag.StringVar(&metricsAddr, "metrics-bind-address", ":8080", "metrics endpoint")
	flag.StringVar(&probeAddr, "health-probe-bind-address", ":8081", "health probe endpoint")
	flag.BoolVar(&enableLeaderElection, "leader-elect", false, "enable leader election")
	flag.StringVar(&twinopsctl, "twinopsctl", "", "path to twinopsctl binary")
	flag.DurationVar(&buildTimeout, "build-timeout", 120*time.Second, "timeout for twinopsctl build/drift")
	flag.IntVar(&maxConcurrent, "max-concurrent-reconciles", 2, "max concurrent DigitalTwin reconciles")
	flag.StringVar(&watchNamespaces, "watch-namespaces", "", "comma-separated namespaces to watch (empty = all / cluster-scoped)")
	opts := zap.Options{Development: true}
	opts.BindFlags(flag.CommandLine)
	flag.Parse()

	ctrl.SetLogger(zap.New(zap.UseFlagOptions(&opts)))
	setupLog := ctrl.Log.WithName("setup")

	mgrOpts := ctrl.Options{
		Scheme: scheme,
		Metrics: metricsserver.Options{
			BindAddress: metricsAddr,
		},
		HealthProbeBindAddress: probeAddr,
		LeaderElection:         enableLeaderElection,
		LeaderElectionID:       "twinops-control-plane.twinops.io",
	}
	if nsList := parseNamespaces(watchNamespaces); len(nsList) > 0 {
		setupLog.Info("namespace-scoped cache", "namespaces", nsList)
		nsMap := map[string]cache.Config{}
		for _, ns := range nsList {
			nsMap[ns] = cache.Config{}
		}
		mgrOpts.Cache = cache.Options{DefaultNamespaces: nsMap}
	}

	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), mgrOpts)
	if err != nil {
		setupLog.Error(err, "unable to start manager")
		os.Exit(1)
	}

	if err = (&controllers.DigitalTwinReconciler{
		Client:        mgr.GetClient(),
		Scheme:        mgr.GetScheme(),
		Runner:        twinbuild.Runner{Binary: twinopsctl},
		Recorder:      mgr.GetEventRecorderFor("twinops-controller"),
		BuildTimeout:  buildTimeout,
		MaxConcurrent: maxConcurrent,
	}).SetupWithManager(mgr); err != nil {
		setupLog.Error(err, "unable to create controller", "controller", "DigitalTwin")
		os.Exit(1)
	}

	if err := mgr.AddHealthzCheck("healthz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up health check")
		os.Exit(1)
	}
	if err := mgr.AddReadyzCheck("readyz", healthz.Ping); err != nil {
		setupLog.Error(err, "unable to set up ready check")
		os.Exit(1)
	}

	setupLog.Info("starting TwinOps manager")
	if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
		setupLog.Error(err, "problem running manager")
		os.Exit(1)
	}
}

func parseNamespaces(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}
