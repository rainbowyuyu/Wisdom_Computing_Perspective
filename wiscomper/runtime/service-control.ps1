# Shared launcher functions. State contains only process identity and local logs.
Set-StrictMode -Version Latest

function Get-VisualizePaths {
    $projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $stateRoot = Join-Path $projectRoot 'data/service'
    [pscustomobject]@{
        Root = $projectRoot
        Python = Join-Path $projectRoot '.venv/Scripts/python.exe'
        Entry = Join-Path $projectRoot 'main.py'
        State = $stateRoot
        Logs = Join-Path $stateRoot 'logs'
    }
}

function Resolve-VisualizePort([int]$RequestedPort, [string]$ProjectRoot) {
    if ($RequestedPort -gt 0) { return $RequestedPort }
    $value = [Environment]::GetEnvironmentVariable('VISUALIZE_PORT', 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) {
        $envPath = Join-Path $ProjectRoot '.env'
        if ([IO.File]::Exists($envPath)) {
            # Read just the non-secret integer setting; never print the file.
            foreach ($line in [IO.File]::ReadLines($envPath)) {
                if ($line -match '^\s*(?:export\s+)?VISUALIZE_PORT\s*=\s*["'']?(\d+)["'']?\s*(?:#.*)?$') { $value = $Matches[1] }
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($value)) { return 3088 }
    $portValue = 0
    if (-not [int]::TryParse($value, [ref]$portValue) -or $portValue -lt 1024 -or $portValue -gt 65535) {
        throw 'VISUALIZE_PORT must be an integer between 1024 and 65535.'
    }
    return $portValue
}

function Enter-VisualizeLock([string]$Path) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        try { return [IO.File]::Open($Path, 'OpenOrCreate', 'ReadWrite', 'None') }
        catch [IO.IOException] {
            if ($timer.Elapsed.TotalSeconds -gt 35) { throw 'Another launcher operation is in progress. Try again after it finishes.' }
            Start-Sleep -Milliseconds 100
        }
    } while ($true)
}

function Read-VisualizeRecord([string]$Path) {
    if (-not [IO.File]::Exists($Path)) { return $null }
    try { return [IO.File]::ReadAllText($Path) | ConvertFrom-Json -ErrorAction Stop }
    catch { throw 'The local service record is invalid. No process was changed.' }
}

function Write-VisualizeRecord([string]$Path, $Value) {
    $temporary = $Path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    } finally {
        if ([IO.File]::Exists($temporary)) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Get-VisualizeProcess($Paths, $Record, [int]$Port) {
    if ($null -eq $Record) { return $null }
    try {
        $processIdValue = 0
        $valid = $Record.schemaVersion -eq 1 -and $Record.root -eq $Paths.Root -and
            $Record.executable -eq $Paths.Python -and $Record.entrypoint -eq $Paths.Entry -and
            [int]$Record.port -eq $Port -and [int]::TryParse([string]$Record.pid, [ref]$processIdValue) -and $processIdValue -gt 0
        $started = if ($Record.startedAtUtc -is [datetime]) { $Record.startedAtUtc.ToUniversalTime() }
            else { [datetime]::Parse([string]$Record.startedAtUtc, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime() }
    } catch { throw 'The local service record is invalid. No process was changed.' }
    if (-not $valid) { throw 'The service record does not belong to this installation. No process was changed.' }
    $running = Get-CimInstance Win32_Process -Filter "ProcessId = $processIdValue"
    if ($null -eq $running) { return $null }
    $pattern = '^\s*"?' + [regex]::Escape($Paths.Python) + '"?\s+"?' + [regex]::Escape($Paths.Entry) + '"?\s*$'
    if ($running.ExecutablePath -ne $Paths.Python -or $running.CommandLine -notmatch $pattern -or
        $null -eq $running.CreationDate -or $running.CreationDate.ToUniversalTime().Ticks -ne $started.Ticks) {
        throw 'The recorded PID no longer matches this project, command and creation time. No process was changed.'
    }
    return $running
}

function Stop-VisualizeProcess($Paths, $Record, [int]$Port) {
    $running = Get-VisualizeProcess $Paths $Record $Port
    if ($null -eq $running) { return }
    # An opened Process object keeps the identity across the final verification.
    $target = Get-Process -Id $running.ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $target) { return }
    try {
        if ($target.HasExited) { return }
        $started = ([datetime]$Record.startedAtUtc).ToUniversalTime()
        if ([Math]::Abs(($target.StartTime.ToUniversalTime() - $started).TotalMilliseconds) -gt 10) {
            throw 'The process changed during verification. No process was stopped.'
        }
        # .NET on PowerShell 7 terminates only this owned process and descendants.
        $target.Kill($true)
        if (-not $target.WaitForExit(10000)) { throw 'The owned process did not stop; its state record was preserved.' }
    } catch {
        if ($target.HasExited) { return }
        throw
    } finally { $target.Dispose() }
}

function Test-VisualizeHealth([int]$Port) {
    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $handler.AllowAutoRedirect = $false
    $client = [Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(2)
    $client.MaxResponseContentBufferSize = 4096
    try {
        $text = $client.GetStringAsync("http://127.0.0.1:$Port/healthz").GetAwaiter().GetResult()
        $health = $text | ConvertFrom-Json -ErrorAction Stop
        return $health.status -eq 'ok' -and $health.app -eq 'visualize-dsh'
    } catch { return $false }
    finally { $client.Dispose(); $handler.Dispose() }
}

function Open-VisualizeBrowser([string]$Url) {
    try { Start-Process -FilePath $Url | Out-Null }
    catch { Write-Warning "The server is ready. Open $Url in your browser." }
}

function Get-VisualizeListener([int]$Port) {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -ne 1) { return $null }
    return Get-CimInstance Win32_Process -Filter "ProcessId = $($owners[0])"
}

function Test-VisualizeListenerBelongs($Listener, $RootProcess) {
    if ($null -eq $Listener -or $null -eq $RootProcess) { return $false }
    $current = $Listener
    for ($depth = 0; $depth -lt 16; $depth++) {
        if ($current.ProcessId -eq $RootProcess.ProcessId) {
            return $current.CreationDate.ToUniversalTime().Ticks -eq $RootProcess.CreationDate.ToUniversalTime().Ticks
        }
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($current.ParentProcessId)"
        if ($null -eq $parent -or $current.CreationDate -lt $parent.CreationDate) { return $false }
        $current = $parent
    }
    return $false
}

function Test-VisualizeUnmanagedProcess($Paths, $Process) {
    if ($null -eq $Process) { return $false }
    # Windows venv Python can be a redirector: the actual listener is its child.
    # Reuse a manual launch from this venv without adopting it for later Stop.
    $entry = '(?:' + [regex]::Escape($Paths.Entry) + '|main\.py)'
    $pattern = '^\s*"?' + [regex]::Escape($Paths.Python) + '"?\s+"?' + $entry + '"?\s*$'
    $current = $Process
    for ($depth = 0; $depth -lt 16; $depth++) {
        if ($current.ExecutablePath -eq $Paths.Python -and $current.CommandLine -match $pattern) { return $true }
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($current.ParentProcessId)"
        if ($null -eq $parent -or $current.CreationDate -lt $parent.CreationDate) { return $false }
        $current = $parent
    }
    return $false
}
