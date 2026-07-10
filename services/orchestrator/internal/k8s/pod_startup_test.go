package k8s

import (
	"strings"
	"testing"
)

// The VM startup script injects the user's SSH public keys via the quoted
// $AUTHORIZED_KEYS env var. Guard the safety-critical shape: password step
// preserved, injection guarded + quoted, permissions locked, supervisord exec'd.
func TestContainerStartupArgs_InjectsAuthorizedKeysSafely(t *testing.T) {
	args := containerStartupArgs()

	base := []string{
		`echo "root:$ROOT_PASSWORD" | chpasswd`,
		`exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf`,
	}
	for _, want := range base {
		if !strings.Contains(args, want) {
			t.Errorf("startup args missing base step %q\ngot: %s", want, args)
		}
	}

	injection := []string{
		`[ -z "$AUTHORIZED_KEYS" ]`,        // no-op guard: password-only VMs unaffected
		`printf '%s\n' "$AUTHORIZED_KEYS"`, // quoted → contents never shell-interpreted
		`> /root/.ssh/authorized_keys`,
		`chmod 700 /root/.ssh`,
		`chmod 600 /root/.ssh/authorized_keys`,
	}
	for _, want := range injection {
		if !strings.Contains(args, want) {
			t.Errorf("startup args missing key-injection step %q\ngot: %s", want, args)
		}
	}

	// AUTHORIZED_KEYS must never be referenced unquoted (command-injection guard):
	// every occurrence is inside double quotes.
	if strings.Contains(args, "$AUTHORIZED_KEYS") &&
		strings.Count(args, `"$AUTHORIZED_KEYS"`) != strings.Count(args, "$AUTHORIZED_KEYS") {
		t.Errorf("AUTHORIZED_KEYS referenced unquoted in: %s", args)
	}
}
