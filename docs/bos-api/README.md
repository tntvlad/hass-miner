# Braiins OS Public REST API Documentation

**API Version:** 1.2.0  
**Base URL:** `http://<miner-ip>/api/v1`  
**Official Docs:** https://developer.braiins-os.com/latest/openapi.html

## Overview

The Braiins OS Public API (introduced in version 23.03) provides REST endpoints to control and monitor miners running Braiins OS firmware.

## Documentation Files

- [Authentication](authentication.md) - Login and token management
- [Actions](actions.md) - Start, stop, reboot, pause mining
- [Performance](performance.md) - Power target, hashrate, tuner settings
- [Miner](miner.md) - Miner details, stats, hashboards
- [Cooling](cooling.md) - Temperature and fan control
- [Pools](pools.md) - Pool configuration
- [Network](network.md) - Network settings
- [Configuration](configuration.md) - Miner configuration
- [License](license.md) - License management
- [Upgrade](upgrade.md) - Auto-upgrade settings

## Authentication

All endpoints (except login) require a Bearer token in the Authorization header:

```
Authorization: Bearer <token>
```

Get a token by calling POST `/api/v1/auth/login` with username and password.

## Quick Example

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
