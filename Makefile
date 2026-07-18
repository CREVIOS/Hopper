.PHONY: help dev dev-up dev-down deploy-local proto frontend api orchestrator test lint clean vm-images vm-images-load frontend-validate test-unit test-integration test-integration-keycloak test-integration-nats test-frontend test-orchestrator test-contract test-migrate test-e2e test-e2e-real test-e2e-real-stack test-load-smoke test-load test-load-stress test-load-spike test-load-soak test-security test-chaos test-coverage test-all test-ci test-services-up test-services-down test-service-logs test-real-stack-up test-real-stack-down test-real-stack-logs test-clean

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
help:
	@./scripts/test/run.sh help

frontend-validate:
	@./scripts/test/run.sh frontend-validate

test-unit:
	@./scripts/test/run.sh test-unit

test-integration:
	@./scripts/test/run.sh test-integration

test-integration-keycloak:
	@./scripts/test/run.sh test-integration-keycloak

test-integration-nats:
	@./scripts/test/run.sh test-integration-nats

test-frontend:
	@./scripts/test/run.sh test-frontend

test-orchestrator:
	@./scripts/test/run.sh test-orchestrator

test-contract:
	@./scripts/test/run.sh test-contract

test-migrate:
	@./scripts/test/run.sh test-migrate

test-e2e:
	@./scripts/test/run.sh test-e2e

test-e2e-real:
	@./scripts/test/run.sh test-e2e-real

test-e2e-real-stack:
	@./scripts/test/run.sh test-e2e-real-stack

test-load-smoke:
	@./scripts/test/run.sh test-load-smoke

test-load:
	@./scripts/test/run.sh test-load

test-load-stress:
	@./scripts/test/run.sh test-load-stress

test-load-spike:
	@./scripts/test/run.sh test-load-spike

test-load-soak:
	@./scripts/test/run.sh test-load-soak

test-security:
	@./scripts/test/run.sh test-security

test-chaos:
	@./scripts/test/run.sh test-chaos

test-coverage:
	@./scripts/test/run.sh test-coverage

test-all:
	@./scripts/test/run.sh test-all

test-ci:
	@./scripts/test/run.sh test-ci

test-services-up:
	@./scripts/test/run.sh test-services-up

test-services-down:
	@./scripts/test/run.sh test-services-down

test-service-logs:
	@./scripts/test/run.sh test-service-logs

test-real-stack-up:
	@./scripts/test/run.sh test-real-stack-up

test-real-stack-down:
	@./scripts/test/run.sh test-real-stack-down

test-real-stack-logs:
	@./scripts/test/run.sh test-real-stack-logs

test-clean:
	@./scripts/test/run.sh test-clean

test: test-unit test-integration

# Linting
lint:
	cd frontend && npx eslint .
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
