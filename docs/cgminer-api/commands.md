# CGMiner Commands Reference

Complete list of CGMiner API commands relevant to Avalon Nano 3s.

## Command Format

Send commands as plain ASCII text over TCP port 4028.

**With parameters:** `command|parameter`  
**Without parameters:** `command`

---

## Read Commands (No Parameters)

| Command | Description |
|---------|-------------|
| `version` | CGMiner and API version |
| `config` | Miner configuration |
| `summary` | Overall mining summary |
| `pools` | Pool status and statistics |
| `devs` | Device (ASC) information |
| `estats` | Extended statistics (workmode, LED, etc.) |
| `coin` | Coin being mined |
| `stats` | Raw statistics from all devices |

---

## Write Commands (Privileged)

| Command | Parameters | Description |
|---------|------------|-------------|
| `restart` | none | Reboot the miner |
| `switchpool` | pool_id | Switch to specified pool |
| `enablepool` | pool_id | Enable a pool |
| `disablepool` | pool_id | Disable a pool |
| `addpool` | URL,User,Pass | Add a new pool |
| `removepool` | pool_id | Remove a pool |
| `poolpriority` | id,id,... | Set pool priority order |

---

## ASC (ASIC) Commands

| Command | Parameters | Description |
|---------|------------|-------------|
| `asc` | device_id | Single ASC device info |
| `asccount` | none | Number of ASC devices |
| `ascenable` | device_id | Enable ASC device |
| `ascdisable` | device_id | Disable ASC device |
| `ascset` | device_id,option,value | Set ASC options |

---

## ascset Options (Avalon Nano 3s)

### Set Work Mode
```
ascset|0,workmode,N
```
Where N is: 0=Low, 1=Mid, 2=High

### Set LED
```
ascset|0,led,effect-brightness-colortemp-R-G-B
```
See [LED Control](led.md) for details.

---

## Response Status Codes

| Code | Meaning |
|------|---------|
| S | Success |
| I | Informational |
| W | Warning |
| E | Error |
| F | Fatal |

---

## Example Session

```bash
# Get version
$ echo "version" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=22,Msg=CGMiner versions,Description=cgminer 4.12.1|
VERSION,CGMiner=4.12.1,API=3.7|

# Get ASC count
$ echo "asccount" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=72,Msg=ASC count,Description=cgminer 4.12.1|
ASCS,Count=1|

# Reboot
$ echo "restart" | nc 192.168.1.100 4028
STATUS=S,When=1711526400,Code=7,Msg=CGMiner restart,Description=cgminer 4.12.1|
```
