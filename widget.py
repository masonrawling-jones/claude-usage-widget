"""
Claude Usage Widget — floating desktop window showing plan usage limits.

Setup:
  1. Open claude.ai in Chrome/Edge
  2. Press F12 → Network tab → refresh the page → click any request to claude.ai
  3. Scroll down in the Headers panel to find the 'Cookie:' request header
  4. Copy the ENTIRE cookie string (everything after 'Cookie: ')
  5. Run: python widget.py and paste it when prompted (saved to config.txt)
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
import json
import os
import sys
import urllib.request
from curl_cffi import requests


def _system_proxies() -> dict:
    """Return proxy dict for curl_cffi, reading Windows system proxy if set.

    Windows often registers the proxy with an https:// scheme even for plain
    HTTP proxies. curl_cffi would then attempt TLS to the proxy itself and
    fail. We always rewrite the scheme to http://.
    """
    proxies = urllib.request.getproxies()
    raw = proxies.get("https") or proxies.get("http") or ""
    if not raw:
        return {}
    # Strip whatever scheme Windows gave us and force http://
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    url = "http://" + raw
    return {"https": url, "http": url}


PROXIES = _system_proxies()

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.txt")
REFRESH_INTERVAL = 120  # seconds (2 minutes)

# ── colours ────────────────────────────────────────────────────────────────
BG       = "#faf9f7"
FG       = "#1a1a1a"
FG_MUTED = "#888888"
ACCENT   = "#3b82f6"
BAR_BG   = "#e5e7eb"
BORDER   = "#e5e7eb"
RED      = "#ef4444"
GREEN    = "#22c55e"
FONT     = ("Segoe UI", 9)
FONT_B   = ("Segoe UI", 9, "bold")
FONT_SM  = ("Segoe UI", 8)


def load_session_key():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return f.read().strip()
    return None


def sanitize_cookie(raw: str) -> str:
    """Remove leading/trailing whitespace and any 'Cookie: ' prefix if accidentally included."""
    val = raw.strip()
    if val.lower().startswith("cookie:"):
        val = val[7:].strip()
    return val


def save_session_key(key: str):
    with open(CONFIG_FILE, "w") as f:
        f.write(key.strip())


# ── API helpers ─────────────────────────────────────────────────────────────

def fetch_usage(session_key: str) -> dict:
    """
    Returns a dict like:
      {
        "session_pct": 38,
        "session_resets": "3 hr 39 min",
        "weekly_pct": 15,
        "weekly_resets": "Thu 8:00 AM",
        "raw": { ... }
      }
    Raises on failure.
    """
    # session_key here is the full Cookie header string from the browser
    headers = {
        "Cookie": session_key.strip(),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-GB,en;q=0.9",
        "Referer": "https://claude.ai/",
        "Origin": "https://claude.ai",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

    # 1. Bootstrap to get org UUID
    r = requests.get("https://claude.ai/api/bootstrap", headers=headers, timeout=15, impersonate="chrome120", proxies=PROXIES)
    r.raise_for_status()
    bootstrap = r.json()

    org_id = None
    for account in bootstrap.get("account", {}).get("memberships", []):
        org = account.get("organization", {})
        if org.get("uuid") and org.get("rate_limit_tier") == "default_claude_ai":
            org_id = org["uuid"]
            break
    if not org_id:
        for account in bootstrap.get("account", {}).get("memberships", []):
            org = account.get("organization", {})
            if org.get("uuid"):
                org_id = org["uuid"]
                break

    if not org_id:
        raise ValueError("Could not find organisation UUID in bootstrap response")

    # 2. Fetch usage
    r2 = requests.get(
        f"https://claude.ai/api/organizations/{org_id}/usage",
        headers=headers,
        timeout=15,
        impersonate="chrome120",
        proxies=PROXIES,
    )
    r2.raise_for_status()
    data = r2.json()

    five_hour = data.get("five_hour") or {}
    seven_day = data.get("seven_day") or {}

    return {
        "session_pct": round(five_hour.get("utilization", 0)),
        "session_resets": format_reset(five_hour.get("resets_at", "")),
        "weekly_pct": round(seven_day.get("utilization", 0)),
        "weekly_resets": format_reset(seven_day.get("resets_at", "")),
    }


def format_reset(resets_at: str) -> str:
    """Convert an ISO timestamp into a human label."""
    from datetime import datetime, timezone

    if not resets_at:
        return "unknown"

    # Seconds until reset (integer)
    if isinstance(resets_at, (int, float)):
        secs = int(resets_at)
        h, rem = divmod(secs, 3600)
        m = rem // 60
        return f"Resets in {h} hr {m} min" if h else f"Resets in {m} min"

    # ISO string
    try:
        dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = dt - now
        total_secs = int(delta.total_seconds())
        if total_secs < 0:
            return "Resetting soon"
        h, rem = divmod(total_secs, 3600)
        m = rem // 60
        if h >= 24:
            day_name = dt.strftime("%a")
            t_str = dt.astimezone().strftime("%-I:%M %p") if sys.platform != "win32" else dt.astimezone().strftime("%#I:%M %p")
            return f"Resets {day_name} {t_str}"
        return f"Resets in {h} hr {m} min" if h else f"Resets in {m} min"
    except Exception:
        return str(resets_at)[:20]


# ── Widget UI ────────────────────────────────────────────────────────────────

class UsageBar(tk.Frame):
    def __init__(self, parent, label: str, sublabel: str = "", **kw):
        super().__init__(parent, bg=BG, **kw)

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text=label, font=FONT_B, bg=BG, fg=FG).pack(side="left")
        self.pct_lbl = tk.Label(top, text="—", font=FONT_SM, bg=BG, fg=ACCENT)
        self.pct_lbl.pack(side="right")

        self.sub_lbl = tk.Label(self, text=sublabel, font=FONT_SM, bg=BG, fg=FG_MUTED)
        self.sub_lbl.pack(anchor="w")

        bar_frame = tk.Frame(self, bg=BAR_BG, height=8, bd=0, highlightthickness=0)
        bar_frame.pack(fill="x", pady=(4, 0))
        bar_frame.pack_propagate(False)

        self._bar_frame = bar_frame
        self._fill = tk.Frame(bar_frame, bg=ACCENT, height=8)
        self._fill.place(relx=0, rely=0, relwidth=0, relheight=1)

    def update(self, pct: int, sublabel: str):
        pct = max(0, min(100, pct))
        color = RED if pct >= 90 else (ACCENT if pct >= 50 else GREEN)
        self._fill.config(bg=color)
        self._fill.place(relwidth=pct / 100)
        self.pct_lbl.config(text=f"{pct}% used", fg=color)
        self.sub_lbl.config(text=sublabel)


class ClaudeUsageWidget:
    def __init__(self, session_key: str):
        self.session_key = session_key
        self._data = None
        self._running = True

        self.root = tk.Tk()
        self.root.title("Claude Usage")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)

        # Remove default title bar, add custom drag
        self.root.overrideredirect(True)
        self._build_ui()
        self._position_bottom_right()

        # Start background refresh thread
        t = threading.Thread(target=self._refresh_loop, daemon=True)
        t.start()

        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.mainloop()

    # ── layout ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="both", expand=True)

        self.card = tk.Frame(outer, bg=BG, padx=14, pady=10)
        self.card.pack(fill="both", expand=True)

        # Title row
        title_row = tk.Frame(self.card, bg=BG)
        title_row.pack(fill="x", pady=(0, 8))
        tk.Label(title_row, text="Plan usage limits", font=FONT_B, bg=BG, fg=FG).pack(side="left")

        btn_row = tk.Frame(title_row, bg=BG)
        btn_row.pack(side="right")

        # Refresh button
        self._refresh_btn = tk.Label(btn_row, text="⟳", font=("Segoe UI", 11), bg=BG, fg=FG_MUTED, cursor="hand2")
        self._refresh_btn.pack(side="left", padx=(0, 4))
        self._refresh_btn.bind("<Button-1>", lambda e: self._trigger_refresh())

        # Close button
        close_btn = tk.Label(btn_row, text="✕", font=FONT_SM, bg=BG, fg=FG_MUTED, cursor="hand2")
        close_btn.pack(side="left")
        close_btn.bind("<Button-1>", lambda e: self.quit())

        sep1 = tk.Frame(self.card, bg=BORDER, height=1)
        sep1.pack(fill="x", pady=(0, 10))

        # Session bar
        self.session_bar = UsageBar(self.card, "Current session", "Loading…")
        self.session_bar.pack(fill="x", pady=(0, 12))

        sep2 = tk.Frame(self.card, bg=BORDER, height=1)
        sep2.pack(fill="x", pady=(0, 10))

        # Weekly section header
        tk.Label(self.card, text="Weekly limits", font=FONT_B, bg=BG, fg=FG).pack(anchor="w")
        tk.Label(self.card, text="Learn more about usage limits", font=FONT_SM, bg=BG, fg=ACCENT,
                 cursor="hand2").pack(anchor="w", pady=(0, 8))

        # Weekly bar
        self.weekly_bar = UsageBar(self.card, "All models", "Loading…")
        self.weekly_bar.pack(fill="x")

        sep3 = tk.Frame(self.card, bg=BORDER, height=1)
        sep3.pack(fill="x", pady=(10, 6))

        # Status row
        self.status_lbl = tk.Label(self.card, text="Last updated: —", font=FONT_SM, bg=BG, fg=FG_MUTED)
        self.status_lbl.pack(anchor="w")

        # Auth refresh button — hidden until session expires
        self._auth_btn = tk.Label(self.card, text="Update cookie", font=FONT_SM, bg=BG, fg=ACCENT, cursor="hand2")
        self._auth_btn.bind("<Button-1>", lambda e: self._update_cookie())

        # Make draggable
        for w in (self.card, title_row):
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag)

    def _position_bottom_right(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = sw - w - 20
        y = sh - h - 60
        self.root.geometry(f"+{x}+{y}")

    # ── drag ────────────────────────────────────────────────────────────────

    def _on_drag_start(self, event):
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    # ── data ────────────────────────────────────────────────────────────────

    def _refresh_loop(self):
        while self._running:
            self._do_refresh()
            time.sleep(REFRESH_INTERVAL)

    def _trigger_refresh(self):
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        try:
            data = fetch_usage(self.session_key)
            self.root.after(0, self._apply_data, data)
        except Exception as e:
            if hasattr(e, "response") and e.response is not None and e.response.status_code in (401, 403):
                self.root.after(0, self._show_auth_error)
            else:
                self.root.after(0, self._show_error, str(e))

    def _apply_data(self, data: dict):
        self.session_bar.update(data["session_pct"], data["session_resets"])
        self.weekly_bar.update(data["weekly_pct"], data["weekly_resets"])
        now = time.strftime("%I:%M %p").lstrip("0")
        self.status_lbl.config(text=f"Last updated: {now}", fg=FG_MUTED)
        self._auth_btn.pack_forget()

    def _show_error(self, msg: str):
        self.status_lbl.config(text=f"Error: {msg[:60]}", fg=RED)
        self._auth_btn.pack_forget()

    def _show_auth_error(self):
        self.status_lbl.config(text="Session expired", fg=RED)
        self._auth_btn.pack(anchor="w", pady=(2, 0))

    def _update_cookie(self, error_msg=None):
        instructions = (
            "Paste the full Cookie header from your browser.\n\n"
            "How to find it:\n"
            "  1. Open claude.ai in Chrome/Edge\n"
            "  2. Press F12 → Network tab → refresh the page\n"
            "  3. Click any request to claude.ai\n"
            "  4. In Headers, find 'Cookie:' and copy the FULL value"
        )
        prompt = f"{error_msg}\n\n{instructions}" if error_msg else instructions

        self.root.attributes("-topmost", False)
        key = simpledialog.askstring("Claude Usage Widget", prompt, show="*", parent=self.root)
        self.root.attributes("-topmost", True)

        if not key:
            return

        key = sanitize_cookie(key)
        self._auth_btn.pack_forget()
        self.status_lbl.config(text="Checking cookie…", fg=FG_MUTED)

        def validate():
            try:
                data = fetch_usage(key)
                save_session_key(key)
                self.session_key = key
                self.root.after(0, self._apply_data, data)
            except Exception as e:
                if hasattr(e, "response") and e.response is not None and e.response.status_code in (401, 403):
                    self.root.after(0, self._update_cookie, "Cookie was not accepted.")
                else:
                    self.root.after(0, self._update_cookie, f"Error: {str(e)[:80]}")

        threading.Thread(target=validate, daemon=True).start()

    def quit(self):
        self._running = False
        self.root.destroy()


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    key = load_session_key()

    if not key:
        # Headless prompt before tk window opens
        root = tk.Tk()
        root.withdraw()
        key = simpledialog.askstring(
            "Claude Usage Widget",
            "Paste the full Cookie header from your browser.\n\n"
            "How to find it:\n"
            "  1. Open claude.ai in Chrome/Edge\n"
            "  2. Press F12 → Network tab → refresh the page\n"
            "  3. Click any request to claude.ai\n"
            "  4. In Headers, find 'Cookie:' and copy the FULL value",
            show="*",
        )
        root.destroy()
        if not key:
            sys.exit(0)
        key = sanitize_cookie(key)
        save_session_key(key)
        print("Session key saved to config.txt")

    ClaudeUsageWidget(key)


if __name__ == "__main__":
    main()
