param()
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Port = 8765
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment not found. Create it and install requirements.txt first."
}

# Replace a stale copy of this project's web server so changed routes/assets load.
$Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($Listener in $Listeners) {
    $Process = Get-CimInstance Win32_Process -Filter "ProcessId = $($Listener.OwningProcess)" -ErrorAction SilentlyContinue
    if ($Process -and $Process.CommandLine -like "*$RepoRoot*visualizer.py*") {
        Write-Host "Restarting the existing Frontier Command server on port $Port..."
        Stop-Process -Id $Listener.OwningProcess -Force
        Start-Sleep -Milliseconds 500
    }
}

$env:PYTHONIOENCODING = "utf-8"
$env:FRONTIER_PORT = [string]$Port
Write-Host "Frontier Command Web is starting at http://127.0.0.1:8765"
Write-Host "Keep this window open while you play. Press Ctrl+C to stop."
& $Python (Join-Path $RepoRoot "visualizer.py")
