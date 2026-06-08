# BatteryClaw — Installer (chay tren may KHACH HANG)
# Tao shortcut Desktop + Start Menu, tuy chon khoi dong cung Windows.
# Khong can cai gi them — chi sap xep shortcut cho goi da giai nen.
#
# Dung:
#   Chuot phai -> Run with PowerShell  (hoac):
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Go cai:
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall

param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$AppName = "BatteryClaw"
$here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe     = Join-Path $here "BatteryClaw.exe"

$desktop   = [Environment]::GetFolderPath("Desktop")
$startmenu = [Environment]::GetFolderPath("Programs")
$lnkDesktop = Join-Path $desktop   "$AppName.lnk"
$lnkStart   = Join-Path $startmenu "$AppName.lnk"
$runKey     = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

function New-Shortcut($path, $target) {
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($path)
    $sc.TargetPath       = $target
    $sc.WorkingDirectory = Split-Path -Parent $target
    $sc.Description       = "BatteryClaw - Toi uu pin AI"
    $sc.Save()
}

if ($Uninstall) {
    Write-Host "Go cai BatteryClaw..." -ForegroundColor Yellow
    Remove-Item $lnkDesktop -ErrorAction SilentlyContinue
    Remove-Item $lnkStart   -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path $runKey -Name $AppName -ErrorAction SilentlyContinue
    Write-Host "Da go shortcut + autostart. (Thu muc app van con, xoa tay neu muon.)" -ForegroundColor Green
    Write-Host "Luu y: cau hinh/license o %APPDATA%\BatteryClaw — xoa tay neu muon sach hoan toan."
    return
}

if (-not (Test-Path $exe)) {
    Write-Host "Khong thay BatteryClaw.exe canh installer. Dat install.ps1 cung thu muc voi exe." -ForegroundColor Red
    return
}

Write-Host "Cai dat BatteryClaw..." -ForegroundColor Cyan
New-Shortcut $lnkDesktop $exe
New-Shortcut $lnkStart   $exe
Write-Host "  + Shortcut Desktop + Start Menu" -ForegroundColor Green

$ans = Read-Host "Khoi dong BatteryClaw cung Windows? (y/N)"
if ($ans -eq "y" -or $ans -eq "Y") {
    Set-ItemProperty -Path $runKey -Name $AppName -Value "`"$exe`""
    Write-Host "  + Da bat khoi dong cung Windows" -ForegroundColor Green
} else {
    Write-Host "  - Bo qua autostart" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "XONG! Mo BatteryClaw tu Desktop (nho chay Run as administrator)." -ForegroundColor Cyan
Write-Host "Lan dau can nhap Server URL + Email + API Key de kich hoat." -ForegroundColor Cyan
