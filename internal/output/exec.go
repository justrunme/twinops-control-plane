package output

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"strings"
)

func runCmd(ctx context.Context, name string, args ...string) error {
	_, err := runCmdOut(ctx, nil, name, args...)
	return err
}

func runCmdEnv(ctx context.Context, env []string, name string, args ...string) error {
	_, err := runCmdOut(ctx, env, name, args...)
	return err
}

// runCmdOut runs a command and returns combined stdout+stderr on success (stdout preferred).
func runCmdOut(ctx context.Context, env []string, name string, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, name, args...)
	if env != nil {
		cmd.Env = env
	}
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		msg := strings.TrimSpace(stderr.String())
		if msg == "" {
			msg = strings.TrimSpace(stdout.String())
		}
		if msg == "" {
			msg = err.Error()
		}
		return "", fmt.Errorf("%s %v: %s", name, args, msg)
	}
	out := stdout.String()
	if strings.TrimSpace(out) == "" {
		out = stderr.String()
	}
	return out, nil
}
