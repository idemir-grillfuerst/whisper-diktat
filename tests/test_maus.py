"""Tests für Push-to-Talk per Maustaste (Mausrad halten). Keine echten Maus- oder Tastatureingaben.

Aufruf (im Projektordner):  %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_maus
"""
import queue
import sys

import diktat.__main__ as hauptmodul
from diktat import maus
from diktat.maus import (WM_MBUTTONDOWN, WM_MBUTTONUP, WM_XBUTTONDOWN, WM_XBUTTONUP, MausTaste,
                         parse_maustaste)

FEHLER = []


def pruefe(name, bedingung):
    print(("OK    " if bedingung else "FEHLER"), name)
    if not bedingung:
        FEHLER.append(name)


class Uhr:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def neue_maus(taste="mitte"):
    events, nachgereicht, uhr = [], [], Uhr()
    m = MausTaste(taste, events.append, halten_s=0.4, max_s=300)
    m._jetzt = uhr
    m._nachreichen = nachgereicht.append
    return m, events, nachgereicht, uhr


def warte_threads():
    import threading
    import time
    for _ in range(50):
        if not any(t.name == "maus-klick" for t in threading.enumerate()):
            return
        time.sleep(0.01)


def test_parse():
    pruefe("leer = aus", parse_maustaste("") is None and parse_maustaste("aus") is None)
    pruefe("Aliase mitte/mausrad/maus3", {parse_maustaste(x) for x in ("mitte", "Mausrad", "maus3")} == {"mitte"})
    pruefe("maus4/maus5 = x1/x2", parse_maustaste("maus4") == "x1" and parse_maustaste("maus5") == "x2")
    try:
        parse_maustaste("links")
        pruefe("unbekannte Taste wird abgelehnt", False)
    except ValueError:
        pruefe("unbekannte Taste wird abgelehnt", True)


def test_logik():
    m, events, nachgereicht, uhr = neue_maus()
    pruefe("Drücken wird geschluckt, Aufnahme startet sofort", m._verarbeite("unten") is True and events == ["maus_press"])
    uhr.t += 0.15
    pruefe("Kurzer Klick: geschluckt", m._verarbeite("oben") is True)
    warte_threads()
    pruefe("Kurzer Klick: cancel + Klick nachgereicht", events == ["maus_press", "maus_cancel"] and nachgereicht == ["mitte"])

    m, events, nachgereicht, uhr = neue_maus()
    m._verarbeite("unten"); uhr.t += 2.5; m._verarbeite("oben")
    warte_threads()
    pruefe("Gehalten: release, kein Klick nachgereicht", events == ["maus_press", "maus_release"] and nachgereicht == [])

    m, events, _, _ = neue_maus()
    pruefe("Loslassen ohne eigenes Drücken geht durch", m._verarbeite("oben") is False and events == [])

    m, events, _, _ = neue_maus()
    pruefe("Mittlere Taste erkannt", m._passt(WM_MBUTTONDOWN, 0) == "unten" and m._passt(WM_MBUTTONUP, 0) == "oben")
    pruefe("Andere Mausereignisse ignoriert", m._passt(0x0201, 0) is None and m._passt(0x0200, 0) is None)
    m, _, _, _ = neue_maus("x1")
    pruefe("x1: nur Seitentaste 1", m._passt(WM_XBUTTONDOWN, 1 << 16) == "unten" and m._passt(WM_XBUTTONUP, 2 << 16) is None)
    pruefe("x1: Mittelklick ignoriert", m._passt(WM_MBUTTONDOWN, 0) is None)


def test_wachhund():
    m, events, _, uhr = neue_maus()
    m._verarbeite("unten")
    for _ in range(20):  # Zustand meldet nie „gedrückt“ (verschluckte Taste): nichts tun
        uhr.t += 0.2
        m._wachhund_schritt(False, uhr.t)
    pruefe("Ohne gesehenen Tastenzustand löst der Wachhund nicht aus", m.aktiv and events == ["maus_press"])
    m._wachhund_schritt(True, uhr.t)
    m._wachhund_schritt(False, uhr.t)
    pruefe("Gesehen gedrückt, dann los: verlorenes Loslassen -> release", not m.aktiv and events[-1] == "maus_release")

    m, events, _, uhr = neue_maus()
    m._verarbeite("unten"); uhr.t += 301
    m._wachhund_schritt(False, uhr.t)
    pruefe("Höchstdauer überschritten -> release", events == ["maus_press", "maus_release"])


def test_app():
    """Bedienlogik der App mit Maus-Ereignissen (ohne Hook, ohne Whisper)."""
    class Rec:
        laeuft = False
        def start(self): self.laeuft = True
        def stop(self):
            self.laeuft = False
            return [0.0] * 16000

    class Tray:
        zustand = "bereit"
        def setze(self, z, d=None): self.zustand = z

    app = hauptmodul.App.__new__(hauptmodul.App)
    app.recorder, app.tray, app.auftraege, app.ausgaben = Rec(), Tray(), queue.Queue(), queue.Queue()
    app.vorwaermung = queue.Queue(maxsize=1)
    app.modus, app.pausiert, app._entladen = "beides", False, False
    app._maus_aufnahme = app._dauer_aktiv = app._release_ignorieren = False
    app._druck_zeit = app._start_zeit = 0.0
    app._aufwecken = lambda: None
    app._zurueck_zu_bereit = lambda detail=None: app.tray.setze("bereit")

    class Cfg:
        min_dauer_s, tipp_grenze_s, shortcut = 0.3, 0.4, "ctrl+win"
    app.cfg = Cfg()

    app._behandle_ereignis("maus_press", 10.0)
    pruefe("App: Maus drücken startet Aufnahme", app.recorder.laeuft and app.tray.zustand == "aufnahme")
    pruefe("App: Aufnahmestart wärmt vor, in eigener Warteschlange (nicht vor den Ausgaben)",
           app.vorwaermung.qsize() == 1 and app.ausgaben.empty())
    app.vorwaermung.get_nowait()
    app._behandle_ereignis("maus_cancel", 10.2)
    pruefe("App: kurzer Klick verwirft, kein Auftrag", not app.recorder.laeuft and app.auftraege.empty())

    app._behandle_ereignis("maus_press", 20.0)
    app._behandle_ereignis("maus_release", 23.0)
    pruefe("App: gehalten -> Auftrag an Whisper, auch im Modus 'beides'",
           app.auftraege.qsize() == 1 and not app._dauer_aktiv)

    app._behandle_ereignis("press", 30.0)  # Tastatur-Aufnahme läuft
    app._behandle_ereignis("maus_press", 30.5)
    pruefe("App: Maus während Tastatur-Aufnahme wird ignoriert", not app._maus_aufnahme)


if __name__ == "__main__":
    test_parse()
    test_logik()
    test_wachhund()
    test_app()
    print("\nALLES OK" if not FEHLER else f"\n{len(FEHLER)} FEHLER: {FEHLER}")
    sys.exit(1 if FEHLER else 0)
