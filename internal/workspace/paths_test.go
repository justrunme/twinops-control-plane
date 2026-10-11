package workspace

import (
	"path/filepath"
	"testing"
)

func TestValidateAllowlistedPath(t *testing.T) {
	t.Parallel()
	base := "/examples"
	ok, err := ValidateAllowlistedPath(base, "/examples/assembly-line/twin.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if ok != filepath.Clean("/examples/assembly-line/twin.yaml") {
		t.Fatalf("got %s", ok)
	}
	rel, err := ValidateAllowlistedPath(base, "assembly-line/twin.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if rel != filepath.Join(base, "assembly-line/twin.yaml") {
		t.Fatalf("got %s", rel)
	}
	if _, err := ValidateAllowlistedPath(base, "/etc/passwd"); err == nil {
		t.Fatal("expected outside-base rejection")
	}
	if _, err := ValidateAllowlistedPath(base, "/examples/../etc/passwd"); err == nil {
		t.Fatal("expected .. rejection")
	}
	if _, err := ValidateAllowlistedPath("", "/examples/x"); err == nil {
		t.Fatal("expected empty base rejection")
	}
	if p, err := ValidateAllowlistedPath(base, ""); err != nil || p != "" {
		t.Fatalf("empty path: %q %v", p, err)
	}
}
