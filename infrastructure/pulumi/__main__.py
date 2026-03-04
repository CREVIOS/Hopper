"""Hopper Infrastructure - Pulumi Program."""

import pulumi

config = pulumi.Config()
environment = config.require("environment")

# TODO: Define infrastructure resources
# - Kubernetes cluster (kubeadm / RKE2)
# - PostgreSQL (managed or self-hosted)
# - NATS JetStream deployment
# - Keycloak deployment
# - GPU Operator Helm release
# - KAI Scheduler Helm release
# - Kueue installation
# - Monitoring stack (Prometheus, Grafana, Loki)

pulumi.export("environment", environment)
