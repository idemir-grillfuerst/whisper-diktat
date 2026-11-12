"""Tests für Phase 3: Mikrofon offen halten, Geräteliste neu laden, Hook erneuern, Wächter-Logik, Autostart-Befehl.
Keine echten Tastatureingaben, keine Änderung an der Registry.

Aufruf (im Projektordner):  %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_phase3
"""
import subprocess
import sys
import time

from diktat import PROJEKT
from diktat.autostart import befehl
from diktat.hotkey import PushToTalk
from diktat.recorder import RATE, Recorder

FEHLER = []


def pruefe(name, bedingung):
    print(("OK    " if bedingung else "FEHLER"), name)
    if not bedingung:
        FEHLER.append(name)


def test_recorder_normal():
    r = Recorder(offen_halten=False)
    r.start()
    time.sleep(0.6)
    a = r.stop()
    pruefe("Normal: ~0,6 s Audio", 0.4 < len(a) / RATE < 0.9)
    pruefe("Normal: Mikrofon danach zu", r._stream is None)  # noqa: SLF001
    pruefe("Geräteliste neu laden geht", r.geraete_neu_laden() is True)
    r.start()
    time.sleep(0.3)
    pruefe("Nach Neuladen: Aufnahme geht", len(r.stop()) > 0)


def test_recorder_offen():
    r = Recorder(offen_halten=True, vorlauf_s=0.4)
    r.bereit_machen()
    time.sleep(1.0)
    pruefe("Offen: Stream läuft dauerhaft", r._stream is not None and r._stream.active)  # noqa: SLF001
    r.start()
    time.sleep(0.5)
    a = r.stop()
    pruefe(f"Offen: Vorlauf ist dabei ({len(a) / RATE:.2f} s statt 0,5 s)", 0.8 < len(a) / RATE < 1.1)
    pruefe("Offen: Stream bleibt nach Stopp offen", r._stream is not None)  # noqa: SLF001
    pruefe("Offen: Neu laden während Aufnahme wird abgelehnt", (r.start() or r.geraete_neu_laden()) is False)
    r.stop()
    pruefe("Offen: Neu laden öffnet Stream wieder", r.geraete_neu_laden() and r._stream is not None)  # noqa: SLF001
    r._stream.stop()  # noqa: SLF001  (Headset weg simulieren)
    r.gesund()
    pruefe("Offen: abgebrochener Stream wird repariert", r._stream is not None and r._stream.active)  # noqa: SLF001
    r.schliessen()
    pruefe("Schließen: Mikrofon zu", r._stream is None)  # noqa: SLF001


def test_hook_erneuern():
    ptt = PushToTalk("ctrl+y", lambda e: None)
    ptt.start()
    time.sleep(0.3)
    erster = ptt._hook  # noqa: SLF001
    ptt.erneuern()
    time.sleep(0.3)
    pruefe("Hook wurde neu gesetzt", ptt._hook and ptt._hook != erster)  # noqa: SLF001
    ptt.stop()
    pruefe("Hook beim Stoppen entfernt", ptt._hook is None)  # noqa: SLF001


def test_waechter():
    """Wächter mit einem Ersatz-'Tool', das die Exit-Codes 1, 1, 4, 0 liefert."""
    import tempfile
    from pathlib import Path

    code = r'''
import sys, pathlib
z = pathlib.Path(sys.argv[1]); n = int(z.read_text()) if z.exists() else 0
z.write_text(str(n + 1)); sys.exit([1, 1, 4, 0][n])
'''
    with tempfile.TemporaryDirectory() as d:
        zaehler = Path(d) / "n.txt"
        fake = Path(d) / "fake.py"
        fake.write_text(code)
        skript = f'''
import sys, time, subprocess
sys.path.insert(0, r"{PROJEKT}")
import diktat.waechter as w
w.MUTEX_NAME = "Local\\whisper-diktat-waechter-test"  # unabhängig vom echten, evtl. laufenden Wächter
w.LOG_NAME = "waechter-test.log"
w.time.sleep = lambda s: None
echt = subprocess.Popen
w.subprocess.Popen = lambda args, **kw: echt([sys.executable, r"{fake}", r"{zaehler}"])
w.main()
'''
        t0 = time.monotonic()
        subprocess.run([sys.executable, "-c", skript], timeout=60, check=True)
        pruefe("Wächter: 2 Abstürze + 1 Neustart + regulär = 4 Starts", zaehler.read_text() == "4")
        pruefe(f"Wächter endet nach regulärem Beenden ({time.monotonic() - t0:.1f} s)", True)
    log = (PROJEKT / "logs" / "waechter-test.log").read_text(encoding="utf-8")
    pruefe("Wächter-Log enthält Absturz und Neustart", "abgestürzt" in log and "Neustart gewünscht" in log)


def test_autostart_befehl():
    b = befehl()
    pruefe("Autostart startet start.pyw mit pythonw ohne Konsole",
           "pythonw.exe" in b and b.endswith('start.pyw"') and (PROJEKT / "start.pyw").exists())


if __name__ == "__main__":
    test_recorder_normal()
    test_recorder_offen()
    test_hook_erneuern()
    test_waechter()
    test_autostart_befehl()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
