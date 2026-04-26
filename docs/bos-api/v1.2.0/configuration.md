# Configuration API

## Get Constraints

**Endpoint:** `GET /api/v1/configuration/constraints`

Returns miner configuration constraints (min/max values).

**Response:**

```json
{
  "cooling_constraints": {},
  "dps_constraints": {},
  "hashboards_constraints": {},
  "tuner_constraints": {}
}
```

## Get Miner Configuration

**Endpoint:** `GET /api/v1/configuration/miner`

**Response:**

```json
{
  "dps": {},
  "hashboard_config": {},
  "pool_groups": [],
  "temperature": {},
  "tuner": {}
}
```
