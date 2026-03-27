# System Commands

System-level commands for the Avalon Nano 3s.

---

## Reboot / Restart

Restart the miner.

**Command:** `restart`

**Example:**
```bash
$ echo "restart" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=7,Msg=CGMiner restart,Description=cgminer 4.12.1|
```

> **Note:** The miner will disconnect immediately after sending the restart status. Connection may fail or timeout on the response read - this is expected.

---

## Version

Get CGMiner and API version information.

**Command:** `version`

**Response Fields:**

| Field | Description |
|-------|-------------|
| CGMiner | CGMiner version |
| API | API version |

**Example:**
```bash
$ echo "version" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=22,Msg=CGMiner versions,Description=cgminer 4.12.1|
VERSION,CGMiner=4.12.1,API=3.7|
```

---

## Check Command Availability

Check if a command exists and if you have access.

**Command:** `check|<command>`

**Response Fields:**

| Field | Values | Description |
|-------|--------|-------------|
| Exists | Y/N | Command exists |
| Access | Y/N | You have access |

**Example:**
```bash
$ echo "check|restart" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=70,Msg=Check command,Description=cgminer 4.12.1|
CHECK,Exists=Y,Access=Y|
```

---

## Quit (Shutdown CGMiner)

Stop the CGMiner process. **Use with caution!**

**Command:** `quit`

**Example:**
```bash
$ echo "quit" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=0,Msg=BYE|
```

> ⚠️ **Warning:** This stops the mining software. On the Nano 3s, use `restart` instead to reboot the miner properly.

---

## Python Example: Reboot Miner

```python
import asyncio

async def reboot_miner(ip: str, timeout: int = 10) -> bool:
    """Reboot Avalon Nano 3s via CGMiner API."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 4028),
            timeout=timeout,
        )
        
        writer.write(b"restart")
        await writer.drain()
        
        # Try to read response (may timeout - that's OK)
        try:
            response = await asyncio.wait_for(reader.read(4096), timeout=5)
            print(f"Response: {response.decode()}")
        except asyncio.TimeoutError:
            print("No response (miner is rebooting)")
        
        writer.close()
        await writer.wait_closed()
        return True
        
    except Exception as e:
        print(f"Reboot failed: {e}")
        return False

# Reboot miner
asyncio.run(reboot_miner("192.168.1.100"))
```

---

## Home Assistant Integration

This integration exposes a **Reboot Button** entity:

- **Entity:** `button.<miner_name>_reboot`
- **Action:** Press to reboot the miner

The button sends the `restart` command via the CGMiner API.

---

## Unsupported System Commands

The following system commands are **not available** on the Avalon Nano 3s:

| Command | Why Not Supported |
|---------|-------------------|
| `save` | No config save support |
| `hotplug` | USB hotplug not applicable |
| `debug` | Debug modes not exposed |

---

## Pause/Resume Mining

Use `ascenable` and `ascdisable` to pause and resume mining:

```bash
# Pause mining
echo "ascdisable|0" | nc 192.168.1.100 4028

# Resume mining
echo "ascenable|0" | nc 192.168.1.100 4028

# Check status (look for Enabled=Y or Enabled=N)
echo "devs" | nc 192.168.1.100 4028
```

The `0` refers to ASC device 0 (the Nano 3s has only one device).

The `devs` command returns `Enabled=Y` or `Enabled=N` to indicate the current state.

### Home Assistant Integration

This integration exposes a **Mining Switch** entity:

- **Entity:** `switch.<miner_name>_mining`
- **Turn OFF** → Sends `ascdisable|0` (pause)
- **Turn ON** → Sends `ascenable|0` (resume)
- **State** → Updated from `devs` command `Enabled` field
