package main

import (
	"flag"
	"os"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/cache"
	"sigs.k8s.io/controller-runtime/pkg/client"
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
	var secretNamespaces string
	var manifestBaseDir string
	var liveAPIAllowPrivate bool
	var liveAPIHostAllowlist string
	var plmAllowPrivate bool
	var plmHostAllowlist string

	flag.StringVar(&metricsAddr, "metrics-bind-address", ":8080", "metrics endpoint")
	flag.StringVar(&probeAddr, "health-probe-bind-address", ":8081", "health probe endpoint")
	flag.BoolVar(&enableLeaderElection, "leader-elect", false, "enable leader election")
	flag.StringVar(&twinopsctl, "twinopsctl", "", "path to twinopsctl binary (operator-controlled; not a CR field)")
	flag.DurationVar(&buildTimeout, "build-timeout", 120*time.Second, "timeout for twinopsctl build/drift")
	flag.IntVar(&maxConcurrent, "max-concurrent-reconciles", 2, "max concurrent DigitalTwin reconciles")
	flag.StringVar(&watchNamespaces, "watch-namespaces", "", "comma-separated namespaces to watch (empty = all / cluster-scoped)")
	flag.StringVar(&secretNamespaces, "secret-namespaces", "", "namespaces where Secrets may be cached/read (empty defaults to POD_NAMESPACE or watch-namespaces)")
	flag.StringVar(&manifestBaseDir, "manifest-base-dir", "", "allowlisted base directory for spec.manifestPath/desiredPath/observedPath (empty rejects host paths)")
	flag.BoolVar(&liveAPIAllowPrivate, "live-api-allow-private", false, "allow loopback/link-local/private liveAPIURL hosts (lab only)")
	flag.StringVar(&liveAPIHostAllowlist, "live-api-host-allowlist", "", "comma-separated allowed liveAPIURL hostnames (empty = any non-blocked host)")
	flag.BoolVar(&plmAllowPrivate, "plm-allow-private", false, "allow loopback/link-local/private plm.url hosts (lab only)")
	flag.StringVar(&plmHostAllowlist, "plm-host-allowlist", "", "comma-separated allowed plm.url hostnames (empty = any non-blocked host)")
	opts := zap.Options{Development: true}
	opts.BindFlags(flag.CommandLine)
	flag.Parse()

	if env := strings.TrimSpace(os.Getenv("TWINOPS_MANIFEST_BASE_DIR")); env != "" && manifestBaseDir == "" {
		manifestBaseDir = env
	}
	if os.Getenv("TWINOPS_LIVE_API_ALLOW_PRIVATE") == "1" {
		liveAPIAllowPrivate = true
	}
	if env := strings.TrimSpace(os.Getenv("TWINOPS_LIVE_API_HOST_ALLOWLIST")); env != "" && liveAPIHostAllowlist == "" {
		liveAPIHostAllowlist = env
	}
	if os.Getenv("TWINOPS_PLM_ALLOW_PRIVATE") == "1" {
		plmAllowPrivate = true
	}
	if env := strings.TrimSpace(os.Getenv("TWINOPS_PLM_HOST_ALLOWLIST")); env != "" && plmHostAllowlist == "" {
		plmHostAllowlist = env
	}
	if env := strings.TrimSpace(os.Getenv("TWINOPS_SECRET_NAMESPACES")); env != "" && secretNamespaces == "" {
		secretNamespaces = env
	}

	ctrl.SetLogger(zap.New(zap.UseFlagOptions(&opts)))
	setupLog := ctrl.Log.WithName("setup")

	watchNS := parseCSV(watchNamespaces)
	secretNS := parseCSV(secretNamespaces)
	if len(secretNS) == 0 {
		secretNS = watchNS
	}
	if len(secretNS) == 0 {
		if podNS := strings.TrimSpace(os.Getenv("POD_NAMESPACE")); podNS != "" {
			secretNS = []string{podNS}
		} else {
			secretNS = []string{"twinops-system"}
		}
	}

	mgrOpts := ctrl.Options{
		Scheme: scheme,
		Metrics: metricsserver.Options{
			BindAddress: metricsAddr,
		},
		HealthProbeBindAddress: probeAddr,
		LeaderElection:         enableLeaderElection,
		LeaderElectionID:       "twinops-control-plane.twinops.io",
	}

	cacheOpts := cache.Options{}
	if len(watchNS) > 0 {
		setupLog.Info("namespace-scoped cache", "namespaces", watchNS)
		nsMap := map[string]cache.Config{}
		for _, ns := range watchNS {
			nsMap[ns] = cache.Config{}
		}
		cacheOpts.DefaultNamespaces = nsMap
	}
	// Never cache Secrets cluster-wide — RBAC is namespaced Roles only.
	secMap := map[string]cache.Config{}
	for _, ns := range secretNS {
		secMap[ns] = cache.Config{}
	}
	cacheOpts.ByObject = map[client.Object]cache.ByObject{
		&corev1.Secret{}: {Namespaces: secMap},
	}
	setupLog.Info("secret cache namespaces", "namespaces", secretNS)
	mgrOpts.Cache = cacheOpts

	mgr, err := ctrl.NewManager(ctrl.GetConfigOrDie(), mgrOpts)
	if err != nil {
		setupLog.Error(err, "unable to start manager")
		os.Exit(1)
	}

	if err = (&controllers.DigitalTwinReconciler{
		Client:               mgr.GetClient(),
		Scheme:               mgr.GetScheme(),
		Runner:               twinbuild.Runner{Binary: twinopsctl},
		Recorder:             mgr.GetEventRecorderFor("twinops-controller"),
		BuildTimeout:         buildTimeout,
		MaxConcurrent:        maxConcurrent,
		ManifestBaseDir:      manifestBaseDir,
		LiveAPIAllowPrivate:  liveAPIAllowPrivate,
		LiveAPIHostAllowlist: parseCSV(liveAPIHostAllowlist),
		PLMAllowPrivate:      plmAllowPrivate,
		PLMHostAllowlist:     parseCSV(plmHostAllowlist),
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

	setupLog.Info("starting TwinOps manager",
		"manifestBaseDir", manifestBaseDir,
		"liveAPIAllowPrivate", liveAPIAllowPrivate,
		"plmAllowPrivate", plmAllowPrivate,
		"secretNamespaces", secretNS,
	)
	if err := mgr.Start(ctrl.SetupSignalHandler()); err != nil {
		setupLog.Error(err, "problem running manager")
		os.Exit(1)
	}
}

func parseCSV(raw string) []string {
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
