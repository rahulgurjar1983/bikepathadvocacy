#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
usage="usage: release.sh <tag> | --plan | --build <region file> <folder>"
mode=release
case "${1:-}" in
  --plan) mode=plan ;;
  --build)
    mode=build
    build_region="${2:?$usage}"
    build_dir="${3:?$usage}"
    ;;
  *) tag="${1:?$usage}" ;;
esac
for tool in gh tar gzip sha256sum git python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "release: $tool is required" >&2
    exit 2
  fi
done
read -r -a bikeplan <<<"${BIKEPLAN:-uv run --frozen bikeplan}"
read -r -a pytest <<<"${PYTEST:-uv run --frozen pytest}"
commit="$(git rev-parse HEAD)"
work="$(mktemp -d)"
if [ -n "${RELEASE_OUT:-}" ]; then
  out="$RELEASE_OUT"
  mkdir -p "$out"
  trap 'rm -rf "$work"' EXIT
else
  out="$(mktemp -d)"
  trap 'rm -rf "$out" "$work"' EXIT
fi
shared=(src profiles pyproject.toml uv.lock VOICE.md specs/13-public-report.md)

field() {
  sed -n "s/^$1: *//p" "$2" | head -n 1
}

snapshot_date() {
  sed -n "s/^ *osm_date: *[\"']\{0,1\}\([0-9-]*\)T.*/\1/p" "$1" | head -n 1
}

record_field() {
  python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$1" "$2"
}

unchanged() {
  git rev-parse --verify -q HEAD^ >/dev/null && [ -z "$(git diff --name-only HEAD^ HEAD -- "$@")" ]
}

changed=1
if unchanged src regions profiles snapshots routes pyproject.toml uv.lock VOICE.md specs/13-public-report.md; then
  changed=0
fi

last=""
find_last() {
  git rev-parse --verify -q HEAD^ >/dev/null || return 0
  local parent prior_tags prior_tag status
  parent="$(git rev-parse HEAD^)"
  prior_tags="$(gh release list --limit 100 --json tagName --jq '.[].tagName | select(startswith("v"))')"
  while read -r prior_tag; do
    [ -n "$prior_tag" ] || continue
    if gh release download "$prior_tag" --pattern index.html --dir "$work/index-$prior_tag" >&2 2>"$work/index-error"; then
      :
    else
      status=$?
      if [ "$(cat "$work/index-error")" = "no assets match the file pattern" ]; then
        echo "release: $prior_tag has no index; skipping it"
        continue
      fi
      cat "$work/index-error" >&2
      exit "$status"
    fi
    if grep -q "$parent" "$work/index-$prior_tag/index.html"; then
      last="$prior_tag"
      break
    fi
  done <<<"$prior_tags"
  if [ -n "$last" ]; then
    gh release download "$last" --dir "$work/last" >&2
  fi
}

needs_build() {
  local region="$1" rid
  rid="$(field id "$region")"
  ! { unchanged "${shared[@]}" && unchanged "$region" "snapshots/$rid" && [ -n "$last" ] &&
    [ -f "$work/last/$rid-report.html" ] && [ -f "$work/last/$rid.tar.gz" ]; }
}

measure() {
  local record="$1" ident="$2"
  shift 2
  python3 - "$record" "$ident" "${RELEASE_MAX_SECS:-3600}" "${RELEASE_MAX_MB:-14336}" "$@" <<'PY'
import json
import os
import resource
import signal
import subprocess
import sys
import time

record, ident, limit, memory = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
start = time.monotonic()
child = subprocess.Popen(sys.argv[5:], start_new_session=True, stdin=subprocess.DEVNULL)
try:
    code = child.wait(timeout=limit)
    status = "built" if code == 0 else f"exit {code}"
except subprocess.TimeoutExpired:
    os.killpg(child.pid, signal.SIGKILL)
    child.wait()
    status = "over time"
seconds = round(time.monotonic() - start, 1)
peak = round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, 1)
if status == "built" and peak > memory:
    status = "over memory"
with open(record, "w") as handle:
    json.dump({"region": ident, "seconds": seconds, "peak_mb": peak, "status": status}, handle)
    handle.write("\n")
print(f"release: {ident} {status} in {seconds} s, peak {peak} MB", file=sys.stderr)
sys.exit(0 if status == "built" else 1)
PY
}

published() {
  [ -f "snapshots/$(field id "$1")/$(snapshot_date "$1")/manifest.json" ]
}

pull() {
  local region="$1"
  local rid date manifest
  rid="$(field id "$region")"
  date="$(snapshot_date "$region")"
  manifest="snapshots/$rid/$date/manifest.json"
  if [ ! -f "data/cache/$rid/$date/manifest.json" ]; then
    "${bikeplan[@]}" snapshot pull "$manifest" >&2
  fi
}

if [ "$mode" = plan ]; then
  if unchanged "${shared[@]}"; then
    find_last >&2
  fi
  planned=()
  for region in regions/*.yaml; do
    published "$region" || continue
    needs_build "$region" && planned+=("$region")
  done
  python3 -c 'import json, sys; print(json.dumps(sys.argv[1:]))' "${planned[@]}"
  exit 0
fi

if [ "$mode" = build ]; then
  rid="$(field id "$build_region")"
  date="$(snapshot_date "$build_region")"
  mkdir -p "$build_dir"
  pull "$build_region"
  measure "$build_dir/report-$rid.json" "$rid" "${bikeplan[@]}" report "$build_region" \
    --snapshot "data/cache/$rid/$date" --out "$build_dir/report-$rid"
  (cd "$build_dir/report-$rid" && sha256sum --check --strict SHA256SUMS)
  exit 0
fi

if [ "$changed" = 0 ] || [ -n "${RELEASE_BUILT:-}" ]; then
  find_last
fi

rows=""
count=0
failed=0

check_copied() {
  local name="$1"
  if ! grep -q "  $name\$" "$work/last/SHA256SUMS"; then
    return 1
  fi
  (cd "$work/last" && grep "  $name\$" SHA256SUMS | sha256sum --check --strict -)
}

publish() {
  local kind="$1" id="$2" region="$3" snapshot="$4" folder="$5" html="$6" archive="$7" record="$8"
  cp "$folder/report.html" "$out/$html"
  tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$folder" . | gzip -n >"$out/$archive"
  rows+="<tr><td>$kind</td><td><a href=\"$html\">$id</a></td><td>$region</td><td>$snapshot</td><td>$commit</td><td>built</td><td>$(record_field "$record" seconds)</td><td>$(record_field "$record" peak_mb)</td></tr>"$'\n'
  count=$((count + 1))
}

copy_last() {
  local kind="$1" id="$2" rid="$3" date="$4" html="$5" archive="$6"
  check_copied "$html"
  check_copied "$archive"
  cp "$work/last/$html" "$work/last/$archive" "$out/"
  rows+="<tr><td>$kind</td><td><a href=\"$html\">$id</a></td><td>$rid</td><td>$date</td><td>$commit</td><td>copied from release $last</td><td></td><td></td></tr>"$'\n'
  count=$((count + 1))
}

fail_row() {
  local kind="$1" id="$2" rid="$3" date="$4" why="$5" seconds="${6:-}" peak="${7:-}"
  echo "release: $id failed: $why" >&2
  rows+="<tr><td>$kind</td><td>$id</td><td>$rid</td><td>$date</td><td>$commit</td><td>failed: $why</td><td>$seconds</td><td>$peak</td></tr>"$'\n'
  failed=$((failed + 1))
}

assemble() {
  local id="$1" region="$2" html="$3" archive="$4"
  local rid date record status
  rid="$(field id "$region")"
  date="$(snapshot_date "$region")"
  record="$RELEASE_BUILT/report-$rid.json"
  if [ -f "$record" ]; then
    status="$(record_field "$record" status)"
    if [ "$status" != built ]; then
      fail_row report "$id" "$rid" "$date" "$status" "$(record_field "$record" seconds)" "$(record_field "$record" peak_mb)"
      return
    fi
    (cd "$RELEASE_BUILT/report-$rid" && sha256sum --check --strict SHA256SUMS)
    publish report "$id" "$rid" "$date" "$RELEASE_BUILT/report-$rid" "$html" "$archive" "$record"
  elif ! needs_build "$region"; then
    copy_last report "$id" "$rid" "$date" "$html" "$archive"
  else
    fail_row report "$id" "$rid" "$date" "no build record"
  fi
}

build() {
  local kind="$1" id="$2" region="$3" html="$4" archive="$5"
  shift 5
  local rid date
  rid="$(field id "$region")"
  date="$(snapshot_date "$region")"
  if [ -n "$last" ] && [ "$changed" = 0 ] && [ -f "$work/last/$html" ] && [ -f "$work/last/$archive" ]; then
    copy_last "$kind" "$id" "$rid" "$date" "$html" "$archive"
    return
  fi
  if [ -n "${RELEASE_BUILT:-}" ] && [ "$kind" = report ]; then
    assemble "$id" "$region" "$html" "$archive"
    return
  fi
  local folder="$work/$kind-$id"
  measure "$work/$kind-$id.json" "$id" "${bikeplan[@]}" "$kind" "$@" --snapshot "data/cache/$rid/$date" --out "$folder"
  (cd "$folder" && sha256sum --check --strict SHA256SUMS)
  publish "$kind" "$id" "$rid" "$date" "$folder" "$html" "$archive" "$work/$kind-$id.json"
}

for region in regions/*.yaml; do
  published "$region" || continue
  [ -n "${RELEASE_BUILT:-}" ] || pull "$region"
  id="$(field id "$region")"
  build report "$id" "$region" "$id-report.html" "$id.tar.gz" "$region"
done

for review in routes/*/review.yaml; do
  [ -f "$review" ] || continue
  grep -q '^public: *true *$' "$review" || continue
  folder="$(dirname "$review")"
  references=()
  for key in region route claims reply; do
    value="$(field "$key" "$review")"
    [ -z "$value" ] || references+=("$folder/$value")
  done
  if python3 - "$review" "${references[@]}" <<'PY'
import sys
from pathlib import Path

try:
    root = Path.cwd().resolve()
    private = (root / "data/private").resolve()
    paths = [Path(path).resolve() for path in sys.argv[1:]]
    if any(not path.is_relative_to(root) or path.is_relative_to(private) for path in paths):
        raise SystemExit(3)
    if any(not path.is_file() for path in paths):
        raise ValueError("public review input is missing or is not a file")
except (OSError, ValueError) as error:
    print(f"publicreview: {error}", file=sys.stderr)
    raise SystemExit(1)
PY
  then
    :
  else
    status=$?
    if [ "$status" = 3 ]; then
      echo "release: private review excluded"
      continue
    fi
    exit "$status"
  fi
  id="$(basename "$folder")"
  region="$folder/$(field region "$review")"
  if ! published "$region"; then
    echo "release: no snapshot manifest for review $id" >&2
    exit 2
  fi
  pull "$region"
  build review "$id" "$region" "$id-review.html" "$id.tar.gz" "$folder/$(field route "$review")" --claims "$folder/$(field claims "$review")" --region "$region"
done

if [ "$count" = 0 ]; then
  echo "release: no report to build" >&2
  exit 2
fi

tests_ok=1
if ! "${pytest[@]}" -q --junitxml="$work/junit.xml" >"$work/pytest.log" 2>&1; then
  tests_ok=0
  tail -n 40 "$work/pytest.log" >&2
fi
checks_ok=1
"${bikeplan[@]}" checks "$work/junit.xml" --root . --out "$out/checks.html" --release "$out" || checks_ok=0
if [ "$tests_ok" = 0 ] || [ "$checks_ok" = 0 ]; then
  echo "release: a check failed, so nothing is uploaded" >&2
  exit 1
fi

tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - artifacts | gzip -n >"$out/artifacts.tar.gz"
{
  echo "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Bike path reports</title></head><body><h1>Bike path reports</h1><table><tr><th>Kind</th><th>Report</th><th>Region</th><th>Snapshot</th><th>Commit</th><th>Source</th><th>Build seconds</th><th>Peak MB</th></tr>"
  printf '%s' "$rows"
  echo "</table><p><a href=\"checks.html\">checks.html</a></p><p><a href=\"artifacts.tar.gz\">artifacts.tar.gz</a></p></body></html>"
} >"$out/index.html"
(cd "$out" && sha256sum -- $(ls | grep -vx SHA256SUMS) >SHA256SUMS && sha256sum --check --strict SHA256SUMS)
files=("$out"/*)
if ! gh release view "$tag" >/dev/null 2>&1; then
  gh release create "$tag" --title "$tag" --notes "Bike path reports built from main"
fi
gh release upload "$tag" "${files[@]}" --clobber
echo "release: uploaded ${#files[@]} files to $tag"
