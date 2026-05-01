<!-- Copied from: battery sim/Ivonne/docs/simulation_loop.md (Ivonne Zhang simulation loop design). -->

# Simulation Loop Design

The **battery simulator** CLI applies this loop at discrete **`time_step_seconds`** steps; see **`battery_simulator.py`** (`BatterySimulator.run`) and **`SIMULATOR.md`** for exact energy terms used in the merged implementation.

---

## 1. Inputs

- Topology JSON (nodes + edges)
- Node configurations (power, battery)
- Event timeline JSON
- Simulation parameters (T_total, num_runs)

---

## 2. Preprocessing

- Normalize all power inputs to Watts
- Build node objects:
    - type
    - battery
    - parent/children
- Load event timeline
- Sort events by time

---

## 3. Initialization

For each node:
- E_remaining = E_battery
- is_alive = True
- initialize time-series arrays

---

## 4. Main Simulation Loop

FOR each run:
    FOR each time step or event:

        IF node is dead:
            skip

        # 1. Idle energy
        apply baseline power consumption

        # 2. Event occurs (Shaman I)
        IF event at node:
            - apply processing energy
            - apply WiFi TX energy

        # 3. Parent node (Shaman II)
            - apply WiFi RX energy
            - apply processing energy
            - apply LoRa TX energy

        # 4. Retry (if needed)
            - apply retry + backoff energy

        # 5. Update battery
        E_remaining -= energy_used

        # 6. Check death
        IF E_remaining ≤ 0:
            mark node dead
            record t_death

        # 7. Save outputs
        record battery level at time t

---

## 5. Output

For each node:
- time array
- battery remaining (Wh)
- battery %
- death time

Output format:
- CSV OR JSON

Example:
{
  node_id: "S9",
  time: [...],
  battery_percent: [...],
  death_time: ...
}
