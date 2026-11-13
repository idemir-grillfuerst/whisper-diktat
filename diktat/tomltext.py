"""TOML-Dateien zeilenweise ändern, ohne Kommentare, Leerzeilen und Reihenfolge anzutasten.

tomllib kann nur lesen. Für das Einstellungsfenster (und config.speichere_wert, Textfeld-Regeln) brauchen wir
Schreiben, das die vom Menschen gepflegten Dateien respektiert. Schlüssel und Tabellenköpfe werden über tomllib
normalisiert, damit `claude`, `"claude"` und `[regeln.claude]`/`[regeln."claude"]` jeweils gleich behandelt werden.
"""
import re
import tomllib

SCHLUESSEL = re.compile(r'''^\s*("(?:[^"\\]|\\.)*"|'[^']*'|[A-Za-z0-9_-]+)\s*=''')
MAX_ZEILEN_WERT = 200


def _toml_text(wert: str) -> str:
    return '"' + wert.replace("\\", "\\\\").replace('"', '\\"') + '"'


def wert_text(wert) -> str:
    if isinstance(wert, bool):
        return "true" if wert else "false"
    if isinstance(wert, (int, float)):
        return repr(wert)
    if isinstance(wert, str):
        return _toml_text(wert)
    if isinstance(wert, (list, tuple)):
        return "[" + ", ".join(wert_text(w) for w in wert) + "]"
    raise TypeError(f"Wert nicht als TOML darstellbar: {wert!r}")


def schluessel_text(schluessel: str) -> str:
    return schluessel if re.fullmatch(r"[A-Za-z0-9_-]+", schluessel) else _toml_text(schluessel)


def tabellen_pfad(zeile: str) -> tuple[str, ...] | None:
    """Pfad eines TOML-Tabellenkopfs, egal wie geschrieben: [regeln.claude], [regeln."claude"]  # Kommentar …"""
    s = zeile.lstrip()
    if not s.startswith("[") or s.startswith("[["):
        return None
    try:
        d = tomllib.loads(zeile.strip() + "\n")
    except tomllib.TOMLDecodeError:
        return None
    pfad = []
    while isinstance(d, dict) and len(d) == 1:
        (schl, d), = d.items()
        pfad.append(schl)
    return tuple(pfad)


def _schluessel_der_zeile(zeile: str) -> tuple[str, str] | None:
    """(normalisierter Schlüssel, Rohtext des Schlüssels) einer Wertzeile, sonst None."""
    m = SCHLUESSEL.match(zeile)
    if not m:
        return None
    roh = m.group(1)
    try:
        d = tomllib.loads(f"{roh} = 0\n")
    except tomllib.TOMLDecodeError:
        return None
    return next(iter(d)), roh


def _gueltig(text: str) -> bool:
    try:
        tomllib.loads(text + "\n")
        return True
    except tomllib.TOMLDecodeError:
        return False


def _wert_ende(zeilen: list[str], i: int) -> int:
    """Index der letzten Zeile des Werts, der in Zeile i beginnt (mehrzeilige Arrays/Strings)."""
    for j in range(i, min(len(zeilen), i + MAX_ZEILEN_WERT)):
        if _gueltig("\n".join(zeilen[i:j + 1])):
            return j
    return i


def _kommentar(zeile: str) -> str:
    """Kommentar am Zeilenende samt Leerraum davor (oder "")."""
    for pos in [m.start() for m in re.finditer("#", zeile)]:
        if _gueltig(zeile[:pos]):
            vorne = zeile[:pos]
            return vorne[len(vorne.rstrip()):] + zeile[pos:]
    return ""


def _abschnitt(zeilen: list[str], abschnitt: str) -> tuple[int, int] | None:
    """(Index des Kopfs, Index hinter dem Abschnitt) oder None."""
    start = None
    for i, z in enumerate(zeilen):
        pfad = tabellen_pfad(z)
        if pfad is None:
            continue
        if start is not None:
            return start, i
        if pfad == (abschnitt,):
            start = i
    return (start, len(zeilen)) if start is not None else None


def _werte(zeilen: list[str], von: int, bis: int):
    """Erzeugt (normalisierter Schlüssel, Rohschlüssel, erste Zeile, letzte Zeile) im Bereich."""
    i = von
    while i < bis:
        z = zeilen[i]
        s = z.strip()
        if not s or s.startswith("#"):
            i += 1
            continue
        k = _schluessel_der_zeile(z)
        ende = _wert_ende(zeilen, i)
        if k:
            yield k[0], k[1], i, ende
        i = ende + 1


def setze(text: str, abschnitt: str, schluessel: str, wert, neuer_schluessel: str | None = None) -> str:
    """Wert setzen (Zeile ersetzen oder ergänzen). Mit neuer_schluessel wird der Eintrag an Ort und Stelle
    umbenannt (z. B. Befehl mit geänderten Sätzen)."""
    zeilen = text.splitlines()
    bereich = _abschnitt(zeilen, abschnitt)
    if bereich is None:
        while zeilen and not zeilen[-1].strip():
            zeilen.pop()
        if zeilen:
            zeilen.append("")
        zeilen += [f"[{abschnitt}]", f"{schluessel_text(neuer_schluessel or schluessel)} = {wert_text(wert)}"]
        return "\n".join(zeilen) + "\n"
    kopf, ende = bereich
    letzte = kopf
    for norm, roh, a, b in _werte(zeilen, kopf + 1, ende):
        if norm == schluessel:
            kommentar = _kommentar(zeilen[a]) if a == b else ""
            name = schluessel_text(neuer_schluessel) if neuer_schluessel is not None else roh
            zeilen[a:b + 1] = [f"{name} = {wert_text(wert)}{kommentar}"]
            return "\n".join(zeilen) + "\n"
        letzte = b
    if letzte == kopf:  # Abschnitt ohne Werte: hinter Kopf und direkt folgende Kommentare
        while letzte + 1 < ende and zeilen[letzte + 1].lstrip().startswith("#"):
            letzte += 1
    zeilen.insert(letzte + 1, f"{schluessel_text(neuer_schluessel or schluessel)} = {wert_text(wert)}")
    return "\n".join(zeilen) + "\n"


def entferne(text: str, abschnitt: str, schluessel: str) -> str:
    zeilen = text.splitlines()
    bereich = _abschnitt(zeilen, abschnitt)
    if bereich is None:
        return text
    for norm, _roh, a, b in _werte(zeilen, bereich[0] + 1, bereich[1]):
        if norm == schluessel:
            del zeilen[a:b + 1]
            return "\n".join(zeilen) + ("\n" if zeilen else "")
    return text


def eintraege(text: str, abschnitt: str) -> list[tuple[str, str]]:
    """[(normalisierter Schlüssel, Rohtext des Werts)] des Abschnitts in Dateireihenfolge."""
    zeilen = text.splitlines()
    bereich = _abschnitt(zeilen, abschnitt)
    if bereich is None:
        return []
    erg = []
    for norm, _roh, a, b in _werte(zeilen, bereich[0] + 1, bereich[1]):
        roh = "\n".join(zeilen[a:b + 1])
        wert = roh[SCHLUESSEL.match(roh).end():].strip()
        erg.append((norm, wert))
    return erg
