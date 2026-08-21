# Repository Agent Instructions

Apply the required [workspace instructions](../../AGENTS.md). The rules below are this repository's delta and override shared rules on conflict.

## Repository Scope

This repository contains the Kafka Adapter product extension/library and its maintained documentation. Use current 1C sources and tests as primary evidence of behavior; use the relevant document under `docs/` as the maintained contract unless it conflicts with them. Preserve Russian 1C identifiers.

## Repository-Specific Rules

- `.codex/config.toml` owns `kfk-edt`, SonarQube, and `bsl-ls`. Keep the repository-specific `bsl-ls-mcp` skill under `.codex/skills/bsl-ls-mcp`; do not install it from `kafka-tools`.
- For each changed BSL file, run focused BSL LS analysis after focused EDT diagnostics. Do not analyze the whole configuration.
- SonarQube analysis and code export are user-operated; run them only when explicitly requested.
- Prefix new repository-owned 1C metadata objects with `кфк`.
- Update the relevant local document under `docs/` when a documented product contract changes.
