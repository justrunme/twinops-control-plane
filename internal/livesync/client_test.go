package livesync

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestFetch(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/ready", func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer tok" {
			t.Fatalf("missing auth header: %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ready","twin":"assembly-line-a"}`))
	})
	mux.HandleFunc("/api/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok","version":"0.4.0"}`))
	})
	mux.HandleFunc("/api/metrics", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"hasDrift":true,"highlightedPrims":2,"timelineEvents":5}`))
	})
	server := httptest.NewServer(mux)
	defer server.Close()

	snap, err := Fetch(context.Background(), server.URL, "tok")
	if err != nil {
		t.Fatal(err)
	}
	if !snap.Ready || snap.Twin != "assembly-line-a" || !snap.HasDrift || snap.HighlightedPrims != 2 {
		t.Fatalf("unexpected snapshot: %+v", snap)
	}
}
