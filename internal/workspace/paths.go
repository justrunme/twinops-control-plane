package workspace

import (
	"fmt"
	"path/filepath"
	"strings"
)

// ValidateAllowlistedPath ensures path is non-empty, contains no "..", and resolves
// under baseDir. Absolute paths outside baseDir are rejected. Relative paths are
// joined with baseDir before the check.
func ValidateAllowlistedPath(baseDir, path string) (string, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return "", nil
	}
	if strings.Contains(path, "..") {
		return "", fmt.Errorf("path must not contain '..': %q", path)
	}
	baseDir = strings.TrimSpace(baseDir)
	if baseDir == "" {
		return "", fmt.Errorf("host filesystem paths require operator --manifest-base-dir")
	}
	baseClean := filepath.Clean(baseDir)
	var abs string
	if filepath.IsAbs(path) {
		abs = filepath.Clean(path)
	} else {
		abs = filepath.Clean(filepath.Join(baseClean, path))
	}
	prefix := baseClean + string(filepath.Separator)
	if abs != baseClean && !strings.HasPrefix(abs, prefix) {
		return "", fmt.Errorf("path %q outside allowlisted base %q", path, baseClean)
	}
	return abs, nil
}
