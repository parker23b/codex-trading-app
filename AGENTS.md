# AGENTS.md

## Spec-driven development rules

This repository uses spec-driven development.

Before implementing, reviewing, or auditing behaviour, read:

- docs/spec/00-product-intent.md
- docs/spec/01-domain-glossary.md
- docs/spec/02-system-architecture.md
- docs/spec/03-broker-contract.md
- docs/spec/04-backend-api-contract.md
- docs/spec/05-frontend-operator-ui-contract.md
- docs/spec/06-end-to-end-flows.md
- docs/spec/07-state-machines.md
- docs/spec/08-risk-allocation-invariants.md
- docs/spec/09-aimee-read-only-contract.md
- docs/spec/10-testing-contract.md
- docs/spec/99-spec-coverage-matrix.md

## Review guidelines

When reviewing code, classify findings as:

- P0: Can cause unsafe trading behaviour, incorrect broker mutation, hidden state corruption, or false operator confidence.
- P1: Violates a documented spec invariant, breaks a core flow, weakens tests around critical behaviour, or creates misleading UI.
- P2: Maintainability, duplication, unclear ownership, missing docs, weak tests outside core trading flows.
- P3: Minor cleanup.

Every review finding must include:

- Spec ID violated or affected.
- Code evidence.
- Test evidence, or state that no test evidence exists.
- Confidence: High, Medium, Low.
- Suggested remediation.

Do not claim a behaviour is correct unless it is supported by code evidence and, for critical flows, test evidence.

If code and spec disagree, say whether:

- code appears wrong
- spec appears stale
- behaviour is ambiguous
- more evidence is needed

Prioritize serious issues. Avoid commenting on style unless it affects correctness or maintainability.
