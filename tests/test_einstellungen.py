"""Tests für das Einstellungsfenster und seine Datenlogik, ohne echte Eingaben. UI-Rauchtests bauen das Fenster
unsichtbar (withdraw) und schließen es wieder.

Aufruf (im Projektordner):
    %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_einstellungen
"""
import sys
import tempfile
import tomllib
from pathlib import Path

from diktat import PROJEKT
from diktat.tomltext import eintraege, entferne, setze

FEHLER = []


def pruefe(name, bedingung):
    print(("OK    " if bedingung else "FEHLER"), name)
    if not bedingung:
        FEHLER.append(name)


def test_tomltext():
    T = '# Kopf\n[allgemein]\nshortcut = "ctrl+y"  # alt\nmodus = "beides"\n\n[modell]\nname = "turbo"\n'
    pruefe("ersetzt, Zeilenkommentar bleibt",
           'shortcut = "ctrl+win"  # alt' in setze(T, "allgemein", "shortcut", "ctrl+win"))
    pruefe("bool", "leerzeichen_danach = false" in setze(T, "allgemein", "leerzeichen_danach", False))
    x = setze(T, "allgemein", "x", 1)
    pruefe("ergänzt im Abschnitt, vor dem nächsten", x.index("x = 1") < x.index("[modell]")
           and tomllib.loads(x)["allgemein"]["x"] == 1)
    pruefe("Kommazahl", tomllib.loads(setze(T, "allgemein", "t", 0.4))["allgemein"]["t"] == 0.4)
    pruefe("Liste", 'enter = ["senden", "enter"]' in setze(T, "befehle", "enter", ["senden", "enter"]))
    pruefe("neuer Abschnitt gültig",
           tomllib.loads(setze(T, "befehle", "enter", ["senden"]))["befehle"]["enter"] == ["senden"])
    pruefe("Kopf bleibt", setze(T, "modell", "name", "large-v3").startswith("# Kopf"))
    pruefe("andere Werte bleiben", tomllib.loads(setze(T, "modell", "name", "large-v3"))["allgemein"]["modus"]
           == "beides")
    M = '[befehle]\nenter = [\n  "senden",\n  "enter",\n]\nx = 1\n'
    pruefe("mehrzeilige Liste ersetzt",
           tomllib.loads(setze(M, "befehle", "enter", ["senden"]))["befehle"] == {"enter": ["senden"], "x": 1})
    Q = '[tasten]\n"kopieren|copy" = "ctrl+c"\nwiederholen = "ctrl+y"\n'
    pruefe("quoted key entfernen", "kopieren" not in entferne(Q, "tasten", "kopieren|copy"))
    pruefe("entfernen lässt den Rest", tomllib.loads(entferne(Q, "tasten", "kopieren|copy"))["tasten"]
           == {"wiederholen": "ctrl+y"})
    pruefe("bare key ersetzen",
           tomllib.loads(setze(Q, "tasten", "wiederholen", "ctrl+shift+z"))["tasten"]["wiederholen"] == "ctrl+shift+z")
    pruefe("eintraege", [s for s, _ in eintraege(Q, "tasten")] == ["kopieren|copy", "wiederholen"])
    pruefe("Sonderzeichen im Schlüssel", tomllib.loads(setze("", "oeffnen", 'a "b"', "x"))["oeffnen"]['a "b"'] == "x")
    pruefe("Backslash im Wert", tomllib.loads(setze("", "oeffnen", "c", "shell:AppsFolder\\C!C"))["oeffnen"]["c"]
           == "shell:AppsFolder\\C!C")
    K = '[allgemein] # Kommentar am Kopf\n# erklärung\nmodus = "beides"\n'
    pruefe("Kopf mit Kommentar", tomllib.loads(setze(K, "allgemein", "modus", "halten"))["allgemein"]["modus"]
           == "halten" and "# erklärung" in setze(K, "allgemein", "modus", "halten"))
    pruefe("entfernen unbekannt: unverändert", entferne(Q, "tasten", "gibtsnicht") == Q)
    pruefe("Unterabschnitt nicht verwechselt",
           tomllib.loads(setze('[modelle.turbo]\nname = "x"\n[modell]\nname = "turbo"\n', "modell", "name", "y"))
           ["modelle"]["turbo"]["name"] == "x")


if __name__ == "__main__":
    test_tomltext()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
