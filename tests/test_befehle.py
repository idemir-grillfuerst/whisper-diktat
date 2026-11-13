"""Tests für Sprachbefehle (Enter am Ende, feste Befehle), ohne echte Tastatureingaben.

Aufruf (im Projektordner):
    %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_befehle
"""
import os
import sys
import tempfile
import time
from pathlib import Path

from diktat import PROJEKT
from diktat.befehle import Aktion, Befehle, Ergebnis, lade_befehle, normalisiere, parse_befehle, zerlege
from diktat.config import lade_config

FEHLER = []


def pruefe(name, bedingung):
    print(("OK    " if bedingung else "FEHLER"), name)
    if not bedingung:
        FEHLER.append(name)


BEISPIEL = '''
[oeffnen]
"outlook|mails" = "https://outlook.office.com/mail/"
"rechner" = "calc.exe"
[tasten]
"rückgängig|mach das rückgängig" = "ctrl+z"
"neuer absatz" = "shift+enter shift+enter"
'''


def test_normalisiere():
    pruefe("Satzzeichen/Groß", normalisiere("  Öffne   Outlook! ") == "öffne outlook")
    pruefe("Anführungszeichen", normalisiere("„Enter.“") == "enter")
    pruefe("Bindestrich im Wort bleibt", normalisiere("E-Mails") == "e-mails")


def test_parse():
    b = parse_befehle(BEISPIEL)
    pruefe("Öffnen-Formen erzeugt", b.saetze.get("outlook öffnen") == Aktion("oeffne", "https://outlook.office.com/mail/"))
    pruefe("Alias", b.saetze.get("zeig mir mails", Aktion("", "")).ziel == "https://outlook.office.com/mail/")
    pruefe("alle 10 Formen", sum(1 for s in b.saetze if "rechner" in s) == 10)
    pruefe("Taste", b.saetze.get("mach das rückgängig") == Aktion("taste", "ctrl+z"))
    pruefe("Tastenfolge", b.saetze.get("neuer absatz") == Aktion("taste", "shift+enter shift+enter"))
    for kaputt in ('[tasten]\n"x" = "ctrl+blub"', '[oeffnen\n', '[tasten]\n"x" = 5', '[tasten]\n"x" = "ctrl"'):
        try:
            parse_befehle(kaputt)
            pruefe(f"abgelehnt: {kaputt!r}", False)
        except ValueError:
            pruefe(f"abgelehnt: {kaputt!r}", True)


def test_zerlege():
    b, E = parse_befehle(BEISPIEL), ["enter"]
    ENTER = Aktion("taste", "enter")
    pruefe("Text + Enter", zerlege("Schick das ab, Enter.", b, E) == Ergebnis("Schick das ab", [ENTER]))
    pruefe("Punkt bleibt", zerlege("Bitte prüfen. Enter!", b, E) == Ergebnis("Bitte prüfen.", [ENTER]))
    pruefe("nur Enter", zerlege("Enter.", b, E) == Ergebnis("", [ENTER]))
    pruefe("Enter mitten im Satz", zerlege("Enter ist eine Taste", b, E) == Ergebnis("Enter ist eine Taste", []))
    pruefe("Enter aus", zerlege("Hallo Enter", b, []) == Ergebnis("Hallo Enter", []))
    pruefe("Öffnen", zerlege("Öffne Outlook!", b, E) == Ergebnis("", [Aktion("oeffne", "https://outlook.office.com/mail/")]))
    pruefe("Taste", zerlege("Rückgängig.", b, E) == Ergebnis("", [Aktion("taste", "ctrl+z")]))
    pruefe("im Satz = Text", zerlege("Bitte mach das rückgängig", b, E).aktionen == [])
    pruefe("unbekannt = Text", zerlege("Öffne das Fenster", b, E) == Ergebnis("Öffne das Fenster", []))
    pruefe("leere Befehle", zerlege("Öffne Outlook", Befehle({}), E) == Ergebnis("Öffne Outlook", []))
    pruefe("Enter-Variante aus Liste", zerlege("Hallo, Enta.", b, ["enter", "enta"]) == Ergebnis("Hallo", [ENTER]))
    pruefe("Wort, das nur mit enter endet", zerlege("Das ist ein Center", b, E).aktionen == [])


def test_laden(tmp):
    d = tmp / "befehle.toml"
    d.write_text('[tasten]\n"rückgängig" = "ctrl+z"\n', encoding="utf-8")
    pruefe("geladen", "rückgängig" in lade_befehle(d).saetze)
    d.write_text('[tasten\n', encoding="utf-8")
    os.utime(d, (time.time() + 5,) * 2)
    b = lade_befehle(d)
    pruefe("kaputt: leer + Fehler", b.saetze == {} and "befehle.toml" in (b.fehler or ""))
    d.write_text('[tasten]\n"kopieren" = "ctrl+c"\n', encoding="utf-8")
    os.utime(d, (time.time() + 10,) * 2)
    pruefe("repariert: neu geladen", "kopieren" in lade_befehle(d).saetze)
    pruefe("fehlende Datei: leer, kein Absturz", lade_befehle(tmp / "gibtsnicht.toml").saetze == {})


def test_vorlage():
    b = parse_befehle((PROJEKT / "befehle.beispiel.toml").read_text(encoding="utf-8"))
    pruefe("Vorlage gültig", b.fehler is None)
    pruefe("Outlook im Browser", b.saetze["öffne outlook"].ziel.startswith("https://outlook."))
    pruefe("rückgängig", b.saetze["rückgängig"] == Aktion("taste", "ctrl+z"))
    pruefe("Emoji-Taste win+.", b.saetze["emoji"] == Aktion("taste", "win+."))


def test_config_enter(tmp):
    c = tmp / "config.toml"
    c.write_text((PROJEKT / "config.beispiel.toml").read_text(encoding="utf-8"), encoding="utf-8")
    pruefe("enter Standard", lade_config(c).enter_woerter == ["enter"])
    c.write_text('[modell]\nname = "turbo"\n', encoding="utf-8")
    pruefe("alte Datei ohne [befehle]", lade_config(c).enter_woerter == ["enter"])
    c.write_text('[befehle]\nenter = []\n', encoding="utf-8")
    pruefe("enter aus", lade_config(c).enter_woerter == [])


def test_druecke():
    from diktat import inserter
    alt = inserter._send, inserter.warte_bis_tasten_los
    gesendet, gewartet = [], []
    inserter._send = lambda inputs: gesendet.append([(i.u.ki.wVk, i.u.ki.dwFlags) for i in inputs])
    inserter.warte_bis_tasten_los = lambda *a: gewartet.append(1)
    try:
        inserter.druecke("ctrl+z")
        pruefe("Strg+Z", gesendet[-1] == [(0x11, 0), (0x5A, 0), (0x5A, 2), (0x11, 2)])
        inserter.druecke("shift+enter shift+enter")
        pruefe("Folge = 2 Sendungen", len(gesendet) == 3)
        inserter.druecke("left")
        pruefe("Pfeil erweitert", gesendet[-1][0] == (0x25, 1))
        inserter.druecke("win+shift+s")
        pruefe("Modifier in umgekehrter Reihenfolge hoch",
               [v for v, f in gesendet[-1]] == [0x5B, 0x10, 0x53, 0x53, 0x10, 0x5B]
               or [v for v, f in gesendet[-1]] == [0x10, 0x5B, 0x53, 0x53, 0x5B, 0x10])
        pruefe("wartet auf losgelassene Tasten", len(gewartet) == 4)
    finally:
        inserter._send, inserter.warte_bis_tasten_los = alt


def test_gib_aus():
    import diktat.__main__ as m
    alt = m.fuege_ein, m.druecke, m.os.startfile
    log_ = []
    m.fuege_ein = lambda t, modus: log_.append(("text", t))
    m.druecke = lambda k: log_.append(("taste", k))
    m.os.startfile = lambda z: log_.append(("oeffne", z))
    try:
        m.gib_aus(Ergebnis("Hallo", [Aktion("taste", "enter")]), "tippen", True)
        pruefe("kein Leerzeichen vor Enter", log_ == [("text", "Hallo"), ("taste", "enter")])
        log_.clear()
        m.gib_aus(Ergebnis("Hallo", []), "tippen", True)
        pruefe("Leerzeichen ohne Aktion", log_ == [("text", "Hallo ")])
        log_.clear()
        m.gib_aus(Ergebnis("Hallo", []), "tippen", False)
        pruefe("ohne leerzeichen_danach", log_ == [("text", "Hallo")])
        log_.clear()
        m.gib_aus(Ergebnis("", [Aktion("oeffne", "https://x/")]), "tippen", True)
        pruefe("nur öffnen, kein Text", log_ == [("oeffne", "https://x/")])

        def kaputt(z):
            raise OSError("nicht gefunden")
        m.os.startfile = kaputt
        try:
            m.gib_aus(Ergebnis("", [Aktion("oeffne", "gibtsnicht.exe"), Aktion("taste", "esc")]), "tippen", True)
            pruefe("Fehler beim Öffnen: weiter mit nächster Aktion", log_[-1] == ("taste", "esc"))
        except OSError:
            pruefe("Fehler beim Öffnen: weiter mit nächster Aktion", False)
    finally:
        m.fuege_ein, m.druecke, m.os.startfile = alt


if __name__ == "__main__":
    test_normalisiere()
    test_parse()
    test_zerlege()
    with tempfile.TemporaryDirectory() as t:
        test_laden(Path(t))
        test_config_enter(Path(t))
    test_vorlage()
    test_druecke()
    test_gib_aus()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
