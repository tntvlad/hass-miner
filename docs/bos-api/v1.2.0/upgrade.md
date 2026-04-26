# Upgrade API

## Get Auto-Upgrade Settings

**Endpoint:** `GET /api/v1/upgrade/auto-upgrade`

**Response:**

```json
{
  "enabled": true,
  "last_execution": {
    "seconds": 1744085400,
    "nanos": 0
  },
  "next_execution": {
    "seconds": 1744171800,
    "nanos": 0
  },
  "schedule": {
    "schedule_type": {}
  }
}
```

## Set Auto-Upgrade Settings

**Endpoint:** `PATCH /api/v1/upgrade/auto-upgrade`

**Request:**

```json
{
  "enabled": true,
  "schedule": {
    "schedule_type": {}
  }
}
```

---

# Version API

## Get API Version

**Endpoint:** `GET /api/v1/version/`

**Response:**

```json
{
  "major": 1,
  "minor": 2,
  "patch": 0
}
```

---

# Documentation API

## Get OpenAPI Schema

**Endpoint:** `GET /api/v1/docs/openapi.json`

Returns the full OpenAPI specification in JSON format.
