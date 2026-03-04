#!/usr/bin/env bash
set -euo pipefail

echo "=== Hopper Dev Environment Setup ==="

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed."; exit 1; }
command -v pnpm >/dev/null 2>&1 || { echo "pnpm is required. Install: npm i -g pnpm"; exit 1; }
command -v poetry >/dev/null 2>&1 || { echo "Poetry is required. Install: pip install poetry"; exit 1; }
command -v go >/dev/null 2>&1 || { echo "Go is required. Install from https://go.dev/dl/"; exit 1; }

# Start infrastructure services
echo "Starting Postgres, NATS, Keycloak..."
docker compose up -d

# Wait for services
echo "Waiting for PostgreSQL..."
until docker compose exec -T postgres pg_isready -U hopper > /dev/null 2>&1; do
  sleep 1
done
echo "PostgreSQL is ready."

# Install frontend dependencies
echo "Installing frontend dependencies..."
cd frontend && pnpm install && cd ..

# Install API gateway dependencies
echo "Installing API gateway dependencies..."
cd services/api-gateway && poetry install && cd ../..

# Run database migrations
echo "Running database migrations..."
cd services/api-gateway && poetry run alembic upgrade head && cd ../..

# Download Go dependencies
echo "Downloading Go dependencies..."
cd services/orchestrator && go mod download && cd ../..

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Start services:"
echo "  Frontend:     cd frontend && pnpm dev"
echo "  API Gateway:  cd services/api-gateway && poetry run uvicorn app.main:app --reload"
echo "  Orchestrator: cd services/orchestrator && go run ./cmd/orchestrator/"
echo ""
echo "Infrastructure: docker compose ps"
