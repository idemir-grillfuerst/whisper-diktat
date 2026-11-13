<#
.SYNOPSIS
  Installiert whisper-diktat für den aktuellen Windows-Benutzer (keine Adminrechte nötig).

.DESCRIPTION
  1. uv (Python-Paketmanager) suchen, sonst von astral.sh installieren
  2. Python 3.12 und die Umgebung unter %USERPROFILE%\.venvs anlegen (kurze Pfade, wegen der 260-Zeichen-Grenze)
  3. Pakete aus requirements.txt installieren
  4. python -m diktat.einrichten: persönliche Dateien, Geräteprüfung, Modell-Download, Verknüpfungen, Autostart
  5. Tool starten

  Aufruf im Projektordner:
    powershell -ExecutionPolicy Bypass -File install.ps1
  Optionen: -OhneAutostart -OhneVerknuepfung -NichtStarten -MitTests -Venv <Pfad> -Desktop <Ordner> -Uv <uv.exe>
  Erneut ausführen ist unbedenklich: Vorhandenes wird wiederverwendet, persönliche Einstellungen bleiben.
#>
param(
    [string]$Venv = (Join-Path $env:USERPROFILE ".venvs\whisper"),
    [string]$Desktop = "",
    [string]$Uv = "",
    [switch]$OhneAutostart,
    [switch]$OhneVerknuepfung,
    [switch]$NichtStarten,
    [switch]$MitTests
)
$ErrorActionPreference = "Stop"
$Projekt = $PSScriptRoot
Set-Location $Projekt

function Schritt($text) { Write-Host "`n== $text ==" -ForegroundColor Cyan }
function Abbruch($text) { Write-Host "FEHLER: $text" -ForegroundColor Red; exit 1 }

Schritt "Voraussetzungen"
if (-not [Environment]::Is64BitOperatingSystem) { Abbruch "Nur 64-Bit-Windows wird unterstützt." }
$os = (Get-CimInstance Win32_OperatingSystem).Caption
$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Write-Host "  $os, $cpu, $ram GB RAM"
if ($ram -lt 8) { Write-Host "  WARNUNG: Weniger als 8 GB RAM, das Modell braucht 2–4 GB." -ForegroundColor Yellow }
$frei = [math]::Round((Get-PSDrive ($env:USERPROFILE.Substring(0, 1))).Free / 1GB)
if ($frei -lt 5) { Abbruch "Nur $frei GB frei auf dem Laufwerk des Benutzerordners, gebraucht werden ca. 5 GB." }

Schritt "uv suchen"
if ($Uv) { if (-not (Test-Path $Uv)) { Abbruch "uv nicht gefunden: $Uv" }; $uv = $Uv } else { $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source }
if (-not $uv) {
    foreach ($k in @("$env:USERPROFILE\.local\bin\uv.exe", "$env:USERPROFILE\.cargo\bin\uv.exe", "$env:LOCALAPPDATA\Programs\uv\uv.exe")) {
        if (Test-Path $k) { $uv = $k; break }
    }
}
if (-not $uv) {
    Write-Host "  uv nicht gefunden, installiere von https://astral.sh/uv ..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $uv = "$env:USERPROFILE\.local\bin\uv.exe"
    if (-not (Test-Path $uv)) { Abbruch "uv-Installation fehlgeschlagen. Siehe https://docs.astral.sh/uv/" }
}
Write-Host "  $uv"

Schritt "Python 3.12 und Umgebung"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE ".venvs\python"
& $uv python install 3.12
if ($LASTEXITCODE) { Abbruch "Python 3.12 konnte nicht installiert werden." }
$py = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
    & $uv venv --python 3.12 $Venv
    if ($LASTEXITCODE) { Abbruch "Umgebung $Venv konnte nicht angelegt werden." }
}
Write-Host "  $Venv"

Schritt "Pakete installieren"
& $uv pip install --python $py -r (Join-Path $Projekt "requirements.txt")
if ($LASTEXITCODE) { Abbruch "Paketinstallation fehlgeschlagen." }
if ($MitTests) {
    & $uv pip install --python $py -r (Join-Path $Projekt "requirements-test.txt")
    if ($LASTEXITCODE) { Abbruch "Installation der Testpakete fehlgeschlagen." }
}

Schritt "Einrichten"
$argumente = @("-m", "diktat.einrichten")
if ($OhneAutostart) { $argumente += "--ohne-autostart" }
if ($OhneVerknuepfung) { $argumente += "--ohne-verknuepfung" }
if ($Desktop) { $argumente += @("--desktop", $Desktop) }
$env:PYTHONIOENCODING = "utf-8"
& $py @argumente
if ($LASTEXITCODE) { Abbruch "Einrichtung fehlgeschlagen (siehe Meldungen oben)." }

if (-not $NichtStarten) {
    Schritt "Starten"
    # Über die Aufgabenplanung bzw. explorer.exe starten, damit das Tool nicht am aufrufenden Fenster hängt
    if (-not $OhneAutostart) {
        schtasks /Run /TN whisper-diktat | Out-Null
    } else {
        Start-Process explorer.exe -ArgumentList "`"$(Join-Path $Projekt 'Whisper Diktat starten.lnk')`""
    }
    Write-Host "  Gestartet. Unten rechts in der Taskleiste erscheint ein Mikrofon-Symbol (evtl. hinter dem ^)."
    Write-Host "  Blau = lädt, grau = bereit. Dann Strg+Y halten, sprechen, loslassen."
}
Write-Host "`nINSTALLATION OK" -ForegroundColor Green