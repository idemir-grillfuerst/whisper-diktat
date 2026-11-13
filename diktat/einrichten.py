"""Einrichtung nach der Installation der Pakete (wird von install.ps1 aufgerufen, geht auch von Hand).

  python -m diktat.einrichten [--ohne-modell] [--ohne-verknuepfung] [--ohne-autostart] [--desktop PFAD]

Schritte:
  1. config.toml und fachwoerter.txt aus den Vorlagen anlegen (bestehende bleiben unverändert)
  2. Recheneinheiten und Mikrofone anzeigen
  3. Das eingestellte Modell herunterladen (ca. 1–2 GB, nur beim ersten Mal)
  4. Verknüpfung „Whisper Diktat starten“ im Projektordner und auf dem Desktop anlegen
  5. Autostart einschalten (Aufgabe „whisper-diktat“ in der Aufgabenplanung, ohne Adminrechte)
Am Ende steht „EINRICHTUNG OK“ oder eine Fehlermeldung (Exit-Code 0 bzw. 1).
"""
import argparse
import subprocess
import sys
from pathlib import Path

from . import PROJEKT

VERKNUEPFUNG = "Whisper Diktat starten.lnk"
CREATE_NO_WINDOW = 0x08000000


def _ps_text(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def desktop_ordner() -> Path:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                       capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    return Path(r.stdout.strip() or Path.home() / "Desktop")


def verknuepfung_anlegen(ziel: Path, pythonw: str, start: Path, ordner: Path) -> None:
    """Windows-Verknüpfung (.lnk) über WScript.Shell, ohne Zusatzpakete."""
    skript = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut({lnk}); "
        "$s.TargetPath = {exe}; $s.Arguments = {arg}; $s.WorkingDirectory = {ordner}; "
        "$s.Description = 'whisper-diktat: lokales Diktier-Tool (Strg+Y)'; "
        "$s.IconLocation = 'shell32.dll,138'; $s.Save()"
    ).format(lnk=_ps_text(ziel), exe=_ps_text(pythonw), arg=_ps_text(f'"{start}"'), ordner=_ps_text(ordner))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", skript], capture_output=True, text=True,
                       creationflags=CREATE_NO_WINDOW)
    if r.returncode != 0 or not ziel.exists():
        raise OSError(f"Verknüpfung {ziel} konnte nicht angelegt werden: {r.stderr.strip()}")


def modell_laden(repo: str) -> str:
    from huggingface_hub import snapshot_download
    try:
        return snapshot_download(repo, local_files_only=True)
    except Exception:  # noqa: BLE001 – noch nicht im Cache
        print(f"  lade {repo} herunter (einmalig, ca. 1–2 GB) …", flush=True)
        return snapshot_download(repo)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ohne-modell", action="store_true", help="Modell nicht herunterladen")
    p.add_argument("--ohne-verknuepfung", action="store_true", help="keine Verknüpfungen anlegen")
    p.add_argument("--ohne-autostart", action="store_true", help="Autostart nicht einschalten")
    p.add_argument("--desktop", type=Path, help="Ordner für die Desktop-Verknüpfung (Standard: echter Desktop)")
    a = p.parse_args(argv)

    from .config import CONFIG_DATEI, lade_config, persoenliche_dateien_anlegen
    from .waechter import pythonw

    print("[1/5] Persönliche Dateien")
    neu = persoenliche_dateien_anlegen()
    for d in (CONFIG_DATEI, PROJEKT / "fachwoerter.txt"):
        print(f"  {d.name}: {'neu aus Vorlage angelegt' if d in neu else 'vorhanden, unverändert'}")
    cfg = lade_config()

    print("[2/5] Geräte")
    from . import geraete
    einheiten = geraete.recheneinheiten()
    for gid, name in einheiten:
        print(f"  Recheneinheit {gid}: {name}")
    gewaehlt = geraete.loese_geraet(cfg.geraet, einheiten)
    print(f"  -> genutzt wird: {gewaehlt} (Einstellung: {cfg.geraet})")
    if not any(g.startswith("GPU") for g, _ in einheiten):
        print("  HINWEIS: Keine Intel-Grafik gefunden. Whisper läuft auf der CPU, ein Diktat dauert dann einige Sekunden.")
    mics = geraete.mikrofone()
    for m in mics:
        print(f"  Mikrofon: {m}")
    if not mics:
        print("  WARNUNG: Kein Mikrofon gefunden. Mikrofon anschließen und in Windows als Eingabegerät freigeben.")

    print("[3/5] Modell")
    modell = cfg.modelle[cfg.modell]
    if a.ohne_modell:
        print("  übersprungen")
    else:
        pfad = modell_laden(modell.repo)
        print(f"  {modell.titel}: bereit ({pfad})")

    print("[4/5] Verknüpfungen")
    if a.ohne_verknuepfung:
        print("  übersprungen")
    else:
        exe, start = pythonw(), PROJEKT / "start.pyw"
        for ordner in (PROJEKT, a.desktop or desktop_ordner()):
            ziel = ordner / VERKNUEPFUNG
            verknuepfung_anlegen(ziel, exe, start, PROJEKT)
            print(f"  {ziel}")

    print("[5/5] Autostart")
    if a.ohne_autostart:
        print("  übersprungen")
    else:
        from . import autostart
        autostart.aktivieren()
        print(f"  Aufgabe '{autostart.AUFGABE}' in der Aufgabenplanung: {'AN' if autostart.ist_aktiv() else 'FEHLT'}")
        if not autostart.ist_aktiv():
            print("FEHLER: Autostart konnte nicht eingerichtet werden.")
            return 1

    print("EINRICHTUNG OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
