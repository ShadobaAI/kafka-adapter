[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$configPath = Join-Path $repositoryRoot '.codex\config.toml'
$config = Get-Content -LiteralPath $configPath -Raw

$bslLsTable = [regex]::Match(
    $config,
    '(?ms)^\[mcp_servers\.bsl-ls\]\r?\n.*?(?=^\[|\z)'
)
if (-not $bslLsTable.Success) {
    throw 'Repository config does not contain the bsl-ls MCP table.'
}
if ($bslLsTable.Value -notmatch '(?m)^cwd\s*=\s*"\."\s*$') {
    throw 'BSL LS MCP cwd must be portable and relative to the repository root.'
}
if ($bslLsTable.Value -match '(?i)[A-Z]:\\') {
    throw 'BSL LS MCP config contains a machine-specific absolute Windows path.'
}
if ($bslLsTable.Value -notmatch [regex]::Escape('.codex\\mcp\\bsl-ls-proxy.mjs')) {
    throw 'BSL LS MCP config does not launch the repository-owned proxy.'
}

Write-Output 'portable-config: repository-relative BSL LS launcher passed'
