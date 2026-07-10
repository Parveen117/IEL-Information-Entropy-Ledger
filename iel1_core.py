"""
IEL-1 — Information–Entropy Ledger (Restricted Base System)
Foundation (LOCKED):
  F1 Information Invariance: ΔI = 0
  F2 Entropy Directionality: ΔE > 0

This is a minimal, deterministic, local append-only ledger.
No accounts, no identities, no ownership, no networking.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Tuple


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_str(s: str) -> str:
    return _sha256_bytes(s.encode("utf-8"))


def canonical_json(obj: Any) -> str:
    # Deterministic JSON serialization: sorted keys, no whitespace
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def isqrt_abs(x: int) -> int:
    return int(math.isqrt(abs(int(x))))


@dataclass(frozen=True)
class State:
    I: int   # invariant information scalar
    E: int   # global entropy scalar
    theta: int  # irreversible transition count

    def to_dict(self) -> Dict[str, int]:
        return {"I": int(self.I), "E": int(self.E), "theta": int(self.theta)}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "State":
        return State(I=int(d["I"]), E=int(d["E"]), theta=int(d["theta"]))


@dataclass(frozen=True)
class Transition:
    payload: Dict[str, Any]
    effect_units: int

    def to_dict(self) -> Dict[str, Any]:
        return {"payload": self.payload, "effect_units": int(self.effect_units)}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Transition":
        return Transition(payload=dict(d["payload"]), effect_units=int(d["effect_units"]))


@dataclass(frozen=True)
class Entry:
    index: int
    prev_hash: str
    state_hash: str
    tau_hash: str
    theta: int
    commit_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": int(self.index),
            "prev_hash": self.prev_hash,
            "state_hash": self.state_hash,
            "tau_hash": self.tau_hash,
            "theta": int(self.theta),
            "commit_hash": self.commit_hash,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Entry":
        return Entry(
            index=int(d["index"]),
            prev_hash=str(d["prev_hash"]),
            state_hash=str(d["state_hash"]),
            tau_hash=str(d["tau_hash"]),
            theta=int(d["theta"]),
            commit_hash=str(d["commit_hash"]),
        )


def delta_entropy(effect_units: int) -> int:
    # Day C (Entropy Logic bound): ΔE = 1 + isqrt(|effect_units|)
    return 1 + isqrt_abs(effect_units)


def apply(state: State, tau: Transition) -> State:
    # APPLY never rejects; it deterministically computes Σ'
    dE = delta_entropy(tau.effect_units)
    return State(I=state.I, E=state.E + dE, theta=state.theta + 1)


def admissible(state: State, next_state: State) -> bool:
    # Day B (minimal admissibility)
    return (
        next_state.I == state.I and
        next_state.E > state.E and
        next_state.theta == state.theta + 1
    )


def hash_state(state: State) -> str:
    return sha256_str(canonical_json(state.to_dict()))


def hash_transition(tau: Transition) -> str:
    return sha256_str(canonical_json(tau.to_dict()))


def commit_entry(index: int, prev_hash: str, next_state: State, tau: Transition) -> Entry:
    state_hash = hash_state(next_state)
    tau_hash = hash_transition(tau)
    material = f"{index}|{prev_hash}|{state_hash}|{tau_hash}|{next_state.theta}"
    commit_hash = sha256_str(material)
    return Entry(
        index=index,
        prev_hash=prev_hash,
        state_hash=state_hash,
        tau_hash=tau_hash,
        theta=next_state.theta,
        commit_hash=commit_hash,
    )


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def effect_units_from_hex_tail(hex_hash: str, tail_hex_digits: int = 6) -> int:
    # Deterministic mapping: last N hex digits -> int
    tail = hex_hash[-tail_hex_digits:]
    return int(tail, 16)



def merkle_root_hex(hex_list: List[str]) -> str:
    """Deterministic Merkle root from a list of hex-encoded SHA-256 hashes.

    Rules:
      - If list is empty: return SHA256("EMPTY")
      - Sort outside this function if you want canonical ordering; this function assumes the input
        order is already canonical.
      - If a layer has odd length: duplicate the last element (standard deterministic padding).
    """
    if not hex_list:
        return sha256_str("EMPTY")
    layer = [bytes.fromhex(h) for h in hex_list]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        nxt = []
        for i in range(0, len(layer), 2):
            nxt.append(hashlib.sha256(layer[i] + layer[i+1]).digest())
        layer = nxt
    return layer[0].hex()

def build_transition_for_file(path: str, payload_extra: Optional[Dict[str, Any]] = None) -> Tuple[Transition, str]:
    sha = file_sha256(path)
    eu = effect_units_from_hex_tail(sha, tail_hex_digits=6)
    payload = {"type": "file_proof", "file_name": path.split("/")[-1], "sha256": sha}
    if payload_extra:
        payload.update(payload_extra)
    return Transition(payload=payload, effect_units=eu), sha
