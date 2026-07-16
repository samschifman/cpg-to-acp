# Contributing to CPG-to-ACP

Thank you for your interest in contributing to CPG-to-ACP.

## Code of Conduct

This project follows the [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

## Guidelines

- **License:** Apache-2.0. All contributions must be compatible with the Apache License 2.0.
- **Architecture:** Read [AGENTS.md](AGENTS.md) before making changes. It defines component ownership boundaries, standards-based contracts, and deployment rules. These are hard rules.
- **Component independence:** Do not add cross-component dependencies unless the contract goes through `shared/`. cpg-ingester must not import from acp-writer or vice versa.
- **Standards over proprietary:** Prefer standard interfaces (MCP, REST, FHIR, DMN, BPMN) over proprietary integrations.
- **Security:** This project handles clinical data. Do not introduce OWASP top 10 vulnerabilities. API keys and credentials go in `.env` files (gitignored), never in source code.
- **Container tooling:** Use Podman (preferred) or Docker. Compose files use the standard `compose.yml` format compatible with both.

## Development Setup

See the [Getting Started](README.md#getting-started) section in the README for setup instructions.

## Reporting Issues

Open a GitHub issue with a clear description of the problem, expected behavior, and steps to reproduce.
