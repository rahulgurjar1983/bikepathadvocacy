# Bike Path Advocacy

`bikeplan` turns open data into a ranked list of bike path projects for any region. Each project says where to build, what to build, what it takes from drivers, and who it links to schools, colleges, aged care, libraries, town centres and stations. The goal is a network safe for a child or a retiree.

Bayside Council in Sydney is the first test region. The method works for any council, state or country. Region facts live in config files, not in code.

## Status

The scaffold is in place: specs, gates, CI and the Ralph loop. The loop builds the tool one row of [`PROGRESS.md`](PROGRESS.md) at a time.

## How it works

1. **Snapshot.** Fetch the input data for a region once, pin it to a date, and record a sha256 for each file.
2. **Network.** Build the street network from OpenStreetMap.
3. **Stress.** Score each street with Level of Traffic Stress (LTS) and flag the ones safe for all ages (AAA).
4. **Width.** Estimate each street's width from the best source on hand, with a confidence label.
5. **Fit.** Try fixes from least to most disruptive until one fits and makes the street AAA.
6. **Access.** Measure how many homes can reach each type of place by a safe route.
7. **Propose.** Rank projects by the access they add per unit of disruption.
8. **Report.** Write a map, a project sheet for each project, and the data behind them.

See [`SPECIFICATION.md`](SPECIFICATION.md) for the full method and [`specs/`](specs) for each part.

## Check the work

```bash
uv sync --frozen
scripts/install-gitleaks.sh
scripts/install-hooks.sh
scripts/gate.sh
```

[`VERIFICATION.md`](VERIFICATION.md) lists a command, the expected result and the proof file for every finished task.

## The build loop

The loop runs as a user service:

```bash
cp deploy/systemd/bikepath-loop.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now bikepath-loop.service
journalctl --user -u bikepath-loop.service -f
```

Each turn reads [`PROMPT.md`](PROMPT.md), takes the top open row, writes failing tests, writes the code, runs the full gate, and opens a PR that merges itself when CI is green. Create a `STOP` file to end the loop, or a `HOLD` file to pause it.

People change only the inputs, on `input/*` branches: specs, rows, gates and the prompt. The loop changes the code.

## Data and credit

Map data © OpenStreetMap contributors (ODbL). Population data © Kontur (CC BY 4.0). NSW data © State of New South Wales (CC BY 4.0). Census data © Australian Bureau of Statistics (CC BY 4.0).
