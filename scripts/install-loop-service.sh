#!/usr/bin/env bash
set -euo pipefail
work="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$work"
work="$(pwd)"
for tool in git systemctl install flock timeout python3; do
  command -v "$tool" >/dev/null
done
timeout --kill-after=10 180 git fetch -q origin
control="$work/.ralph/control"
mkdir -p "$work/.ralph"
systemctl --user stop bikepath-loop.service
if [ -f "$control/.git" ]; then
  if [ -n "$(git -C "$control" status --porcelain)" ]; then
    echo "install-loop: controller has changes; preserve and inspect them" >&2
    exit 1
  fi
  git -C "$control" checkout -q --detach origin/main
else
  git worktree add --detach "$control" origin/main
fi
unit_dir="${RALPH_USER_UNIT_DIR:-$HOME/.config/systemd/user}"
mkdir -p "$unit_dir"
install -m 0644 "$control/deploy/systemd/bikepath-loop.service" "$unit_dir/bikepath-loop.service"
systemctl --user daemon-reload
systemctl --user enable bikepath-loop.service
systemctl --user reset-failed bikepath-loop.service
systemctl --user start bikepath-loop.service
systemctl --user show bikepath-loop.service --property=ActiveState,SubState,MainPID,NRestarts
