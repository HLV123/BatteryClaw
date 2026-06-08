<#
  BatteryClaw — check_env.ps1
  Kiem tra may Windows da du moi truong de chay project chua.
  Bao ro: cai gi DA CO, cai gi THIEU, va lenh cai tung thu.

  Cach chay (PowerShell, KHONG can quyen Admin de kiem tra):
      powershell -ExecutionPolicy Bypass -File check_env.ps1

  Neu bi chan ExecutionPolicy, mo PowerShell roi go:
      Set-ExecutionPolicy -Scope Process Bypass
      .\check_env.ps1
#>

$ErrorActionPreference = "SilentlyContinue"

$ok    = @()   # da co
$miss  = @()   # thieu
$warn  = @()   # canh bao / tuy chon

function Test-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  BatteryClaw - Kiem tra moi truong" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# 1) HE DIEU HANH
# ============================================================
Write-Host "[1] He dieu hanh" -ForegroundColor Yellow
$os = Get-CimInstance Win32_OperatingSystem
$build = [int]([System.Environment]::OSVersion.Version.Build)
Write-Host ("    {0} (build {1})" -f $os.Caption, $build)
if ($build -ge 22000) {
    $ok += "Windows 11 (build $build) - ho tro day du EcoQoS (Phase 5)"
} else {
    $warn += "Windows 10 (build $build) - EcoQoS per-process (Phase 5.3) KHONG chay; cac phan khac van OK"
}

# ============================================================
# 2) PYTHON  (bat buoc - chay rl_brain, simulator, server, app...)
# ============================================================
Write-Host "[2] Python" -ForegroundColor Yellow
if (Test-Cmd python) {
    $pyv = (python --version 2>&1).ToString().Trim()
    Write-Host "    $pyv"
    # kiem tra >= 3.10
    $m = [regex]::Match($pyv, "(\d+)\.(\d+)")
    if ($m.Success) {
        $maj = [int]$m.Groups[1].Value; $min = [int]$m.Groups[2].Value
        if ($maj -eq 3 -and $min -ge 10) {
            $ok += "$pyv"
        } else {
            $warn += "$pyv - nen dung Python 3.10+ (project test tren 3.12)"
        }
    }
    $pipOk = Test-Cmd pip
    if (-not $pipOk) { $miss += "pip (thuong di kem Python; cai lai Python co tick 'pip')" }
} else {
    $miss += "Python 3.10+ - TAI: https://www.python.org/downloads/  (nho tick 'Add Python to PATH')"
    Write-Host "    CHUA CO" -ForegroundColor Red
}

# ============================================================
# 3) THU VIEN PYTHON
# ============================================================
Write-Host "[3] Thu vien Python" -ForegroundColor Yellow
if (Test-Cmd python) {
    # ten import (python) -> ten pip de goi y cai
    $libs = [ordered]@{
        "numpy"                  = "numpy"
        "torch"                  = "torch"
        "gymnasium"              = "gymnasium"
        "stable_baselines3"      = "stable-baselines3"
        "onnx"                   = "onnx"
        "onnxruntime"            = "onnxruntime"
        "pandas"                 = "pandas"
        "pyarrow"                = "pyarrow"
        "fastapi"                = "fastapi"
        "uvicorn"                = "uvicorn"
        "jinja2"                 = "jinja2"
        "requests"               = "requests"
        "winotify"               = "winotify"     # toast (Phase 6)
        "wmi"                    = "wmi"          # doc trang thai may
        "win32api"               = "pywin32"      # WinAPI
    }
    $needPip = @()
    foreach ($imp in $libs.Keys) {
        python -c "import $imp" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host ("    [OK]   {0}" -f $imp) -ForegroundColor DarkGreen
        } else {
            $pipName = $libs[$imp]
            Write-Host ("    [MISS] {0}  -> pip install {1}" -f $imp, $pipName) -ForegroundColor Red
            $needPip += $pipName
        }
    }
    if ($needPip.Count -gt 0) {
        $miss += ("Thu vien Python: " + ($needPip -join ", "))
        $script:PipInstallCmd = "pip install " + ($needPip -join " ")
    } else {
        $ok += "Tat ca thu vien Python da day du"
    }
} else {
    Write-Host "    (bo qua - chua co Python)" -ForegroundColor DarkGray
}

# ============================================================
# 4) .NET 8 SDK  (Phase 5 - engine C#; tuy chon neu chi chay Python)
# ============================================================
Write-Host "[4] .NET 8 SDK (Phase 5 - tuy chon)" -ForegroundColor Yellow
if (Test-Cmd dotnet) {
    $sdks = (dotnet --list-sdks 2>&1)
    $has8 = $sdks | Select-String "^8\."
    if ($has8) {
        Write-Host ("    .NET SDK: " + ($has8 -join "; "))
        $ok += ".NET 8 SDK"
    } else {
        Write-Host ("    Co dotnet nhung khong phai 8.x:`n    $sdks")
        $warn += ".NET SDK khac 8.x - engine_dotnet can net8.0. TAI: https://dotnet.microsoft.com/download/dotnet/8.0"
    }
} else {
    Write-Host "    CHUA CO" -ForegroundColor Red
    $warn += ".NET 8 SDK - chi can neu build engine C# (Phase 5). TAI: https://dotnet.microsoft.com/download/dotnet/8.0"
}

# ============================================================
# 5) C++ BUILD (Phase 1 - engine batteryclaw.exe)
# ============================================================
Write-Host "[5] C++ build tools (Phase 1 - engine)" -ForegroundColor Yellow
$hasCmake = Test-Cmd cmake
if ($hasCmake) {
    $cmv = (cmake --version 2>&1 | Select-Object -First 1)
    Write-Host "    $cmv"
    $ok += "CMake"
} else {
    Write-Host "    CMake: CHUA CO" -ForegroundColor Red
    $warn += "CMake - can de build engine C++. TAI: https://cmake.org/download/ (hoac: winget install Kitware.CMake)"
}
# MSVC: kiem tra cl.exe hoac Visual Studio
$hasCl = Test-Cmd cl
$vsPath = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -latest -property installationPath 2>$null
if ($hasCl -or $vsPath) {
    if ($vsPath) { Write-Host "    Visual Studio: $vsPath" }
    else { Write-Host "    cl.exe (MSVC) co trong PATH" }
    $ok += "MSVC / Visual Studio C++"
} else {
    Write-Host "    MSVC (Visual Studio C++): CHUA CO" -ForegroundColor Red
    $warn += "MSVC C++ Build Tools - can de build engine C++ (Phase 1). TAI: 'Build Tools for Visual Studio' (chon 'Desktop development with C++'), hoac: winget install Microsoft.VisualStudio.2022.BuildTools"
}

# ============================================================
# 6) GPU / DirectML (Phase 5 WinML - tang toc, tuy chon)
# ============================================================
Write-Host "[6] GPU (Phase 5 WinML/DirectML - tuy chon)" -ForegroundColor Yellow
$gpus = Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name
if ($gpus) {
    foreach ($g in $gpus) { Write-Host "    $g" }
    $ok += "GPU phat hien duoc (DirectML se tang toc WinML neu dung Phase 5)"
} else {
    Write-Host "    Khong doc duoc GPU (khong sao - WinML se fallback CPU)" -ForegroundColor DarkGray
}

# ============================================================
# TONG KET
# ============================================================
Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  TONG KET" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "DA CO:" -ForegroundColor Green
if ($ok.Count -eq 0) { Write-Host "    (chua co gi)" } else { $ok | ForEach-Object { Write-Host "    [+] $_" -ForegroundColor Green } }

if ($miss.Count -gt 0) {
    Write-Host ""
    Write-Host "THIEU (BAT BUOC de chay phan loi Python):" -ForegroundColor Red
    $miss | ForEach-Object { Write-Host "    [-] $_" -ForegroundColor Red }
}

if ($warn.Count -gt 0) {
    Write-Host ""
    Write-Host "CANH BAO / TUY CHON (chi can cho mot so phase):" -ForegroundColor Yellow
    $warn | ForEach-Object { Write-Host "    [!] $_" -ForegroundColor Yellow }
}

# ============================================================
# LENH CAI NHANH
# ============================================================
Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  LENH CAI NHANH" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

if ($script:PipInstallCmd) {
    Write-Host "1) Cai thu vien Python con thieu:" -ForegroundColor White
    Write-Host "   $($script:PipInstallCmd)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "   (Hoac cai het tu requirements - khuyen nghi):" -ForegroundColor White
    Write-Host "   pip install -r datacollector/requirements.txt" -ForegroundColor Gray
    Write-Host "   pip install -r server/requirements.txt" -ForegroundColor Gray
    Write-Host "   pip install -r app/requirements.txt" -ForegroundColor Gray
} else {
    if (Test-Cmd python) {
        Write-Host "Thu vien Python da day du - khong can cai them." -ForegroundColor Green
    }
}

Write-Host ""
$ready = ($miss.Count -eq 0)
if ($ready) {
    Write-Host "=> Du moi truong cho phan Python (RL brain, simulator, server, dashboard, app)." -ForegroundColor Green
    Write-Host "   Engine C++ (Phase 1) va C# (Phase 5) can build tools rieng neu muon dung." -ForegroundColor Green
} else {
    Write-Host "=> CHUA du. Cai cac muc [THIEU] o tren roi chay lai script nay." -ForegroundColor Red
}
Write-Host ""
