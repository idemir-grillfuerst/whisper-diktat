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


class FakeUia:
    """Ersetzt diktat.uia: liefert vorgegebene Fenster/Kandidaten, schreibt Fokus-Versuche mit. Nur lesend."""

    def __init__(self, prozess="claude", kandidaten_folge=None, adresse=None, rect=(0, 0, 1000, 1000),
                 unter_maus=None, maus=(0, 0), fokus_klappt=True, fehlt=False):
        import diktat.textfeld as tf
        from diktat.uia import UiaFehlt
        self.UiaFehlt = UiaFehlt
        self.prozess, self.folge, self._adresse, self.rect = prozess, list(kandidaten_folge or [[]]), adresse, rect
        self.unter_maus, self.maus, self.fokus_klappt, self.fehlt = unter_maus, maus, fokus_klappt, fehlt
        self.fokussiert, self.elemente, self.gewaermt = [], {}, 0
        tf.uia = self

    def _pruefe(self):
        if self.fehlt:
            raise self.UiaFehlt("comtypes fehlt")

    def fenster_vorne(self):
        self._pruefe()
        return 1

    def fenster_unter_maus(self):
        self._pruefe()
        return 1

    def maus_position(self):
        return self.maus

    def prozessname(self, hwnd):
        return self.prozess

    def fenster_rect(self, hwnd):
        return self.rect

    def adresse(self, hwnd):
        return self._adresse

    def kandidaten(self, hwnd):
        self._pruefe()
        liste = self.folge.pop(0) if len(self.folge) > 1 else self.folge[0]
        for kand, el in liste:
            self.elemente[el] = kand
        return liste

    def kandidat_unter_maus(self):
        self._pruefe()
        return self.unter_maus

    def fokussiere(self, el):
        self.fokussiert.append(el)
        return self.fokus_klappt

    def mitte(self, el):
        l, o, r, u = self.elemente[el].rect
        return (l + r) // 2, (o + u) // 2

    def vorwaermen(self, hwnd):
        self._pruefe()
        self.gewaermt += 1


def mit_attrappen(regeldatei):
    """druecke/klicke aufzeichnen, Regeldatei umbiegen. Gibt (gedrueckt, geklickt, aufraeumen) zurück."""
    import diktat.inserter as ins
    import diktat.textfeld as tf
    gedrueckt, geklickt = [], []
    alt = (getattr(ins, "druecke"), getattr(ins, "klicke", None), tf.REGEL_DATEI, tf.uia)
    ins.druecke = gedrueckt.append
    ins.klicke = lambda x, y: geklickt.append((x, y))
    tf.REGEL_DATEI = regeldatei

    def aufraeumen():
        ins.druecke, ins.klicke, tf.REGEL_DATEI, tf.uia = alt
    return gedrueckt, geklickt, aufraeumen


def test_aktion_textfeld(tmp):
    import diktat.textfeld as tf
    regeldatei = tmp / "textfelder.toml"
    regeldatei.write_text("", encoding="utf-8")
    gedrueckt, geklickt, aufraeumen = mit_attrappen(regeldatei)
    try:
        f = FakeUia(prozess="claude", kandidaten_folge=[[], [], [(k("Prompt"), "E1")]])  # Chromium wacht erst auf
        pruefe("findet nach Wiederholung", tf.textfeld(frist_s=1.0, takt_s=0.01).ok and f.fokussiert == ["E1"])
        pruefe("Strg+Ende danach", gedrueckt[-1:] == ["ctrl+end"])
        FakeUia(prozess="claude", kandidaten_folge=[[]])
        a = tf.textfeld(frist_s=0.05, takt_s=0.01)
        pruefe("nichts gefunden", not a.ok and "Kein Textfeld" in a.meldung and "claude" in a.meldung)
        FakeUia(prozess="claude", kandidaten_folge=[[(k("Prompt"), "E1")]], fokus_klappt=False)
        tf.textfeld(frist_s=0.05, takt_s=0.01)
        pruefe("Fokus klappt nicht -> Klick in die Mitte", geklickt[-1:] == [(500, 925)])

        regeldatei.write_text('[regeln."ms-teams"]\ntaste = "alt+shift+c"\n', encoding="utf-8")
        gedrueckt.clear()
        FakeUia(prozess="ms-teams", kandidaten_folge=[[]])
        pruefe("Regel Taste", tf.textfeld(frist_s=0.05, takt_s=0.01).ok and gedrueckt == ["alt+shift+c"])

        _neu(regeldatei, '[regeln."greyhound"]\nx = 0.5\ny = 0.9\n')
        FakeUia(prozess="greyhound", rect=(100, 0, 1100, 1000))
        tf.textfeld(frist_s=0.05, takt_s=0.01)
        pruefe("Regel Position relativ zum Fenster", geklickt[-1:] == [(600, 900)])

        _neu(regeldatei, '[regeln."chrome|outlook.office.com"]\nname = "Nachrichtentext"\n')
        f = FakeUia(prozess="chrome", adresse="https://outlook.office.com/mail/", kandidaten_folge=[[
            (k("Suchen", rect=(0, 900, 500, 950)), "S"),
            (k("Nachrichtentext", typ="Document", rect=(0, 100, 500, 500)), "N")]])
        tf.textfeld(frist_s=0.05, takt_s=0.01)
        pruefe("Regel Name schlägt Automatik", f.fokussiert == ["N"])
        f = FakeUia(prozess="chrome", adresse="https://claude.ai/new", kandidaten_folge=[[
            (k("Suchen", rect=(0, 100, 500, 150)), "S"), (k("Prompt", rect=(0, 900, 500, 950)), "P")]])
        tf.textfeld(frist_s=0.05, takt_s=0.01)
        pruefe("andere Website: Automatik", f.fokussiert == ["P"])
    finally:
        aufraeumen()


def _neu(datei, text):
    """Datei neu schreiben und Änderungszeit sicher weiterschieben (Cache nach Änderungszeit)."""
    import os
    import time
    datei.write_text(text, encoding="utf-8")
    t = time.time() + len(text)
    os.utime(datei, (t, t))


def test_aktion_merken(tmp):
    import diktat.textfeld as tf
    regeldatei = tmp / "merken.toml"
    _neu(regeldatei, "# Kopf\n")
    gedrueckt, geklickt, aufraeumen = mit_attrappen(regeldatei)
    try:
        FakeUia(prozess="ms-teams", unter_maus=(
            k("Nachricht eingeben", aid="new-message-7ee15fb7-3873-4ecc-b06d-d7fa1545eacd"), "E"))
        a = tf.textfeld_merken()
        pruefe("gemerkt ohne UUID", a.ok and "ms-teams" in a.meldung
               and tf.lade_regeln(regeldatei)[0].get("ms-teams") == Regel(name="Nachricht eingeben", typ="Edit"))
        pruefe("Kopf bleibt", regeldatei.read_text(encoding="utf-8").startswith("# Kopf"))
        FakeUia(prozess="greyhound", unter_maus=None, maus=(350, 900), rect=(100, 0, 1100, 1000))
        tf.textfeld_merken()
        pruefe("ohne Feld: Position", tf.lade_regeln(regeldatei)[0].get("greyhound") == Regel(x=0.25, y=0.9))
        FakeUia(prozess="ms-teams")
        a = tf.textfeld_vergessen()
        pruefe("vergessen", a.ok and "ms-teams" not in tf.lade_regeln(regeldatei)[0])
        a = tf.textfeld_vergessen()
        pruefe("nochmal vergessen: keine Regel", not a.ok and "Keine Regel" in a.meldung)
    finally:
        aufraeumen()


def test_ohne_comtypes(tmp):
    import diktat.textfeld as tf
    gedrueckt, geklickt, aufraeumen = mit_attrappen(tmp / "leer.toml")
    try:
        FakeUia(fehlt=True)
        a = tf.textfeld(frist_s=0.05, takt_s=0.01)
        pruefe("comtypes fehlt: Meldung statt Absturz", not a.ok and "comtypes" in a.meldung)
        pruefe("merken ohne comtypes", not tf.textfeld_merken().ok)
        try:
            tf.vorwaermen()
            pruefe("vorwärmen schluckt Fehler", True)
        except Exception:  # noqa: BLE001
            pruefe("vorwärmen schluckt Fehler", False)
    finally:
        aufraeumen()


def test_vorwaermen(tmp):
    import diktat.textfeld as tf
    gedrueckt, geklickt, aufraeumen = mit_attrappen(tmp / "leer.toml")
    try:
        f = FakeUia()
        tf.vorwaermen()
        pruefe("vorwärmen fragt das Fenster ab", f.gewaermt == 1)
    finally:
        aufraeumen()


if __name__ == "__main__":
    test_wahl()
    test_schluessel()
    test_ids()
    test_regeln()
    with tempfile.TemporaryDirectory() as t:
        test_aktion_textfeld(Path(t))
        test_aktion_merken(Path(t))
        test_ohne_comtypes(Path(t))
        test_vorwaermen(Path(t))
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
