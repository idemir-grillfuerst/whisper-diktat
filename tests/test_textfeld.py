"""Tests für den Sprachbefehl „Textfeld“, ohne echte Eingaben und ohne UI Automation (Fake statt uia).

Aufruf (im Projektordner):
    %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_textfeld
"""
import sys
import tempfile
from pathlib import Path

from diktat import PROJEKT
from diktat.textfeld import (Kandidat, Regel, parse_regeln, passt, regel_aus_kandidat, schluessel, setze_regel,
                             waehle, wechselnde_id)

FEHLER = []


def pruefe(name, bedingung):
    print(("OK    " if bedingung else "FEHLER"), name)
    if not bedingung:
        FEHLER.append(name)


F = (0, 0, 1000, 1000)


def k(name="", aid="", typ="Edit", klasse="", rect=(100, 900, 900, 950), fokus=False):
    return Kandidat(name, aid, typ, klasse, rect, fokus)


def test_wahl():
    suche, chat = k("Suchen", rect=(100, 50, 900, 90)), k("Nachricht eingeben", rect=(100, 900, 900, 960))
    pruefe("Chatfeld vor Suche", waehle([suche, chat], F) == chat)
    pruefe("Name schlägt Lage", waehle([k("Prompt", rect=(0, 100, 500, 140)), k(rect=(0, 800, 500, 840))], F).name
           == "Prompt")
    pruefe("unten schlägt oben ohne Namen",
           waehle([k(rect=(0, 100, 500, 140)), k(rect=(0, 800, 500, 840))], F).rect[1] == 800)
    pruefe("Fokus-Bonus", waehle([k(rect=(0, 800, 500, 840)), k(rect=(0, 100, 500, 140), fokus=True)], F).fokus)
    pruefe("Gleichstand: größere Fläche",
           waehle([k(rect=(0, 800, 100, 840)), k(rect=(0, 800, 600, 840))], F).rect[2] == 600)
    pruefe("Adressleiste nie", waehle([k("Adress- und Suchleiste", klasse="OmniboxViewViews")], F) is None)
    pruefe("Firefox-Adressleiste nie", waehle([k(aid="urlbar-input")], F) is None)
    pruefe("Fläche 0 nie", waehle([k(rect=(5, 5, 5, 5))], F) is None)
    pruefe("leer", waehle([], F) is None)


def test_schluessel():
    pruefe("Browser+Domain", schluessel("chrome", "https://www.claude.ai/new") == "chrome|claude.ai")
    pruefe("ohne Schema", schluessel("msedge", "outlook.office.com/mail/") == "msedge|outlook.office.com")
    pruefe("Browser ohne URL", schluessel("chrome", None) == "chrome")
    pruefe("Browser mit leerer URL", schluessel("firefox", "") == "firefox")
    pruefe("App", schluessel("ms-teams", "egal") == "ms-teams")


def test_ids():
    pruefe("Teams-UUID wechselt", wechselnde_id("new-message-7ee15fb7-3873-4ecc-b06d-d7fa1545eacd"))
    pruefe("lange Ziffern wechseln", wechselnde_id("UniqueMessageBody_1234567"))
    pruefe("stabil", not wechselnde_id("view_1012") and not wechselnde_id("urlbar-input"))
    pruefe("Regel ohne wechselnde ID",
           regel_aus_kandidat(k("Nachricht eingeben", aid="new-message-7ee15fb7-3873-4ecc-b06d-d7fa1545eacd"))
           == Regel(name="Nachricht eingeben", typ="Edit"))
    pruefe("Regel mit stabiler ID", regel_aus_kandidat(k("", aid="eingabe")) == Regel(automation_id="eingabe", typ="Edit"))
    pruefe("ohne Name und ID: None", regel_aus_kandidat(k()) is None)
    pruefe("passt", passt(Regel(name="Prompt", typ="Edit"), k("Prompt")) and not passt(Regel(name="Prompt"), k("Suche")))
    pruefe("passt nicht bei anderem Typ", not passt(Regel(name="Prompt", typ="Document"), k("Prompt")))


def test_regeln():
    text = ('# Kopf bleibt\n[regeln."ms-teams"]\ntaste = "alt+shift+c"\n# Kommentar bleibt\n'
            '[regeln."greyhound"]\nx = 0.4\ny = 0.9\n')
    r = parse_regeln(text)
    pruefe("taste", r["ms-teams"] == Regel(taste="alt+shift+c"))
    pruefe("position", r["greyhound"] == Regel(x=0.4, y=0.9))
    neu = setze_regel(text, "chrome|claude.ai", Regel(name="Prompt", typ="Edit"))
    pruefe("ergänzt", parse_regeln(neu)["chrome|claude.ai"] == Regel(name="Prompt", typ="Edit"))
    pruefe("Kommentare bleiben", "# Kopf bleibt" in neu and "# Kommentar bleibt" in neu)
    neu2 = setze_regel(neu, "ms-teams", Regel(name="Nachricht eingeben"))
    pruefe("ersetzt", parse_regeln(neu2)["ms-teams"] == Regel(name="Nachricht eingeben")
           and neu2.count('"ms-teams"') == 1)
    pruefe("andere Regeln bleiben", parse_regeln(neu2)["greyhound"] == Regel(x=0.4, y=0.9))
    pruefe("entfernt", "ms-teams" not in parse_regeln(setze_regel(neu2, "ms-teams", None)))
    pruefe("Anführungszeichen im Namen", parse_regeln(setze_regel("", "a", Regel(name='Sag "hi"')))["a"].name
           == 'Sag "hi"')
    pruefe("leere Datei", parse_regeln("") == {})
    for kaputt in ('[regeln."a"]\nx = 2\ny = 0.5', '[regeln."a"]\ntaste = "ctrl+blub"', '[regeln."a"]\nfoo = 1',
                   '[regeln."a"\n', '[regeln."a"]\nx = 0.5', '[regeln."a"]\n'):
        try:
            parse_regeln(kaputt)
            pruefe(f"abgelehnt {kaputt!r}", False)
        except ValueError:
            pruefe(f"abgelehnt {kaputt!r}", True)
    pruefe("Vorlage gültig",
           isinstance(parse_regeln((PROJEKT / "textfelder.beispiel.toml").read_text(encoding="utf-8")), dict))


if __name__ == "__main__":
    test_wahl()
    test_schluessel()
    test_ids()
    test_regeln()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
