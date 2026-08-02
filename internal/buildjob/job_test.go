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

func TestExecutionKeyChangesWithPublishSpec(t *testing.T) {
	d := "sha256:a81f94c2aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	k1 := ExecutionKey(d, &twinopsv1alpha1.OutputPublish{Mode: "configmap"})
	k2 := ExecutionKey(d, &twinopsv1alpha1.OutputPublish{Mode: "oci", Repository: "ghcr.io/org/a"})
	k3 := ExecutionKey(d, &twinopsv1alpha1.OutputPublish{Mode: "oci", Repository: "ghcr.io/org/b"})
	k4 := ExecutionKey(d, &twinopsv1alpha1.OutputPublish{Mode: "s3", S3Bucket: "twins"})
	if k1 == k2 || k2 == k3 || k1 == k4 {
		t.Fatalf("execution keys must differ by publish dest: %s %s %s %s", k1, k2, k3, k4)
	}
	// Same publish fingerprint is stable.
	if ExecutionKey(d, &twinopsv1alpha1.OutputPublish{Mode: "oci", Repository: "ghcr.io/org/a"}) != k2 {
		t.Fatal("execution key not stable")
	}
	// Input change also changes key.
	d2 := "sha256:b92e05d3bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	if ExecutionKey(d2, &twinopsv1alpha1.OutputPublish{Mode: "configmap"}) == k1 {
		t.Fatal("input digest must change execution key")
	}
}

func TestJobAndResultNamesKeyByExecKey(t *testing.T) {
	twin := &twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: "assembly-line-a", Namespace: "ns", Generation: 1},
	}
	d1 := "sha256:a81f94c2aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	exec1 := ExecutionKey(d1, &twinopsv1alpha1.OutputPublish{Mode: "configmap"})
	exec2 := ExecutionKey(d1, &twinopsv1alpha1.OutputPublish{Mode: "oci", Repository: "r"})
	j1 := JobName(twin, exec1)
	j2 := JobName(twin, exec2)
	if j1 == j2 {
		t.Fatalf("jobs must differ by publish-spec: %s", j1)
	}
	if !stringsHasPrefix(j1, "assembly-line-a-build-") {
		t.Fatalf("job name: %s", j1)
	}
	r1 := ResultConfigMapName(twin, exec1)
	if !stringsHasPrefix(r1, "assembly-line-a-build-result-") {
		t.Fatalf("result cm: %s", r1)
	}
	// Generation must not affect job name.
	if JobName(twin, exec1) != JobName(&twinopsv1alpha1.DigitalTwin{
		ObjectMeta: metav1.ObjectMeta{Name: twin.Name, Generation: 99},
	}, exec1) {
		t.Fatal("generation must not affect job name")
	}
}

func stringsHasPrefix(s, p string) bool {
	return len(s) >= len(p) && s[:len(p)] == p
}
