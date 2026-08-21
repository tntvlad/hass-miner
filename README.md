# hass-miner

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![pre-commit][pre-commit-shield]][pre-commit]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]

> **Note:** This is a fork of the original [Schnitzel/hass-miner](https://github.com/Schnitzel/hass-miner) which is no longer actively maintained. Full credit goes to [@Schnitzel](https://github.com/Schnitzel) and [@b-rowan](https://github.com/b-rowan) for creating this excellent integration.

Control and monitor your Bitcoin miners from Home Assistant.

Great for heat reuse, solar mining, or any use case where you don't need your miners running 24/7 or at full wattage.

Works great in coordination with [ESPHome](https://www.home-assistant.io/integrations/esphome/) for extra sensors (like ambient temperature) and [Grafana](https://github.com/hassio-addons/addon-grafana) for dashboards.

See the [changelog](CHANGELOG.md) for what's new.

## Features

### Automatic discovery

Don't know your miner's IP? Leave the IP field empty during setup and the integration scans your network for miners — pick one from the discovered list and continue. Duplicate protection is built in: each miner can only be added once (identified by MAC address).

### Resilient by design

- **Offline-tolerant setup** — powered-off miners (e.g. for energy saving) set up fine from a cached device profile; entities show *unavailable* and recover automatically when the miner returns.
- **No fake data** — transient poll failures keep last-known values instead of showing zeros; entities go unavailable after ~4 minutes of continuous failure.
- **Hard timeouts everywhere** — detection and network scanning are bounded so a flaky miner can never hang setup.

### Monitoring & control

| Platform | Description |
| -------- | ----------- |
| `sensor`  | Hashrate, expected hashrate, power draw, efficiency, per-board temps/clocks, fans, uptime, best share, found blocks, pool info and more |
| `switch`  | Turn mining on/off (pause/resume) |
| `number`  | Power limit; VNish voltage/frequency/throttle controls |
| `select`  | Avalon work modes & LED effects; VNish overclock presets |
| `light`   | Avalon Nano RGB LED |
| `button`  | Avalon reboot |

**Services:**

| Service           | Description                          |
| ----------------- | ------------------------------------ |
| `reboot`          | Reboot a miner                       |
| `restart_backend` | Restart the mining process on a miner |
| `set_work_mode`   | Set the work mode of an Avalon miner |

## Supported hardware

Any miner supported by [pyasic](https://pyasic.readthedocs.io/en/latest/miners/supported_types/) works for basic monitoring, including:

Antminer, Whatsminer, Avalonminer, Innosilicon, Goldshell, Auradine, BitAxe, IceRiver, Hammer, and miners running Braiins OS, VNish, ePIC, HiveOS, LuxOS or Mara firmware.

On top of pyasic, this integration adds **direct vendor API integrations** for richer data and controls:

---

### Braiins OS (BOS)

Direct integration with the BOS REST API (`http://<miner>/api/v1`) plus the gRPC stats API (port 50051).
Tested with: **Antminer S21e Hyd** running BOS firmware.

> Requires BOS firmware ≥ 23.03 (REST API). Older BOS releases (e.g. S9 with GraphQL API) fall back to pyasic-only data.

**Extras beyond pyasic:**

- Per-board inlet/outlet temperatures and real hashrate (REST)
- Best share & found blocks (gRPC)
- Mining switch and power-limit number created regardless of capability flags
- Hydro models (e.g. S21e Hyd): fan entities suppressed, water inlet/outlet temperatures per hashboard

API docs: [docs/bos-api/README.md](docs/bos-api/README.md)

---

### VNish firmware

Direct integration with the VNish REST API (`http://<miner>/api/v1`).

**Extras beyond pyasic:**

- Per-chain PCB/chip temperatures (min/max), stable across transient fetch errors
- Best share & found blocks
- Active preset display and a preset dropdown (with a safety limit: presets above `preset_switcher.top_preset` are hidden)
- Throttle number entity (20–100 % in 5 % steps) to dim mining without stopping it — VNish ≥ 1.3.3, takes ~80 s to apply
- Voltage/frequency overclock numbers
- Water inlet/outlet temperature sensors for hydro miners
- Legacy support for VNish 3.x via its CGI mining switch

**Auth:** `POST /api/v1/unlock` with `{"pw": "<password>"}` → token used as `Authorization` header.

---

### Avalon Nano 3s

Direct CGMiner API communication on port 4028:

- Work mode select (Low / Mid / High)
- RGB LED light with effects (Stay, Flash, Breathing, Loop)
- Reboot button
- Best share (auto-scaling K/M/G/T/P/E/Z) & found blocks

Avalon units can be configured in **Simple** mode (pyasic only) or **Full** mode (adds CGMiner API control).

---

### Whatsminer

- **Auto API enable** — automatically enables the Whatsminer write API when a "can't access write cmd" error occurs
- **Power limit control** — reliable fixed power limit slider ([#1](https://github.com/tntvlad/hass-miner/issues/1))
- RPC password supported during setup

> If auto-enable fails, enable the API manually using WhatsMinerTool: Remote Ctrl → Miner API Switch → Enable

---

### BitAxe

Best difficulty and found-block sensors via the local HTTP API (`/api/system/info`) — no credentials required.

## Installation

### Option 1: HACS (custom repository)

1. Open HACS in Home Assistant
2. Click the three dots menu (⋮) in the top right
3. Select **Custom repositories**
4. Add `tntvlad/hass-miner` with Category: **Integration**
5. Click **Add**
6. Search for "Miner" in HACS and download

### Option 2: One-Click Install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tntvlad&repository=hass-miner&category=integration)

### Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **HASS-miner**
3. Enter your miner's IP address — **or leave it empty to scan your network** for miners and pick one from the discovered list
4. Follow the prompts for credentials (if required) and finish setup

Repeat per miner. The network scan covers the subnet(s) Home Assistant is connected to and can take up to a couple of minutes on large networks.

## Known Issues

### Avalon Nano 3s

- **LED Brightness** — brightness slider not working correctly (WRGB format investigation needed)
- **Mining Enable/Disable** — `ascenable`/`ascdisable` command format needs investigation
- **Restart Function** — miner restart service not yet implemented

### Whatsminer M30S

- **Chip Temperature** — may show *unknown* on some firmware versions (investigating)

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

## Credits

This project was generated from [@oncleben31](https://github.com/oncleben31)'s [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.

Code template was mainly taken from [@Ludeeus](https://github.com/ludeeus)'s [integration_blueprint][integration_blueprint] template.

Miner control and data is handled using [@UpstreamData](https://github.com/UpstreamData)'s [pyasic](https://github.com/UpstreamData/pyasic).

---

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[commits-shield]: https://img.shields.io/github/commit-activity/y/tntvlad/hass-miner.svg?style=for-the-badge
[commits]: https://github.com/tntvlad/hass-miner/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/tntvlad/hass-miner.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40tntvlad-blue.svg?style=for-the-badge
[pre-commit]: https://github.com/pre-commit/pre-commit
[pre-commit-shield]: https://img.shields.io/badge/pre--commit-enabled-brightgreen?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/tntvlad/hass-miner.svg?style=for-the-badge
[releases]: https://github.com/tntvlad/hass-miner/releases
[user_profile]: https://github.com/tntvlad
