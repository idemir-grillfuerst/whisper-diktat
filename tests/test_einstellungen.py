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
    um = setze(Q, "tasten", "kopieren|copy", "ctrl+c", neuer_schluessel="kopieren|kopie")
    pruefe("umbenennen an Ort und Stelle", [s for s, _ in eintraege(um, "tasten")] == ["kopieren|kopie", "wiederholen"])
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


def test_daten():
    from diktat.befehle import Aktion, parse_befehle
    from diktat.einstellungen.daten import (FELDER, Befehl, doppelte_saetze, fachwort_laenge, lies_befehle,
                                            lies_werte, pruefe_wert, regel_loeschen, regeln_liste, schreibe_werte,
                                            setze_befehl, tasten_lesbar, wirkung_lesbar)
    C = (PROJEKT / "config.beispiel.toml").read_text(encoding="utf-8")
    w = lies_werte(C)
    pruefe("Standardwerte", w["modus"] == "beides" and w["enter"] == ["enter", "senden"] and w["modell"] == "turbo"
           and w["geraet"] == "auto" and w["sprache"] == "de" and w["leerzeichen_danach"] is True)
    pruefe("alle Felder gelesen", set(w) == set(FELDER))
    pruefe("Neustart-Felder", {n for n, f in FELDER.items() if f.neustart}
           == {"shortcut", "maustaste", "mikrofon_offen_halten"})
    pruefe("jedes Feld erklärt", all(f.titel and f.erklaerung for f in FELDER.values()))
    pruefe("Shortcut falsch", pruefe_wert("shortcut", "ctrl") is not None and pruefe_wert("shortcut", "ctrl+win") is None)
    pruefe("Zahl falsch", pruefe_wert("max_aufnahme_s", "abc") is not None and pruefe_wert("tipp_grenze_s", 5) is not None
           and pruefe_wert("tipp_grenze_s", 0.4) is None and pruefe_wert("leerlauf_minuten", -1) is not None)
    pruefe("Wahl falsch", pruefe_wert("modus", "irgendwas") is not None and pruefe_wert("modus", "halten") is None)
    pruefe("Absenden-Wörter", pruefe_wert("enter", ["senden"]) is None and pruefe_wert("enter", [""]) is not None
           and pruefe_wert("enter", []) is None)
    neu = schreibe_werte(C, {"shortcut": "ctrl+win", "leerzeichen_danach": False})
    pruefe("nur geänderte Werte", lies_werte(neu)["shortcut"] == "ctrl+win" and lies_werte(neu)["modus"] == "beides"
           and lies_werte(neu)["leerzeichen_danach"] is False)
    pruefe("Kommentare bleiben", [z for z in C.splitlines() if z.startswith("#")]
           == [z for z in neu.splitlines() if z.startswith("#")])
    for kaputt in ({"modus": "kaputt"}, {"shortcut": "ctrl"}, {"modell": "gibtsnicht"}):
        try:
            schreibe_werte(C, kaputt)
            pruefe(f"ungültig nicht geschrieben {kaputt}", False)
        except ValueError:
            pruefe(f"ungültig nicht geschrieben {kaputt}", True)
    menue = setze(C, "allgemein", "mikrofon", "Headset")
    pruefe("Menü-Änderung bleibt", lies_werte(schreibe_werte(menue, {"modus": "halten"}))["mikrofon"] == "Headset")
    pruefe("Modell und Senden-Wörter schreiben",
           lies_werte(schreibe_werte(C, {"modell": "large-v3", "enter": ["senden"]}))["enter"] == ["senden"])

    B = (PROJEKT / "befehle.beispiel.toml").read_text(encoding="utf-8")
    bs = lies_befehle(B)
    kop = next(b for b in bs if "kopieren" in b.saetze)
    pruefe("Befehl gelesen", kop.art == "tasten" and kop.ziel == "ctrl+c" and "copy" in kop.saetze and kop.schluessel)
    pruefe("Aktionen gelesen", any(b.art == "aktionen" and b.ziel == "textfeld" for b in bs))
    neu = setze_befehl(B, kop, Befehl("tasten", ["kopieren", "kopie"], "ctrl+c", kop.schluessel))
    pruefe("geändert", parse_befehle(neu).saetze["kopie"] == Aktion("taste", "ctrl+c")
           and "copy" not in parse_befehle(neu).saetze)
    pruefe("Kommentare der Befehle bleiben", [z for z in B.splitlines() if z.startswith("#")]
           == [z for z in neu.splitlines() if z.startswith("#")])
    pruefe("neu", parse_befehle(setze_befehl(B, None, Befehl("oeffnen", ["portal"], "https://x.de")))
           .saetze["öffne portal"].ziel == "https://x.de")
    pruefe("gelöscht", "kopieren" not in parse_befehle(setze_befehl(B, kop, None)).saetze)
    for kaputt in (Befehl("tasten", ["x"], "ctrl+blub"), Befehl("tasten", [""], "ctrl+c"), Befehl("oeffnen", ["x"], ""),
                   Befehl("aktionen", ["x"], "gibtsnicht")):
        try:
            setze_befehl(B, None, kaputt)
            pruefe(f"abgelehnt {kaputt}", False)
        except ValueError:
            pruefe(f"abgelehnt {kaputt}", True)
    pruefe("doppelt", doppelte_saetze(bs, Befehl("tasten", ["Kopieren!"], "ctrl+x")) == ["kopieren"])
    pruefe("nicht doppelt mit sich selbst", doppelte_saetze(bs, kop) == [])
    pruefe("lesbar", tasten_lesbar("ctrl+shift+t") == "Strg+Umschalt+T"
           and tasten_lesbar("shift+enter shift+enter") == "Umschalt+Enter, dann Umschalt+Enter"
           and tasten_lesbar("win+.") == "Win+." and tasten_lesbar("alt+left") == "Alt+←")
    pruefe("Wirkung lesbar", wirkung_lesbar(kop) == "Strg+C"
           and wirkung_lesbar(Befehl("aktionen", ["x"], "textfeld")) == "Ins Textfeld springen")
    R = '# Kopf\n[regeln."ms-teams"]\ntaste = "alt+shift+c"\n[regeln."chrome|claude.ai"]\nname = "Prompt"\n'
    pruefe("Regeln", regeln_liste(R) == [("ms-teams", "Taste Alt+Umschalt+C"), ("chrome|claude.ai", "Feld „Prompt“")])
    pruefe("Regel löschen", [s for s, _ in regeln_liste(regel_loeschen(R, "ms-teams"))] == ["chrome|claude.ai"]
           and regel_loeschen(R, "ms-teams").startswith("# Kopf"))
    pruefe("Fachwortlänge", fachwort_laenge("# Kommentar\nGrillfürst\nPlenty\n") == len("Fachbegriffe: Grillfürst, Plenty.")
           and fachwort_laenge("") == 0)


def test_tool_seite(tmp):
    """Das Diktier-Tool übernimmt geänderte config.toml live (ohne echtes Whisper, Mikrofon oder Fenster)."""
    import os
    import time
    import diktat.__main__ as hm
    from diktat.config import lade_config_text
    C = (PROJEKT / "config.beispiel.toml").read_text(encoding="utf-8")
    aufrufe, meldungen = [], []

    class Rec:
        mikrofon = ""

        def waehle(self, name):
            aufrufe.append(("mikrofon", name))
            self.mikrofon = name

    class Tray:
        zustand = "bereit"

        def melde(self, text):
            meldungen.append(text)

        def setze(self, *a, **k):
            pass

    app = hm.App.__new__(hm.App)
    app.cfg = lade_config_text(C)
    app.modell, app.geraet_wahl, app.modus = app.cfg.modell, app.cfg.geraet, app.cfg.modus
    app.recorder, app.tray = Rec(), Tray()
    def wechsle(modell=None, geraet_wahl=None):  # wie das echte _wechsle: Zustand der App nachziehen
        aufrufe.append(("wechsle", modell, geraet_wahl))
        app.modell, app.geraet_wahl = modell or app.modell, geraet_wahl or app.geraet_wahl
    app._wechsle = wechsle
    app._engine_neu_starten = lambda grund, warten=False: aufrufe.append(("engine", grund))

    neu = setze(setze(setze(C, "allgemein", "modus", "halten"), "modell", "name", "large-v3"), "allgemein",
                "shortcut", "ctrl+win")
    geaendert = app._config_anwenden(lade_config_text(neu))
    pruefe("Tool: Bedienung live", app.modus == "halten" and app.cfg.modus == "halten")
    pruefe("Tool: Modellwechsel", ("wechsle", "large-v3", None) in aufrufe)
    pruefe("Tool: Shortcut nur gemeldet", "shortcut" in geaendert and app.cfg.shortcut == "ctrl+win")
    aufrufe.clear()
    neu = setze(neu, "allgemein", "mikrofon", "Headset")
    app._config_anwenden(lade_config_text(neu))
    pruefe("Tool: Mikrofon live", aufrufe == [("mikrofon", "Headset")])
    aufrufe.clear()
    neu = setze(neu, "allgemein", "sprache", "en")
    app._config_anwenden(lade_config_text(neu))
    pruefe("Tool: Sprache startet Whisper neu", [a[0] for a in aufrufe] == ["engine"] and app.cfg.sprache == "en")
    aufrufe.clear()
    app._config_anwenden(lade_config_text(neu))
    pruefe("Tool: nichts geändert = nichts tun", aufrufe == [])

    datei = tmp / "config.toml"
    datei.write_text(C, encoding="utf-8")
    app._config_datei, app._config_mtime = datei, 0.0
    app._config_pruefen()
    pruefe("Tool: Datei geladen", app.cfg.modus == "beides")
    datei.write_text("[allgemein\n", encoding="utf-8")
    t = time.time() + 5
    os.utime(datei, (t, t))
    app._config_pruefen()
    pruefe("Tool: kaputte Datei -> alte Werte, Meldung", app.cfg.modus == "beides" and meldungen
           and "config.toml" in meldungen[-1])
    anzahl = len(meldungen)
    app._config_pruefen()
    pruefe("Tool: Meldung nur einmal je Änderung", len(meldungen) == anzahl)


def test_menue():
    import diktat.tray as tr

    class A:
        pausiert, unter_waechter, modell, geraet_wahl, mikrofon, modus = False, True, "turbo", "auto", "", "beides"
        modelle, recheneinheiten = {}, []

        def mikrofone(self):
            return []

        def aktuelles_mikrofon(self):
            return ""

        def bedien_hinweis(self):
            return ""

        def autostart_aktiv(self):
            return False

    t = tr.Tray.__new__(tr.Tray)
    t.a, t.zustand, t.detail = A(), "bereit", ""
    menue = t._menue()
    texte = [str(e.text) for e in menue.items if isinstance(e.text, str)]
    pruefe("Menü: Einstellungen …", "Einstellungen …" in texte and "Log öffnen" in texte)
    pruefe("Menü: alte Datei-Einträge weg", not any("bearbeiten" in x or "öffnen …" in x for x in texte))
    pruefe("Menü: Einstellungen ist Standard (Linksklick)",
           any(e.default for e in menue.items if str(e.text) == "Einstellungen …"))


if __name__ == "__main__":
    test_tomltext()
    test_daten()
    with tempfile.TemporaryDirectory() as t:
        test_tool_seite(Path(t))
    test_menue()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
