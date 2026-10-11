package livesync

import (
	"fmt"
	"net/url"
	"strings"

	"github.com/justrunme/twinops-control-plane/internal/artifacts"
)

// ValidateURL checks liveAPIURL scheme, optional host allowlist, and SSRF policy.
// Schemes are restricted to http/https. Link-local, metadata, and loopback hosts
// are blocked unless allowPrivate is true. When allowHosts is non-empty, the
// hostname must match one of the allowlisted hosts (case-insensitive).
func ValidateURL(raw string, allowPrivate bool, allowHosts []string) error {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	parsed, err := url.Parse(raw)
	if err != nil {
		return fmt.Errorf("liveAPIURL: %w", err)
	}
	scheme := strings.ToLower(parsed.Scheme)
	if scheme != "https" && scheme != "http" {
		return fmt.Errorf("liveAPIURL scheme must be http or https")
	}
	host := parsed.Hostname()
	if host == "" {
		return fmt.Errorf("liveAPIURL missing host")
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
			return fmt.Errorf("liveAPIURL host %q not in operator allowlist", host)
		}
	}
	if err := artifacts.CheckHostSSRF(host, allowPrivate); err != nil {
		return fmt.Errorf("liveAPIURL: %w", err)
	}
	return nil
}
