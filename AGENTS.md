# Repository Agent Instructions

## Workspace Instructions

Read the required [workspace instructions](../../AGENTS.md) before working in this repository. The fixed `KAFKA_PROJECTS_ROOT` layout is required. If the shared file is missing, report a workspace-layout error and stop. The repository-specific rules below supplement and override the shared rules when they conflict.

## Repository Scope

This repository contains the Kafka Adapter product extension/library and its maintained documentation. Start with [README.md](README.md). Use [docs/project/repositories.md](docs/project/repositories.md) for ecosystem boundaries and the relevant document under `docs/` for product behavior.

Current local 1C sources and tests are the primary evidence of actual behavior. Repository documentation is the canonical maintained description unless it conflicts with current sources or tests. Preserve original Russian 1C identifiers.

## Repository-Specific Rules

- Use `kfk_edt` as the authoritative current-state and editing interface for this 1C project.
- Use `code-metadata-mcp` and `graph-metadata-mcp` only for bounded navigation and impact analysis in this repository.
- Treat `kfk_edt` as current when it conflicts with navigation indexes.
- Prefix new repository-owned 1C metadata objects with `кфк`.
- Update the relevant local document under `docs/` when a documented product contract changes.

