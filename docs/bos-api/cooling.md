# Cooling API

Temperature and fan control.

## Get Cooling State

**Endpoint:** `GET /api/v1/cooling/state`

**Response:**

```json
{
  "fans": [],
  "highest_temperature": {}
}
```

## Set Cooling Mode

**Endpoint:** `PUT /api/v1/cooling/mode`

Modes: `auto`, `manual`, `immersion`, `hydro`

### Auto Mode

```json
{
  "auto": {
    "target_temperature": { "celsius": 75 },
    "hot_temperature": { "celsius": 85 },
    "dangerous_temperature": { "celsius": 95 }
  }
}
```

### Manual Mode

```json
{
  "manual": {
    "fan_speed_percent": 80
  }
}
```

### Immersion Mode

```json
{
  "immersion": {
    "target_temperature": { "celsius": 75 },
    "hot_temperature": { "celsius": 85 },
    "dangerous_temperature": { "celsius": 95 }
  }
}
```

### Hydro Mode

```json
{
  "hydro": {
    "target_temperature": { "celsius": 75 },
    "hot_temperature": { "celsius": 85 },
    "dangerous_temperature": { "celsius": 95 }
  }
}
```
