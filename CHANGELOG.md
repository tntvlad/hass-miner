# Changelog

## v1.4.0-beta9 (2026-10-14)

- **Configurable refresh interval** — the miner's **Configure** dialog (Settings → Devices & Services → miner → Configure) now exposes a *Refresh interval* in seconds (5–3600, default 60), replacing the hard-coded 60 s poll. Every entity, including board and chip temperatures, refreshes on this cadence. The setting is per miner and saving it reloads the config entry immediately — no restart needed.

## v1.4.0-beta8 (2026-08-22)

- **Gentle retry pass for WiFi miners** — the BitAxe/NerdMiner are WiFi-only ESP32 devices whose tiny stacks drop probes while a 254-host sweep saturates them (found on only 1 of 4 scans). Hosts that stay *silently* unresponsive during the main sweep are now re-probed calmly seconds later, when they answer reliably. Definitively-refused hosts are not retried, keeping the extra time to a few seconds.
- Clearer scan summary lines: per-subnet retry recoveries plus totals for HTTP-fallback identifications.

## v1.4.0-beta7 (2026-08-22)

- **Reliable BitAxe discovery** — esp-miner devices reset bare TCP connections that carry no data, so both pyasic's probe and a plain connect test lost them intermittently (found on 1 of 4 scans). The fallback now sends a real HTTP GET; a connection with a request in flight is served normally, making detection deterministic.
- **Unidentified-device banner** — hosts that answer HTTP but which pyasic cannot identify log the first bytes of their response (e.g. NerdMiner firmware pages), providing exact evidence for adding support.

## v1.4.0-beta6 (2026-08-22)

- **Stronger BitAxe/NerdMiner recovery** — the port-80 liveness check now runs for every host pyasic cannot identify, instead of only after a specific failure mode; anything serving HTTP is explicitly identified via pyasic.
- **Decisive scan diagnostics** — already-configured miner IPs get a detailed probe line (`Probe detail for <ip>: pyasic=..., tcp80=...`), so if a known-live miner is still missed the next log shows exactly which signal failed.

## v1.4.0-beta5 (2026-08-22)

- **Scan diagnostics** — scan log lines are now stamped with the integration version and report port-80 recheck statistics and a per-miner summary, so submitted logs unambiguously show which build ran and whether the BitAxe/NerdMiner fallback engaged. (HACS updates only take effect after restarting Home Assistant - if you updated without a restart you were still on the previous version.)

## v1.4.0-beta4 (2026-08-22)

- **Discovery now finds BitAxe / NerdMiner** — esp-miner devices accept the scan's TCP probe and then reset the connection, which pyasic misreads as "refused" and skips; the Gamma at 192.168.1.92 was therefore never offered despite answering every poll. After pyasic's probe reports nothing, the integration now re-checks port 80 itself (tolerating the reset) and identifies the device explicitly.
- **Progress screen text** — "Scanning your network for miners…" shows next to the spinner (hard-refresh the browser with Ctrl+F5 if HA still shows a bare circle - translations are cached).

## v1.4.0-beta3 (2026-08-21)

- **Fix scan flow stalling / orphaned scans** — the progress screen now passes its backing task to Home Assistant (`progress_task`), as current HA requires. Without it HA logged a warning and the scan could silently die when the dialog was dismissed, leaving "no miner found".
- **Hardened sweeps** — host probes run through a bounded semaphore (pyasic skips its own by default, so large ranges could open thousands of simultaneous connections) and each probe is exception-isolated: one misbehaving host can no longer abort or zero out a whole subnet's results.
- **CIDR in the IP field** — typing a range like `192.168.1.0/24` directly into the IP field now starts a scan of that range; invalid/oversized ranges show a clear error instead of "Unable to connect".

## v1.4.0-beta2 (2026-08-21)

- **Fix scan crash / HA restart** — discovery no longer scans internal networks (docker bridges, Tailscale/CGNAT, link-local, loopback) or any range larger than 1024 addresses; sweeping those could exhaust memory and take Home Assistant down. Malformed adapter data and per-subnet failures are now contained and logged instead of surfacing as "Unknown error occurred".
- **Fix discovery on Home Assistant OS** — HAOS runs HA in an internal container network, so adapter-derived subnets never contain your LAN. Candidate ranges are now derived from already-configured miner IPs as well, and the scan screen gained an optional **Network range** field (CIDR, e.g. `192.168.1.0/24`) to point the scan anywhere.
- **Proper progress screen** — scanning shows a real progress page instead of a spinning submit button.
- **Faster sweeps** — ping timeout is temporarily lowered while scanning.

## v1.4.0-beta1 (2026-08-21)

- **Network scan-for-miners** — leave the IP field empty during setup and the integration scans the subnet(s) Home Assistant is connected to; discovered miners are offered in a dropdown to pick from. Scan is bounded by a 120 s timeout and can be re-run if nothing is found.
- **Duplicate protection** — config entries now get a unique ID (miner MAC address, IP fallback), so the same miner can no longer be added twice.
- **README refresh** — documents all entity platforms and services, direct vendor integrations (BOS REST + gRPC, VNish throttle/presets, BitAxe, Avalon Nano full mode) and the offline-tolerant setup behavior.

## v1.3.9-beta6 (2026-06-15)

- **VNish preset select: respect "Don't raise preset above" limit** — presets whose wattage exceeds `miner.overclock.preset_switcher.top_preset` (set in VNish UI under /mining/performance) are now hidden from the dropdown, so users cannot accidentally pick a preset above their own safety ceiling.
- **Fix: remove duplicate "disabled" entry** — the synthetic "disabled" option added in beta5 was duplicating the "Disabled" preset that the VNish API already returns on its own.

## v1.3.9-beta5 (2026-06-14)

- **VNish preset select: "disabled" option** — adds a synthetic "disabled" entry to the preset dropdown so you can switch back from a named preset to no-preset operation directly from HA, without going into the VNish web UI.

## v1.3.9-beta4 (2026-06-14)

- **VNish preset select: retry on reconnect** (#34) — if the miner was offline when the preset list was first fetched, it now retries automatically once the coordinator detects the miner is back online.
- **Fix offline startup loop** (#36) — coordinators no longer get stuck in a retry loop when the miner is powered off at integration setup time.

## v1.3.9-beta3 (2026-06-11)

- **Offline-tolerant setup** (#31): powered-off miners no longer end in "retrying setup" — entities are created from a cached device profile and show *unavailable* until the miner returns.
- **VNish throttle control** (#20, #35): new number entity (20–100 %, 5 % steps) to dim mining power without stopping the miner. VNish ≥ 1.3.3 only; ~80 s to take effect.
- **Quieter failure handling** (#29): single flaky polls no longer log ERRORs or flap entities; hard powered-off miners now go *unavailable* after ~4 min instead of showing frozen data forever.
- **Stable VNish board temps** (#30): transient temperature-fetch errors keep last known values instead of going *unknown*.

## v1.3.9-beta2 (2026-06-09)

- Water inlet/outlet temperature sensors for VNish hydro miners (#28)
