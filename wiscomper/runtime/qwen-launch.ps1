param(
    [Parameter(Mandatory = $true)][string]$LoaderPath,
    [Parameter(Mandatory = $true)][string]$NodePath,
    [Parameter(Mandatory = $true)][string]$BridgePath
)

# Run without a profile. Only this process decrypts the current-user DPAPI key;
# there is no credential protocol over stdout, argv or the Python parent.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
try {
    . $LoaderPath *> $null
    if ([string]::IsNullOrWhiteSpace($env:DASHSCOPE_API_KEY)) { throw 'Missing credential' }
    $env:DSH_VISUALIZATION_API_KEY = $env:DASHSCOPE_API_KEY
    if ($env:DSH_VISUALIZATION_QWEN_BASE_OVERRIDE -ne '1') {
        $env:DSH_VISUALIZATION_BASE_URL = $env:QWEN_BASE_URL
    }
    # Give Node only its explicitly named provider secret and validated endpoint.
    Remove-Item Env:DASHSCOPE_API_KEY, Env:QWEN_API_KEY, Env:DASHSCOPE_API_BASE, Env:QWEN_BASE_URL -ErrorAction SilentlyContinue
} catch {
    [Console]::WriteLine('{"type":"result","ok":false,"code":"QWEN_NOT_CONFIGURED"}')
    exit 1
}

try {
    & $NodePath $BridgePath
    $qwenExitCode = $LASTEXITCODE
} catch {
    [Console]::WriteLine('{"type":"result","ok":false,"code":"RUNTIME_UNAVAILABLE"}')
    $qwenExitCode = 1
} finally {
    Remove-Item Env:DSH_VISUALIZATION_API_KEY -ErrorAction SilentlyContinue
}
exit $qwenExitCode
