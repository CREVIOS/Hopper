.PHONY: dev dev-up dev-down deploy-local proto frontend api orchestrator test lint ci clean vm-images vm-images-load

# Same checks as GitHub Actions CI (no Docker integration tests)
ci:
	./scripts/ci/run-all.sh

# Development environment
dev-up:
	docker compose up -d

dev-down:
	docker compose down

dev: dev-up
	@echo "Dev services started (Postgres, NATS, Keycloak)"

# Full local deployment (infra + all app services)
deploy-local:
	./scripts/deploy-local.sh

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
	cd services/api-gateway && PYTHONPATH=. poetry run alembic upgrade head

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

# VM template images. The base must build first because the templates
# `FROM hopper/vm-ubuntu:22.04`. After building, load them into the K8s
# runtime if the cluster doesn't pull from a registry (`make vm-images-load`).
vm-images:
	docker build -t hopper/vm-ubuntu:22.04   images/hopper-vm
	docker build -t hopper/vm-python-ml:22.04 images/hopper-vm-python
	docker build -t hopper/vm-cpp:22.04      images/hopper-vm-cpp
	docker build -t hopper/vm-java:22.04     images/hopper-vm-java

# Load locally-built VM images into the K8s runtime (k3s/containerd here).
# Use `minikube image load <tag>` for minikube; adapt to your cluster.
vm-images-load: vm-images
	for tag in hopper/vm-ubuntu:22.04 hopper/vm-python-ml:22.04 hopper/vm-cpp:22.04 hopper/vm-java:22.04; do \
		docker save "$$tag" | sudo k3s ctr images import - ; \
	done

# Cleanup
clean:
	rm -rf frontend/.svelte-kit frontend/node_modules
	rm -rf services/orchestrator/orchestrator
	find . -type d -name __pycache__ -exec rm -rf {} +
