# Stats & Monitoring

Commands to retrieve miner statistics and monitoring data.

---

## summary

Get overall mining summary.

**Command:** `summary`

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| Elapsed | int | Seconds since miner started |
| MHS av | float | Average hashrate (MH/s) |
| MHS 5s | float | 5-second hashrate (MH/s) |
| MHS 1m | float | 1-minute hashrate (MH/s) |
| MHS 5m | float | 5-minute hashrate (MH/s) |
| MHS 15m | float | 15-minute hashrate (MH/s) |
| Found Blocks | int | Blocks found |
| Accepted | int | Accepted shares |
| Rejected | int | Rejected shares |
| Hardware Errors | int | Hardware errors |
| Best Share | int | Best share difficulty |
| Pool Rejected% | float | Rejection percentage |
| Pool Stale% | float | Stale share percentage |

**Example:**
```bash
$ echo "summary" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=11,Msg=Summary,Description=cgminer 4.12.1|
SUMMARY,Elapsed=86400,MHS av=0.50,MHS 5s=0.52,Found Blocks=0,Accepted=1234,
Rejected=5,Hardware Errors=0,Best Share=98765,...|
```

---

## estats

Get extended statistics including Avalon-specific data like workmode and LED state.

**Command:** `estats`

**Response Fields (Avalon-specific):**

| Field | Format | Description |
|-------|--------|-------------|
| WORKMODE | `WORKMODE[N]` | Current work mode (0=Low, 1=Mid, 2=High) |
| LED | `LED[e-b-t-R-G-B]` | LED state (effect-brightness-temp-R-G-B) |
| TEMP | `TEMP[N]` | Temperature in Celsius |
| FAN | `FAN[N]` | Fan speed (RPM or %) |
| FREQ | `FREQ[N]` | Chip frequency |
| VOLTAGE | `VOLTAGE[N]` | Voltage (mV) |

**Example:**
```bash
$ echo "estats" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=70,Msg=CGMiner stats,Description=cgminer 4.12.1|
STATS=0,ID=AVA100,Elapsed=86400,...,WORKMODE[1],LED[1-100-50-255-255-255],
TEMP[45],FAN[3500],...|
```

**Parsing WORKMODE:**
```python
import re
match = re.search(r"WORKMODE\[(\d+)\]", response)
if match:
    workmode = int(match.group(1))  # 0=Low, 1=Mid, 2=High
```

**Parsing LED:**
```python
import re
match = re.search(r"LED\[(\d+)-(\d+)-(\d+)-(\d+)-(\d+)-(\d+)\]", response)
if match:
    effect = int(match.group(1))      # 0-4
    brightness = int(match.group(2))  # 0-100
    color_temp = int(match.group(3))  # 0-100
    r = int(match.group(4))           # 0-255
    g = int(match.group(5))           # 0-255
    b = int(match.group(6))           # 0-255
```

---

## devs

Get information about all devices.

**Command:** `devs`

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| ASC | int | ASC device ID |
| Name | string | Device name |
| ID | int | Device ID |
| Enabled | string | Y/N |
| Status | string | Alive/Dead |
| Temperature | float | Temperature (°C) |
| MHS av | float | Average hashrate |
| MHS 5s | float | 5-second hashrate |
| Accepted | int | Accepted shares |
| Rejected | int | Rejected shares |
| Hardware Errors | int | HW errors |
| Last Share Pool | int | Pool ID of last share |
| Last Share Time | int | Unix timestamp |

**Example:**
```bash
$ echo "devs" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=9,Msg=1 ASC(s),Description=cgminer 4.12.1|
ASC=0,Name=AVA10,ID=0,Enabled=Y,Status=Alive,Temperature=45.00,
MHS av=0.50,Accepted=1234,Rejected=5,...|
```

---

## pools

Get pool status and statistics.

**Command:** `pools`

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| POOL | int | Pool ID |
| URL | string | Pool URL |
| Status | string | Alive/Dead/Disabled |
| Priority | int | Pool priority |
| Accepted | int | Accepted shares |
| Rejected | int | Rejected shares |
| Stale | int | Stale shares |
| Last Share Time | int | Unix timestamp |
| Diff1 Shares | int | Difficulty 1 equivalent |
| Stratum Active | bool | Using stratum |

**Example:**
```bash
$ echo "pools" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=7,Msg=1 Pool(s),Description=cgminer 4.12.1|
POOL=0,URL=stratum+tcp://pool.example.com:3333,Status=Alive,Priority=0,
Accepted=1234,Rejected=5,Stale=0,...|
```

---

## config

Get miner configuration.

**Command:** `config`

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| ASC Count | int | Number of ASC devices |
| Pool Count | int | Number of pools |
| Strategy | string | Pool strategy |
| Log Interval | int | Log interval (seconds) |
| Device Code | string | Compiled device drivers |
| OS | string | Operating system |

**Example:**
```bash
$ echo "config" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=33,Msg=CGMiner config,Description=cgminer 4.12.1|
CONFIG,ASC Count=1,Pool Count=1,Strategy=Failover,Log Interval=5,
Device Code=AVA,OS=Linux|
```
