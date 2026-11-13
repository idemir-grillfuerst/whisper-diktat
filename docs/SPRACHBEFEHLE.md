# Sprachbefehle: Anleitung

Mit whisper-diktat kannst du nicht nur Text diktieren, sondern den PC auch per Sprache bedienen. Alles läuft lokal,
ohne KI und ohne Internet (außer die Seiten, die du öffnen lässt).

## Die drei Regeln
1. **Absenden am Ende:** Endet ein Diktat auf **„Senden“** oder **„Enter“**, wird das Wort weggelassen, der Text
   eingefügt und danach Enter gedrückt.
   „Passt so, bis morgen. Senden.“ → `Passt so, bis morgen.` + Enter.
   Mitten im Satz passiert nichts: „Senden wir das morgen“ bleibt Text.
2. **Befehl = das ganze Diktat:** Sagst du *nur* einen Befehl, etwa „Kopieren“ oder „Öffne Outlook“, wird er
   ausgeführt. Kommt das Wort in einem längeren Satz vor („Mach mal eine Copy davon“), ist es normaler Text.
3. **Groß-/Kleinschreibung und Satzzeichen sind egal.** „Öffne Outlook!“ wirkt wie „öffne outlook“.

## Befehle (Auswahl, alle stehen in `befehle.toml`)

**Bearbeiten**

| Sagen | Wirkung |
|---|---|
| Kopieren · Copy · Strg C | Strg+C |
| Einfügen · Paste · Strg V | Strg+V |
| Ausschneiden · Cut · Strg X | Strg+X |
| Rückgängig · Undo · Strg Z | Strg+Z |
| Wiederholen · Redo · Strg Y | Strg+Y |
| Alles markieren · Select all · Strg A | Strg+A |
| Speichern · Save · Strg S | Strg+S |
| Suchen | Strg+F |
| Neue Zeile / Neuer Absatz | Zeilenumbruch (ohne Absenden) |
| Wort löschen / Zeile löschen | Strg+Rücktaste / ganze Zeile |
| Ganz nach oben / Ganz nach unten | Strg+Pos1 / Strg+Ende |

**Fenster und Browser**

| Sagen | Wirkung |
|---|---|
| Neuer Tab / Tab schließen / Letzten Tab wieder öffnen | Strg+T / Strg+W / Strg+Shift+T |
| Neu laden · Zurück · Vor | F5 · Alt+← · Alt+→ |
| Fenster wechseln / Fenster schließen | Alt+Tab / Alt+F4 |
| Desktop anzeigen | Win+D |
| Screenshot · Zwischenablage · Emoji | Win+Shift+S · Win+V · Win+. |
| Abbrechen · Escape / Tab | Esc / Tab |

**Öffnen**: jeder Name funktioniert als „öffne X“, „X öffnen“, „öffne mal X“, „mach X auf“, „X aufmachen“,
„starte X“, „X starten“, „geh zu X“, „zeig X“, „zeig mir X“.
Outlook, Kalender, Teams, OneDrive, Office, Claude (App), Claude im Browser, ChatGPT, Google, Maps, YouTube,
GitHub, WhatsApp, DeepL, Rechner, Editor, Explorer, Downloads, Dokumente, Einstellungen, Task Manager, dazu deine
eigenen Einträge.

## Textfeld: ohne Maus ins Eingabefeld

| Sagen | Wirkung |
|---|---|
| Textfeld · Eingabefeld · Chatfeld | Cursor ins Eingabefeld des Fensters vorne (ans Ende des Texts) |
| Textfeld, *Text* … Senden | ins Feld, Text einfügen, absenden, alles in einem Diktat |
| Merke Textfeld | das Feld unter dem Mauszeiger merken (für dieses Programm bzw. diese Website) |
| Vergiss Textfeld | die gemerkte Regel für das Programm/die Website vorne löschen |

- Funktioniert in der Claude-App, in Teams und im Browser. Das Tool sucht das Feld über die Windows-Bedienungshilfe.
- Als Vorsilbe gilt „Textfeld“ nur mit Satzzeichen danach („Textfeld, Hallo“). „Textfeld muss breiter werden“ bleibt
  Text. Nach „Textfeld,“ wird nur noch auf „Senden“ am Ende geachtet: „Textfeld, rückgängig“ schreibt das Wort hin.
- Findet das Tool kein Feld, kommt eine **Windows-Meldung** und es wird **nichts** eingefügt, damit der Text nicht im
  falschen Programm landet. Der diktierte Text steht dann im Log.
- **Bestätigung am Bildschirm:** Bei „merke Textfeld“ und „vergiss Textfeld“ leuchtet kurz ein **grüner Haken** auf,
  am gemerkten Feld bzw. am Mauszeiger. Klappt etwas nicht (auch wenn „Textfeld“ kein Feld findet), erscheint ein
  **rotes Kreuz**. Das Zeichen ist durchklickbar und verschwindet nach 1,5 s.
- Gemerkte Felder stehen in `textfelder.toml` (Projektordner). Dort kann man auch von Hand eine Taste oder
  Klickposition hinterlegen, siehe Kommentare in der Datei.

## Einstellungen und eigene Befehle
Klick auf das Symbol in der Taskleiste (oder Rechtsklick → **„Einstellungen …“**) öffnet das Einstellungsfenster:

| Reiter | Was du dort machst |
|---|---|
| Allgemein | Tastenkombination, Bedienung, Maustaste, Einfügen, **Wörter zum Absenden**, Autostart |
| Mikrofon | Mikrofon wählen, **Pegeltest** („hört mich das Mikrofon?“), Mikrofon offen halten |
| Modell | Turbo oder Large-v3, Grafik/NPU/Prozessor, Sprache |
| Befehle | alle Sprachbefehle als Tabelle: suchen, **Neu**, **Ändern** (Doppelklick), **Löschen** |
| Textfelder | gemerkte Textfelder ansehen und löschen |
| Fachwörter | Begriffe, die Whisper richtig schreiben soll |
| Info | Version, Anleitung, Log, Projektordner |

- Jede Option ist im Fenster erklärt. Was erst nach einem Neustart greift, ist mit „↻“ markiert; das Fenster bietet
  den Neustart dann selbst an. Alles andere übernimmt das Tool in wenigen Sekunden.
- **Neuer Befehl:** Reiter Befehle → „Neu …“ → wählen, was passieren soll (etwas öffnen, Tasten drücken,
  eingebaute Aktion), Sätze eintragen (eine Zeile je Variante). Tasten musst du nicht tippen: „Taste wählen …“
  nimmt sie auf oder du klickst sie zusammen. Programme und Ordner gehen über „Programm wählen …“ / „Ordner
  wählen …“, mit „Testen“ probierst du es direkt aus.
- Befehle werden sofort gespeichert, die übrigen Reiter mit „Übernehmen“ oder „OK“.

Für Fortgeschrittene stehen alle Einstellungen weiter in Textdateien im Projektordner (`config.toml`,
`befehle.toml`, `textfelder.toml`, `fachwoerter.txt`, Reiter Info → „Dateien von Hand bearbeiten …“). Das Fenster
lässt Kommentare darin stehen. Ist eine Datei fehlerhaft, läuft das Diktieren weiter; das Symbol meldet den Fehler.

## Tipps
- Kurze Einzelwörter wie „Zurück.“ oder „Tab.“ lösen immer den Befehl aus. Willst du so ein Wort als Text,
  diktiere einen ganzen Satz oder lösch den Befehl im Einstellungsfenster (Reiter Befehle).
- Erkennt Whisper ein Wort bei dir anders (z. B. „Enta“), trag die Schreibweise im Reiter Befehle als weiteren Satz ein (bei „Senden“: Reiter Allgemein).
- Was ausgeführt wurde, steht im Log (Menü „Log öffnen“), Zeilen „Befehl: …“.
