# whisper-diktat

Lokales Diktier-Tool für Windows: läuft im Hintergrund, nimmt per globalem Shortcut über das Mikrofon auf,
transkribiert lokal mit Whisper und fügt den Text dort ein, wo der Cursor steht. Audio verlässt den Laptop nie.

## Regeln für Claude in diesem Projekt
- Antworten auf Deutsch.
- Projektwissen, Entscheidungen und Messergebnisse in `MEMORY.md` in diesem Ordner festhalten,
  **nicht** im globalen Claude-Memory unter `~/.claude`.
- Alles Projektbezogene liegt in diesem Ordner. Ausnahme: die Python-Umgebung (siehe unten).

## Umgebung
- Laptop: HP EliteBook 8 G1i, Intel Core Ultra 7 255H (16 Kerne), 64 GB RAM, Intel Arc 140T (iGPU),
  NPU „Intel AI Boost“, keine NVIDIA-Karte (kein CUDA).
- Mikrofon: Yealink WDD60 Headset (Windows-Standardeingang).
- Python-Umgebung: `%USERPROFILE%\.venvs\whisper` (Python 3.12 aus `%USERPROFILE%\.venvs\python`).
  Aufruf: `%USERPROFILE%\.venvs\whisper\Scripts\python.exe`
- Pakete: siehe `requirements.txt`. **`av<16` ist Pflicht**, weil av 16+ den Parameter `metadata_errors`
  entfernt hat, den faster-whisper 1.2.1 nutzt.
- uv: `%USERPROFILE%\AppData\Local\hermes\bin\uv.exe`

## Aufbau
- `diktat/`: das Tool. Start im Projektordner: `%USERPROFILE%\.venvs\whisper\Scripts\python.exe -m diktat`
  - `hotkey.py`: Win32 `WH_KEYBOARD_LL`-Hook, Push-to-Talk. Ereignisse press/release/cancel.
  - `recorder.py`: Mikrofon 16 kHz mono, nur während der Aufnahme offen
  - `engine.py`: OpenVINO-WhisperPipeline in einem **eigenen Prozess** (wegen GIL/Hook-Timeout und Treiberabstürzen)
  - `inserter.py`: Text tippen (SendInput Unicode) oder über die Zwischenablage einfügen
  - `tray.py`: Taskleisten-Symbol (pystray). Farben: blau = lädt, grau = bereit, rot = Aufnahme, gelb = transkribiert, schwarz = Fehler
  - `__main__.py`: App, Threads (Ereignisse, Transkription, Wartung), Bereinigung von Halluzinationen,
    Log in `logs/diktat.log`, harte Abstürze in `logs/absturz.log`. Exit-Codes: 0 = Beenden, 3 = läuft schon, 4 = Neustart
  - `waechter.py`: startet das Tool neu, wenn es abstürzt (max. 5 Abstürze in 10 min), Log in `logs/waechter.log`
  - `autostart.py`: Aufgabe „whisper-diktat“ in der Windows-Aufgabenplanung (Anmeldung, Entsperren, alle 10 min),
    an/aus mit `python -m diktat.autostart an|aus|status`. Der alte HKCU\Run-Eintrag wird dabei entfernt.
    Aus einer Claude-Sitzung starten: `schtasks /Run /TN whisper-diktat` (läuft dann unabhängig von der App).
- Normaler Start: `Whisper Diktat starten.lnk` (→ `start.pyw` → Wächter). Zum Entwickeln: `python -m diktat` im Terminal.
- Aus einer Claude-Sitzung unabhängig starten: `explorer.exe "%USERPROFILE%\Desktop\whisper-diktat\Whisper Diktat starten.lnk"`.
  Ein Start aus einem Terminal-Tab heraus stirbt, sobald der Tab geschlossen wird.
- Laufende Instanz für ein Update beenden: Menü „Beenden“ (Exit 0, der Wächter endet mit), oder alle python-Prozesse
  hart beenden, deren Befehlszeile `diktat`, `start.pyw` oder `multiprocessing-fork` enthält.
- `config.toml`: Shortcut, Stufen (Modell + Gerät), Einfügemodus. `fachwoerter.txt`: initial_prompt.
- `tests/`: `test_kern`, `test_phase2 [--engine]`, `test_phase3`, `test_phase4 [--engine]`, `test_autostart` (jeweils `python -m tests.<name>`), ohne echte
  Tastatureingaben. Außerdem `mikro_probe` (Stille-Messung am Mikrofon). Achtung: test_phase3 schreibt in `logs/waechter.log`.
- `whisper-test/`: frühere Experimente und Benchmarks.
- Keine echten Tastatureingaben (SendInput) in automatischen Tests: Sie landen im aktiven Fenster des Nutzers.

## Versionsstand (Git)
- `main` = stabiler Stand. Tag `v0.3` = Phase 1–3 fertig. Neue Arbeit auf eigenen Branches, erst nach dem Praxistest mergen.
- Nicht in Git: `.ov_cache/`, `logs/`, `aufnahmen/`, `*.wav` (Sprachaufnahmen bleiben lokal).
- Zurückgehen: `git switch main` (oder `git checkout v0.3`), danach das Tool neu starten (siehe oben).

## Fallstricke
- Die Claude-App leitet Schreibzugriffe auf `AppData\Roaming` in einen privaten Bereich um. Ein Python, das dort
  von uv installiert wurde, ist im normalen Terminal unsichtbar. Python deshalb immer mit
  `UV_PYTHON_INSTALL_DIR=%USERPROFILE%\.venvs\python` installieren.
- Sehr lange Pfade (über 260 Zeichen) brechen pip/uv-Installationen. Umgebungen deshalb unter kurzen Pfaden anlegen.
- Strg+Y ist in vielen Programmen für „Wiederholen“ belegt und taugt nicht als Shortcut.
