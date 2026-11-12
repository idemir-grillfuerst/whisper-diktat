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


MODI = ("halten", "umschalten", "beides")


@dataclass
class Config:
    shortcut: str
    sprache: str
    modus: str
    tipp_grenze_s: float
    max_aufnahme_s: float
    leerlauf_minuten: float
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
    modus = a.get("modus", "halten")
    if modus not in MODI:
        raise ValueError(f"modus muss einer von {', '.join(MODI)} sein")
    return Config(
        shortcut=a.get("shortcut", "ctrl+y"),
        sprache=a.get("sprache", "de"),
        modus=modus,
        tipp_grenze_s=float(a.get("tipp_grenze_s", 0.4)),
        max_aufnahme_s=float(a.get("max_aufnahme_s", 300)),
        leerlauf_minuten=float(a.get("leerlauf_minuten", 0)),
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


def speichere_wert(abschnitt: str, schluessel: str, wert: str, datei=None) -> None:
    """Ersetzt in config.toml genau die Zeile `schluessel = ...` im Abschnitt [abschnitt] durch einen
    Text-Wert. Kommentare und alles andere bleiben unverändert."""
    datei = datei or CONFIG_DATEI
    zeilen = datei.read_text(encoding="utf-8").splitlines(keepends=True)
    aktuell, ersetzt = None, False
    for i, z in enumerate(zeilen):
        s = z.strip()
        if s.startswith("[") and s.endswith("]"):
            aktuell = s
        elif aktuell == f"[{abschnitt}]" and not s.startswith("#") and s.split("=")[0].strip() == schluessel:
            zeilen[i] = f'{schluessel} = "{wert}"\n'
            ersetzt = True
            break
    if not ersetzt:
        raise ValueError(f"In config.toml fehlt [{abschnitt}] {schluessel} = ...")
    datei.write_text("".join(zeilen), encoding="utf-8")


def speichere_stufe(name: str, datei=None) -> None:
    speichere_wert("modell", "stufe", name, datei)


def speichere_modus(modus: str, datei=None) -> None:
    if modus not in MODI:
        raise ValueError(modus)
    speichere_wert("allgemein", "modus", modus, datei)
