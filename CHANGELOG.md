# Changelog

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
