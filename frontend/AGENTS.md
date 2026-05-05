# frontend/AGENTS.md

## Frontend review guidelines

Pay special attention to:

- UI fields that rename backend fields in misleading ways.
- Status badges that imply exactness when backend confidence is degraded.
- Components that call mutation endpoints from passive dashboard/read views.
- Missing loading, stale, empty, and error states.
- API response assumptions that are not represented in backend schemas.
- Operator controls without clear confirmation or disabled states.
