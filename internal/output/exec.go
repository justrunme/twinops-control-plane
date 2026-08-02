package output

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"strings"
)

func runCmd(ctx context.Context, name string, args ...string) error {
	return runCmdEnv(ctx, nil, name, args...)
}

func runCmdEnv(ctx context.Context, env []string, name string, args ...string) error {
	cmd := exec.CommandContext(ctx, name, args...)
	if env != nil {
		cmd.Env = env
	}
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		msg := strings.TrimSpace(stderr.String())
		if msg == "" {
			msg = err.Error()
		}
		return fmt.Errorf("%s %v: %s", name, args, msg)
	}
	return nil
}
