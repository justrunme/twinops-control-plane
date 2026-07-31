package twinbuild

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestBuildAndDriftWithTwinopsctl(t *testing.T) {
	if _, err := exec.LookPath("twinopsctl"); err != nil {
		t.Skip("twinopsctl not installed in PATH")
	}

	root := findRepoRoot(t)
	out := t.TempDir()
	runner := Runner{}

	stage, err := runner.Build(
		context.Background(),
		filepath.Join(root, "examples/assembly-line/twin.yaml"),
		out,
	)
	if err != nil {
		t.Fatalf("build: %v", err)
	}
	if _, err := os.Stat(stage); err != nil {
		t.Fatalf("stage missing: %v", err)
	}

	result, err := runner.Drift(
		context.Background(),
		filepath.Join(root, "examples/assembly-line/desired.yaml"),
		stage,
		filepath.Join(root, "examples/assembly-line/telemetry.json"),
		filepath.Join(root, "examples/assembly-line/twin.yaml"),
		filepath.Join(out, "drift"),
	)
	if err != nil {
		t.Fatalf("drift: %v", err)
	}
	if !result.HasDrift {
		t.Fatalf("expected drift from sample telemetry")
	}
}

func findRepoRoot(t *testing.T) string {
	t.Helper()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	dir := wd
	for i := 0; i < 6; i++ {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir
		}
		dir = filepath.Dir(dir)
	}
	t.Fatal("go.mod not found")
	return ""
}
