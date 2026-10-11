package plmsync

import (
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/justrunme/twinops-control-plane/internal/artifacts"
)

const (
	// MaxResponseBytes caps a single PLM HTTP response body.
	MaxResponseBytes int64 = 1 << 20 // 1 MiB
)

// ValidateURL enforces PLM SSRF policy: scheme, optional host allowlist,
// private/link-local/loopback/metadata blocking (via DNS), and https when a token is set.
func ValidateURL(raw string, token string, allowPrivate bool, allowHosts []string) error {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return fmt.Errorf("plm url is empty")
	}
	parsed, err := url.Parse(raw)
	if err != nil {
		return fmt.Errorf("plm url: %w", err)
	}
	scheme := strings.ToLower(parsed.Scheme)
	if scheme != "https" && scheme != "http" {
		return fmt.Errorf("plm url scheme must be http or https")
	}
	if token != "" && scheme != "https" && !allowPrivate {
		return fmt.Errorf("plm url must use https when a token is configured")
	}
	host := parsed.Hostname()
	if host == "" {
		return fmt.Errorf("plm url missing host")
	}
	if len(allowHosts) > 0 {
		ok := false
		lower := strings.ToLower(host)
		for _, h := range allowHosts {
			if strings.ToLower(strings.TrimSpace(h)) == lower {
				ok = true
				break
			}
		}
		if !ok {
			return fmt.Errorf("plm url host %q not in operator allowlist", host)
		}
	}
	if err := artifacts.CheckHostSSRF(host, allowPrivate); err != nil {
		return fmt.Errorf("plm url: %w", err)
	}
	return nil
}

// safeHTTPClient returns a client that re-checks SSRF on every redirect target.
func safeHTTPClient(timeout time.Duration, allowPrivate bool) *http.Client {
	if timeout <= 0 {
		timeout = 5 * time.Second
	}
	return &http.Client{
		Timeout: timeout,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) >= 5 {
				return fmt.Errorf("plm: too many redirects")
			}
			host := req.URL.Hostname()
			if err := artifacts.CheckHostSSRF(host, allowPrivate); err != nil {
				return fmt.Errorf("plm redirect: %w", err)
			}
			// Re-resolve DNS for redirect host (TOCTOU hardening).
			if ip := net.ParseIP(host); ip == nil {
				if err := artifacts.CheckHostSSRF(host, allowPrivate); err != nil {
					return err
				}
			}
			return nil
		},
	}
}

// ClassifyReason maps an HTTP status to a short reason suitable for status/events
// (never includes response bodies).
func ClassifyReason(code int) string {
	switch {
	case code == http.StatusUnauthorized || code == http.StatusForbidden:
		return "auth_failed"
	case code == http.StatusConflict:
		return "conflict"
	case code == http.StatusNotFound:
		return "not_found"
	case code == http.StatusNotModified:
		return "not_modified"
	case code == http.StatusRequestEntityTooLarge:
		return "response_too_large"
	case code >= 500:
		return "upstream_5xx"
	case code >= 400:
		return "client_error"
	default:
		return "unexpected_status"
	}
}
