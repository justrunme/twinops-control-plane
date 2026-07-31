package livesync

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// Snapshot is a compact view of a TwinOps live API for DigitalTwin status.
type Snapshot struct {
	Ready            bool
	Version          string
	Twin             string
	HasDrift         bool
	HighlightedPrims int
	TimelineEvents   int
}

type readyBody struct {
	Status string `json:"status"`
	Twin   string `json:"twin"`
}

type metricsBody struct {
	HasDrift         bool `json:"hasDrift"`
	HighlightedPrims int  `json:"highlightedPrims"`
	TimelineEvents   int  `json:"timelineEvents"`
}

type healthBody struct {
	Version string `json:"version"`
}

// Fetch probes /api/ready, /api/health, and /api/metrics on a live API base URL.
func Fetch(ctx context.Context, baseURL string, token string) (*Snapshot, error) {
	base := strings.TrimRight(baseURL, "/")
	client := &http.Client{Timeout: 3 * time.Second}

	ready, err := getJSON[readyBody](ctx, client, base+"/api/ready", token)
	if err != nil {
		return nil, err
	}
	health, err := getJSON[healthBody](ctx, client, base+"/api/health", token)
	if err != nil {
		return nil, err
	}
	metrics, err := getJSON[metricsBody](ctx, client, base+"/api/metrics", token)
	if err != nil {
		return nil, err
	}

	return &Snapshot{
		Ready:            ready.Status == "ready",
		Version:          health.Version,
		Twin:             ready.Twin,
		HasDrift:         metrics.HasDrift,
		HighlightedPrims: metrics.HighlightedPrims,
		TimelineEvents:   metrics.TimelineEvents,
	}, nil
}

func getJSON[T any](ctx context.Context, client *http.Client, url, token string) (*T, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("GET %s: HTTP %d", url, resp.StatusCode)
	}
	var out T
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &out, nil
}
