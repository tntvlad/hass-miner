# LED Control

Control the RGB LED on the Avalon Nano 3s.

---

## Reading LED State

Use the `estats` command and parse the LED field.

**Command:** `estats`

**LED Response Format:** `LED[effect-brightness-colortemp-R-G-B]`

**Example:**
```bash
$ echo "estats" | nc 192.168.1.100 4028
...LED[1-100-50-255-0-0]...
```

This means: Effect=Stay, Brightness=100%, R=255, G=0, B=0 (red)

---

## Setting LED State

**Command:** `ascset|0,led,effect-brightness-colortemp-R-G-B`

### Parameters

| Parameter | Range | Description |
|-----------|-------|-------------|
| effect | 0-4 | LED effect mode |
| brightness | 0-100 | Brightness percentage |
| colortemp | 0-100 | Color temperature (unused for RGB) |
| R | 0-255 | Red component |
| G | 0-255 | Green component |
| B | 0-255 | Blue component |

### Effect Modes

| Value | Effect | Description |
|-------|--------|-------------|
| 0 | Off | LED turned off |
| 1 | Stay | Solid color (always on) |
| 2 | Flash | Blinking/flashing |
| 3 | Breathing | Fade in/out pulsing |
| 4 | Loop | Color cycling/rainbow |

---

## Examples

### Turn LED Off
```bash
echo "ascset|0,led,0-100-50-255-255-255" | nc 192.168.1.100 4028
```

### Solid Red at Full Brightness
```bash
echo "ascset|0,led,1-100-50-255-0-0" | nc 192.168.1.100 4028
```

### Solid Green at 50% Brightness
```bash
echo "ascset|0,led,1-50-50-0-255-0" | nc 192.168.1.100 4028
```

### Blue Breathing Effect
```bash
echo "ascset|0,led,3-100-50-0-0-255" | nc 192.168.1.100 4028
```

### White Flash
```bash
echo "ascset|0,led,2-100-50-255-255-255" | nc 192.168.1.100 4028
```

### Rainbow Loop
```bash
echo "ascset|0,led,4-100-50-255-255-255" | nc 192.168.1.100 4028
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

## Python Example

```python
import asyncio

async def set_led(ip: str, effect: int, brightness: int, r: int, g: int, b: int):
    """Set Avalon Nano 3s LED via CGMiner API."""
    color_temp = 50  # Not used for RGB, but required
    command = f"ascset|0,led,{effect}-{brightness}-{color_temp}-{r}-{g}-{b}"
    
    reader, writer = await asyncio.open_connection(ip, 4028)
    writer.write(command.encode())
    await writer.drain()
    
    response = await reader.read(4096)
    writer.close()
    await writer.wait_closed()
    
    return b"STATUS=S" in response

# Set LED to purple breathing effect at 80% brightness
asyncio.run(set_led("192.168.1.100", 3, 80, 128, 0, 255))
```

---

## Home Assistant Integration

This integration exposes LED control through two entities:

1. **Select Entity (LED Effect)** - Choose effect mode
2. **Light Entity (LED)** - Control brightness and RGB color

Both entities work together - changing the effect via select updates the light entity and vice versa.
