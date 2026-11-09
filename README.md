# lp-bug-monitor

Scan Launchpad bugs for Ubuntu source packages and generate self-contained,
interactive HTML status dashboards.

## Usage

Scan a single set of packages (packages as arguments or via a packages file):

```sh
./lp-bug-monitor linux-firmware systemd
./lp-bug-monitor -f data/firmware/packages.txt --state-file data/firmware/bugs-state.json -o data/firmware/index.html
```

Useful options: `--full` (force full scan), `--no-scan` / `--report-only`
(regenerate the HTML from the state file), `--dry-run`, `-s noble jammy`
(specific series), `--json PATH` (export bug data as JSON).

## Multiple package sets

`scan-all` scans every package set under a directory. A *set* is any
subdirectory containing a `packages.txt` file (one package per line, `#` for
comments):

```
data/
├── firmware/
│   ├── packages.txt        ← you maintain this
│   ├── bugs-state.json     ← generated
│   └── index.html          ← generated dashboard
├── systemd/
│   └── packages.txt
└── index.html              ← generated landing page linking all dashboards
```

```sh
./lp-bug-monitor scan-all data            # scan all sets (one Launchpad connection)
./lp-bug-monitor scan-all data --no-scan  # regenerate all dashboards from state
```

Each dashboard is titled after its set directory (e.g. `Ubuntu Bug Status —
firmware`). Adding a new dashboard is just a matter of creating a new
subdirectory with a `packages.txt` file.

## Development

```sh
make test   # uv run pytest
make lint   # uv run ruff check && uv run ruff format --check
```

## CI

`.github/workflows/sync.yaml` runs `scan-all` on the `data` branch every
4 hours and commits the generated dashboards, state files, and landing page.
