import urllib.request, urllib.error, http.cookiejar, json

IP = "192.168.1.245"
BASE = f"http://{IP}/api/v1"

# Login
req = urllib.request.Request(
    f"{BASE}/auth/login",
    data=json.dumps({"username": "root", "password": "root"}).encode(),
    headers={"Content-Type": "application/json"},
)
r = urllib.request.urlopen(req, timeout=10)
login_data = json.loads(r.read())
print("Login response:", json.dumps(login_data))
tok = login_data.get("token", "")

# Try version endpoint (may not require auth)
try:
    r_ver = urllib.request.urlopen(f"{BASE}/version/", timeout=5)
    print("version/ (no auth):", r_ver.read().decode()[:200])
except urllib.error.HTTPError as e:
    print(f"version/ without auth: {e.code} {e.reason}")

# Try different auth approaches
for ep in ["miner/stats", "miner/details", "cooling/state", "miner/hw/hashboards"]:
    url = f"{BASE}/{ep}"
    # Try Bearer token
    req2 = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    try:
        r2 = urllib.request.urlopen(req2, timeout=10)
        print(f"\n=== {ep} (Bearer) ===")
        print(json.dumps(json.loads(r2.read()), indent=2))
    except urllib.error.HTTPError as e:
        # Try just the raw token (no "Bearer" prefix)
        req3 = urllib.request.Request(url, headers={"Authorization": tok})
        try:
            r3 = urllib.request.urlopen(req3, timeout=10)
            print(f"\n=== {ep} (raw token) ===")
            print(json.dumps(json.loads(r3.read()), indent=2))
        except urllib.error.HTTPError as e2:
            print(f"ERROR {ep}: Bearer={e.code}, raw={e2.code}")
