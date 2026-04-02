# Work Mode Control

Control the performance/power mode of the Avalon Nano 3s.

---

## Reading Work Mode

Use the `estats` command and parse the WORKMODE field.

**Command:** `estats`

**WORKMODE Response Format:** `WORKMODE[N]`

**Example:**

```bash
$ echo "estats" | nc 192.168.1.100 4028
...WORKMODE[1]...
```

This means: Work mode = Mid (1)

---

## Setting Work Mode

**Command:** `ascset|0,workmode,N`

### Mode Values

| Value | Mode | Description                          |
| ----- | ---- | ------------------------------------ |
| 0     | Low  | Lower power, lower hashrate, quieter |
| 1     | Mid  | Balanced power and performance       |
| 2     | High | Maximum hashrate, higher power/heat  |

---

## Examples

### Set to Low Power Mode

```bash
echo "ascset|0,workmode,0" | nc 192.168.1.100 4028
```

### Set to Mid (Balanced) Mode

```bash
echo "ascset|0,workmode,1" | nc 192.168.1.100 4028
```

### Set to High Performance Mode

```bash
echo "ascset|0,workmode,2" | nc 192.168.1.100 4028
```

---

## Response

**Success:**

```
STATUS=S,When=1711526400,Code=120,Msg=ASC 0 set OK,Description=cgminer 4.12.1|
```

**Error:**

```
STATUS=E,When=1711526400,Code=121,Msg=ASC 0 set failed,Description=cgminer 4.12.1|
```

---

## Performance Characteristics

| Mode | Hashrate  | Power | Noise  | Temperature |
| ---- | --------- | ----- | ------ | ----------- |
| Low  | ~300 GH/s | ~6W   | Quiet  | Cooler      |
| Mid  | ~400 GH/s | ~8W   | Medium | Moderate    |
| High | ~500 GH/s | ~12W  | Louder | Warmer      |

> **Note:** Actual values vary based on chip quality and ambient temperature.

---

## Python Example

```python
import asyncio

WORK_MODES = {"Low": 0, "Mid": 1, "High": 2}
REVERSE_WORK_MODES = {0: "Low", 1: "Mid", 2: "High"}

async def set_workmode(ip: str, mode: str) -> bool:
    """Set Avalon Nano 3s workmode via CGMiner API."""
    mode_id = WORK_MODES.get(mode)
    if mode_id is None:
        raise ValueError(f"Invalid mode: {mode}")

    command = f"ascset|0,workmode,{mode_id}"

    reader, writer = await asyncio.open_connection(ip, 4028)
    writer.write(command.encode())
    await writer.drain()

    response = await reader.read(4096)
    writer.close()
    await writer.wait_closed()

    return b"STATUS=S" in response

async def get_workmode(ip: str) -> str:
    """Get current workmode from Avalon Nano 3s."""
    import re

    reader, writer = await asyncio.open_connection(ip, 4028)
    writer.write(b"estats")
    await writer.drain()

    response = await reader.read(8192)
    writer.close()
    await writer.wait_closed()

    match = re.search(r"WORKMODE\[(\d+)\]", response.decode())
    if match:
        return REVERSE_WORK_MODES.get(int(match.group(1)), "Unknown")
    return "Unknown"

# Set to High mode
asyncio.run(set_workmode("192.168.1.100", "High"))

# Get current mode
mode = asyncio.run(get_workmode("192.168.1.100"))
print(f"Current mode: {mode}")
```

---

## Why No Manual Overclock?

Unlike larger Avalon miners (BTB, MBA, etc.) that support custom frequency and voltage settings, the Avalon Nano 3s uses **fixed hardware profiles** controlled by the workmode setting.

The CGMiner `ascset` command for frequency/voltage:

- `ascset|0,freq,N` - **Not supported** on Nano 3s
- `ascset|0,millivolts,N` - **Not supported** on Nano 3s

These commands return an error on the Nano 3s. Use workmode instead for performance tuning.

---

## Home Assistant Integration

This integration exposes workmode control through a **Select Entity**:

- **Entity:** `select.<miner_name>_work_mode`
- **Options:** Low, Mid, High

The current workmode is also displayed in the **Active Preset Name** sensor.
