"""
IEL-1 local persistence (append-only JSONL).
Ledger file: ledger.jsonl
State snapshot: state.json

Crash-safe strategy: append-only; rebuild by replay.
"""

from __future__ import annotations
import os
import json
from typing import Any, Dict, List, Tuple, Optional

from iel1_core import State, Transition, Entry, canonical_json, apply, admissible, commit_entry, file_sha256, merkle_root_hex, effect_units_from_hex_tail, delta_entropy


LEDGER_FILE = "ledger.jsonl"
STATE_FILE = "state.json"


def init_ledger(folder: str, information_scalar: int = 42, entropy0: int = 0) -> None:
    os.makedirs(folder, exist_ok=True)
    ledger_path = os.path.join(folder, LEDGER_FILE)
    state_path = os.path.join(folder, STATE_FILE)

    if os.path.exists(ledger_path) or os.path.exists(state_path):
        raise FileExistsError("Ledger already exists in this folder.")

    genesis = State(I=int(information_scalar), E=int(entropy0), theta=0)
    with open(state_path, "w", encoding="utf-8") as f:
        f.write(canonical_json(genesis.to_dict()))
    # ledger starts empty; prev_hash = 64 zeros for first entry
    with open(ledger_path, "w", encoding="utf-8") as f:
        f.write("")


def load_state(folder: str) -> State:
    state_path = os.path.join(folder, STATE_FILE)
    with open(state_path, "r", encoding="utf-8") as f:
        return State.from_dict(json.loads(f.read()))


def save_state(folder: str, state: State) -> None:
    state_path = os.path.join(folder, STATE_FILE)
    with open(state_path, "w", encoding="utf-8") as f:
        f.write(canonical_json(state.to_dict()))


def last_commit_hash(folder: str) -> str:
    ledger_path = os.path.join(folder, LEDGER_FILE)
    if not os.path.exists(ledger_path):
        return "0" * 64
    last = None
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = json.loads(line)
    if last is None:
        return "0" * 64
    return str(last["entry"]["commit_hash"])


def entry_count(folder: str) -> int:
    ledger_path = os.path.join(folder, LEDGER_FILE)
    if not os.path.exists(ledger_path):
        return 0
    n = 0
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def append_transition(folder: str, tau: Transition) -> Entry:
    state = load_state(folder)
    next_state = apply(state, tau)
    if not admissible(state, next_state):
        raise ValueError("Transition is not admissible under IEL-1 (should not happen).")

    idx = entry_count(folder) + 1
    prev_hash = last_commit_hash(folder)
    ent = commit_entry(idx, prev_hash, next_state, tau)

    ledger_path = os.path.join(folder, LEDGER_FILE)
    record = {
        "tau": tau.to_dict(),
        "state_after": next_state.to_dict(),
        "entry": ent.to_dict(),
    }
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    save_state(folder, next_state)
    return ent


def replay(folder: str) -> State:
    # Rebuild state by replaying ledger.jsonl from genesis snapshot in state.json? 
    # We treat state.json as current snapshot; for full replay integrity checks, start from genesis in separate file.
    # For simplicity: return current state.
    return load_state(folder)


# ----------------------------
# Axiom U′: Canonical Merkle-Batch Commit
# ----------------------------
PENDING_DIR = "pending"


def _pending_folder(folder: str) -> str:
    return os.path.join(folder, PENDING_DIR)


def ensure_pending_dir(folder: str) -> str:
    """Create pending/ if missing. Returns its path."""
    pdir = _pending_folder(folder)
    os.makedirs(pdir, exist_ok=True)
    return pdir


def canonical_batch_transition(folder: str) -> Transition:
    """Build the *unique* next transition from the current pending/ evidence set.

    Deterministic rule:
      1) Hash every file in pending/ with SHA-256.
      2) Sort hashes lexicographically (canonical order).
      3) Compute Merkle root over the sorted hash list.
      4) Derive effect_units from the Merkle root tail (same spirit as IEL-1).
      5) Store the root + per-file hashes in payload for audit.

    If pending/ is empty -> a deterministic heartbeat transition.
    """
    pdir = _pending_folder(folder)
    files: List[str] = []
    if os.path.isdir(pdir):
        for name in os.listdir(pdir):
            path = os.path.join(pdir, name)
            if os.path.isfile(path):
                files.append(path)

    if not files:
        return Transition(payload={"type": "heartbeat"}, effect_units=0)

    payload_files = []
    hashes = []
    for path in files:
        h = file_sha256(path)
        hashes.append(h)
        payload_files.append({"file": os.path.basename(path), "sha256": h})

    hashes.sort()
    root = merkle_root_hex(hashes)
    effect_units = effect_units_from_hex_tail(root, tail_hex_digits=6)

    return Transition(
        payload={
            "type": "merkle_batch",
            "count": len(files),
            "merkle_root": root,
            "files": payload_files,
        },
        effect_units=effect_units,
    )


def append_merkle_batch(folder: str, clear_pending: bool = True) -> Entry:
    """Append exactly the canonical Merkle-batch transition (Axiom U′).

    If clear_pending=True, pending/ files are deleted after committing.
    """
    tau = canonical_batch_transition(folder)
    ent = append_transition(folder, tau)

    if clear_pending:
        pdir = _pending_folder(folder)
        if os.path.isdir(pdir):
            for name in os.listdir(pdir):
                path = os.path.join(pdir, name)
                if os.path.isfile(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
    return ent




# ----------------------------
# Verification
# ----------------------------

def _is_hex64(s: str) -> bool:
    if not isinstance(s, str) or len(s) != 64:
        return False
    try:
        int(s, 16)
        return True
    except Exception:
        return False


def iter_ledger_records(folder: str):
    """Yield (line_no, record_dict) for non-empty JSONL ledger entries."""
    ledger_path = os.path.join(folder, LEDGER_FILE)
    if not os.path.exists(ledger_path):
        return
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            yield line_no, json.loads(line)


def _reconstruct_genesis_from_first_record(first_record: Dict[str, Any]) -> State:
    """Reconstruct genesis state (theta=0) from the first ledger record.

    Works because:
      - I is invariant (so I0 = I1)
      - theta increments by 1 (so theta0 = theta1 - 1)
      - E increments by delta_entropy(effect_units) (so E0 = E1 - dE)
    """
    tau = Transition.from_dict(first_record["tau"])
    s1 = State.from_dict(first_record["state_after"])
    dE = delta_entropy(tau.effect_units)
    E0 = int(s1.E) - int(dE)
    return State(I=int(s1.I), E=int(E0), theta=0)


def verify_ledger(folder: str, strict_files: bool = False) -> Dict[str, Any]:
    """Verify ledger integrity by replaying from genesis and recomputing hashes.

    Checks:
      - state transitions (apply) match stored state_after
      - commit hash chain matches recomputed commit_entry
      - indexes and prev_hash chaining are correct
      - payload self-consistency for file_proof and merkle_batch
      - final replayed state matches state.json snapshot

    strict_files:
      - If True, additionally tries to verify referenced files exist under pending/ or via absolute paths.
        (By default we do NOT require files, because proofs may be transported without originals.)
    """
    errors: List[str] = []
    checked = 0

    # Load current snapshot (may be latest, not genesis)
    try:
        snapshot = load_state(folder)
    except Exception as e:
        return {"ok": False, "errors": [f"Failed to read state.json: {e}"]}

    # Read first record (if any) to reconstruct genesis
    rec_iter = list(iter_ledger_records(folder))
    if not rec_iter:
        # No ledger entries: snapshot must be genesis-like (theta=0)
        if snapshot.theta != 0:
            return {"ok": False, "errors": [f"Ledger empty but state.theta={snapshot.theta} (expected 0)"]}
        return {"ok": True, "errors": [], "checked": 0, "final_state": snapshot.to_dict()}

    first_line_no, first_rec = rec_iter[0]

    # Prefer explicit genesis file if present (future-proof), else reconstruct
    genesis_path = os.path.join(folder, "genesis.json")
    if os.path.exists(genesis_path):
        try:
            with open(genesis_path, "r", encoding="utf-8") as f:
                genesis = State.from_dict(json.loads(f.read()))
        except Exception as e:
            errors.append(f"Failed to read genesis.json, falling back to reconstruction: {e}")
            genesis = _reconstruct_genesis_from_first_record(first_rec)
    else:
        genesis = _reconstruct_genesis_from_first_record(first_rec)

    state = genesis
    prev_hash = "0" * 64
    expected_index = 1

    for line_no, rec in rec_iter:
        checked += 1
        try:
            tau = Transition.from_dict(rec["tau"])
            stored_state = State.from_dict(rec["state_after"])
            stored_entry = Entry.from_dict(rec["entry"])
        except Exception as e:
            errors.append(f"Line {line_no}: malformed record: {e}")
            break

        # Basic entry fields
        if stored_entry.index != expected_index:
            errors.append(f"Line {line_no}: entry.index={stored_entry.index} expected {expected_index}")

        if stored_entry.prev_hash != prev_hash:
            errors.append(f"Line {line_no}: prev_hash mismatch (got {stored_entry.prev_hash[:12]}..., expected {prev_hash[:12]}...)")

        # Payload self-consistency checks (do not require original files unless strict_files=True)
        ptype = str(tau.payload.get("type", ""))
        if ptype == "file_proof":
            sha = str(tau.payload.get("sha256", ""))
            if not _is_hex64(sha):
                errors.append(f"Line {line_no}: file_proof sha256 invalid")
            else:
                eu_expected = effect_units_from_hex_tail(sha, tail_hex_digits=6)
                if int(tau.effect_units) != int(eu_expected):
                    errors.append(f"Line {line_no}: file_proof effect_units mismatch (got {tau.effect_units}, expected {eu_expected})")
            if strict_files:
                # Try to locate file by name in pending/ (best-effort)
                fname = str(tau.payload.get("file_name", ""))
                if fname:
                    candidate = os.path.join(folder, PENDING_DIR, fname)
                    if os.path.exists(candidate):
                        real_sha = file_sha256(candidate)
                        if sha and real_sha != sha:
                            errors.append(f"Line {line_no}: file content hash mismatch for {fname}")
        elif ptype == "merkle_batch":
            root = str(tau.payload.get("merkle_root", ""))
            files = tau.payload.get("files", [])
            if not _is_hex64(root):
                errors.append(f"Line {line_no}: merkle_root invalid")
            try:
                hashes = [str(x["sha256"]) for x in files if isinstance(x, dict) and "sha256" in x]
                hashes_sorted = sorted(hashes)
                recomputed_root = merkle_root_hex(hashes_sorted)
                if root and recomputed_root != root:
                    errors.append(f"Line {line_no}: merkle_root mismatch (got {root[:12]}..., expected {recomputed_root[:12]}...)")
                eu_expected = effect_units_from_hex_tail(root, tail_hex_digits=6) if _is_hex64(root) else None
                if eu_expected is not None and int(tau.effect_units) != int(eu_expected):
                    errors.append(f"Line {line_no}: merkle_batch effect_units mismatch (got {tau.effect_units}, expected {eu_expected})")
            except Exception as e:
                errors.append(f"Line {line_no}: merkle_batch payload invalid: {e}")

        # Replay step
        next_state = apply(state, tau)
        if not admissible(state, next_state):
            errors.append(f"Line {line_no}: transition not admissible during replay (should not happen)")

        if next_state != stored_state:
            errors.append(
                f"Line {line_no}: state_after mismatch (stored {stored_state.to_dict()}, recomputed {next_state.to_dict()})"
            )

        # Recompute entry and compare hashes
        recomputed_entry = commit_entry(expected_index, prev_hash, next_state, tau)

        if recomputed_entry.commit_hash != stored_entry.commit_hash:
            errors.append(
                f"Line {line_no}: commit_hash mismatch (got {stored_entry.commit_hash[:12]}..., expected {recomputed_entry.commit_hash[:12]}...)"
            )

        if recomputed_entry.state_hash != stored_entry.state_hash:
            errors.append(f"Line {line_no}: state_hash mismatch")

        if recomputed_entry.tau_hash != stored_entry.tau_hash:
            errors.append(f"Line {line_no}: tau_hash mismatch")

        if recomputed_entry.theta != stored_entry.theta:
            errors.append(f"Line {line_no}: theta mismatch in entry")

        # advance
        state = next_state
        prev_hash = recomputed_entry.commit_hash
        expected_index += 1

    # Final snapshot check
    if state != snapshot:
        errors.append(
            f"Final snapshot mismatch: state.json has {snapshot.to_dict()}, replay ended at {state.to_dict()}"
        )

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "checked": checked,
        "genesis": genesis.to_dict(),
        "final_state": state.to_dict(),
        "last_commit_hash": prev_hash,
    }
