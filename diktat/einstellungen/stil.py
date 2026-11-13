"""Aussehen des Einstellungsfensters: Windows-11-Design (sv-ttk), hell/dunkel nach Windows, Schriften, Bausteine."""
import tkinter as tk
import tkinter.font as tkfont
import winreg
from tkinter import ttk

BREITE_TEXT = 640   # Umbruchbreite für Erklärungen bei 100 % (wird mit der Bildschirmskalierung multipliziert)
_dunkel = False
_faktor = 1.0       # Bildschirmskalierung (1,5 bei 150 %)


def px(wert: float) -> int:
    """Pixelangabe für 100 % in echte Pixel umrechnen."""
    return round(wert * _faktor)


def windows_dunkel() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def einrichten(root: tk.Tk) -> None:
    global _dunkel, _faktor
    _dunkel = windows_dunkel()
    _faktor = max(1.0, root.winfo_fpixels("1i") / 96)
    try:
        import sv_ttk
        sv_ttk.set_theme("dark" if _dunkel else "light", root)
        # sv-ttk gibt Schriften in festen Pixeln an; bei 150 % wären sie kleiner als alles andere -> in Punkt umrechnen
        for name in tkfont.names(root):
            if name.startswith("SunValley"):
                f = tkfont.nametofont(name, root)
                if f.cget("size") < 0:
                    f.configure(size=max(1, round(-f.cget("size") * 0.75)))
        koerper, stark, klein, gross = ("SunValleyBodyFont", "SunValleyBodyStrongFont", "SunValleyCaptionFont",
                                        "SunValleySubtitleFont")
    except Exception:  # noqa: BLE001 – ohne sv-ttk: Standardaussehen
        ttk.Style(root).theme_use("vista" if "vista" in ttk.Style(root).theme_names() else "default")
        koerper, stark, klein, gross = (("Segoe UI", 10), ("Segoe UI Semibold", 10), ("Segoe UI", 9),
                                        ("Segoe UI Semibold", 14))
    s = ttk.Style(root)
    grau = "#a0a0a0" if _dunkel else "#5f6368"
    s.configure("Erklaerung.TLabel", foreground=grau, font=klein)
    s.configure("Fehler.TLabel", foreground="#e5534b" if _dunkel else "#c42b1c", font=klein)
    s.configure("Titel.TLabel", font=stark)
    s.configure("Ueberschrift.TLabel", font=gross)
    s.configure("Neustart.TLabel", foreground="#d18616" if _dunkel else "#9a6700", font=klein)
    s.configure("TLabel", font=koerper)


def erklaerung(eltern, text: str, **kw) -> ttk.Label:
    return ttk.Label(eltern, text=text, style="Erklaerung.TLabel", wraplength=px(BREITE_TEXT), justify="left", **kw)


class ScrollRahmen(ttk.Frame):
    """Rahmen mit senkrechtem Rollbalken; Inhalt in `.innen` packen. Mausrad rollt, solange die Maus darüber ist."""

    def __init__(self, eltern, **kw):
        super().__init__(eltern, **kw)
        self._canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self._balken = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self.innen = ttk.Frame(self._canvas, padding=(px(22), px(16), px(22), px(16)))
        self._id = self._canvas.create_window((0, 0), window=self.innen, anchor="nw")
        self._canvas.configure(yscrollcommand=self._balken.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._balken.pack(side="right", fill="y")
        self.innen.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfigure(self._id, width=e.width))
        self._canvas.bind("<Enter>", lambda e: self._canvas.bind_all("<MouseWheel>", self._rad))
        self._canvas.bind("<Leave>", lambda e: self._canvas.unbind_all("<MouseWheel>"))
        self.after_idle(self._hintergrund)

    def _hintergrund(self):
        try:
            self._canvas.configure(background=ttk.Style(self).lookup("TFrame", "background") or None)
        except tk.TclError:
            pass

    def _rad(self, e):
        if self.innen.winfo_height() > self._canvas.winfo_height():
            self._canvas.yview_scroll(int(-e.delta / 120) * 3, "units")
