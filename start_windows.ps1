# ClassPulse — Windows PowerShell launcher (latest merged main only).
# Use: powershell -NoProfile -ExecutionPolicy Bypass -File .\start_windows.ps1
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8502
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $project

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step 失敗（結束代碼 $LASTEXITCODE）。不強制覆寫本機檔案，也不開啟舊版。"
    }
}

try {
    Write-Host ""
    Write-Host "=== ClassPulse｜最新已合併版本啟動器（Windows） ==="
    Write-Host "專案資料夾：$project"
    if (-not (Test-Path "app.py") -or -not (Test-Path "requirements.txt") -or
        -not (Test-Path ".git")) {
        throw "請確認 start_windows.ps1 位於 ClassPulse Git 專案根目錄。"
    }

    Write-Host "[1/4] 更新 GitHub main..."
    & git fetch origin main
    Assert-LastExitCode "git fetch"
    & git switch main
    Assert-LastExitCode "git switch main"
    & git pull --ff-only origin main
    Assert-LastExitCode "git pull --ff-only"

    $branch = (& git branch --show-current).Trim()
    Assert-LastExitCode "讀取分支"
    $sha = (& git rev-parse --short HEAD).Trim()
    Assert-LastExitCode "讀取版本"
    Write-Host "已選版本：$branch · $sha"

    Write-Host "[2/4] 檢查 Python..."
    & py -3 -c "import sys; sys.exit(sys.version_info < (3,11))"
    Assert-LastExitCode "Python 3.11 版本檢查"
    $python = Join-Path $project ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        & py -3 -m venv .venv
        Assert-LastExitCode "建立 .venv"
    }

    Write-Host "[3/4] 確保依賴符合目前版本..."
    & $python -m pip install -r requirements.txt
    Assert-LastExitCode "安裝 requirements.txt"

    Write-Host "[4/4] 檢查專用 Port $Port..."
    $socket = New-Object System.Net.Sockets.TcpClient
    try {
        try {
            $socket.Connect("127.0.0.1", $Port)
        }
        catch [System.Net.Sockets.SocketException] {
            # Connection refused: the port is available.
        }
        if ($socket.Connected) {
            throw "Port $Port 已有網站在運作。請先在先前啟動的 PowerShell 按 Ctrl+C。"
        }
    }
    finally {
        $socket.Dispose()
    }

    Write-Host ""
    Write-Host "======================================================"
    Write-Host "ClassPulse：main / $sha"
    Write-Host "網站網址：http://localhost:$Port"
    Write-Host "不要開先前的 http://localhost:8501。"
    Write-Host "停止：Ctrl+C"
    Write-Host "======================================================"
    Write-Host ""

    & $python -m streamlit run app.py --server.port $Port --server.address 127.0.0.1
    Assert-LastExitCode "Streamlit"
}
finally {
    Pop-Location
}
