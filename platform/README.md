# Platform Services

Shared infrastructure services that multiple application components consume. These are platform-level dependencies, not application logic.

On OpenShift AI, these are typically platform capabilities that are configured rather than deployed by this project. For local development (podman/kind), this directory contains the deployment artifacts needed to stand up equivalent services locally.

## Services

| Service | Purpose | Phase |
|---|---|---|
| `litellm/` | LiteLLM inference gateway — local stand-in for MaaS, routing to configurable LLM providers | Phase 1 |
| `maas/` | MaaS inference gateway — replaces LiteLLM on OpenShift with enterprise governance | Phase 2 |
| `mlflow/` | MLflow tracing and experiment tracking | Phase 2 |

## LiteLLM (Phase 1)

LiteLLM provides a unified OpenAI-compatible endpoint that proxies requests to one or more LLM providers. Two models are pre-configured:

| Model name | Provider | Notes |
|---|---|---|
| `default` | OpenAI (GPT-5.6) | Requires `OPENAI_API_KEY` |
| `claude` | Claude Opus 4.6 via Vertex AI | Requires `VERTEX_PROJECT`, `VERTEX_LOCATION`, and GCP Application Default Credentials |

The `default` model is used by cpg-ingester unless overridden with `--model`. In Phase 2, MaaS replaces LiteLLM on OpenShift — application code should not need to change since both expose the same OpenAI-compatible API.

### Setup

1. Copy `.env.example` to `.env` and configure at least one provider:
   ```bash
   cp platform/litellm/deploy/.env.example platform/litellm/deploy/.env
   ```

2. Run via compose (see root `compose.yml`) or standalone:
   ```bash
   cd platform/litellm
   podman build -f deploy/Dockerfile -t cpg-litellm .
   podman run -p 4000:4000 --env-file deploy/.env cpg-litellm
   ```

### Test

```bash
# OpenAI (default)
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{"model": "default", "messages": [{"role": "user", "content": "Hello"}]}'

# Claude (requires Vertex AI credentials)
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{"model": "claude", "messages": [{"role": "user", "content": "Hello"}]}'
```
