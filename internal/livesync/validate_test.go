package livesync

import "testing"

func TestValidateURL(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name         string
		raw          string
		allowPrivate bool
		allowHosts   []string
		wantErr      bool
	}{
		{name: "empty", raw: ""},
		{name: "https public", raw: "https://example.com/api", wantErr: false},
		{name: "http loopback blocked", raw: "http://127.0.0.1:8080", wantErr: true},
		{name: "metadata blocked", raw: "http://169.254.169.254/latest", wantErr: true},
		{name: "loopback allowed in lab", raw: "http://127.0.0.1:8080", allowPrivate: true},
		{name: "bad scheme", raw: "ftp://example.com", wantErr: true},
		{name: "allowlist miss", raw: "https://example.com", allowHosts: []string{"other.example.com"}, wantErr: true},
		{name: "allowlist hit", raw: "https://example.com", allowHosts: []string{"example.com"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := ValidateURL(tc.raw, tc.allowPrivate, tc.allowHosts)
			if tc.wantErr && err == nil {
				t.Fatal("expected error")
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
		})
	}
}
