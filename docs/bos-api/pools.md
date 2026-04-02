# Pools API

Pool configuration management.

## Get Pool Groups

**Endpoint:** `GET /api/v1/pools/`

**Response:**

```json
[
  {
    "uid": "group1",
    "name": "High Performance",
    "pools": [],
    "strategy": {}
  }
]
```

## Create Pool Group

**Endpoint:** `POST /api/v1/pools/`

**Request:**

```json
{
  "name": "My Pool",
  "pools": [
    {
      "url": "stratum+tcp://pool.example.com:3333",
      "user": "worker.1",
      "password": "x"
    }
  ],
  "load_balance_strategy": {
    "failonly": {}
  }
}
```

## Update Pool Group

**Endpoint:** `PUT /api/v1/pools/{uid}`

## Delete Pool Group

**Endpoint:** `DELETE /api/v1/pools/{uid}`

## Set Multiple Pool Groups (Batch)

**Endpoint:** `PUT /api/v1/pools/batch`

Replace all pool groups at once.

**Request:**

```json
[
  {
    "name": "Pool 1",
    "pools": [],
    "load_balance_strategy": {}
  }
]
```

## Load Balance Strategies

- `failonly` - Failover only
- `fixedshareratio` - Fixed ratio between pools
