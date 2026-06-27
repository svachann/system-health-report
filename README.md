# 🖥️ System Health Report

Daily diagnostics: CPU, memory, disk, temperatures, battery, network, Arch Linux package updates, top processes, zsh shell history analysis, and data pipeline freshness checks.

## Features

- **CPU & uptime** — load averages, per-core utilization, top CPU consumers
- **Memory & swap** — physical memory and swap usage with available capacity
- **Disk usage** — per-mountpoint breakdown with visual usage bars (btrfs-aware)
- **Temperatures** — CPU core, package, NVMe, and other sensors via lm-sensors
- **Battery** — charge percentage, state, model, and time remaining via upower
- **Network** — interface IPs, total RX/TX, active connections
- **Package updates** — pending Arch Linux updates count with package names
- **Top processes** — sorted by CPU and memory with PID and RSS
- **Shell history** — most-used zsh commands (all-time + last 200)
- **Pipeline health** — freshness check on existing data files and daily build stats
- **JSON data output** — structured data saved for historic trending

## Usage

```bash
python3 system-health-report.py
```

Outputs a formatted report to stdout, saves JSON to `~/.hermes/data/system-health.json`, and archives dated copies to `~/.hermes/data/system-health/YYYY-MM-DD.json` for trend analysis.

## Data

The script saves structured JSON for programmatic access:

```json
{
  "fetched_at": "2026-06-27T18:36:00",
  "hostname": "localhost",
  "kernel": "7.0.10-arch1",
  "uptime_seconds": 29128,
  "cpu": {
    "load_1m": 0.98,
    "percent_total": 5.3,
    "cores_physical": 16,
    "top_processes": [
      {"pid": 20598, "name": "haruna", "cpu_percent": 138.4}
    ]
  },
  "memory": {
    "percent": 31.6,
    "total_bytes": 16648982528,
    "available_bytes": 11382517760
  },
  "disks": [
    {"device": "/dev/nvme0n1p2", "mount": "/", "percent": 38}
  ],
  "updates": {
    "pending_count": 150
  },
  "shell_history": {
    "total_unique_commands": 54,
    "top_10": [{"command": "ls", "count": 110}]
  }
}
```

Historic archives accumulate in `~/.hermes/data/system-health/` for trend queries.

## Part of Daily Python Builds

This is Day 3 of a daily series building useful Python tools across anime, JRPGs, trading, OS tweaking, AI agents, Hermes plugins, and Digimon.

[⬆ Back to svachann](https://github.com/svachann)
