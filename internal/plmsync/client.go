// Package plmsync polls a vendor-neutral REST PLM and syncs revisions into twin.yaml.
package plmsync

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"sigs.k8s.io/yaml"
)

// Item is a normalized PLM catalog entry.
type Item struct {
	ID        string
	Revision  string
	Lifecycle string
	Prim      string
	Name      string
}

// Result is the outcome of one poll/sync attempt.
type Result struct {
	Changed             bool
	NotModified         bool
	ETag                string
	Fingerprint         string
	Items               int
	Conflict            bool
	ConflictMessage     string
	Transient           bool
	AuthFailed          bool
	InvalidCatalog      bool
	SSRFBlocked         bool
	Error               string
	Resynced            bool
	ConsecutiveFailures int64
	InOutage            bool
	ResyncCount         int64
}

// Session tracks ETag / outage / resync across reconciles.
type Session struct {
	ETag                string
	Fingerprint         string
	ResyncCount         int64
	ConsecutiveFailures int64
	InOutage            bool
	Conflict            bool
	ConflictMessage     string
	LastError           string
}

// Client talks to GET /items with optional bearer token and ETag.
type Client struct {
	BaseURL       string
	Token         string
	HTTPClient    *http.Client
	Timeout       time.Duration
	AllowPrivate  bool
	HostAllowlist []string
	MaxBodyBytes  int64
}

func (c *Client) http() *http.Client {
	if c.HTTPClient != nil {
		return c.HTTPClient
	}
	return safeHTTPClient(c.Timeout, c.AllowPrivate)
}

func (c *Client) maxBody() int64 {
	if c.MaxBodyBytes > 0 {
		return c.MaxBodyBytes
	}
	return MaxResponseBytes
}

type rawItem struct {
	ID        string         `json:"id"`
	ItemID    string         `json:"itemId"`
	Revision  string         `json:"revision"`
	Lifecycle string         `json:"lifecycle"`
	Prim      string         `json:"prim"`
	Name      string         `json:"name"`
	Metadata  map[string]any `json:"metadata"`
}

// FetchCatalog GETs /items with If-None-Match when session has an ETag.
// Response bodies are never returned in errors (status + classified reason only).
func (c *Client) FetchCatalog(ctx context.Context, etag string) ([]Item, string, bool, error) {
	if err := ValidateURL(c.BaseURL, c.Token, c.AllowPrivate, c.HostAllowlist); err != nil {
		return nil, "", false, &SSRFError{Reason: err.Error()}
	}
	url := strings.TrimRight(c.BaseURL, "/") + "/items"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, "", false, err
	}
	req.Header.Set("Accept", "application/json")
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}
	if etag != "" {
		req.Header.Set("If-None-Match", etag)
	}
	resp, err := c.http().Do(req)
	if err != nil {
		return nil, "", false, fmt.Errorf("plm fetch: %w", err)
	}
	defer resp.Body.Close()
	limited := io.LimitReader(resp.Body, c.maxBody()+1)
	body, err := io.ReadAll(limited)
	if err != nil {
		return nil, "", false, fmt.Errorf("plm read: %w", err)
	}
	if int64(len(body)) > c.maxBody() {
		return nil, "", false, &TransientError{Code: http.StatusRequestEntityTooLarge, Reason: "response_too_large"}
	}
	newETag := resp.Header.Get("ETag")
	reason := ClassifyReason(resp.StatusCode)
	switch resp.StatusCode {
	case http.StatusNotModified:
		if newETag == "" {
			newETag = etag
		}
		return nil, newETag, true, nil
	case http.StatusUnauthorized, http.StatusForbidden:
		return nil, newETag, false, &AuthError{Code: resp.StatusCode, Reason: reason}
	case http.StatusConflict:
		return nil, newETag, false, &ConflictError{Reason: reason, ETag: newETag}
	default:
		if resp.StatusCode >= 500 {
			return nil, newETag, false, &TransientError{Code: resp.StatusCode, Reason: reason}
		}
		if resp.StatusCode != http.StatusOK {
			return nil, newETag, false, fmt.Errorf("plm HTTP %d: %s", resp.StatusCode, reason)
		}
	}
	items, err := decodeItems(body)
	if err != nil {
		return nil, newETag, false, err
	}
	return items, newETag, false, nil
}

func decodeItems(body []byte) ([]Item, error) {
	var asList []rawItem
	if err := json.Unmarshal(body, &asList); err == nil {
		return normalize(asList)
	}
	var wrapped struct {
		Items []rawItem `json:"items"`
	}
	if err := json.Unmarshal(body, &wrapped); err != nil {
		return nil, fmt.Errorf("plm decode: %w", err)
	}
	return normalize(wrapped.Items)
}

func normalize(raw []rawItem) ([]Item, error) {
	out := make([]Item, 0, len(raw))
	for _, r := range raw {
		id := r.ID
		if id == "" {
			id = r.ItemID
		}
		if id == "" {
			continue
		}
		prim := r.Prim
		name := r.Name
		if r.Metadata != nil {
			if prim == "" {
				if v, ok := r.Metadata["prim"].(string); ok {
					prim = v
				}
			}
			if name == "" {
				if v, ok := r.Metadata["name"].(string); ok {
					name = v
				}
			}
		}
		rev := strings.TrimSpace(r.Revision)
		life := strings.TrimSpace(r.Lifecycle)
		if rev == "" || life == "" {
			return nil, &InvalidCatalogError{
				ItemID: id,
				Reason: "missing_revision_or_lifecycle",
			}
		}
		out = append(out, Item{ID: id, Revision: rev, Lifecycle: life, Prim: prim, Name: name})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out, nil
}

// Fingerprint returns sha256 of sorted itemId:revision:lifecycle:prim tuples.
// Lifecycle/prim are included so Released→Obsolete (or prim remap) triggers recompose.
func Fingerprint(items []Item) string {
	parts := make([]string, 0, len(items))
	for _, it := range items {
		parts = append(parts, it.ID+":"+it.Revision+":"+it.Lifecycle+":"+it.Prim)
	}
	sum := sha256.Sum256([]byte(strings.Join(parts, ",")))
	return hex.EncodeToString(sum[:])
}

// EffectiveDigest folds artifact digest with PLM fingerprint.
func EffectiveDigest(artifactDigest, fingerprint string) string {
	if fingerprint == "" {
		return artifactDigest
	}
	sum := sha256.Sum256([]byte(artifactDigest + "|" + fingerprint))
	return "sha256:" + hex.EncodeToString(sum[:])
}

// SyncManifest rewrites spec.plm.mappings in twin.yaml from catalog items.
func SyncManifest(path string, items []Item) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return err
	}
	spec, _ := doc["spec"].(map[string]any)
	if spec == nil {
		spec = map[string]any{}
		doc["spec"] = spec
	}
	plm, _ := spec["plm"].(map[string]any)
	if plm == nil {
		plm = map[string]any{}
		spec["plm"] = plm
	}
	if _, ok := plm["provider"]; !ok {
		plm["provider"] = "rest"
	}
	mappings := make([]any, 0, len(items))
	for _, it := range items {
		m := map[string]any{
			"itemId":    it.ID,
			"revision":  it.Revision,
			"lifecycle": it.Lifecycle,
		}
		if it.Prim != "" {
			m["prim"] = it.Prim
		}
		mappings = append(mappings, m)
	}
	plm["mappings"] = mappings
	out, err := yaml.Marshal(doc)
	if err != nil {
		return err
	}
	return os.WriteFile(path, out, 0o644)
}

// Poll runs one poll against the PLM and updates session + optional manifest.
func Poll(ctx context.Context, client *Client, session *Session, manifestPath string, syncManifest bool) Result {
	wasOutage := session.InOutage
	items, etag, notMod, err := client.FetchCatalog(ctx, session.ETag)
	res := Result{
		ETag:                session.ETag,
		Fingerprint:         session.Fingerprint,
		ResyncCount:         session.ResyncCount,
		ConsecutiveFailures: session.ConsecutiveFailures,
		InOutage:            session.InOutage,
	}
	if err != nil {
		session.ConsecutiveFailures++
		session.InOutage = true
		session.LastError = err.Error()
		res.Error = err.Error()
		res.ConsecutiveFailures = session.ConsecutiveFailures
		res.InOutage = true
		switch e := err.(type) {
		case *ConflictError:
			session.Conflict = true
			session.ConflictMessage = e.Error()
			res.Conflict = true
			res.ConflictMessage = e.Error()
			if e.ETag != "" {
				res.ETag = e.ETag
			}
		case *AuthError:
			res.AuthFailed = true
			// Permanent — do not mark transient (no infinite retry).
		case *SSRFError:
			res.SSRFBlocked = true
		case *InvalidCatalogError:
			res.InvalidCatalog = true
		case *TransientError:
			res.Transient = true
		default:
			res.Transient = true
		}
		return res
	}

	if notMod {
		if wasOutage {
			session.ResyncCount++
			session.InOutage = false
			res.Resynced = true
		}
		session.ConsecutiveFailures = 0
		session.LastError = ""
		session.Conflict = false
		session.ConflictMessage = ""
		if etag != "" {
			session.ETag = etag
		}
		res.NotModified = true
		res.ETag = session.ETag
		res.Fingerprint = session.Fingerprint
		res.ResyncCount = session.ResyncCount
		res.ConsecutiveFailures = 0
		res.InOutage = false
		return res
	}

	fp := Fingerprint(items)
	changed := fp != session.Fingerprint
	if wasOutage {
		session.ResyncCount++
		session.InOutage = false
		res.Resynced = true
	}
	session.ETag = etag
	session.Fingerprint = fp
	session.ConsecutiveFailures = 0
	session.LastError = ""
	session.Conflict = false
	session.ConflictMessage = ""
	if changed && syncManifest && manifestPath != "" {
		if err := SyncManifest(manifestPath, items); err != nil {
			session.ConsecutiveFailures++
			session.InOutage = true
			session.LastError = err.Error()
			res.Error = err.Error()
			res.Transient = true
			res.ConsecutiveFailures = session.ConsecutiveFailures
			res.InOutage = true
			return res
		}
	}
	res.Changed = changed
	res.ETag = session.ETag
	res.Fingerprint = session.Fingerprint
	res.Items = len(items)
	res.ResyncCount = session.ResyncCount
	res.ConsecutiveFailures = 0
	res.InOutage = false
	return res
}

// AuthError is HTTP 401/403 (permanent).
type AuthError struct {
	Code   int
	Reason string
}

func (e *AuthError) Error() string {
	if e.Reason == "" {
		e.Reason = ClassifyReason(e.Code)
	}
	return fmt.Sprintf("plm auth HTTP %d: %s", e.Code, e.Reason)
}

// ConflictError is HTTP 409.
type ConflictError struct {
	Reason string
	ETag   string
}

func (e *ConflictError) Error() string {
	if e.Reason == "" {
		e.Reason = "conflict"
	}
	return fmt.Sprintf("plm conflict: %s", e.Reason)
}

// TransientError is HTTP 5xx / retryable.
type TransientError struct {
	Code   int
	Reason string
}

func (e *TransientError) Error() string {
	if e.Reason == "" {
		e.Reason = ClassifyReason(e.Code)
	}
	return fmt.Sprintf("plm transient HTTP %d: %s", e.Code, e.Reason)
}

// SSRFError is a blocked / disallowed PLM URL (permanent until spec/config changes).
type SSRFError struct {
	Reason string
}

func (e *SSRFError) Error() string {
	return fmt.Sprintf("plm ssrf blocked: %s", e.Reason)
}

// InvalidCatalogError is a fail-closed catalog (missing revision/lifecycle).
type InvalidCatalogError struct {
	ItemID string
	Reason string
}

func (e *InvalidCatalogError) Error() string {
	return fmt.Sprintf("plm invalid catalog item %q: %s", e.ItemID, e.Reason)
}
