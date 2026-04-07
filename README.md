# Claude Usage Widget

A floating desktop widget for Windows that shows your Claude.ai plan usage limits in real time.

## Features

- Shows current session usage (5-hour window) and weekly usage
- Colour-coded progress bars (green → blue → red as usage increases)
- Auto-refreshes every 2 minutes
- Draggable, always-on-top floating window
- Manual refresh button

## Requirements

- Python 3.9+
- [`curl-cffi`](https://github.com/yifeikong/curl_cffi) (handles Cloudflare bot protection)

## Setup

### 1. Create a venv and install dependency

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install curl-cffi
```

> **Behind a corporate proxy?** Set `HTTPS_PROXY` before installing so pip can reach PyPI:
>
> ```powershell
> $env:HTTPS_PROXY="http://<your-proxy-address>:<port>"; .venv\Scripts\pip.exe install curl-cffi
> ```
>
> The widget itself auto-detects your Windows system proxy at runtime — no extra configuration needed.

### 2. Get your session cookie

1. Open [claude.ai](https://claude.ai) in Chrome or Edge
2. Press **F12** → **Network** tab → refresh the page (**F5**)
3. Click any request to `claude.ai`
4. In the **Headers** panel, find `Cookie:` under Request Headers
5. Copy the **entire** value (it is very long)

### 3. Run the widget

```powershell
.venv\Scripts\python.exe widget.py
```

Paste your cookie when prompted. It is saved to `config.txt` so you only need to do this once.

### Optional: VS Code keyboard shortcut

A VS Code task is included. To bind it to a key, add this to your `keybindings.json` (**Ctrl+Shift+P** → *Open Keyboard Shortcuts (JSON)*):

```json
{
  "key": "ctrl+alt+w",
  "command": "workbench.action.tasks.runTask",
  "args": "Launch Claude Usage Widget"
}
```

Or double-click `launch_widget.bat` to launch without VS Code.

## Cookie expiry

The session cookie expires periodically (every few weeks). When the widget shows **"Session expired"**, repeat step 2 above, delete `config.txt`, and re-run.

## Security

`config.txt` contains your session cookie and is excluded from git via `.gitignore`. Do not share or commit it.
