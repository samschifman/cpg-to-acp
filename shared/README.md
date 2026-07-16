# Shared Resources

Cross-component contracts and utilities. Used sparingly to prevent coupling between components.

## cpg-contracts

Python package defining the data types that form the API contract between components. Both cpg-ingester and acp-writer depend on this package; neither depends on the other.

### Contract Types

| Module | Types | Boundary |
|---|---|---|
| `cpg_contracts.decisions` | `DecisionModelSummary`, `DecisionVariable`, `DecisionEvaluationRequest`, `DecisionEvaluationResponse` | cpg-ingester → acp-writer (DMN deployment and evaluation) |

### Installation

```bash
pip install -e shared/
```

Or as a dependency in another component's `pyproject.toml`:
```toml
dependencies = [
    "cpg-contracts @ file:///${PROJECT_ROOT}/shared",
]
```
