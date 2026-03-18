FROM golang:1.23-alpine AS builder

# Install protoc and proto generators
RUN apk add --no-cache protobuf-dev make
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.34.2 && \
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.4.0

WORKDIR /app
COPY services/orchestrator/go.mod services/orchestrator/go.sum ./
RUN go mod download

COPY services/orchestrator/ .

# Generate proto stubs from .proto files
RUN mkdir -p api/proto/hopper/pod/v1 api/proto/hopper/billing/v1 && \
    protoc --proto_path=proto \
      --go_out=api/proto --go_opt=paths=source_relative \
      --go-grpc_out=api/proto --go-grpc_opt=paths=source_relative \
      proto/hopper/pod/v1/pod.proto \
      proto/hopper/billing/v1/billing.proto

RUN CGO_ENABLED=0 go build -o orchestrator ./cmd/orchestrator/

FROM alpine:3.20

RUN apk --no-cache add ca-certificates
WORKDIR /app
COPY --from=builder /app/orchestrator .

EXPOSE 50051
CMD ["./orchestrator"]
