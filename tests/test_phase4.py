"""Tests für Phase 4: Bedienmodi (halten, umschalten, beides), Maximaldauer, Leerlauf-Entladen.
Ohne echte Tastatureingaben: fuege_ein wird abgefangen, config.toml wird nicht verändert.

Aufruf (im Projektordner):
    %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_phase4 [--engine]
"""
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

import diktat.__main__ as hauptmodul
from diktat import PROJEKT
from diktat.config import CONFIG_DATEI, speichere_modus

FEHLER = []


def pruefe(name, bedingung):
    print(("OK    " if bedingung else "FEHLER"), name)
    if not bedingung:
        FEHLER.append(name)


class FakeRecorder:
    def __init__(self):
        self.laeuft = False
        self.starts = 0
        self.geraet = "Fake"

    def start(self):
        self.laeuft = True
        self.starts += 1

    def stop(self):
        self.laeuft = False
        return np.zeros(10, dtype=np.float32)

    def schliessen(self):
        self.laeuft = False


class FakeEngine:
    def __init__(self):
        self.bereit = True
        self.gestoppt = False
        self._proc = None

    def stop(self):
        self.bereit = False
        self.gestoppt = True


def neue_app(modus):
    for f in ("speichere_modell", "speichere_geraet", "speichere_mikrofon", "speichere_modus"):
        setattr(hauptmodul, f, lambda *a: None)
    app = hauptmodul.App()
    app.recorder = FakeRecorder()
    app.modus = modus
    app.cfg.min_dauer_s, app.cfg.tipp_grenze_s, app.cfg.max_aufnahme_s = 0.3, 0.4, 300
    app.engine = FakeEngine()
    app._starte_engine = lambda: setattr(app, "_geladen", True)  # kein echtes Modell laden
    return app


def jobs(app):
    n = 0
    while not app.auftraege.empty():
        app.auftraege.get()
        n += 1
    return n


def test_config_modus():
    with tempfile.TemporaryDirectory() as d:
        kopie = Path(d) / "config.toml"
        shutil.copy(CONFIG_DATEI, kopie)
        speichere_modus("umschalten", kopie)
        neu = kopie.read_text(encoding="utf-8")
        pruefe("Modus wird gespeichert", 'modus = "umschalten"' in neu)
        pruefe("Kommentar mit 'modus' bleibt unverändert", '#   "halten"     = gedrückt halten' in neu)
        try:
            speichere_modus("quatsch", kopie)
            pruefe("Ungültiger Modus wird abgelehnt", False)
        except ValueError:
            pruefe("Ungültiger Modus wird abgelehnt", True)


def test_halten():
    app = neue_app("halten")
    b = app._behandle_ereignis
    b("press", 0.0); b("release", 1.0)
    pruefe("halten: 1 s gedrückt -> 1 Diktat", jobs(app) == 1 and not app.recorder.laeuft)
    b("press", 5.0); b("release", 5.2)
    pruefe("halten: 0,2 s -> verworfen", jobs(app) == 0 and not app.recorder.laeuft and not app._dauer_aktiv)


def test_umschalten():
    app = neue_app("umschalten")
    b = app._behandle_ereignis
    b("press", 0.0); b("release", 0.1)
    pruefe("umschalten: Tippen startet Daueraufnahme", app.recorder.laeuft and app._dauer_aktiv and jobs(app) == 0)
    pruefe("umschalten: Symbol zeigt Daueraufnahme", app.tray.zustand == "aufnahme" and "tippen" in app.tray.detail)
    b("press", 8.0)
    pruefe("umschalten: zweites Tippen stoppt -> 1 Diktat", not app.recorder.laeuft and jobs(app) == 1)
    b("release", 8.1)
    pruefe("umschalten: Loslassen danach startet nichts", not app.recorder.laeuft and app.recorder.starts == 1)
    b("press", 10.0); b("release", 12.0)
    pruefe("umschalten: auch langes Drücken startet Daueraufnahme", app._dauer_aktiv and app.recorder.laeuft)


def test_beides():
    app = neue_app("beides")
    b = app._behandle_ereignis
    b("press", 0.0); b("release", 0.2)
    pruefe("beides: kurz tippen -> Daueraufnahme", app._dauer_aktiv and app.recorder.laeuft)
    b("press", 4.0); b("release", 4.1)
    pruefe("beides: nochmal tippen -> 1 Diktat (4 s)", jobs(app) == 1 and not app.recorder.laeuft)
    b("press", 10.0); b("release", 12.0)
    pruefe("beides: 2 s halten -> Push-to-Talk-Diktat", jobs(app) == 1 and not app._dauer_aktiv)
    b("press", 20.0); b("release", 20.5)
    pruefe("beides: 0,5 s (über Tipp-Grenze) -> Push-to-Talk", jobs(app) == 1 and not app._dauer_aktiv)


def test_maxdauer_cancel_pause():
    app = neue_app("umschalten")
    b = app._behandle_ereignis
    b("press", 0.0); b("release", 0.1)
    app._pruefe_max_dauer(100.0)
    pruefe("Max-Dauer: nach 100 s läuft noch", app.recorder.laeuft)
    app._pruefe_max_dauer(300.0)
    pruefe("Max-Dauer: nach 300 s automatisch beendet -> Diktat", not app.recorder.laeuft and jobs(app) == 1)

    app = neue_app("halten")
    app._behandle_ereignis("press", 0.0)
    app._behandle_ereignis("cancel", 0.5)
    pruefe("cancel: verworfen", jobs(app) == 0 and not app.recorder.laeuft)

    app = neue_app("umschalten")
    app._behandle_ereignis("press", 0.0); app._behandle_ereignis("release", 0.1)
    app.umschalten_pause()
    pruefe("Pause während Daueraufnahme: Aufnahme aus, Zustand zurückgesetzt",
           not app.recorder.laeuft and not app._dauer_aktiv and app.pausiert)


def test_leerlauf():
    app = neue_app("halten")
    app.cfg.leerlauf_minuten = 1
    alt = app.engine
    app._letzte_aktivitaet = 0.0
    pruefe("Leerlauf: nach 30 s noch geladen", app._pruefe_leerlauf(30.0) is False and alt.bereit)
    app.recorder.laeuft = True
    pruefe("Leerlauf: während Aufnahme nie entladen", app._pruefe_leerlauf(120.0) is False)
    app.recorder.laeuft = False
    pruefe("Leerlauf: nach 61 s entladen", app._pruefe_leerlauf(61.0) is True and app._entladen)
    time.sleep(0.2)
    pruefe("Leerlauf: altes Modell gestoppt", alt.gestoppt)
    pruefe("Leerlauf: Symbol 'ruht'", app.tray.zustand == "ruht")
    pruefe("Leerlauf: kein zweites Entladen", app._pruefe_leerlauf(500.0) is False)
    app._behandle_ereignis("press", 600.0)
    pruefe("Leerlauf: Tastendruck weckt auf und lädt", not app._entladen and getattr(app, "_geladen", False))
    pruefe("Leerlauf: Aufnahme läuft dabei schon (rotes Symbol)",
           app.recorder.laeuft and app.tray.zustand == "aufnahme")

    app2 = neue_app("halten")
    app2.cfg.leerlauf_minuten = 0
    app2._letzte_aktivitaet = 0.0
    pruefe("Leerlauf 0 = nie entladen", app2._pruefe_leerlauf(10_000.0) is False)


def test_leerlauf_echt():
    """Echtes Modell: entladen, dann ein Diktat -> lädt nach und transkribiert."""
    from faster_whisper.audio import decode_audio

    eingefuegt = []
    hauptmodul.fuege_ein = lambda text, modus: eingefuegt.append(text)  # nicht ins aktive Fenster tippen
    app = hauptmodul.App()
    app.modell, app.geraet_wahl = "turbo", "GPU"
    app.engine = app._neue_engine()
    app._lade(app.engine)
    app.cfg.leerlauf_minuten = 1
    app._letzte_aktivitaet = time.monotonic() - 120
    pruefe("Echt: Modell geladen", app.engine.bereit)
    alt = app.engine
    pruefe("Echt: wird nach Leerlauf entladen", app._pruefe_leerlauf(time.monotonic()))
    time.sleep(4)
    pruefe("Echt: Whisper-Prozess beendet", alt._proc is None)
    audio = decode_audio(str(PROJEKT / "whisper-test" / "test_de.wav"))[: 16000 * 8]
    t0 = time.perf_counter()
    app._verarbeite(audio)
    dauer = time.perf_counter() - t0
    print(f"      Diktat nach Leerlauf fertig nach {dauer:.1f} s (inkl. Nachladen): {eingefuegt[:1]}")
    pruefe("Echt: Diktat nach Leerlauf wird transkribiert", eingefuegt and "Kundenservice" in eingefuegt[0])
    pruefe("Echt: Modell danach wieder geladen", app.engine.bereit and not app._entladen)
    app.engine.stop()


if __name__ == "__main__":
    test_config_modus()
    test_halten()
    test_umschalten()
    test_beides()
    test_maxdauer_cancel_pause()
    test_leerlauf()
    if "--engine" in sys.argv:
        test_leerlauf_echt()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
