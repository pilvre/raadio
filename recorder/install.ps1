# Raadiosalvestaja paigaldus Windowsile: venv, seaded, taustateenus (Task Scheduler), `raadio` käsk.
# Mitteinteraktiivselt (nt CI): $env:RAADIO_NONINTERACTIVE=1; $env:RAADIO_MODE="local"; $env:RAADIO_PASS="..."
$ErrorActionPreference = "Stop"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Task = "Raadiosalvestaja"
$ConfDir = Join-Path $HOME ".config\raadiosalvestaja"
$Conf = Join-Path $ConfDir "config.env"
$LogFile = Join-Path $env:LOCALAPPDATA "Raadiosalvestaja\salvestaja.log"
$Utf8 = New-Object System.Text.UTF8Encoding $false

function Ask($q, $def) {
  if ($env:RAADIO_NONINTERACTIVE) { return $def }
  $a = Read-Host $q
  if ([string]::IsNullOrWhiteSpace($a)) { return $def } else { return $a }
}
function Set-ConfLine($key, $value) {
  $lines = [System.IO.File]::ReadAllLines($Conf, $Utf8)
  $found = $false
  $lines = $lines | ForEach-Object { if ($_ -match "^$key=") { $found = $true; "$key=$value" } else { $_ } }
  if (-not $found) { $lines += "$key=$value" }
  [System.IO.File]::WriteAllLines($Conf, [string[]]$lines, $Utf8)
}
function Find-Python {
  $probe = "import sys; assert sys.version_info >= (3, 9); print(sys.executable)"
  foreach ($try in @({ & py -3 -c $probe 2>$null }, { & python -c $probe 2>$null })) {
    try {
      $exe = & $try
      # WindowsApps\python.exe on Microsoft Store'i suunaja, mitte päris Python
      if ($LASTEXITCODE -eq 0 -and $exe -and $exe -notlike "*WindowsApps*") { return "$exe".Trim() }
    } catch { }
  }
  return $null
}

$ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if (-not $ffmpeg) { throw "ffmpeg puudub (winget install Gyan.FFmpeg)" }
$py = Find-Python
if (-not $py) { throw "Python 3.9+ puudub (winget install Python.Python.3.12)" }

# töötav teenus hoiab .venv faile lukus
Stop-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='ffmpeg.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like '*write_xing*' } | Invoke-CimMethod -MethodName Terminate | Out-Null
Start-Sleep -Seconds 1

Write-Host "-> Pythoni keskkond"
& $py -m venv "$Dir\.venv"
& "$Dir\.venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r "$Dir\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw "pip install ebaõnnestus" }

if (-not (Test-Path $Conf)) {
  New-Item -ItemType Directory -Force -Path $ConfDir | Out-Null
  Copy-Item "$Dir\config.env.example" $Conf
  $mode = $env:RAADIO_MODE
  if (-not $mode) {
    Write-Host ""
    Write-Host "Kus salvestusi hoida?"
    Write-Host "  1) Siin arvutis (soovitatav - pilve pole vaja, telefonist koduvõrgus)"
    Write-Host "  2) Cloudflare R2 (kuulamine kõikjal, vajab Cloudflare'i seadistamist)"
    $mode = if ((Ask "Valik [1]" "1") -eq "2") { "r2" } else { "local" }
  }
  if ($mode -eq "r2") {
    Set-ConfLine "STORAGE" "r2"
    Write-Host "-> Täida R2 andmed failis $Conf ja käivita paigaldaja uuesti."
    if (-not $env:RAADIO_NONINTERACTIVE) { Start-Process notepad $Conf }
    exit 0
  }
  $pass = $env:RAADIO_PASS
  if (-not $pass) { $pass = Ask "Veebilehe parool (soovitatav, tühi = ilma)" "" }
  if ($pass) { Set-ConfLine "WEB_PASS" $pass }
}
Set-ConfLine "FFMPEG" $ffmpeg
Set-ConfLine "LOG_FILE" $LogFile
New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
$confText = [System.IO.File]::ReadAllText($Conf, $Utf8)
if ($confText -match "(?m)^STORAGE=r2" -and $confText -notmatch "(?m)^R2_SECRET_ACCESS_KEY=.+") {
  throw "Täida R2 andmed failis $Conf"
}

Write-Host "-> Taustateenus (Task Scheduler)"
$pythonw = "$Dir\.venv\Scripts\pythonw.exe"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$Dir\kuku_recorder.py`"" -WorkingDirectory $Dir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
# kordus iga 5 min: kui protsess on kokku jooksnud, käivitub uuesti (töötava kõrvale uut ei teki)
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)).Repetition
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $Task -Action $action -Trigger $trigger -Settings $settings `
  -Description "Raadiosalvestaja – salvestab valitud raadiosaateid" -Force | Out-Null
Start-ScheduledTask -TaskName $Task

# käsk `raadio` (WindowsApps kaust on vaikimisi PATH-is)
$cmd = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\raadio.cmd"
[System.IO.File]::WriteAllText($cmd, "@`"$Dir\.venv\Scripts\python.exe`" `"$Dir\raadio.py`" %*`r`n", $Utf8)

if ($confText -notmatch "(?m)^STORAGE=r2") {
  # tulemüür: telefon peab saama veebilehe poole pöörduda (privaatvõrgus)
  $rule = "Raadiosalvestaja"
  if (-not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)) {
    if ((Ask "Luba telefonil arvuti veebilehte avada? Windows küsib administraatori kinnitust. [J/e]" "j") -notmatch "^[eEnN]") {
      $fw = "New-NetFirewallRule -DisplayName '$rule' -Direction Inbound -Program '$pythonw' -Action Allow -Profile Private,Domain | Out-Null"
      try {
        $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if ($isAdmin) { Invoke-Expression $fw } else { Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile", "-Command", $fw }
      } catch { Write-Host "   (tulemüüri reeglit ei õnnestunud lisada – Windows võib küsida luba esimesel käivitamisel)" }
    }
  }
  if ((Ask "Kas lülitada vooluvõrgus unerežiim välja (arvuti peab salvestamiseks ärkvel olema)? [J/e]" "j") -notmatch "^[eEnN]") {
    powercfg /change standby-timeout-ac 0 | Out-Null
  }
}

Start-Sleep -Seconds 5
Write-Host ""
Write-Host "Valmis."
$u = & "$Dir\.venv\Scripts\python.exe" "$Dir\raadio.py" url
if ($u -like "http*") { Write-Host "  Ava telefonis (samas Wi-Fi võrgus): $u" }
Write-Host "  Olek: raadio   (uues terminaliaknas)"
