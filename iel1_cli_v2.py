"""
IEL-1 CLI (Anaconda friendly)

Usage:
  python iel1_cli.py init --dir ./my_ledger --I 42
  python iel1_cli.py commit-effect --dir ./my_ledger --effect 123 --note "test"
  python iel1_cli.py commit-file --dir ./my_ledger --file "MyPaper.pdf"
  python iel1_cli.py commit-batch --dir ./my_ledger
  python iel1_cli.py show --dir ./my_ledger
"""

from __future__ import annotations
import argparse
import json
import os
from datetime import datetime, UTC

from iel1_core import Transition, build_transition_for_file, canonical_json
from iel1_storage_v2 import init_ledger, load_state, append_transition, append_merkle_batch, ensure_pending_dir, LEDGER_FILE, verify_ledger


def cmd_init(args):
    init_ledger(args.dir, information_scalar=args.I, entropy0=args.E)
    print("OK: initialized ledger at", args.dir)
    print("Genesis:", load_state(args.dir))


def cmd_commit_effect(args):
    payload = {
        "type": "effect",
        "note": args.note or "",
        "ts_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    tau = Transition(payload=payload, effect_units=int(args.effect))
    ent = append_transition(args.dir, tau)
    print("OK: committed")
    print("commit_hash:", ent.commit_hash)


def cmd_commit_file(args):
    tau, sha = build_transition_for_file(args.file, payload_extra={
        "note": args.note or "",
        "ts_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    })
    ent = append_transition(args.dir, tau)
    print("OK: committed file proof")
    print("file_sha256:", sha)
    print("effect_units:", tau.effect_units)
    print("commit_hash:", ent.commit_hash)




def cmd_commit_batch(args):
    # Ensure pending/ exists so the user knows where to drop files
    ensure_pending_dir(args.dir)
    ent = append_merkle_batch(args.dir)
    print("OK: committed canonical Merkle batch")
    print("commit_hash:", ent.commit_hash)


def cmd_verify(args):
    report = verify_ledger(args.dir, strict_files=args.strict_files)
    if report.get("ok"):
        print("OK: ledger verified")
        print("checked_entries:", report.get("checked"))
        print("genesis:", report.get("genesis"))
        print("final_state:", report.get("final_state"))
        print("last_commit_hash:", report.get("last_commit_hash"))
    else:
        print("FAIL: ledger verification failed")
        print("checked_entries:", report.get("checked"))
        for e in report.get("errors", []):
            print(" -", e)
        # exit code non-zero (best effort)
        raise SystemExit(2)

def cmd_show(args):
    state = load_state(args.dir)
    print("Current State:", state)
    ledger_path = os.path.join(args.dir, LEDGER_FILE)
    if not os.path.exists(ledger_path):
        print("No ledger file found.")
        return
    print("\n--- ledger entries (tail) ---")
    tail_n = args.tail
    lines = []
    with open(ledger_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                lines.append(line.strip())
    for line in lines[-tail_n:]:
        rec = json.loads(line)
        print("index:", rec["entry"]["index"], "commit_hash:", rec["entry"]["commit_hash"], "theta:", rec["entry"]["theta"])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_init = sub.add_parser("init")
    ap_init.add_argument("--dir", required=True)
    ap_init.add_argument("--I", type=int, default=42)
    ap_init.add_argument("--E", type=int, default=0)
    ap_init.set_defaults(func=cmd_init)

    ap_ce = sub.add_parser("commit-effect")
    ap_ce.add_argument("--dir", required=True)
    ap_ce.add_argument("--effect", required=True, type=int)
    ap_ce.add_argument("--note", default="")
    ap_ce.set_defaults(func=cmd_commit_effect)

    ap_cf = sub.add_parser("commit-file")
    ap_cf.add_argument("--dir", required=True)
    ap_cf.add_argument("--file", required=True)
    ap_cf.add_argument("--note", default="")
    ap_cf.set_defaults(func=cmd_commit_file)

    
    ap_cb = sub.add_parser("commit-batch")
    ap_cb.add_argument("--dir", required=True)
    ap_cb.set_defaults(func=cmd_commit_batch)

    ap_show = sub.add_parser("show")
    ap_show.add_argument("--dir", required=True)
    ap_show.add_argument("--tail", type=int, default=10)
    ap_show.set_defaults(func=cmd_show)


    ap_v = sub.add_parser("verify")
    ap_v.add_argument("--dir", required=True)
    ap_v.add_argument("--strict-files", action="store_true", help="Also verify referenced file contents when available under pending/")
    ap_v.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
