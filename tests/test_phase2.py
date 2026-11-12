"""Tests für Phase 2: Stufe speichern, Stufe wechseln, Pausieren. Keine echten Tastatureingaben, kein Tray-Fenster.

Aufruf (im Projektordner):
    %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_phase2 [--engine]
"""
import shutil
import sys
import tempfile
import time
from pathlib import Path

from diktat import PROJEKT
from diktat.config import CONFIG_DATEI, fachwort_prompt, speichere_stufe
import diktat.__main__ as hauptmodul

FEHLER = []


def pruefe(name, bedingung):
    print(("OK    " if bedingung else "FEHLER"), name)
    if not bedingung:
        FEHLER.append(name)


def warte(bedingung, max_s):
    ende = time.monotonic() + max_s
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.2)
    return False


def test_stufe_speichern():
    with tempfile.TemporaryDirectory() as d:
        kopie = Path(d) / "config.toml"
        shutil.copy(CONFIG_DATEI, kopie)
        speichere_stufe("leise", kopie)
        inhalt = kopie.read_text(encoding="utf-8")
        pruefe("Stufe 'leise' gespeichert", 'stufe = "leise"' in inhalt)
        pruefe("Kommentare bleiben erhalten", "# Aktive Stufe" in inhalt)
        vorher = CONFIG_DATEI.read_text(encoding="utf-8").splitlines()
        nachher = inhalt.splitlines()
        anders = [i for i, (a, b) in enumerate(zip(vorher, nachher)) if a != b]
        pruefe("Nur die eine Zeile 'stufe = ...' geändert",
               len(vorher) == len(nachher) and len(anders) == 1 and nachher[anders[0]] == 'stufe = "leise"')


def test_fachwort_kuerzen():
    p = fachwort_prompt(max_zeichen=60)
    pruefe("Prompt wird an Wortgrenze gekürzt", p.endswith(".") and len(p) <= 61 and ", ." not in p)


def test_umschalten_und_pause():
    from faster_whisper.audio import decode_audio

    gespeichert = []
    hauptmodul.speichere_stufe = gespeichert.append  # echte config.toml nicht anfassen
    audio = decode_audio(str(PROJEKT / "whisper-test" / "test_de.wav"))[: 16000 * 8]

    app = hauptmodul.App()
    app.stufe = "schnell"
    app.engine = app._neue_engine("schnell")
    app._lade(app.engine)
    pruefe("Start: Stufe schnell geladen (GPU)", app.engine.bereit and app.engine.geraet == "GPU")
    alt = app.engine

    app.waehle_stufe("notfall")
    pruefe("Wechsel: neue Engine ist CPU", app.engine.geraet == "CPU" and app.stufe == "notfall")
    pruefe("Wechsel: Stufe wird gespeichert", gespeichert == ["notfall"])
    pruefe("Wechsel: neue Engine lädt", warte(lambda: app.engine.bereit, 180))
    pruefe("Wechsel: alte GPU-Engine beendet", warte(lambda: alt._proc is None, 10))
    text, sek = app.engine.transkribiere(audio, None)
    print(f"      CPU: {sek:.2f} s -> {text[:60]} …")
    pruefe("CPU-Engine transkribiert", "Kundenservice" in text)

    app.umschalten_pause()
    pruefe("Pause: Shortcut aus", app.hotkey.eingeschaltet is False and app.pausiert)
    pruefe("Pause: Modell entladen", app.engine._proc is None and not app.engine.bereit)
    pruefe("Pause: Symbol pausiert", app.tray.zustand == "pausiert")

    app.waehle_stufe("schnell")
    pruefe("Stufenwechsel in Pause lädt nichts", not app.engine.bereit and app.engine._proc is None)

    app.umschalten_pause()
    pruefe("Fortsetzen: Shortcut an", app.hotkey.eingeschaltet is True and not app.pausiert)
    pruefe("Fortsetzen: GPU-Modell wieder geladen", warte(lambda: app.engine.bereit, 120)
           and app.engine.geraet == "GPU")
    pruefe("Fortsetzen: Symbol bereit", warte(lambda: app.tray.zustand == "bereit", 5))

    # Schneller Doppelwechsel: die zuerst gestartete Engine darf nicht übrig bleiben
    app.waehle_stufe("notfall")
    zwischen = app.engine
    app.waehle_stufe("schnell")
    pruefe("Doppelwechsel: Ziel GPU lädt", warte(lambda: app.engine.bereit, 120) and app.engine.geraet == "GPU")
    pruefe("Doppelwechsel: verworfene CPU-Engine beendet", warte(lambda: zwischen._proc is None, 60))

    # Pause und Ladethread rufen stop() gleichzeitig auf (Absturz vom 12.11. 13:21)
    import threading
    app.umschalten_pause()
    app.umschalten_pause()
    e = app.engine
    fehler = []

    def stopp():
        try:
            e.stop()
        except Exception as ex:  # noqa: BLE001
            fehler.append(ex)
    ts = [threading.Thread(target=stopp) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    pruefe("Gleichzeitiges stop() aus 4 Threads ohne Fehler", fehler == [] and e._proc is None)
    app.umschalten_pause()
    time.sleep(3)  # dem Ladethread Zeit geben, falls er doch etwas starten wollte
    pruefe("Schnelles Pause/Fortsetzen/Pause: nichts lädt nach", app.pausiert and app.engine._proc is None
           and e._proc is None and e.gestoppt)


if __name__ == "__main__":
    test_stufe_speichern()
    test_fachwort_kuerzen()
    if "--engine" in sys.argv:
        test_umschalten_und_pause()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
