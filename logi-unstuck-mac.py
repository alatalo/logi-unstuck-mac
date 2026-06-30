#!/usr/bin/env python3
"""
Logi Unstuck Mac

Problem: Logitech Logi Options / Options+ features can stop working on macOS.
For example, MX Master thumb wheel Spaces switching may stop responding.

One common cause is macOS Secure Input being left enabled by another process.
This tool helps identify the process macOS reports as the Secure Input owner,
kill running owner processes, and trigger a lock/unlock cycle when the session
state appears stale.

Logitech support article:
Logitech Options and Options+ issues when Secure Input is enabled
https://support.logi.com/hc/en-us/articles/360023189334-Logitech-Options-and-Options-issues-when-Secure-Input-is-enabled

Run:
  python3 logi-unstuck-mac.py

Notes:
* Killing a process is not always enough.
* If ioreg still reports a PID after the process exited, try lock/unlock.
* If the session state stays stuck, logout/login or reboot may be needed.

Ville Alatalo 2026 with GPT-5.5 Thinking
https://github.com/alatalo/logi-unstuck-mac
"""

from __future__ import annotations

import argparse
import curses
import os
import re
import signal
import shutil
import subprocess
import time
from dataclasses import dataclass

APP_NAME = "Logi Unstuck Mac"
VERSION = "0.1.0"
SECURE_INPUT_RE = re.compile(r'"kCGSSessionSecureInputPID"=(\d+)')
os.environ.setdefault("ESCDELAY", "25")


@dataclass
class Proc:
    pid: int
    ppid: str = "?"
    user: str = "?"
    stat: str = "?"
    app: str = "?"
    command: str = "?"


def run_text(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return ""


def secure_input_pids() -> list[int]:
    out = run_text(["ioreg", "-l", "-d", "1", "-w", "0"])
    return sorted({int(match) for match in SECURE_INPUT_RE.findall(out)})


def friendly_app_name(command: str) -> str:
    if not command:
        return "?"

    marker = ".app/Contents/MacOS/"
    if marker in command:
        app_path = command.split(marker, 1)[0] + ".app"
        return os.path.basename(app_path)

    executable = command.split(None, 1)[0]
    return os.path.basename(executable)


def process_info(pid: int) -> Proc:
    meta = run_text(["ps", "-p", str(pid), "-o", "pid=,ppid=,user=,stat="]).strip()
    command = run_text(["ps", "-ww", "-p", str(pid), "-o", "command="]).strip()

    if not meta or not command:
        return Proc(
            pid=pid,
            stat="stale",
            app="<exited>",
            command="<PID still in ioreg; no running process>",
        )

    parts = meta.split(None, 3)
    if len(parts) < 4:
        return Proc(pid=pid, command=command)

    pid_s, ppid, user, stat = parts
    return Proc(
        pid=int(pid_s),
        ppid=ppid,
        user=user,
        stat=stat,
        app=friendly_app_name(command),
        command=command,
    )


def get_processes() -> list[Proc]:
    return [process_info(pid) for pid in secure_input_pids()]


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def is_stale(proc: Proc) -> bool:
    return proc.stat == "stale" or proc.app == "<exited>"


def send_signal(pid: int, sig: signal.Signals) -> tuple[bool, str]:
    try:
        os.kill(pid, sig)
        return True, f"sent {sig.name} to PID {pid}"
    except ProcessLookupError:
        return False, f"PID {pid} is no longer running"
    except PermissionError:
        return False, f"permission denied for PID {pid}; try sudo only if you trust the target process"


def truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def addstr_safe(stdscr: curses.window, y: int, x: int, text: str, attr: int = 0) -> None:
    height, width = stdscr.getmaxyx()
    if y < 0 or y >= height or x >= width:
        return
    stdscr.addstr(y, x, truncate(text, width - x - 1), attr)


def draw(stdscr: curses.window, procs: list[Proc], selected: int, message: str) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    running = sum(1 for proc in procs if not is_stale(proc))
    stale = len(procs) - running

    addstr_safe(stdscr, 0, 0, f"{APP_NAME} - macOS Secure Input helper for Logitech Options+", curses.A_BOLD)
    addstr_safe(stdscr, 1, 0, "Up/Down/Enter: select  a: kill all  l: lock screen  r: refresh  q: quit")

    if not procs:
        addstr_safe(stdscr, 4, 0, "No Secure Input processes found.", curses.A_BOLD)
        addstr_safe(stdscr, height - 1, 0, message)
        stdscr.refresh()
        return

    header = f"{'PID':>6} {'PPID':>6} {'USER':<12} {'STATE':<8} APP / COMMAND"
    addstr_safe(stdscr, 3, 0, header, curses.A_UNDERLINE)

    visible_rows = max(1, height - 7)
    top = max(0, min(selected - visible_rows + 1, len(procs) - visible_rows))

    for row, proc in enumerate(procs[top : top + visible_rows], start=4):
        index = top + row - 4
        attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
        state = "stale" if is_stale(proc) else proc.stat
        hint = "  [try lock/unlock]" if is_stale(proc) else ""
        line = f"{proc.pid:>6} {proc.ppid:>6} {proc.user:<12.12} {state:<8.8} {proc.app:<20.20} {proc.command}{hint}"
        addstr_safe(stdscr, row, 0, line, attr)

    addstr_safe(stdscr, height - 2, 0, f"{running} running, {stale} stale")
    addstr_safe(stdscr, height - 1, 0, message)
    stdscr.refresh()


def prompt(stdscr: curses.window, lines: list[str], question: str, choices: str) -> str:
    height, width = stdscr.getmaxyx()
    box_height = min(height - 2, len(lines) + 4)
    box_width = min(width - 4, max([len(question) + 8, *(len(line) for line in lines)], default=40) + 4)
    y0 = max(0, (height - box_height) // 2)
    x0 = max(0, (width - box_width) // 2)

    win = curses.newwin(box_height, box_width, y0, x0)
    win.keypad(True)
    win.box()

    for i, line in enumerate(lines[: box_height - 4], start=1):
        win.addstr(i, 2, truncate(line, box_width - 4))

    win.addstr(box_height - 2, 2, truncate(question, box_width - 4), curses.A_BOLD)
    win.refresh()

    valid = set(choices.lower())
    while True:
        ch = win.getch()
        if ch in (27, ord("q")) and "n" in valid:
            return "n"
        if ch == curses.KEY_RESIZE:
            return ""
        try:
            value = chr(ch).lower()
        except ValueError:
            continue
        if value in valid:
            return value


def inspect_process(stdscr: curses.window, proc: Proc) -> str:
    current = process_info(proc.pid)
    if is_stale(current):
        prompt(
            stdscr,
            [
                f"PID {current.pid} is still reported by ioreg,",
                "but ps says the process no longer exists.",
                "",
                "There is nothing left to kill for this PID.",
                "Use l to lock/unlock, then refresh with r.",
                "If that fails, logout/login or reboot may be needed.",
            ],
            "Press y to continue",
            "y",
        )
        return f"PID {current.pid} is stale; try lock/unlock"

    lines = [
        f"PID:     {current.pid}",
        f"PPID:    {current.ppid}",
        f"User:    {current.user}",
        f"Stat:    {current.stat}",
        f"App:     {current.app}",
        f"Command: {current.command}",
    ]
    answer = prompt(stdscr, lines, "Send TERM to this process? [y/n]", "yn")
    if answer != "y":
        return f"skipped PID {proc.pid}"

    ok, msg = send_signal(proc.pid, signal.SIGTERM)
    if not ok:
        return msg

    time.sleep(1.5)
    if not is_alive(proc.pid):
        return f"PID {proc.pid} exited after TERM"

    answer = prompt(stdscr, [msg, f"PID {proc.pid} is still alive."], "Force kill with KILL? [y/n]", "yn")
    if answer == "y":
        _, msg = send_signal(proc.pid, signal.SIGKILL)
        return msg

    return f"left PID {proc.pid} running"


def kill_running(stdscr: curses.window, procs: list[Proc]) -> str:
    running = [process_info(proc.pid) for proc in procs]
    running = [proc for proc in running if not is_stale(proc)]
    stale_count = len(procs) - len(running)

    if not running:
        return "only stale ioreg PID(s) found; try lock/unlock"

    lines = [f"{proc.pid}  {proc.app}  {proc.command}" for proc in running[:10]]
    if len(running) > 10:
        lines.append(f"...and {len(running) - 10} more")
    if stale_count:
        lines.append(f"Skipping {stale_count} stale PID(s) with no running process.")

    answer = prompt(stdscr, lines, f"Send TERM to {len(running)} running process(es)? [y/n]", "yn")
    if answer != "y":
        return "kill running cancelled"

    for proc in running:
        send_signal(proc.pid, signal.SIGTERM)

    time.sleep(1.5)
    alive = [proc for proc in running if is_alive(proc.pid)]
    if not alive:
        return "all running owner processes exited after TERM"

    answer = prompt(
        stdscr,
        [f"{proc.pid}  {proc.app}" for proc in alive[:10]],
        f"{len(alive)} still alive. Force kill remaining? [y/n]",
        "yn",
    )
    if answer == "y":
        for proc in alive:
            send_signal(proc.pid, signal.SIGKILL)
        return f"sent KILL to {len(alive)} process(es)"

    return f"left {len(alive)} process(es) running"


def lock_screen(stdscr: curses.window) -> str:
    answer = prompt(
        stdscr,
        [
            "This locks the current macOS session.",
            "After unlocking, refresh and check whether Secure Input cleared.",
        ],
        "Lock screen now? [y/n]",
        "yn",
    )
    if answer != "y":
        return "lock screen cancelled"

    methods = [
        (
            "CGSession",
            ["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"],
            True,
        ),
        ("display sleep", ["/usr/bin/pmset", "displaysleepnow"], True),
        (
            "screen saver",
            ["/System/Library/CoreServices/ScreenSaverEngine.app/Contents/MacOS/ScreenSaverEngine"],
            False,
        ),
        (
            "keyboard shortcut",
            [
                "/usr/bin/osascript",
                "-e",
                'tell application "System Events" to keystroke "q" using {control down, command down}',
            ],
            True,
        ),
    ]

    errors = []
    for name, cmd, wait_for_exit in methods:
        executable = cmd[0]
        if executable.startswith("/") and not os.path.exists(executable):
            errors.append(f"{name}: {executable} not found")
            continue
        if not executable.startswith("/") and not shutil.which(executable):
            errors.append(f"{name}: {executable} not found in PATH")
            continue

        try:
            if wait_for_exit:
                completed = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=3)
                if completed.returncode != 0:
                    detail = completed.stderr.strip() or f"exit {completed.returncode}"
                    errors.append(f"{name}: {detail}")
                    continue
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"{name} requested; unlock, then refresh"
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{name}: {exc}")

    return "could not lock screen: " + "; ".join(errors[-2:])


def run_tui(stdscr: curses.window) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    curses.use_default_colors()

    procs = get_processes()
    selected = 0
    message = "ready"

    while True:
        if selected >= len(procs):
            selected = max(0, len(procs) - 1)

        draw(stdscr, procs, selected, message)
        ch = stdscr.getch()

        if ch in (ord("q"), ord("Q"), 27):
            return
        if ch in (ord("r"), ord("R")):
            procs = get_processes()
            message = "refreshed"
        elif ch in (curses.KEY_UP, ord("k")) and procs:
            selected = max(0, selected - 1)
        elif ch in (curses.KEY_DOWN, ord("j")) and procs:
            selected = min(len(procs) - 1, selected + 1)
        elif ch in (ord("a"), ord("A")) and procs:
            message = kill_running(stdscr, procs)
            procs = get_processes()
        elif ch in (ord("l"), ord("L")):
            message = lock_screen(stdscr)
            procs = get_processes()
        elif ch in (curses.KEY_ENTER, 10, 13) and procs:
            message = inspect_process(stdscr, procs[selected])
            procs = get_processes()
        elif ch == curses.KEY_RESIZE:
            message = "resized"


def main() -> None:
    parser = argparse.ArgumentParser(description="macOS Secure Input helper for Logitech Options / Options+ issues.")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    parser.parse_args()
    curses.wrapper(run_tui)


if __name__ == "__main__":
    main()
