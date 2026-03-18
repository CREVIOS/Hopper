FROM python:3.12-slim AS builder

RUN pip install poetry==1.8.4
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1

WORKDIR /app
COPY services/api-gateway/pyproject.toml services/api-gateway/poetry.lock* ./
RUN poetry install --no-root --only main

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY services/api-gateway/ .
COPY proto/ /proto

ENV PATH="/app/.venv/bin:$PATH"

# Generate gRPC Python stubs from proto definitions
RUN python -m grpc_tools.protoc \
    --proto_path=/proto \
    --python_out=app/proto \
    --grpc_python_out=app/proto \
    hopper/pod/v1/pod.proto \
    hopper/billing/v1/billing.proto && \
    find app/proto -name '*_pb2_grpc.py' -exec sed -i 's/^from hopper\./from app.proto.hopper./g' {} + && \
    find app/proto -name '*_pb2.py' -exec sed -i 's/^from hopper\./from app.proto.hopper./g' {} +

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
