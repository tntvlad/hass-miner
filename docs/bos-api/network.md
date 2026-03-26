# Network API

Network configuration.

## Get Network Information

**Endpoint:** `GET /api/v1/network/`

**Response:**
```json
{
  "name": "eth0",
  "hostname": "miner-01.local",
  "mac_address": "00:1A:2B:3C:4D:5E",
  "default_gateway": "192.168.1.1",
  "dns_servers": ["8.8.8.8", "8.8.4.4"],
  "networks": [],
  "protocol": 1
}
```

## Get Network Configuration

**Endpoint:** `GET /api/v1/network/configuration`

**Response:**
```json
{
  "hostname": "miner-01.local",
  "protocol": {
    "dhcp": {}
  }
}
```

## Update Network Configuration

**Endpoint:** `PATCH /api/v1/network/configuration`

### DHCP
```json
{
  "hostname": "miner-01.local",
  "protocol": {
    "dhcp": {}
  }
}
```

### Static IP
```json
{
  "hostname": "miner-01.local",
  "protocol": {
    "static": {
      "ip_address": "192.168.1.100",
      "netmask": "255.255.255.0",
      "gateway": "192.168.1.1",
      "dns_servers": ["8.8.8.8"]
    }
  }
}
```
