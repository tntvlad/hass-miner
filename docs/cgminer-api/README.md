# CGMiner API Documentation (Avalon Nano 3s)

**API Version:** CGMiner 4.x  
**Protocol:** TCP Socket (ASCII)  
**Port:** 4028  
**Target Device:** Avalon Nano 3s

## Overview

The Avalon Nano 3s uses CGMiner's ASCII-based socket API for control and monitoring. Commands are sent as plain text over TCP and responses are pipe-delimited key=value pairs.

## Documentation Files

- [Commands](commands.md) - Available API commands
- [Stats & Monitoring](stats.md) - estats, summary, devs
- [LED Control](led.md) - RGB color, brightness, effects
- [Work Mode](workmode.md) - Low/Mid/High performance modes
- [System](system.md) - Reboot, version info

## Connection

Connect to the miner via TCP on port 4028:

```bash
# Using netcat (Linux/Mac)
echo "command" | nc <miner-ip> 4028

# Using PowerShell (Windows)
$client = New-Object System.Net.Sockets.TcpClient("<miner-ip>", 4028)
$stream = $client.GetStream()
$writer = New-Object System.IO.StreamWriter($stream)
$writer.WriteLine("command")
$writer.Flush()
```

## Response Format

Responses use pipe (`|`) as record separator and comma (`,`) as field separator:

```
STATUS=S,When=1234567890,Code=69,Msg=...,Description=cgminer 4.x|
SUMMARY,Elapsed=12345,MHS av=0.50,...|
```

## Quick Examples

```bash
# Get miner summary
echo "summary" | nc 192.168.1.100 4028

# Get extended stats (workmode, LED state)
echo "estats" | nc 192.168.1.100 4028

# Pause mining
echo "ascdisable|0" | nc 192.168.1.100 4028

# Resume mining
echo "ascenable|0" | nc 192.168.1.100 4028

# Set LED to red with Stay effect at 100% brightness
echo "ascset|0,led,1-100-50-255-0-0" | nc 192.168.1.100 4028

# Set workmode to High
echo "ascset|0,workmode,2" | nc 192.168.1.100 4028

# Reboot miner
echo "restart" | nc 192.168.1.100 4028
```

## Authentication

The CGMiner API on Avalon Nano 3s does **not require authentication** by default. Commands are executed with full access.

> ⚠️ **Security Note:** Ensure your miner is on a trusted network as there is no authentication.

## Limitations

| Feature | Supported | Notes |
|---------|-----------|-------|
| Workmode | ✅ Yes | Low (0), Mid (1), High (2) |
| LED Control | ✅ Yes | Effect, brightness, RGB |
| Reboot | ✅ Yes | Via `restart` command |
| Pause Mining | ✅ Yes | Via `ascdisable\|0` command |
| Resume Mining | ✅ Yes | Via `ascenable\|0` command |
| Overclock | ❌ No | Use workmode instead |
| Voltage Control | ❌ No | Fixed by hardware |
