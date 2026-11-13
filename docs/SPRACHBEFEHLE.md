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

## Eigene Befehle
Rechtsklick auf das Symbol → **„Befehle bearbeiten …“** öffnet `befehle.toml`. Änderungen gelten ab dem nächsten
Diktat, ohne Neustart. Mehrere Schreibweisen mit `|` trennen.

```toml
[oeffnen]
"lieferantenportal|portal" = "https://..."          # Webseite (öffnet im Standardbrowser)
"claude" = "shell:AppsFolder\\Claude_pzs8sxrjxfjjc!Claude"   # installierte App

[tasten]
"fett" = "ctrl+b"
"neuer absatz" = "shift+enter shift+enter"          # mehrere Tasten nacheinander
```

Ist die Datei fehlerhaft, zeigt das Symbol-Menü den Fehler an. Diktieren geht trotzdem weiter, nur die Befehle sind
dann aus.

Die Wörter für „Absenden“ stehen in `config.toml`:

```toml
[befehle]
enter = ["enter", "senden"]   # [] = aus
```

## Tipps
- Kurze Einzelwörter wie „Zurück.“ oder „Tab.“ lösen immer den Befehl aus. Willst du so ein Wort als Text,
  diktiere einen ganzen Satz oder nimm den Eintrag aus `befehle.toml`.
- Erkennt Whisper ein Wort bei dir anders (z. B. „Enta“), trag die Schreibweise als weitere Variante ein.
- Was ausgeführt wurde, steht im Log (Menü „Log öffnen“), Zeilen „Befehl: …“.
