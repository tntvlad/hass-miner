# Actions API

Control mining operations.

## Start Mining
**Endpoint:** `PUT /api/v1/actions/start`  
**Response:** `true` if was already running

## Stop Mining
**Endpoint:** `PUT /api/v1/actions/stop`  
**Response:** `true` if was already stopped

## Pause Mining
**Endpoint:** `PUT /api/v1/actions/pause`  
**Response:** `true` if was already paused

## Resume Mining
**Endpoint:** `PUT /api/v1/actions/resume`  
**Response:** `true` if was already mining

## Restart Mining
**Endpoint:** `PUT /api/v1/actions/restart`  
**Response:** `true` if was already running

## Reboot Miner
**Endpoint:** `PUT /api/v1/actions/reboot`  
**Response:** 204 on success

## Factory Reset
**Endpoint:** `PUT /api/v1/actions/factory-reset`  
**Response:** 204 on success

## Locate Device (LED Blink)

**Get status:** `GET /api/v1/actions/locate`  
**Set status:** `PUT /api/v1/actions/locate`

Request body: `true` or `false`
