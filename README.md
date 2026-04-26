# hass-miner

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![pre-commit][pre-commit-shield]][pre-commit]
[![Black][black-shield]][black]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]

> **⚠️ BETA BRANCH** - This branch contains experimental features that are not yet merged to main. Current version: **v1.3.8-beta5**

> **Note:** This is a fork of the original [Schnitzel/hass-miner](https://github.com/Schnitzel/hass-miner) which is no longer actively maintained. Full credit goes to [@Schnitzel](https://github.com/Schnitzel) and [@b-rowan](https://github.com/b-rowan) for creating this excellent integration.

Control and monitor your Bitcoin Miners from Home Assistant.

Great for Heat Reusage, Solar Mining or any usecase where you don't need your miners running 24/7 or with a specific wattage.

Works great in coordination with [ESPHome](https://www.home-assistant.io/integrations/esphome/) for Sensors (like temperature) and [Grafana](https://github.com/hassio-addons/addon-grafana) for Dashboards.

## Beta Branch Features

This beta branch includes direct API implementations on top of pyasic, providing richer data and firmware-specific entities not available through pyasic alone.

> **Note:** Uses pyasic 0.78.0 for compatibility with Home Assistant's pinned pydantic version.  
> **Note:** Includes Python 3.14 compatibility patch for pydantic/pyasic interaction.

---

### Braiins OS (BOS) — REST API

Direct integration with the Braiins OS Public REST API (`http://<miner>/api/v1`).  
Tested with: **Antminer S21e Hyd.** running BOS firmware.

> **Note:** The REST API was introduced in BOS firmware **23.03**. Older BOS firmware (e.g. S9 running BOS 22.08 or earlier) uses a **GraphQL API** at `/graphql` — those miners rely on pyasic only and do not benefit from the direct API sensors below.

**Additional sensors beyond pyasic:**

| Sensor | Source |
|---|---|
| Per-board Inlet Temperature | `GET /api/v1/miner/hw/hashboards` → `lowest_inlet_temp` |
| Per-board Outlet Temperature | `GET /api/v1/miner/hw/hashboards` → `highest_outlet_temp` |
| Per-board Real Hashrate | `GET /api/v1/miner/hw/hashboards` → `stats.real_hashrate.last_5m` |
| Ideal Hashrate (total) | Sum of `stats.nominal_hashrate` across all boards |
| Best Share | `GET /api/v1/miner/stats` → `miner_stats.best_share` |
| Found Blocks | `GET /api/v1/miner/stats` → `miner_stats.found_blocks` |

**Hydro miner support (e.g. S21e Hyd.):**
- Fan entities are automatically suppressed for hydro-cooled models (no fans)
- Inlet and outlet water temperatures exposed per hashboard

**Supported API versions:** v1.2.0, v1.3.0 — see [docs/bos-api/README.md](docs/bos-api/README.md)

---

### VNish Firmware — REST API

Direct integration with the VNish REST API (`http://<miner>/api/v1`).

**Additional sensors beyond pyasic:**

| Sensor | Source |
|---|---|
| Per-board PCB Temp (max) | `GET /api/v1/summary` → `miner.chains[].pcb_temp.max` |
| Per-board PCB Temp (min) | `GET /api/v1/summary` → `miner.chains[].pcb_temp.min` |
| Per-board Chip Temp (max) | `GET /api/v1/summary` → `miner.chains[].chip_temp.max` |
| Per-board Chip Temp (min) | `GET /api/v1/summary` → `miner.chains[].chip_temp.min` |
| Best Share | `GET /api/v1/summary` → `miner.best_share` |
| Found Blocks | `GET /api/v1/summary` → `miner.found_blocks` |
| Active Preset | `GET /api/v1/settings` → `miner.overclock.preset` |

**Auth:** `POST /api/v1/unlock` with `{"pw": "<password>"}` → returns `token`. Used as `Authorization: <token>` header.

---

### Avalon Nano 3s — CGMiner API

Direct CGMiner API communication on port 4028.

- **Work Mode Control** — Switch between Low / Mid / High mining modes
- **LED Control** — RGB color picker and effect selection (Stay, Flash, Breathing, Loop)
- **Best Share** — Auto-scaling display (K/M/G/T/P/E/Z)
- **Found Blocks** — Mining statistics

---

### Whatsminer M30S — pyasic + Auto-Enable

- **Power Limit Control** — Fixed power limit slider that was resetting after 2 seconds ([#1](https://github.com/tntvlad/hass-miner/issues/1))
- **Auto API Enable** — Automatically enables the Whatsminer write API when "can't access write cmd" error occurs
- **RPC Password Support** — Configure RPC password during setup for encrypted API commands

> If auto-enable fails, manually enable the API using WhatsMinerTool: Remote Ctrl → Miner API Switch → Enable

---

### Support for:

- Antminers
- Whatsminers
- Avalonminers
- Innosilicons
- Goldshells
- Auradine
- BitAxe
- IceRiver
- Hammer
- Braiins Firmware
- Vnish Firmware
- ePIC Firmware
- HiveOS Firmware
- LuxOS Firmware
- Mara Firmware

[Full list of supported miners](https://pyasic.readthedocs.io/en/latest/miners/supported_types/).

**This component will set up the following platforms -**

| Platform | Description               |
| -------- | ------------------------- |
| `sensor` | Show info from miner API. |
| `number` | Set Power Limit of Miner. |
| `switch` | Switch Miner on and off   |

**This component will add the following services -**

| Service           | Description                          |
| ----------------- | ------------------------------------ |
| `reboot`          | Reboot a miner by IP                 |
| `restart_backend` | Restart the backend of a miner by IP |

## Installation

### Option 1: Manual HACS Installation

1. Open HACS in Home Assistant
2. Click the three dots menu (⋮) in the top right
3. Select **Custom repositories**
4. Add `tntvlad/hass-miner` with Category: **Integration**
5. Click **Add**
6. Search for "Miner" in HACS and download

### Option 2: One-Click Install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tntvlad&repository=hass-miner&category=integration)

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

## Credits

This project was generated from [@oncleben31](https://github.com/oncleben31)'s [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.

Code template was mainly taken from [@Ludeeus](https://github.com/ludeeus)'s [integration_blueprint][integration_blueprint] template.

Miner control and data is handled using [@UpstreamData](https://github.com/UpstreamData)'s [pyasic](https://github.com/UpstreamData/pyasic).

## Known Issues (Beta)

### Avalon Nano 3s

- **LED Brightness** — Brightness slider not working correctly (WRGB format investigation needed)
- **Mining Enable/Disable** — `ascenable`/`ascdisable` command format needs investigation
- **Restart Function** — Miner restart service not yet implemented

### Whatsminer M30S

- **Chip Temperature** — May show "unknown" on some firmware versions (investigating)

---

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[black]: https://github.com/psf/black
[black-shield]: https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/tntvlad/hass-miner.svg?style=for-the-badge
[commits]: https://github.com/tntvlad/hass-miner/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[exampleimg]: example.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/tntvlad/hass-miner.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40tntvlad-blue.svg?style=for-the-badge
[pre-commit]: https://github.com/pre-commit/pre-commit
[pre-commit-shield]: https://img.shields.io/badge/pre--commit-enabled-brightgreen?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/tntvlad/hass-miner.svg?style=for-the-badge
[releases]: https://github.com/tntvlad/hass-miner/releases
[user_profile]: https://github.com/tntvlad
