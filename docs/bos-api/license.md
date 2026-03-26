# License API

## Get License State

**Endpoint:** `GET /api/v1/license/license`

**Response:**
```json
{
  "state": {}
}
```

States: `none`, `limited`, `valid`, `expired`

## Apply Contract Key

**Endpoint:** `PUT /api/v1/license/apply-contract-key`

**Request:**
```json
{
  "contract_key": "your-license-key"
}
```

**Response:**
```json
{
  "successful": true
}
```
