"""Analyze relationships between BOS hashboard temps and water circuit temps.

Data captured from BOS fleet dashboard 'Hash Boards' table for an
Antminer S21e Hydro at 192.168.1.245 (firmware 26.04-plus).

UI columns -> API fields (from /api/v1/miner/hw/hashboards):
  Max Board Temp -> board_temp.degree_c
  Max Chip Temp  -> highest_chip_temp.temperature.degree_c
  Inlet Temp     -> lowest_inlet_temp.degree_c
  Outlet Temp    -> highest_outlet_temp.degree_c
  Water Inlet/Outlet -> NOT exposed by API
"""
import statistics

boards = [
    {"id": 1, "board": 52.2, "chip": 67.2, "inlet": 44.3, "outlet": 52.2, "w_inlet": 35.0, "w_outlet": 45.0},
    {"id": 2, "board": 51.9, "chip": 66.9, "inlet": 43.6, "outlet": 51.9, "w_inlet": 36.0, "w_outlet": 44.5},
    {"id": 3, "board": 53.8, "chip": 68.8, "inlet": 44.5, "outlet": 53.8, "w_inlet": 35.5, "w_outlet": 45.5},
]

print("=== Raw ===")
for b in boards:
    print(b)

print()
print("=== Differences ===")
print(f"{'B':<3} {'chip-board':<11} {'outlet-board':<13} {'board-inlet':<12} {'w_out-inlet':<12} {'w_in-inlet':<11} {'w_out-w_in':<10}")
for b in boards:
    print(
        f"{b['id']:<3} "
        f"{b['chip']-b['board']:<11.1f} "
        f"{b['outlet']-b['board']:<13.1f} "
        f"{b['board']-b['inlet']:<12.1f} "
        f"{b['w_outlet']-b['inlet']:<12.1f} "
        f"{b['w_inlet']-b['inlet']:<11.1f} "
        f"{b['w_outlet']-b['w_inlet']:<10.1f}"
    )

print()
print("=== Consistency (low stdev = strong predictor) ===")
candidates = {
    "w_out = inlet + C":   [b["w_outlet"] - b["inlet"]    for b in boards],
    "w_out = board - C":   [b["w_outlet"] - b["board"]    for b in boards],
    "w_out = chip  - C":   [b["w_outlet"] - b["chip"]     for b in boards],
    "w_in  = inlet - C":   [b["w_inlet"]  - b["inlet"]    for b in boards],
    "w_in  = board - C":   [b["w_inlet"]  - b["board"]    for b in boards],
    "w_in  = chip  - C":   [b["w_inlet"]  - b["chip"]     for b in boards],
    "w_in  = w_out - C":   [b["w_inlet"]  - b["w_outlet"] for b in boards],
}
for name, vals in candidates.items():
    avg = statistics.mean(vals)
    stdev = statistics.stdev(vals)
    print(f"  {name:<22}: C={avg:+6.2f}  stdev={stdev:.2f}  vals={[round(v,1) for v in vals]}")

print()
w_out_off = statistics.mean([b["w_outlet"] - b["inlet"] for b in boards])
w_in_off  = statistics.mean([b["w_inlet"]  - b["inlet"] for b in boards])
print(f"Best fit:  w_out ≈ inlet_chip {w_out_off:+.2f}   |   w_in ≈ inlet_chip {w_in_off:+.2f}")
print()
for b in boards:
    pwo = b["inlet"] + w_out_off
    pwi = b["inlet"] + w_in_off
    print(f"Board {b['id']}: w_out actual={b['w_outlet']:.1f} pred={pwo:.2f} err={pwo-b['w_outlet']:+.2f}  |  w_in actual={b['w_inlet']:.1f} pred={pwi:.2f} err={pwi-b['w_inlet']:+.2f}")
