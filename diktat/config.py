"""Einstellungen (config.toml) und Fachwortliste (fachwoerter.txt) laden."""
import tomllib
from dataclasses import dataclass

from . import PROJEKT

CONFIG_DATEI = PROJEKT / "config.toml"
FACHWORT_DATEI = PROJEKT / "fachwoerter.txt"


@dataclass
class Stufe:
    name: str
    repo: str
    geraet: str


@dataclass
class Config:
    shortcut: str
    sprache: str
    min_dauer_s: float
    einfuegen: str
    leerzeichen_danach: bool
    aufnahmen_speichern: bool
    mikrofon_offen_halten: bool
    stufe: Stufe
    stufen: dict


def lade_config() -> Config:
    raw = tomllib.loads(CONFIG_DATEI.read_text(encoding="utf-8"))
    a = raw.get("allgemein", {})
    stufen = {n: Stufe(n, s["repo"], s["geraet"]) for n, s in raw.get("stufen", {}).items()}
    aktiv = raw.get("modell", {}).get("stufe", "schnell")
    if aktiv not in stufen:
        raise ValueError(f"Stufe '{aktiv}' fehlt in config.toml unter [stufen.*]")
    einfuegen = a.get("einfuegen", "tippen")
    if einfuegen not in ("tippen", "zwischenablage"):
        raise ValueError("einfuegen muss 'tippen' oder 'zwischenablage' sein")
    return Config(
        shortcut=a.get("shortcut", "ctrl+y"),
        sprache=a.get("sprache", "de"),
        min_dauer_s=float(a.get("min_dauer_s", 0.3)),
        einfuegen=einfuegen,
        leerzeichen_danach=bool(a.get("leerzeichen_danach", True)),
        aufnahmen_speichern=bool(a.get("aufnahmen_speichern", False)),
        mikrofon_offen_halten=bool(a.get("mikrofon_offen_halten", False)),
        stufe=stufen[aktiv],
        stufen=stufen,
    )


def fachwort_prompt(max_zeichen: int = 600) -> str | None:
    """Baut aus fachwoerter.txt den initial_prompt für Whisper (oder None, wenn leer)."""
    if not FACHWORT_DATEI.exists():
        return None
    woerter = []
    for zeile in FACHWORT_DATEI.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if zeile and not zeile.startswith("#"):
            woerter.append(zeile)
    if not woerter:
        return None
    prompt = "Fachbegriffe: " + ", ".join(woerter) + "."
    if len(prompt) > max_zeichen:  # an einer Wortgrenze kürzen, nicht mitten im Begriff
        prompt = prompt[:max_zeichen].rsplit(", ", 1)[0] + "."
    return prompt


def speichere_stufe(name: str, datei=None) -> None:
    """Schreibt die gewählte Stufe nach config.toml ([modell] stufe = ...), Kommentare bleiben erhalten."""
    datei = datei or CONFIG_DATEI
    zeilen = datei.read_text(encoding="utf-8").splitlines(keepends=True)
    abschnitt, ersetzt = None, False
    for i, z in enumerate(zeilen):
        s = z.strip()
        if s.startswith("[") and s.endswith("]"):
            abschnitt = s
        elif abschnitt == "[modell]" and s.split("=")[0].strip() == "stufe":
            zeilen[i] = f'stufe = "{name}"\n'
            ersetzt = True
            break
    if not ersetzt:
        raise ValueError("In config.toml fehlt [modell] stufe = ...")
    datei.write_text("".join(zeilen), encoding="utf-8")
