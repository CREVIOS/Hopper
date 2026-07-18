# Hopper: mark the VM active on every interactive shell command so the
# idle-detection agent does not reclaim a session you are actively using.
# Paired with /usr/local/bin/hopper-idle-agent.py, which reports the
# /tmp/active marker (and SSH / code-server activity) to the API gateway.
_hopper_mark_active() { : > /tmp/active 2>/dev/null || true; }
case "${PROMPT_COMMAND:-}" in
  *_hopper_mark_active*) ;;
  "") PROMPT_COMMAND="_hopper_mark_active" ;;
  *)  PROMPT_COMMAND="_hopper_mark_active;${PROMPT_COMMAND}" ;;
esac
