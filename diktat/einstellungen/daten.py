"""Reine Logik des Einstellungsfensters (ohne Tk, testbar): Felder mit Erklärungen, Werte lesen/prüfen/schreiben,
Befehle als Liste, Textfeld-Regeln, lesbare Anzeigen.

Geschrieben wird immer in den vorhandenen Dateitext (tomltext), nur die geänderten Werte, und nie ein Text, der
danach nicht mehr geladen werden kann.
"""
import math
import tomllib
from dataclasses import dataclass

from ..befehle import INTERNE_AKTIONEN, normalisiere, parse_befehle
from ..config import lade_config_text
from ..hotkey import parse_shortcut
from ..textfeld import parse_regeln, setze_regel
from .. import tomltext

ABSCHNITTE = ("oeffnen", "tasten", "aktionen")
FACHWORT_GRENZE = 600


@dataclass(frozen=True)
class Feld:
    abschnitt: str
    schluessel: str
    titel: str
    erklaerung: str
    art: str                                  # "text" | "wahl" | "bool" | "zahl" | "liste"
    wahl: tuple[tuple[str, str], ...] = ()    # (Wert, Anzeige)
    neustart: bool = False
    standard: object = None
    von: float | None = None                  # Zahlen: erlaubter Bereich
    bis: float | None = None
    einheit: str = ""


FELDER: dict[str, Feld] = {
    "shortcut": Feld(
        "allgemein", "shortcut", "Tastenkombination",
        "Halten = Aufnahme, loslassen = Text wird eingefügt. Gut sind Kombinationen, die sonst kein Programm braucht, "
        "z. B. Strg+Win. Strg+Y ist in vielen Programmen schon für „Wiederholen“ belegt.",
        "text", neustart=True, standard="ctrl+y"),
    "modus": Feld(
        "allgemein", "modus", "Bedienung",
        "Gilt für die Tastenkombination. Die Maustaste diktiert immer, solange sie gehalten wird.", "wahl",
        (("halten", "Halten – gedrückt halten diktiert, loslassen beendet"),
         ("umschalten", "Umschalten – einmal tippen startet, nochmal tippen beendet"),
         ("beides", "Beides – lang halten diktiert, kurz tippen startet eine Daueraufnahme")),
        standard="halten"),
    "maustaste": Feld(
        "allgemein", "maustaste", "Diktieren mit der Maus",
        "Zusätzlich zur Tastenkombination mit einer Maustaste diktieren: halten = Aufnahme. Ein kurzer Klick bleibt "
        "ein normaler Klick.", "wahl",
        (("", "Aus"), ("mitte", "Mausrad gedrückt halten"), ("x1", "Seitentaste hinten („Zurück“)"),
         ("x2", "Seitentaste vorne („Vor“)")),
        neustart=True, standard=""),
    "tipp_grenze_s": Feld(
        "allgemein", "tipp_grenze_s", "Grenze zwischen Tippen und Halten",
        "Nur für „Beides“: Kürzer gedrückt gilt als Tippen (Daueraufnahme), länger als Halten.",
        "zahl", standard=0.4, von=0.1, bis=2, einheit="s"),
    "einfuegen": Feld(
        "allgemein", "einfuegen", "Text einfügen",
        "„Tippen“ schickt den Text als Tastatureingabe und lässt die Zwischenablage in Ruhe. „Zwischenablage“ ist bei "
        "langen Texten schneller und klappt in manchen Programmen besser; der alte Inhalt wird danach "
        "wiederhergestellt.", "wahl",
        (("tippen", "Tippen"), ("zwischenablage", "Über die Zwischenablage (Strg+V)")), standard="tippen"),
    "leerzeichen_danach": Feld(
        "allgemein", "leerzeichen_danach", "Leerzeichen nach jedem Diktat",
        "Damit mehrere Diktate hintereinander nicht zusammenkleben.", "bool", standard=True),
    "enter": Feld(
        "befehle", "enter", "Wörter zum Absenden",
        "Endet ein Diktat auf eines dieser Wörter, wird es weggelassen und danach Enter gedrückt. Nur am Ende: "
        "„Passt so. Senden.“ schickt ab, „Senden wir das morgen“ bleibt Text. Leere Liste = aus.",
        "liste", standard=["enter", "senden"]),
    "max_aufnahme_s": Feld(
        "allgemein", "max_aufnahme_s", "Daueraufnahme endet spätestens nach",
        "Falls man vergisst, eine Daueraufnahme zu beenden.", "zahl", standard=300, von=10, bis=3600, einheit="s"),
    "min_dauer_s": Feld(
        "allgemein", "min_dauer_s", "Kürzere Aufnahmen ignorieren",
        "Versehentliches kurzes Drücken erzeugt so keinen Text.", "zahl", standard=0.3, von=0, bis=5, einheit="s"),
    "leerlauf_minuten": Feld(
        "allgemein", "leerlauf_minuten", "Modell entladen nach",
        "Spart Arbeitsspeicher, wenn länger nicht diktiert wird. Beim nächsten Diktat lädt es neu (ca. 4 s), "
        "während du schon sprichst. 0 = nie.", "zahl", standard=0, von=0, bis=1440, einheit="min"),
    "aufnahmen_speichern": Feld(
        "allgemein", "aufnahmen_speichern", "Aufnahmen speichern",
        "Speichert jede Aufnahme als WAV im Ordner „aufnahmen“. Nur zum Testen, die Dateien enthalten deine Diktate.",
        "bool", standard=False),
    "mikrofon": Feld(
        "allgemein", "mikrofon", "Mikrofon",
        "„Windows-Standard“ folgt dem Mikrofon, das in Windows eingestellt ist (z. B. Headset, sobald es "
        "angeschlossen ist).", "text", standard=""),
    "mikrofon_offen_halten": Feld(
        "allgemein", "mikrofon_offen_halten", "Mikrofon dauerhaft offen halten",
        "Hilft, wenn ein Funkheadset nach einer Pause den Anfang verschluckt: Das Tool nimmt dann ~0,4 s vor dem "
        "Tastendruck mit. Nachteil: Windows zeigt dauerhaft „Mikrofon in Verwendung“, das Headset bleibt aktiv (Akku).",
        "bool", neustart=True, standard=False),
    "modell": Feld(
        "modell", "name", "Modell",
        "Turbo ist schnell und für Diktate meist genau genug. Large-v3 ist genauer bei Namen und Fachbegriffen, "
        "braucht aber etwa doppelt so lange.", "text", standard="turbo"),
    "geraet": Feld(
        "modell", "geraet", "Recheneinheit",
        "Worauf Whisper rechnet. „Automatisch“ nimmt die Grafik, wenn vorhanden, sonst den Prozessor. Die NPU ist "
        "sparsam, das erste Laden dauert dort aber Minuten.", "text", standard="auto"),
    "sprache": Feld(
        "allgemein", "sprache", "Sprache",
        "In welcher Sprache du diktierst.", "wahl", (("de", "Deutsch"), ("en", "Englisch")), standard="de"),
}


# --- Werte --------------------------------------------------------------------------------------------------------
def lies_werte(text: str) -> dict[str, object]:
    """Aktuelle Werte aller FELDER (wirft ValueError, wenn die Datei nicht ladbar ist)."""
    c = lade_config_text(text)
    return {
        "shortcut": c.shortcut, "modus": c.modus, "maustaste": c.maustaste, "tipp_grenze_s": c.tipp_grenze_s,
        "einfuegen": c.einfuegen, "leerzeichen_danach": c.leerzeichen_danach, "enter": list(c.enter_woerter),
        "max_aufnahme_s": c.max_aufnahme_s, "min_dauer_s": c.min_dauer_s, "leerlauf_minuten": c.leerlauf_minuten,
        "aufnahmen_speichern": c.aufnahmen_speichern, "mikrofon": c.mikrofon,
        "mikrofon_offen_halten": c.mikrofon_offen_halten, "modell": c.modell, "geraet": c.geraet,
        "sprache": c.sprache,
    }


def zahl(wert) -> float:
    """Zahl aus Eingabe ("0,4" und "0.4" gehen). ValueError, wenn keine Zahl."""
    if isinstance(wert, bool):
        raise ValueError("keine Zahl")
    if isinstance(wert, (int, float)):
        return float(wert)
    return float(str(wert).strip().replace(",", "."))


def pruefe_wert(name: str, wert) -> str | None:
    """Fehlertext oder None."""
    f = FELDER[name]
    if f.art == "zahl":
        try:
            z = zahl(wert)
        except ValueError:
            return "Bitte eine Zahl eingeben."
        if not math.isfinite(z):
            return "Bitte eine Zahl eingeben."
        if (f.von is not None and z < f.von) or (f.bis is not None and z > f.bis):
            return f"Erlaubt: {f.von:g} bis {f.bis:g} {f.einheit}".strip()
        return None
    if f.art == "wahl":
        return None if wert in {w for w, _ in f.wahl} else "Bitte einen Eintrag aus der Liste wählen."
    if f.art == "bool":
        return None if isinstance(wert, bool) else "Ja oder nein."
    if f.art == "liste":
        if not isinstance(wert, (list, tuple)) or any(not normalisiere(str(w)) for w in wert):
            return "Leere Wörter sind nicht erlaubt."
        return None
    if name == "shortcut":
        try:
            parse_shortcut(str(wert))
        except ValueError as e:
            return str(e)
    return None


def _als_toml(name: str, wert):
    f = FELDER[name]
    if f.art == "zahl":
        z = zahl(wert)
        return int(z) if z == int(z) and name in ("max_aufnahme_s", "leerlauf_minuten") else z
    if f.art == "liste":
        return [str(w).strip() for w in wert]
    return wert


def schreibe_werte(text: str, aenderungen: dict[str, object]) -> str:
    """Nur die geänderten Werte in den Dateitext schreiben. ValueError (mit allen Fehlern), wenn etwas ungültig ist."""
    fehler = {n: m for n, w in aenderungen.items() if (m := pruefe_wert(n, w))}
    if fehler:
        raise ValueError("; ".join(f"{FELDER[n].titel}: {m}" for n, m in fehler.items()))
    for name, wert in aenderungen.items():
        f = FELDER[name]
        text = tomltext.setze(text, f.abschnitt, f.schluessel, _als_toml(name, wert))
    lade_config_text(text)  # wirft ValueError, z. B. bei unbekanntem Modell
    return text


# --- Befehle ------------------------------------------------------------------------------------------------------
@dataclass
class Befehl:
    art: str            # "oeffnen" | "tasten" | "aktionen"
    saetze: list[str]
    ziel: str
    schluessel: str = ""  # Originalschlüssel in der Datei, "" = neu


def lies_befehle(text: str) -> list[Befehl]:
    erg = []
    for art in ABSCHNITTE:
        for schl, roh in tomltext.eintraege(text, art):
            try:
                ziel = tomllib.loads(f"x = {roh}")["x"]
            except Exception:  # noqa: BLE001
                ziel = roh
            erg.append(Befehl(art, [s.strip() for s in schl.split("|") if s.strip()], str(ziel), schl))
    return erg


def setze_befehl(text: str, alt: Befehl | None, neu: Befehl | None) -> str:
    """Befehl anlegen (alt=None), ändern oder löschen (neu=None). ValueError mit verständlicher Meldung."""
    if neu is not None:
        saetze = [s.strip() for s in neu.saetze]
        if not saetze or any(not normalisiere(s) for s in saetze):
            raise ValueError("Jeder Satz braucht mindestens ein Wort.")
        if not neu.ziel.strip():
            raise ValueError("Es fehlt, was passieren soll (Ziel, Tasten oder Aktion).")
        if neu.art == "aktionen" and neu.ziel not in INTERNE_AKTIONEN:
            raise ValueError(f"Unbekannte Aktion „{neu.ziel}“.")
        schluessel = "|".join(saetze)
    if alt is not None and alt.schluessel:
        if neu is not None and neu.art == alt.art:
            text = tomltext.setze(text, alt.art, alt.schluessel, neu.ziel.strip(), neuer_schluessel=schluessel)
        else:
            text = tomltext.entferne(text, alt.art, alt.schluessel)
            if neu is not None:
                text = tomltext.setze(text, neu.art, schluessel, neu.ziel.strip())
    elif neu is not None:
        text = tomltext.setze(text, neu.art, schluessel, neu.ziel.strip())
    try:
        parse_befehle(text)
    except ValueError as e:
        if "already" in str(e) or "overwrite" in str(e) or "twice" in str(e):
            raise ValueError("Diesen Satz gibt es schon als eigenen Befehl.") from None
        raise
    return text


def doppelte_saetze(befehle: list[Befehl], neu: Befehl) -> list[str]:
    """Sätze von `neu`, die schon in einem anderen Befehl vorkommen (normalisiert)."""
    andere = {normalisiere(s) for b in befehle if b.schluessel != neu.schluessel or b.art != neu.art
              for s in b.saetze}
    return [n for n in (normalisiere(s) for s in neu.saetze) if n in andere]


# --- Anzeige ------------------------------------------------------------------------------------------------------
TASTEN_NAMEN = {
    "ctrl": "Strg", "shift": "Umschalt", "alt": "Alt", "win": "Win", "enter": "Enter", "esc": "Esc", "tab": "Tab",
    "space": "Leertaste", "leertaste": "Leertaste", "backspace": "Rücktaste", "delete": "Entf", "entf": "Entf",
    "left": "←", "right": "→", "up": "↑", "down": "↓", "home": "Pos1", "pos1": "Pos1", "end": "Ende",
    "ende": "Ende", "pageup": "Bild↑", "pagedown": "Bild↓", "insert": "Einfg", "einfg": "Einfg", "pause": "Pause",
    "capslock": "Feststell", "strg": "Strg", "umschalt": "Umschalt",
}
AKTIONEN_LESBAR = {
    "textfeld": "Ins Textfeld springen",
    "textfeld_merken": "Textfeld merken (Feld unter der Maus)",
    "textfeld_vergessen": "Gemerktes Textfeld vergessen",
}
ARTEN_LESBAR = {"oeffnen": "Öffnen", "tasten": "Taste", "aktionen": "Aktion"}


def tasten_lesbar(kombi: str) -> str:
    def eine(teil: str) -> str:
        return "+".join(TASTEN_NAMEN.get(t, t.upper()) for t in teil.lower().split("+"))
    return ", dann ".join(eine(t) for t in kombi.split())


def wirkung_lesbar(b: Befehl) -> str:
    if b.art == "tasten":
        return tasten_lesbar(b.ziel)
    if b.art == "aktionen":
        return AKTIONEN_LESBAR.get(b.ziel, b.ziel)
    return b.ziel


def regeln_liste(text: str) -> list[tuple[str, str]]:
    erg = []
    for schl, r in parse_regeln(text).items():
        if r.taste:
            erg.append((schl, f"Taste {tasten_lesbar(r.taste)}"))
        elif r.name:
            erg.append((schl, f"Feld „{r.name}“"))
        elif r.automation_id:
            erg.append((schl, f"Feld mit Kennung {r.automation_id}"))
        else:
            erg.append((schl, f"Klickposition {r.x:.0%} / {r.y:.0%}"))
    return erg


def regel_loeschen(text: str, schluessel: str) -> str:
    return setze_regel(text, schluessel, None)


def fachwoerter(text: str) -> list[str]:
    return [z.strip() for z in text.splitlines() if z.strip() and not z.strip().startswith("#")]


def fachwort_laenge(text: str) -> int:
    """Länge des Whisper-Prompts, der aus diesem Text entstehen würde (ungekürzt; 0 = keine Fachwörter)."""
    w = fachwoerter(text)
    return len("Fachbegriffe: " + ", ".join(w) + ".") if w else 0
