"""Run this to diagnose the API endpoints."""
from curl_cffi import requests
import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.txt")

key = open(CONFIG_FILE).read().strip() if os.path.exists(CONFIG_FILE) else input("Paste full Cookie header: ").strip()
if key.lower().startswith("cookie:"):
    key = key[7:].strip()

headers = {
    "Cookie": key,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-NZ,en;q=0.9",
    "Referer": "https://claude.ai/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

def try_url(label, url):
    print(f"\n── {label} ──")
    print(f"GET {url}")
    r = requests.get(url, headers=headers, timeout=15, impersonate="chrome120")
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        try:
            print(json.dumps(r.json(), indent=2)[:500])
        except Exception:
            print(r.text[:300])
    else:
        print(r.text[:300])
    return r

# Try bootstrap first to get org ID
r = try_url("bootstrap", "https://claude.ai/api/bootstrap")

org_id = None
if r.status_code == 200:
    data = r.json()
    memberships = data.get("account", {}).get("memberships", [])
    for acc in memberships:
        org = acc.get("organization", {})
        if org.get("uuid"):
            org_id = org["uuid"]
            print(f"\n>>> Found org_id: {org_id}")
            break

# Try common endpoints
try_url("progress", "https://claude.ai/api/progress")

if org_id:
    try_url("rate_limits", f"https://claude.ai/api/organizations/{org_id}/rate_limits")
    try_url("usage", f"https://claude.ai/api/organizations/{org_id}/usage")
    try_url("limits", f"https://claude.ai/api/organizations/{org_id}/limits")
    try_url("overage_spend_limit", f"https://claude.ai/api/organizations/{org_id}/overage_spend_limit")
