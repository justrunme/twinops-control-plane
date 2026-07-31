package twinbuild

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// Result captures twinopsctl build/drift outputs used by the operator.
type Result struct {
	StagePath string
	HasDrift  bool
	Findings  int
	Summary   string
	RawDrift  map[string]any
}

// Runner executes twinopsctl commands.
type Runner struct {
	Binary string
}

func (r Runner) binary() string {
	if r.Binary != "" {
		return r.Binary
	}
	if env := os.Getenv("TWINOPSCTL"); env != "" {
		return env
	}
	return "twinopsctl"
}

func (r Runner) Build(ctx context.Context, manifestPath, outputDir string) (string, error) {
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return "", err
	}
	cmd := exec.CommandContext(ctx, r.binary(), "build", manifestPath, "--out", outputDir)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("twinopsctl build failed: %w: %s", err, strings.TrimSpace(stderr.String()))
	}
	stage := filepath.Join(outputDir, "root.usda")
	if _, err := os.Stat(stage); err != nil {
		return "", fmt.Errorf("composed stage missing: %s", stage)
	}
	return stage, nil
}

func (r Runner) Drift(ctx context.Context, desired, stage, observed, manifest, outDir string) (*Result, error) {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return nil, err
	}
	args := []string{
		"drift",
		"--desired", desired,
		"--stage", stage,
		"--observed", observed,
		"--out", outDir,
		"--json",
	}
	if manifest != "" {
		args = append(args, "--manifest", manifest)
	}
	cmd := exec.CommandContext(ctx, r.binary(), args...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	// twinopsctl drift returns non-zero when drift/critical is present.
	reportPath := filepath.Join(outDir, "drift-report.json")
	data, readErr := os.ReadFile(reportPath)
	if readErr != nil {
		// Fall back to stdout JSON if file write failed.
		data = stdout.Bytes()
	}
	if len(data) == 0 {
		if err != nil {
			return nil, fmt.Errorf("twinopsctl drift failed: %w: %s", err, strings.TrimSpace(stderr.String()))
		}
		return nil, fmt.Errorf("empty drift report")
	}

	var payload map[string]any
	if unmarshalErr := json.Unmarshal(data, &payload); unmarshalErr != nil {
		return nil, fmt.Errorf("parse drift report: %w", unmarshalErr)
	}

	status, _ := payload["status"].(map[string]any)
	hasDrift, _ := status["hasDrift"].(bool)
	summaryMap, _ := status["summary"].(map[string]any)
	findings, _ := status["findings"].([]any)

	nonSynced := 0
	parts := make([]string, 0, len(summaryMap))
	for key, value := range summaryMap {
		parts = append(parts, fmt.Sprintf("%s=%v", key, value))
		if key != "SYNCED" {
			if n, ok := value.(float64); ok {
				nonSynced += int(n)
			}
		}
	}
	if nonSynced == 0 && hasDrift {
		nonSynced = len(findings)
	}

	return &Result{
		StagePath: stage,
		HasDrift:  hasDrift,
		Findings:  nonSynced,
		Summary:   strings.Join(parts, ", "),
		RawDrift:  payload,
	}, nil
}
