#Requires -Version 5.1
# Builds rtx_vsr.exe (RTX Video Super Resolution / TrueHDR as a pipe between two ffmpeg processes) from rtx_vsr.cpp and
# the NVIDIA RTX Video SDK, and puts beside it what it needs at run time: the SDK's nvngx DLLs (signed by NVIDIA), the
# SDK license and NOTICE.txt. Nothing of the SDK goes into git (tools/rtxvsr/.gitignore). The desktop installer ships
# this folder (desktop/scripts/prepare-resources.js); -Zip also makes remiqora-video-rtxvsr-<version>.zip for a release.
# Needs Visual Studio 2022 Build Tools (C++), the CUDA Toolkit (CUDA_PATH) and the SDK:
#   powershell -File tools\rtxvsr\build.ps1 -SdkDir D:\sdk\RTX_Video_SDK_v1.1.0 [-Zip]
param([Parameter(Mandatory = $true)][string]$SdkDir, [string]$CudaDir = $env:CUDA_PATH, [switch]$Zip, [string]$Version = '1.1.0')
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path (Join-Path $SdkDir 'include\nvsdk_ngx.h'))) { throw "Not the RTX Video SDK: $SdkDir" }
if (-not $CudaDir -or -not (Test-Path (Join-Path $CudaDir 'include\cuda.h'))) { throw 'No CUDA Toolkit: set CUDA_PATH or pass -CudaDir' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'No Visual Studio C++ build tools (winget install Microsoft.VisualStudio.2022.BuildTools)' }
$vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat'
$sample = Join-Path $SdkDir 'samples\RTX_Video_API'
$obj = Join-Path $env:TEMP 'rtxvsr-build'
New-Item -ItemType Directory -Force $obj | Out-Null
$cl = "cl /nologo /O2 /EHsc /MD /std:c++17 /Fo`"$obj\\`" /I`"$SdkDir\include`" /I`"$sample`" /I`"$CudaDir\include`" " +
      "`"$here\rtx_vsr.cpp`" `"$sample\rtx_video_api_cuda_impl.cpp`" /Fe:`"$here\rtx_vsr.exe`" " +
      "/link /LIBPATH:`"$SdkDir\lib\Windows\x64`" /LIBPATH:`"$CudaDir\lib\x64`" nvsdk_ngx_d.lib cuda.lib"
cmd /c "call `"$vcvars`" >nul && $cl"
if ($LASTEXITCODE -ne 0) { throw "cl failed with code $LASTEXITCODE" }
Remove-Item (Join-Path $here 'rtx_vsr.exp'), (Join-Path $here 'rtx_vsr.lib') -ErrorAction SilentlyContinue
foreach ($dll in 'nvngx_vsr.dll', 'nvngx_truehdr.dll') {
    $src = Join-Path $SdkDir "bin\Windows\x64\rel\$dll"   # the release x64 build (bin\ also has dev and arm64 ones)
    if (-not (Test-Path $src)) { throw "$dll is not in the SDK's bin\Windows\x64\rel" }
    Copy-Item $src (Join-Path $here $dll) -Force
}
Copy-Item (Join-Path $SdkDir 'NVIDIA_RTX_Video_SDK_License.pdf') $here -Force
$notice = @"
rtx_vsr.exe contains code provided by NVIDIA Corporation (the NVIDIA RTX Video SDK sample rtx_video_api_cuda_impl.cpp).
nvngx_vsr.dll and nvngx_truehdr.dll are the property of NVIDIA Corporation. They and rtx_vsr.exe are distributed under
the NVIDIA RTX Video SDK license (NVIDIA_RTX_Video_SDK_License.pdf), not under the license of the Remiqora Video
repository, and only as part of Remiqora Video.
"@
Set-Content -Path (Join-Path $here 'NOTICE.txt') -Value $notice -Encoding ASCII
$files = 'rtx_vsr.exe', 'nvngx_vsr.dll', 'nvngx_truehdr.dll', 'NVIDIA_RTX_Video_SDK_License.pdf', 'NOTICE.txt' | ForEach-Object { Join-Path $here $_ }
if ($Zip) {
    $out = Join-Path $here "remiqora-video-rtxvsr-$Version.zip"
    Compress-Archive -Path $files -DestinationPath $out -Force
    Write-Host "$out  sha256 $((Get-FileHash $out -Algorithm SHA256).Hash.ToLower())"
}
Write-Host 'rtx_vsr is built in tools\rtxvsr'
