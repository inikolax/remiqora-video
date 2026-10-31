#Requires -Version 5.1
param(
    [string]$ModelsDir,
    [string[]]$Find,
    [string]$Sets,
    [Alias('Profile')][ValidateSet('', 'minimum', 'faces', 'all')][string]$SetProfile = '',   # not $Profile: PowerShell's own variable
    [switch]$SkipWeights,
    [switch]$SkipEngine,
    [switch]$SkipApp,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

# Message language: REMIQORA_VIDEO_LANG if set (the desktop wizard does not run these scripts), else the Windows display language; Russian or English
$lang = if ($env:REMIQORA_VIDEO_LANG) { $env:REMIQORA_VIDEO_LANG } else { (Get-UICulture).TwoLetterISOLanguageName }
$script:ru = $lang.ToLowerInvariant().StartsWith('ru')
function T([string]$Ru, [string]$En) { if ($script:ru) { $Ru } else { $En } }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$engine = Join-Path $root 'engine'

# winget writes new PATH entries to the registry; refresh them in this PowerShell process so a GUI
# installer can install prerequisites and then continue without asking the user to reopen a terminal.
$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$env:Path = @($env:Path, $machinePath, $userPath) -join ';'

function Require-Command([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw (T "Не найдено '$Name'. $Hint" "'$Name' not found. $Hint") }
}
function Invoke-Native([string]$Name, [string[]]$NativeArgs) {
    & $Name @NativeArgs
    if ($LASTEXITCODE -ne 0) { throw (T "Команда завершилась с кодом $LASTEXITCODE`: $Name $($NativeArgs -join ' ')" "Command exited with code $LASTEXITCODE`: $Name $($NativeArgs -join ' ')") }
}
function Invoke-Native-Retry([string]$Name, [string[]]$NativeArgs, [int]$Attempts = 5) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        & $Name @NativeArgs
        if ($LASTEXITCODE -eq 0) { return }
        if ($attempt -lt $Attempts) {
            $delay = [Math]::Min(30, 3 * [Math]::Pow(2, $attempt - 1))
            Write-Host (T "Сетевой запрос не завершился (код $LASTEXITCODE). Повтор $attempt из $($Attempts - 1) через $([int]$delay) сек…" "Network request failed (code $LASTEXITCODE). Retry $attempt of $($Attempts - 1) in $([int]$delay) s…") -ForegroundColor Yellow
            Start-Sleep -Seconds ([int]$delay)
        }
    }
    throw (T "Команда не удалась после $Attempts попыток (код $LASTEXITCODE): $Name $($NativeArgs -join ' ')" "Command failed after $Attempts attempts (code $LASTEXITCODE): $Name $($NativeArgs -join ' ')")
}
function Resolve-ModelRoots {
    param([string]$DefaultPath, [string[]]$SearchRoots)
    if (-not $DefaultPath) { $DefaultPath = Join-Path $env:LOCALAPPDATA 'RemiqoraVideo\models' }
    Write-Host (T "`nПапка для моделей. Можно выбрать существующую папку ComfyUI/Comfy Desktop с подпапками моделей." "`nModels folder. You can pick an existing ComfyUI/Comfy Desktop folder with model subfolders.")
    Write-Host (T "Папка по умолчанию: $DefaultPath" "Default folder: $DefaultPath")
    if (-not $ModelsDir -and -not $DryRun) {
        $answer = Read-Host (T 'Введите путь, нажмите B чтобы выбрать папку в окне, или Enter для пути по умолчанию' 'Type a path, press B to pick a folder in a window, or Enter for the default')
        if ($answer.Trim().ToUpperInvariant() -eq 'B') {
            Add-Type -AssemblyName System.Windows.Forms
            $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
            $dialog.Description = T 'Выберите папку models (или общую папку с подпапкой models)' 'Choose the models folder (or a parent folder that has a models subfolder)'
            $dialog.ShowNewFolderButton = $true
            $dialog.SelectedPath = $DefaultPath
            if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $DefaultPath = $dialog.SelectedPath }
        } elseif ($answer.Trim()) { $DefaultPath = $answer.Trim().Trim('"') }
    }
    $roots = @($DefaultPath)
    if ($SearchRoots) { $roots += $SearchRoots }
    $roots = @($roots | ForEach-Object {
        $candidate = [IO.Path]::GetFullPath($_)
        foreach ($nested in @((Join-Path $candidate 'models'), (Join-Path $candidate 'ComfyUI\models'))) {
            if (-not (Test-Path (Join-Path $candidate 'diffusion_models')) -and (Test-Path (Join-Path $nested 'diffusion_models'))) { $candidate = $nested; break }
        }
        $candidate
    } | Select-Object -Unique)
    foreach ($path in $roots) {
        if (-not (Test-Path -LiteralPath $path)) {
            if ($path -eq $DefaultPath) { New-Item -ItemType Directory -Path $path -Force | Out-Null }
            else { throw (T "Указанная папка моделей не существует: $path" "The models folder does not exist: $path") }
        }
    }
    $found = foreach ($path in $roots) {
        Get-ChildItem -LiteralPath $path -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in '.safetensors','.gguf','.ckpt','.pt','.bin' } |
            Select-Object -First 20 -ExpandProperty FullName
    }
    if ($found) { Write-Host (T 'Найдены существующие веса. Они останутся на месте и будут подключены:' 'Existing weights found. They stay where they are and will be connected:'); $found | Select-Object -First 8 | ForEach-Object { Write-Host "  $_" } }
    else { Write-Host (T 'В выбранной папке пока не найдены файлы моделей. Её можно оставить пустой и скачать веса позже со страницы «Модели».' 'No model files in the chosen folder yet. You can leave it empty and download the weights later from the Models page.') -ForegroundColor Yellow }
    return $roots
}
function Set-DotEnvValue([string]$Path, [string]$Key, [string]$Value) {
    # .env is UTF-8 without BOM (python-dotenv reads it so); Get-Content/Set-Content in PowerShell 5.1 would read it as
    # the ANSI codepage and write a BOM, turning the comments' «» into mojibake
    $lines = @(if (Test-Path -LiteralPath $Path) { [IO.File]::ReadAllLines($Path, $utf8) })
    $prefix = "$Key="
    $replacement = "$Key=$Value"
    $found = $false
    $out = foreach ($line in $lines) {
        if ($line.StartsWith($prefix)) { $found = $true; $replacement } else { $line }
    }
    if (-not $found) { $out += $replacement }
    [IO.File]::WriteAllLines($Path, [string[]]$out, $utf8)
}

$modelRoots = @(Resolve-ModelRoots -DefaultPath $ModelsDir -SearchRoots $Find)
if ($DryRun) {
    Write-Host (T "`nПроверка пройдена: папки моделей будут подключены через H3_MODEL_ROOTS=$($modelRoots -join ';')" "`nCheck passed: the model folders will be connected through H3_MODEL_ROOTS=$($modelRoots -join ';')")
    exit 0
}

$python = $null
$needPython = (-not $SkipEngine) -or ((-not $SkipApp) -and -not (Test-Path (Join-Path $root '.venv\Scripts\python.exe')))
if ($needPython) {
    if (Get-Command py -ErrorAction SilentlyContinue) { $python = (& py -3.13 -c 'import sys; print(sys.executable)' 2>$null | Select-Object -First 1) }
    if (-not $python -or -not (Test-Path -LiteralPath $python)) { throw (T 'Нужен Python 3.13. Запустите setup_prereqs.bat, затем откройте новое окно.' 'Python 3.13 is required. Run setup_prereqs.bat, then open a new window.') }
}

$envFile = Join-Path $root '.env'
if (-not (Test-Path -LiteralPath $envFile)) { Copy-Item (Join-Path $root '.env.example') $envFile }
Set-DotEnvValue $envFile 'H3_MODEL_ROOTS' ($modelRoots -join ';')
$primary = $modelRoots[0]
Set-DotEnvValue $envFile 'H3_REF_DIR' $primary
Set-DotEnvValue $envFile 'LLM_DIRS' (Join-Path $primary 'llm')
Set-DotEnvValue $envFile 'LORA_DIRS' (Join-Path $primary 'loras\h3')
Set-DotEnvValue $envFile 'LTX23_LORA_DIRS' (Join-Path $primary 'loras\ltx23')
Set-DotEnvValue $envFile 'LTX25_LORA_DIRS' (Join-Path $primary 'loras\ltx25')
Set-DotEnvValue $envFile 'WAN_LORA_DIRS' (Join-Path $primary 'loras\wan5b')
Set-DotEnvValue $envFile 'KREA_LORA_DIRS' (Join-Path $primary 'loras\krea2')
foreach ($folder in @('diffusion_models','text_encoders','vae','loras','checkpoints','latent_upscale_models','llm','loras\h3','loras\ltx23','loras\ltx25','loras\wan5b','loras\krea2')) {
    New-Item -ItemType Directory -Path (Join-Path $primary $folder) -Force | Out-Null
}

if (-not $SkipEngine) {
    Require-Command 'git' (T 'Запустите setup_prereqs.bat.' 'Run setup_prereqs.bat.')
    Require-Command 'uv' (T 'Запустите setup_prereqs.bat.' 'Run setup_prereqs.bat.')
    $coreInfo = @(Get-Content (Join-Path $engine 'core.txt') | Where-Object { $_.Trim() })
    if ($coreInfo.Count -lt 2) { throw (T 'engine\core.txt должен содержать URL репозитория и закреплённый commit SHA.' 'engine\core.txt must hold the repository URL and the pinned commit SHA.') }
    $repoUrl, $sha = $coreInfo[0].Trim(), $coreInfo[1].Trim()
    $comfy = Join-Path $engine 'ComfyUI'
    if (-not (Test-Path (Join-Path $comfy '.git'))) { New-Item -ItemType Directory -Path $comfy -Force | Out-Null; Invoke-Native git @('-C',$comfy,'init','-q'); Invoke-Native git @('-C',$comfy,'remote','add','origin',$repoUrl) }
    $gitLock = Join-Path $comfy '.git\index.lock'
    if (Test-Path -LiteralPath $gitLock) {
        $activeGit = @(Get-Process -Name git -ErrorAction SilentlyContinue)
        if ($activeGit.Count -gt 0) { throw (T 'Git ещё работает. Дождитесь завершения другого процесса установки и повторите запуск.' 'Git is still running. Wait for the other install process to finish and run this again.') }
        Write-Host (T 'Удаляю оставшийся lock-файл Git после прерванной установки.' 'Removing the Git lock file left by an interrupted install.') -ForegroundColor Yellow
        Remove-Item -LiteralPath $gitLock -Force
    }
    # Fetch advertised refs rather than a raw SHA (GitHub may reject an unadvertised commit fetch).
    Invoke-Native-Retry git @('-C',$comfy,'fetch','-q','--filter=blob:none','origin')
    Invoke-Native git @('-C',$comfy,'-c','advice.detachedHead=false','checkout','-q','--force',$sha)
    $env:UV_PYTHON = $python
    $env:UV_PYTHON_DOWNLOADS = 'never'
    $env:UV_LINK_MODE = 'copy'
    Invoke-Native uv @('sync','--project',$engine,'--frozen')
    $enginePython = Join-Path $engine '.venv\Scripts\python.exe'
    Invoke-Native $enginePython @('-c',"import torch; assert torch.cuda.is_available(), 'CUDA is unavailable or the NVIDIA driver is too old'; print('torch', torch.__version__, '-', torch.cuda.get_device_name(0))")
}

if (-not $SkipApp -and -not (Test-Path (Join-Path $root '.venv\Scripts\python.exe'))) {
    Invoke-Native $python @('-m','venv',(Join-Path $root '.venv'))
    Invoke-Native (Join-Path $root '.venv\Scripts\python.exe') @('-m','pip','install','--upgrade','pip')
    Invoke-Native (Join-Path $root '.venv\Scripts\pip.exe') @('install','-r',(Join-Path $root 'requirements.txt'))
}

# The model sets: the official weights of install\manifest.json, the same downloader the desktop wizard runs
$appPython = Join-Path $root '.venv\Scripts\python.exe'
$weightsCode = 0
if (-not $SkipWeights -and (Test-Path $appPython)) {
    if (-not $Sets -and -not $SetProfile) {
        Write-Host (T "`nКакие модели скачать? Только официальные веса; свои файлы подключаются на странице «Модели»." "`nWhich models to download? Official weights only; your own files are connected on the Models page.")
        Write-Host (T '  1  Минимум: H3 и сценарист                     ~53 ГБ' '  1  Minimum: H3 and the writer                         ~53 GB')
        Write-Host (T '  2  + картинки Krea 2 и лица по фото (Ref2VA)   ~95 ГБ' '  2  + Krea 2 pictures and faces from photos (Ref2VA)   ~95 GB')
        Write-Host (T '  3  Всё: + LTX 2.5, LTX 2.3, WAN 2.2 5B         ~196 ГБ' '  3  Everything: + LTX 2.5, LTX 2.3, WAN 2.2 5B         ~196 GB')
        Write-Host (T '  4  Ничего сейчас (скачать позже на странице «Модели»)' '  4  Nothing now (download later on the Models page)')
        $answer = Read-Host (T 'Номер' 'Number')
        $SetProfile = @{ '1' = 'minimum'; '2' = 'faces'; '3' = 'all' }[$answer.Trim()]
    }
    if ($Sets -or $SetProfile) {
        $pick = if ($Sets) { @('--sets', $Sets) } else { @('--profile', $SetProfile) }
        $findArg = @($modelRoots | Select-Object -Skip 1) -join ';'
        & $appPython (Join-Path $root 'tools\install_models.py') --lang (T 'ru' 'en') --models-dir $primary --find $findArg @pick
        $weightsCode = $LASTEXITCODE
        if ($weightsCode -eq 2) { Write-Host (T 'Часть наборов не скачалась: запустите setup_models.bat ещё раз, он продолжит с того же места.' 'Some sets did not download: run setup_models.bat again, it resumes where it stopped.') -ForegroundColor Yellow }
        elseif ($weightsCode -ne 0) { throw (T "Загрузка моделей завершилась с кодом $weightsCode" "The model download exited with code $weightsCode") }
    }
}

Write-Host (T "`nУстановка завершена. Папки моделей подключены: $($modelRoots -join ';')" "`nInstall finished. Model folders connected: $($modelRoots -join ';')") -ForegroundColor Green
Write-Host (T 'Запустите dev.bat. Недостающие веса можно докачать на странице «Модели».' 'Run dev.bat. Missing weights can be downloaded later on the Models page.')
