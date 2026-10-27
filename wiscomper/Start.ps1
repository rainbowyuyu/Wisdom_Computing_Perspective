#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateRange(0,65535)][int]$Port = 0,
    [switch]$NoBrowser,
    [ValidateRange(5,120)][int]$StartupTimeoutSeconds = 30
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime/service-control.ps1')
$paths = Get-VisualizePaths
$lock = $null
$launchedRecord = $null
$child = $null
$statePath = $null
try {
    $Port = Resolve-VisualizePort $Port $paths.Root
    if ($Port -lt 1024) { throw 'Use a local port between 1024 and 65535.' }
    if (-not [IO.File]::Exists($paths.Python)) { throw 'Project Python is missing. Create .venv and install requirements.txt first.' }
    if (-not [IO.File]::Exists($paths.Entry)) { throw 'This installation has no main.py.' }
    [IO.Directory]::CreateDirectory($paths.Logs) | Out-Null
    $statePath = Join-Path $paths.State "$Port.json"
    $lock = Enter-VisualizeLock (Join-Path $paths.State "$Port.lock")
    $record = Read-VisualizeRecord $statePath
    $running = Get-VisualizeProcess $paths $record $Port
    $url = "http://127.0.0.1:$Port/"
    if ($null -ne $running) {
        if (-not (Test-VisualizeHealth $Port)) { throw 'This project is still running but is not healthy. Inspect data/service/logs or use Stop.ps1 before restarting.' }
        $listener = Get-VisualizeListener $Port
        if (-not (Test-VisualizeListenerBelongs $listener $running)) { throw 'The port listener does not match the recorded process tree. No process was changed.' }
        Write-Output "Already running: $url"
        if (-not $NoBrowser) { Open-VisualizeBrowser $url }
        exit 0
    }
    if (Test-VisualizeHealth $Port) {
        $listener = Get-VisualizeListener $Port
        if (-not (Test-VisualizeUnmanagedProcess $paths $listener)) { throw 'A healthy service from another installation owns this port. Choose another -Port.' }
        Write-Output "Reusing existing manual launch: $url (not adopted by Stop.ps1)"
        if (-not $NoBrowser) { Open-VisualizeBrowser $url }
        exit 0
    }
    $probe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    try { $probe.Start() }
    catch { throw "Port $Port is already in use. Its owner was not changed. Choose another -Port." }
    finally { $probe.Stop() }
    if ([IO.File]::Exists($statePath)) { Remove-Item -LiteralPath $statePath -Force }
    $logName = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + "-$Port-" + [guid]::NewGuid().ToString('N').Substring(0,8)
    $stdoutPath = Join-Path $paths.Logs "$logName.stdout.log"
    $stderrPath = Join-Path $paths.Logs "$logName.stderr.log"
    $savedEnvironment = @{}
    foreach ($name in @('VISUALIZE_PORT','PYTHONUTF8','PYTHONIOENCODING')) {
        $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    try {
        $env:VISUALIZE_PORT = [string]$Port
        $env:PYTHONUTF8 = '1'
        $env:PYTHONIOENCODING = 'utf-8'
        $child = Start-Process -FilePath $paths.Python -ArgumentList ('"' + $paths.Entry + '"') -WorkingDirectory $paths.Root `
            -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    } finally {
        foreach ($name in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
    }
    $running = Get-CimInstance Win32_Process -Filter "ProcessId = $($child.Id)"
    if ($null -eq $running) { throw 'The server exited during startup. Check data/service/logs.' }
    $launchedRecord = [pscustomobject]@{
        schemaVersion = 1; root = $paths.Root; pid = $child.Id; port = $Port
        executable = $paths.Python; entrypoint = $paths.Entry
        startedAtUtc = $running.CreationDate.ToUniversalTime().ToString('o')
        stdout = $stdoutPath; stderr = $stderrPath
    }
    Write-VisualizeRecord $statePath $launchedRecord
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $StartupTimeoutSeconds) {
        if ($child.HasExited) { throw 'The server exited during startup. Check data/service/logs.' }
        if (Test-VisualizeHealth $Port) {
            $listener = Get-VisualizeListener $Port
            if (-not (Test-VisualizeListenerBelongs $listener $running)) { throw 'Another listener appeared on this port during startup.' }
            Write-Output "Started: $url"
            if (-not $NoBrowser) { Open-VisualizeBrowser $url }
            exit 0
        }
        Start-Sleep -Milliseconds 300
    }
    throw "Startup did not complete in $StartupTimeoutSeconds seconds. Check data/service/logs."
} catch {
    if ($null -ne $launchedRecord) {
        try {
            Stop-VisualizeProcess $paths $launchedRecord $Port
            if ([IO.File]::Exists($statePath)) { Remove-Item -LiteralPath $statePath -Force }
        } catch { Write-Warning 'Startup cleanup could not verify the process. Its state record was preserved.' }
    } elseif ($null -ne $child) {
        # Start-Process returned this handle before a record could be written.
        # It cannot refer to a later process that reused the numeric PID.
        try { if (-not $child.HasExited) { $child.Kill($true); $child.WaitForExit(10000) | Out-Null } }
        catch { Write-Warning 'The owned startup process could not be stopped.' }
    }
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
} finally {
    if ($null -ne $lock) { $lock.Dispose() }
    if ($null -ne $child) { $child.Dispose() }
}
