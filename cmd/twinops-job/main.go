// twinops-job runs an isolated twinopsctl build (and optional drift) then
// writes a result ConfigMap for the controller to publish durably.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"

	"github.com/justrunme/twinops-control-plane/internal/output"
	"github.com/justrunme/twinops-control-plane/internal/twinbuild"
)

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
	driftSummary := ""
	if desired != "" && observed != "" {
		dr, derr := runner.Drift(ctx, desired, stage, observed, manifest, filepath.Join(outDir, "drift"))
		if derr != nil {
			// Non-fatal: still publish stage; controller can mark Error if needed.
			driftSummary = derr.Error()
		} else if dr != nil {
			driftSummary = dr.Summary
		}
	}

	bundle, err := output.BuildBundle(outDir)
	if err != nil {
		fail("bundle: %v", err)
	}

	result := map[string]any{
		"phase":         "Succeeded",
		"stagePath":     "root.usda",
		"contentDigest": bundle.Digest,
		"driftSummary":  driftSummary,
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

	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      resultCM,
			Namespace: namespace,
			Labels: map[string]string{
				"twinops.io/build-result": "true",
			},
			Annotations: map[string]string{
				"twinops.io/output-digest": bundle.Digest,
			},
		},
		BinaryData: map[string][]byte{
			output.BundleKey: bundle.Bytes,
		},
		Data: map[string]string{
			"result.json": string(resultJSON),
		},
	}

	// Create or replace.
	_, err = cs.CoreV1().ConfigMaps(namespace).Create(ctx, cm, metav1.CreateOptions{})
	if apierrors.IsAlreadyExists(err) {
		existing, gerr := cs.CoreV1().ConfigMaps(namespace).Get(ctx, resultCM, metav1.GetOptions{})
		if gerr != nil {
			fail("get result cm: %v", gerr)
		}
		cm.ResourceVersion = existing.ResourceVersion
		_, err = cs.CoreV1().ConfigMaps(namespace).Update(ctx, cm, metav1.UpdateOptions{})
	}
	if err != nil {
		fail("write result configmap: %v", err)
	}
	fmt.Printf("twinops-job OK digest=%s cm=%s/%s\n", bundle.Digest, namespace, resultCM)
}

func firstFile(dir string, names ...string) string {
	for _, n := range names {
		p := filepath.Join(dir, n)
		if st, err := os.Stat(p); err == nil && !st.IsDir() {
			return p
		}
	}
	// shallow walk
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
