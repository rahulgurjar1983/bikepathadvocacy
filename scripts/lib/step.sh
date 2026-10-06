step() {
  local name="$*" out start status=0
  if [ "${GATE_VERBOSE:-0}" = 1 ]; then
    echo "== gate: $name"
    "$@" || status=$?
    if [ "$status" -ne 0 ]; then
      echo "FAIL $name (exit $status)"
      exit "$status"
    fi
    return 0
  fi
  out="$(mktemp)"
  start=$SECONDS
  "$@" >"$out" 2>&1 || status=$?
  if [ "$status" -eq 0 ]; then
    echo "ok   $name ($((SECONDS - start))s)"
    rm -f "$out"
    return 0
  fi
  echo "FAIL $name (exit $status); last 60 lines:"
  tail -n 60 "$out"
  rm -f "$out"
  exit "$status"
}
