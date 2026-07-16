# Platform Services

Shared infrastructure services that multiple application components consume. These are platform-level dependencies, not application logic.

On OpenShift AI, these are typically platform capabilities that are configured rather than deployed by this project. For local development (podman/kind), this directory contains the deployment artifacts needed to stand up equivalent services locally.

## Services

| Service | Purpose | Phase |
|---|---|---|
| `litellm/` | LiteLLM inference gateway — local stand-in for MaaS, routing to frontier models via Vertex AI | Phase 1 |
| `maas/` | MaaS inference gateway — replaces LiteLLM on OpenShift with enterprise governance | Phase 2 |
| `mlflow/` | MLflow tracing and experiment tracking | Phase 2 |

## LiteLLM (Phase 1)

LiteLLM provides a unified OpenAI-compatible endpoint that proxies requests to Claude Opus 4.6 on Google Vertex AI. In Phase 2, MaaS replaces LiteLLM — application code should not need to change since both expose the same OpenAI-compatible API.

### Setup

1. Copy `.env.example` to `.env` and fill in your GCP project details:
   ```bash
   cp platform/litellm/deploy/.env.example platform/litellm/deploy/.env
   ```

2. Place your GCP service account credentials JSON file where the container can mount it (path configured via `GOOGLE_APPLICATION_CREDENTIALS`).

3. Run via compose (see root `compose.yml`) or standalone:
   ```bash
   cd platform/litellm
   podman build -f deploy/Dockerfile -t cpg-litellm .
   podman run -p 4000:4000 \
     --env-file deploy/.env \
     -v /path/to/credentials.json:/app/credentials.json \
     cpg-litellm
   ```

### Test

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{"model": "opus", "messages": [{"role": "user", "content": "Hello"}]}'
```
