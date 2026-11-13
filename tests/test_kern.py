"""Tests für Phase 1, ohne echte Tastatureingaben.

Aufruf (im Projektordner):
    %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_kern [--engine]
--engine lädt zusätzlich Whisper auf der GPU und transkribiert whisper-test/test_de.wav.
"""
import ctypes
import sys

from diktat import PROJEKT, hotkey
from diktat.__main__ import bereinige
from diktat.config import fachwort_prompt, lade_config
from diktat.hotkey import PushToTalk, parse_shortcut, WM_KEYDOWN

FEHLER = []


def pruefe(name, bedingung):
    print(("OK    " if bedingung else "FEHLER"), name)
    if not bedingung:
        FEHLER.append(name)


def test_shortcut_parsen():
    pruefe("ctrl+y", parse_shortcut("ctrl+y") == (frozenset({"ctrl"}), 0x59))
    pruefe("Strg + Y (deutsch, Leerzeichen)", parse_shortcut("Strg + Y") == (frozenset({"ctrl"}), 0x59))
    pruefe("ctrl+shift ohne Taste", parse_shortcut("ctrl+shift") == (frozenset({"ctrl", "shift"}), None))
    pruefe("ctrl+alt+space", parse_shortcut("ctrl+alt+space") == (frozenset({"ctrl", "alt"}), 0x20))
    pruefe("f9", parse_shortcut("f9") == (frozenset(), 0x78))
    for falsch in ("ctrl", "ctrl+y+x", "ctrl+blub"):
        try:
            parse_shortcut(falsch)
            pruefe(f"'{falsch}' wird abgelehnt", False)
        except ValueError:
            pruefe(f"'{falsch}' wird abgelehnt", True)


class Simulator:
    """Simuliert Tastendrücke gegen PushToTalk._verarbeite, mit vorgetäuschtem Modifier-Zustand."""

    def __init__(self, shortcut):
        self.gedrueckt = set()
        self.events = []
        self.ptt = PushToTalk(shortcut, self.events.append)
        hotkey.gedrueckte_modifier = self._mods

    def _mods(self, ausser_vk=None):
        return {hotkey.VK_ZU_GRUPPE[v] for v in self.gedrueckt
                if v in hotkey.VK_ZU_GRUPPE and v != ausser_vk}

    def runter(self, vk):
        r = self.ptt._verarbeite(vk, True)
        self.gedrueckt.add(vk)
        return r

    def hoch(self, vk):
        self.gedrueckt.discard(vk)
        return self.ptt._verarbeite(vk, False)


def test_push_to_talk():
    LCTRL, Y, LSHIFT, T = 0xA2, 0x59, 0xA0, 0x54
    original = hotkey.gedrueckte_modifier
    original_gedrueckt = hotkey._gedrueckt
    try:
        s = Simulator("ctrl+y")
        pruefe("Strg runter wird durchgelassen", s.runter(LCTRL) is False)
        pruefe("Y bei gedrücktem Strg wird geschluckt", s.runter(Y) is True)
        pruefe("Tastenwiederholung wird geschluckt", s.runter(Y) is True)
        pruefe("Y loslassen wird geschluckt", s.hoch(Y) is True)
        s.hoch(LCTRL)
        pruefe("Ereignisse press, release", s.events == ["press", "release"])

        s = Simulator("ctrl+y")
        hotkey._gedrueckt = lambda vk: vk in s.gedrueckt
        s.runter(LCTRL); s.runter(Y); s.hoch(LCTRL)
        pruefe("Strg zuerst losgelassen beendet Aufnahme", s.events == ["press", "release"])
        wdh = [s.runter(Y) for _ in range(6)]  # Tastenwiederholung von Y ohne Strg (vorher: „yyyyyy“)
        pruefe("Danach weiterlaufende Y-Wiederholungen werden geschluckt", all(wdh))
        pruefe("Wachhund schweigt während des Nachlaufs",
               s.ptt._wachhund_schritt(True, 0.0, 5.0) is None and s.events == ["press", "release"])
        pruefe("Y loslassen wird geschluckt und beendet den Nachlauf", s.hoch(Y) is True)
        pruefe("Danach ist Y wieder normal", s.runter(Y) is False)
        s.hoch(Y)
        s.runter(LCTRL)
        pruefe("Danach löst Strg+Y wieder normal aus", s.runter(Y) is True and s.events[-1] == "press")

        s = Simulator("ctrl+y")
        hotkey._gedrueckt = lambda vk: vk in s.gedrueckt
        s.runter(LCTRL); s.runter(Y); s.hoch(LCTRL)
        s.gedrueckt.discard(Y)  # Y physisch los, aber der Hook hat das Loslassen nie gesehen
        s.ptt._wachhund_schritt(False, None, 9.0)
        pruefe("Verlorenes Y-Loslassen: Wachhund gibt Y wieder frei", s.runter(Y) is False)

        s = Simulator("ctrl+y")
        s.runter(LCTRL); s.runter(LSHIFT)
        pruefe("Strg+Umschalt+Y löst nicht aus", s.runter(Y) is False and s.events == [])

        s = Simulator("ctrl+y")
        pruefe("Y ohne Strg geht normal durch", s.runter(Y) is False and s.events == [])

        s = Simulator("ctrl+shift")
        s.runter(LCTRL); s.runter(LSHIFT); s.hoch(LSHIFT); s.hoch(LCTRL)
        pruefe("ctrl+shift: press, release", s.events == ["press", "release"])

        s = Simulator("ctrl+shift")
        s.runter(LCTRL); s.runter(LSHIFT); s.runter(T)
        pruefe("ctrl+shift+T bricht ab (cancel)", s.events == ["press", "cancel"])

        s = Simulator("ctrl+y")
        s.ptt.eingeschaltet = False
        s.gedrueckt.add(LCTRL)
        # Pausiert: Der Callback darf die Struktur gar nicht erst lesen (l_param=0 wäre sonst ein Absturz)
        # und reicht an CallNextHookEx weiter, schluckt also nichts (Rückgabe != 1).
        pruefe("pausiert: Hook-Callback schluckt nichts",
               s.ptt._hook_proc(0, WM_KEYDOWN, 0) != 1 and s.events == [])
    finally:
        hotkey.gedrueckte_modifier = original
        hotkey._gedrueckt = original_gedrueckt


def test_wachhund():
    """Toter Hook: Shortcut ist physisch gedrückt, aber der Hook meldet nichts."""
    events = []
    ptt = PushToTalk("ctrl+y", events.append)
    erneuert = []
    ptt.erneuern = lambda: erneuert.append(1)
    seit = ptt._wachhund_schritt(True, None, 10.0)
    pruefe("Wachhund: wartet kurz (0,25 s)", events == [] and seit == 10.0)
    seit = ptt._wachhund_schritt(True, seit, 10.1)
    pruefe("Wachhund: nach 0,1 s noch nichts", events == [])
    seit = ptt._wachhund_schritt(True, seit, 10.3)
    pruefe("Wachhund: nach 0,3 s press + Hook neu gesetzt",
           events == ["press"] and erneuert == [1] and ptt.aktiv and ptt.hook_ausfaelle == 1)
    ptt._wachhund_schritt(True, seit, 10.5)
    pruefe("Wachhund: solange gedrückt kein zweites press", events == ["press"])
    ptt._wachhund_schritt(False, None, 11.0)
    pruefe("Wachhund: Loslassen erkannt -> release", events == ["press", "release"] and not ptt.aktiv)

    events.clear()
    ptt2 = PushToTalk("ctrl+y", events.append)
    ptt2.erneuern = lambda: None
    ptt2.aktiv = True  # Hook funktioniert und hat press gemeldet
    ptt2._wachhund_schritt(True, None, 1.0)
    ptt2._wachhund_schritt(False, None, 2.0)
    pruefe("Wachhund: funktionierender Hook bleibt unangetastet", events == [] and ptt2.aktiv)

    ptt3 = PushToTalk("ctrl+y", events.append)
    ptt3.eingeschaltet = False
    pruefe("Wachhund: pausiert -> nichts", ptt3._wachhund_schritt(True, 1.0, 5.0) is None and events == [])


def test_bereinigen():
    pruefe("ZDF-Abspann wird entfernt",
           bereinige("Bitte die Maximal-Request je Aufruf. Untertitelung des ZDF, 2020") ==
           "Bitte die Maximal-Request je Aufruf.")
    pruefe("Nur 'Vielen Dank.' wird verworfen", bereinige("Vielen Dank.") == "")
    pruefe("Normaler Satz mit 'vielen Dank' bleibt",
           bereinige("Ich sage vielen Dank für die Hilfe.") == "Ich sage vielen Dank für die Hilfe.")
    schleife = "Bitte prüfe das. " + "Das ist ein Test. " * 30
    pruefe("Satz-Schleife wird auf einmal gekürzt",
           bereinige(schleife) == "Bitte prüfe das. Das ist ein Test.")
    ergebnis = bereinige("Ja ja ja ja ja ja ja ja genau.")
    pruefe(f"Wort-Schleife wird gekürzt ('{ergebnis}')", ergebnis in ("Ja genau.", "Ja ja genau."))
    pruefe("Einzelwort 6x wird gekürzt", bereinige("okay okay okay okay okay okay") == "okay")
    normal = "Das ist gut, das ist gut so. Wir machen das morgen."
    pruefe("Normale Wiederholung (2x) bleibt", bereinige(normal) == normal)
    aufzaehlung = "Erstens lesen, zweitens schreiben, drittens testen."
    pruefe("Aufzählung bleibt", bereinige(aufzaehlung) == aufzaehlung)

    from diktat.__main__ import max_tokens_fuer, zu_lang
    pruefe("4 s Diktat: 881 Zeichen sind unplausibel", zu_lang("x" * 881, 4.0))
    pruefe("4 s Diktat: 80 Zeichen sind normal", not zu_lang("x" * 80, 4.0))
    pruefe("53 s Diktat: 840 Zeichen sind normal (echter Test vom 12.11.)", not zu_lang("x" * 840, 53.5))
    pruefe("Token-Grenze 4 s = 78, 60 s = keine", max_tokens_fuer(4.0) == 78 and max_tokens_fuer(60) is None)


def test_config():
    cfg = lade_config()
    pruefe("config.toml lädt", cfg.shortcut == "ctrl+y" and cfg.modell in cfg.modelle)
    pruefe("2 Modelle definiert", set(cfg.modelle) == {"turbo", "large-v3"})
    p = fachwort_prompt()
    pruefe("Fachwort-Prompt enthält Claude", p is not None and "Claude" in p and "#" not in p)


def test_inserter_strukturen():
    from diktat.inserter import INPUT
    pruefe("INPUT-Struktur hat Windows-Größe (40 Byte bei 64 Bit)",
           ctypes.sizeof(INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28))


def test_engine():
    import time
    from faster_whisper.audio import decode_audio
    from diktat.engine import Engine

    cfg = lade_config()
    e = Engine(cfg.modelle["turbo"].repo, "GPU", cfg.sprache)
    t0 = time.perf_counter()
    e.start()
    print(f"      Modell geladen in {time.perf_counter() - t0:.1f} s")
    audio = decode_audio(str(PROJEKT / "whisper-test" / "test_de.wav"))
    text, sek = e.transkribiere(audio, fachwort_prompt())
    print(f"      {len(audio) / 16000:.1f} s Audio in {sek:.2f} s: {text[:90]} …")
    pruefe("Engine erkennt 'Kundenservice'", "Kundenservice" in text)
    pruefe("Engine schneller als 5 s", sek < 5)
    e.stop()
    pruefe("Engine-Prozess beendet", e._proc is None)


if __name__ == "__main__":
    test_shortcut_parsen()
    test_push_to_talk()
    test_wachhund()
    test_bereinigen()
    test_config()
    test_inserter_strukturen()
    if "--engine" in sys.argv:
        test_engine()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
