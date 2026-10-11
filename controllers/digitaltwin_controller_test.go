package controllers

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientgoscheme "k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/record"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/envtest"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
	"github.com/justrunme/twinops-control-plane/internal/twinbuild"
	"github.com/justrunme/twinops-control-plane/internal/workspace"
)

var (
	testCfg    *rest.Config
	testClient client.Client
	testScheme = runtime.NewScheme()
)

func TestMain(m *testing.M) {
	utilruntime.Must(clientgoscheme.AddToScheme(testScheme))
	utilruntime.Must(batchv1.AddToScheme(testScheme))
	utilruntime.Must(twinopsv1alpha1.AddToScheme(testScheme))

	tmpRoot, err := os.MkdirTemp("", "twinops-ws-*")
	if err != nil {
		panic(err)
	}
	workspace.Root = tmpRoot

	env := &envtest.Environment{
		CRDDirectoryPaths:     []string{filepath.Join("..", "config", "crd", "bases")},
		ErrorIfCRDPathMissing: true,
	}
	cfg, err := env.Start()
	if err != nil {
		fmt.Fprintf(os.Stderr, "envtest start: %v\n", err)
		_ = os.RemoveAll(tmpRoot)
		os.Exit(1)
	}
	testCfg = cfg
	c, err := client.New(cfg, client.Options{Scheme: testScheme})
	if err != nil {
		fmt.Fprintf(os.Stderr, "client: %v\n", err)
		_ = env.Stop()
		_ = os.RemoveAll(tmpRoot)
		os.Exit(1)
	}
	testClient = c

	code := m.Run()
	_ = env.Stop()
	_ = os.RemoveAll(tmpRoot)
	os.Exit(code)
}

type fakeRunner struct {
	buildErr   error
	driftErr   error
	hasDrift   bool
	buildCalls int
	driftCalls int
}

func (f *fakeRunner) Build(_ context.Context, _, outputDir string) (string, error) {
	f.buildCalls++
	if f.buildErr != nil {
		return "", f.buildErr
	}
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return "", err
	}
	stage := filepath.Join(outputDir, "root.usda")
	if err := os.WriteFile(stage, []byte("#usda 1.0\n"), 0o644); err != nil {
		return "", err
	}
	return stage, nil
}

func (f *fakeRunner) Drift(_ context.Context, _, _, _, _, outDir string) (*twinbuild.Result, error) {
	f.driftCalls++
	if f.driftErr != nil {
		return nil, f.driftErr
	}
	_ = os.MkdirAll(outDir, 0o755)
	report := filepath.Join(outDir, "drift-report.json")
	_ = os.WriteFile(report, []byte(`{}`), 0o644)
	findings, critical, summary := 0, 0, "SYNCED=3"
	if f.hasDrift {
		findings, critical, summary = 2, 1, "CRITICAL=1"
	}
	return &twinbuild.Result{
		HasDrift:   f.hasDrift,
		Findings:   findings,
		Critical:   critical,
		Summary:    summary,
		ReportPath: report,
	}, nil
}

func boolPtr(v bool) *bool { return &v }

func conditionReason(conds []metav1.Condition, typ string) string {
	for _, c := range conds {
		if c.Type == typ {
			return c.Reason
		}
	}
	return ""
}

func conditionStatus(conds []metav1.Condition, typ string) metav1.ConditionStatus {
	for _, c := range conds {
		if c.Type == typ {
			return c.Status
		}
	}
	return ""
}

func setupNS(t *testing.T) (context.Context, string, *fakeRunner, *DigitalTwinReconciler) {
	t.Helper()
	ctx := context.Background()
	ns := fmt.Sprintf("twin-test-%d", time.Now().UnixNano())
	if err := testClient.Create(ctx, &corev1.Namespace{ObjectMeta: metav1.ObjectMeta{Name: ns}}); err != nil {
		t.Fatalf("create ns: %v", err)
	}
	base := filepath.Join(workspace.Root, "examples-"+ns)
	if err := os.MkdirAll(filepath.Join(base, "assembly-line"), 0o755); err != nil {
		t.Fatal(err)
	}
	_ = os.WriteFile(filepath.Join(base, "assembly-line", "twin.yaml"), []byte("name: t\n"), 0o644)

	runner := &fakeRunner{}
	r := &DigitalTwinReconciler{
		Client:          testClient,
		Scheme:          testScheme,
		Runner:          runner,
		Recorder:        record.NewFakeRecorder(64),
		BuildTimeout:    30 * time.Second,
		ManifestBaseDir: base,
	}
	return ctx, ns, runner, r
}

func TestReconcileHappyPath(t *testing.T) {
	ctx, ns, runner, r := setupNS(t)
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "twin-inputs", Namespace: ns},
		Data: map[string]string{
			"twin.yaml":      "name: assembly\n",
			"desired.yaml":   "line: ok\n",
			"telemetry.json": `{"temp":1}`,
		},
	}
	if err := testClient.Create(ctx, cm); err != nil {
		t.Fatal(err)
	}
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "happy", Namespace: ns},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ArtifactSource:  &twinopsv1alpha1.ArtifactSource{ConfigMapName: "twin-inputs"},
			IntervalSeconds: 30,
			OutputPublish:   &twinopsv1alpha1.OutputPublish{Enabled: boolPtr(false), Mode: "none"},
		},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	req := ctrl.Request{NamespacedName: types.NamespacedName{Namespace: ns, Name: "happy"}}
	if _, err := r.Reconcile(ctx, req); err != nil {
		t.Fatal(err)
	}
	if _, err := r.Reconcile(ctx, req); err != nil {
		t.Fatal(err)
	}
	if runner.buildCalls < 1 {
		t.Fatalf("expected build, got %d", runner.buildCalls)
	}
	var got twinopsv1alpha1.DigitalTwin
	if err := testClient.Get(ctx, req.NamespacedName, &got); err != nil {
		t.Fatal(err)
	}
	if got.Status.Phase != "Ready" && got.Status.Phase != "DriftDetected" {
		t.Fatalf("phase=%s msg=%s", got.Status.Phase, got.Status.Message)
	}
	if got.Status.StagePath == "" {
		t.Fatal("expected stage path")
	}
	if conditionReason(got.Status.Conditions, "Stalled") == "InvalidSpec" {
		t.Fatal("should not be stalled")
	}
}

func TestReconcileInvalidLiveAPIURL(t *testing.T) {
	ctx, ns, runner, r := setupNS(t)
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "cm", Namespace: ns},
		Data:       map[string]string{"twin.yaml": "name: t\n"},
	}
	if err := testClient.Create(ctx, cm); err != nil {
		t.Fatal(err)
	}
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "ssrf", Namespace: ns},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ArtifactSource: &twinopsv1alpha1.ArtifactSource{ConfigMapName: "cm"},
			LiveAPIURL:     "http://169.254.169.254/latest/meta-data",
		},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	req := ctrl.Request{NamespacedName: types.NamespacedName{Namespace: ns, Name: "ssrf"}}
	_, _ = r.Reconcile(ctx, req)
	res, err := r.Reconcile(ctx, req)
	if err != nil {
		t.Fatal(err)
	}
	if res.RequeueAfter != 0 || res.Requeue {
		t.Fatalf("permanent error must not requeue: %+v", res)
	}
	if runner.buildCalls != 0 {
		t.Fatal("must not exec twinopsctl")
	}
	var got twinopsv1alpha1.DigitalTwin
	if err := testClient.Get(ctx, req.NamespacedName, &got); err != nil {
		t.Fatal(err)
	}
	if conditionReason(got.Status.Conditions, "Ready") != "InvalidSpec" {
		t.Fatalf("ready reason=%s", conditionReason(got.Status.Conditions, "Ready"))
	}
	if conditionStatus(got.Status.Conditions, "Stalled") != metav1.ConditionTrue {
		t.Fatal("expected Stalled=True")
	}
}

func TestReconcileInvalidManifestPath(t *testing.T) {
	ctx, ns, runner, r := setupNS(t)
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "badpath", Namespace: ns},
		Spec:       twinopsv1alpha1.DigitalTwinSpec{ManifestPath: "/etc/passwd"},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	req := ctrl.Request{NamespacedName: types.NamespacedName{Namespace: ns, Name: "badpath"}}
	_, _ = r.Reconcile(ctx, req)
	res, err := r.Reconcile(ctx, req)
	if err != nil {
		t.Fatal(err)
	}
	if res != (ctrl.Result{}) {
		t.Fatalf("expected empty result, got %+v", res)
	}
	if runner.buildCalls != 0 {
		t.Fatal("must not exec")
	}
	var got twinopsv1alpha1.DigitalTwin
	_ = testClient.Get(ctx, req.NamespacedName, &got)
	if conditionReason(got.Status.Conditions, "Ready") != "InvalidSpec" {
		t.Fatalf("got reason %s msg %s", conditionReason(got.Status.Conditions, "Ready"), got.Status.Message)
	}
}

func TestReconcileDriftDetection(t *testing.T) {
	ctx, ns, runner, r := setupNS(t)
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "drift-cm", Namespace: ns},
		Data: map[string]string{
			"twin.yaml":      "name: t\n",
			"desired.yaml":   "x: 1\n",
			"telemetry.json": `{}`,
		},
	}
	if err := testClient.Create(ctx, cm); err != nil {
		t.Fatal(err)
	}
	runner.hasDrift = true
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "drift", Namespace: ns},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ArtifactSource:  &twinopsv1alpha1.ArtifactSource{ConfigMapName: "drift-cm"},
			IntervalSeconds: 60,
			OutputPublish:   &twinopsv1alpha1.OutputPublish{Enabled: boolPtr(false), Mode: "none"},
		},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	req := ctrl.Request{NamespacedName: types.NamespacedName{Namespace: ns, Name: "drift"}}
	_, _ = r.Reconcile(ctx, req)
	if _, err := r.Reconcile(ctx, req); err != nil {
		t.Fatal(err)
	}
	var got twinopsv1alpha1.DigitalTwin
	if err := testClient.Get(ctx, req.NamespacedName, &got); err != nil {
		t.Fatal(err)
	}
	if got.Status.Phase != "DriftDetected" || got.Status.Drift.Status != "Detected" {
		t.Fatalf("phase=%s drift=%+v", got.Status.Phase, got.Status.Drift)
	}
	builds := runner.buildCalls
	// Force skipCompose on next pass via status digests + output.
	got.Status.Output.Digest = "sha256:deadbeef"
	got.Status.LastComposeGeneration = got.Generation
	got.Status.LastComposeInputDigest = got.Status.InputDigest
	if err := testClient.Status().Update(ctx, &got); err != nil {
		t.Fatal(err)
	}
	if _, err := r.Reconcile(ctx, req); err != nil {
		t.Fatal(err)
	}
	if runner.buildCalls != builds {
		t.Fatalf("skipCompose should not rebuild: before=%d after=%d", builds, runner.buildCalls)
	}
	_ = testClient.Get(ctx, req.NamespacedName, &got)
	if got.Status.Drift.Status != "Detected" {
		t.Fatalf("drift not preserved: %+v", got.Status.Drift)
	}
}

func TestReconcileErrorBackoff(t *testing.T) {
	ctx, ns, runner, r := setupNS(t)
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "fail-cm", Namespace: ns},
		Data:       map[string]string{"twin.yaml": "name: t\n"},
	}
	if err := testClient.Create(ctx, cm); err != nil {
		t.Fatal(err)
	}
	runner.buildErr = fmt.Errorf("compose boom")
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "fail", Namespace: ns},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ArtifactSource: &twinopsv1alpha1.ArtifactSource{ConfigMapName: "fail-cm"},
			OutputPublish:  &twinopsv1alpha1.OutputPublish{Enabled: boolPtr(false), Mode: "none"},
		},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	req := ctrl.Request{NamespacedName: types.NamespacedName{Namespace: ns, Name: "fail"}}
	_, _ = r.Reconcile(ctx, req)
	res, err := r.Reconcile(ctx, req)
	if err == nil {
		t.Fatal("expected error for workqueue backoff")
	}
	if res.RequeueAfter != 0 {
		t.Fatalf("transient errors must use workqueue backoff, not RequeueAfter: %+v", res)
	}
	var got twinopsv1alpha1.DigitalTwin
	_ = testClient.Get(ctx, req.NamespacedName, &got)
	if conditionReason(got.Status.Conditions, "Ready") != "ComposeFailed" {
		t.Fatalf("reason=%s", conditionReason(got.Status.Conditions, "Ready"))
	}
}

func TestManagedGenerationPath(t *testing.T) {
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "t", Namespace: "ns", UID: "uid-1", Generation: 7},
	}
	p := workspace.ManagedGeneration(twin)
	if filepath.Base(p) != "g7" {
		t.Fatalf("got %s", p)
	}
}
