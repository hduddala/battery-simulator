# Digital Twin Energy Model — Variable Reference

**Scope of this document:** The battery energy simulator models power draw and battery depletion across a sensor network over time. It does **not** model RF path-loss, packet collision probability, channel fading, or camera capture. All energy is computed from user-supplied power constants and a discrete time-step loop.

---

## Quick-Reference Table

All symbols used in this document, in one place. Sections below give full definitions and equations.

| Symbol | Description | Unit | Input or Computed |
|---|---|---|---|
| $G = (\mathcal{N}, \mathcal{E})$ | Network graph | — | Input |
| $(x_i, y_i)$ | Node coordinates | — | Input |
| $p(i)$ | Parent node of $i$ | — | Input |
| $\mathcal{C}(i)$ | Children of node $i$ | — | Input |
| $r_i$ | Hop rank (hops to command center) | hops | Input |
| $E_i^{\max}$ | Battery capacity | Wh | Input |
| $E_i(t)$ | Remaining battery energy at time $t$ | Wh | Computed |
| $B_i(t)$ | Battery percentage at time $t$ | % | Computed |
| $t_i^{\text{death}}$ | Time of battery depletion | s | Computed |
| $a_i(t)$ | Node alive indicator | 0 or 1 | Computed |
| $T_{\text{total}}$ | Total simulation duration | s | Input |
| $\Delta t$ | Simulation time step | s | Input |
| $P^{(I)}_{\text{proc,act}}$ | Shaman I: processor active power | W | Input |
| $P^{(I)}_{\text{proc,slp}}$ | Shaman I: processor sleep power | W | Input |
| $P^{(I)}_{\text{wifi,tx}}$ | Shaman I: WiFi transmit power | W | Input |
| $P^{(I)}_{\text{mic,listen}}$ | Shaman I: microphone listening power | W | Input |
| $P^{(I)}_{\text{mic,off}}$ | Shaman I: microphone off-state power | W | Input |
| $t^{(I)}_{\text{proc}}$ | Shaman I: time to process one event | s | Input |
| $t^{(I)}_{\text{wifi,tx}}$ | Shaman I: WiFi transmit duration per frame | s | Input |
| $n^{(I)}_{\text{local}}$ | Shaman I: events detected locally this step | count | Computed |
| $n^{(I)}_{\text{tx}}$ | Shaman I: messages transmitted to parent | count | Computed |
| $P^{(II)}_{\text{proc,act}}$ | Shaman II: processor active power | W | Input |
| $P^{(II)}_{\text{proc,slp}}$ | Shaman II: processor sleep power | W | Input |
| $P^{(II)}_{\text{ctrl,act}}$ | Shaman II: controller active power | W | Input |
| $P^{(II)}_{\text{ctrl,slp}}$ | Shaman II: controller sleep power | W | Input |
| $P^{(II)}_{\text{lora,tx}}$ | Shaman II: LoRa transmit power | W | Input |
| $P^{(II)}_{\text{lora,rx}}$ | Shaman II: LoRa receive power | W | Input |
| $P^{(II)}_{\text{wifi,rx}}$ | Shaman II: WiFi receive power (from sensors) | W | Input |
| $P^{(II)}_{\text{backoff}}$ | Shaman II: power during retry backoff | W | Input |
| $t^{(II)}_{\text{proc}}$ | Shaman II: time to process one packet | s | Input |
| $t^{(II)}_{\text{lora,tx}}$ | Shaman II: LoRa airtime per frame | s | **Computed** from radio params |
| $t^{(II)}_{\text{wifi,rx}}$ | Shaman II: WiFi receive duration per frame | s | Input |
| $t^{(II)}_{\text{backoff}}$ | Shaman II: backoff wait duration per retry | s | Input |
| $n^{(II)}_{\text{local}}$ | Shaman II: events generated locally | count | Computed |
| $n^{(II)}_{\text{rx,wifi}}$ | Shaman II: packets received via WiFi (from sensors) | count | Computed |
| $n^{(II)}_{\text{rx,lora}}$ | Shaman II: packets received via LoRa (from relay children) | count | Computed |
| $n^{(II)}_{\text{fwd}}$ | Shaman II: total packets forwarded upward | count | Computed |
| $\bar{r}_{\text{tx}}$ | Mean retries per successful LoRa TX (fractional) | — | Input |
| $T^{(II)}_{\text{idle}}$ | Shaman II: time without active packet processing | s | Computed |
| $f_{\text{hop}}$ | Frames per transmission hop | — | Input |
| SF | LoRa spreading factor | — | Input |
| BW | LoRa bandwidth | Hz | Input |
| $\ell$ | LoRa payload size | bytes | Input |
| CR | LoRa coding rate | — | Input |
| $N_{\text{pre}}$ | LoRa preamble length | symbols | Input |

---

## 1. System Overview

The network is a directed tree graph:

$$G = (\mathcal{N}, \mathcal{E})$$

- $\mathcal{N}$: set of all nodes
- $\mathcal{E}$: directed communication links

Each node has a fixed role:

$$\text{type}(i) \in \{\text{Shaman I},\ \text{Shaman II},\ \text{Command Center}\}$$

Data always flows toward the root (command center). The command center is assumed to be externally powered and draws no battery energy in the model.

---

## 2. Topology Variables

| Symbol | Description | Type |
|---|---|---|
| $(x_i, y_i)$ | Coordinates of node $i$ (used for layout) | Input |
| $p(i)$ | Parent node of $i$ — the node it forwards data to | Input |
| $\mathcal{C}(i)$ | Set of child nodes of $i$ — nodes that send data to it | Input |
| $r_i$ | Rank of node $i$: number of hops to the command center | Input |

Data flow direction:

$$i \rightarrow p(i)$$

The graph must be a directed acyclic tree. Each node has exactly one parent (except the command center, which has none). Cycles are rejected at validation time.

---

## 3. Battery Variables

$$E_i^{\max}$$

**Maximum battery capacity of node $i$.**
- Unit: **Wh** (watt-hours). This is a direct input — the simulator does not take voltage and capacity-Ah separately and multiply them.
- Code field: `ShamanIConfig.battery_wh`, `ShamanIIConfig.battery_wh`

**`battery_wh`** — Usable battery energy available to the node, measured in watt-hours under real load. This is the number you would read from a datasheet after accounting for discharge efficiency — not the nameplate cell capacity. The simulator treats it as $E_i^{\max}$ and depletes it directly each step.

$$E_i(t) = \max\!\left(0,\ E_i^{\max} - \sum_{\tau \le t} E_i^{\text{used}}(\tau)\right)$$

**Remaining battery energy at time $t$.** Decrements each time step by the energy consumed that step.

$$B_i(t) = \frac{E_i(t)}{E_i^{\max}} \cdot 100$$

**Battery percentage at time $t$.**

$$t_i^{\text{death}} = \min \{ t \mid E_i(t) \le 0 \}$$

**Time of battery depletion.** `None` if the node survives the full simulation.

$$a_i(t) =
\begin{cases}
1, & E_i(t) > 0 \\
0, & E_i(t) \le 0
\end{cases}$$

**Node alive indicator.** A dead node stops consuming energy and stops forwarding traffic.

---

## 4. Simulation Parameters

These control what the simulator computes. They are inputs, not physical properties of the hardware.

| Symbol | Code field | Description | Default |
|---|---|---|---|
| $T_{\text{total}}$ | `duration_hours × 3600` | Total simulation duration | — |
| $\Delta t$ | `time_step_seconds` | Length of one discrete time step | 60 s |
| — | `gateway_externally_powered` | If true, command center draws zero energy | `True` |
| — | `tx_only_if_confirmed` | If true, only AI-confirmed detections trigger uplink and relay forwarding | `False` |

The simulator runs $\lceil T_{\text{total}} / \Delta t \rceil$ steps. Each step applies baseline idle power to all alive nodes, then processes all events whose timestamp falls within that step.

---

## 5. Shaman I Variables (Sensor Node)

Shaman I nodes detect acoustic events, process them locally, and transmit results to their parent relay via **WiFi**. They do not receive packets and do not use LoRa.

### 5.1 Power Inputs

| Symbol | Code field | Description | Unit |
|---|---|---|---|
| $P^{(I)}_{\text{proc,act}}$ | `P_proc_shaI_active` | Processor active — during local event processing | W |
| $P^{(I)}_{\text{proc,slp}}$ | `P_proc_shaI_sleep` | Processor sleep — baseline idle draw | W |
| $P^{(I)}_{\text{wifi,tx}}$ | `P_wifi_tx` | WiFi transmit power (sensor → relay link only; Shaman I never receives) | W |
| $P^{(I)}_{\text{mic,listen}}$ | `P_mic` | Microphone continuously listening | W |
| $P^{(I)}_{\text{mic,off}}$ | `P_mic_off` | Microphone off/deep-sleep state | W |

**Definitions:**

- **`P_proc_shaI_active`** — Power used by the Shaman I processor while actively processing a detected event. Applied for `t_proc_shaI` seconds per event.
- **`P_proc_shaI_sleep`** — Power used by the Shaman I processor while idle or sleeping between active work. Applied for the remainder of the time step when no events are being processed.
- **`P_wifi_tx`** — Power used when a Shaman I node transmits a WiFi message to its parent relay. Applied for `t_tx_wifi × frames_per_hop` seconds per transmitted event. Shaman I never receives — this is its only radio draw.
- **`P_mic`** — Power used by the microphone while continuously listening for acoustic events. Applied for the full duration of every time step; the microphone is always on.
- **`P_mic_off`** — Power used by the microphone when it is off or in a deep-sleep state. Not used in the current baseline energy calculation — the mic is modelled as always listening — but available as a config input for future duty-cycling models.

### 5.2 Time Inputs

| Symbol | Code field | Description | Unit |
|---|---|---|---|
| $t^{(I)}_{\text{proc}}$ | `t_proc_shaI` | CPU time to process one detected event | s |
| $t^{(I)}_{\text{wifi,tx}}$ | `t_tx_wifi` | WiFi transmit duration per frame | s |

**Definitions:**

- **`t_proc_shaI`** — Time required for a Shaman I node to process one detected event. Multiplied by `n_local` each step to compute the total active processor time; the remainder of the step is spent in sleep.
- **`t_tx_wifi`** — Time required to transmit one WiFi frame from a Shaman I node. Total transmit time per event is `t_tx_wifi × frames_per_hop`.

### 5.3 Event Counts (computed per step)

| Symbol | Description |
|---|---|
| $n^{(I)}_{\text{local}}$ | Events detected at this sensor in this time step |
| $n^{(I)}_{\text{tx}}$ | Messages transmitted to parent. Equal to $n^{(I)}_{\text{local}}$ if parent is alive; 0 if parent is dead. |

---

## 6. Shaman II Variables (Relay Node)

Shaman II nodes receive packets from child sensors via **WiFi**, from child relays via **LoRa**, aggregate them, and forward via **LoRa** to their parent. The two receive channels have different power levels and must be tracked separately.

### 6.1 Power Inputs

| Symbol | Code field | Description | Unit |
|---|---|---|---|
| $P^{(II)}_{\text{proc,act}}$ | `P_proc_shaII_active` | Main processor active power | W |
| $P^{(II)}_{\text{proc,slp}}$ | `P_proc_shaII_sleep` | Main processor sleep power | W |
| $P^{(II)}_{\text{ctrl,act}}$ | `P_controller_active` | ESP32 controller active power | W |
| $P^{(II)}_{\text{ctrl,slp}}$ | `P_controller_sleep` | ESP32 controller sleep power | W |
| $P^{(II)}_{\text{lora,tx}}$ | `P_lora_tx` | LoRa transmit power (relay → relay/command) | W |
| $P^{(II)}_{\text{lora,rx}}$ | `P_lora_rx` | LoRa receive power (relay child → this relay) | W |
| $P^{(II)}_{\text{wifi,rx}}$ | `P_wifi_rx` | WiFi receive power (sensor child → this relay) | W |
| $P^{(II)}_{\text{backoff}}$ | `P_backoff` | Power during CSMA backoff between retries | W |

**Definitions:**

- **`P_proc_shaII_active`** — Power used by the Shaman II main processor while actively processing packets. Applied as a delta above sleep power (`P_proc_shaII_active − P_proc_shaII_sleep`) for `t_proc_shaII` seconds per packet forwarded.
- **`P_proc_shaII_sleep`** — Power used by the Shaman II main processor while idle or sleeping. Part of the baseline draw applied continuously throughout each time step.
- **`P_controller_active`** — Power used by the Shaman II controller (ESP32) while active. Present in the config but not currently applied in the baseline equation — only `P_controller_sleep` enters the idle draw.
- **`P_controller_sleep`** — Power used by the Shaman II controller while sleeping. Applied for the full duration of the idle period every step as part of the baseline.
- **`P_lora_tx`** — Power used when a Shaman II relay transmits a LoRa message upward to its parent. Applied for `t_lora_tx × frames_per_hop` seconds per forwarded packet, plus the same amount again per retry cycle.
- **`P_lora_rx`** — Power used when a Shaman II relay receives or listens for LoRa messages from relay children. Also included in the baseline idle draw, since the relay must listen continuously even when no packets arrive.
- **`P_wifi_rx`** — Power used when a Shaman II relay receives WiFi messages from Shaman I sensors. Applied for `t_rx_wifi` seconds per packet received from a sensor child. Distinct from `P_lora_rx` — different hardware, different power draw.
- **`P_backoff`** — Power used by a Shaman II relay while waiting during retry backoff. Applied for `t_backoff` seconds per retry cycle, scaled by `avg_retries_per_tx × n_fwd`.

### 6.2 Time Inputs

| Symbol | Code field | Description | Unit |
|---|---|---|---|
| $t^{(II)}_{\text{proc}}$ | `t_proc_shaII` | Time to process one forwarded packet | s |
| $t^{(II)}_{\text{wifi,rx}}$ | `t_rx_wifi` | WiFi receive duration per frame (from sensor child) | s |
| $t^{(II)}_{\text{backoff}}$ | `t_backoff` | Backoff wait duration per retry attempt | s |
| $t^{(II)}_{\text{lora,tx}}$ | — | LoRa airtime per frame — **computed from radio parameters**, not a direct input (see §7) | s |

**Definitions:**

- **`t_proc_shaII`** — Time required for a Shaman II relay to process one packet. Applied once per forwarded packet (`n_fwd`) to compute the active processor time above the sleep baseline.
- **`t_rx_wifi`** — Time required for a Shaman II relay to receive one WiFi frame from a sensor child. Applied once per `n_rx_wifi` packet received.
- **`t_backoff`** — Time spent waiting during one retry backoff period. Applied once per retry cycle; total retry time per step is `avg_retries_per_tx × n_fwd × t_backoff`.

### 6.3 Event Counts (computed per step)

| Symbol | Code field | Description |
|---|---|---|
| $n^{(II)}_{\text{local}}$ | `n_local` | Events generated at this relay itself |
| $n^{(II)}_{\text{rx,wifi}}$ | `n_received_wifi` | Packets received via WiFi from sensor children |
| $n^{(II)}_{\text{rx,lora}}$ | `n_received_lora` | Packets received via LoRa from relay children |
| $n^{(II)}_{\text{fwd}}$ | `n_forward` | Total packets forwarded upward: $n^{(II)}_{\text{local}} + n^{(II)}_{\text{rx,wifi}} + n^{(II)}_{\text{rx,lora}}$ |
| $\bar{r}_{\text{tx}}$ | `avg_retries_per_tx` | **Mean** CSMA retries per successful LoRa TX. This is a fractional mean-field rate (e.g. 0.5 means on average half a retry per packet), not an integer count. The energy is $\bar{r}_{\text{tx}}$ × cost-per-retry-cycle. |

**`avg_retries_per_tx`** — Average number of LoRa retry attempts per successful transmission. Modelled as a continuous mean-field rate rather than a per-packet integer: a value of 1.5 means that on average each forwarded packet requires 1.5 extra transmit+backoff cycles before succeeding. The retry energy cost per step is `avg_retries_per_tx × n_fwd × (E_one_tx + E_one_backoff)`. Set to 0 for an ideal lossless channel.

### 6.4 Derived Time (computed per step)

$$T^{(II)}_{\text{idle}} = \max\!\left(0,\ \Delta t - t_{\text{active}}\right)$$

where

$$t_{\text{active}} = n^{(II)}_{\text{local}} \cdot t^{(II)}_{\text{proc}} + n^{(II)}_{\text{rx}} \cdot t^{(II)}_{\text{rx}} + n^{(II)}_{\text{fwd}} \cdot t^{(II)}_{\text{lora,tx}} \cdot f_{\text{hop}} + \bar{r}_{\text{tx}} \cdot \left(t^{(II)}_{\text{lora,tx}} + t^{(II)}_{\text{backoff}}\right)$$

**$T^{(II)}_{\text{idle}}$** is the remaining time in the step after all active processing — the relay spends this at its baseline idle draw.

---

## 7. LoRa Radio Parameters

The LoRa airtime per frame is **computed** from the physical radio configuration using the Semtech standard formula. It is not a direct input.

| Symbol | Code field | Description | Default |
|---|---|---|---|
| SF | `spreading_factor` | Spreading factor (6–12) | 10 |
| BW | `bandwidth_hz` | Channel bandwidth | 125 000 Hz |
| $\ell$ | `packet_bytes` | Payload size per frame | 128 bytes |
| CR | `coding_rate` | LoRa coding rate denominator (5 = 4/5) | 5 |
| $N_{\text{pre}}$ | `preamble_symbols` | Number of preamble symbols | 8 |
| $f_{\text{hop}}$ | `frames_per_hop` | Frames transmitted per relay hop (protocol overhead) | 3 |
| $\bar{r}_{\text{tx}}$ | `avg_retries_per_tx` | Mean CSMA retries per successful TX | 0.0 |

### LoRa Airtime Formula

$$t_{\text{sym}} = \frac{2^{\text{SF}}}{\text{BW}}$$

$$t_{\text{preamble}} = (N_{\text{pre}} + 4.25) \cdot t_{\text{sym}}$$

$$N_{\text{payload}} = 8 + \max\!\left(\left\lceil \frac{8\ell - 4\,\text{SF} + 44}{4\,\text{SF}} \right\rceil \cdot \text{CR},\ 0\right)$$

$$t_{\text{payload}} = N_{\text{payload}} \cdot t_{\text{sym}}$$

$$\boxed{t^{(II)}_{\text{lora,tx}} = t_{\text{preamble}} + t_{\text{payload}}}$$

This is the per-frame airtime. Total relay transmit time for one forwarded packet is $t^{(II)}_{\text{lora,tx}} \cdot f_{\text{hop}}$.

---

## 8. Energy Equations

All energies are in **Wh** (watt-hours): $E[\text{Wh}] = P[\text{W}] \times t[\text{s}] \div 3600$.

### 8.1 Shaman I Total Energy per Step

The sensor has a continuous baseline (processor + mic always on), plus per-event additions:

$$E^{(I)} = \underbrace{(P^{(I)}_{\text{proc,act}} + P^{(I)}_{\text{mic,listen}}) \cdot \Delta t}_{\text{baseline}} + E^{(I)}_{\text{proc,spike}} + E^{(I)}_{\text{wifi,tx}}$$

#### Per-event processor spike

$$E^{(I)}_{\text{proc,spike}} = n^{(I)}_{\text{local}} \cdot P^{(I)}_{\text{proc,act}} \cdot t^{(I)}_{\text{proc}}$$

#### WiFi transmission

$$E^{(I)}_{\text{wifi,tx}} = n^{(I)}_{\text{tx}} \cdot P^{(I)}_{\text{wifi,tx}} \cdot t^{(I)}_{\text{wifi,tx}} \cdot f_{\text{hop}}$$

### 8.2 Shaman II Total Energy per Step

$$E^{(II)} = E^{(II)}_{\text{idle}} + E^{(II)}_{\text{rx}} + E^{(II)}_{\text{proc}} + E^{(II)}_{\text{tx}} + E^{(II)}_{\text{retry}}$$

#### Idle (baseline draw during quiet time)

$$E^{(II)}_{\text{idle}} = \left(P^{(II)}_{\text{proc,slp}} + P^{(II)}_{\text{ctrl,slp}} + P^{(II)}_{\text{lora,rx}}\right) \cdot T^{(II)}_{\text{idle}}$$

#### Receive (two channels, different power)

$$E^{(II)}_{\text{rx}} = n^{(II)}_{\text{rx,wifi}} \cdot P^{(II)}_{\text{wifi,rx}} \cdot t^{(II)}_{\text{wifi,rx}} + n^{(II)}_{\text{rx,lora}} \cdot P^{(II)}_{\text{lora,rx}} \cdot t^{(II)}_{\text{lora,tx}}$$

#### Processing

$$E^{(II)}_{\text{proc}} = n^{(II)}_{\text{fwd}} \cdot P^{(II)}_{\text{proc,act}} \cdot t^{(II)}_{\text{proc}}$$

#### Transmission

$$E^{(II)}_{\text{tx}} = n^{(II)}_{\text{fwd}} \cdot P^{(II)}_{\text{lora,tx}} \cdot t^{(II)}_{\text{lora,tx}} \cdot f_{\text{hop}}$$

#### Retry (mean-field)

$$E^{(II)}_{\text{retry}} = \bar{r}_{\text{tx}} \cdot n^{(II)}_{\text{fwd}} \cdot \left(P^{(II)}_{\text{lora,tx}} \cdot t^{(II)}_{\text{lora,tx}} \cdot f_{\text{hop}} + P^{(II)}_{\text{backoff}} \cdot t^{(II)}_{\text{backoff}}\right)$$

---

## 9. Battery Update Rule

Each time step, for every alive node:

$$E_i(t + \Delta t) = \max\!\left(0,\ E_i(t) - E_i^{\text{used}}\right)$$

$$a_i(t) = \begin{cases} 1, & E_i(t) > 0 \\ 0, & E_i(t) \le 0 \end{cases}$$

$$t_i^{\text{death}} = \min \{ t \mid E_i(t) \le 0 \}$$

A node that reaches $E_i = 0$ stops forwarding traffic from that step onward. Its children's $n^{(i)}_{\text{tx}}$ counts are zeroed in subsequent steps (the parent being dead suppresses transmissions from the child).

---

## 10. Network Flow Constraint

$$n^{(i)}_{\text{fwd}} = n^{(i)}_{\text{local}} + \sum_{j \in \mathcal{C}(i)} n^{(j)}_{\text{tx}}$$

Traffic accumulates as it moves toward the command center. A relay aggregates its own local events plus everything forwarded by its children.

---

## 11. Key Insight: Rank and Energy

$$r_i \downarrow \quad\Longrightarrow\quad n^{(i)}_{\text{fwd}} \uparrow \quad\Longrightarrow\quad E^{(i)} \uparrow$$

Nodes closer to the command center (lower rank) forward more aggregate traffic and therefore drain faster. The relay nearest the gateway is the most likely first failure. This is the primary design constraint the simulator is built to expose.
