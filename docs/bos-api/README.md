# Braiins OS Public REST API Documentation

**API Version:** 1.2.0 — see [v1.3.0/openapi.json](v1.3.0/openapi.json) for the latest spec  
**Base URL:** `http://<miner-ip>/api/v1`  
**Official Docs:** https://developer.braiins-os.com/latest/openapi.html

## Overview

The Braiins OS Public API (introduced in version 23.03) provides REST endpoints to control and monitor miners running Braiins OS firmware.

## Documentation Files

- [Authentication](v1.2.0/authentication.md) - Login and token management
- [Actions](v1.2.0/actions.md) - Start, stop, reboot, pause mining
- [Performance](v1.2.0/performance.md) - Power target, hashrate, tuner settings
- [Miner](v1.2.0/miner.md) - Miner details, stats, hashboards
- [Cooling](v1.2.0/cooling.md) - Temperature and fan control
- [Pools](v1.2.0/pools.md) - Pool configuration
- [Network](v1.2.0/network.md) - Network settings
- [Configuration](v1.2.0/configuration.md) - Miner configuration
- [License](v1.2.0/license.md) - License management
- [Upgrade](v1.2.0/upgrade.md) - Auto-upgrade settings

## Authentication

Get a token by calling `POST /api/v1/auth/login` with username and password.

### v1.2.0 — Bearer prefix required

```
Authorization: Bearer <token>
```

### v1.3.0 — Raw token, NO Bearer prefix

> **Important:** Using `Bearer` in v1.3.0 returns 401. Send the raw token directly.

```
Authorization: <token>
```

## Quick Example

### v1.2.0

```bash
# Login
TOKEN=$(curl -s -X POST "http://192.168.1.21/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"root","password":"root"}' | jq -r '.token')

# Set power target (no restart!)
curl -X PUT "http://192.168.1.21/api/v1/performance/power-target" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"watt": 1800}'
```

### v1.3.0

```bash
# Login
TOKEN=$(curl -s -X POST "http://192.168.1.21/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"root","password":"root"}' | jq -r '.token')

# Set power target — raw token, no Bearer!
curl -X PUT "http://192.168.1.21/api/v1/performance/power-target" \
  -H "Authorization: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"watt": 1800}'
```
