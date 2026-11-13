"""Sprachbefehle: „… Enter“ am Diktat-Ende und feste Befehlssätze aus befehle.toml.

`zerlege()` macht aus dem erkannten Text den einzufügenden Text und eine Liste von Aktionen. Ein Befehlssatz löst nur
aus, wenn das ganze Diktat genau dieser Satz ist; alles andere bleibt normaler Text.
"""
import logging
import re
import tomllib
from dataclasses import dataclass, field

from .hotkey import parse_shortcut

log = logging.getLogger("diktat")

SATZZEICHEN = ".,!?;:\"'„“”‚‘’»«()-–—…"
# Satzformen für [oeffnen]; {} = Name
OEFFNEN_FORMEN = ("öffne {}", "{} öffnen", "öffne mal {}", "mach {} auf", "{} aufmachen",
                  "starte {}", "{} starten", "geh zu {}", "zeig {}", "zeig mir {}")
LETZTES_WORT = re.compile(r"\S+\s*$")


@dataclass(frozen=True)
class Aktion:
    art: str   # "taste" | "oeffne"
    ziel: str  # z. B. "ctrl+z" oder "https://…"


@dataclass
class Ergebnis:
    text: str
    aktionen: list[Aktion] = field(default_factory=list)


@dataclass
class Befehle:
    saetze: dict[str, Aktion]  # normalisierter Satz -> Aktion
    fehler: str | None = None


def normalisiere(text: str) -> str:
    woerter = (w.strip(SATZZEICHEN) for w in text.lower().split())
    return " ".join(w for w in woerter if w)


def pruefe_tasten(kombi: str) -> None:
    """Wirft ValueError, wenn eine Kombination der Folge keine gültige Taste hat."""
    teile = kombi.split()
    if not teile:
        raise ValueError("leere Tastenangabe")
    for teil in teile:
        try:
            mods, key = parse_shortcut(teil)
        except ValueError as e:
            raise ValueError(f"Taste '{teil}': {e}") from None
        if key is None:
            raise ValueError(f"Taste '{teil}': nur Zusatztasten, es fehlt eine normale Taste")


def _namen(schluessel: str) -> list[str]:
    return [n for n in (normalisiere(t) for t in schluessel.split("|")) if n]


def parse_befehle(toml_text: str) -> Befehle:
    try:
        raw = tomllib.loads(toml_text)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Syntaxfehler: {e}") from None
    saetze: dict[str, Aktion] = {}

    def neu(satz: str, aktion: Aktion):
        saetze.setdefault(satz, aktion)  # bei doppelten Sätzen gewinnt der erste

    for abschnitt in ("oeffnen", "tasten"):
        eintraege = raw.get(abschnitt, {})
        if not isinstance(eintraege, dict):
            raise ValueError(f"[{abschnitt}] muss ein Abschnitt sein")
        for schluessel, ziel in eintraege.items():
            if not isinstance(ziel, str) or not ziel.strip():
                raise ValueError(f"[{abschnitt}] \"{schluessel}\": Wert muss ein Text sein")
            ziel = ziel.strip()
            if abschnitt == "oeffnen":
                for name in _namen(schluessel):
                    for form in OEFFNEN_FORMEN:
                        neu(form.format(name), Aktion("oeffne", ziel))
            else:
                pruefe_tasten(ziel)
                for satz in _namen(schluessel):
                    neu(satz, Aktion("taste", ziel))
    return Befehle(saetze)


def zerlege(text: str, befehle: Befehle, enter_woerter: list[str]) -> Ergebnis:
    aktion = befehle.saetze.get(normalisiere(text))
    if aktion is not None:
        return Ergebnis("", [aktion])
    m = LETZTES_WORT.search(text)
    if m and enter_woerter and normalisiere(m.group()) in {normalisiere(w) for w in enter_woerter}:
        rest = text[:m.start()].rstrip().rstrip(",;:-–—").rstrip()
        return Ergebnis(rest, [Aktion("taste", "enter")])
    return Ergebnis(text, [])
