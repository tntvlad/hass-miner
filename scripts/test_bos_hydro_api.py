"""Test BOS REST API endpoints on the S21e Hydro miner at 192.168.1.245."""
import urllib.request
import json

IP = "192.168.1.245"
BASE = f"http://{IP}/api/v1"

# Login
req = urllib.request.Request(
    f"{BASE}/auth/login",
    data=json.dumps({"username": "root", "password": "root"}).encode(),
    headers={"Content-Type": "application/json"},
)
r = urllib.request.urlopen(req, timeout=10)
tok = json.loads(r.read())["token"]
print(f"Token: {tok[:8]}...")


def get(endpoint):
    req2 = urllib.request.Request(
        f"{BASE}/{endpoint}", headers={"Authorization": "Bearer " + tok}
    )
    try:
        r2 = urllib.request.urlopen(req2, timeout=10)
        return json.loads(r2.read())
    except Exception as e:
        return {"ERROR": str(e)}


for ep in ["miner/stats", "miner/details", "cooling/state", "miner/hw/hashboards"]:
    print(f"\n{'='*60}")
    print(f"=== {ep} ===")
    print(json.dumps(get(ep), indent=2))
