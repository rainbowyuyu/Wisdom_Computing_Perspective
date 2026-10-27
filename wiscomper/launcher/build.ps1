# Only needed when changing the launcher itself, never for website updates.
#requires -Version 7.0
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw '.NET Framework C# compiler was not found.' }
$output = Join-Path $projectRoot '万象世界.exe'
& $compiler /nologo /target:winexe /platform:anycpu /optimize+ /utf8output `
    /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll `
    ('/win32manifest:' + (Join-Path $PSScriptRoot 'app.manifest')) `
    ('/win32icon:' + (Join-Path $PSScriptRoot 'wisdom-logo.ico')) `
    ('/resource:' + (Join-Path $PSScriptRoot 'wisdom-logo.png') + ',wisdom-logo.png') `
    ('/out:' + $output) (Join-Path $PSScriptRoot 'Launcher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
Get-Item -LiteralPath $output | Select-Object FullName, Length, LastWriteTime
