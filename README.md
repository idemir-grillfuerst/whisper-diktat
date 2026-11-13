# whisper-diktat

Lokales Diktier-Tool für Windows. **Strg+Y halten, sprechen, loslassen**: Der gesprochene Text erscheint dort,
wo der Cursor steht, ob in Outlook, Teams, im Browser oder in jedem anderen Textfeld.

Die Spracherkennung läuft mit [OpenAI Whisper](https://github.com/openai/whisper) **komplett auf dem eigenen
Rechner**. Die Aufnahme verlässt den Laptop nie, es gibt keine Cloud und keine Kosten pro Minute.

**Autor:** Ismail Demir  
Entwickelt mit Unterstützung von Claude (Anthropic).

---

## Was es kann

- **Push-to-Talk:** Strg+Y gedrückt halten = Aufnahme, loslassen = Text wird eingefügt.
- **Daueraufnahme:** Strg+Y kurz antippen = Aufnahme läuft, bis du nochmal tippst (max. 5 Minuten).
- **Schnell:** Mit der Intel-Arc-Grafik ist ein Diktat von 5–10 Sekunden in 0,3–1 Sekunde fertig.
- **Fachwörter:** Eine eigene Wortliste (`fachwoerter.txt`) sorgt dafür, dass Namen und Fachbegriffe richtig
  geschrieben werden.
- **Läuft im Hintergrund:** Symbol in der Taskleiste, startet mit Windows und kommt nach Abstürzen, Standby
  und Ruhezustand von selbst wieder.
- **Schutz vor Whisper-Fehlern:** Typische Halluzinationen („Untertitelung des ZDF“) und Wiederholungsschleifen
  werden erkannt und nicht eingefügt.

## Voraussetzungen

| | Empfohlen | Mindestens |
|---|---|---|
| Betriebssystem | Windows 11 | Windows 10 (64 Bit) |
| Prozessor/Grafik | Intel Core Ultra mit Arc-Grafik | x86-64-CPU mit AVX2 (Stufe „Notfall“, deutlich langsamer) |
| Arbeitsspeicher | 16 GB | 8 GB |
| Speicherplatz | ca. 5 GB (Python, Modelle, Cache) | ca. 3 GB (nur ein Modell) |
| Mikrofon | Headset | eingebautes Mikrofon |

Die Stufen „Schnell“, „Leise“ und „Genau“ nutzen Intels OpenVINO und laufen am besten auf **Intel**-Grafik bzw.
NPU. Auf Rechnern ohne Intel-Grafik bleibt nur die CPU-Stufe.

## Installation

> **Stand heute:** Die Installation ist noch Handarbeit und auf den Entwickler-Laptop zugeschnitten.
> Ein Installer bzw. eine fertige `.exe` für Kollegen ist noch nicht gebaut. Siehe „Weitergabe an Kollegen“ unten.

1. **uv installieren** (Python-Paketmanager): <https://docs.astral.sh/uv/>
2. **Python 3.12 und Umgebung anlegen.** Die Umgebung bewusst unter einem kurzen Pfad anlegen, damit Windows
   nicht an der Pfadlänge scheitert:
   ```powershell
   $env:UV_PYTHON_INSTALL_DIR = "$env:USERPROFILE\.venvs\python"
   uv python install 3.12
   uv venv --python 3.12 "$env:USERPROFILE\.venvs\whisper"
   uv pip install --python "$env:USERPROFILE\.venvs\whisper\Scripts\python.exe" -r requirements.txt
   ```
3. **Einmal von Hand starten** (lädt beim ersten Mal das Modell herunter, ca. 1,6 GB):
   ```powershell
   & "$env:USERPROFILE\.venvs\whisper\Scripts\python.exe" -m diktat
   ```
   Unten rechts erscheint ein Mikrofon-Symbol: blau = lädt, grau = bereit.
4. **Autostart einschalten:** Rechtsklick auf das Symbol → „Mit Windows starten“. Das Tool legt dann die
   Aufgabe „whisper-diktat“ in der Windows-Aufgabenplanung an. Sie startet das Tool bei der Anmeldung, beim
   Entsperren und alle 10 Minuten, falls es nicht läuft. Adminrechte sind nicht nötig.

## Bedienung

| Aktion | Was passiert |
|---|---|
| Strg+Y **halten** | Aufnahme (Symbol rot), beim Loslassen wird transkribiert (gelb) und eingefügt |
| Strg+Y **kurz tippen** | Daueraufnahme startet, nochmal tippen = fertig |
| Rechtsklick auf das Symbol | Menü: Pausieren, Stufe, Bedienung, Fachwörter, Einstellungen, Log, Autostart, Beenden |

Solange das Tool läuft, ist Strg+Y in anderen Programmen nicht als „Wiederholen“ verfügbar. Pausieren gibt
die Taste frei. Der Shortcut ist in `config.toml` änderbar.

### Stufen

| Stufe | Modell | Gerät | Wofür |
|---|---|---|---|
| Schnell | large-v3-turbo (int8) | Intel-Grafik | Standard |
| Leise | large-v3-turbo (int8) | NPU | sparsam, Lüfter bleibt ruhig. Das erste Laden dauert einige Minuten |
| Genau | large-v3 (int8) | Intel-Grafik | schwierige Aufnahmen, etwas langsamer |
| Notfall | large-v3-turbo (int8) | CPU | wenn die Grafik Probleme macht |

### Symbolfarben

blau = lädt · grau = bereit · rot = Aufnahme · gelb = transkribiert · durchgestrichen = pausiert ·
Mond = Modell im Leerlauf entladen (lädt beim nächsten Diktat nach) · schwarz = Fehler (siehe Log)

## Einstellungen

`config.toml` (Menü → „Einstellungen öffnen“, wirkt nach einem Neustart):

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `shortcut` | `ctrl+y` | z. B. `ctrl+alt+space`, `f9`, `ctrl+shift` |
| `modus` | `beides` | `halten`, `umschalten` oder `beides` |
| `einfuegen` | `tippen` | `tippen` (Zwischenablage bleibt unberührt) oder `zwischenablage` |
| `leerlauf_minuten` | `30` | Modell nach so vielen Minuten ohne Diktat entladen, `0` = nie |
| `max_aufnahme_s` | `300` | Höchstdauer einer Daueraufnahme |
| `mikrofon_offen_halten` | `false` | Mikrofon dauerhaft offen, mit 0,4 s Vorlauf (für Funkheadsets, die den Anfang verschlucken) |

`fachwoerter.txt`: ein Begriff pro Zeile, wirkt ab dem nächsten Diktat. Whisper nutzt nur die ersten ca. 600 Zeichen.

## Datenschutz

- Aufnahme und Text bleiben auf dem Rechner. Das Modell wird einmalig von Hugging Face geladen, danach braucht
  das Tool kein Internet.
- Aufnahmen werden nicht gespeichert (außer `aufnahmen_speichern = true` zum Testen).
- Das Log (`logs/diktat.log`) enthält nur Dauer, Zeichenzahl und Zeiten, **keinen Text**.

## Fehlersuche

- **Symbol fehlt:** Hinter dem „^“ in der Taskleiste nachsehen. Sonst `logs/waechter.log` und `logs/diktat.log` prüfen.
- **„Aufnahme war stumm“:** Mikrofon stummgeschaltet oder falsches Standard-Eingabegerät in Windows.
- **Text kommt in einem Programm nicht an:** Programme, die als Administrator laufen, nehmen aus
  Sicherheitsgründen keine Eingaben von normalen Programmen an.
- **Virenscanner meldet das Tool:** Das Tool liest Tastendrücke (für Strg+Y) und tippt selbst Text. Für
  Virenscanner sieht das ähnlich aus wie ein Keylogger. Gegebenenfalls von der IT freigeben lassen.

## Aufbau

```
diktat/            das Tool
  __main__.py      App, Bedienlogik, Wartung (Standby, Headset, Leerlauf), Halluzinations-Filter
  hotkey.py        globaler Shortcut (Win32-Tastatur-Hook + Wachhund)
  recorder.py      Mikrofon, 16 kHz mono
  engine.py        Whisper über OpenVINO GenAI in einem eigenen Prozess
  inserter.py      Text einfügen (Tippen oder Zwischenablage)
  tray.py          Taskleisten-Symbol und Menü
  waechter.py      startet das Tool nach Abstürzen neu
  autostart.py     Aufgabe in der Windows-Aufgabenplanung
start.pyw          Startpunkt für Autostart/Verknüpfung (Wächter → Tool)
config.toml        Einstellungen
fachwoerter.txt    Fachwortliste
tests/             Tests (python -m tests.test_kern usw.), ohne echte Tastatureingaben
whisper-test/      frühere Experimente und Benchmarks
```

## Verwendete Open-Source-Komponenten

| Komponente | Lizenz |
|---|---|
| OpenAI Whisper (Modelle large-v3, large-v3-turbo) | MIT |
| OpenVINO / OpenVINO GenAI (Intel) | Apache 2.0 |
| faster-whisper (nur Tests/Benchmarks) | MIT |
| sounddevice | MIT |
| pystray | LGPL-3.0 |
| Pillow | MIT-CMU (HPND) |
| huggingface_hub, NumPy | Apache 2.0 / BSD |

## Weitergabe an Kollegen

Noch nicht „herunterladen und loslegen“. Dafür fehlen:

1. **Installer oder `.exe`:** Heute braucht es uv, Python und Befehle im Terminal. Einige Stellen sind noch auf
   den Entwickler-Laptop zugeschnitten (die Verknüpfung `Whisper Diktat starten.lnk` und die erste Zeile in
   `start.pyw`).
2. **Automatische Geräteauswahl:** Auf Rechnern ohne Intel-Grafik sollte das Tool von selbst die CPU-Stufe nehmen.
3. **Freigabe durch die IT** wegen des Virenscanners (siehe Fehlersuche).

Alternative: Whisper zentral auf einem Server, die Laptops schicken nur die Aufnahme. Dafür braucht der Server
eine CPU mit AVX2 oder eine Grafikkarte.
