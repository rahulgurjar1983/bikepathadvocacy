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

provider_failed() {
  grep -qiE '(api|stream|server|http|request)[[:space:]]*error[[:space:][:punct:]]*(code[[:space:]]*)?(402|429|5[0-9][0-9])|overloaded_error|insufficient balance|authentication (failed|error)|unauthori[sz]ed|connection refused|network is unreachable' "$1"
}

rung_limited() {
  local rung="$1" status="$2" log_file="$3"
  [ "$status" -ne 0 ] || return 1
  case "$rung" in
    codex) fallback_limited "$log_file" ;;
    *) is_limited "$log_file" || provider_failed "$log_file" ;;
  esac
}

reset_secs() {
  python3 -m gates.providerwait --default "$RALPH_BACKOFF_SECS" "$@"
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
  if [ "$used_model" = deepseek ]; then
    fields=",${fields#*,}"
  fi
  if [ ! -f .ralph/usage.csv ]; then
    echo "utc,turn,row,model,exit,progress,cost_usd,input,cache_write,cache_read,output,api_calls" >.ralph/usage.csv
  fi
  echo "$(date -u +%FT%TZ),$turn,$row_id,$used_model,$status,$progress,$fields" >>.ralph/usage.csv
  IFS=, read -r cost _input cache_write cache_read output calls <<<"$fields"
  log "turn $turn $row_id: $used_model \$${cost:-?}, ${calls:-?} calls, ${cache_read:-?} cache-read, ${cache_write:-?} cache-write, ${output:-?} output tokens, progress $progress"
}

record_attempt() {
  local row="$1" provider="$2" requested="$3" effort="$4" status="$5" log_file="$6" fields progress=no
  fields="$(usage_fields "$log_file")"
  if [ "$(commit_count)" -gt "$before" ]; then
    progress=yes
  fi
  python3 - "$row" "$provider" "$requested" "$effort" "$status" "$progress" "$fields" <<'PYCODE'
import datetime
import json
import sys

row, provider, model, effort, status, progress, fields = sys.argv[1:]
values = fields.split(",")
entry = {
    "utc": datetime.datetime.now(datetime.UTC).isoformat(),
    "row": row, "provider": provider, "model": model, "effort": effort,
    "exit": int(status), "progress": progress,
    "cost_usd": float(values[0]) if values[0] and provider != "deepseek" else None,
}
for key, value in zip(("input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens", "api_calls"), values[1:], strict=True):
    entry[key] = int(value) if value else None
with open(".ralph/model-usage.jsonl", "a") as target:
    target.write(json.dumps(entry, sort_keys=True) + "\n")
PYCODE
}

finish_row() {
  local row="$1" progress="$2" outcome reason
  if [ "$progress" = yes ]; then
    rm -f .ralph/escalate
  else
    printf '%s\n' "$row" >.ralph/escalate
  fi
  outcome="$(python3 -m gates.loopstate "$row" "$progress" "$max_stalls")" || return 2
  if [ "$outcome" = blocked ]; then
    reason="$(python3 - "$row" <<'PYCODE'
import sys
from gates.loopstate import read_state
print(read_state()[sys.argv[1]]["reason"])
PYCODE
    )" || return 2
    log "row $row blocked: $reason; inputs saved in .ralph/stalls.json"
  fi
}

bounded_backoff() {
  local until=$((SECONDS + $1)) remaining tick
  while [ "$SECONDS" -lt "$until" ] && [ ! -f STOP ] && [ ! -f HOLD ]; do
    remaining=$((until - SECONDS))
    tick="$hold_poll"
    if [ "$remaining" -lt "${hold_poll%.*}" ]; then
      tick="$remaining"
    fi
    sleep "$tick"
  done
}

commit_count() {
  git rev-list --branches --count 2>/dev/null || echo 0
}

codex_skills_off() {
  python3 - <<'PYCODE'
import json
import os
from pathlib import Path

home = Path.home()
roots = {Path(os.environ.get("CODEX_HOME", home / ".codex")) / "skills", home / ".agents/skills", Path("/etc/codex/skills")}
for parent in (Path.cwd(), *Path.cwd().parents):
    roots.update((parent / ".agents/skills", parent / ".codex/skills"))
paths = sorted({path.resolve() for root in roots if root.is_dir() for path in root.rglob("SKILL.md")})
entries = ["{path=" + json.dumps(str(path)) + ",enabled=false}" for path in paths]
print("skills.config=[" + ",".join(entries) + "]")
PYCODE
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
  local deepseek_env="${RALPH_DEEPSEEK_ENV:-}"
  local prompt_file="${RALPH_PROMPT_FILE:-PROMPT.md}"
  local pick_cmd="${RALPH_PICK_CMD:-uv run --frozen python -m gates.ledger pick}"
  local base_model="${RALPH_MODEL:-sonnet}"
  local escalate_model="${RALPH_ESCALATE_MODEL:-$base_model}"
  local reasoning_model="${RALPH_REASONING_MODEL:-$base_model}"
  local routine_effort="${RALPH_ROUTINE_EFFORT:-medium}"
  local reasoning_effort="${RALPH_REASONING_EFFORT:-high}"
  local codex_routine="${RALPH_CODEX_ROUTINE_MODEL:-gpt-6.1-sol}"
  local codex_reasoning="${RALPH_CODEX_REASONING_MODEL:-$codex_routine}"
  local codex_routine_effort="${RALPH_CODEX_ROUTINE_EFFORT:-medium}"
  local codex_reasoning_effort="${RALPH_CODEX_REASONING_EFFORT:-high}"
  local premium_allowed="${RALPH_ALLOW_PREMIUM:-0}"
  case "$premium_allowed" in 0 | 1) ;; *) log "RALPH_ALLOW_PREMIUM must be 0 or 1"; exit 2 ;; esac
  local max_stalls="${RALPH_MAX_STALLS:-3}"
  case "$max_stalls" in '' | 0 | *[!0-9]*) log "RALPH_MAX_STALLS must be positive"; exit 2 ;; esac
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
  local rungs=() deepseek_settings=() line
  if [ -n "$fallback_bin" ]; then
    if ! command -v "$fallback_bin" >/dev/null 2>&1; then
      log "fallback agent '$fallback_bin' is not on PATH"
      exit 127
    fi
    rungs+=(codex)
  fi
  if [ -n "$deepseek_env" ]; then
    if [ ! -r "$deepseek_env" ]; then
      log "deepseek settings $deepseek_env cannot be read"
      exit 1
    fi
    while IFS= read -r line || [ -n "$line" ]; do
      case "$line" in
        '' | '#'*) ;;
        *=*) deepseek_settings+=("$line") ;;
      esac
    done <"$deepseek_env"
    if [ "${#deepseek_settings[@]}" -eq 0 ]; then
      log "deepseek settings $deepseek_env name no setting"
      exit 1
    fi
    rungs+=(deepseek)
  fi
  local fingerprint
  fingerprint="$(cksum <"$self")"

  local i=0 idle=0 row status stamp turn_log note prompt agent_status secs rung rung_log
  local model row_id before progress effort role codex_model codex_effort codex_skills
  local limited_logs=()
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
      if ! git fetch -q origin 2>>ralph.log; then
        log "git fetch failed; the loop stopped"
        exit 2
      fi
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
    row_id="${row%% *}"
    note="$row_id"
    prompt+=$'\n\n'"Work on this row only: ${row}. Follow PROMPT.md. The system turn note is its row ID."
    model="$base_model"
    effort="$routine_effort"
    role=routine
    if [[ "$row" == *"[reasoning]"* ]]; then
      model="$reasoning_model"
      effort="$reasoning_effort"
      role=reasoning
    elif [ "$(cat .ralph/escalate 2>/dev/null)" = "$row_id" ]; then
      model="$escalate_model"
      effort="$reasoning_effort"
      role=reasoning
    fi
    codex_model="$codex_routine"
    codex_effort="$codex_routine_effort"
    if [ "$role" = reasoning ]; then
      codex_model="$codex_reasoning"
      codex_effort="$codex_reasoning_effort"
    fi
    if [ "$premium_allowed" != 1 ]; then
      model="$base_model"
      codex_model="$codex_routine"
      effort="$routine_effort"
      codex_effort="$codex_routine_effort"
      if [ "$(cat .ralph/escalate 2>/dev/null)" = "$row_id" ]; then
        effort="$reasoning_effort"
        codex_effort="$codex_reasoning_effort"
      fi
    fi
    rm -f .ralph/turn-result.json
    before="$(commit_count)"
    log "turn $((i + 1))/$max: $row ($model, effort $effort, role $role)"
    run_agent "$claude_bin" -p "$prompt" --model "$model" --effort "$effort" "${perm[@]}" \
      --append-system-prompt "$note" --output-format json --disable-slash-commands \
      --strict-mcp-config --tools "$tools" >"$turn_log" 2>&1 </dev/null
    agent_status=$?
    cat "$turn_log" >>ralph.log
    record_attempt "$row_id" claude "$model" "$effort" "$agent_status" "$turn_log" || exit 2

    if [ "$agent_status" -ne 0 ] && { is_limited "$turn_log" || provider_failed "$turn_log"; }; then
      limited_logs=("$turn_log")
      for rung in ${rungs[@]+"${rungs[@]}"}; do
        if [ "$rung" = deepseek ] && [ "$role" = reasoning ]; then
          log "skipping third-party fallback for reasoning work"
          continue
        fi
        rm -f .ralph/turn-result.json
        log "usage limit on the agent before; running $rung"
        rung_log="${turn_log%.log}-$rung.log"
        if [ "$rung" = codex ]; then
          codex_skills="$(codex_skills_off)" || exit 2
          printf '%s\n\n%s\n' "$prompt" "$note" |
            run_agent "$fallback_bin" --dangerously-bypass-approvals-and-sandbox exec --json --ignore-user-config \
              --model "$codex_model" -c "model_reasoning_effort=\"$codex_effort\"" \
              -c 'features.multi_agent=false' -c 'features.multi_agent_v2=false' \
              -c 'features.plugins=false' -c "$codex_skills" --cd "$PWD" - \
              >"$rung_log" 2>&1
        else
          run_agent env -u ANTHROPIC_API_KEY "${deepseek_settings[@]}" "$claude_bin" -p "$prompt" "${perm[@]}" \
            --append-system-prompt "$note" --output-format json --disable-slash-commands \
            --strict-mcp-config --tools "$tools" >"$rung_log" 2>&1 </dev/null
        fi
        agent_status=$?
        cat "$rung_log" >>ralph.log
        if [ "$rung" = codex ]; then
          record_attempt "$row_id" "$rung" "$codex_model" "$codex_effort" "$agent_status" "$rung_log" || exit 2
        else
          record_attempt "$row_id" "$rung" provider-default provider-default "$agent_status" "$rung_log" || exit 2
        fi
        if rung_limited "$rung" "$agent_status" "$rung_log"; then
          limited_logs+=("$rung_log")
          continue
        fi
        i=$((i + 1))
        progress=no
        if [ "$(commit_count)" -gt "$before" ]; then
          progress=yes
        fi
        local label="$rung"
        if [ "$rung" = codex ]; then
          label=fallback
        fi
        record_turn "$i" "$row_id" "$label" "$agent_status" "$progress" "$rung_log"
        finish_row "$row_id" "$progress" || exit 2
        sleep "$pause"
        continue 2
      done
      secs="$(reset_secs "${limited_logs[@]}")" || exit 2
      if [ "$secs" -gt "$max_sleep" ]; then
        secs="$max_sleep"
      fi
      log "usage limit hit; sleeping ${secs}s; this turn does not count; next retry $(date -u -d "+${secs} seconds" +%FT%TZ)"
      bounded_backoff "$secs"
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
    finish_row "$row_id" "$progress" || exit 2
    sleep "$pause"
  done
  log "loop finished after $i turn(s)"
}

main "$@"
exit $?
