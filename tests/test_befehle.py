"""Tests für Sprachbefehle (Enter am Ende, feste Befehle), ohne echte Tastatureingaben.

Aufruf (im Projektordner):
    %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_befehle
"""
import sys

from diktat.befehle import Aktion, Befehle, Ergebnis, normalisiere, parse_befehle, zerlege

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


if __name__ == "__main__":
    test_normalisiere()
    test_parse()
    test_zerlege()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
