# Скачать новые обращения «Обратная связь» с сервера по SSH в QA\<server>\ (см. tools/feedback_export.py).
# Только чтение: на сервере ничего не меняется и не удаляется.
# Пример: .\tools\feedback_export.ps1 -Server test -Key $HOME\.ssh\id_ed25519
param(
    [ValidateSet('test', 'prod')][string]$Server = 'test',
    [string]$Key,
    [string]$SshHost,
    [string]$User,
    [int]$Port = 0,
    [string]$RemoteDir,
    [switch]$DryRun
)
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $py = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }
    $argsList = @('tools/feedback_export.py', '--server', $Server)
    if ($Key) { $argsList += @('--key', $Key) }
    if ($SshHost) { $argsList += @('--host', $SshHost) }
    if ($User) { $argsList += @('--user', $User) }
    if ($Port -gt 0) { $argsList += @('--port', "$Port") }
    if ($RemoteDir) { $argsList += @('--remote-dir', $RemoteDir) }
    if ($DryRun) { $argsList += '--dry-run' }
    & $py @argsList
    exit $LASTEXITCODE
} finally { Pop-Location }
