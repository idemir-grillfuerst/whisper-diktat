"""Einstellungen (config.toml) und Fachwortliste (fachwoerter.txt) laden.

Beide Dateien sind persönlich und nicht in Git. Im Repo liegen nur die Vorlagen config.beispiel.toml und
fachwoerter.beispiel.txt. Fehlt eine persönliche Datei, wird sie beim ersten Zugriff aus der Vorlage angelegt.
"""
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import PROJEKT

CONFIG_DATEI = PROJEKT / "config.toml"
FACHWORT_DATEI = PROJEKT / "fachwoerter.txt"
VORLAGEN = {
    CONFIG_DATEI: PROJEKT / "config.beispiel.toml",
    FACHWORT_DATEI: PROJEKT / "fachwoerter.beispiel.txt",
}


def aus_vorlage(datei: Path, vorlage: Path | None = None) -> bool:
    """Legt `datei` aus ihrer Vorlage an, falls sie fehlt. True = neu angelegt."""
    vorlage = vorlage or VORLAGEN.get(datei)
    if datei.exists() or vorlage is None or not vorlage.exists():
        return False
    shutil.copyfile(vorlage, datei)
    return True


def persoenliche_dateien_anlegen() -> list[Path]:
    """config.toml und fachwoerter.txt aus den Vorlagen anlegen, soweit sie fehlen."""
    return [d for d in VORLAGEN if aus_vorlage(d)]

MODI = ("halten", "umschalten", "beides")

# Bis v0.5 gab es „Stufen“ (Modell + Gerät fest gekoppelt). Ältere config.toml werden so übersetzt:
ALTE_STUFEN = {
    "schnell": ("turbo", "GPU"),
    "leise": ("turbo", "NPU"),
    "genau": ("large-v3", "GPU"),
    "notfall": ("turbo", "CPU"),
}
STANDARD_MODELLE = {
    "turbo": ("Turbo – schnell", "OpenVINO/whisper-large-v3-turbo-int8-ov"),
    "large-v3": ("Large-v3 – genau", "OpenVINO/whisper-large-v3-int8-ov"),
}


@dataclass
class Modell:
    name: str
    titel: str
    repo: str


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
    mikrofon: str              # "" = Windows-Standard
    mikrofon_offen_halten: bool
    modell: str                # Schlüssel in modelle
    geraet: str                # "auto", "GPU", "NPU", "CPU", "GPU.0" …
    modelle: dict


def lade_config(datei=None) -> Config:
    if datei is None:
        aus_vorlage(CONFIG_DATEI)
    raw = tomllib.loads((datei or CONFIG_DATEI).read_text(encoding="utf-8"))
    a = raw.get("allgemein", {})
    m = raw.get("modell", {})

    if raw.get("modelle"):
        modelle = {n: Modell(n, s.get("titel", n), s["repo"]) for n, s in raw["modelle"].items()}
    else:
        modelle = {n: Modell(n, t, r) for n, (t, r) in STANDARD_MODELLE.items()}

    if "name" in m:
        modell, geraet = m["name"], m.get("geraet", "auto")
    else:  # alte Datei mit [modell] stufe = "..."
        modell, geraet = ALTE_STUFEN.get(m.get("stufe", "schnell"), ("turbo", "auto"))
    if modell not in modelle:
        raise ValueError(f"Modell '{modell}' fehlt in config.toml unter [modelle.*]")

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
        mikrofon=str(a.get("mikrofon", "")),
        mikrofon_offen_halten=bool(a.get("mikrofon_offen_halten", False)),
        modell=modell,
        geraet=str(geraet),
        modelle=modelle,
    )


def fachwort_prompt(max_zeichen: int = 600) -> str | None:
    """Baut aus fachwoerter.txt den initial_prompt für Whisper (oder None, wenn leer)."""
    aus_vorlage(FACHWORT_DATEI)
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


def _toml_text(wert: str) -> str:
    return '"' + wert.replace("\\", "\\\\").replace('"', '\\"') + '"'


def speichere_wert(abschnitt: str, schluessel: str, wert: str, datei=None) -> None:
    """Setzt in config.toml `schluessel = "wert"` im Abschnitt [abschnitt]. Fehlt die Zeile, wird sie am Ende des
    Abschnitts ergänzt. Kommentare und alles andere bleiben unverändert."""
    datei = datei or CONFIG_DATEI
    zeilen = datei.read_text(encoding="utf-8").splitlines(keepends=True)
    neu = f"{schluessel} = {_toml_text(wert)}\n"
    aktuell, ende_abschnitt = None, None
    for i, z in enumerate(zeilen):
        s = z.strip()
        if s.startswith("[") and s.endswith("]"):
            if aktuell == f"[{abschnitt}]" and ende_abschnitt is None:
                ende_abschnitt = i
            aktuell = s
        elif aktuell == f"[{abschnitt}]" and not s.startswith("#") and s.split("=")[0].strip() == schluessel:
            zeilen[i] = neu
            break
    else:
        if aktuell == f"[{abschnitt}]" and ende_abschnitt is None:
            ende_abschnitt = len(zeilen)
        if ende_abschnitt is None:
            raise ValueError(f"In config.toml fehlt der Abschnitt [{abschnitt}]")
        while ende_abschnitt > 0 and not zeilen[ende_abschnitt - 1].strip():
            ende_abschnitt -= 1  # vor der Leerzeile zum nächsten Abschnitt einfügen
        if ende_abschnitt > 0 and not zeilen[ende_abschnitt - 1].endswith("\n"):
            zeilen[ende_abschnitt - 1] += "\n"
        zeilen.insert(ende_abschnitt, neu)
    datei.write_text("".join(zeilen), encoding="utf-8")


def speichere_modell(name: str, datei=None) -> None:
    speichere_wert("modell", "name", name, datei)


def speichere_geraet(geraet: str, datei=None) -> None:
    speichere_wert("modell", "geraet", geraet, datei)


def speichere_mikrofon(name: str, datei=None) -> None:
    speichere_wert("allgemein", "mikrofon", name, datei)


def speichere_modus(modus: str, datei=None) -> None:
    if modus not in MODI:
        raise ValueError(modus)
    speichere_wert("allgemein", "modus", modus, datei)
