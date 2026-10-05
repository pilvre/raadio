# Raadiosalvestaja - one-command installer for Windows 10/11 (PowerShell):
#   irm https://raadio.mastering.ee/install.ps1 | iex
# Installs Python + ffmpeg via winget if missing, downloads the tool to
# %LOCALAPPDATA%\Raadiosalvestaja\app and runs recorder\install.ps1.
# (ASCII only: Windows PowerShell 5.1 + irm|iex mangle non-ASCII text.)
$ErrorActionPreference = "Stop"
$Repo = if ($env:RAADIO_REPO) { $env:RAADIO_REPO } else { "pilvre/raadio" }
$Ref  = if ($env:RAADIO_REF)  { $env:RAADIO_REF }  else { "main" }
$Root = Join-Path $env:LOCALAPPDATA "Raadiosalvestaja"
$App  = Join-Path $Root "app"

Write-Host "Raadiosalvestaja - paigaldus"

function Test-Py {
  foreach ($try in @({ & py -3 -c "import sys; assert sys.version_info >= (3, 9)" 2>$null }, { & python -c "import sys; assert sys.version_info >= (3, 9); assert 'WindowsApps' not in sys.executable" 2>$null })) {
    try { & $try; if ($LASTEXITCODE -eq 0) { return $true } } catch { }
  }
  return $false
}
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

$needPy = -not (Test-Py)
$needFf = -not (Get-Command ffmpeg -ErrorAction SilentlyContinue)
if ($needPy -or $needFf) {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget puudub. Paigalda Microsoft Store'ist 'App Installer' voi kasitsi Python 3 ja ffmpeg."
  }
  if ($needPy) { Write-Host "-> Python (winget)"; winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements }
  if ($needFf) { Write-Host "-> ffmpeg (winget)"; winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements }
  Refresh-Path
}

Write-Host "-> Laen alla: $Repo ($Ref)"
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("raadio-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
  if ($env:RAADIO_SOURCE) {
    Copy-Item -Recurse $env:RAADIO_SOURCE (Join-Path $tmp "src")
  } else {
    $zip = Join-Path $tmp "src.zip"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest "https://github.com/$Repo/archive/refs/heads/$Ref.zip" -OutFile $zip -UseBasicParsing
    Expand-Archive $zip -DestinationPath $tmp
    Move-Item (Get-ChildItem $tmp -Directory | Where-Object Name -like "*-$Ref" | Select-Object -First 1).FullName (Join-Path $tmp "src")
  }
  New-Item -ItemType Directory -Force -Path $App | Out-Null
  # vana kood asendatakse, Pythoni keskkond (.venv) jaab alles
  Get-ChildItem $App -Force | Where-Object Name -ne "recorder" | Remove-Item -Recurse -Force
  if (Test-Path "$App\recorder") { Get-ChildItem "$App\recorder" -Force | Where-Object Name -ne ".venv" | Remove-Item -Recurse -Force }
  Copy-Item -Recurse -Force (Join-Path $tmp "src\*") $App
} finally {
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

& powershell -NoProfile -ExecutionPolicy Bypass -File "$App\recorder\install.ps1"
