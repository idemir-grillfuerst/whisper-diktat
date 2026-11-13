"""Dialoge des Einstellungsfensters: Tastenkombination wählen (aufnehmen, zusammenklicken oder aus einer Liste)."""
import tkinter as tk
from tkinter import ttk

from ..hotkey import parse_shortcut
from . import stil
from .daten import tasten_lesbar

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
