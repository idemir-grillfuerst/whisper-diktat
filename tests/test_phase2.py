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
from diktat.config import (CONFIG_DATEI, fachwort_prompt, lade_config, speichere_geraet, speichere_mikrofon,
                           speichere_modell)
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


def test_auswahl_speichern():
    with tempfile.TemporaryDirectory() as d:
        kopie = Path(d) / "config.toml"
        shutil.copy(CONFIG_DATEI, kopie)
        speichere_geraet("NPU", kopie)
        inhalt = kopie.read_text(encoding="utf-8")
        pruefe("Recheneinheit 'NPU' gespeichert", 'geraet = "NPU"' in inhalt)
        pruefe("Kommentare bleiben erhalten", "# Recheneinheit:" in inhalt)
        vorher = CONFIG_DATEI.read_text(encoding="utf-8").splitlines()
        nachher = inhalt.splitlines()
        anders = [i for i, (a, b) in enumerate(zip(vorher, nachher)) if a != b]
        pruefe("Nur die eine Zeile 'geraet = ...' geändert",
               len(vorher) == len(nachher) and len(anders) == 1 and nachher[anders[0]] == 'geraet = "NPU"')
        speichere_mikrofon('Headset "Yealink" C:\\x', kopie)
        pruefe("Mikrofon mit Sonderzeichen bleibt gültiges TOML",
               lade_config(kopie).mikrofon == 'Headset "Yealink" C:\\x')
        speichere_modell("turbo", kopie)
        pruefe("Modell gespeichert", lade_config(kopie).modell == "turbo")

        # Fehlende Zeile wird im richtigen Abschnitt ergänzt (ältere config.toml ohne 'mikrofon')
        alt = "[allgemein]\nshortcut = \"ctrl+y\"\n\n[modell]\nstufe = \"leise\"\n"
        kopie.write_text(alt, encoding="utf-8")
        speichere_mikrofon("Mic A", kopie)
        cfg = lade_config(kopie)
        pruefe("Fehlende Zeile wird im Abschnitt ergänzt", cfg.mikrofon == "Mic A" and cfg.shortcut == "ctrl+y")
        pruefe("Alte Stufe 'leise' wird zu Turbo auf NPU", cfg.modell == "turbo" and cfg.geraet == "NPU")


def test_fachwort_kuerzen():
    p = fachwort_prompt(max_zeichen=60)
    pruefe("Prompt wird an Wortgrenze gekürzt", p.endswith(".") and len(p) <= 61 and ", ." not in p)


def test_umschalten_und_pause():
    from faster_whisper.audio import decode_audio

    gespeichert = []
    hauptmodul.speichere_geraet = gespeichert.append  # echte config.toml nicht anfassen
    hauptmodul.speichere_modell = gespeichert.append
    audio = decode_audio(str(PROJEKT / "whisper-test" / "test_de.wav"))[: 16000 * 8]

    app = hauptmodul.App()
    app.modell, app.geraet_wahl = "turbo", "GPU"
    app.engine = app._neue_engine()
    app._lade(app.engine)
    pruefe("Start: Turbo auf GPU geladen", app.engine.bereit and app.engine.geraet == "GPU")
    alt = app.engine

    app.waehle_geraet("CPU")
    pruefe("Wechsel: neue Engine ist CPU", app.engine.geraet == "CPU" and app.geraet_wahl == "CPU")
    pruefe("Wechsel: Recheneinheit wird gespeichert", gespeichert == ["CPU"])
    pruefe("Wechsel: neue Engine lädt", warte(lambda: app.engine.bereit, 180))
    pruefe("Wechsel: alte GPU-Engine beendet", warte(lambda: alt._proc is None, 10))
    text, sek = app.engine.transkribiere(audio, None)
    print(f"      CPU: {sek:.2f} s -> {text[:60]} …")
    pruefe("CPU-Engine transkribiert", "Kundenservice" in text)

    app.umschalten_pause()
    pruefe("Pause: Shortcut aus", app.hotkey.eingeschaltet is False and app.pausiert)
    pruefe("Pause: Modell entladen", app.engine._proc is None and not app.engine.bereit)
    pruefe("Pause: Symbol pausiert", app.tray.zustand == "pausiert")

    app.waehle_geraet("GPU")
    pruefe("Wechsel in Pause lädt nichts", not app.engine.bereit and app.engine._proc is None)

    app.umschalten_pause()
    pruefe("Fortsetzen: Shortcut an", app.hotkey.eingeschaltet is True and not app.pausiert)
    pruefe("Fortsetzen: GPU-Modell wieder geladen", warte(lambda: app.engine.bereit, 120)
           and app.engine.geraet == "GPU")
    pruefe("Fortsetzen: Symbol bereit", warte(lambda: app.tray.zustand == "bereit", 5))

    # Schneller Doppelwechsel: die zuerst gestartete Engine darf nicht übrig bleiben
    app.waehle_geraet("CPU")
    zwischen = app.engine
    app.waehle_geraet("GPU")
    pruefe("Doppelwechsel: Ziel GPU lädt", warte(lambda: app.engine.bereit, 120) and app.engine.geraet == "GPU")
    pruefe("Doppelwechsel: verworfene CPU-Engine beendet", warte(lambda: zwischen._proc is None, 60))

    # "auto" löst hier zu GPU auf: gleiche Engine, nichts neu laden
    vorher = app.engine
    app.waehle_geraet("auto")
    pruefe("auto = GPU: Engine bleibt geladen, kein Neuladen",
           app.engine is vorher and app.engine.bereit and app.geraet == "GPU")

    # Modell wechseln
    app.waehle_modell("large-v3")
    pruefe("Modellwechsel: large-v3 lädt auf GPU", warte(lambda: app.engine.bereit, 180)
           and "large-v3-int8" in app.engine.repo and app.engine.geraet == "GPU")
    app.waehle_modell("turbo")
    pruefe("Zurück auf Turbo", warte(lambda: app.engine.bereit, 120) and "turbo" in app.engine.repo)

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
    test_auswahl_speichern()
    test_fachwort_kuerzen()
    if "--engine" in sys.argv:
        test_umschalten_und_pause()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
