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
| Prozessor/Grafik | Intel Core Ultra mit Arc-Grafik | x86-64-CPU mit AVX2 (Recheneinheit CPU, deutlich langsamer) |
| Arbeitsspeicher | 16 GB | 8 GB |
| Speicherplatz | ca. 5 GB (Python, Modelle, Cache) | ca. 3 GB (nur ein Modell) |
| Mikrofon | Headset | eingebautes Mikrofon |

Das Tool nutzt Intels OpenVINO und läuft am besten auf **Intel**-Grafik oder -NPU. Auf Rechnern ohne
Intel-Grafik bleibt nur die Recheneinheit CPU.

## Installation

Repo herunterladen (oder klonen), im Ordner PowerShell öffnen und:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Das Skript installiert uv, Python 3.12 und die Pakete im Benutzerordner. Dann lädt es das Modell, legt die
Desktop-Verknüpfung an, schaltet den Autostart ein und startet das Tool. Adminrechte sind nicht nötig.
Einzelheiten, Optionen, Update, Deinstallation und Fehlersuche: **[INSTALL.md](INSTALL.md)**.

Mit Claude Code geht es auch so: „Installier mir whisper-diktat, Anleitung steht in INSTALL.md.“

Der Autostart läuft über die Aufgabe „whisper-diktat“ in der Windows-Aufgabenplanung. Sie startet das Tool bei
der Anmeldung, beim Entsperren und alle 10 Minuten, falls es nicht läuft.

## Bedienung

| Aktion | Was passiert |
|---|---|
| Strg+Y **halten** | Aufnahme (Symbol rot), beim Loslassen wird transkribiert (gelb) und eingefügt |
| Strg+Y **kurz tippen** | Daueraufnahme startet, nochmal tippen = fertig |
| **Mausrad halten** (wenn `maustaste = "mitte"`) | Aufnahme, loslassen = einfügen. Kurzer Mittelklick wirkt wie immer (z. B. Link in neuem Tab) |
| Rechtsklick auf das Symbol | Menü: Pausieren, Modell, Recheneinheit, Mikrofon, Bedienung, Fachwörter, Einstellungen, Log, Autostart, Neu starten, Beenden |

Solange das Tool läuft, ist Strg+Y in anderen Programmen nicht als „Wiederholen“ verfügbar. Pausieren gibt
die Taste frei. Der Shortcut ist in `config.toml` änderbar.

### Modell, Recheneinheit und Mikrofon (im Menü wählbar)

**Modell**

| Modell | Wofür |
|---|---|
| Turbo – schnell (large-v3-turbo, int8) | voreingestellt, am schnellsten, fast so genau wie Large-v3 |
| Large-v3 – genau (large-v3, int8) | etwas genauer bei schwierigen Aufnahmen, etwas langsamer (wird beim ersten Wählen geladen, ca. 1,6 GB) |

**Recheneinheit:** Im Menü stehen nur die Einheiten, die auf dem Rechner wirklich vorhanden sind, mit Namen.

| Auswahl | Bedeutung |
|---|---|
| Automatisch | Grafik, wenn vorhanden, sonst CPU (Standard) |
| Grafik | am schnellsten (Intel-Grafik) |
| NPU | sparsam, Lüfter bleibt ruhig. Das erste Laden dauert einige Minuten |
| CPU | geht überall, aber deutlich langsamer |

Ist eine gewählte Einheit nicht (mehr) vorhanden, nimmt das Tool automatisch die beste vorhandene.

**Mikrofon:** „Windows-Standard“ folgt dem Standard-Eingabegerät von Windows. Oder du wählst ein bestimmtes
Mikrofon, z. B. das Headset. Ist es gerade nicht angeschlossen, nimmt das Tool den Windows-Standard und
wechselt zurück, sobald es wieder da ist. Neu angesteckte Mikrofone erscheinen nach spätestens einer Minute im Menü.

### Symbolfarben

blau = lädt · grau = bereit · rot = Aufnahme · gelb = transkribiert · durchgestrichen = pausiert ·
Mond = Modell im Leerlauf entladen (lädt beim nächsten Diktat nach) · schwarz = Fehler (siehe Log)

## Einstellungen

Klick auf das Symbol öffnet das **Einstellungsfenster** (Reiter Allgemein, Mikrofon, Modell, Befehle,
Textfelder, Fachwörter, Info), jede Option ist dort erklärt. Gespeichert wird in `config.toml`; das Tool
übernimmt Änderungen nach wenigen Sekunden, Tastenkombination und Maustaste nach einem Neustart. Die Datei ist
persönlich und nicht in Git. Beim ersten Start entsteht sie aus der Vorlage `config.beispiel.toml`. Genauso entsteht
`fachwoerter.txt` aus `fachwoerter.beispiel.txt`.

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `shortcut` | `ctrl+y` | z. B. `ctrl+alt+space`, `f9`, `ctrl+shift` |
| `[modell] name` | `turbo` | `turbo` oder `large-v3` (auch im Menü) |
| `[modell] geraet` | `auto` | `auto`, `GPU`, `NPU`, `CPU` (auch im Menü) |
| `mikrofon` | `""` | leer = Windows-Standard, sonst Gerätename (auch im Menü) |
| `modus` | `beides` | `halten`, `umschalten` oder `beides` |
| `maustaste` | `""` | zusätzlich per Maus diktieren: `mitte` (Mausrad halten), `x1`/`x2` (Seitentasten). Kurzer Klick bleibt ein normaler Klick, nur Auto-Scroll per Mausrad fällt weg |
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
  geraete.py       vorhandene Recheneinheiten (OpenVINO) und Mikrofone
  waechter.py      startet das Tool nach Abstürzen neu
  autostart.py     Aufgabe in der Windows-Aufgabenplanung
  einrichten.py    Einrichtung nach der Installation (Dateien, Geräte, Modell, Verknüpfungen, Autostart)
install.ps1        Installation für den aktuellen Benutzer (siehe INSTALL.md)
start.pyw          Startpunkt für Autostart/Verknüpfung (Wächter → Tool)
config.beispiel.toml      Vorlage für config.toml (persönlich, nicht in Git)
fachwoerter.beispiel.txt  Vorlage für fachwoerter.txt (persönlich, nicht in Git)
requirements.txt   Pakete (requirements-test.txt zusätzlich für Tests)
tests/             Tests (python -m tests.test_kern usw.), ohne echte Tastatureingaben
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

1. Repo freigeben (GitHub: Settings → Collaborators) oder als ZIP weitergeben.
2. Der Kollege führt `install.ps1` aus oder lässt Claude Code das nach [INSTALL.md](INSTALL.md) erledigen.
3. **Freigabe durch die IT** wegen des Virenscanners (siehe Fehlersuche) vorher klären.

Persönliches bleibt beim jeweiligen Nutzer: Einstellungen, Fachwortliste, Logs und Aufnahmen sind nicht in Git.
Die Recheneinheit wählt das Tool selbst: Ohne Intel-Grafik nimmt es automatisch die CPU, dann dauert ein Diktat
einige Sekunden.

Alternative: Whisper zentral auf einem Server, die Laptops schicken nur die Aufnahme. Dafür braucht der Server
eine CPU mit AVX2 oder eine Grafikkarte.
