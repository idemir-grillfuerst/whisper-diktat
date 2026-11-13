"""Tests für den Autostart über die Aufgabenplanung.

Legt eine Test-Aufgabe „whisper-diktat-test“ mit harmloser Aktion an (cmd /c exit) und löscht sie wieder.
Die echte Aufgabe „whisper-diktat“ und der Run-Eintrag werden nicht angefasst.
Aufruf (im Projektordner):  %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_autostart
"""
import subprocess
import sys
import xml.etree.ElementTree as ET

from diktat import autostart
from diktat.waechter import pythonw

FEHLER = []
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
TEST = "whisper-diktat-test"


def pruefe(name, bedingung):
    print(("OK    " if bedingung else "FEHLER"), name)
    if not bedingung:
        FEHLER.append(name)


def test_xml():
    x = autostart.aufgaben_xml()
    root = ET.fromstring(x.replace('encoding="UTF-16"', ""))
    pruefe("Trigger: Anmeldung", root.find("t:Triggers/t:LogonTrigger", NS) is not None)
    pruefe("Trigger: Entsperren",
           root.findtext("t:Triggers/t:SessionStateChangeTrigger/t:StateChange", namespaces=NS) == "SessionUnlock")
    pruefe("Trigger: alle 10 Minuten",
           root.findtext("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval", namespaces=NS) == "PT10M")
    pruefe("Kein zweiter Start, solange der Wächter läuft",
           root.findtext("t:Settings/t:MultipleInstancesPolicy", namespaces=NS) == "IgnoreNew")
    pruefe("Kein Zeitlimit, läuft auch im Akkubetrieb",
           root.findtext("t:Settings/t:ExecutionTimeLimit", namespaces=NS) == "PT0S"
           and root.findtext("t:Settings/t:DisallowStartIfOnBatteries", namespaces=NS) == "false"
           and root.findtext("t:Settings/t:StopIfGoingOnBatteries", namespaces=NS) == "false")
    pruefe("Ohne Adminrechte (LeastPrivilege, InteractiveToken)",
           root.findtext("t:Principals/t:Principal/t:RunLevel", namespaces=NS) == "LeastPrivilege"
           and root.findtext("t:Principals/t:Principal/t:LogonType", namespaces=NS) == "InteractiveToken")
    pruefe("Aktion: pythonw start.pyw",
           root.findtext("t:Actions/t:Exec/t:Command", namespaces=NS) == pythonw()
           and root.findtext("t:Actions/t:Exec/t:Arguments", namespaces=NS).endswith('start.pyw"'))


def test_registrieren():
    x = autostart.aufgaben_xml(TEST)
    x = x.replace(f"<Command>{pythonw()}</Command>", "<Command>cmd.exe</Command>")
    x = x.split("<Arguments>")[0] + "<Arguments>/c exit</Arguments>" + x.split("</Arguments>")[1]
    autostart.aufgabe_loeschen(TEST)
    try:
        autostart.aufgabe_registrieren(TEST, x)
        pruefe("Test-Aufgabe ohne Adminrechte angelegt", autostart.aufgabe_existiert(TEST))
        r = subprocess.run(["schtasks", "/Query", "/TN", TEST, "/XML"], capture_output=True, text=True)
        pruefe("Windows hat alle 3 Trigger übernommen",
               "LogonTrigger" in r.stdout and "SessionUnlock" in r.stdout and "PT10M" in r.stdout)
    except OSError as e:
        pruefe(f"Test-Aufgabe ohne Adminrechte angelegt ({e})", False)
    finally:
        autostart.aufgabe_loeschen(TEST)
    pruefe("Test-Aufgabe wieder gelöscht", not autostart.aufgabe_existiert(TEST))


if __name__ == "__main__":
    test_xml()
    test_registrieren()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
