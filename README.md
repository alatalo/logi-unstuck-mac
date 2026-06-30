# Logi Unstuck Mac

A small macOS terminal UI helper for Logitech Options / Logi Options+ Secure Input issues.

Sometimes Logitech MX Keys / MX Master features stop working on macOS. One common symptom is the MX Master thumb wheel no longer switching between Spaces or other mapped key shortcuts stop working. Logitech documents a common cause for the issue: some app has enabled macOS Secure Input and it's intefering with the Logitech key shortcut.

Logi Unstuck Mac shows the processes macOS reports as the Secure Input owners and helps you kill the offending ones.

## Killing processes is not always enough

The usual advice is to find the Secure Input owner PID and kill that process. That often works, but not always.

Sometimes macOS continues to report `kCGSSessionSecureInputPID` after the process has already exited. In that case `ioreg` still shows a PID, but `ps` says the process no longer exists so there is nothing left to kill. The session state itself may be stuck.

Recommended action:

1. Quit the app that requested Secure Input, if it's obvious. Many times it's Slack, Firefox, 1Password...
2. Use the Logi Unstuck Mac script to inspect and terminate the running process with Secure Input.
3. If the PID is stale, lock and unlock the Mac either manually or with the script.
4. If still broken, log out and log back in.
5. If still broken, reboot.

## Run

```bash
python3 logi-unstuck-mac.py
```

No external Python packages are required.

## Controls

| Key | Action |
| --- | --- |
| Up/Down or `j`/`k` | Move selection |
| Enter | Inspect selected entry |
| `a` | Kill running owner process(es) |
| `l` | Lock screen |
| `r` | Refresh |
| `q` or Esc | Quit |

## What It Checks

Logi Unstuck Mac reads Secure Input owner PIDs and resolves each PID with:

```bash
ioreg -l -d 1 -w 0 | grep SecureInput
ps -p <pid>
```

If `ioreg` reports a PID but `ps` cannot find it, the entry is stale and lock/unlock is adviced.

## Safety note

LogiUnstuck sends `TERM` first. It only offers `KILL` if the process is still alive.

Be careful when terminating system processes such as `loginwindow`; doing so may log you out or disrupt the current session.

## Background

Logitech support article:

https://support.logi.com/hc/en-us/articles/360023189334-Logitech-Options-and-Options-issues-when-Secure-Input-is-enabled

## License

MIT
