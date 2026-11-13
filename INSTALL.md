# Installation von whisper-diktat

Diese Anleitung ist für Menschen **und** für KI-Assistenten (z. B. Claude Code) geschrieben. Wer Claude bittet,
„installier mir das“, kann Claude einfach auf diese Datei verweisen.

## Kurzfassung

Im Projektordner in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Das dauert beim ersten Mal 5–15 Minuten (Download ca. 2–3 GB). Am Ende steht **`INSTALLATION OK`**, und unten
rechts in der Taskleiste erscheint ein Mikrofon-Symbol. Danach: **Strg+Y halten, sprechen, loslassen.**

## Voraussetzungen

| | Empfohlen | Mindestens |
|---|---|---|
| Betriebssystem | Windows 11 | Windows 10, 64 Bit |
| Prozessor/Grafik | Intel Core Ultra mit Arc-Grafik | x86-64-CPU mit AVX2 (dann deutlich langsamer) |
| Arbeitsspeicher | 16 GB | 8 GB |
| Speicherplatz | 5 GB frei auf dem Laufwerk des Benutzerordners | |
| Internet | nur für die Installation | |
| Rechte | normaler Benutzer, **keine Adminrechte nötig** | |

## Was install.ps1 macht

1. Prüft Windows, Arbeitsspeicher und freien Platz.
2. Sucht **uv** (Python-Paketmanager). Fehlt es, installiert es uv von <https://astral.sh/uv> in den Benutzerordner.
3. Installiert **Python 3.12** nach `%USERPROFILE%\.venvs\python` und legt die Umgebung
   `%USERPROFILE%\.venvs\whisper` an. Kurze Pfade mit Absicht, weil Windows bei über 260 Zeichen scheitert.
4. Installiert die Pakete aus `requirements.txt`.
5. Ruft `python -m diktat.einrichten` auf:
   - legt `config.toml`, `fachwoerter.txt`, `befehle.toml` und `textfelder.toml` aus den Vorlagen an (bestehende bleiben unverändert),
   - zeigt die gefundenen Recheneinheiten (Grafik/NPU/CPU) und Mikrofone,
   - lädt das Whisper-Modell von Hugging Face (ca. 1–2 GB, einmalig),
   - legt die Verknüpfung „Whisper Diktat starten“ im Projektordner und auf dem Desktop an,
   - schaltet den Autostart ein: Aufgabe „whisper-diktat“ in der Windows-Aufgabenplanung.
6. Startet das Tool.

Optionen: `-OhneAutostart`, `-OhneVerknuepfung`, `-NichtStarten`, `-MitTests` (Testpakete),
`-Venv <Pfad>` (andere Umgebung), `-Desktop <Ordner>`, `-Uv <Pfad zu uv.exe>`.
Das Skript darf mehrfach laufen, zum Beispiel nach einem Update. Persönliche Einstellungen bleiben dabei erhalten.
Es installiert dabei auch neue Pakete (z. B. `comtypes` für „Textfeld“, `sv-ttk` für das Einstellungsfenster).

Nach der Installation: Klick auf das Symbol in der Taskleiste öffnet die Einstellungen.

## Ohne GitHub: Installation aus der ZIP-Datei

Wer keinen GitHub-Zugang hat, bekommt eine ZIP-Datei (z. B. `whisper-diktat-v0.8.zip`). Sie enthält dasselbe
wie das Repo, nur ohne Git:

1. Die ZIP in einen kurzen Pfad entpacken, z. B. `%USERPROFILE%\Desktop\whisper-diktat`. Nicht in einen
   OneDrive-Ordner, sonst synchronisiert OneDrive Logs und Cache mit.
2. Im entpackten Ordner wie oben `install.ps1` ausführen.

## Update

Vorher das Tool beenden: Rechtsklick auf das Symbol → „Beenden“. Dann:

- **Mit Git:** `git pull`
- **Mit ZIP:** die neue ZIP über den bestehenden Ordner entpacken und vorhandene Dateien ersetzen. Die
  persönlichen Dateien `config.toml`, `fachwoerter.txt`, `befehle.toml` und `textfelder.toml` sind nicht in der ZIP und bleiben erhalten.

Danach erneut ausführen:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

## Deinstallation

1. Rechtsklick auf das Symbol → „Beenden“.
2. Autostart entfernen:
   `& "$env:USERPROFILE\.venvs\whisper\Scripts\python.exe" -m diktat.autostart aus` (im Projektordner)
3. Ordner löschen:
   1. den Projektordner,
   2. `%USERPROFILE%\.venvs\whisper`,
   3. die Desktop-Verknüpfung,
   4. optional die Modelle unter `%USERPROFILE%\.cache\huggingface\hub\models--OpenVINO--whisper-*`.

---

## Für KI-Assistenten (Claude Code o. Ä.)

Wenn der Nutzer dich bittet, whisper-diktat zu installieren:

1. **Vorher kurz sagen, was passiert, und das OK abwarten:**
   - uv und Python 3.12 kommen in den Benutzerordner;
   - ca. 2–3 GB Download;
   - eine Aufgabe in der Aufgabenplanung (Autostart);
   - eine Verknüpfung auf dem Desktop;
   - das Tool hört global auf **Strg+Y**: In anderen Programmen geht Strg+Y („Wiederholen“) nicht mehr, solange es läuft.
2. **Im Projektordner ausführen** (Laufzeit bis 15 min, deshalb mit langem Timeout oder im Hintergrund):
   ```powershell
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```
3. **Erfolg prüfen:**
   - Die Ausgabe enthält `EINRICHTUNG OK` und `INSTALLATION OK`.
   - `schtasks /Query /TN whisper-diktat` findet die Aufgabe.
   - Nach ca. 10–30 s steht in `logs\diktat.log` eine Zeile `Modell … geladen`.
   - Im Abschnitt „Geräte“ der Ausgabe steht, welche Recheneinheit genutzt wird. Steht dort der Hinweis
     „Keine Intel-Grafik“, dem Nutzer sagen, dass ein Diktat einige Sekunden dauert.
4. **Den Nutzer bitten, es selbst auszuprobieren:** In ein Textfeld klicken, Strg+Y halten, sprechen, loslassen.
   **Keine echten Tastatureingaben simulieren:** Sie würden im aktiven Fenster des Nutzers landen.

**Regeln:**
- `config.toml`, `fachwoerter.txt`, `befehle.toml` und `textfelder.toml` gehören dem Nutzer. Nicht überschreiben, nur auf Wunsch ändern.
- Keine Adminrechte anfordern. Es ist keine nötig.
- Nichts außerhalb von Projektordner, `%USERPROFILE%\.venvs`, Hugging-Face-Cache, Desktop-Verknüpfung und
  Aufgabe „whisper-diktat“ anlegen.

**Typische Fehler:**

| Meldung / Symptom | Ursache und Abhilfe |
|---|---|
| „Ausführung von Skripts ist deaktiviert“ | Mit `powershell -ExecutionPolicy Bypass -File install.ps1` aufrufen (gilt nur für diesen Aufruf) |
| uv-Download blockiert (Proxy/Firewall) | uv von Hand installieren und `-Uv <Pfad>` angeben, oder die IT fragen |
| Paketinstallation bricht mit Pfadfehler ab | Pfad zu lang: `-Venv C:\venvs\whisper` o. Ä. verwenden |
| Modell-Download scheitert | Zugriff auf `huggingface.co` nötig. Später erneut `install.ps1` ausführen |
| Virenscanner schlägt an / Tool wird beendet | Tastatur-Hook + Texteingabe sehen aus wie ein Keylogger. Die IT muss den Projektordner und `pythonw.exe` der Umgebung freigeben |
| Symbol schwarz | `logs\diktat.log` lesen. Häufig: Grafiktreiber. Im Menü Recheneinheit „CPU“ wählen |
| Läuft eine Claude-Sitzung in einer Sandbox, die `AppData\Roaming` oder die Registry umleitet | `install.ps1` in einem echten Terminal-Fenster laufen lassen |
| Tool beendet sich, wenn das Terminal geschlossen wird | Nicht mit `python -m diktat` aus dem Terminal starten, sondern über die Verknüpfung oder `schtasks /Run /TN whisper-diktat` |
