# Battery simulator

Core handoff files:

| File | Role |
|------|------|
| **`battery_simulator.py`** | All logic + CLI (`python battery_simulator.py …`) |
| **`scenario.json`** | **Default** demo: one relay hop, **72 h**, 42 events — easiest charts |
| **`scenario_spec_complete.json`** | **Spec-heavy** dataset: **two relay hops** (WiFi → LoRa → LoRa), **96 h**, 52 events, every §2 field + `controllerActive` / extra components |
| **`SIMULATOR.md`** | This document — math, variables, where outputs live |

Energy is in **watt-hours (Wh)**. Power **P** [W], time **t** [s]: **Wh = P × t / 3600**.

### Repository handoff (supervisor direction)

Single combined program suitable for its **own small repository**: one Python module, documented scenarios, and this guide.

---

## Where inputs and outputs live

Nothing magic happens in this folder until you **run** the script. Before that, only **JSON inputs** exist; **battery %** and **timestamps** are **created** when you run.

| What you want | Where it is |
|----------------|-------------|
| **How long the run lasts** | Input: `duration_hours` in the scenario JSON (e.g. **72** or **96**). |
| **How often SOC is sampled** | Input: `time_step_seconds` (e.g. **3600** = hourly points). |
| **When each detection happens** | Input: `events[]`, each **`time`** is **seconds from the start** (not a calendar clock). |
| **Battery capacity (E_battery)** | Input: `shaman_i.batteryLife` / `battery_wh`, `shaman_ii.batteryLife` / `battery_wh`. |
| **All power/timing constants** | Input: `shaman_i`, `shaman_ii`, `radio` blocks (see mapping table below). |
| **Battery % over time (results)** | Output: **`output/full_result.json`** → `nodes.<node_id>.series.battery_percent` and `.time_hours` (same for custom `--out-dir`). |
| **Final battery % one-liner** | Output: **`RUN_SUMMARY.txt`** or `full_result.json` → `nodes.<id>.summary.final_battery_percent`. |
| **CSV for Excel/plots** | Output: **`combined_battery_timeseries.csv`** — columns include `time_hours`, `battery_percent`, `node_id`. |
| **Computed LoRa frame time (t_tx_lora)** | Not in scenario; output: **`full_result.json`** top-level **`radio.airtime_per_frame_ms`** after a run. |

**Why `scenario.json` was the default:** the CLI uses `--scenario`’s default path (`scenario.json`) so `python battery_simulator.py --overwrite` works with zero extra flags. That does **not** mean other datasets are wrong — pass **`--scenario scenario_spec_complete.json`** for the fuller mesh.

---

## How to run

**Python 3.10+.** From this folder:

```bash
# Default 72 h demo → writes folder output/
python battery_simulator.py --overwrite
```

Spec-complete **two-hop** dataset → separate output folder (recommended):

```bash
python battery_simulator.py --scenario scenario_spec_complete.json --out-dir output_spec --overwrite
```

Optional virtualenv (no third-party packages required):

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
python battery_simulator.py --overwrite
```

Custom scenario / output directory:

```bash
python battery_simulator.py --scenario ./my.json --out-dir ./output --overwrite
```

**Regression:** `python battery_simulator.py --verify` (uses a minimal payload embedded in `battery_simulator.py`, not a separate file).

**Outputs** (folder `output/` by default, recreated when `--overwrite`):

| File | Use |
|------|-----|
| `RUN_SUMMARY.txt` | Quick numbers |
| `full_result.json` | API-shaped payload + time series |
| `combined_battery_timeseries.csv` | Plot `battery_percent` vs `time_hours` per `node_id` |
| `synthetic_events_log.csv` | Event list for this run |

You may keep a local `.venv` here if you use one — it is **not** part of the handoff bundle.

---

## Scenario JSON (test data)

**Top-level** keys whose names start with `_` (e.g. `_readme`, `_documentation`, `_event_summary`) are **stripped** before the run — they are documentation only.

Inside `shaman_i`, `shaman_ii`, `radio`, or each node object, extra `_…` fields are **harmless**: loaders only read known keys; use them for comments and spec cross-references (see bundled **`scenario.json`**).

| Section | Contents |
|---------|-----------|
| `duration_hours`, `time_step_seconds` | **T** — simulation horizon and timestep (`time_step_seconds` ↔ timestep for SOC sampling) |
| `gateway_externally_powered` | Command Center externally powered → **zero** drain when true |
| `tx_only_if_confirmed` | If true, only `"confirmed": true` events trigger uplink + relay chain |
| `shaman_i` | Sensor — **`batteryLife`** / **`battery_wh`** (**E_battery** Wh); **`components`** (Ivonne-style mA/V or W) and/or explicit **`P_*`**, **`t_*`** scalars |
| `shaman_ii` | Relay — same pattern; includes **`P_wifi_rx`**, **`t_rx_wifi`**, **`t_proc_shaII`**, **`P_backoff`**, **`t_backoff`** |
| `radio` | **`frames_per_hop`**; **SF/BW/payload** → **`t_tx_lora`** computed inside the engine (`full_result.json` reports **`airtime_per_frame_ms`**) |
| `nodes` | Topology — **`node_id`**, **`node_type`** or **`role`**, **`parent_id`**, **`child_ids`** |
| `events` | Timeline — **`node_id`**, **`time`** [s], **`confirmed`**, **`event_type`** (labels are synthetic; only counts matter for energy) |

### Bundled `scenario.json` ↔ Energy Spec variables

Use this table to audit **`scenario.json`** against the team Energy Spec (§2 naming):

| Spec §2 variable | JSON location |
|------------------|----------------|
| **E_battery** | `shaman_i.batteryLife` / `battery_wh`; `shaman_ii.batteryLife` / `battery_wh` |
| **P_mic**, **P_mic_off**, **P_proc_shaI_active**, **P_proc_shaI_sleep**, **P_wifi_tx** | `shaman_i` scalars (or derived from `components`) |
| **t_tx_wifi**, **t_proc_shaI** | `shaman_i.t_tx_wifi`, `shaman_i.t_proc_shaI` |
| **P_proc_shaII_***, **P_controller_***, **P_lora_tx**, **P_lora_rx**, **P_wifi_rx**, **P_backoff** | `shaman_ii` scalars (or `components`) |
| **t_proc_shaII**, **t_rx_wifi**, **t_backoff** | `shaman_ii` scalars; **t_tx_lora** is **computed** from `radio` |
| **t_rx_lora** (spec) | In code, LoRa RX duration uses **`airtime_per_frame_s()`** per packet (same airtime as TX frame) |
| **frames_per_hop**, **SF**, BW-related terms | `radio.frames_per_hop`, `radio.spreading_factor`, `radio.bandwidth_hz`, … |
| **n_retries** (mean-field) | `radio.avg_retries_per_tx` scales §3.2 **E_retry** |

Bundled **`scenario.json`** lists **every scalar used in §3.1–§3.2 today**, alongside **`components{}`** for Ivonne-style GUIs. **`scenario_spec_complete.json`** adds **two-hop relays** (R2 → R1 → CMD1), **`controllerActive`** in components, extra Shaman‑I component slots (`micSleep`, `sleep`), **96 h** horizon, **30‑minute** timestep, and `_battery_variables_doc` (**V/Q** ↔ **Wh** notes per §2.3).

---

## What the simulator does

**Inputs:** topology, power/radio parameters, event timeline.

**Loop:** For each time step, add **baseline** Wh for every finite node; for each event in that interval, apply WiFi TX on the sensor then walk **parent → … → command**, applying WiFi RX / LoRa RX, processor spike, LoRa TX (+ optional retry energy).

**Outputs:** Per-node SOC series and **`summary`** metrics (see bottom).

---

## Roles

| Role | Model behaviour |
|------|-----------------|
| **sensor** | Baseline `P_proc_shaI_active + P_mic`; per-event **WiFi TX** |
| **relay** | Baseline `P_controller_sleep + P_lora_rx + P_proc_shaII_sleep`; RX/process/TX per packet |
| **command** | Like relay for reception unless **externally powered** → zero drain |

---

## Variables (team spec)

### Shaman I — power

`P_mic`, `P_mic_off`, `P_proc_shaI_active`, `P_proc_shaI_sleep`, `P_wifi_tx`

### Shaman I — timing

`t_tx_wifi`, `t_proc_shaI`

### Shaman II — power

`P_proc_shaII_*`, `P_controller_*`, `P_lora_tx`, `P_lora_rx`, `P_wifi_rx`, `P_backoff`

### Shaman II — timing

`t_proc_shaII`, `t_rx_wifi`, `t_backoff`; **`t_tx_lora`** from Semtech formula (`RadioConfig.airtime_per_frame_s`)

### Battery / protocol

`E_battery` ↔ `battery_wh` / `batteryLife`; `frames_per_hop`; LoRa SF/BW/payload

### Counters

`n_local`, `n_received_wifi`, `n_received_lora`, `n_received`, `n_forward` (= `n_local + n_received`)

---

## Energy equations

### Shaman I

`E_ShaI = E_baseline + E_tx`

- `E_baseline = (P_proc_shaI_active + P_mic) × T`
- `E_tx = n_local × P_wifi_tx × t_tx_wifi × frames_per_hop` (applied as one burst per event)

### Shaman II

`E_ShaII = E_baseline + E_rx_wifi + E_rx_lora + E_tx + E_process + E_retry`

- Baseline: `(P_controller_sleep + P_lora_rx + P_proc_shaII_sleep) × T`
- Rx / process / Tx terms match packet counts along the tree
- **Retries:** mean-field `avg_retries_per_tx` per LoRa forward hop

### Per-event chain

Sensor WiFi burst → parent WiFi RX + process → each ancestor LoRa RX + process + LoRa TX until gateway.

---

## Implementation notes

Extra variables (`P_mic_off`, sleep powers, `t_proc_shaI`, `P_controller_active`) exist in config for spec completeness; **baseline equations above** describe what is accumulated today.

---

## `summary` fields (per node in `full_result.json`)

| Field | Meaning |
|-------|---------|
| `energy_consumed_wh`, `energy_remaining_wh` | Totals |
| `percent_used`, `percent_remaining`, `final_battery_percent` | SOC |
| `average_power_w` | `consumed / duration_hours` |
| `projected_total_life_hours` | `E_battery / average_power` |
| `projected_remaining_life_hours` | `E_remaining / average_power` |
| `projected_life_hours` | Alias of `projected_total_life_hours` |
| `n_retries_effective` | Mean-field retry counter |

---

## Source code

All logic is in **`battery_simulator.py`**. Import `run_from_dict`, `BatterySimulator`, `SimulationConfig` from there in your own scripts.
