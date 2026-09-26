[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$proxy = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\mcp\bsl-ls-proxy.mjs'))
$node = (Get-Command 'node' -CommandType Application -ErrorAction Stop).Source
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("bsl-ls-proxy-lifecycle-" + [guid]::NewGuid().ToString('N'))
$process = $null

try {
    New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
    $configuration = Join-Path $temporaryRoot '.bsl-language-server.json'
    $fakeJar = Join-Path $temporaryRoot 'fake-bsl-language-server.jar'
    [System.IO.File]::WriteAllText($configuration, '{}', [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText($fakeJar, 'not a jar', [System.Text.UTF8Encoding]::new($false))

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $node
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $arguments = @(
        $proxy,
        '--root', $temporaryRoot,
        '--configuration', $configuration,
        '--jar', $fakeJar,
        '--java', $node
    )
    $startInfo.Arguments = ($arguments | ForEach-Object {
        '"' + ([string]$_).Replace('"', '\"') + '"'
    }) -join ' '

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw 'Could not start BSL LS proxy lifecycle test process.'
    }
    if (-not $process.WaitForExit(5000)) {
        throw 'BSL LS proxy stayed alive after its child exited while client stdin remained open.'
    }
    if ($process.ExitCode -eq 0) {
        throw 'BSL LS proxy hid an unexpected child startup failure.'
    }

    Write-Output 'bsl-ls-proxy-lifecycle: child exit terminates proxy with open client stdin'
}
finally {
    if ($null -ne $process -and -not $process.HasExited) {
        $process.Kill($true)
    }
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
