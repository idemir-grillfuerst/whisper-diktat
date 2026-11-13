"""Sprachbefehl „Textfeld“: Cursor ins Eingabefeld des Fensters vorne setzen.

Reihenfolge (siehe docs/superpowers/specs/2026-11-13-textfeld-design.md):
  1. Regel aus textfelder.toml für Programm bzw. Browser+Domain (Feldmerkmale, Taste oder Klickposition)
  2. automatische Suche über die Windows-Bedienungshilfe (UI Automation, Modul uia)
  3. gemerkte Klickposition (über „merke Textfeld“, wenn unter der Maus kein Feld erkennbar war)

Dieser Teil enthält die reine Logik (ohne Windows testbar) und die Aktionen. Der Zugriff auf UI Automation steckt in
uia.py und wird hier über die Modulvariable `uia` benutzt, damit Tests ihn ersetzen können.
"""
import logging
import re
import time
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from . import inserter, marker, uia
from .befehle import pruefe_tasten
from .config import TEXTFELDER_DATEI, _toml_text, aus_vorlage
from .tomltext import tabellen_pfad
from .uia import UiaFehlt

log = logging.getLogger("diktat")

BROWSER = ("chrome", "msedge", "firefox")
ADRESSLEISTEN_KLASSEN = ("OmniboxViewViews",)          # Chrome, Edge
ADRESSLEISTEN_IDS = ("urlbar-input",)                  # Firefox
NAMENS_WOERTER = ("nachricht", "message", "prompt", "eingeben", "antwort", "reply", "chat", "schreib", "verfassen",
                  "compose", "frag")
TYPEN = ("Edit", "Document")
WECHSELNDE_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d{6,}", re.IGNORECASE)


@dataclass(frozen=True)
class Kandidat:
    name: str
    automation_id: str
    typ: str                          # "Edit" | "Document"
    klasse: str
    rect: tuple[int, int, int, int]   # links, oben, rechts, unten (Bildschirmpunkte)
    fokus: bool = False


@dataclass(frozen=True)
class Regel:
    name: str = ""
    automation_id: str = ""
    typ: str = ""
    taste: str = ""
    x: float | None = None            # Klickposition als Bruchteil 0–1 der Fensterbreite/-höhe
    y: float | None = None


# --- Auswahl ------------------------------------------------------------------------------------------------------
def flaeche(k: Kandidat) -> int:
    l, o, r, u = k.rect
    return max(0, r - l) * max(0, u - o)


def ist_adressleiste(k: Kandidat) -> bool:
    return k.klasse in ADRESSLEISTEN_KLASSEN or k.automation_id in ADRESSLEISTEN_IDS


def bewerte(k: Kandidat, fenster: tuple[int, int, int, int]) -> float:
    punkte = 0.0
    name = k.name.lower()
    if any(w in name for w in NAMENS_WOERTER):
        punkte += 100
    if k.fokus:
        punkte += 50
    oben, unten = fenster[1], fenster[3]
    if unten > oben:  # Chat-Felder liegen unten: je weiter unten, desto mehr (0–30)
        mitte = (k.rect[1] + k.rect[3]) / 2
        punkte += min(30.0, max(0.0, 30 * (mitte - oben) / (unten - oben)))
    return punkte


def waehle(kandidaten: list[Kandidat], fenster: tuple[int, int, int, int]) -> Kandidat | None:
    gueltig = [k for k in kandidaten if flaeche(k) > 0 and not ist_adressleiste(k)]
    if not gueltig:
        return None
    return max(gueltig, key=lambda k: (bewerte(k, fenster), flaeche(k)))


# --- Schlüssel und Regeln -----------------------------------------------------------------------------------------
def domain(url: str | None) -> str | None:
    if not url:
        return None
    rest = re.sub(r"^[a-z][a-z0-9+.-]*://", "", url.strip(), flags=re.IGNORECASE)
    host = re.split(r"[/?#:]", rest, maxsplit=1)[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def schluessel(prozess: str, url: str | None) -> str:
    prozess = prozess.lower()
    if prozess in BROWSER:
        d = domain(url)
        if d:
            return f"{prozess}|{d}"
    return prozess


def wechselnde_id(aid: str) -> bool:
    return bool(WECHSELNDE_ID.search(aid or ""))


def regel_aus_kandidat(k: Kandidat) -> Regel | None:
    aid = "" if wechselnde_id(k.automation_id) else k.automation_id
    if not k.name and not aid:
        return None
    return Regel(name=k.name, automation_id=aid, typ=k.typ)


def passt(regel: Regel, k: Kandidat) -> bool:
    if not (regel.name or regel.automation_id):
        return False
    return ((not regel.name or regel.name == k.name) and (not regel.automation_id or regel.automation_id ==
            k.automation_id) and (not regel.typ or regel.typ == k.typ))


def _regel(schl: str, werte) -> Regel:
    if not isinstance(werte, dict):
        raise ValueError(f"[regeln.\"{schl}\"] muss ein Abschnitt sein")
    erlaubt = {f.name for f in fields(Regel)}
    fremd = set(werte) - erlaubt
    if fremd:
        raise ValueError(f"[regeln.\"{schl}\"]: unbekannt: {', '.join(sorted(fremd))}")
    for feld in ("name", "automation_id", "typ", "taste"):
        if feld in werte and not isinstance(werte[feld], str):
            raise ValueError(f"[regeln.\"{schl}\"] {feld} muss ein Text sein")
    if werte.get("typ") and werte["typ"] not in TYPEN:
        raise ValueError(f"[regeln.\"{schl}\"] typ muss {' oder '.join(TYPEN)} sein")
    for feld in ("x", "y"):
        if feld in werte and (isinstance(werte[feld], bool) or not isinstance(werte[feld], (int, float))
                              or not 0 <= werte[feld] <= 1):
            raise ValueError(f"[regeln.\"{schl}\"] {feld} muss eine Zahl zwischen 0 und 1 sein")
    r = Regel(**{k: (float(v) if k in ("x", "y") else v) for k, v in werte.items()})
    if r.taste:
        pruefe_tasten(r.taste)
    elif not (r.name or r.automation_id) and (r.x is None or r.y is None):
        raise ValueError(f"[regeln.\"{schl}\"] braucht taste, name/automation_id oder x und y")
    return r


def parse_regeln(text: str) -> dict[str, Regel]:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Syntaxfehler: {e}") from None
    regeln = raw.get("regeln", {})
    if not isinstance(regeln, dict):
        raise ValueError("[regeln] muss ein Abschnitt sein")
    return {schl: _regel(schl, werte) for schl, werte in regeln.items()}


def _block(schl: str, regel: Regel) -> list[str]:
    zeilen = [f"[regeln.{_toml_text(schl)}]"]
    for f in fields(Regel):
        wert = getattr(regel, f.name)
        if wert in ("", None):
            continue
        zeilen.append(f"{f.name} = {_toml_text(wert) if isinstance(wert, str) else repr(round(wert, 4))}")
    return zeilen


def setze_regel(text: str, schl: str, regel: Regel | None) -> str:
    """Ersetzt, ergänzt (regel) oder entfernt (None) nur den Block [regeln."schl"]. Der Block reicht bis zum nächsten
    Tabellenkopf; seine Wertzeilen werden ersetzt, Kommentare und Leerzeilen darin bleiben stehen."""
    zeilen = text.splitlines()
    neu, i, ersetzt = [], 0, False
    while i < len(zeilen):
        if tabellen_pfad(zeilen[i]) == ("regeln", schl):
            i += 1
            behalten = []
            while i < len(zeilen) and tabellen_pfad(zeilen[i]) is None:
                if not zeilen[i].strip() or zeilen[i].lstrip().startswith("#"):
                    behalten.append(zeilen[i])
                i += 1
            if regel is not None and not ersetzt:
                neu.extend(_block(schl, regel))
            neu.extend(behalten)
            ersetzt = True
            continue
        neu.append(zeilen[i])
        i += 1
    if regel is not None and not ersetzt:
        if neu and neu[-1].strip():
            neu.append("")
        neu.extend(_block(schl, regel))
    return "\n".join(neu) + "\n" if neu else ""


_CACHE: dict[Path, tuple[float, dict[str, Regel], str | None]] = {}


def lade_regeln(datei: Path | None = None) -> tuple[dict[str, Regel], str | None]:
    """(Regeln, Fehlermeldung). Neu gelesen nur nach Änderung; Fehler legen nur die Regeln still."""
    if datei is None:
        datei = TEXTFELDER_DATEI
        try:
            aus_vorlage(datei)
        except OSError as e:
            log.warning("textfelder.toml konnte nicht aus der Vorlage angelegt werden: %s", e)
    try:
        mtime = datei.stat().st_mtime
    except OSError:
        return {}, None
    alt = _CACHE.get(datei)
    if alt and alt[0] == mtime:
        return alt[1], alt[2]
    try:
        regeln, fehler = parse_regeln(datei.read_text(encoding="utf-8")), None
    except Exception as e:  # noqa: BLE001 – eine kaputte Regeldatei darf nie ein Diktat kosten
        regeln, fehler = {}, f"{datei.name}: {e}"[:200]
        log.warning("Textfeld-Regeln aus – %s", fehler)
    _CACHE[datei] = (mtime, regeln, fehler)
    return regeln, fehler


# --- Aktionen -----------------------------------------------------------------------------------------------------
REGEL_DATEI: Path | None = None   # None = textfelder.toml im Projektordner (Tests biegen das um)
OHNE_COMTYPES = "Textfeld braucht das Paket comtypes – Installation aktualisieren (install.ps1)"


@dataclass
class Antwort:
    ok: bool
    meldung: str


def _schluessel_fuer(hwnd: int) -> str:
    prozess = uia.prozessname(hwnd)
    return schluessel(prozess, uia.adresse(hwnd) if prozess in BROWSER else None)


def _regeln() -> dict[str, Regel]:
    return lade_regeln(REGEL_DATEI)[0]


def _schreibe(schl: str, regel: Regel | None) -> None:
    datei = REGEL_DATEI or TEXTFELDER_DATEI
    if REGEL_DATEI is None:
        aus_vorlage(datei)
    alt = datei.read_text(encoding="utf-8") if datei.exists() else ""
    neu = setze_regel(alt, schl, regel)
    parse_regeln(neu)  # nie eine Datei schreiben, die danach nicht mehr lesbar ist (wirft ValueError)
    datei.write_text(neu, encoding="utf-8")
    _CACHE.pop(datei, None)


def zeichen_fuer_feld(rect: tuple[int, int, int, int]) -> tuple[int, int]:
    """Wo das Bestätigungszeichen an einem Feld sitzt: rechts innen, bei schmalen Feldern in der Mitte."""
    l, o, r, u = rect
    return (r - 24 if r - l > 80 else (l + r) // 2), (o + u) // 2


def _markiere(pos: tuple[int, int] | None, ok: bool) -> None:
    """Kurzes Zeichen am Bildschirm (Haken/Kreuz). Darf nie eine Aktion scheitern lassen."""
    if pos is None:
        return
    try:
        marker.zeige(pos[0], pos[1], ok)
    except Exception:  # noqa: BLE001
        log.exception("Bestätigungszeichen ging nicht")


def _fokus_setzen(el, typ: str) -> None:
    if not uia.fokussiere(el):
        inserter.klicke(*uia.mitte(el))
    if typ == "Edit":  # bei ganzen Dokumenten (z. B. Mailtext mit Zitat) nicht ans Ende springen
        inserter.druecke("ctrl+end")


def textfeld(frist_s: float = 1.5, takt_s: float = 0.3) -> Antwort:
    """Cursor ins Eingabefeld des Fensters vorne setzen."""
    try:
        hwnd = uia.fenster_vorne()
        schl = _schluessel_fuer(hwnd)
        regel = _regeln().get(schl)
        rect = uia.fenster_rect(hwnd)
        if regel and regel.taste:
            inserter.druecke(regel.taste)
            return Antwort(True, f"Textfeld per Taste {regel.taste} ({schl})")
        if regel and regel.x is not None and regel.y is not None and not (regel.name or regel.automation_id):
            l, o, r, u = rect
            inserter.klicke(round(l + regel.x * (r - l)), round(o + regel.y * (u - o)))
            inserter.druecke("ctrl+end")
            return Antwort(True, f"Textfeld per Klickposition ({schl})")
        ende = time.monotonic() + frist_s
        while True:
            liste = uia.kandidaten(hwnd)
            treffer = None
            if regel:
                treffer = next(((k, e) for k, e in liste if passt(regel, k)), None)
            if treffer is None:
                beste = waehle([k for k, _ in liste], rect)
                treffer = next(((k, e) for k, e in liste if k is beste), None) if beste else None
            if treffer is not None:
                break
            if time.monotonic() >= ende:
                log.info("Kein Textfeld gefunden (%s, %d Kandidaten)", schl, len(liste))
                _markiere(((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2), False)
                return Antwort(False, f"Kein Textfeld gefunden ({schl})")
            time.sleep(takt_s)
        kand, el = treffer
        _fokus_setzen(el, kand.typ)
        log.info("Textfeld: %s „%s“ (%s)", kand.typ, kand.name, schl)
        return Antwort(True, f"Textfeld: {kand.name or kand.typ} ({schl})")
    except UiaFehlt:
        return Antwort(False, OHNE_COMTYPES)
    except Exception as e:  # noqa: BLE001
        log.exception("Textfeld fehlgeschlagen")
        return Antwort(False, f"Textfeld ging nicht: {e}"[:100])


def textfeld_merken() -> Antwort:
    """Feld unter der Maus (ersatzweise die Mausposition) als Regel für Programm/Website unter der Maus merken."""
    pos = None
    try:
        hwnd = uia.fenster_unter_maus()
        schl = _schluessel_fuer(hwnd)
        unter = uia.kandidat_unter_maus()
        regel = regel_aus_kandidat(unter[0]) if unter else None
        if regel is not None:
            pos = zeichen_fuer_feld(unter[0].rect)
            was = regel.name or regel.automation_id
        else:
            mx, my = uia.maus_position()
            pos = (mx, my)
            l, o, r, u = uia.fenster_rect(hwnd)
            if r <= l or u <= o:
                _markiere(pos, False)
                return Antwort(False, f"Textfeld merken ging nicht: Fenster unbekannt ({schl})")
            regel = Regel(x=round(min(1.0, max(0.0, (mx - l) / (r - l))), 4),
                          y=round(min(1.0, max(0.0, (my - o) / (u - o))), 4))
            was = f"Position {regel.x:.0%} / {regel.y:.0%}"
        _schreibe(schl, regel)
        log.info("Textfeld gemerkt für %s: %s", schl, regel)
        _markiere(pos, True)
        return Antwort(True, f"Textfeld gemerkt für {schl}: {was}")
    except UiaFehlt:
        return Antwort(False, OHNE_COMTYPES)
    except Exception as e:  # noqa: BLE001
        log.exception("Textfeld merken fehlgeschlagen")
        _markiere(pos, False)
        return Antwort(False, f"Textfeld merken ging nicht: {e}"[:100])


def textfeld_vergessen() -> Antwort:
    """Regel für Programm/Website des Fensters vorne löschen."""
    pos = None
    try:
        pos = uia.maus_position()
        schl = _schluessel_fuer(uia.fenster_vorne())
        if schl not in _regeln():
            _markiere(pos, False)
            return Antwort(False, f"Keine Regel für {schl}")
        _schreibe(schl, None)
        log.info("Textfeld-Regel gelöscht für %s", schl)
        _markiere(pos, True)
        return Antwort(True, f"Textfeld-Regel gelöscht für {schl}")
    except UiaFehlt:
        return Antwort(False, OHNE_COMTYPES)
    except Exception as e:  # noqa: BLE001
        log.exception("Textfeld vergessen fehlgeschlagen")
        return Antwort(False, f"Textfeld vergessen ging nicht: {e}"[:100])


def vorwaermen() -> None:
    """Beim Aufnahmestart: Fenster vorne einmal abfragen, damit Chromium seine Bedienungshilfe einschaltet."""
    try:
        uia.vorwaermen(uia.fenster_vorne())
    except Exception:  # noqa: BLE001 – Vorwärmen ist nur eine Hilfe
        pass
