.PHONY: dev dev-up dev-down proto frontend api orchestrator test lint clean

# Development environment
dev-up:
	docker compose up -d

dev-down:
	docker compose down

dev: dev-up
	@echo "Dev services started (Postgres, NATS, Keycloak)"

# Code generation
proto:
	./scripts/generate-proto.sh

# Frontend
frontend-install:
	cd frontend && pnpm install

frontend-dev:
	cd frontend && pnpm dev

frontend-build:
	cd frontend && pnpm build

# API Gateway
api-install:
	cd services/api-gateway && poetry install

api-dev:
	cd services/api-gateway && poetry run uvicorn app.main:app --reload --port 8000

api-migrate:
	cd services/api-gateway && poetry run alembic upgrade head

# Orchestrator
orchestrator-build:
	cd services/orchestrator && go build ./cmd/orchestrator/

orchestrator-dev:
	cd services/orchestrator && go run ./cmd/orchestrator/

# Testing
test-unit:
	cd services/api-gateway && poetry run pytest tests/unit/ -v
	cd services/orchestrator && go test ./... -v -race

test-integration:
	cd services/api-gateway && poetry run pytest tests/integration/ -v

test-e2e:
	cd tests/e2e && npx playwright test

test-load:
	cd tests/load && k6 run class-start.js

test: test-unit test-integration

# Linting
lint:
	cd frontend && pnpm lint
	cd services/api-gateway && poetry run ruff check .
	cd services/orchestrator && golangci-lint run

# Cleanup
clean:
	rm -rf frontend/.svelte-kit frontend/node_modules
	rm -rf services/orchestrator/orchestrator
	find . -type d -name __pycache__ -exec rm -rf {} +
