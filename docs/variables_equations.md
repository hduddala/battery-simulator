<!-- Copied from: battery sim/Ivonne/docs/variables_equations.md (Ivonne Zhang documentation). -->

# Variables Documentation

## Note on naming

Ivonne’s document uses prefixes **`P_sha1_*`** / **`P_sha2_*`**. The merged **`battery_sim`** codebase and **`SIMULATOR.md`** use **`P_mic`**, **`P_proc_shaI_*`**, **`P_proc_shaII_*`**, etc. The physics roles align; see **`SIMULATOR.md`** for JSON ↔ equation mapping.

---

## 1. Node Types

### Shaman I (Sensor Node)
- Detects events via microphone
- Processes locally (ESP32)
- Sends data via WiFi to parent Shaman II
- Does NOT receive or relay

### Shaman II (Relay Node)
- Receives from children (WiFi / LoRa)
- Processes data
- Forwards data via LoRa toward command center

---

## 2. Topology Variables

- node_id
- node_type ∈ {shaman_I, shaman_II, command_center}
- x_coord, y_coord
- parent_id
- children_ids
- rank (distance to gateway)
- link_type ∈ {wifi, lora}

---

## 3. Battery Variables

- V: battery voltage (V)
- Q: battery capacity (Ah)
- E_battery = V × Q (Wh)

For each node:
- E_remaining(t)
- battery_percent(t)
- t_death
- is_alive(t)

---

## 4. Shaman I Variables

### Power
- P_sha1_mic_on
- P_sha1_mic_off
- P_sha1_cpu_active
- P_sha1_cpu_sleep
- P_sha1_wifi_tx

### Timing
- t_sha1_proc
- t_sha1_wifi_tx

### Event Counts
- n_sha1_local_events

---

## 5. Shaman II Variables

### Power
- P_sha2_proc_active
- P_sha2_proc_sleep
- P_sha2_controller_active
- P_sha2_controller_sleep
- P_sha2_lora_tx
- P_sha2_lora_rx
- P_sha2_wifi_rx
- P_sha2_backoff

### Timing
- t_sha2_proc
- t_sha2_lora_tx
- t_sha2_lora_rx
- t_sha2_wifi_rx
- t_backoff

### Event Counts
- n_sha2_local
- n_sha2_received_wifi
- n_sha2_received_lora
- n_sha2_forwarded
- n_sha2_retries

---

## 6. Communication Variables

- frames_per_hop
- link_type (wifi or lora)
- hop_count

---

## 7. Event Variables

From AI pipeline:

- event_id
- node_id
- event_time
- event_type

---

## 8. Simulation Variables

- T_total (simulation duration)
- Δt (time step OR event-driven)
- num_runs



# Energy Equations

## 1. General Energy Model

Energy = Power × Time

E = P × t

---

## 2. Shaman I Energy

E_ShaI = E_idle + E_proc + E_wifi_tx

### Idle Energy
E_idle = (P_sha1_cpu_sleep + P_sha1_mic_on) × T_idle

### Processing Energy
E_proc = n_sha1_local_events × P_sha1_cpu_active × t_sha1_proc

### WiFi Transmission
E_wifi_tx = n_sha1_local_events × P_sha1_wifi_tx × t_sha1_wifi_tx

---

## 3. Communication: Shaman I → Shaman II

### Sender (Shaman I)
E_tx_wifi = P_sha1_wifi_tx × t_sha1_wifi_tx

### Receiver (Shaman II)
E_rx_wifi = P_sha2_wifi_rx × t_sha2_wifi_rx

---

## 4. Shaman II Energy

E_ShaII = E_idle + E_wifi_rx + E_proc + E_lora_tx + E_retry

### Idle Energy
E_idle = (P_sha2_controller_sleep + P_sha2_proc_sleep + P_sha2_lora_rx) × T_idle

### WiFi Receive
E_wifi_rx = n_sha2_received_wifi × P_sha2_wifi_rx × t_sha2_wifi_rx

### Processing
E_proc = n_sha2_forwarded × P_sha2_proc_active × t_sha2_proc

### LoRa Transmission
E_lora_tx = n_sha2_forwarded × P_sha2_lora_tx × t_sha2_lora_tx × frames_per_hop

### Retry Energy
E_retry = n_sha2_retries × (
    P_sha2_lora_tx × t_sha2_lora_tx +
    P_sha2_backoff × t_backoff
)

---

## 5. Battery Model

E_remaining(t) = E_battery - E_consumed(t)

battery_percent(t) = 100 × E_remaining / E_battery

---

## 6. Death Condition

t_death = first time when E_remaining ≤ 0

If E_remaining ≤ 0:
    node is dead
    stop all future activity
