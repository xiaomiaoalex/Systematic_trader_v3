# 1. 环境自检：确保在正确的目录下
$projectRoot = "$PSScriptRoot\.."
Set-Location $projectRoot

Write-Host "--- Trading System Startup (PowerShell 7) ---" -ForegroundColor Cyan

# 2. 检查 .env 是否存在
if (-not (Test-Path "backend\.env")) {
    Write-Host "[Error] .env not found in backend folder!" -ForegroundColor Red
    exit
}

# 3. 启动进程并提升优先级
# 使用绝对路径定位 python 和 main.py 以防万一
$backendPath = Join-Path $projectRoot "backend"
$mainScript = Join-Path $backendPath "main.py"

$process = Start-Process python -ArgumentList $mainScript -PassThru -WorkingDirectory $backendPath

# 设置 CPU 优先级为 AboveNormal
$process.PriorityClass = 'AboveNormal'

Write-Host "[Success] Systematic_trader_v3 is running." -ForegroundColor Green
Write-Host "Process PID: $($process.Id) | Priority: AboveNormal" -ForegroundColor Cyan