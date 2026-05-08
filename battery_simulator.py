"""Shaman I/II battery simulator (single file bundle).

Public API: BatterySimulator, SimulationConfig, run_from_dict, build_network_from_payload_nodes,
timeline_from_simple_events, NodeRole, SimNetwork, SimNode, SimEvent, EventTimeline.

Energy: Wh = P[W] * t[s] / 3600.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# ----- was events.py -----
"""AI event timeline (same schema as upstream battery_sim)."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class SimEvent:
    node_id: str
    timestamp_s: float
    event_type: str = "detection"
    confirmed: bool = True
    confidence: float = 1.0
    stage1_duration_s: float = 0.0
    stage2_duration_s: float = 0.03
    clip_duration_s: float = 3.0


@dataclass
class EventTimeline:
    events: List[SimEvent] = field(default_factory=list)
    duration_seconds: float = 3 * 3600

    def __post_init__(self):
        self.events.sort(key=lambda e: e.timestamp_s)

    def confirmed_count(self) -> int:
        return sum(1 for e in self.events if e.confirmed)

    @classmethod
    def generate_mock(
        cls,
        node_ids: List[str],
        duration_hours: float = 3.0,
        events_per_node: int = 15,
    ) -> "EventTimeline":
        import random

        events: List[SimEvent] = []
        duration_s = duration_hours * 3600
        for node_id in node_ids:
            n = random.randint(max(0, events_per_node - 5), events_per_node + 5)
            for _ in range(n):
                confirmed = random.random() > 0.4
                events.append(
                    SimEvent(
                        node_id=node_id,
                        timestamp_s=random.uniform(0, duration_s),
                        event_type="gunshot_confirmed" if confirmed else "gunshot_candidate",
                        confirmed=confirmed,
                        confidence=random.uniform(0.7, 1.0),
                    )
                )
        return cls(events=events, duration_seconds=duration_s)

# ----- was config.py -----
"""Configuration: Shaman I/II power, radio (LoRa airtime, retries), simulation flags."""
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
import math


@dataclass
class ComponentPower:
    current_ma: Optional[float] = None
    voltage_v: Optional[float] = None
    power_w: Optional[float] = None

    @property
    def watts(self) -> float:
        if self.power_w is not None:
            return float(self.power_w)
        if self.current_ma is not None and self.voltage_v is not None:
            return (self.current_ma / 1000.0) * self.voltage_v
        return 0.0

    @classmethod
    def from_cvp_dict(cls, d: Optional[Dict[str, Any]]) -> "ComponentPower":
        if not d:
            return cls()
        return cls(
            current_ma=d.get("current"),
            voltage_v=d.get("voltage"),
            power_w=d.get("power"),
        )


@dataclass
class ShamanIConfig:
    battery_wh: float = 22.0
    P_mic: float = 0.00198
    """Mic deep sleep / off-state draw — listed in team spec §2; not in §3.1 baseline."""
    P_mic_off: float = 0.00033
    P_proc_shaI_active: float = 0.528
    """Processor sleep draw — spec §2; §3.1 baseline uses active + mic only."""
    P_proc_shaI_sleep: float = 0.00264
    P_wifi_tx: float = 0.726
    t_tx_wifi: float = 0.005
    """Per-detection CPU spike duration — spec §2; unused by §3.1 as written."""
    t_proc_shaI: float = 0.030

    @classmethod
    def from_gui_payload(cls, payload: Optional[Dict[str, Any]]) -> "ShamanIConfig":
        inst = cls()
        if not payload:
            return inst
        inst.battery_wh = float(payload.get("batteryLife") or inst.battery_wh)
        comps = payload.get("components") or {}

        def w(name: str, default: float) -> float:
            cp = ComponentPower.from_cvp_dict(comps.get(name))
            return cp.watts if cp.watts > 0 else default

        inst.P_proc_shaI_active = w("working", inst.P_proc_shaI_active)
        inst.P_wifi_tx = w("transmit", inst.P_wifi_tx)
        inst.P_mic = w("micListen", inst.P_mic)
        inst.P_mic_off = w("micSleep", inst.P_mic_off)
        inst.P_proc_shaI_sleep = w("sleep", inst.P_proc_shaI_sleep)
        inst.apply_optional_scalar_overrides(payload)
        return inst

    def apply_optional_scalar_overrides(self, payload: Optional[Dict[str, Any]]) -> "ShamanIConfig":
        """Numeric keys from JSON payloads or CLI (`t_proc_shaI`, ...)."""
        if not payload:
            return self
        floats = (
            "P_mic",
            "P_mic_off",
            "P_proc_shaI_active",
            "P_proc_shaI_sleep",
            "P_wifi_tx",
            "t_tx_wifi",
            "t_proc_shaI",
        )
        for k in floats:
            if payload.get(k) is not None:
                setattr(self, k, float(payload[k]))
        if payload.get("battery_wh") is not None:
            self.battery_wh = float(payload["battery_wh"])
        return self


@dataclass
class ShamanIIConfig:
    battery_wh: float = 22.0
    P_proc_shaII_active: float = 3.5
    P_proc_shaII_sleep: float = 0.5
    """ESP32 controller active — listed in spec §2; §3.2 baseline uses sleep-only."""
    P_controller_active: float = 0.528
    P_controller_sleep: float = 0.00264
    P_lora_tx: float = 0.389
    P_lora_rx: float = 0.0198
    P_wifi_rx: float = 0.330
    P_backoff: float = 0.0198
    t_proc_shaII: float = 0.010
    t_rx_wifi: float = 0.005
    t_backoff: float = 0.100

    @classmethod
    def from_gui_payload(cls, payload: Optional[Dict[str, Any]]) -> "ShamanIIConfig":
        inst = cls()
        if not payload:
            return inst
        inst.battery_wh = float(payload.get("batteryLife") or inst.battery_wh)
        comps = payload.get("components") or {}

        def w(name: str, default: float) -> float:
            cp = ComponentPower.from_cvp_dict(comps.get(name))
            return cp.watts if cp.watts > 0 else default

        inst.P_proc_shaII_sleep = w("sleep", inst.P_proc_shaII_sleep)
        inst.P_proc_shaII_active = w("working", inst.P_proc_shaII_active)
        inst.P_lora_tx = w("transmit", inst.P_lora_tx)
        inst.P_lora_rx = w("receive", inst.P_lora_rx)
        ctrl_awake = ComponentPower.from_cvp_dict(comps.get("controllerActive"))
        if ctrl_awake.watts > 0:
            inst.P_controller_active = ctrl_awake.watts
        inst.apply_optional_scalar_overrides(payload)
        return inst

    def apply_optional_scalar_overrides(self, payload: Optional[Dict[str, Any]]) -> "ShamanIIConfig":
        if not payload:
            return self
        floats = (
            "P_proc_shaII_active",
            "P_proc_shaII_sleep",
            "P_controller_active",
            "P_controller_sleep",
            "P_lora_tx",
            "P_lora_rx",
            "P_wifi_rx",
            "P_backoff",
            "t_proc_shaII",
            "t_rx_wifi",
            "t_backoff",
        )
        for k in floats:
            if payload.get(k) is not None:
                setattr(self, k, float(payload[k]))
        if payload.get("battery_wh") is not None:
            self.battery_wh = float(payload["battery_wh"])
        return self


@dataclass
class RadioConfig:
    packet_bytes: int = 128
    spreading_factor: int = 10
    bandwidth_hz: int = 125_000
    coding_rate: int = 5
    preamble_symbols: int = 8
    frames_per_hop: int = 3
    """Mean CSMA retries per successful LoRa transmission (0 = ideal channel)."""
    avg_retries_per_tx: float = 0.0

    def airtime_per_frame_s(self) -> float:
        sf = self.spreading_factor
        bw = self.bandwidth_hz
        cr = self.coding_rate
        pl = self.packet_bytes
        t_sym = (2 ** sf) / bw
        t_preamble = (self.preamble_symbols + 4.25) * t_sym
        n_payload = 8 + max(math.ceil((8 * pl - 4 * sf + 28 + 16) / (4 * sf)) * cr, 0)
        t_payload = n_payload * t_sym
        return t_preamble + t_payload


@dataclass
class SimulationConfig:
    shaman_i: ShamanIConfig = field(default_factory=ShamanIConfig)
    shaman_ii: ShamanIIConfig = field(default_factory=ShamanIIConfig)
    radio: RadioConfig = field(default_factory=RadioConfig)
    time_step_seconds: float = 60.0
    """If True, command/gateway draws no energy (Ivonne-style external power)."""
    gateway_externally_powered: bool = True
    """If True, only `_confirmed` AI events trigger WiFi uplink + relay forwarding."""
    tx_only_if_confirmed: bool = False

    @classmethod
    def from_run_config(
        cls,
        shaman_i_config: Optional[Dict[str, Any]] = None,
        shaman_ii_config: Optional[Dict[str, Any]] = None,
        radio_config: Optional[Dict[str, Any]] = None,
        *,
        gateway_externally_powered: Optional[bool] = None,
        tx_only_if_confirmed: Optional[bool] = None,
    ) -> "SimulationConfig":
        cfg = cls(
            shaman_i=ShamanIConfig.from_gui_payload(shaman_i_config),
            shaman_ii=ShamanIIConfig.from_gui_payload(shaman_ii_config),
        )
        if radio_config:
            for k, v in radio_config.items():
                if hasattr(cfg.radio, k) and v is not None:
                    setattr(cfg.radio, k, v)
        if gateway_externally_powered is not None:
            cfg.gateway_externally_powered = gateway_externally_powered
        if tx_only_if_confirmed is not None:
            cfg.tx_only_if_confirmed = tx_only_if_confirmed
        return cfg

# ----- was network.py -----
"""Topology: SENSOR (Shaman I), RELAY (Shaman II), COMMAND (gateway)."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class NodeRole(Enum):
    COMMAND = "command"
    RELAY = "relay"
    SENSOR = "sensor"


@dataclass
class SimNode:
    node_id: str
    role: NodeRole
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

    energy_consumed_wh: float = 0.0

    n_local: int = 0
    n_received_wifi: int = 0
    n_received_lora: int = 0
    n_retries_fractional: float = 0.0
    step_tx_count: int = 0

    alive: bool = True
    death_time_seconds: Optional[float] = None

    battery_history: List[Dict] = field(default_factory=list)

    @property
    def n_received(self) -> int:
        return self.n_received_wifi + self.n_received_lora

    @property
    def n_forward(self) -> int:
        return self.n_local + self.n_received

    def record_state(
        self,
        time_seconds: float,
        capacity_wh: float,
        *,
        infinite_battery: bool = False,
    ):
        if infinite_battery or capacity_wh <= 0:
            remaining = capacity_wh if capacity_wh > 0 else 0.0
            pct = 100.0 if infinite_battery else 0.0
        else:
            remaining = max(0.0, capacity_wh - self.energy_consumed_wh)
            pct = (remaining / capacity_wh) * 100.0
        self.battery_history.append({
            "time_seconds": time_seconds,
            "time_hours": time_seconds / 3600,
            "battery_percent": round(pct, 4),
            "battery_wh": round(remaining, 6),
            "alive": 1 if self.alive else 0,
        })


@dataclass
class SimNetwork:
    nodes: Dict[str, SimNode] = field(default_factory=dict)

    def add_node(self, node: SimNode):
        self.nodes[node.node_id] = node

    def get_node(self, node_id: str) -> Optional[SimNode]:
        return self.nodes.get(node_id)

    @classmethod
    def from_db_nodes(cls, db_nodes: List, db_edges: List) -> "SimNetwork":
        rank = {NodeRole.SENSOR: 0, NodeRole.RELAY: 1, NodeRole.COMMAND: 2}
        network = cls()

        for n in db_nodes:
            role = NodeRole(n.role) if hasattr(n, "role") else NodeRole(n["role"])
            node_id = n.node_id if hasattr(n, "node_id") else n["id"]
            network.add_node(SimNode(node_id=node_id, role=role))

        for e in db_edges:
            from_id = e.from_node if hasattr(e, "from_node") else e["from"]
            to_id = e.to_node if hasattr(e, "to_node") else e["to"]
            a = network.get_node(from_id)
            b = network.get_node(to_id)
            if a is None or b is None:
                continue
            if rank[a.role] < rank[b.role]:
                child, parent = a, b
            elif rank[a.role] > rank[b.role]:
                child, parent = b, a
            else:
                child, parent = a, b
            if child.parent_id is None:
                child.parent_id = parent.node_id
            if child.node_id not in parent.children_ids:
                parent.children_ids.append(child.node_id)

        return network

# ----- was engine.py -----
"""
Battery simulator: spec-aligned energies + retries + Ivonne-style output series.

Energy (Wh): P[W] × t[s] / 3600 unless noted.
"""
from typing import Any, Dict, Optional
from datetime import datetime


SECONDS_PER_HOUR = 3600.0


def _wh_from_w_s(p_watts: float, seconds: float) -> float:
    return p_watts * (seconds / SECONDS_PER_HOUR)


class BatterySimulator:
    def __init__(
        self,
        config: SimulationConfig,
        network: SimNetwork,
        timeline: EventTimeline,
        duration_hours: float = 3.0,
    ):
        self.config = config
        self.network = network
        self.timeline = timeline
        self.duration_hours = duration_hours
        self.duration_seconds = duration_hours * SECONDS_PER_HOUR

        self._t_lora = self.config.radio.airtime_per_frame_s()
        self._frames = self.config.radio.frames_per_hop
        self._topo_order: List[SimNode] = self._topological_sort()

    def _topological_sort(self) -> List[SimNode]:
        """Return nodes leaves-first so each relay is processed after all its children."""
        visited: set = set()
        order: List[SimNode] = []

        def visit(node: SimNode) -> None:
            if node.node_id in visited:
                return
            visited.add(node.node_id)
            for child_id in node.children_ids:
                child = self.network.get_node(child_id)
                if child is not None:
                    visit(child)
            order.append(node)

        for node in self.network.nodes.values():
            visit(node)
        return order

    def _capacity_wh(self, node: SimNode) -> float:
        if node.role == NodeRole.SENSOR:
            return self.config.shaman_i.battery_wh
        return self.config.shaman_ii.battery_wh

    def _baseline_power_w(self, node: SimNode) -> float:
        if node.role == NodeRole.SENSOR:
            s1 = self.config.shaman_i
            return s1.P_proc_shaI_active + s1.P_mic
        if node.role == NodeRole.COMMAND and self.config.gateway_externally_powered:
            return 0.0
        s2 = self.config.shaman_ii
        return s2.P_controller_sleep + s2.P_lora_rx + s2.P_proc_shaII_sleep

    def _gateway_infinite(self, node: SimNode) -> bool:
        return node.role == NodeRole.COMMAND and self.config.gateway_externally_powered

    def _add_energy(self, node: SimNode, delta_wh: float, current_time_end: float) -> None:
        if self._gateway_infinite(node) or not node.alive:
            return
        cap = self._capacity_wh(node)
        node.energy_consumed_wh += max(0.0, delta_wh)
        remaining = cap - node.energy_consumed_wh
        if remaining <= 0 and node.alive:
            node.alive = False
            node.death_time_seconds = current_time_end

    def run(self) -> Dict[str, Any]:
        for node in self.network.nodes.values():
            node.energy_consumed_wh = 0.0
            node.battery_history = []
            node.n_local = 0
            node.n_received_wifi = 0
            node.n_received_lora = 0
            node.n_retries_fractional = 0.0
            node.step_tx_count = 0
            node.alive = True
            node.death_time_seconds = None

        events = sorted(self.timeline.events, key=lambda e: e.timestamp_s)
        event_idx = 0
        time_step = self.config.time_step_seconds
        current_time = 0.0

        while current_time < self.duration_seconds:
            next_time = min(current_time + time_step, self.duration_seconds)
            dt = next_time - current_time

            self._apply_baseline(dt, next_time)

            # Reset per-step TX counters before Phase A.
            for node in self.network.nodes.values():
                node.step_tx_count = 0

            # Phase A: charge sensors for WiFi TX; accumulate step_tx_count on sensors.
            while event_idx < len(events) and events[event_idx].timestamp_s < next_time:
                ev = events[event_idx]
                if not self.config.tx_only_if_confirmed or ev.confirmed:
                    self._process_sensor_event(ev, next_time)
                event_idx += 1

            # Phase B: charge relays bottom-up using children's step_tx_count.
            self._apply_relay_forwarding(next_time)

            for node in self.network.nodes.values():
                node.record_state(
                    next_time,
                    self._capacity_wh(node),
                    infinite_battery=self._gateway_infinite(node),
                )

            current_time = next_time

        return self._build_output()

    def _apply_baseline(self, dt_seconds: float, t_end: float) -> None:
        dt_h = dt_seconds / SECONDS_PER_HOUR
        for node in self.network.nodes.values():
            if self._gateway_infinite(node):
                continue
            if not node.alive:
                continue
            self._add_energy(node, self._baseline_power_w(node) * dt_h, t_end)

    def _process_sensor_event(self, event: SimEvent, t_end: float) -> None:
        """Phase A: charge originating sensor for WiFi TX; mark it transmitted."""
        source = self.network.get_node(event.node_id)
        if source is None or source.role != NodeRole.SENSOR or not source.alive:
            return
        source.n_local += 1
        source.step_tx_count += 1
        self._sensor_tx(source, t_end)

    def _apply_relay_forwarding(self, t_end: float) -> None:
        """Phase B: walk nodes leaves-first; each relay reads children's step_tx_count."""
        for node in self._topo_order:
            if node.role == NodeRole.SENSOR or self._gateway_infinite(node):
                continue
            if not node.alive:
                continue

            n_wifi = 0
            n_lora = 0
            for child_id in node.children_ids:
                child = self.network.get_node(child_id)
                if child is None or child.step_tx_count == 0:
                    continue
                if child.role == NodeRole.SENSOR:
                    n_wifi += child.step_tx_count
                else:
                    n_lora += child.step_tx_count

            n_rx = n_wifi + n_lora
            if n_rx == 0:
                continue

            self._relay_receive(node, n_wifi, n_lora, t_end)
            self._relay_process(node, n_rx, t_end)
            if node.role != NodeRole.COMMAND and node.parent_id is not None:
                self._relay_transmit(node, n_rx, t_end)
                node.step_tx_count = n_rx

    def _sensor_tx(self, sensor: SimNode, t_end: float) -> None:
        s1 = self.config.shaman_i
        on_s = s1.t_tx_wifi * self._frames
        self._add_energy(sensor, _wh_from_w_s(s1.P_wifi_tx, on_s), t_end)

    def _relay_receive(self, relay: SimNode, n_wifi: int, n_lora: int, t_end: float) -> None:
        if self._gateway_infinite(relay):
            return
        s2 = self.config.shaman_ii
        if n_wifi > 0:
            relay.n_received_wifi += n_wifi
            self._add_energy(relay, n_wifi * _wh_from_w_s(s2.P_wifi_rx, s2.t_rx_wifi), t_end)
        if n_lora > 0:
            relay.n_received_lora += n_lora
            self._add_energy(relay, n_lora * _wh_from_w_s(s2.P_lora_rx, self._t_lora), t_end)

    def _relay_process(self, relay: SimNode, n_packets: int, t_end: float) -> None:
        if self._gateway_infinite(relay):
            return
        s2 = self.config.shaman_ii
        delta_w = max(0.0, s2.P_proc_shaII_active - s2.P_proc_shaII_sleep)
        self._add_energy(relay, n_packets * _wh_from_w_s(delta_w, s2.t_proc_shaII), t_end)

    def _relay_transmit(self, relay: SimNode, n_packets: int, t_end: float) -> None:
        if self._gateway_infinite(relay):
            return
        s2 = self.config.shaman_ii
        hop_on_s = self._t_lora * self._frames
        self._add_energy(relay, n_packets * _wh_from_w_s(s2.P_lora_tx, hop_on_s), t_end)

        r = max(0.0, float(self.config.radio.avg_retries_per_tx))
        if r > 0 and relay.alive:
            # Spec §3.2: P_lora_tx * t_tx * frames + P_backoff * t_backoff per retry cycle
            e_one = _wh_from_w_s(s2.P_lora_tx, hop_on_s) + _wh_from_w_s(
                s2.P_backoff, s2.t_backoff
            )
            self._add_energy(relay, n_packets * r * e_one, t_end)
            relay.n_retries_fractional += n_packets * r

    def _build_output(self) -> Dict[str, Any]:
        nodes_out: Dict[str, Any] = {}
        worst_percent = 101.0
        worst_node_id = ""

        for node_id, node in self.network.nodes.items():
            cap = self._capacity_wh(node)
            infinite = self._gateway_infinite(node)
            if infinite:
                remaining = cap
                percent = 100.0
            else:
                remaining = max(0.0, cap - node.energy_consumed_wh)
                percent = (remaining / cap * 100.0) if cap > 0 else 0.0

            p_avg_w = (
                node.energy_consumed_wh / self.duration_hours if self.duration_hours > 0 else 0.0
            )
            pct_used = (
                (node.energy_consumed_wh / cap * 100.0) if cap > 0 and not infinite else 0.0
            )
            energy_remaining_wh = round(remaining, 6) if not infinite else round(cap, 6)

            projected_total_life_h = (
                (cap / p_avg_w) if (p_avg_w > 0 and not infinite) else None
            )
            projected_remaining_life_h = (
                (remaining / p_avg_w) if (p_avg_w > 0 and not infinite) else None
            )

            hist = node.battery_history
            flat = self._flatten_series(hist)

            if not infinite and percent < worst_percent:
                worst_percent = percent
                worst_node_id = node_id

            nodes_out[node_id] = {
                "node_id": node_id,
                "role": node.role.value,
                "capacity_wh": round(cap, 4),
                "time_series": hist,
                "series": flat,
                "summary": {
                    "final_battery_percent": round(percent, 2),
                    "percent_remaining": round(percent, 4),
                    "percent_used": round(pct_used, 4),
                    "energy_consumed_wh": round(node.energy_consumed_wh, 6),
                    "energy_remaining_wh": energy_remaining_wh,
                    "average_power_w": round(p_avg_w, 6),
                    "projected_total_life_hours": round(projected_total_life_h, 2)
                    if projected_total_life_h is not None
                    else None,
                    "projected_remaining_life_hours": round(projected_remaining_life_h, 2)
                    if projected_remaining_life_h is not None
                    else None,
                    "projected_life_hours": round(projected_total_life_h, 2)
                    if projected_total_life_h is not None
                    else None,
                    "alive": node.alive,
                    "death_time_seconds": node.death_time_seconds,
                    "n_local": node.n_local,
                    "n_received_wifi": node.n_received_wifi,
                    "n_received_lora": node.n_received_lora,
                    "n_received": node.n_received,
                    "n_forward": node.n_forward if node.role == NodeRole.RELAY else 0,
                    "n_retries_effective": round(node.n_retries_fractional, 4),
                },
            }

        return {
            "simulation_id": f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "duration_hours": self.duration_hours,
            "total_events_processed": len(self.timeline.events),
            "config_flags": {
                "gateway_externally_powered": self.config.gateway_externally_powered,
                "tx_only_if_confirmed": self.config.tx_only_if_confirmed,
            },
            "radio": {
                "spreading_factor": self.config.radio.spreading_factor,
                "bandwidth_hz": self.config.radio.bandwidth_hz,
                "packet_bytes": self.config.radio.packet_bytes,
                "airtime_per_frame_ms": round(self._t_lora * 1000, 3),
                "frames_per_hop": self._frames,
                "avg_retries_per_tx": self.config.radio.avg_retries_per_tx,
            },
            "nodes": nodes_out,
            "summary": {
                "worst_node_id": worst_node_id or None,
                "worst_battery_percent": round(worst_percent, 2)
                if worst_node_id
                else None,
                "total_nodes": len(self.network.nodes),
            },
        }

    @staticmethod
    def _flatten_series(hist: list) -> Dict[str, Any]:
        return {
            "time_seconds": [h["time_seconds"] for h in hist],
            "time_hours": [h["time_hours"] for h in hist],
            "battery_percent": [h["battery_percent"] for h in hist],
            "battery_wh": [h["battery_wh"] for h in hist],
            "alive": [h["alive"] for h in hist],
        }

# ----- was api.py -----
"""
Compatibility entrypoints (Ivonne-style dict payloads ↔ internal graph).
"""
from typing import Any, Dict, List, Optional


NODE_TYPE_SENSOR = "Shaman I"
NODE_TYPE_RELAY = "Shaman II"
NODE_TYPE_COMMAND = "Command Center"


def _role_from_type(nt: str) -> NodeRole:
    s = str(nt).strip().lower().replace("_", " ")
    if "command" in s or "gateway" in s:
        return NodeRole.COMMAND
    if "shaman ii" in s or s.endswith("relay"):
        return NodeRole.RELAY
    # Shaman I, sensor leaf, generic shaman-i
    return NodeRole.SENSOR


def build_network_from_payload_nodes(nodes_payload: List[dict]) -> SimNetwork:
    """Build SimNetwork from a list of nodes with optional parent_id / child_ids."""
    net = SimNetwork()
    for nd in nodes_payload:
        nid = nd.get("node_id") or nd.get("id")
        raw_role = nd.get("role")

        if isinstance(raw_role, str) and raw_role.strip().lower() in (
            "sensor",
            "relay",
            "command",
        ):
            rlower = raw_role.strip().lower()
            nr = {
                "sensor": NodeRole.SENSOR,
                "relay": NodeRole.RELAY,
                "command": NodeRole.COMMAND,
            }[rlower]
        else:
            nr = _role_from_type(nd.get("node_type", NODE_TYPE_SENSOR))

        pid = nd.get("parent_id")
        kids = nd.get("child_ids") or nd.get("children_ids") or nd.get("children") or []
        net.add_node(
            SimNode(
                node_id=str(nid),
                role=nr,
                parent_id=str(pid) if pid is not None else None,
                children_ids=[str(x) for x in kids],
            )
        )

    return net


def timeline_from_simple_events(events: List[dict], *, duration_hours: float) -> EventTimeline:
    """Map [{node_id, time}, ...] to EventTimeline (`time` in seconds)."""
    out = [
        SimEvent(
            node_id=str(e["node_id"]),
            timestamp_s=float(e.get("time", e.get("timestamp_s", 0.0))),
            event_type=e.get("event_type", "trace"),
            confirmed=bool(e.get("confirmed", True)),
        )
        for e in events
    ]
    return EventTimeline(events=out, duration_seconds=duration_hours * 3600.0)


def run_from_dict(
    payload: dict,
    *,
    duration_hours: Optional[float] = None,
    time_step_seconds: Optional[float] = None,
    gateway_externally_powered: Optional[bool] = None,
    tx_only_if_confirmed: Optional[bool] = None,
) -> dict:
    """Run simulation from a plain JSON-like dict.

    Payload keys::

        nodes: list of node specs (see ``build_network_from_payload_nodes``).
        events: list of {node_id, time, confirmed?}.
        duration_hours OR total_time (seconds).

    Optional tuning: shaman_i, shaman_ii, radio, time_step_seconds, gateway flags.

    Mirrors Ivonne ``run_from_dict`` loosely; returns the ``BatterySimulator.run()`` dict.
    """
    if duration_hours is not None:
        dh = float(duration_hours)
    elif "duration_hours" in payload:
        dh = float(payload["duration_hours"])
    elif "total_time" in payload:
        dh = float(payload["total_time"]) / 3600.0
    else:
        dh = float(payload.get("total_time_hours") or payload.get("T_total_hours") or 3.0)

    net = build_network_from_payload_nodes(payload.get("nodes", []))
    evs = timeline_from_simple_events(payload.get("events", []), duration_hours=dh)

    cfg = SimulationConfig.from_run_config(
        payload.get("shaman_i"),
        payload.get("shaman_ii"),
        payload.get("radio"),
        gateway_externally_powered=gateway_externally_powered
        if gateway_externally_powered is not None
        else payload.get("gateway_externally_powered"),
        tx_only_if_confirmed=tx_only_if_confirmed
        if tx_only_if_confirmed is not None
        else payload.get("tx_only_if_confirmed"),
    )

    ts = time_step_seconds
    if ts is None:
        ts = payload.get("time_step") or payload.get("time_step_seconds")
    cfg.time_step_seconds = float(ts or cfg.time_step_seconds)

    sim = BatterySimulator(cfg, net, evs, duration_hours=dh)
    return sim.run()


# ---------- CLI & regression (scenario.json + optional output/ — created on run) ----------
_ROOT = Path(__file__).resolve().parent
DEFAULT_SCENARIO_PATH = _ROOT / "scenario.json"
DEFAULT_OUTPUT_DIR = _ROOT / "output"

# Minimal 1 h / one-event case for --verify (formerly scenario_minimal.json).
_MINIMAL_VERIFY_PAYLOAD: Dict[str, Any] = {
    "duration_hours": 1.0,
    "time_step_seconds": 3600,
    "gateway_externally_powered": True,
    "tx_only_if_confirmed": False,
    "shaman_i": {
        "battery_wh": 22.0,
        "P_mic": 0.00198,
        "P_proc_shaI_active": 0.528,
        "P_wifi_tx": 0.726,
        "t_tx_wifi": 0.005,
    },
    "shaman_ii": {
        "battery_wh": 22.0,
        "P_proc_shaII_active": 3.5,
        "P_proc_shaII_sleep": 0.5,
        "P_controller_sleep": 0.00264,
        "P_lora_tx": 0.389,
        "P_lora_rx": 0.0198,
        "P_wifi_rx": 0.330,
        "P_backoff": 0.0198,
        "t_proc_shaII": 0.010,
        "t_rx_wifi": 0.005,
        "t_backoff": 0.100,
    },
    "radio": {
        "packet_bytes": 128,
        "spreading_factor": 10,
        "bandwidth_hz": 125000,
        "coding_rate": 5,
        "preamble_symbols": 8,
        "frames_per_hop": 3,
        "avg_retries_per_tx": 0,
    },
    "nodes": [
        {"node_id": "CMD1", "node_type": "Command Center", "parent_id": None, "child_ids": ["R1"]},
        {"node_id": "R1", "node_type": "Shaman II", "parent_id": "CMD1", "child_ids": ["S1"]},
        {"node_id": "S1", "node_type": "Shaman I", "parent_id": "R1", "child_ids": []},
    ],
    "events": [{"node_id": "S1", "time": 100.0, "confirmed": True, "event_type": "golden_ping"}],
}


def _strip_doc_keys(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if not str(k).startswith("_")}


def _flatten_timeseries_rows(result: dict) -> List[dict]:
    rows: List[dict] = []
    for node_id, node in result["nodes"].items():
        role = node["role"]
        cap = node["capacity_wh"]
        series = node.get("series", {})
        ts = series.get("time_seconds", [])
        for i in range(len(ts)):
            rows.append({
                "time_seconds": ts[i],
                "time_hours": series["time_hours"][i],
                "node_id": node_id,
                "role": role,
                "capacity_wh": cap,
                "battery_percent": series["battery_percent"][i],
                "battery_wh": series["battery_wh"][i],
                "alive": series["alive"][i],
            })
    rows.sort(key=lambda r: (r["time_hours"], r["node_id"]))
    return rows


def _write_run_summary(result: dict, scen_label: str, out_dir: Path) -> None:
    lines = [
        "Battery simulator — run summary",
        "=" * 60,
        f"Generated (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}",
        f"Scenario: {scen_label}",
        f"Simulation ID: {result['simulation_id']}",
        f"Duration: {result['duration_hours']} h",
        f"Events processed: {result['total_events_processed']}",
        "",
        "Per-node (sorted by final %):",
        "-" * 40,
    ]
    tbl = [(nid, nd["role"], nd["summary"]["final_battery_percent"], nd["summary"]["energy_consumed_wh"])
           for nid, nd in result["nodes"].items()]
    tbl.sort(key=lambda x: x[2])
    for nid, role, pct, wh in tbl:
        lines.append(f"  {nid:<8} {role:<10} {pct:>8.2f}%   {wh:.6f} Wh")
    lines.extend(["", f"Outputs in: {out_dir.resolve()}", ""])
    text = "\n".join(lines)
    (out_dir / "RUN_SUMMARY.txt").write_text(text + "\n", encoding="utf-8")
    print(text)


def verify_minimal_scenario() -> None:
    SECONDS_PER_HOUR = 3600.0

    def wh(p_w: float, t_s: float) -> float:
        return p_w * (t_s / SECONDS_PER_HOUR)

    clean = _strip_doc_keys(dict(_MINIMAL_VERIFY_PAYLOAD))
    s1 = ShamanIConfig()
    s1.apply_optional_scalar_overrides(clean["shaman_i"])
    s2 = ShamanIIConfig()
    s2.apply_optional_scalar_overrides(clean["shaman_ii"])
    radio = RadioConfig()
    for k, v in clean["radio"].items():
        if hasattr(radio, k) and v is not None:
            setattr(radio, k, v)
    t_lora = radio.airtime_per_frame_s()
    frames = radio.frames_per_hop
    dur_h = float(clean["duration_hours"])
    exp_s = dur_h * (s1.P_proc_shaI_active + s1.P_mic) + wh(s1.P_wifi_tx, s1.t_tx_wifi * frames)
    hop_on_s = t_lora * frames
    exp_r = (
        dur_h * (s2.P_controller_sleep + s2.P_lora_rx + s2.P_proc_shaII_sleep)
        + wh(s2.P_wifi_rx, s2.t_rx_wifi)
        + wh(max(0.0, s2.P_proc_shaII_active - s2.P_proc_shaII_sleep), s2.t_proc_shaII)
        + wh(s2.P_lora_tx, hop_on_s)
    )
    out = run_from_dict(clean)
    gs = out["nodes"]["S1"]["summary"]["energy_consumed_wh"]
    gr = out["nodes"]["R1"]["summary"]["energy_consumed_wh"]
    if abs(gs - exp_s) >= 1e-6:
        raise AssertionError(f"sensor Wh mismatch {gs} vs {exp_s}")
    if abs(gr - exp_r) >= 1e-6:
        raise AssertionError(f"relay Wh mismatch {gr} vs {exp_r}")
    cmd = out["nodes"]["CMD1"]["summary"]
    if cmd["energy_consumed_wh"] != 0 or cmd["final_battery_percent"] != 100.0:
        raise AssertionError("gateway should be externally powered with zero drain")
    print("verify_minimal_scenario: OK")


def main() -> None:
    ap = argparse.ArgumentParser(description="Shaman battery simulator")
    ap.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO_PATH)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--verify", action="store_true", help="Regression check (minimal payload baked into this file)")
    args = ap.parse_args()

    if args.verify:
        verify_minimal_scenario()
        return

    scen = args.scenario.resolve()
    if not scen.is_file():
        sys.exit(f"Scenario not found: {scen}")

    raw = json.loads(scen.read_text(encoding="utf-8"))
    events_backup = list(raw.get("events", []))
    clean = _strip_doc_keys(raw)

    out_dir = args.out_dir.resolve()
    if args.overwrite and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"scenario: {scen}")
    print(f"output:   {out_dir}")
    result = run_from_dict(clean)

    rows = _flatten_timeseries_rows(result)
    if rows:
        cols = sorted(rows[0].keys())
        with open(out_dir / "combined_battery_timeseries.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow(r)

    with open(out_dir / "synthetic_events_log.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=("seq", "time_seconds", "time_hours", "node_id", "confirmed", "event_type"),
        )
        w.writeheader()
        for i, e in enumerate(events_backup, start=1):
            t = float(e.get("time") or e.get("timestamp_s", 0))
            w.writerow({
                "seq": i,
                "time_seconds": t,
                "time_hours": round(t / 3600.0, 6),
                "node_id": e.get("node_id"),
                "confirmed": bool(e.get("confirmed", True)),
                "event_type": e.get("event_type", ""),
            })

    with open(out_dir / "full_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    _write_run_summary(result, str(scen), out_dir)
    print(f"Done. Chart: {out_dir / 'combined_battery_timeseries.csv'}")


if __name__ == "__main__":
    main()
