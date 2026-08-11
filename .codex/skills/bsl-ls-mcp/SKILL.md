---
name: bsl-ls-mcp
description: Run fast, focused static analysis and semantic navigation for 1C:Enterprise BSL or OneScript through BSL Language Server MCP. Use after BSL changes, during code review, or when Codex needs file diagnostics, document symbols, references, call hierarchy, definitions, hover/type information, or platform-member lookup while respecting each workspace .bsl-language-server.json configuration.
---

# BSL Language Server MCP

Use BSL LS MCP as the immediate static-analysis layer for changed BSL files. It complements EDT diagnostics, platform documentation, v8std, and tests; it does not replace them.

## Bind the correct workspace

1. Identify the target repository root and exact changed BSL files from repository instructions and the task. Never analyze another checkout merely because it is already indexed.
2. Ensure that exact repository root is an MCP root. Never replace it with `configurationRoot` or add the workspace collection root or another broad parent as a shortcut. BSL LS indexes MCP roots and any LSP workspace folders into one shared context and resynchronizes after `roots/list_changed`; record other active roots when they could affect cross-module results.
3. Read `<workspace>/.bsl-language-server.json` when present before interpreting results. BSL LS has distinct global and per-workspace scopes: global configuration covers language, telemetry/logging, and selected capabilities; the workspace file controls diagnostics and other workspace behavior. If the workspace file is absent, workspace defaults are supplemented by global configuration.
4. Establish effective startup/global settings from an explicit `-c` argument, server CWD, or exposed server configuration when available. Do not inspect unrelated user files for a routine check. If the effective global configuration remains unknown and can affect the conclusion, classify that part of coverage as unverified.
5. Resolve `configurationRoot` relative to the repository workspace root; for `configurationRoot: "src"`, the MCP root remains `<repo>` while the configuration source root is `<repo>/src`. Respect language, diagnostic mode and trigger, disabled diagnostics, minimum and overridden severity, diagnostic parameters, exclusions, support handling, subsystem filters, ignored authors, and target-platform settings.
6. Never edit, bypass, or replace project configuration merely to expose or silence a finding. If the requested task changes analyzer policy, treat the config edit as a separate explicit change.
7. Use current MCP tool schemas as authoritative; MCP mode uses an experimental API and may evolve.

## Choose the narrowest tool

| Need | Tool |
| --- | --- |
| Diagnostics for one changed file | `analyze_file` |
| Methods, regions, and variables | `document_symbols` |
| Symbol usages | `find_references` |
| Incoming or outgoing calls | `call_hierarchy` |
| Signature, inferred type, or docs at a position | `hover` or `type_at_position` |
| Symbol declaration | `definition` |
| Platform type members and version metadata | `type_info` |
| Global function/property/enum details | `global_member_info` |
| Discover a global member by fuzzy name | `global_member_search` |

MCP positions use zero-based `line` and `character`, unlike many EDT tools. Convert coordinates deliberately and report user-facing source locations as one-based unless the tool contract says otherwise.

## Run focused diagnostics

1. Before editing, run `analyze_file` on each target BSL file when practical and save a baseline of diagnostic ID, severity, message, and position.
2. After the change is persisted by the repository-authorized mechanism, analyze only changed BSL files. Use EDT-MCP where repository rules require it. Do not trigger a broad project scan for a focused change.
3. Compare with the baseline. Classify findings as `new`, `pre-existing`, `resolved`, `not applicable`, `suppressed by policy`, or `coverage-limited`.
4. Preserve every diagnostic ID, type, and severity exactly. Do not interpret `CODE_SMELL`, `ERROR`, `VULNERABILITY`, and `SECURITY_HOTSPOT` as equivalent; security hotspots require manual contextual review.
5. Resolve relevant BSLLS IDs through `$v8std-mcp`, open the full diagnostic and linked standard pages, then check applicability against actual code and project configuration.
6. Correct confirmed new findings only when the fix preserves required behavior, compatibility, security, permissions, transactions, and project style.
7. Run one focused correction iteration. If a finding persists and may be a false positive, report evidence instead of weakening configuration or adding suppression.
8. Re-run `analyze_file` after the correction and record the final result.

Do not treat an absent diagnostic as proof of correct behavior. A rule may not run because of `diagnostics.mode`, `minimumLSPDiagnosticLevel`, support or subsystem filtering, excluded paths, `ignoredAuthors`, or `// BSLLS...` suppression comments. For zero output, inspect the target module header and relevant ranges for active suppression comments through the repository-authorized source tool. If `ignoredAuthors` is non-empty, verify the candidate committed lines with bounded `git blame`; author filtering does not suppress uncommitted changed lines. Until the applicable filter or suppression is proven, classify zero output as `coverage-limited`, not `suppressed by policy`. `overrideMinimumLSPDiagnosticLevel` changes reported severity; it does not prove greater coverage. Also run assigned EDT syntax/semantic/project checks, platform API verification, query validation, and relevant tests.

## Use semantic tools carefully

- Prefer symbols, references, definitions, and call hierarchy over textual assumptions.
- Keep queries bound to the exact file and symbol position. Verify that the position still matches the current file revision.
- Use `document_symbols` to locate methods and regions before issuing position-based requests. Use `find_references` for actual project usages and `call_hierarchy` when incoming versus outgoing calls matter.
- Classify every returned definition, reference, or call-hierarchy URI as inside or outside the target root. If duplicate symbols or FQNs across roots make resolution ambiguous, repeat in an isolated target-root context when available; otherwise cross-check with the assigned EDT-MCP and report the ambiguity.
- Use BSL LS platform type/member information for navigation and compatibility cross-checks. Use EDT `get_platform_documentation` in the target project as the authoritative platform API source when available.
- Distinguish parser/type inference output from runtime behavior and project metadata semantics.

## Handle failures

- If the target root is missing, request or restore the correct MCP root rather than analyzing a parent workspace or unrelated repository.
- If diagnostics appear inconsistent, re-check all active roots, `configurationRoot`, config layering, filters, suppressions, config reload, and file revision before retrying.
- If BSL LS MCP is unavailable, report the focused static-analysis gap. Do not fall back to SonarQube or start a separate broad analysis unless explicitly requested.
- Do not enable trace/debug logging or error reporting for routine checks. Such telemetry can include protocol messages, source fragments, or full files; require an explicit troubleshooting need and user approval.

## Report evidence

Report analyzed workspace, active-root effects, and files; relevant project-config effects and suppressions; tool calls used; diagnostics by ID, type, severity, classification, and source location; v8std pages used for interpretation; corrections made; final re-analysis; and anything unverified. Never claim a project-wide clean state from changed-file checks.

## Authoritative references

- [MCP mode](https://1c-syntax.github.io/bsl-language-server/features/McpMode/)
- [Configuration file](https://1c-syntax.github.io/bsl-language-server/features/ConfigurationFile/)
- [Diagnostic suppression](https://1c-syntax.github.io/bsl-language-server/features/DiagnosticIgnorance/)
- [Core documentation tree](https://github.com/1c-syntax/bsl-language-server/tree/develop/docs)
