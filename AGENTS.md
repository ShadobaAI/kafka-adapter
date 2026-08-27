# Repository Agent Instructions

Apply the required [workspace instructions](../../AGENTS.md). The rules below are this repository's delta and override shared rules on conflict.

## Repository Scope

This repository contains the Kafka Adapter product extension/library and its maintained documentation. Use current 1C sources and tests as primary evidence of behavior; use the relevant document under `docs/` as the maintained contract unless it conflicts with them. Preserve Russian 1C identifiers.

## Repository-Specific Rules

- `.codex/config.toml` owns `kfk-edt`, repository-local `bsl-ls`, and the adapter-only `sonarqube`; shared code-index/v8std policy and 1C skills come from `tools/ai`.
- Use `kfk-edt` for current source, semantic navigation, every persistent 1C mutation, and focused validation. Use the shared `code-index` only for supplementary indexed discovery/graphs and local `bsl-ls` only for focused BSL evidence according to workspace policy.
- Use SonarQube as supplementary analysis only for this repository. Its bearer token comes exclusively from `SONARQUBE_TOKEN`; never store the token in repository files.
- Prefix new repository-owned 1C metadata objects with `кфк`.
- Update the relevant local document under `docs/` when a documented product contract changes.
