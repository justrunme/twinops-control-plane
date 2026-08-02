// twinops-job runs an isolated twinopsctl build (and optional drift) then
// publishes according to TWINOPS_PUBLISH_MODE and writes a result ConfigMap.
//
// For mode=configmap the Job returns the full bundle via the result ConfigMap
// (size-limited); the controller then mints immutable output revisions.
// For mode=oci|s3 the Job pushes the bundle itself and returns only metadata
// (digest + URI) so large industrial bundles never traverse a ConfigMap bridge.
//
// Drift is structured in result.json; a fatal drift tool error aborts before publish.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"

	"github.com/justrunme/twinops-control-plane/internal/output"
	"github.com/justrunme/twinops-control-plane/internal/twinbuild"
)

// DriftReport is the structured drift payload written into result.json.
type DriftReport struct {
	Ran      bool   `json:"ran"`
	OK       bool   `json:"ok"`
	Error    string `json:"error,omitempty"`
	HasDrift bool   `json:"hasDrift,omitempty"`
	Findings int    `json:"findings,omitempty"`
	Critical int    `json:"critical,omitempty"`
	Warning  int    `json:"warning,omitempty"`
	Summary  string `json:"summary,omitempty"`
	Status   string `json:"status,omitempty"` // Synced | Detected | Unknown | Error
}

func main() {
	var (
		inputDir   string
		outDir     string
		resultCM   string
		namespace  string
		twinopsctl string
		timeout    time.Duration
	)
	flag.StringVar(&inputDir, "input", "/input", "input directory (ConfigMap mount)")
	flag.StringVar(&outDir, "out", "/work/out", "compose output directory")
	flag.StringVar(&resultCM, "result-cm", "", "result ConfigMap name (required)")
	flag.StringVar(&namespace, "namespace", os.Getenv("POD_NAMESPACE"), "Kubernetes namespace")
	flag.StringVar(&twinopsctl, "twinopsctl", "/usr/local/bin/twinopsctl", "twinopsctl binary")
	flag.DurationVar(&timeout, "timeout", 4*time.Minute, "build timeout")
	flag.Parse()

	if resultCM == "" || namespace == "" {
		fail("result-cm and namespace are required")
	}

	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	manifest := firstFile(inputDir, "twin.yaml", "manifest.yaml")
	if manifest == "" {
		fail("missing twin.yaml in input")
	}

	runner := twinbuild.Runner{Binary: twinopsctl}
	stage, err := runner.Build(ctx, manifest, outDir)
	if err != nil {
		fail("build: %v", err)
	}

	desired := firstFile(inputDir, "desired.yaml")
	observed := firstFile(inputDir, "telemetry.json", "observed.json")
	drift := DriftReport{Ran: false, OK: true, Status: "Unknown"}
	if desired != "" && observed != "" {
		drift.Ran = true
		dr, derr := runner.Drift(ctx, desired, stage, observed, manifest, filepath.Join(outDir, "drift"))
		if derr != nil {
			// Fatal: do not publish on drift tool / report failure.
			fail("drift: %v", derr)
		}
		if dr != nil {
			drift.OK = true
			drift.HasDrift = dr.HasDrift
			drift.Findings = dr.Findings
			drift.Critical = dr.Critical
			drift.Warning = dr.Warning
			drift.Summary = dr.Summary
			if dr.HasDrift {
				drift.Status = "Detected"
			} else {
				drift.Status = "Synced"
			}
		}
	}

	bundle, err := output.BuildBundle(outDir)
	if err != nil {
		fail("bundle: %v", err)
	}

	publishMode := strings.ToLower(strings.TrimSpace(os.Getenv("TWINOPS_PUBLISH_MODE")))
	if publishMode == "" {
		publishMode = "configmap"
	}
	twinName := os.Getenv("TWINOPS_TWIN_NAME")
	inputDigest := os.Getenv("TWINOPS_INPUT_DIGEST")
	rev, _ := strconv.ParseInt(os.Getenv("TWINOPS_OUTPUT_REVISION"), 10, 64)
	if rev <= 0 {
		rev = 1
	}

	publishedURI := ""
	publishedName := ""
	jobPublished := false

	switch publishMode {
	case "oci":
		repo := os.Getenv("TWINOPS_OCI_REPOSITORY")
		uri, ref, perr := output.PublishOCIStandalone(ctx, repo, bundle, rev, inputDigest, twinName, namespace, os.Environ())
		if perr != nil {
			fail("oci publish: %v", perr)
		}
		publishedURI = uri
		publishedName = ref
		jobPublished = true
	case "s3":
		uri, key, perr := output.PublishS3Standalone(
			ctx,
			os.Getenv("TWINOPS_S3_BUCKET"),
			os.Getenv("TWINOPS_S3_PREFIX"),
			os.Getenv("TWINOPS_S3_ENDPOINT"),
			os.Getenv("TWINOPS_S3_REGION"),
			namespace,
			twinName,
			bundle,
			rev,
			os.Environ(),
		)
		if perr != nil {
			fail("s3 publish: %v", perr)
		}
		publishedURI = uri
		publishedName = key
		jobPublished = true
	case "configmap", "":
		// Bundle returned to controller for immutable ConfigMap revision publish.
	case "none":
		// Explicit no-publish (enabled=false / mode=none). Still write result metadata.
		jobPublished = false
		// Do not embed full bundle when publish is disabled and mode was oci/s3 intent —
		// controller only needs digest for status; for none we keep optional small bundle
		// only if under budget (helps local drift path). Prefer metadata-only.
	default:
		fail("unknown TWINOPS_PUBLISH_MODE=%q", publishMode)
	}

	result := map[string]any{
		"phase":         "Succeeded",
		"stagePath":     "root.usda",
		"contentDigest": bundle.Digest,
		"inputDigest":   inputDigest,
		"drift":         drift,
		// Legacy string field kept for older controllers / debugging.
		"driftSummary": drift.Summary,
		"publishMode":  publishMode,
		"published":    jobPublished,
		"uri":          publishedURI,
		"publishName":  publishedName,
		"revision":     rev,
	}
	resultJSON, _ := json.MarshalIndent(result, "", "  ")

	cfg, err := rest.InClusterConfig()
	if err != nil {
		fail("in-cluster config: %v", err)
	}
	cs, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		fail("clientset: %v", err)
	}

	labels := map[string]string{
		"twinops.io/build-result": "true",
	}
	if twinName != "" {
		labels["twinops.io/twin"] = twinName
	}

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      resultCM,
			Namespace: namespace,
			Labels:    labels,
			Annotations: map[string]string{
				"twinops.io/output-digest": bundle.Digest,
				"twinops.io/input-digest":  inputDigest,
				"twinops.io/publish-mode":  publishMode,
				"twinops.io/drift-status":  drift.Status,
				"twinops.io/drift-ran":     strconv.FormatBool(drift.Ran),
			},
		},
		Data: map[string]string{
			"result.json": string(resultJSON),
		},
	}
	if drift.Summary != "" {
		// Annotation size is limited; keep a short summary only.
		sum := drift.Summary
		if len(sum) > 200 {
			sum = sum[:200]
		}
		cm.Annotations["twinops.io/drift-summary"] = sum
	}
	// Embed full bundle only for configmap publish path (controller mints revisions).
	// OCI/S3 and mode=none are metadata-only (no ConfigMap size bridge).
	if !jobPublished && publishMode != "none" {
		if len(bundle.Bytes) > output.MaxBundleBytes {
			fail("bundle exceeds ConfigMap budget (%d > %d); use mode=oci or mode=s3 for large stages",
				len(bundle.Bytes), output.MaxBundleBytes)
		}
		cm.BinaryData = map[string][]byte{
			output.BundleKey: bundle.Bytes,
		}
	} else if publishedURI != "" {
		cm.Annotations["twinops.io/output-uri"] = publishedURI
	}

	_, err = cs.CoreV1().ConfigMaps(namespace).Create(ctx, cm, metav1.CreateOptions{})
	if apierrors.IsAlreadyExists(err) {
		existing, gerr := cs.CoreV1().ConfigMaps(namespace).Get(ctx, resultCM, metav1.GetOptions{})
		if gerr != nil {
			fail("get result cm: %v", gerr)
		}
		cm.ResourceVersion = existing.ResourceVersion
		cm.OwnerReferences = existing.OwnerReferences
		_, err = cs.CoreV1().ConfigMaps(namespace).Update(ctx, cm, metav1.UpdateOptions{})
	}
	if err != nil {
		fail("write result configmap: %v", err)
	}
	fmt.Printf("twinops-job OK digest=%s mode=%s published=%v drift=%s uri=%s cm=%s/%s\n",
		bundle.Digest, publishMode, jobPublished, drift.Status, publishedURI, namespace, resultCM)
}

func firstFile(dir string, names ...string) string {
	for _, n := range names {
		p := filepath.Join(dir, n)
		if st, err := os.Stat(p); err == nil && !st.IsDir() {
			return p
		}
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return ""
	}
	want := map[string]struct{}{}
	for _, n := range names {
		want[n] = struct{}{}
	}
	for _, e := range entries {
		if e.IsDir() {
			if p := firstFile(filepath.Join(dir, e.Name()), names...); p != "" {
				return p
			}
			continue
		}
		if _, ok := want[e.Name()]; ok {
			return filepath.Join(dir, e.Name())
		}
	}
	return ""
}

func fail(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "twinops-job: "+format+"\n", args...)
	os.Exit(1)
}
