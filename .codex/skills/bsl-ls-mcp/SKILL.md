---
name: bsl-ls-mcp
description: Run focused BSL Language Server MCP diagnostics or semantic navigation in a repository where BSL LS is configured. Use for changed BSL files when local repository policy requires it, for focused BSL review, or for a specific symbol/reference/type question. Do not activate for every 1C task, metadata-only work, or repositories without this configured capability.
---

# BSL Language Server MCP

Use BSL LS as a fast, focused analyzer for BSL files. It complements but does not replace the assigned EDT project model, metadata/query/platform validation, or tests.

## Bind the target

- Use the exact target repository as the MCP root; never substitute another checkout, `configurationRoot`, or a broad parent workspace.
- Read only configuration values that can affect the current question, such as diagnostics mode, severity, exclusions, subsystem or author filters, suppressions, language, and target platform. Do not load or restate the entire `.bsl-language-server.json`.
- Do not edit, bypass, or replace analyzer configuration to expose or silence findings.
- If active roots can make a symbol result ambiguous, constrain or cross-check that result; do not perform a broad scan.

## Focused diagnostics

1. When useful, capture a pre-change baseline for each target file.
2. After the repository-authorized change is persisted, analyze only changed BSL files.
3. Compare diagnostic ID, type, severity, and location; classify findings as new, pre-existing, resolved, not applicable, policy-suppressed, or coverage-limited.
4. Resolve through v8std only a diagnostic whose rule or applicability is not already established and can affect the task.
5. Correct confirmed new findings without changing required behavior or weakening safeguards.
6. Re-analyze once after a correction. Report an ambiguous or likely false-positive remainder instead of adding suppressions or entering another correction loop.

Absence of findings is not proof of coverage. If relevant filters or suppressions cannot be established with a bounded check, classify coverage as limited rather than guessing. Do not analyze the whole configuration for a focused task.

## Semantic navigation and failures

Use document symbols, references, definitions, call hierarchy, hover, or type information only for a specific file, symbol, and question. Treat inferred types and cross-root results as analyzer evidence, not runtime or EDT metadata truth.

If the target root or BSL LS MCP is unavailable, report the focused-analysis gap. Do not use an unrelated root, start SonarQube, or launch another broad analyzer as a silent fallback.

Report analyzed files, material configuration effects, diagnostics with their classification, the single correction/re-analysis result, and remaining coverage limits. Never claim a project-wide clean state from changed-file checks.
