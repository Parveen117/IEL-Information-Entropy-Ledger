# Security Policy

IEL is an experimental and research-grade implementation.

It should not be used as the sole security, integrity, financial, identity, audit, evidentiary, or legal-finality control for a production system.

The public code demonstrates deterministic serialization, SHA-256 commitments, append-only JSONL records, chained hashes, local state snapshots, file-proof commitments, and basic verification.

It does not independently provide authentication, authorization, secure key management, HSM/KMS integration, distributed consensus, trusted timestamping, encryption, secure networking, rollback-resistant storage, regulatory compliance, or post-quantum security.

Production use requires independent review, protected keys, established cryptographic libraries, access controls, audit logging, secure storage, versioning, concurrency controls, threat modelling, and penetration testing.
