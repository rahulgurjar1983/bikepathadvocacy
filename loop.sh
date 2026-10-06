#!/usr/bin/env bash
set -uo pipefail

log() {
  printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a ralph.log
}

notify() {
  if ! $RALPH_NOTIFY_CMD "$*" >/dev/null 2>&1; then
    log "notify failed: $*"
  fi
}

is_limited() {
  grep -qiE 'hit your[[:alnum:][:space:]-]{0,16}limit|usage limit|limit (reached|exceeded)|reached your[[:alnum:][:space:]-]{0,16}limit' "$1"
}

reset_secs() {
  local line clock zone target now secs
  line="$(grep -ioE '(resets|try again at|available at)[^.]*' "$1" | tail -1)"
  clock="$(printf '%s' "$line" | grep -oiE '[0-9]{1,2}(:[0-9]{2})?[[:space:]]*(am|pm)' | tail -1)"
  zone="$(printf '%s' "$line" | grep -oE '\([A-Za-z_]+/[A-Za-z_]+\)' | tr -d '()' | tail -1)"
  if [ -n "$clock" ]; then
    target="$(TZ="${zone:-${TZ:-}}" date -d "$clock" +%s 2>/dev/null || true)"
    now="$(date +%s)"
    if [ -n "$target" ]; then
      secs=$((target - now))
      if [ "$secs" -lt 0 ]; then
        secs=$((secs + 86400))
      fi
      echo $((secs + 60))
      return
    fi
  fi
  echo "$RALPH_BACKOFF_SECS"
}

run_agent() {
  timeout --kill-after=60 "$RALPH_TURN_SECS" "$@"
}

main() {
  cd "$(dirname "$0")" || exit 1
  local self="$PWD/loop.sh"
  local max="${1:-200}"
  case "$max" in '' | *[!0-9]*) max=200 ;; esac
  local flags=()
  local perm=(--permission-mode acceptEdits)
  local arg
  for arg in "$@"; do
    if [ "$arg" = "--yolo" ]; then
      perm=(--dangerously-skip-permissions)
      flags+=("$arg")
    fi
  done

  local claude_bin="${RALPH_CLAUDE_BIN:-claude}"
  local fallback_bin="${RALPH_FALLBACK_BIN:-}"
  local prompt_file="${RALPH_PROMPT_FILE:-PROMPT.md}"
  local pick_cmd="${RALPH_PICK_CMD:-uv run --frozen python -m gates.ledger pick}"
  local model="${RALPH_MODEL:-opus}"
  local pause="${RALPH_PAUSE_SECS:-5}"
  local hold_poll="${RALPH_HOLD_POLL_SECS:-30}"
  local idle_secs="${RALPH_IDLE_SECS:-1800}"
  local max_idle="${RALPH_MAX_IDLE:-0}"
  local max_sleep="${RALPH_MAX_SLEEP_SECS:-21600}"
  RALPH_NOTIFY_CMD="${RALPH_NOTIFY_CMD:-scripts/notify.sh}"
  RALPH_TURN_SECS="${RALPH_TURN_SECS:-7200}"
  RALPH_BACKOFF_SECS="${RALPH_BACKOFF_SECS:-1800}"
  export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-Ralph (bikeplan)}"
  export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-ralph@bikeplan.invalid}"
  export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-$GIT_AUTHOR_NAME}"
  export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-$GIT_AUTHOR_EMAIL}"

  mkdir -p .ralph
  if ! command -v "$claude_bin" >/dev/null 2>&1; then
    log "agent '$claude_bin' is not on PATH"
    exit 127
  fi
  local fingerprint
  fingerprint="$(cksum <"$self")"

  local i=0 idle=0 row status stamp turn_log note prompt agent_status secs fallback_log
  while [ "$i" -lt "$max" ]; do
    if [ -f STOP ]; then
      log "STOP file present; ending after $i turn(s)"
      break
    fi
    if [ -f HOLD ]; then
      log "HOLD file present; waiting until it is removed"
      while [ -f HOLD ] && [ ! -f STOP ]; do
        sleep "$hold_poll"
      done
      continue
    fi
    if [ "${RALPH_SKIP_SYNC:-0}" != 1 ]; then
      git fetch -q origin 2>>ralph.log || log "git fetch failed; working from the last fetch"
    fi
    if [ "$(cksum <"$self")" != "$fingerprint" ]; then
      log "loop.sh changed; starting the new copy for $((max - i)) turn(s)"
      exec bash "$self" "$((max - i))" ${flags[@]+"${flags[@]}"}
    fi

    row="$($pick_cmd 2>>ralph.log)"
    status=$?
    if [ "$status" -eq 3 ]; then
      idle=$((idle + 1))
      log "no open row in PROGRESS.md (idle check $idle)"
      if [ "$idle" -eq 1 ]; then
        notify "no open row left in PROGRESS.md; the loop is idle"
      fi
      if [ "$max_idle" -gt 0 ] && [ "$idle" -ge "$max_idle" ]; then
        break
      fi
      sleep "$idle_secs"
      continue
    fi
    if [ "$status" -ne 0 ]; then
      log "row picker failed with exit $status; fix PROGRESS.md"
      notify "row picker failed with exit $status; the loop stopped"
      exit 1
    fi
    idle=0

    if ! prompt="$(cat "$prompt_file")"; then
      log "prompt file $prompt_file is missing"
      exit 1
    fi
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    turn_log=".ralph/iter-${stamp}-$((i + 1)).log"
    note="You are one turn of the Ralph loop. Work on this row only: ${row}. Follow PROMPT.md."
    log "turn $((i + 1))/$max: $row"
    run_agent "$claude_bin" -p "$prompt" --model "$model" "${perm[@]}" \
      --append-system-prompt "$note" >"$turn_log" 2>&1 </dev/null
    agent_status=$?
    cat "$turn_log" >>ralph.log

    if [ "$agent_status" -ne 0 ] && is_limited "$turn_log"; then
      if [ -n "$fallback_bin" ]; then
        log "usage limit on $claude_bin; running the fallback agent"
        fallback_log="${turn_log%.log}-fallback.log"
        printf '%s\n\n%s\n' "$prompt" "$note" |
          run_agent "$fallback_bin" --dangerously-bypass-approvals-and-sandbox exec --cd "$PWD" - \
            >"$fallback_log" 2>&1
        agent_status=$?
        cat "$fallback_log" >>ralph.log
        if ! { [ "$agent_status" -ne 0 ] && is_limited "$fallback_log"; }; then
          i=$((i + 1))
          log "turn $i done by the fallback agent (exit $agent_status)"
          sleep "$pause"
          continue
        fi
      fi
      secs="$(reset_secs "$turn_log")"
      if [ "$secs" -gt "$max_sleep" ]; then
        secs="$max_sleep"
      fi
      log "usage limit hit; sleeping ${secs}s; this turn does not count"
      sleep "$secs"
      continue
    fi

    if [ "$agent_status" -eq 124 ] || [ "$agent_status" -eq 137 ]; then
      log "turn $((i + 1)) hit the time bound of ${RALPH_TURN_SECS}s"
    elif [ "$agent_status" -ne 0 ]; then
      log "turn $((i + 1)) ended with exit $agent_status"
    fi
    i=$((i + 1))
    sleep "$pause"
  done
  log "loop finished after $i turn(s)"
}

main "$@"
exit $?
