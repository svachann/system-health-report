#!/usr/bin/env python3
"""
System Health Report
────────────────────
Daily diagnostics: CPU, memory, disk, temps, battery, network, updates,
top processes, and cross-references with existing data pipelines.

Category: os_tweaking
Usage:    python3 ~/.hermes/scripts/system-health-report.py
"""

import datetime
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

# ── Config ──────────────────────────────────────────────────────────────
DATA_DIR = Path.home() / ".hermes" / "data"
SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"
STATE_FILE = SCRIPTS_DIR / "daily-build-state.json"

# ── Helpers ─────────────────────────────────────────────────────────────

def run(cmd, timeout=10):
    """Run a shell command, return (stdout, stderr) or (None, None)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip(), r.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
        return None, None


def fmt_bytes(n):
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PiB"


def fmt_temp(celsius):
    if celsius is None:
        return "N/A"
    emoji = "🟢" if celsius < 60 else ("🟡" if celsius < 80 else "🔴")
    return f"{emoji} {celsius:.0f}°C"


def box(title, lines, width=56):
    """Wrap content in a box."""
    out = [f"╔{'═' * (width - 2)}╗"]
    out.append(f"║  {title:<{width - 4}}║")
    out.append(f"╠{'═' * (width - 2)}╣")
    for line in lines:
        out.append(f"║  {line:<{width - 4}}║")
    out.append(f"╚{'═' * (width - 2)}╝")
    return out


SAVED_DATA = {}  # populated by sections for JSON export


def save_data():
    """Write structured data for skill queries + archive dated copy."""
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.datetime.now()
    SAVED_DATA["fetched_at"] = now.isoformat()
    SAVED_DATA["fetched_at_epoch"] = now.timestamp()

    # Main file (latest)
    path = DATA_DIR / "system-health.json"
    with open(path, "w") as f:
        json.dump(SAVED_DATA, f, indent=2)

    # Archive dated copy for trending
    archive_dir = DATA_DIR / "system-health"
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = archive_dir / f"{now.strftime('%Y-%m-%d')}.json"
    # Only overwrite if today's archive doesn't exist yet (cron runs first, on-demand keeps latest)
    if not archive_path.exists():
        with open(archive_path, "w") as f:
            json.dump(SAVED_DATA, f, indent=2)
    else:
        # For on-demand runs, overwrite today's archive with latest data
        with open(archive_path, "w") as f:
            json.dump(SAVED_DATA, f, indent=2)


def collect(key, data):
    """Collect data for JSON export."""
    if data is not None:
        SAVED_DATA[key] = data


# ── Section functions ───────────────────────────────────────────────────

def section_cpu():
    if not psutil:
        return box("CPU", ["⚠️  psutil not installed"])
    now = datetime.datetime.now()
    boot_ts = datetime.datetime.fromtimestamp(psutil.boot_time())
    uptime = now - boot_ts
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    mins = remainder // 60
    uptime_str = f"{days}d {hours}h {mins}m" if days else f"{hours}h {mins}m"

    load1, load5, load15 = psutil.getloadavg()
    cpu_pct = psutil.cpu_percent(interval=0.5)
    cpu_count = psutil.cpu_count()
    cpu_count_logical = psutil.cpu_count(logical=True)
    per_core = psutil.cpu_percent(interval=0.3, percpu=True)

    lines = [
        f"Uptime:    {uptime_str}  (boot: {boot_ts.strftime('%b %d %H:%M')})",
        f"Load avg:  {load1:.2f} / {load5:.2f} / {load15:.2f}  (1/5/15 min)",
        f"CPU cores: {cpu_count} physical / {cpu_count_logical} logical",
        f"Total:     {cpu_pct:.0f}%",
        f"Per-core:  {' '.join(f'{c:.0f}%' for c in per_core)}",
    ]

    # Top CPU processes
    procs = sorted(psutil.process_iter(["pid", "name", "cpu_percent"]),
                   key=lambda p: p.info.get("cpu_percent") or 0, reverse=True)[:5]
    if procs:
        lines.append("")
        lines.append("Top CPU consumers:")
        for p in procs:
            pid = p.info["pid"]
            name = p.info["name"] or "?"
            cpu = p.info.get("cpu_percent", 0)
            lines.append(f"  {pid:>6}  {cpu:>5.1f}%  {name[:40]}")

    collect("cpu", {
        "load_1m": load1, "load_5m": load5, "load_15m": load15,
        "percent_total": cpu_pct,
        "cores_physical": cpu_count, "cores_logical": cpu_count_logical,
        "per_core": per_core,
        "top_processes": [
            {"pid": p.info["pid"], "name": p.info["name"] or "?",
             "cpu_percent": p.info.get("cpu_percent") or 0}
            for p in procs
        ] if procs else []
    })
    return box("🖥  CPU & UPTIME", lines)


def section_memory():
    if not psutil:
        return box("Memory", ["⚠️  psutil not installed"])
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    lines = [
        f"Physical:  {fmt_bytes(mem.used)} / {fmt_bytes(mem.total)}"
        f"  ({mem.percent:.0f}%)  —  available: {fmt_bytes(mem.available)}",
        f"Swap:      {fmt_bytes(swap.used)} / {fmt_bytes(swap.total)}"
        f"  ({swap.percent:.0f}%)",
    ]
    collect("memory", {
        "total_bytes": mem.total, "used_bytes": mem.used,
        "available_bytes": mem.available, "percent": mem.percent,
        "swap_total_bytes": swap.total, "swap_used_bytes": swap.used,
        "swap_percent": swap.percent,
    })
    return box("🧠  MEMORY", lines)


def section_disk():
    if not psutil:
        return box("Disk", ["⚠️  psutil not installed"])

    seen_devices = set()
    lines = []
    for part in psutil.disk_partitions():
        if part.fstype in ("proc", "sysfs", "devtmpfs", "devpts",
                           "tmpfs", "fusectl", "cgroup2", "pstore",
                           "securityfs", "debugfs", "hugetlbfs", "configfs",
                           "bpf", "autofs", "mqueue", "efivarfs"):
            continue
        if part.device in seen_devices:
            continue
        seen_devices.add(part.device)
        try:
            usage = psutil.disk_usage(part.mountpoint)
            bar_len = 16
            filled = int(usage.percent / 100 * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            lines.append(
                f"{part.device:<18} {fmt_bytes(usage.used):>9}"
                f" / {fmt_bytes(usage.total):>9}  {bar}  {usage.percent:.0f}%"
            )
        except PermissionError:
            continue
    collect("disks", [
        {"device": part.device, "mount": part.mountpoint,
         "used_bytes": psutil.disk_usage(part.mountpoint).used,
         "total_bytes": psutil.disk_usage(part.mountpoint).total,
         "percent": psutil.disk_usage(part.mountpoint).percent}
        for part in psutil.disk_partitions()
        if part.fstype not in ("proc", "sysfs", "devtmpfs", "devpts",
                               "tmpfs", "fusectl", "cgroup2", "pstore",
                               "securityfs", "debugfs", "hugetlbfs", "configfs",
                               "bpf", "autofs", "mqueue", "efivarfs")
    ])
    return box("💾  DISK USAGE", lines)


def section_temperatures():
    """Read temperatures from sensors CLI (lm-sensors)."""
    out, _ = run(["sensors", "-u"])
    if not out:
        return box("🌡  TEMPERATURES", ["No sensor data (install lm-sensors)"])

    lines = []
    current_chip = None
    for line in out.splitlines():
        if "Adapter:" in line or line.strip() == "":
            continue
        if not line.startswith(" "):  # chip name
            current_chip = line.strip()
        if "temp1_input" in line or "temp2_input" in line:
            try:
                value = float(line.split(":")[1].strip())
                label = current_chip or "sensor"
                emoji = "🟢" if value < 50 else ("🟡" if value < 70 else ("🔴" if value < 90 else "🔥"))
                lines.append(f"  {emoji} {label:<30}  {value:.1f}°C")
            except ValueError:
                pass
            if current_chip:
                current_chip = None  # don't repeat

    if not lines:
        # Try flat parse
        out2, _ = run(["sensors"])
        if out2:
            lines = []
            for l in out2.splitlines():
                if "°C" in l or "+" in l:
                    lines.append(f"  {l.strip()[:60]}")

    if not lines:
        lines = ["No temperature data available"]

    # Parse structured temps for JSON
    temp_data = []
    for l in lines:
        temp_data.append(l.strip())
    collect("temperatures", temp_data)

    return box("🌡  TEMPERATURES", lines)


def section_battery():
    """Get battery status via upower."""
    out, _ = run(["upower", "-e"])
    if not out:
        return None  # No battery (desktop)

    bat_path = None
    for line in out.splitlines():
        if "BAT" in line:
            bat_path = line.strip()
            break
    if not bat_path:
        return None

    info, _ = run(["upower", "-i", bat_path])
    if not info:
        return None

    lines = []
    data = {}
    for line in info.splitlines():
        if ":" in line:
            parts = line.split(":", 1)
            data[parts[0].strip()] = parts[1].strip()

    percentage = data.get("percentage", "?")
    state = data.get("state", "?")
    time_to = data.get("time to empty", "") or data.get("time to full", "")
    model = data.get("model", "") or data.get("Model", "")

    icon = "🔋" if state == "fully-charged" else ("⚡" if state == "charging" else "🔋")
    pct_str = percentage
    try:
        pct_val = float(percentage.replace("%", ""))
        pct_str = f"{percentage} {'🟢' if pct_val > 60 else ('🟡' if pct_val > 20 else '🔴')}"
    except ValueError:
        pass

    lines.append(f"  {icon} Battery: {pct_str}")
    lines.append(f"  State:   {state}")
    if model:
        lines.append(f"  Model:   {model}")
    if time_to:
        lines.append(f"  Time:    {time_to}")

    return box("🔋  BATTERY", lines)


def section_network():
    if not psutil:
        return None
    lines = []
    if_addrs = psutil.net_if_addrs()
    io = psutil.net_io_counters()
    # Show non-loopback interfaces
    for name, addrs in if_addrs.items():
        if name == "lo":
            continue
        ips = [a.address for a in addrs if a.family == 2]  # AF_INET
        if ips:
            lines.append(f"  {name:<12} {'  '.join(ips)}")

    lines.append(f"  Total RX: {fmt_bytes(io.bytes_recv):>8}  |  Total TX: {fmt_bytes(io.bytes_sent):>8}")

    # Connection counts
    try:
        conns = psutil.net_connections()
        states = Counter(c.status for c in conns)
        lines.append(f"  Connections: {sum(states.values())} total"
                     f"  ({states.get('ESTABLISHED',0)} ESTABLISHED,"
                     f" {states.get('LISTEN',0)} LISTEN)")
    except (psutil.AccessDenied, PermissionError):
        lines.append(f"  Connections: (need root for full info)")

    return box("🌐  NETWORK", lines)


def section_updates():
    """Check Arch Linux package updates."""
    out, err = run(["checkupdates"], timeout=30)
    if out is None:
        return None
    if not out:
        return box("📦  PACKAGE UPDATES", ["  ✅ System is up to date (no pending updates)"])

    count = len(out.splitlines())
    lines = [f"  📦 {count} package{'s' if count != 1 else ''} can be updated:"]
    # Show first 15
    pkgs = out.splitlines()[:15]
    for p in pkgs:
        lines.append(f"     {p}")
    if count > 15:
        lines.append(f"     ... and {count - 15} more")
    lines.append("")
    lines.append("  💡 Run: sudo pacman -Syu")
    return box("📦  PACKAGE UPDATES", lines)


def section_top_processes():
    if not psutil:
        return None
    lines = []
    procs = list(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info"]))
    by_cpu = sorted(procs, key=lambda p: p.info.get("cpu_percent") or 0, reverse=True)[:5]
    by_mem = sorted(procs, key=lambda p: p.info.get("memory_percent") or 0, reverse=True)[:5]

    lines.append("  🔥 Top 5 by CPU:")
    lines.append(f"  {'PID':>6} {'CPU%':>5} {'MEM%':>5}  {'Name':<30}")
    for p in by_cpu:
        pid = p.info["pid"]
        cpu = p.info.get("cpu_percent", 0)
        mem = p.info.get("memory_percent", 0)
        name = (p.info.get("name") or "?")[:30]
        lines.append(f"  {pid:>6} {cpu:>5.1f} {mem:>5.1f}  {name}")

    lines.append("")
    lines.append("  🧠 Top 5 by Memory:")
    lines.append(f"  {'PID':>6} {'MEM%':>5} {'RSS':>9}  {'Name':<30}")
    for p in by_mem:
        pid = p.info["pid"]
        mem = p.info.get("memory_percent", 0)
        rss = p.info.get("memory_info", None)
        rss_str = fmt_bytes(rss.rss) if rss and rss.rss else "N/A"
        name = (p.info.get("name") or "?")[:30]
        lines.append(f"  {pid:>6} {mem:>5.1f} {rss_str:>9}  {name}")

    return box("📊  TOP PROCESSES", lines)


def section_zsh_history():
    """Show most used commands from zsh history."""
    hist_path = Path.home() / ".zsh_history"
    if not hist_path.exists():
        return None

    cmds = []
    try:
        raw = hist_path.read_text(errors="replace")
        for line in raw.splitlines():
            # zsh history format: : <timestamp>:<n>;<command>
            if ";" in line:
                cmd = line.split(";", 1)[1].strip()
                if cmd:
                    # Get base command
                    base = cmd.split()[0] if cmd.split() else ""
                    cmds.append(base)
    except Exception:
        return None

    if not cmds:
        return None

    top = Counter(cmds).most_common(10)
    lines = [f"  Your top {len(top)} commands (all time):"]
    max_count = top[0][1] if top else 1
    for cmd, count in top:
        bar_len = int(count / max_count * 12)
        bar = "█" * bar_len + "░" * (12 - bar_len)
        lines.append(f"  {cmd:<15} {count:>6}  {bar}")

    # Recent activity
    recent = [c for c in cmds[-200:]]
    if recent:
        recent_top = Counter(recent).most_common(5)
        lines.append("")
        lines.append("  Last 200 commands:")
        for cmd, count in recent_top:
            lines.append(f"    {cmd:<15} {count:>3}x")

    return box("📜  SHELL HISTORY (zsh)", lines)


def section_data_pipelines():
    """Cross-reference existing data pipeline freshness."""
    files = {
        "Anime Season": DATA_DIR / "anime-season.json",
        "Steam Deals": DATA_DIR / "steam-deals.json",
        "Price History": DATA_DIR / "steam-price-history.json",
        "Wishlist": DATA_DIR / "steam-wishlist.json",
    }

    now = datetime.datetime.now()
    lines = []
    total_size = 0
    for label, path in files.items():
        if path.exists():
            mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime)
            age = now - mtime
            size = path.stat().st_size
            total_size += size
            if age.total_seconds() < 3600:
                age_str = f"{int(age.total_seconds() / 60)} min ago"
            elif age.days == 0:
                age_str = f"{int(age.total_seconds() / 3600)} hours ago"
            else:
                age_str = f"{age.days} days ago"
            icon = "🟢" if age.total_seconds() < 86400 else ("🟡" if age.total_seconds() < 172800 else "🔴")
            lines.append(f"  {icon} {label:<20} {age_str:<14} {fmt_bytes(size):>8}")
        else:
            lines.append(f"  ⚪ {label:<20} {'not generated yet':<14}")

    lines.append(f"  {'─' * 44}")
    lines.append(f"  Total data stored:  {fmt_bytes(total_size):>8}")

    # Read state file
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            days_count = len(state.get("days", []))
            lines.append(f"  Daily builds so far:  {days_count}")
            cats = state.get("categories_used", {})
            used = [k for k, v in cats.items() if v > 0]
            lines.append(f"  Categories used:      {', '.join(used)}")
        except (json.JSONDecodeError, KeyError):
            pass

    return box("📡  DATA PIPELINES", lines)


# ── Main ────────────────────────────────────────────────────────────────

def main():
    now = datetime.datetime.now()
    report_date = now.strftime("%A, %b %d, %Y — %H:%M WIB")

    print("╔══════════════════════════════════════════════════════╗")
    print("║        🖥  SYSTEM HEALTH REPORT                      ║")
    print(f"║  {report_date:<47}║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    # ── System info header ──
    hostname = os.uname().nodename
    kernel = os.uname().release
    print(f"  Host:     {hostname}")
    print(f"  Kernel:   {kernel}")
    # Model from /proc
    model, _ = run(["cat", "/proc/cpuinfo"])
    if model:
        for line in model.splitlines():
            if "model name" in line:
                print(f"  Model:    {line.split(':')[1].strip()}")
                break
    if psutil:
        n_users = len(psutil.users())
        print(f"  Users:    {n_users} logged in")
    print()

    # System info for JSON
    collect("hostname", hostname)
    collect("kernel", kernel)
    collect("users_logged_in", n_users)
    uptime_seconds = None
    if psutil:
        uptime_seconds = int(datetime.datetime.now().timestamp() - psutil.boot_time())
    collect("uptime_seconds", uptime_seconds)

    # ── Sections ──
    sections = [
        section_cpu(),
        section_memory(),
        section_disk(),
        section_temperatures(),
        section_battery(),
        section_network(),
        section_updates(),
        section_top_processes(),
        section_zsh_history(),
        section_data_pipelines(),
    ]

    for s in sections:
        if s:
            print("\n".join(s))
            print()

    # ── Footer ──
    print(f"╔{'═' * 56}╗")
    print(f"║  🛠  Generated by system-health-report.py {now.strftime('%H:%M WIB')}")
    print(f"║  📁  {SCRIPTS_DIR / 'system-health-report.py'}")
    print(f"╚{'═' * 56}╝")

    # Save structured data — additional collections from main context
    if psutil:
        # Network
        try:
            io = psutil.net_io_counters()
            if_addrs = psutil.net_if_addrs()
            ifaces = []
            for name, addrs in if_addrs.items():
                if name == "lo":
                    continue
                ips = [a.address for a in addrs if a.family == 2]
                if ips:
                    ifaces.append({"name": name, "ips": ips})
            conns = psutil.net_connections()
            states = {}
            for c in conns:
                states[c.status] = states.get(c.status, 0) + 1
            collect("network", {
                "interfaces": ifaces,
                "total_rx_bytes": io.bytes_recv,
                "total_tx_bytes": io.bytes_sent,
                "connections_total": sum(states.values()),
                "connections_established": states.get("ESTABLISHED", 0),
                "connections_listen": states.get("LISTEN", 0),
            })
        except Exception:
            pass

        # Top processes (re-collect for full data in main scope)
        try:
            procs = list(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "memory_info"]))
            by_cpu = sorted(procs, key=lambda p: p.info.get("cpu_percent") or 0, reverse=True)[:5]
            by_mem = sorted(procs, key=lambda p: p.info.get("memory_percent") or 0, reverse=True)[:5]
            collect("top_processes", {
                "by_cpu": [{"pid": p.info["pid"], "name": p.info["name"] or "?",
                            "cpu_percent": p.info.get("cpu_percent") or 0}
                           for p in by_cpu],
                "by_memory": [{"pid": p.info["pid"], "name": p.info["name"] or "?",
                               "memory_percent": p.info.get("memory_percent") or 0,
                               "rss_bytes": (p.info["memory_info"].rss if p.info.get("memory_info") and p.info["memory_info"].rss else 0)}
                              for p in by_mem],
            })
        except Exception:
            pass

    # Battery
    try:
        bat_path = None
        out, _ = run(["upower", "-e"])
        if out:
            for line in out.splitlines():
                if "BAT" in line:
                    bat_path = line.strip()
                    break
        if bat_path:
            info, _ = run(["upower", "-i", bat_path])
            if info:
                bdata = {}
                for line in info.splitlines():
                    if ":" in line:
                        parts = line.split(":", 1)
                        bdata[parts[0].strip()] = parts[1].strip()
                collect("battery", {
                    "present": True,
                    "percentage": bdata.get("percentage"),
                    "state": bdata.get("state"),
                    "model": bdata.get("model") or bdata.get("Model"),
                    "time_to_empty": bdata.get("time to empty"),
                    "time_to_full": bdata.get("time to full"),
                })
        else:
            collect("battery", {"present": False})
    except Exception:
        collect("battery", {"present": False, "error": str(Exception)})

    # Package updates
    try:
        out, _ = run(["checkupdates"], timeout=30)
        if out is not None and out:
            pkgs = out.splitlines()
            collect("updates", {
                "pending_count": len(pkgs),
                "packages": [p.strip().split(" -> ")[0] for p in pkgs[:20]],
            })
        else:
            collect("updates", {"pending_count": 0, "packages": []})
    except Exception:
        pass

    # Shell history
    try:
        hist_path = Path.home() / ".zsh_history"
        if hist_path.exists():
            raw = hist_path.read_text(errors="replace")
            cmds = []
            for line in raw.splitlines():
                if ";" in line:
                    cmd = line.split(";", 1)[1].strip()
                    if cmd and cmd.split():
                        cmds.append(cmd.split()[0])
            from collections import Counter
            top = Counter(cmds).most_common(10)
            recent = Counter(c for c in cmds[-200:]).most_common(5)
            collect("shell_history", {
                "total_unique_commands": len(set(cmds)),
                "total_commands": len(cmds),
                "top_10": [{"command": c, "count": n} for c, n in top],
                "last_200_top": [{"command": c, "count": n} for c, n in recent],
            })
    except Exception:
        pass

    # Data pipelines freshness
    try:
        files_info = {
            "anime_season_json": DATA_DIR / "anime-season.json",
            "steam_deals_json": DATA_DIR / "steam-deals.json",
            "system_health_json": DATA_DIR / "system-health.json",
        }
        pipelines = {}
        for label, path in files_info.items():
            if path.exists():
                age = (datetime.datetime.now() - datetime.datetime.fromtimestamp(path.stat().st_mtime)).total_seconds()
                pipelines[label] = {"exists": True, "age_seconds": int(age), "size_bytes": path.stat().st_size}
            else:
                pipelines[label] = {"exists": False}
        collect("data_pipelines", pipelines)
    except Exception:
        pass

    save_data()
    print(file=sys.stderr)
    print(f"💾 Data saved to {DATA_DIR / 'system-health.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
