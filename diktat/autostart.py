"""Autostart über die Windows-Aufgabenplanung (keine Adminrechte nötig).

Warum nicht mehr HKCU\\...\\Run: Run-Einträge starten nur bei der Anmeldung. Nach dem Aufwachen aus Standby oder
Ruhezustand gibt es keine Anmeldung, nur ein Entsperren. Ist das Tool zwischendurch verschwunden (13.11.2026:
spurlos zwischen Abend und Morgen), kam es nicht wieder.

Die Aufgabe „whisper-diktat“ startet start.pyw (Wächter -> Tool):
  - bei der Anmeldung (15 s verzögert),
  - beim Entsperren des Rechners,
  - alle 10 Minuten als Sicherheitsnetz.
Läuft das Tool schon, beendet sich der neue Start sofort (Mutex im Wächter). Außerdem gilt
MultipleInstancesPolicy=IgnoreNew: Solange der Wächter läuft, startet die Aufgabe gar nichts.

Aufruf von Hand:  python -m diktat.autostart [an|aus|status]
"""
import os
import subprocess
import sys
import tempfile
import winreg
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from . import PROJEKT
from .waechter import pythonw

AUFGABE = "whisper-diktat"
RUN_SCHLUESSEL = r"Software\Microsoft\Windows\CurrentVersion\Run"
CREATE_NO_WINDOW = 0x08000000


def benutzer() -> str:
    return f"{os.environ.get('USERDOMAIN', '')}\\{os.environ['USERNAME']}".lstrip("\\")


def befehl() -> str:
    return f'"{pythonw()}" "{PROJEKT / "start.pyw"}"'


def aufgaben_xml(name: str = AUFGABE, intervall_min: int = 10) -> str:
    u = escape(benutzer())
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Startet whisper-diktat (lokales Diktier-Tool) bei Anmeldung, Entsperren und alle {intervall_min} Minuten, falls es nicht läuft.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{u}</UserId><Delay>PT15S</Delay></LogonTrigger>
    <SessionStateChangeTrigger><Enabled>true</Enabled><StateChange>SessionUnlock</StateChange><UserId>{u}</UserId></SessionStateChangeTrigger>
    <TimeTrigger>
      <Repetition><Interval>PT{intervall_min}M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>{date.today().isoformat()}T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>{u}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(pythonw())}</Command>
      <Arguments>"{escape(str(PROJEKT / "start.pyw"))}"</Arguments>
      <WorkingDirectory>{escape(str(PROJEKT))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(*args) -> subprocess.CompletedProcess:
    # schtasks schreibt in der OEM-Codepage (Umlaute in deutschen Meldungen)
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, encoding="oem", errors="replace",
                          creationflags=CREATE_NO_WINDOW)


def aufgabe_registrieren(name: str = AUFGABE, xml: str | None = None) -> None:
    with tempfile.TemporaryDirectory() as d:
        datei = Path(d) / "aufgabe.xml"
        datei.write_text(xml or aufgaben_xml(name), encoding="utf-16")
        r = _schtasks("/Create", "/TN", name, "/XML", str(datei), "/F")
    if r.returncode != 0:
        raise OSError(f"Aufgabe konnte nicht angelegt werden: {(r.stderr or r.stdout).strip()}")


def aufgabe_loeschen(name: str = AUFGABE) -> None:
    _schtasks("/Delete", "/TN", name, "/F")


def aufgabe_existiert(name: str = AUFGABE) -> bool:
    return _schtasks("/Query", "/TN", name).returncode == 0


def _run_eintrag_loeschen() -> None:
    """Alten Autostart (bis v0.4) entfernen, damit nicht doppelt gestartet wird."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_SCHLUESSEL, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, AUFGABE)
    except FileNotFoundError:
        pass


def ist_aktiv() -> bool:
    return aufgabe_existiert()


def aktivieren() -> None:
    aufgabe_registrieren()
    _run_eintrag_loeschen()


def deaktivieren() -> None:
    aufgabe_loeschen()
    _run_eintrag_loeschen()


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    if arg == "an":
        aktivieren()
    elif arg == "aus":
        deaktivieren()
    print(f"Autostart (Aufgabenplanung '{AUFGABE}'): {'AN' if ist_aktiv() else 'AUS'}  ({befehl()})")
