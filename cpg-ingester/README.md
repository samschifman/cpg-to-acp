# Clinical Practice Guideline Ingester

Parses CPG documents and extracts both computable decision logic (DMN) and narrative recommendations for the acp-writer.

## Two Outputs

1. **DMN decision tables** — Computable logic extracted from clinical decision algorithms, delivered to acp-writer's Drools/Kogito decision service.
2. **Recommendations** — Non-computable narrative content for RAG retrieval. Contract defined in `shared/cpg_contracts/` (`Recommendation`, `RecommendationBundle`).

## Phase 1 Capabilities

- Parse CPG PDFs into structured Markdown using [Docling](https://github.com/docling-project/docling)
- Extract DMN decision tables from parsed content using an LLM (Opus 4.6 via LiteLLM)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

### Parse a CPG PDF

```bash
cpg-parse data/synthetic-hypertension-cpg.pdf -o output
```

Produces:
- `output/synthetic-hypertension-cpg.md` — Structured Markdown (primary, for LLM consumption)
- `output/synthetic-hypertension-cpg.json` — Docling JSON (secondary, for debugging)

### Extract DMN (Step 5)

```bash
cpg-extract-dmn output/synthetic-hypertension-cpg.md -o output --litellm-url http://localhost:4000
```

## Container

```bash
podman build -t cpg-ingester .
podman run -v $(pwd)/output:/app/output cpg-ingester data/synthetic-hypertension-cpg.pdf -o /app/output
```

## Data

- `data/synthetic-hypertension-cpg.md` — Source Markdown for the synthetic CPG
- `data/synthetic-hypertension-cpg.pdf` — PDF version for Docling parsing
