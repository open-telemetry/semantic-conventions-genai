<!--- Hugo front matter used to generate the website version of this page:
linkTitle: Agent Action Gate & Ledger
--->

# Semantic Conventions for AI Agent Action Gate & Cryptographic Ledgers

**Status**: [Development][DocumentStatus]

This document defines semantic conventions for recording **Gate/Prove runtime safety evaluations, tool tiers, simulation modes, and cryptographic action ledgers** in AI Agent spans.

---

## Zero-Trust Agent Execution Conventions

When an autonomous agent invokes tools with potential side-effects (e.g., executing commands, modifying databases, provisioning cloud resources), spans MUST capture the deterministic policy evaluation and audit receipt.

### Attributes

| Attribute | Type | Description | Examples |
|---|---|---|---|
| `gen_ai.agent.tool.disposition` | string (enum) | Operational decision disposition | `allow`, `simulate`, `deny` |
| `gen_ai.agent.tool.tier` | string (enum) | Tool sensitivity tier | `read`, `write`, `destructive`, `provision`, `decommission` |
| `gen_ai.agent.tool.never_equate_intent_to_approval` | boolean | Policy invariant flag | `true` |
| `gen_ai.agent.action_ledger.receipt_hash` | string | SHA-256 hash of the append-only ledger entry | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `gen_ai.agent.kill_switch_engaged` | boolean | Whether an atomic kill-switch was active | `false` |

---

## Compliance Crosswalk

These attributes map directly to international AI governance and security frameworks:
- **ISO 42001 (A.6.2):** Continuous validation and authorization of AI decisions.
- **NIST AI RMF (GOVERN-1.2 & MANAGE-2.4):** Human-in-the-loop oversight and fail-safe mechanisms for autonomous actions.
- **SOC 2 Type II (CC6.8):** Immutable audit trails for automated configuration changes.

[DocumentStatus]: https://opentelemetry.io/docs/specs/otel/document-status
