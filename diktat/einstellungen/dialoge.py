"""Dialoge des Einstellungsfensters: Tastenkombination wählen (aufnehmen, zusammenklicken oder aus einer Liste)."""
import tkinter as tk
from tkinter import ttk

from ..hotkey import parse_shortcut
from . import stil
from .daten import AKTIONEN_LESBAR, Befehl, doppelte_saetze, setze_befehl, tasten_lesbar

ZUSATZ_KEYSYMS = {"Control_L": "ctrl", "Control_R": "ctrl", "Shift_L": "shift", "Shift_R": "shift",
                  "Alt_L": "alt", "Alt_R": "alt", "Win_L": "win", "Win_R": "win", "Meta_L": "alt", "Meta_R": "alt"}
KEYSYM_TASTE = {"Return": "enter", "KP_Enter": "enter", "Escape": "esc", "Tab": "tab", "space": "space",
                "BackSpace": "backspace", "Delete": "delete", "Insert": "insert", "Left": "left", "Right": "right",
                "Up": "up", "Down": "down", "Home": "home", "End": "end", "Prior": "pageup", "Next": "pagedown",
                "period": ".", "Pause": "pause"}
REIHENFOLGE = ("ctrl", "alt", "shift", "win")
# Tasten zum Zusammenklicken: (interner Name, Anzeige)
TASTEN_AUSWAHL = ([("", "(keine – nur Zusatztasten)")] + [(c, c.upper()) for c in "abcdefghijklmnopqrstuvwxyz"]
                  + [(str(i), str(i)) for i in range(10)] + [(f"f{i}", f"F{i}") for i in range(1, 25)]
                  + [(t, tasten_lesbar(t)) for t in ("enter", "esc", "tab", "space", "backspace", "delete", "insert",
                                                       "left", "right", "up", "down", "home", "end", "pageup",
                                                       "pagedown", ".", "pause")])
BEKANNTE_KUERZEL = [("ctrl+win", "Diktieren (Vorschlag)"), ("ctrl+shift", "Diktieren (Alternative)"),
                    ("f9", "Diktieren (eine Taste)"), ("ctrl+alt+space", "Diktieren (Alternative)"),
                    ("win+d", "Desktop anzeigen"), ("alt+tab", "Fenster wechseln"), ("alt+f4", "Fenster schließen"),
                    ("win+v", "Zwischenablage-Verlauf"), ("win+shift+s", "Bildschirmausschnitt"),
                    ("win+.", "Emoji"), ("ctrl+shift+t", "Letzten Tab wieder öffnen")]


def taste_aus_keysym(keysym: str) -> str | None:
    """Tk-Tastenname -> Name wie in parse_shortcut; None für Zusatztasten und Unbekanntes."""
    if keysym in ZUSATZ_KEYSYMS:
        return None
    if len(keysym) == 1 and keysym.isascii() and keysym.isalnum():
        return keysym.lower()
    if keysym[:1] in "Ff" and keysym[1:].isdigit() and 1 <= int(keysym[1:]) <= 24:
        return keysym.lower()
    return KEYSYM_TASTE.get(keysym)


def kombi_aus(zusatz: set[str], taste: str | None) -> str:
    return "+".join([z for z in REIHENFOLGE if z in zusatz] + ([taste] if taste else []))


def pruefe_kombi(kombi: str, nur_zusatz_erlaubt: bool) -> str | None:
    if not kombi:
        return "Noch keine Tasten gewählt."
    try:
        mods, key = parse_shortcut(kombi)
    except ValueError as e:
        return str(e).split(": ", 1)[-1]
    if key is None and not nur_zusatz_erlaubt:
        return "Es fehlt eine normale Taste (nur Zusatztasten gehen hier nicht)."
    return None


class TastenDialog(tk.Toplevel):
    """Tastenkombination wählen. `ergebnis` ist nach OK die Kombination (z. B. "ctrl+shift+t"), sonst None."""

    def __init__(self, eltern, start: str = "", titel: str = "Tastenkombination wählen",
                 nur_zusatz_erlaubt: bool = False):
        super().__init__(eltern)
        self.title(titel)
        self.transient(eltern.winfo_toplevel())
        self.resizable(False, False)
        self.ergebnis: str | None = None
        self._nur_zusatz = nur_zusatz_erlaubt
        self._gehalten: set[str] = set()
        self._aufnahme = False
        self.kombi = tk.StringVar(value=start)
        self.zusatz = {z: tk.BooleanVar() for z in REIHENFOLGE}
        self.taste = tk.StringVar()

        f = ttk.Frame(self, padding=20)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Aufnehmen", style="Titel.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        stil.erklaerung(f, "Auf „Aufnehmen“ klicken und die Kombination drücken. Kombinationen, die Windows selbst "
                        "abfängt (z. B. Win+D, Alt+Tab), und die Diktier-Kombination kommen hier nicht an – die "
                        "unten zusammenklicken oder aus der Liste wählen.").grid(row=1, column=0, columnspan=2,
                                                                                sticky="w", pady=(2, 6))
        self._knopf = ttk.Button(f, text="Aufnehmen", command=self._aufnehmen)
        self._knopf.grid(row=2, column=0, sticky="w")

        ttk.Label(f, text="Zusammenklicken", style="Titel.TLabel").grid(row=3, column=0, columnspan=2, sticky="w",
                                                                       pady=(16, 4))
        z = ttk.Frame(f)
        z.grid(row=4, column=0, columnspan=2, sticky="w")
        for i, (name, text) in enumerate((("ctrl", "Strg"), ("alt", "Alt"), ("shift", "Umschalt"), ("win", "Win"))):
            ttk.Checkbutton(z, text=text, variable=self.zusatz[name], command=self._geklickt).grid(row=0, column=i,
                                                                                                 padx=(0, 12))
        self._anzeige_tasten = [a for _, a in TASTEN_AUSWAHL]
        self._box = ttk.Combobox(z, values=self._anzeige_tasten, state="readonly", width=24)
        self._box.grid(row=0, column=4)
        self._box.bind("<<ComboboxSelected>>", lambda e: self._geklickt())

        ttk.Label(f, text="Bekannte Kombinationen", style="Titel.TLabel").grid(row=5, column=0, columnspan=2,
                                                                              sticky="w", pady=(16, 4))
        self._liste = ttk.Treeview(f, columns=("kombi", "wofuer"), show="headings", height=6, selectmode="browse")
        self._liste.heading("kombi", text="Kombination")
        self._liste.heading("wofuer", text="Wofür")
        self._liste.column("kombi", width=180)
        self._liste.column("wofuer", width=260)
        for k, w in BEKANNTE_KUERZEL:
            self._liste.insert("", "end", iid=k, values=(tasten_lesbar(k), w))
        self._liste.grid(row=6, column=0, columnspan=2, sticky="we")
        self._liste.bind("<<TreeviewSelect>>", self._aus_liste)

        ttk.Separator(f).grid(row=7, column=0, columnspan=2, sticky="we", pady=16)
        zeile = ttk.Frame(f)
        zeile.grid(row=8, column=0, columnspan=2, sticky="we")
        ttk.Label(zeile, text="Gewählt:").pack(side="left")
        self._gewaehlt = ttk.Label(zeile, style="Titel.TLabel")
        self._gewaehlt.pack(side="left", padx=8)
        self._fehler = ttk.Label(f, style="Fehler.TLabel")
        self._fehler.grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 0))
        knoepfe = ttk.Frame(f)
        knoepfe.grid(row=10, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(knoepfe, text="Abbrechen", command=self.destroy).pack(side="right")
        self._ok = ttk.Button(knoepfe, text="OK", style="Accent.TButton", command=self._fertig)
        self._ok.pack(side="right", padx=(0, 8))

        self.bind("<KeyPress>", self._druck)
        self.bind("<KeyRelease>", self._los)
        self.kombi.trace_add("write", lambda *a: self._zeigen())
        self._zeigen()

    # --- Aufnehmen über Tk-Tastenereignisse ------------------------------------------------------------------------
    def _aufnehmen(self):
        self._aufnahme, self._gehalten = True, set()
        self._knopf.configure(text="Drück jetzt die Kombination …")
        self.focus_set()

    def _druck(self, e):
        if not self._aufnahme:
            return None
        if e.keysym in ZUSATZ_KEYSYMS:
            self._gehalten.add(ZUSATZ_KEYSYMS[e.keysym])
            return "break"
        taste = taste_aus_keysym(e.keysym)
        if taste:
            self._setze(kombi_aus(self._gehalten, taste))
        return "break"

    def _los(self, e):
        if not self._aufnahme or e.keysym not in ZUSATZ_KEYSYMS:
            return None
        if len(self._gehalten) >= 2 and self._nur_zusatz:  # z. B. Strg+Win ohne weitere Taste
            self._setze(kombi_aus(self._gehalten, None))
        self._gehalten.discard(ZUSATZ_KEYSYMS[e.keysym])
        return "break"

    def _setze(self, kombi: str):
        self._aufnahme = False
        self._knopf.configure(text="Aufnehmen")
        self.kombi.set(kombi)

    # --- Zusammenklicken und Liste -----------------------------------------------------------------------------------
    def _geklickt(self):
        i = self._box.current()
        taste = TASTEN_AUSWAHL[i][0] if i >= 0 else ""
        self.kombi.set(kombi_aus({z for z, v in self.zusatz.items() if v.get()}, taste or None))

    def _aus_liste(self, _e=None):
        sel = self._liste.selection()
        if sel:
            self.kombi.set(sel[0])

    def _zeigen(self):
        k = self.kombi.get()
        self._gewaehlt.configure(text=tasten_lesbar(k) if k else "–")
        f = pruefe_kombi(k, self._nur_zusatz)
        self._fehler.configure(text=f or "")
        self._ok.state(["disabled"] if f else ["!disabled"])

    def _fertig(self):
        if pruefe_kombi(self.kombi.get(), self._nur_zusatz) is None:
            self.ergebnis = self.kombi.get()
            self.destroy()


def tasten_waehlen(eltern, start: str = "", nur_zusatz_erlaubt: bool = False,
                   titel: str = "Tastenkombination wählen") -> str | None:
    d = TastenDialog(eltern, start, titel, nur_zusatz_erlaubt)
    d.grab_set()
    d.wait_window()
    return d.ergebnis


# --- Befehl anlegen / ändern ---------------------------------------------------------------------------------------
class BefehlDialog(tk.Toplevel):
    """Ein Befehl: Art, Sätze (eine Zeile je Variante) und was passieren soll. `ergebnis` = Befehl nach OK."""

    def __init__(self, eltern, befehl: Befehl | None, alle: list[Befehl], dateitext: str):
        super().__init__(eltern)
        self.title("Befehl ändern" if befehl else "Neuer Befehl")
        self.transient(eltern.winfo_toplevel())
        self.ergebnis: Befehl | None = None
        self._alt, self._alle, self._dateitext = befehl, alle, dateitext
        self.art = tk.StringVar(value=befehl.art if befehl else "tasten")
        self.ziel = tk.StringVar(value=befehl.ziel if befehl and befehl.art == "oeffnen" else "")
        self.tasten: list[str] = befehl.ziel.split() if befehl and befehl.art == "tasten" else []
        self._aktionen = list(AKTIONEN_LESBAR)

        f = ttk.Frame(self, padding=20)
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        ttk.Label(f, text="Was soll passieren?", style="Titel.TLabel").grid(row=0, column=0, sticky="w")
        arten = ttk.Frame(f)
        arten.grid(row=1, column=0, sticky="w", pady=(4, 12))
        for wert, text in (("oeffnen", "Etwas öffnen (Seite, Programm, Ordner)"), ("tasten", "Tasten drücken"),
                           ("aktionen", "Eingebaute Aktion")):
            ttk.Radiobutton(arten, text=text, value=wert, variable=self.art, command=self._art_zeigen).pack(
                side="left", padx=(0, 16))

        ttk.Label(f, text="Sätze", style="Titel.TLabel").grid(row=2, column=0, sticky="w")
        stil.erklaerung(f, "Eine Zeile je Variante. Der Befehl wirkt nur, wenn das ganze Diktat genau so ein Satz ist; "
                        "Groß-/Kleinschreibung und Satzzeichen sind egal.").grid(row=3, column=0, sticky="w")
        self.saetze_text = tk.Text(f, height=4, width=56, wrap="word", font=("Segoe UI", 10))
        self.saetze_text.grid(row=4, column=0, sticky="we", pady=(4, 0))
        if befehl:
            self.saetze_text.insert("1.0", "\n".join(befehl.saetze))
        self.saetze_text.bind("<KeyRelease>", lambda e: self._pruefen_live())
        self.warnung = ttk.Label(f, style="Neustart.TLabel", wraplength=stil.px(520), justify="left")
        self.warnung.grid(row=5, column=0, sticky="w")

        self._teil = ttk.Frame(f)
        self._teil.grid(row=6, column=0, sticky="we", pady=(12, 0))
        # Öffnen
        self._oeffnen = ttk.Frame(self._teil)
        ttk.Label(self._oeffnen, text="Adresse, Programm oder Ordner", style="Titel.TLabel").grid(row=0, column=0,
                                                                                                 sticky="w")
        ttk.Entry(self._oeffnen, textvariable=self.ziel, width=56).grid(row=1, column=0, columnspan=4, sticky="we",
                                                                       pady=(4, 4))
        ttk.Button(self._oeffnen, text="Programm wählen …", command=self._programm).grid(row=2, column=0, sticky="w")
        ttk.Button(self._oeffnen, text="Ordner wählen …", command=self._ordner).grid(row=2, column=1, sticky="w",
                                                                                   padx=(8, 0))
        ttk.Button(self._oeffnen, text="Testen", command=self._testen).grid(row=2, column=2, sticky="w", padx=(8, 0))
        self._formen = stil.erklaerung(self._oeffnen, "")
        self._formen.grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))
        # Tasten
        self._tasten_rahmen = ttk.Frame(self._teil)
        ttk.Label(self._tasten_rahmen, text="Tasten", style="Titel.TLabel").grid(row=0, column=0, sticky="w")
        self._tasten_anzeige = ttk.Label(self._tasten_rahmen, style="Titel.TLabel")
        self._tasten_anzeige.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 4))
        ttk.Button(self._tasten_rahmen, text="Taste wählen …", command=self._taste_neu).grid(row=2, column=0,
                                                                                            sticky="w")
        ttk.Button(self._tasten_rahmen, text="+ weitere Taste danach", command=self._taste_dazu).grid(
            row=2, column=1, sticky="w", padx=(8, 0))
        ttk.Button(self._tasten_rahmen, text="Zurücksetzen", command=self._tasten_leeren).grid(row=2, column=2,
                                                                                               sticky="w", padx=(8, 0))
        # Aktion
        self._aktion_rahmen = ttk.Frame(self._teil)
        ttk.Label(self._aktion_rahmen, text="Aktion", style="Titel.TLabel").grid(row=0, column=0, sticky="w")
        self.aktion_box = ttk.Combobox(self._aktion_rahmen, state="readonly", width=48,
                                       values=[AKTIONEN_LESBAR[a] for a in self._aktionen])
        self.aktion_box.grid(row=1, column=0, sticky="w", pady=(4, 0))
        if befehl and befehl.art == "aktionen" and befehl.ziel in self._aktionen:
            self.aktion_box.current(self._aktionen.index(befehl.ziel))

        self.fehler_text = ttk.Label(f, style="Fehler.TLabel", wraplength=stil.px(520), justify="left")
        self.fehler_text.grid(row=7, column=0, sticky="w", pady=(12, 0))
        knoepfe = ttk.Frame(f)
        knoepfe.grid(row=8, column=0, sticky="e", pady=(12, 0))
        ttk.Button(knoepfe, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(knoepfe, text="OK", style="Accent.TButton", command=self._fertig).pack(side="right", padx=(0, 8))
        self._art_zeigen()
        self._tasten_zeigen()
        self._pruefen_live()

    def _saetze(self) -> list[str]:
        return [z.strip() for z in self.saetze_text.get("1.0", "end").splitlines() if z.strip()]

    def _art_zeigen(self):
        for teil in (self._oeffnen, self._tasten_rahmen, self._aktion_rahmen):
            teil.pack_forget()
        {"oeffnen": self._oeffnen, "tasten": self._tasten_rahmen, "aktionen": self._aktion_rahmen}[
            self.art.get()].pack(fill="x")
        self._pruefen_live()

    def _pruefen_live(self):
        saetze = self._saetze()
        name = saetze[0] if saetze else "Name"
        self._formen.configure(text=f"Sagbar als: „öffne {name}“, „{name} öffnen“, „mach {name} auf“, "
                                    f"„zeig mir {name}“ … (alle Formen automatisch).")
        eigen = self._alt.schluessel if self._alt else ""
        doppelt = doppelte_saetze(self._alle, Befehl(self.art.get(), saetze, "", eigen))
        self.warnung.configure(text=("Schon in einem anderen Befehl: " + ", ".join(doppelt)
                                     + " – dort bleibt er wirksam, hier nicht.") if doppelt else "")

    # --- Öffnen ---
    def _programm(self):
        from tkinter import filedialog
        pfad = filedialog.askopenfilename(parent=self, title="Programm wählen",
                                          filetypes=[("Programme", "*.exe *.lnk *.bat *.cmd"), ("Alle Dateien", "*")])
        if pfad:
            self.ziel.set(pfad.replace("/", "\\"))

    def _ordner(self):
        from tkinter import filedialog
        pfad = filedialog.askdirectory(parent=self, title="Ordner wählen")
        if pfad:
            self.ziel.set(pfad.replace("/", "\\"))

    def _testen(self):
        import os
        try:
            os.startfile(self.ziel.get().strip())
            self.fehler_text.configure(text="")
        except OSError as e:
            self.fehler_text.configure(text=f"Lässt sich nicht öffnen: {e}")

    # --- Tasten ---
    def _tasten_zeigen(self):
        self._tasten_anzeige.configure(text=tasten_lesbar(" ".join(self.tasten)) if self.tasten
                                       else "noch keine Taste gewählt")

    def _taste_neu(self):
        k = tasten_waehlen(self, self.tasten[-1] if self.tasten else "")
        if k:
            self.tasten = (self.tasten[:-1] if self.tasten else []) + [k]
            self._tasten_zeigen()

    def _taste_dazu(self):
        k = tasten_waehlen(self, "", titel="Weitere Taste (wird danach gedrückt)")
        if k:
            self.tasten.append(k)
            self._tasten_zeigen()

    def _tasten_leeren(self):
        self.tasten = []
        self._tasten_zeigen()

    # --- Fertig ---
    def _befehl(self) -> Befehl:
        art = self.art.get()
        if art == "tasten":
            ziel = " ".join(self.tasten)
        elif art == "aktionen":
            i = self.aktion_box.current()
            ziel = self._aktionen[i] if i >= 0 else ""
        else:
            ziel = self.ziel.get().strip()
        return Befehl(art, self._saetze(), ziel)

    def _fertig(self):
        neu = self._befehl()
        try:
            setze_befehl(self._dateitext, self._alt, neu)  # nur prüfen, gespeichert wird im Reiter
        except ValueError as e:
            self.fehler_text.configure(text=str(e))
            return
        self.ergebnis = neu
        self.destroy()


def befehl_bearbeiten(eltern, befehl: Befehl | None, alle: list[Befehl], dateitext: str) -> Befehl | None:
    d = BefehlDialog(eltern, befehl, alle, dateitext)
    d.grab_set()
    d.wait_window()
    return d.ergebnis
