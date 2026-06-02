# Readiness And Safe Usage

InvestMate is **not ready for live trading** and is **not automatically ready for a supervised broker-connected demo**.

A local UI/research demo with broker dealing disabled is currently acceptable when the safe posture below is followed.

## Current CI Truth

The newest successful GitHub Actions `Repo Audit` run is [26776683955](https://github.com/parker23b/codex-trading-app/actions/runs/26776683955).

- `Verify backend lockfiles`: passed
- `Migration and drift tests`: passed
- `Postgres migration rehearsal`: passed with exactly `5 passed` and zero skips
- backend `Pytest`: passed

Advisory annotations still exist in that run, including Node 20 deprecation warnings and non-blocking lint/type warnings, but they do not negate the successful required backend verification path above.

## Current Closure Inventory

There is **no current code-actionable P0 or P1 defect** in the reviewed closure slice.

The remaining items are one or more of: documented limitations, manual security actions, or future production hardening.

| Finding | Classification | Current meaning |
| --- | --- | --- |
| `AUDIT-UI-006` | `CLOSED_CURRENT_SCOPE` | Closed for the reviewed events/live/dashboard/control-plane/markets surface inventory. Keep the same browser discipline for future surface growth. |
| `AUDIT-LIFE-005` | `CLOSED_CURRENT_SCOPE` | Current simulated-vs-broker-confirmed operator-visible provenance slice is closed. |
| `AUDIT-005` | `CLOSED_CURRENT_SCOPE` | Current backend/frontend operator-vocabulary parity slice is closed. |
| `AUDIT-UI-002` | `CLOSED_CURRENT_SCOPE` | Current reviewed unknown/degraded enum-truth slice is closed. |
| `AUDIT-UI-004` | `CLOSED_CURRENT_SCOPE` | Current reviewed mutation-control family slice is closed. |
| `AUDIT-UI-005` | `CLOSED_CURRENT_SCOPE` | Current reviewed provenance/parity slice is closed. |
| `AUDIT-DB-001` | `DOCUMENTED_LIMITATION` | CI truth is closed; the remaining limitation is the legacy unversioned non-SQLite manual-upgrade path. Use a fresh versioned database unless a reviewed legacy migration exists. |
| `AUDIT-SEC-002` | `DOCUMENTED_LIMITATION` | The reviewed operator/API/events projection and redaction boundary is fixed for the current surface set. Raw internal authority identifiers remain acceptable internally and must stay behind the current projection/redaction boundary. |
| `AUDIT-SEC-003` | `MANUAL_SECURITY_ACTION` | Repository-history cleanup and any needed credential rotation remain manual actions outside code changes. |
| `AUDIT-DEP-001` | `FUTURE_PRODUCTION_HARDENING` | Stronger provenance attestation, editable-package hardening, and broader host/container dependency scanning remain future production work. |

### Local UI/research demo with dealing disabled

This is currently acceptable if all of the following stay true:

1. `IG_TRADING_ENABLED=false`
2. No broker mutation is attempted.
3. Test-only controls remain explicitly gated and disabled unless you are in an approved dev/test workflow.
4. The session is treated as UI review, operator research, broker-read investigation, or smoke testing only.

Recommended smoke-test order:

1. Start with `IG_TRADING_ENABLED=false`.
2. Verify `/health`, `/system/health`, `/dashboard`, `/control-plane/summary`, and `/events`.
3. Verify test-only controls are hidden unless explicitly enabled for dev/test.
4. Verify degraded broker-read and freshness states remain clearly labelled when credentials or data are unavailable.
5. Only after that review should you consider a supervised broker-connected session.

### Supervised broker-connected demo

This is **not automatically approved** by the current repository state.

Minimum blockers or human sign-offs still required:

1. Use a **fresh versioned database** for the demo. Do not use an existing unversioned non-SQLite database unless a reviewed migration path exists.
2. Resolve or explicitly sign off the `AUDIT-SEC-003` manual security posture:
   - purge historical SQLite DB blobs before any broader sharing or publication;
   - rotate any local/demo credentials if the repository or workstation state was shared.
3. Run the final smoke test with `IG_TRADING_ENABLED=false` first, then enable broker connectivity only for the supervised session you intend to observe.
4. Confirm test-only controls remain explicitly gated during the broker-connected session.

Not a blocker at this level:

- Stronger supply-chain attestation/signing is **not** a supervised-demo blocker in the current closure inventory.
- Intentionally retained raw internal authority identifiers are acceptable with the current reviewed projection/redaction boundary and should not be treated as a current defect on their own.

### Live trading

Live trading is still blocked.

Additional production-only hardening still required beyond the supervised-demo minimum:

1. Complete the manual history-cleanup and any required credential-rotation work with actual verification, not documentation alone.
2. Move beyond the fresh-database-only demo posture to a production-grade reviewed migration story for legacy/non-SQLite environments.
3. Add stronger supply-chain provenance controls, including attestation/signing and broader host/container dependency scanning.
4. Keep expanding operator/browser evidence, operational runbooks, and production supervision controls as the surface area evolves.

## Historical Notes

Historical remediation slices are preserved in [docs/audit-status.md](audit-status.md).

Treat those dated entries as **historical-at-the-time evidence**, not as the current readiness snapshot.
