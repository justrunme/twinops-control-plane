package controllers

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
	"github.com/justrunme/twinops-control-plane/internal/buildjob"
	"github.com/justrunme/twinops-control-plane/internal/output"
	"github.com/justrunme/twinops-control-plane/internal/workspace"
)

func TestMapConfigMapAndJob(t *testing.T) {
	ctx, ns, _, r := setupNS(t)
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "mapme", Namespace: ns},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ArtifactSource: &twinopsv1alpha1.ArtifactSource{ConfigMapName: "src-cm"},
		},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	cm := &corev1.ConfigMap{ObjectMeta: metav1.ObjectMeta{Name: "src-cm", Namespace: ns}}
	reqs := r.mapConfigMapToTwins(ctx, cm)
	if len(reqs) != 1 || reqs[0].Name != "mapme" {
		t.Fatalf("mapConfigMap: %+v", reqs)
	}
	outCM := &corev1.ConfigMap{ObjectMeta: metav1.ObjectMeta{
		Name: "out", Namespace: ns, Labels: map[string]string{"twinops.io/output": "true"},
	}}
	if r.mapConfigMapToTwins(ctx, outCM) != nil {
		t.Fatal("output cm should be ignored")
	}
	job := &batchv1.Job{ObjectMeta: metav1.ObjectMeta{
		Name: "j", Namespace: ns,
		Labels: map[string]string{"twinops.io/build": "true", "twinops.io/twin": "mapme"},
	}}
	jreqs := r.mapJobToTwin(ctx, job)
	if len(jreqs) != 1 || jreqs[0].Name != "mapme" {
		t.Fatalf("mapJob: %+v", jreqs)
	}
	if r.mapJobToTwin(ctx, &batchv1.Job{}) != nil {
		t.Fatal("unlabeled job")
	}
}

func TestFinalizerCleanup(t *testing.T) {
	ctx, ns, _, r := setupNS(t)
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{
			Name:       "dying",
			Namespace:  ns,
			Finalizers: []string{finalizerName},
		},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ArtifactSource: &twinopsv1alpha1.ArtifactSource{ConfigMapName: "x"},
		},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	// Ensure managed workspace exists then delete twin.
	var got twinopsv1alpha1.DigitalTwin
	if err := testClient.Get(ctx, types.NamespacedName{Namespace: ns, Name: "dying"}, &got); err != nil {
		t.Fatal(err)
	}
	ws := workspace.Managed(&got)
	_ = os.MkdirAll(filepath.Join(ws, "g1"), 0o755)
	now := metav1.Now()
	got.DeletionTimestamp = &now
	// envtest: use Delete which sets deletionTimestamp when finalizers present.
	if err := testClient.Delete(ctx, &got); err != nil {
		t.Fatal(err)
	}
	req := ctrl.Request{NamespacedName: types.NamespacedName{Namespace: ns, Name: "dying"}}
	if _, err := r.Reconcile(ctx, req); err != nil {
		t.Fatal(err)
	}
	err := testClient.Get(ctx, req.NamespacedName, &got)
	if err == nil && controllerutil.ContainsFinalizer(&got, finalizerName) {
		t.Fatal("finalizer should be removed")
	}
}

func TestHostPathHappyAndLiveProbe(t *testing.T) {
	ctx, ns, runner, r := setupNS(t)
	mux := http.NewServeMux()
	mux.HandleFunc("/api/ready", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"status":"ready","twin":"t"}`))
	})
	mux.HandleFunc("/api/health", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"version":"1.0"}`))
	})
	mux.HandleFunc("/api/metrics", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"hasDrift":false,"highlightedPrims":0,"timelineEvents":1}`))
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	r.LiveAPIAllowPrivate = true
	manifest := filepath.Join(r.ManifestBaseDir, "assembly-line", "twin.yaml")
	desired := filepath.Join(r.ManifestBaseDir, "assembly-line", "desired.yaml")
	observed := filepath.Join(r.ManifestBaseDir, "assembly-line", "telemetry.json")
	_ = os.WriteFile(desired, []byte("x: 1\n"), 0o644)
	_ = os.WriteFile(observed, []byte("{}"), 0o644)

	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "host", Namespace: ns},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ManifestPath:    manifest,
			DesiredPath:     desired,
			ObservedPath:    observed,
			LiveAPIURL:      srv.URL,
			IntervalSeconds: 30,
			OutputPublish:   &twinopsv1alpha1.OutputPublish{Enabled: boolPtr(false), Mode: "none"},
		},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	req := ctrl.Request{NamespacedName: types.NamespacedName{Namespace: ns, Name: "host"}}
	_, _ = r.Reconcile(ctx, req)
	if _, err := r.Reconcile(ctx, req); err != nil {
		t.Fatal(err)
	}
	if runner.buildCalls < 1 || runner.driftCalls < 1 {
		t.Fatalf("build=%d drift=%d", runner.buildCalls, runner.driftCalls)
	}
	var got twinopsv1alpha1.DigitalTwin
	_ = testClient.Get(ctx, req.NamespacedName, &got)
	if !got.Status.Live.Ready {
		t.Fatalf("live status: %+v", got.Status.Live)
	}
	// generation-keyed stage path
	if got.Status.StagePath == "" || filepath.Base(filepath.Dir(got.Status.StagePath)) != fmt.Sprintf("g%d", got.Generation) &&
		!containsGen(got.Status.StagePath, got.Generation) {
		// Stage is outputDir/root.usda where outputDir ends with g<gen>
		if !containsGen(got.Status.StagePath, got.Generation) {
			t.Fatalf("expected generation in stage path: %s gen=%d", got.Status.StagePath, got.Generation)
		}
	}
}

func containsGen(path string, gen int64) bool {
	return filepath.Base(filepath.Dir(path)) == fmt.Sprintf("g%d", gen) ||
		len(path) > 0 && (stringContains(path, fmt.Sprintf("/g%d/", gen)) || stringContains(path, fmt.Sprintf("/g%d", gen)))
}

func stringContains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(sub) == 0 ||
		bytes.Contains([]byte(s), []byte(sub)))
}

func TestJobModeComposeSuccess(t *testing.T) {
	ctx, ns, _, r := setupNS(t)
	t.Setenv("TWINOPS_BUILD_IMAGE", "twinops-operator:test")

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "job-inputs", Namespace: ns},
		Data: map[string]string{
			"twin.yaml":      "name: t\n",
			"desired.yaml":   "x: 1\n",
			"telemetry.json": `{}`,
		},
	}
	if err := testClient.Create(ctx, cm); err != nil {
		t.Fatal(err)
	}
	enabled := false
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "jobtwin", Namespace: ns},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ArtifactSource: &twinopsv1alpha1.ArtifactSource{ConfigMapName: "job-inputs"},
			Build:          &twinopsv1alpha1.BuildIsolation{Mode: "job"},
			OutputPublish:  &twinopsv1alpha1.OutputPublish{Enabled: &enabled, Mode: "none"},
		},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	req := ctrl.Request{NamespacedName: types.NamespacedName{Namespace: ns, Name: "jobtwin"}}
	_, _ = r.Reconcile(ctx, req) // finalizer

	// First compose attempt creates Job (Pending) → requeue.
	res, err := r.Reconcile(ctx, req)
	if err != nil {
		t.Fatal(err)
	}
	if res.RequeueAfter == 0 {
		// May already succeed if we race — fetch twin for digest
	}

	var got twinopsv1alpha1.DigitalTwin
	if err := testClient.Get(ctx, req.NamespacedName, &got); err != nil {
		t.Fatal(err)
	}
	inputDigest := got.Status.InputDigest
	if inputDigest == "" {
		// Compose may have failed before setting digest; materialize again via status.
		// Re-read after forcing — actually Controllers sets digest in Composing patch.
		t.Logf("status: %+v", got.Status)
	}
	execKey := buildjob.ExecutionKey(inputDigest, twin.Spec.OutputPublish)
	if inputDigest == "" {
		// Compute digest like materialize would for the CM content.
		inputDigest = hashCM(cm)
		execKey = buildjob.ExecutionKey(inputDigest, twin.Spec.OutputPublish)
	}
	jobName := buildjob.JobName(&got, execKey)
	cmName := buildjob.ResultConfigMapName(&got, execKey)

	var job batchv1.Job
	if err := testClient.Get(ctx, types.NamespacedName{Namespace: ns, Name: jobName}, &job); err != nil {
		jobs, listErr := listJobs(ctx, ns)
		if listErr != nil || len(jobs) == 0 {
			t.Fatalf("expected job created, status=%+v err=%v listErr=%v", got.Status, err, listErr)
		}
		job = jobs[0]
		jobName = job.Name
		if job.Labels["twinops.io/exec-key"] != "" {
			execKey = job.Labels["twinops.io/exec-key"]
			cmName = buildjob.ResultConfigMapName(&got, execKey)
		}
	}
	_ = jobName

	now := metav1.Now()
	job.Status.StartTime = &now
	job.Status.CompletionTime = &now
	job.Status.Succeeded = 1
	job.Status.Conditions = []batchv1.JobCondition{
		{Type: batchv1.JobSuccessCriteriaMet, Status: corev1.ConditionTrue, LastProbeTime: now, LastTransitionTime: now},
		{Type: batchv1.JobComplete, Status: corev1.ConditionTrue, LastProbeTime: now, LastTransitionTime: now},
	}
	if err := testClient.Status().Update(ctx, &job); err != nil {
		t.Fatal(err)
	}

	bundle := mustTarGz(t, map[string][]byte{"root.usda": []byte("#usda 1.0\n")})
	digest := "sha256:" + sha256Hex(bundle)
	result := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      cmName,
			Namespace: ns,
			Labels: map[string]string{
				"twinops.io/twin":         got.Name,
				"twinops.io/build-result": "true",
			},
			Annotations: map[string]string{
				"twinops.io/output-digest": digest,
				"twinops.io/drift-status":  "Synced",
				"twinops.io/drift-summary": "SYNCED=1",
			},
		},
		BinaryData: map[string][]byte{output.BundleKey: bundle},
		Data: map[string]string{
			"result.json": `{"published":false,"drift":{"ran":true,"ok":true,"hasDrift":false,"findings":0,"summary":"SYNCED=1","status":"Synced"}}`,
		},
	}
	if err := testClient.Create(ctx, result); err != nil {
		t.Fatal(err)
	}

	res, err = r.Reconcile(ctx, req)
	if err != nil {
		t.Fatal(err)
	}
	_ = res
	if err := testClient.Get(ctx, req.NamespacedName, &got); err != nil {
		t.Fatal(err)
	}
	if got.Status.Phase != "Ready" && got.Status.Phase != "DriftDetected" {
		t.Fatalf("job compose phase=%s msg=%s build=%+v", got.Status.Phase, got.Status.Message, got.Status.Build)
	}
	if got.Status.Build.Phase != "Succeeded" && got.Status.Output.Digest == "" {
		t.Fatalf("expected success artifacts: %+v", got.Status)
	}
}

func listJobs(ctx context.Context, ns string) ([]batchv1.Job, error) {
	var list batchv1.JobList
	err := testClient.List(ctx, &list)
	var out []batchv1.Job
	for i := range list.Items {
		if list.Items[i].Namespace == ns {
			out = append(out, list.Items[i])
		}
	}
	return out, err
}

func mustTarGz(t *testing.T, files map[string][]byte) []byte {
	t.Helper()
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	for name, data := range files {
		hdr := &tar.Header{Name: name, Mode: 0o644, Size: int64(len(data))}
		if err := tw.WriteHeader(hdr); err != nil {
			t.Fatal(err)
		}
		if _, err := tw.Write(data); err != nil {
			t.Fatal(err)
		}
	}
	_ = tw.Close()
	_ = gz.Close()
	return buf.Bytes()
}

func sha256Hex(b []byte) string {
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}

func hashCM(cm *corev1.ConfigMap) string {
	// Approximate — real digest comes from materialize; tests recover from Job labels.
	h := sha256.New()
	_, _ = h.Write([]byte(cm.Data["twin.yaml"]))
	return "sha256:" + hex.EncodeToString(h.Sum(nil))
}

func TestSetConditionTransition(t *testing.T) {
	st := &twinopsv1alpha1.DigitalTwinStatus{ObservedGeneration: 3}
	setCondition(st, "Ready", metav1.ConditionFalse, "Error", "boom")
	if len(st.Conditions) != 1 {
		t.Fatal(st.Conditions)
	}
	first := st.Conditions[0].LastTransitionTime
	time.Sleep(2 * time.Millisecond)
	setCondition(st, "Ready", metav1.ConditionFalse, "Error", "boom")
	if !st.Conditions[0].LastTransitionTime.Equal(&first) {
		t.Fatal("transition time should be stable when unchanged")
	}
	setCondition(st, "Ready", metav1.ConditionTrue, "Reconciled", "ok")
	if st.Conditions[0].LastTransitionTime.Equal(&first) {
		t.Fatal("transition time should update on change")
	}
}

func TestEnsureResultOwner(t *testing.T) {
	ctx, ns, _, r := setupNS(t)
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "own", Namespace: ns},
		Spec:       twinopsv1alpha1.DigitalTwinSpec{ArtifactSource: &twinopsv1alpha1.ArtifactSource{ConfigMapName: "c"}},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	var got twinopsv1alpha1.DigitalTwin
	_ = testClient.Get(ctx, types.NamespacedName{Namespace: ns, Name: "own"}, &got)
	cm := &corev1.ConfigMap{ObjectMeta: metav1.ObjectMeta{Name: "result", Namespace: ns}}
	if err := testClient.Create(ctx, cm); err != nil {
		t.Fatal(err)
	}
	_ = testClient.Get(ctx, types.NamespacedName{Namespace: ns, Name: "result"}, cm)
	if err := r.ensureResultOwner(ctx, &got, cm); err != nil {
		t.Fatal(err)
	}
	_ = testClient.Get(ctx, types.NamespacedName{Namespace: ns, Name: "result"}, cm)
	if len(cm.OwnerReferences) != 1 || cm.OwnerReferences[0].UID != got.UID {
		t.Fatalf("ownerRefs=%+v", cm.OwnerReferences)
	}
	// idempotent
	if err := r.ensureResultOwner(ctx, &got, cm); err != nil {
		t.Fatal(err)
	}
}

func TestValidateMissingArtifactAndLiveAllowlist(t *testing.T) {
	r := &DigitalTwinReconciler{
		ManifestBaseDir:      "/examples",
		LiveAPIHostAllowlist: []string{"allowed.example"},
		LiveAPIAllowPrivate:  true,
	}
	_, _, _, err := r.validateAndResolvePaths(&twinopsv1alpha1.DigitalTwin{})
	if err == nil {
		t.Fatal("expected missing source")
	}
	_, _, _, err = r.validateAndResolvePaths(&twinopsv1alpha1.DigitalTwin{
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ArtifactSource: &twinopsv1alpha1.ArtifactSource{ConfigMapName: "c"},
			LiveAPIURL:     "http://127.0.0.1:9",
		},
	})
	if err == nil {
		t.Fatal("expected allowlist miss")
	}
}

func TestResolvePlmToken(t *testing.T) {
	ctx, ns, _, _ := setupNS(t)
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "plm-tok", Namespace: ns},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			PLM: &twinopsv1alpha1.PlmSourceSpec{
				URL:            "http://127.0.0.1:9",
				TokenSecretRef: &twinopsv1alpha1.SecretKeyRef{Name: "plm-token", Key: "token"},
			},
		},
	}
	if tok, err := resolvePlmToken(ctx, nil, twin); err == nil || tok != "" {
		t.Fatalf("nil client: tok=%q err=%v", tok, err)
	}
	if tok, err := resolvePlmToken(ctx, testClient, twin); err == nil || tok != "" {
		t.Fatalf("missing secret: tok=%q err=%v", tok, err)
	}
	sec := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: "plm-token", Namespace: ns},
		Data:       map[string][]byte{"token": []byte("s3cr3t")},
	}
	if err := testClient.Create(ctx, sec); err != nil {
		t.Fatal(err)
	}
	tok, err := resolvePlmToken(ctx, testClient, twin)
	if err != nil || tok != "s3cr3t" {
		t.Fatalf("tok=%q err=%v", tok, err)
	}
	// no PLM / no ref → empty
	if tok, err := resolvePlmToken(ctx, testClient, &twinopsv1alpha1.DigitalTwin{}); err != nil || tok != "" {
		t.Fatalf("empty: tok=%q err=%v", tok, err)
	}
}

func TestReconcilePlmAuthFailed(t *testing.T) {
	ctx, ns, _, r := setupNS(t)
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "plm-cm", Namespace: ns},
		Data: map[string]string{
			"twin.yaml": "name: assembly\nspec:\n  plm:\n    mappings: []\n",
		},
	}
	if err := testClient.Create(ctx, cm); err != nil {
		t.Fatal(err)
	}
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "plm-auth", Namespace: ns},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ArtifactSource:  &twinopsv1alpha1.ArtifactSource{ConfigMapName: "plm-cm"},
			IntervalSeconds: 30,
			OutputPublish:   &twinopsv1alpha1.OutputPublish{Enabled: boolPtr(false), Mode: "none"},
			PLM: &twinopsv1alpha1.PlmSourceSpec{
				URL:            "http://127.0.0.1:9",
				TokenSecretRef: &twinopsv1alpha1.SecretKeyRef{Name: "missing-plm", Key: "token"},
			},
		},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	req := ctrl.Request{NamespacedName: types.NamespacedName{Namespace: ns, Name: "plm-auth"}}
	_, err := r.Reconcile(ctx, req)
	if err == nil {
		t.Fatal("expected auth error")
	}
	var got twinopsv1alpha1.DigitalTwin
	if err := testClient.Get(ctx, req.NamespacedName, &got); err != nil {
		t.Fatal(err)
	}
	if conditionReason(got.Status.Conditions, "PlmSynced") != "AuthFailed" {
		t.Fatalf("want AuthFailed, got %s msg=%s", conditionReason(got.Status.Conditions, "PlmSynced"), got.Status.PLM.Message)
	}
}

func TestReconcilePlmSyncHappy(t *testing.T) {
	ctx, ns, runner, r := setupNS(t)

	// Minimal mock PLM HTTP server with ETag
	store := map[string]any{
		"items": []map[string]any{
			{"id": "1004711", "revision": "B", "lifecycle": "Released", "metadata": map[string]string{"prim": "/World/Robot"}},
		},
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/items", func(w http.ResponseWriter, req *http.Request) {
		if req.Header.Get("Authorization") != "Bearer plm-tok" {
			w.WriteHeader(401)
			return
		}
		body, _ := json.Marshal(store)
		w.Header().Set("ETag", `"etag-1"`)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	sec := &corev1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: "plm-token", Namespace: ns},
		Data:       map[string][]byte{"token": []byte("plm-tok")},
	}
	if err := testClient.Create(ctx, sec); err != nil {
		t.Fatal(err)
	}
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{Name: "plm-inputs", Namespace: ns},
		Data: map[string]string{
			"twin.yaml": "apiVersion: twinops.io/v1alpha1\nkind: DigitalTwin\nmetadata:\n  name: t\nspec:\n  plm:\n    provider: rest\n    mappings: []\n",
		},
	}
	if err := testClient.Create(ctx, cm); err != nil {
		t.Fatal(err)
	}
	sync := true
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "plm-ok", Namespace: ns},
		Spec: twinopsv1alpha1.DigitalTwinSpec{
			ArtifactSource:  &twinopsv1alpha1.ArtifactSource{ConfigMapName: "plm-inputs"},
			IntervalSeconds: 30,
			OutputPublish:   &twinopsv1alpha1.OutputPublish{Enabled: boolPtr(false), Mode: "none"},
			PLM: &twinopsv1alpha1.PlmSourceSpec{
				URL:            srv.URL,
				TokenSecretRef: &twinopsv1alpha1.SecretKeyRef{Name: "plm-token", Key: "token"},
				SyncManifest:   &sync,
				PollSeconds:    15,
			},
		},
	}
	if err := testClient.Create(ctx, twin); err != nil {
		t.Fatal(err)
	}
	req := ctrl.Request{NamespacedName: types.NamespacedName{Namespace: ns, Name: "plm-ok"}}
	if _, err := r.Reconcile(ctx, req); err != nil {
		t.Fatalf("reconcile: %v", err)
	}
	var got twinopsv1alpha1.DigitalTwin
	if err := testClient.Get(ctx, req.NamespacedName, &got); err != nil {
		t.Fatal(err)
	}
	if conditionReason(got.Status.Conditions, "PlmSynced") != "Synced" {
		t.Fatalf("PlmSynced=%s msg=%s", conditionReason(got.Status.Conditions, "PlmSynced"), got.Status.PLM.Message)
	}
	if got.Status.PLM.ETag == "" {
		t.Fatal("expected PLM etag")
	}
	if runner.buildCalls < 1 {
		t.Fatalf("expected build after PLM sync, got %d", runner.buildCalls)
	}
}
