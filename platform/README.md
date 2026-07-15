# Platform Services

Shared infrastructure services that multiple application components consume. These are platform-level dependencies, not application logic.

On OpenShift AI, these are typically platform capabilities that are configured rather than deployed by this project. For local development (podman/kind), this directory contains the deployment artifacts needed to stand up equivalent services locally.

## Services

| Service | Purpose |
|---|---|
| `maas/` | MaaS inference gateway — unified endpoint routing to frontier and self-hosted models |
| `mlflow/` | MLflow tracing and experiment tracking |
