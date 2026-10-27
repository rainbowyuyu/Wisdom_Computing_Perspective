param(
    [ValidateSet('Configure','Check','Guide')][string]$Action='Configure',
    [string]$EnvFile='',
    [ValidateRange(1,65535)][int]$Port=3088
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$githubProjectRoot=Split-Path $PSScriptRoot -Parent
$githubPython=Join-Path $githubProjectRoot '.venv/Scripts/python.exe'
$githubScript=Join-Path $PSScriptRoot 'configure_github.py'
if (-not (Test-Path -LiteralPath $githubPython -PathType Leaf)) {
    Write-Error '项目 Python 环境尚未安装，请先完成工作台依赖安装。'
    exit 1
}
$githubArgs=@($githubScript)
if ($EnvFile) { $githubArgs+=@('--env-file',$EnvFile) }
if ($Action -eq 'Check') { $githubArgs+='--check' }
if ($Action -eq 'Guide') { $githubArgs+='--guide' }
if ($PSBoundParameters.ContainsKey('Port') -and $Action -ne 'Configure') { $githubArgs+=@('--port',"$Port") }
# ID/Secret are requested by Python getpass. Never accept them as script params,
# environment overrides, transcript output, or command-line arguments.
& $githubPython @githubArgs
exit $LASTEXITCODE
