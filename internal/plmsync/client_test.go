package plmsync

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
)

func TestFetchCatalogETagAndConflict(t *testing.T) {
	var generation int32 = 1
	store := []map[string]any{
		{"id": "1004711", "revision": "C", "lifecycle": "Released", "metadata": map[string]any{"prim": "/World/R"}},
	}
	etag := func() string {
		return `W/"g` + string(rune('0'+atomic.LoadInt32(&generation))) + `"`
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/items", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer secret" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		cur := etag()
		if r.Header.Get("If-None-Match") == cur {
			w.Header().Set("ETag", cur)
			w.WriteHeader(http.StatusNotModified)
			return
		}
		w.Header().Set("ETag", cur)
		_ = json.NewEncoder(w).Encode(map[string]any{"items": store})
	})
	mux.HandleFunc("/fail", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"error":"down"}`))
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	client := &Client{BaseURL: srv.URL, Token: "secret", Timeout: 0}
	items, tag, notMod, err := client.FetchCatalog(context.Background(), "")
	if err != nil || notMod || len(items) != 1 || tag == "" {
		t.Fatalf("fetch1: items=%v etag=%q notMod=%v err=%v", items, tag, notMod, err)
	}
	_, tag2, notMod2, err := client.FetchCatalog(context.Background(), tag)
	if err != nil || !notMod2 || tag2 != tag {
		t.Fatalf("fetch304: etag=%q notMod=%v err=%v", tag2, notMod2, err)
	}

	client.Token = "wrong"
	_, _, _, err = client.FetchCatalog(context.Background(), "")
	if _, ok := err.(*AuthError); !ok {
		t.Fatalf("expected AuthError, got %T %v", err, err)
	}
}

func TestPollResyncExactlyOnce(t *testing.T) {
	var down atomic.Bool
	store := []map[string]any{
		{"id": "1", "revision": "A", "lifecycle": "Released", "metadata": map[string]any{"prim": "/P"}},
	}
	etag := `W/"v1"`
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if down.Load() {
			w.WriteHeader(http.StatusBadGateway)
			return
		}
		if r.Header.Get("If-None-Match") == etag {
			w.Header().Set("ETag", etag)
			w.WriteHeader(http.StatusNotModified)
			return
		}
		w.Header().Set("ETag", etag)
		_ = json.NewEncoder(w).Encode(map[string]any{"items": store})
	}))
	defer srv.Close()

	dir := t.TempDir()
	manifest := filepath.Join(dir, "twin.yaml")
	if err := os.WriteFile(manifest, []byte("apiVersion: twinops.io/v1alpha1\nkind: DigitalTwin\nmetadata:\n  name: t\nspec:\n  plm:\n    provider: rest\n    mappings: []\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	client := &Client{BaseURL: srv.URL}
	session := &Session{}
	r1 := Poll(context.Background(), client, session, manifest, true)
	if !r1.Changed || r1.Fingerprint == "" || r1.ResyncCount != 0 {
		t.Fatalf("first poll: %+v", r1)
	}
	down.Store(true)
	r2 := Poll(context.Background(), client, session, manifest, true)
	if !r2.Transient || !session.InOutage {
		t.Fatalf("outage: %+v session=%+v", r2, session)
	}
	down.Store(false)
	r3 := Poll(context.Background(), client, session, manifest, true)
	if !r3.Resynced || r3.ResyncCount != 1 {
		t.Fatalf("recovery resync: %+v", r3)
	}
	r4 := Poll(context.Background(), client, session, manifest, true)
	if r4.Resynced || r4.ResyncCount != 1 || !r4.NotModified {
		t.Fatalf("idempotent: %+v", r4)
	}

	raw, _ := os.ReadFile(manifest)
	if !contains(string(raw), "revision: A") {
		t.Fatalf("manifest not synced: %s", raw)
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(sub) == 0 || (len(s) > 0 && (func() bool {
		for i := 0; i+len(sub) <= len(s); i++ {
			if s[i:i+len(sub)] == sub {
				return true
			}
		}
		return false
	})()))
}

func TestEffectiveDigest(t *testing.T) {
	a := EffectiveDigest("sha256:abc", "fp1")
	b := EffectiveDigest("sha256:abc", "fp2")
	if a == b || a == "sha256:abc" {
		t.Fatalf("expected distinct folded digests: %s %s", a, b)
	}
}
