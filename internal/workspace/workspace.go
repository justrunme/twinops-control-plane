// Package workspace resolves controller-owned twin workspaces safely.
package workspace

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"k8s.io/apimachinery/pkg/types"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

// DefaultRoot is the default operator workspace root (emptyDir or PVC mount).
const DefaultRoot = "/tmp/twinops"

// Root is the only directory tree the operator finalizer may delete.
// Override with TWINOPS_WORKSPACE_ROOT for tests or a persistent volume mount.
var Root = DefaultRoot

func init() {
	if v := strings.TrimSpace(os.Getenv("TWINOPS_WORKSPACE_ROOT")); v != "" {
		Root = v
	}
}

// Managed returns the controller-owned workspace for a twin.
// Always under Root/<namespace>/<uid> so CR deletion cannot wipe sibling twins
// or arbitrary Spec.OutputDir paths.
func Managed(twin *twinopsv1alpha1.DigitalTwin) string {
	uid := twin.UID
	if uid == types.UID("") {
		// Before UID is assigned (should not happen mid-reconcile), fall back to name.
		return filepath.Join(Root, twin.Namespace, twin.Name)
	}
	return filepath.Join(Root, twin.Namespace, string(uid))
}

// ManagedGeneration returns a per-generation build directory under the twin workspace.
// Keying by generation keeps prior stages available across reconciles and reduces
// full recomposes after leader failover when the volume (emptyDir/PVC) is retained.
func ManagedGeneration(twin *twinopsv1alpha1.DigitalTwin) string {
	gen := twin.Generation
	if gen <= 0 {
		gen = 1
	}
	return filepath.Join(Managed(twin), fmt.Sprintf("g%d", gen))
}

// IsManaged reports whether path is strictly under the managed root for this twin.
func IsManaged(twin *twinopsv1alpha1.DigitalTwin, path string) bool {
	if path == "" {
		return false
	}
	clean := filepath.Clean(path)
	managed := filepath.Clean(Managed(twin))
	if clean == managed {
		return true
	}
	prefix := managed + string(filepath.Separator)
	return strings.HasPrefix(clean, prefix)
}

// CleanupPath returns the path safe to RemoveAll on finalizer, or empty if none.
func CleanupPath(twin *twinopsv1alpha1.DigitalTwin) string {
	return Managed(twin)
}
