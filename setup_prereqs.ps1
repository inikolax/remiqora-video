#Requires -Version 5.1
param([switch]$SkipNode, [switch]$SkipFfmpeg)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

# Message language: REMIQORA_VIDEO_LANG if set (the desktop wizard does not run these scripts), else the Windows display language; Russian or English
$lang = if ($env:REMIQORA_VIDEO_LANG) { $env:REMIQORA_VIDEO_LANG } else { (Get-UICulture).TwoLetterISOLanguageName }
$script:ru = $lang.ToLowerInvariant().StartsWith('ru')
function T([string]$Ru, [string]$En) { if ($script:ru) { $Ru } else { $En } }

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host (T 'winget не найден. Установите App Installer из Microsoft Store и повторите запуск.' 'winget not found. Install App Installer from the Microsoft Store and run this again.') -ForegroundColor Red
    exit 1
}

function Install-Package([string]$Id) {
    Write-Host "`n== $Id ==" -ForegroundColor Cyan
    $found = winget list --id $Id --exact --accept-source-agreements 2>$null
    if ($LASTEXITCODE -eq 0 -and ($found | Select-String -SimpleMatch $Id)) { Write-Host (T 'Уже установлен.' 'Already installed.'); return }
    winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Write-Host (T "Не удалось установить $Id автоматически. Установите его вручную и повторите." "Could not install $Id automatically. Install it by hand and run this again.") -ForegroundColor Yellow }
}

Install-Package 'Git.Git'
Install-Package 'astral-sh.uv'
Install-Package 'Python.Python.3.13'
if (-not $SkipNode) { Install-Package 'OpenJS.NodeJS.LTS' }
if (-not $SkipFfmpeg) { Install-Package 'Gyan.FFmpeg' }

Write-Host (T "`nДрайвер NVIDIA установите с официального сайта NVIDIA. После установки закройте это окно, откройте новое и запустите setup_models.bat." "`nInstall the NVIDIA driver from NVIDIA's official site. Then close this window, open a new one and run setup_models.bat.") -ForegroundColor Cyan
