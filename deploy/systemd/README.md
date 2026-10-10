# Loop service

The service keeps its code in `.ralph/control`, a separate Git worktree. Models work in the main folder. An old task branch cannot replace the code of the running service. Git keeps the folders apart; `systemd` owns start, restart and process cleanup.

After the input PR merges, run this from the main work folder:

```bash
bash scripts/install-loop-service.sh
bash scripts/loop-status.sh
```

The install command fetches `origin/main`, stops the old service, sets up its clean code folder, installs the unit and starts it. App files and local stashes are kept. The loop saves unfinished work before its next main sync. If the service code folder has changes, install fails so those changes can be kept.

The status command shows the process state, task row, owning PR, reason and next retry time where known. A heartbeat is the time of its last check. It updates during work and waits. Use the phase and reason to see what the service is doing and what it needs next.

`quota_wait` means both available plans are limited. `waiting_ci` means a PR awaits checks or merge. `blocked` means a stated input or saved-work problem. These waits do not spend a model turn. The service checks for changes each minute.

`STOP` ends the loop. `HOLD` pauses it. Install keeps both files. The installed service retries failed Git or GitHub calls before work. A manual run shows errors and exits. Models stay on Sonnet and Sol within the owner's plans. All CI and release checks still apply.

Sources: [Git guide](https://git-scm.com/docs/git-worktree), [service guide](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml).
