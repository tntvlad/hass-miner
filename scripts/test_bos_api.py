"""Test BOS API on S21e Hyd miner."""
import urllib.request
import urllib.error
import json

MINER_IP = "192.168.1.245"
BASE_URL = f"http://{MINER_IP}/api/v1"

# Login
req = urllib.request.Request(
    f"{BASE_URL}/auth/login",
    method="POST",
    data=json.dumps({"username": "root", "password": "root"}).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as r:
    login = json.loads(r.read())
    token = login["token"]
    print(f"Token: {token}")

headers = {"Authorization": f"Bearer {token}"}


def get(path):
    req = urllib.request.Request(f"{BASE_URL}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
            print(f"\n=== GET {path} ===")
            print(json.dumps(data, indent=2))
            return data
    except urllib.error.HTTPError as e:
        print(f"\n=== GET {path} => {e.code} ===")
        print(e.read().decode())
        return None


get("/miner/hw/hashboards")
get("/cooling/state")
get("/miner/details")
get("/miner/stats")
