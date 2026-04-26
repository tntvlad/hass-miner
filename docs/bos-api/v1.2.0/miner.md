# Miner API

Get miner information and statistics.

## Get Miner Details

**Endpoint:** `GET /api/v1/miner/details`

**Response:**

```json
{
  "bos_mode": 0,
  "bos_version": {},
  "bosminer_uptime_s": 0,
  "hostname": "string",
  "kernel_version": "string",
  "mac_address": "string",
  "miner_identity": {},
  "platform": 0,
  "psu_info": {},
  "serial_number": "string",
  "status": 0,
  "sticker_hashrate": {},
  "system_uptime_s": 0,
  "uid": "string"
}
```

## Get Miner Statistics

**Endpoint:** `GET /api/v1/miner/stats`

**Response:**

```json
{
  "miner_stats": {},
  "pool_stats": {},
  "power_stats": {}
}
```

## Get Miner Status (Stream)

**Endpoint:** `GET /api/v1/miner/status`

Status values: `unspecified`, `not_started`, `normal`, `paused`, `suspended`, `restricted`

## Get Miner Errors

**Endpoint:** `GET /api/v1/miner/errors`

**Response:**

```json
{
  "errors": []
}
```

## Hashboards

### Get Hashboard Details

**Endpoint:** `GET /api/v1/miner/hw/hashboards`

### Enable/Disable Hashboards

**Endpoint:** `PATCH /api/v1/miner/hw/hashboards`

**Request:**

```json
{
  "enable": false,
  "hashboard_ids": ["1", "3"]
}
```

## Support Archive

**Endpoint:** `GET /api/v1/miner/support-archive`

**Request:**

```json
{
  "format": "zip"
}
```

Format options: `zip`, `bos`, `zipencrypted`
