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

fallback_limited() {
  grep -E '^\{ *"type" *: *"(error|turn\.failed)"' "$1" |
    grep -qiE 'hit your[[:alnum:][:space:]-]{0,16}limit|usage limit|limit (reached|exceeded)|reached your[[:alnum:][:space:]-]{0,16}limit|at capacity|rate limit'
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

usage_fields() {
  python3 - "$1" <<'PY'
import json
import sys

found = None
codex = []
with open(sys.argv[1], encoding="utf-8", errors="replace") as handle:
    for line in handle:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or "usage" not in record:
            continue
        if record.get("type") == "turn.completed":
            codex.append(record["usage"] or {})
        else:
            found = record
if codex:
    def total(key):
        return sum(int(usage.get(key) or 0) for usage in codex)
    cached = total("cached_input_tokens")
    counts = [total("input_tokens") - cached, total("cache_write_input_tokens"), cached, total("output_tokens")]
    print(",".join(["", *map(str, counts), str(len(codex))]))
    sys.exit(0)
if found is None:
    print(",,,,,")
    sys.exit(0)
usage = found.get("usage") or {}
cost = f"{float(found.get('total_cost_usd') or 0):.4f}".rstrip("0").rstrip(".")
keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
counts = [str(int(usage.get(key) or 0)) for key in keys]
print(",".join([cost, *counts, str(int(found.get("num_turns") or 0))]))
PY
}

record_turn() {
  local turn="$1" row_id="$2" used_model="$3" status="$4" progress="$5" log_file="$6" fields
  fields="$(usage_fields "$log_file")"
  if [ ! -f .ralph/usage.csv ]; then
    echo "utc,turn,row,model,exit,progress,cost_usd,input,cache_write,cache_read,output,api_calls" >.ralph/usage.csv
  fi
  echo "$(date -u +%FT%TZ),$turn,$row_id,$used_model,$status,$progress,$fields" >>.ralph/usage.csv
  IFS=, read -r cost _input cache_write cache_read output calls <<<"$fields"
  log "turn $turn $row_id: $used_model \$${cost:-?}, ${calls:-?} calls, ${cache_read:-?} cache-read, ${cache_write:-?} cache-write, ${output:-?} output tokens, progress $progress"
}

commit_count() {
  git rev-list --branches --count 2>/dev/null || echo 0
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
  local base_model="${RALPH_MODEL:-sonnet}"
  local escalate_model="${RALPH_ESCALATE_MODEL:-opus}"
  local tools="${RALPH_TOOLS:-Bash,Read,Edit,Write,Glob,Grep,WebSearch,WebFetch}"
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
  export BASH_MAX_TIMEOUT_MS="${RALPH_BASH_MAX_MS:-3600000}"

  mkdir -p .ralph
  if ! command -v "$claude_bin" >/dev/null 2>&1; then
    log "agent '$claude_bin' is not on PATH"
    exit 127
  fi
  local fingerprint
  fingerprint="$(cksum <"$self")"

  local i=0 idle=0 row status stamp turn_log note prompt agent_status secs fallback_log
  local model row_id before progress
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
      if ! git checkout -q main 2>>ralph.log || ! git merge -q --ff-only origin/main 2>>ralph.log; then
        log "cannot return to an up-to-date main; commit or clear the work tree"
        notify "cannot return to an up-to-date main; the loop stopped"
        exit 1
      fi
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
    row_id="${row%% *}"
    model="$base_model"
    if [ "$(cat .ralph/escalate 2>/dev/null)" = "$row_id" ]; then
      model="$escalate_model"
    fi
    before="$(commit_count)"
    log "turn $((i + 1))/$max: $row ($model)"
    run_agent "$claude_bin" -p "$prompt" --model "$model" "${perm[@]}" \
      --append-system-prompt "$note" --output-format json --disable-slash-commands \
      --strict-mcp-config --tools "$tools" >"$turn_log" 2>&1 </dev/null
    agent_status=$?
    cat "$turn_log" >>ralph.log

    if [ "$agent_status" -ne 0 ] && is_limited "$turn_log"; then
      if [ -n "$fallback_bin" ]; then
        log "usage limit on $claude_bin; running the fallback agent"
        fallback_log="${turn_log%.log}-fallback.log"
        printf '%s\n\n%s\n' "$prompt" "$note" |
          run_agent "$fallback_bin" --dangerously-bypass-approvals-and-sandbox exec --json --cd "$PWD" - \
            >"$fallback_log" 2>&1
        agent_status=$?
        cat "$fallback_log" >>ralph.log
        if ! { [ "$agent_status" -ne 0 ] && fallback_limited "$fallback_log"; }; then
          i=$((i + 1))
          progress=no
          if [ "$(commit_count)" -gt "$before" ]; then
            progress=yes
          fi
          record_turn "$i" "$row_id" fallback "$agent_status" "$progress" "$fallback_log"
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
    progress=no
    if [ "$(commit_count)" -gt "$before" ]; then
      progress=yes
      rm -f .ralph/escalate
    else
      printf '%s\n' "$row_id" >.ralph/escalate
    fi
    record_turn "$i" "$row_id" "$model" "$agent_status" "$progress" "$turn_log"
    sleep "$pause"
  done
  log "loop finished after $i turn(s)"
}

main "$@"
exit $?
