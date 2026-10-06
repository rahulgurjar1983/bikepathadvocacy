#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
version="8.30.1"
sha256="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
dest="$root/.tools/bin"
bin="$dest/gitleaks"

if [ -x "$bin" ] && [ "$("$bin" version 2>/dev/null)" = "$version" ]; then
  echo "gitleaks $version ready at $bin"
  exit 0
fi
if [ "$(uname -s)-$(uname -m)" != "Linux-x86_64" ]; then
  echo "install-gitleaks: only Linux x86_64 is pinned; install gitleaks $version and set GITLEAKS_BIN" >&2
  exit 2
fi
for tool in curl sha256sum tar install; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "install-gitleaks: $tool is required" >&2
    exit 2
  fi
done

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
url="https://github.com/gitleaks/gitleaks/releases/download/v${version}/gitleaks_${version}_linux_x64.tar.gz"
curl -fsSL --retry 3 --retry-delay 2 -o "$tmp/gitleaks.tgz" "$url"
echo "$sha256  $tmp/gitleaks.tgz" | sha256sum -c - >/dev/null
tar -xzf "$tmp/gitleaks.tgz" -C "$tmp" gitleaks
mkdir -p "$dest"
install -m 0755 "$tmp/gitleaks" "$bin"
echo "gitleaks $("$bin" version) installed at $bin"
