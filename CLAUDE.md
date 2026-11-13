# whisper-diktat

Lokales Diktier-Tool für Windows: läuft im Hintergrund, nimmt per globalem Shortcut über das Mikrofon auf,
transkribiert lokal mit Whisper (OpenVINO) und fügt den Text dort ein, wo der Cursor steht. Audio verlässt den
Rechner nie.

**Soll das Tool installiert werden: `INSTALL.md` lesen und befolgen.**

## Regeln für Claude in diesem Projekt
- Antworten auf Deutsch.
- Rechnerspezifisches (Pfade, Hardware, Notizen) steht in `CLAUDE.local.md`, falls vorhanden. Nicht in Git.
- Projektwissen, Entscheidungen und Messergebnisse in `MEMORY.md` in diesem Ordner festhalten (nicht in Git),
  **nicht** im globalen Claude-Memory unter `~/.claude`.
- Keine echten Tastatureingaben (SendInput) in automatischen Tests: Sie landen im aktiven Fenster des Nutzers.
- Keine persönlichen Daten ins Repo: `config.toml`, `fachwoerter.txt`, `befehle.toml`, `textfelder.toml`,
  Aufnahmen, Logs und Notizen sind in `.gitignore`. Neue Standardwerte gehören in die Vorlagen
  `config.beispiel.toml` / `fachwoerter.beispiel.txt` / `befehle.beispiel.toml` / `textfelder.beispiel.toml`.

## Umgebung
- Python 3.12 in `%USERPROFILE%\.venvs\whisper` (Python selbst in `%USERPROFILE%\.venvs\python`), angelegt von
  `install.ps1`. Aufruf: `%USERPROFILE%\.venvs\whisper\Scripts\python.exe`
- Pakete: `requirements.txt` (Laufzeit), `requirements-test.txt` (Tests mit `--engine`). **`av<16` ist Pflicht**,
  weil av 16+ den Parameter `metadata_errors` entfernt hat, den faster-whisper 1.2.1 nutzt.
- Am schnellsten auf Intel-Grafik (Arc) oder NPU, sonst CPU.

## Aufbau
- `diktat/`: das Tool. Start im Projektordner: `python -m diktat`
  - `hotkey.py`: Win32 `WH_KEYBOARD_LL`-Hook, Push-to-Talk. Ereignisse press/release/cancel.
  - `recorder.py`: Mikrofon 16 kHz mono, nur während der Aufnahme offen
  - `engine.py`: OpenVINO-WhisperPipeline in einem **eigenen Prozess** (wegen GIL/Hook-Timeout und Treiberabstürzen)
  - `inserter.py`: Text tippen (SendInput Unicode) oder über die Zwischenablage einfügen
    sowie Tastenkombinationen drücken (`druecke`, für Sprachbefehle)
  - `befehle.py`: Sprachbefehle. „… Enter“ am Diktat-Ende drückt Enter (`[befehle] enter` in `config.toml`);
    ist das ganze Diktat ein Satz aus `befehle.toml` („öffne Outlook“, „rückgängig“), wird statt Text eine Aktion
    ausgeführt (Seite/Programm öffnen per `os.startfile` oder Tasten). Datei wird bei Änderung neu geladen.
    `[aktionen]` = eingebaute Aktionen (textfeld, textfeld_merken, textfeld_vergessen); „Textfeld, …“ als Vorsilbe.
  - `textfeld.py`: Sprachbefehl „Textfeld“ (Bewertung der Eingabefelder, Regeln in `textfelder.toml`, Aktionen)
  - `marker.py`: kurzes Bestätigungszeichen am Bildschirm (Haken/Kreuz, durchklickbar), Probe `python -m diktat.marker`
  - `uia.py`: Windows-Bedienungshilfe (UI Automation über comtypes) und Fensterabfragen, nur für `textfeld.py`.
    Chromium/Electron liefern beim ersten Zugriff keine Felder, deshalb wird beim Aufnahmestart vorgewärmt.
  - `tray.py`: Taskleisten-Symbol (pystray). Farben: blau = lädt, grau = bereit, rot = Aufnahme, gelb = transkribiert, schwarz = Fehler
  - `__main__.py`: App, Threads (Ereignisse, Transkription, Wartung, Aktionen = Ausgabe mit COM),
    Bereinigung von Halluzinationen,
    Log in `logs/diktat.log`, harte Abstürze in `logs/absturz.log`. Exit-Codes: 0 = Beenden, 3 = läuft schon, 4 = Neustart
  - `waechter.py`: startet das Tool neu, wenn es abstürzt (max. 5 Abstürze in 10 min), Log in `logs/waechter.log`
  - `autostart.py`: Aufgabe „whisper-diktat“ in der Windows-Aufgabenplanung (Anmeldung, Entsperren, alle 10 min),
    an/aus mit `python -m diktat.autostart an|aus|status`. Der alte HKCU\Run-Eintrag wird dabei entfernt.
  - `geraete.py`: vorhandene Recheneinheiten (OpenVINO `available_devices`) und Mikrofone (MME, Namen statt Nummern)
  - `config.py`: lädt `config.toml`/`fachwoerter.txt`/`befehle.toml`, legt sie beim ersten Zugriff aus den Vorlagen an
  - `einrichten.py`: Einrichtung nach der Paketinstallation (Dateien, Geräte, Modell, Verknüpfungen, Autostart)
- `docs/SPRACHBEFEHLE.md`: Anleitung für Nutzer (Befehle, eigene Einträge). Bei neuen Befehlen mitpflegen.
- `install.ps1`: komplette Installation für den aktuellen Benutzer, siehe `INSTALL.md`.
- `start.pyw` → Wächter → Tool. Die Verknüpfung `Whisper Diktat starten.lnk` legt `einrichten.py` an.
- `config.toml`: Shortcut, `[modell] name` (turbo/large-v3) + `geraet` (auto/GPU/NPU/CPU), `mikrofon` ("" = Windows-
  Standard), Einfügemodus. Alte Dateien mit `[modell] stufe` werden beim Laden übersetzt. `fachwoerter.txt`: initial_prompt.
- `tests/`: `test_kern`, `test_befehle`, `test_textfeld`, `test_phase2 [--engine]`, `test_phase3`,
  `test_phase4 [--engine]`, `test_autostart`, `test_geraete`, `test_einrichten` (jeweils `python -m tests.<name>`), ohne echte Tastatureingaben. Außerdem
  `mikro_probe` (Stille-Messung am Mikrofon) und `textfeld_probe [--prozess name]` (welche Eingabefelder das
  Tool in einem Fenster sieht, nur lesend). Achtung: test_phase3 schreibt in `logs/waechter.log`.
  `--engine` braucht `requirements-test.txt` und eine eigene Testaufnahme `whisper-test/test_de.wav` (nicht in Git).

## Laufende Instanz
- Beenden für ein Update: Menü „Beenden“ (Exit 0, der Wächter endet mit), oder alle python-Prozesse hart beenden,
  deren Befehlszeile `diktat`, `start.pyw` oder `multiprocessing-fork` enthält.
- Unabhängig starten: `schtasks /Run /TN whisper-diktat` (wenn Autostart an) oder die Verknüpfung per `explorer.exe`.

## Versionsstand (Git)
- `main` = stabiler Stand, Tags `v0.x`. Neue Arbeit auf eigenen Branches, erst nach dem Praxistest mergen.
- Zurückgehen: `git switch main` (oder `git checkout <tag>`), danach das Tool neu starten.

## Fallstricke
- Sehr lange Pfade (über 260 Zeichen) brechen pip/uv-Installationen. Umgebungen deshalb unter kurzen Pfaden anlegen.
- Strg+Y ist in vielen Programmen für „Wiederholen“ belegt; solange das Tool läuft, bekommt das Programm es nicht.
- Virenscanner können das Tool wegen Tastatur-Hook + SendInput als Keylogger einstufen.
