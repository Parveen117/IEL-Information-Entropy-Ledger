# IEL Information–Entropy Ledger

IEL is a deterministic, local, append-only ledger for recording state transitions, file proofs, and machine-verifiable integrity evidence.

## Core model

The public state is represented as `State(I, E, θ)` where:

- `I` remains invariant;
- `E` increases under accepted transitions;
- `θ` increases by one for each accepted transition.

Each accepted transition is written to an append-only JSONL ledger using deterministic serialization and SHA-256 commitments.

## Files

- `iel1_core.py` — state, transition, hashing, admissibility, and commitment logic.
- `iel1_storage_v2.py` — local persistence and ledger verification.
- `iel1_cli_v2.py` — command-line interface.
- `sample_evidence.txt` — public demonstration input.
- `demo_ledger/` — reproducible demonstration ledger.

## Quick start

```bash
python iel1_cli_v2.py init --dir my_ledger --I 42
python iel1_cli_v2.py commit-effect --dir my_ledger --effect 123 --note "demo"
python iel1_cli_v2.py commit-file --dir my_ledger --file sample_evidence.txt --note "file proof"
python iel1_cli_v2.py verify --dir my_ledger
python iel1_cli_v2.py show --dir my_ledger --tail 10
```

## Status

This is an experimental, research-grade technical release. It is not a cryptocurrency, financial ledger, identity system, production blockchain, trusted timestamp authority, or legal proof system.

## Public boundary

The release excludes complete patent specifications, unpublished claim strategy, private notebooks, historical private ledgers, confidential research files, local source paths, credentials, keys, deployment configuration, and undisclosed hardware embodiments.

See `PATENT_NOTICE.md`, `SECURITY.md`, and `docs/PUBLIC_RELEASE_BOUNDARY.md`.

## Names

Publication and citation name: **Monty Dabas**

Legal rights holder: **Parveen**

## Version

`v1.0.0`
