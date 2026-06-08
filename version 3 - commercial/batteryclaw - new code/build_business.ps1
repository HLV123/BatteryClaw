<#
  BatteryClaw — build_business.ps1
  Đóng gói bản thương mại đầy đủ license gate.
  Entry point: app\buy_business.py

  Output: dist\BatteryClaw\
      BatteryClaw.exe              <- app GUI + license check (PyInstaller)
      engine\BatteryClawEngine.exe <- engine C# (self-contained, không cần .NET)
      models\*.onnx                <- AI model đã train

  Khách hàng chỉ cần:
    1. Giải nén thư mục nhận được
    2. Chạy BatteryClaw.exe → Windows hỏi Admin → bấm Yes
    3. Nhập Server URL + Email → Nhập API Key → Kích hoạt → Bắt đầu

  Yêu cầu MÁY BUILD (không phải máy khách):
    - .NET SDK 8+       : dotnet publish engine
    - Python 3.10+      : PyInstaller
    - PyInstaller       : pip install pyinstaller
    - requests          : pip install requests
#>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$dist = Join-Path $root "dist\BatteryClaw_business"

Write-Host ""
Write-Host "==== BatteryClaw Business Build ====" -ForegroundColor Cyan
Write-Host "Entry point : app\buy_business.py (co license gate)" -ForegroundColor Cyan
Write-Host "Output      : $dist" -ForegroundColor Cyan
Write-Host ""

# ── 0) Dọn dist cũ ────────────────────────────────────────────────────────────
Write-Host "[0] Don dist cu..." -ForegroundColor Yellow
if (Test-Path $dist) {
    # Dung cmd rmdir manh hon PowerShell Remove-Item khi co file bi lock
    cmd /c "rmdir /s /q `"$dist`"" 2>$null
    Start-Sleep -Seconds 1
    if (Test-Path $dist) {
        Write-Host "    WARN: Khong xoa het duoc dist cu, tiep tuc..." -ForegroundColor DarkYellow
    }
}
New-Item -ItemType Directory -Force -Path $dist | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dist "engine") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dist "models") | Out-Null

# ── 1) Train model nếu chưa có ────────────────────────────────────────────────
Write-Host "[1] Kiem tra model..." -ForegroundColor Yellow
$model     = Join-Path $root "simulator\models\batteryclaw_policy.onnx"
$modelData = $model + ".data"

if (-not (Test-Path $model)) {
    Write-Host "    Chua co model, dang train (300k steps)..." -ForegroundColor Yellow
    python simulator\train.py --steps 300000
} else {
    Write-Host "    Model co san: $model" -ForegroundColor Green
}

Copy-Item $model (Join-Path $dist "models\batteryclaw_policy.onnx") -Force
if (Test-Path $modelData) {
    Copy-Item $modelData (Join-Path $dist "models\batteryclaw_policy.onnx.data") -Force
}

# [1.1] Copy them model rieng cho profile battery_saver / performance (neu da train)
foreach ($p in @("battery_saver", "performance")) {
    $pm = Join-Path $root "simulator\models\batteryclaw_policy_$p.onnx"
    if (Test-Path $pm) {
        Copy-Item $pm (Join-Path $dist "models\batteryclaw_policy_$p.onnx") -Force
        if (Test-Path ($pm + ".data")) {
            Copy-Item ($pm + ".data") (Join-Path $dist "models\batteryclaw_policy_$p.onnx.data") -Force
        }
        Write-Host "    + model profile: $p" -ForegroundColor Green
    }
}

# ── 2) Build engine C# self-contained ────────────────────────────────────────
Write-Host "[2] Building engine C# (self-contained, khong can .NET tren may khach)..." -ForegroundColor Yellow
$engineProj = Join-Path $root "engine_dotnet"
if (Test-Path $engineProj) {
    Push-Location $engineProj
    dotnet publish -c Release -r win-x64 --self-contained true `
        /p:PublishSingleFile=true /p:IncludeNativeLibrariesForSelfExtract=true `
        -o (Join-Path $dist "engine")
    Pop-Location
    Write-Host "    Engine built." -ForegroundColor Green
} else {
    Write-Host "    WARN: Khong tim thay engine_dotnet\ - bo qua." -ForegroundColor DarkYellow
}

# ── 3) Build app GUI + license + brain → 1 exe (PyInstaller) ─────────────────
Write-Host "[3] Building BatteryClaw.exe (buy_business.py + license gate)..." -ForegroundColor Yellow

$addData = @(
    "brain;brain",
    "online;online",
    "datacollector;datacollector",
    "commons;commons",
    "dashboard;dashboard",
    "commercial;commercial",
    "worldmodel;worldmodel"
)
$addArgs  = $addData | ForEach-Object { "--add-data `"$root\$_`"" }

# [FIX online learning chet trong exe] online/ import submodule qua sys.path.insert
#  dong (online/buffer/replay_buffer.py ...). PyInstaller khong tu thay -> phai
#  them --paths cho TUNG thu muc con + --collect-submodules online.
$pathDirs = @(
    "brain","online","datacollector","commons","dashboard","commercial","app","worldmodel",
    "online\buffer","online\safety","online\finetune","online\personalize","online\feedback"
)
$pathArgs = $pathDirs | ForEach-Object { "--paths `"$root\$_`"" }

# hidden-import cho cac module nap dong (PyInstaller khong do duoc qua sys.path.insert)
$hidden = @(
    "replay_buffer","constraints","ewc","checkpoint","finetuner",
    "pattern_tracker","feedback_store","modes","online_loop","brain_online_adapter"
)
$hiddenArgs = $hidden | ForEach-Object { "--hidden-import $_" }

$pyiCmd = "pyinstaller" +
    " --noconfirm" +
    " --onefile" +
    " --windowed" +
    " --uac-admin" +
    " --name BatteryClaw" +
    " --distpath `"$dist`"" +
    " --workpath `"$root\build`"" +
    " --specpath `"$root\build`"" +
    " --collect-submodules online" +
    " " + ($addArgs    -join " ") +
    " " + ($pathArgs   -join " ") +
    " " + ($hiddenArgs -join " ") +
    " `"$root\app\buy_business.py`""

Write-Host $pyiCmd -ForegroundColor DarkGray
Invoke-Expression $pyiCmd

# [4.4] Copy installer cho khach (tao shortcut + tuy chon autostart)
$installer = Join-Path $root "install.ps1"
if (Test-Path $installer) {
    Copy-Item $installer (Join-Path $dist "install.ps1") -Force
    Write-Host "  + install.ps1 (installer cho khach)" -ForegroundColor Green
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==== BUILD HOAN THANH ====" -ForegroundColor Green
Write-Host ""
Write-Host "Goi khach hang: $dist" -ForegroundColor Green
Write-Host ""
Write-Host "Cach gui khach:" -ForegroundColor Cyan
Write-Host "  1. Nen thu muc '$dist' thanh BatteryClaw.zip"
Write-Host "  2. Gui file zip cho khach"
Write-Host "  3. Khach giai nen -> (tuy chon) chay install.ps1 de tao shortcut"
Write-Host "  4. Chay BatteryClaw.exe (Run as admin) -> nhap Server URL + Email + Key"
Write-Host ""
Write-Host "Luu y: key khach nhap se duoc lock vao may do, khong dung tren may khac." -ForegroundColor Yellow
