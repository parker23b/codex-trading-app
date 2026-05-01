.PHONY: install-hooks audit audit-backend audit-frontend audit-fast

install-hooks:
	cd backend && source .venv/bin/activate && cd .. && pre-commit install

audit-fast:
	cd backend && source .venv/bin/activate && cd .. && pre-commit run --all-files

audit-backend:
	cd backend && source .venv/bin/activate && ruff check .
	cd backend && source .venv/bin/activate && ruff format . --check
	cd backend && source .venv/bin/activate && pyright .
	cd backend && source .venv/bin/activate && pytest
	cd backend && source .venv/bin/activate && vulture app tests --min-confidence 80
	cd backend && source .venv/bin/activate && bandit -r app
	cd backend && source .venv/bin/activate && pip-audit

audit-frontend:
	cd frontend && npm run lint
	cd frontend && npm run typecheck
	cd frontend && npm run audit:unused
	cd frontend && npm run audit:arch
	cd frontend && npm audit --audit-level=moderate

audit: audit-backend audit-frontend
