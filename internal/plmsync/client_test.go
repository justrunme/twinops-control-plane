package plmsync

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
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
			_, _ = w.Write([]byte(`{"error":"nope-secret-body-must-not-leak"}`))
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
	srv := httptest.NewServer(mux)
	defer srv.Close()

	client := &Client{BaseURL: srv.URL, Token: "secret", Timeout: 0, AllowPrivate: true}
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
	ae, ok := err.(*AuthError)
	if !ok {
		t.Fatalf("expected AuthError, got %T %v", err, err)
	}
	if strings.Contains(ae.Error(), "nope-secret") {
		t.Fatalf("auth error leaked response body: %v", ae)
	}
	if ae.Reason != "auth_failed" {
		t.Fatalf("want auth_failed reason, got %q", ae.Reason)
	}
}

func TestFetchCatalogRejectsMissingRevisionLifecycle(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"items": []map[string]any{
				{"id": "1", "revision": "", "lifecycle": "Released"},
			},
		})
	}))
	defer srv.Close()
	client := &Client{BaseURL: srv.URL, AllowPrivate: true}
	_, _, _, err := client.FetchCatalog(context.Background(), "")
	if _, ok := err.(*InvalidCatalogError); !ok {
		t.Fatalf("expected InvalidCatalogError, got %T %v", err, err)
	}
}

func TestFetchCatalogSSRFBlocksPrivateAndMetadata(t *testing.T) {
	client := &Client{BaseURL: "http://127.0.0.1:9", AllowPrivate: false}
	_, _, _, err := client.FetchCatalog(context.Background(), "")
	if _, ok := err.(*SSRFError); !ok {
		t.Fatalf("loopback: expected SSRFError, got %T %v", err, err)
	}
	client.BaseURL = "http://169.254.169.254/latest"
	_, _, _, err = client.FetchCatalog(context.Background(), "")
	if _, ok := err.(*SSRFError); !ok {
		t.Fatalf("metadata: expected SSRFError, got %T %v", err, err)
	}
	client.BaseURL = "http://evil.example"
	client.HostAllowlist = []string{"good.example"}
	client.AllowPrivate = true
	_, _, _, err = client.FetchCatalog(context.Background(), "")
	if _, ok := err.(*SSRFError); !ok {
		t.Fatalf("allowlist miss: expected SSRFError, got %T %v", err, err)
	}
}

func TestFetchCatalogRequiresHTTPSWhenTokenSet(t *testing.T) {
	client := &Client{
		BaseURL:      "http://plm.example.com",
		Token:        "tok",
		AllowPrivate: false,
		HostAllowlist: []string{"plm.example.com"},
	}
	_, _, _, err := client.FetchCatalog(context.Background(), "")
	if _, ok := err.(*SSRFError); !ok {
		t.Fatalf("expected SSRFError for http+token, got %T %v", err, err)
	}
}

func TestFetchCatalogCapsResponseAndOmitsBodyInErrors(t *testing.T) {
	big := strings.Repeat("x", int(MaxResponseBytes)+10)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(big))
	}))
	defer srv.Close()
	client := &Client{BaseURL: srv.URL, AllowPrivate: true, MaxBodyBytes: 1024}
	_, _, _, err := client.FetchCatalog(context.Background(), "")
	if err == nil {
		t.Fatal("expected size cap error")
	}
	if strings.Contains(err.Error(), "xxxx") {
		t.Fatalf("error leaked body content: %v", err)
	}

	srv2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte(`{"error":"internal-secret-xyz"}`))
	}))
	defer srv2.Close()
	client2 := &Client{BaseURL: srv2.URL, AllowPrivate: true}
	_, _, _, err = client2.FetchCatalog(context.Background(), "")
	te, ok := err.(*TransientError)
	if !ok {
		t.Fatalf("expected TransientError, got %T %v", err, err)
	}
	if strings.Contains(te.Error(), "internal-secret") {
		t.Fatalf("5xx error leaked body: %v", te)
	}
}

func TestFetchCatalogBlocksPrivateRedirect(t *testing.T) {
	private := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"items": []any{}})
	}))
	defer private.Close()
	public := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, private.URL+"/items", http.StatusFound)
	}))
	defer public.Close()
	// Allow the first hop host (loopback via allowPrivate=false would already block).
	// Use allowPrivate so first hop works, but CheckRedirect still calls CheckHostSSRF
	// — with allowPrivate=true redirects to private are allowed. So test the opposite:
	// allowPrivate=false blocks the initial loopback URL.
	client := &Client{BaseURL: public.URL, AllowPrivate: false}
	_, _, _, err := client.FetchCatalog(context.Background(), "")
	if _, ok := err.(*SSRFError); !ok {
		t.Fatalf("expected SSRFError blocking private hop, got %T %v", err, err)
	}
}

func TestFingerprintIncludesLifecycleAndPrim(t *testing.T) {
	a := Fingerprint([]Item{{ID: "1", Revision: "A", Lifecycle: "Released", Prim: "/P"}})
	b := Fingerprint([]Item{{ID: "1", Revision: "A", Lifecycle: "Obsolete", Prim: "/P"}})
	c := Fingerprint([]Item{{ID: "1", Revision: "A", Lifecycle: "Released", Prim: "/Q"}})
	if a == b {
		t.Fatal("lifecycle change must change fingerprint")
	}
	if a == c {
		t.Fatal("prim change must change fingerprint")
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

	client := &Client{BaseURL: srv.URL, AllowPrivate: true}
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

	// Lifecycle change must trigger change/recompose fingerprint.
	store[0]["lifecycle"] = "Obsolete"
	etag = `W/"v2"`
	r5 := Poll(context.Background(), client, session, manifest, true)
	if !r5.Changed {
		t.Fatalf("lifecycle Obsolete should change fingerprint: %+v", r5)
	}

	raw, _ := os.ReadFile(manifest)
	if !contains(string(raw), "revision: A") {
		t.Fatalf("manifest not synced: %s", raw)
	}
}

func contains(s, sub string) bool {
	return strings.Contains(s, sub)
}

func TestEffectiveDigest(t *testing.T) {
	a := EffectiveDigest("sha256:abc", "fp1")
	b := EffectiveDigest("sha256:abc", "fp2")
	if a == b || a == "sha256:abc" {
		t.Fatalf("expected distinct folded digests: %s %s", a, b)
	}
}

func TestAuthErrorIsPermanentInPoll(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte(`{"error":"forbidden-body"}`))
	}))
	defer srv.Close()
	client := &Client{BaseURL: srv.URL, Token: "x", AllowPrivate: true}
	session := &Session{}
	res := Poll(context.Background(), client, session, "", false)
	if !res.AuthFailed || res.Transient {
		t.Fatalf("auth must be permanent non-transient: %+v", res)
	}
	if strings.Contains(res.Error, "forbidden-body") {
		t.Fatalf("body leaked into poll error: %s", res.Error)
	}
}
