# Performance API

Control power and hashrate targets. **These endpoints don't trigger a restart!**

## Set Power Target

**Endpoint:** `PUT /api/v1/performance/power-target`

**Request:**

```json
{
  "watt": 1800
}
```

**Response:**

```json
{
  "watt": 1800
}
```

## Increment/Decrement Power

**Increment:** `PATCH /api/v1/performance/power-target/increment`
**Decrement:** `PATCH /api/v1/performance/power-target/decrement`

```json
{
  "watt": 100
}
```

## Set Default Power Target

**Endpoint:** `PUT /api/v1/performance/power-target/default`

## Relative Power Target

**Endpoint:** `PATCH /api/v1/performance/power-target/relative`

```json
{
  "percentage": 85.5,
  "reference": 1
}
```

Reference values:

- 1 = nominal (sticker)
- 2 = min
- 3 = max
- 4 = current

---

## Hashrate Target

**Set:** `PUT /api/v1/performance/hashrate-target`

```json
{
  "terahash_per_second": 190
}
```

**Increment:** `PATCH /api/v1/performance/hashrate-target/increment`
**Decrement:** `PATCH /api/v1/performance/hashrate-target/decrement`
**Default:** `PUT /api/v1/performance/hashrate-target/default`
**Relative:** `PATCH /api/v1/performance/hashrate-target/relative`

---

## Performance Mode

**Get:** `GET /api/v1/performance/mode`
**Set:** `PUT /api/v1/performance/mode`

## Tuner State

**Get:** `GET /api/v1/performance/tuner-state`

## Target Profiles

**Get:** `GET /api/v1/performance/target-profiles`

## Remove Tuned Profiles

**Delete:** `DELETE /api/v1/performance/tuned-profiles`

---

## DPS (Dynamic Performance Scaling)

**Set:** `PUT /api/v1/performance/dps`

```json
{
  "enable": true,
  "enable_shutdown": true,
  "mode": 1,
  "on_start_target_percent": 100,
  "shutdown_duration": { "hours": 4 },
  "target": { "target": {} }
}
```

---

## Quick Ramping (Curtailment)

**Set:** `PUT /api/v1/performance/quick-ramping`

```json
{
  "up_s": 5,
  "down_s": 2
}
```

**Default:** `PUT /api/v1/performance/quick-ramping/default`
