"""Tests für Vorlagen, Einrichtung und Verknüpfungen (portable Installation).
Verändert weder config.toml noch fachwoerter.txt, legt keine Verknüpfung auf dem Desktop an, kein Autostart.

Aufruf (im Projektordner):  %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_einrichten
"""
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from diktat import PROJEKT, einrichten
from diktat.config import VORLAGEN, aus_vorlage, lade_config
from diktat.waechter import pythonw

FEHLER = []


def pruefe(name, bedingung):
    print(("OK    " if bedingung else "FEHLER"), name)
    if not bedingung:
        FEHLER.append(name)


def test_vorlagen():
    for datei, vorlage in VORLAGEN.items():
        pruefe(f"Vorlage {vorlage.name} ist vorhanden", vorlage.exists())
    vorlage = PROJEKT / "config.beispiel.toml"
    cfg = lade_config(vorlage)
    pruefe("config.beispiel.toml lädt: Turbo, auto, Windows-Standard-Mikrofon",
           cfg.modell == "turbo" and cfg.geraet == "auto" and cfg.mikrofon == "" and cfg.shortcut == "ctrl+y")
    raw = tomllib.loads(vorlage.read_text(encoding="utf-8"))
    pruefe("Vorlage enthält beide Modelle", set(raw["modelle"]) == {"turbo", "large-v3"})
    fach = (PROJEKT / "fachwoerter.beispiel.txt").read_text(encoding="utf-8")
    pruefe("Fachwort-Vorlage ohne Firmenbegriffe", not any(w in fach for w in ("Grillfürst", "Plenty", "3CX")))


def test_aus_vorlage():
    with tempfile.TemporaryDirectory() as d:
        ziel, vorlage = Path(d) / "x.toml", Path(d) / "x.beispiel.toml"
        vorlage.write_text("a = 1\n", encoding="utf-8")
        pruefe("Fehlende Datei wird aus Vorlage angelegt", aus_vorlage(ziel, vorlage) and ziel.read_text() == "a = 1\n")
        ziel.write_text("a = 2\n", encoding="utf-8")
        pruefe("Vorhandene Datei bleibt unverändert", not aus_vorlage(ziel, vorlage) and ziel.read_text() == "a = 2\n")
        pruefe("Ohne Vorlage passiert nichts", not aus_vorlage(Path(d) / "y.toml", Path(d) / "fehlt.toml"))


def test_verknuepfung():
    with tempfile.TemporaryDirectory() as d:
        lnk = Path(d) / einrichten.VERKNUEPFUNG
        einrichten.verknuepfung_anlegen(lnk, pythonw(), PROJEKT / "start.pyw", PROJEKT)
        pruefe("Verknüpfung wird angelegt", lnk.exists())
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); "
                            "$s.TargetPath; $s.Arguments; $s.WorkingDirectory"],
                           capture_output=True, text=True, encoding="oem", errors="replace")
        ziel, argumente, ordner = (r.stdout.strip().splitlines() + ["", "", ""])[:3]
        pruefe("Verknüpfung zeigt auf pythonw.exe der Umgebung", Path(ziel).resolve() == Path(pythonw()).resolve())
        pruefe("Verknüpfung startet start.pyw", "start.pyw" in argumente)
        pruefe("Arbeitsordner = Projektordner", Path(ordner).resolve() == PROJEKT.resolve())


def test_einrichten_ohne_eingriffe():
    vorher = {d: d.read_bytes() for d in VORLAGEN if d.exists()}
    r = subprocess.run([sys.executable, "-m", "diktat.einrichten", "--ohne-modell", "--ohne-verknuepfung",
                        "--ohne-autostart"], cwd=PROJEKT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    pruefe("einrichten läuft durch (EINRICHTUNG OK)", r.returncode == 0 and "EINRICHTUNG OK" in r.stdout)
    pruefe("einrichten zeigt Recheneinheiten", "Recheneinheit" in r.stdout)
    pruefe("Vorhandene persönliche Dateien unverändert",
           all(d.read_bytes() == inhalt for d, inhalt in vorher.items()))
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])


def test_keine_festen_pfade():
    dateien = [PROJEKT / "start.pyw", PROJEKT / "install.ps1", *PROJEKT.glob("diktat/*.py"), *PROJEKT.glob("tests/*.py")]
    treffer = [p.name for p in dateien if p.name != "test_einrichten.py"
               and ("C:\\Users\\" in p.read_text(encoding="utf-8-sig") or "C:\\\\Users\\\\" in p.read_text(encoding="utf-8-sig"))]
    pruefe(f"Keine festen Benutzerpfade im Code {treffer or ''}", not treffer)


if __name__ == "__main__":
    test_vorlagen()
    test_aus_vorlage()
    test_verknuepfung()
    test_einrichten_ohne_eingriffe()
    test_keine_festen_pfade()
    print("\nALLES OK" if not FEHLER else f"\n{len(FEHLER)} FEHLER: {FEHLER}")
    sys.exit(1 if FEHLER else 0)
