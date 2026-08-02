package buildjob

import (
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	twinopsv1alpha1 "github.com/justrunme/twinops-control-plane/api/v1alpha1"
)

func TestDigestKey(t *testing.T) {
	cases := []struct {
		in, want string
	}{
		{"sha256:a81f94c2deadbeefcafe", "a81f94c2dead"},
		{"SHA256:ABCDEF0123456789", "abcdef012345"},
		{"", "unknown"},
		{"not-a-digest", "unknown"},
		{"sha256:ab", "unknown"},
	}
	for _, tc := range cases {
		if got := DigestKey(tc.in); got != tc.want {
			t.Errorf("DigestKey(%q)=%q want %q", tc.in, got, tc.want)
		}
	}
}

func TestJobAndResultNamesKeyByDigest(t *testing.T) {
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "assembly-line-a", Namespace: "ns", Generation: 1},
	}
	d1 := "sha256:a81f94c2aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	d2 := "sha256:b92e05d3bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	j1 := JobName(twin, d1)
	j2 := JobName(twin, d2)
	if j1 == j2 {
		t.Fatalf("jobs must differ by input digest: %s", j1)
	}
	if j1 != "assembly-line-a-build-a81f94c2aaaa" {
		t.Fatalf("job name: %s", j1)
	}
	r1 := ResultConfigMapName(twin, d1)
	if r1 != "assembly-line-a-build-result-a81f94c2aaaa" {
		t.Fatalf("result cm: %s", r1)
	}
	// Generation must not appear in the name.
	if JobName(twin, d1) != JobName(&twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: twin.Name, Generation: 99},
	}, d1) {
		t.Fatal("generation must not affect job name")
	}
}
