#requires -Version 7.0
[CmdletBinding()]
param([ValidateRange(0,65535)][int]$Port = 0)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime/service-control.ps1')
$paths = Get-VisualizePaths
$lock = $null
try {
    $Port = Resolve-VisualizePort $Port $paths.Root
    if (-not [IO.Directory]::Exists($paths.State)) { Write-Output 'No launcher-managed server is recorded.'; exit 0 }
    $lock = Enter-VisualizeLock (Join-Path $paths.State "$Port.lock")
    $statePath = Join-Path $paths.State "$Port.json"
    $record = Read-VisualizeRecord $statePath
    if ($null -eq $record) { Write-Output "No launcher-managed server is recorded for port $Port. No process was changed."; exit 0 }
    Stop-VisualizeProcess $paths $record $Port
    Remove-Item -LiteralPath $statePath -Force
    Write-Output "Stopped the verified project process tree on port $Port."
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
} finally { if ($null -ne $lock) { $lock.Dispose() } }
