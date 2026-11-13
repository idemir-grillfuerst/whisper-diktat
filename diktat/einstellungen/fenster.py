"""Hauptfenster: Reiter, Übernehmen/OK/Abbrechen, ungespeicherte Änderungen, Neustart anbieten."""
import ctypes
import importlib
import logging
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..config import BEFEHLE_DATEI, CONFIG_DATEI, FACHWORT_DATEI, TEXTFELDER_DATEI, schreibe_atomar
from . import daten, stil

log = logging.getLogger("diktat")
TITEL = "Whisper Diktat – Einstellungen"
NEUSTART_EREIGNIS = "Local\\whisper-diktat-neustart"
STANDARD_DATEIEN = {"config": CONFIG_DATEI, "befehle": BEFEHLE_DATEI, "textfelder": TEXTFELDER_DATEI,
                    "fachwoerter": FACHWORT_DATEI}
# (Modul, Klasse) in der Reihenfolge der Reiter. Fehlt ein Modul, fehlt nur der Reiter.
REITER = [("allgemein", "Allgemein"), ("mikrofon", "Mikrofon"), ("modell", "Modell"),
          ("befehle_reiter", "BefehleReiter"), ("textfelder_reiter", "TextfelderReiter"),
          ("fachwoerter", "Fachwoerter"), ("info", "Info")]


class Reiter(ttk.Frame):
    """Basis eines Reiters. Unterklassen setzen `titel` und überschreiben laden/geaendert/fehler/uebernehmen."""
    titel = ""

    def __init__(self, eltern, fenster: "Fenster"):
        super().__init__(eltern)
        self.fenster = fenster

    def laden(self) -> None:
        pass

    def geaendert(self) -> bool:
        return False

    def fehler(self) -> dict[str, str]:
        return {}

    def uebernehmen(self) -> list[str]:
        """Änderungen in die Dateien schreiben; Rückgabe: Namen der geänderten Felder (für ↻)."""
        return []

    def aktualisieren(self) -> None:
        """Dateistand neu lesen, falls er sich von außen geändert hat. Standard: nichts."""

    def melden(self, *_):
        self.fenster.markiere(self)

    def im_hintergrund(self, arbeit, fertig) -> None:
        """`arbeit()` in einem Thread ausführen, danach `fertig(ergebnis)` im Tk-Thread (Tk darf nur von dort
        aus benutzt werden). Eine Ausnahme kommt als Ergebnis an."""
        ergebnis: queue.Queue = queue.Queue()

        def lauf():
            try:
                ergebnis.put(arbeit())
            except Exception as e:  # noqa: BLE001
                ergebnis.put(e)
        threading.Thread(target=lauf, daemon=True).start()

        def abholen():
            try:
                wert = ergebnis.get_nowait()
            except queue.Empty:
                try:
                    self.after(50, abholen)
                except tk.TclError:  # Fenster schon zu
                    pass
                return
            fertig(wert)
        self.after(50, abholen)


class KonfigReiter(Reiter):
    """Reiter mit Feldern aus config.toml (daten.FELDER). Erzeugt Eingaben samt Titel, Erklärung und Fehlerzeile."""
    felder: tuple[str, ...] = ()

    def __init__(self, eltern, fenster):
        super().__init__(eltern, fenster)
        self.rahmen = stil.ScrollRahmen(self)
        self.rahmen.pack(fill="both", expand=True)
        self.innen = self.rahmen.innen
        self.innen.columnconfigure(0, weight=1)
        self.var: dict[str, tk.Variable] = {}
        self.original: dict[str, object] = {}
        self._fehler_label: dict[str, ttk.Label] = {}
        self._zeilen: dict[str, ttk.Frame] = {}
        self._zeile = 0
        self.angefasst: set[str] = set()   # vom Nutzer seit dem letzten Laden/Übernehmen geänderte Felder
        self._laedt = False
        self._mtime = None

    # --- Bausteine -------------------------------------------------------------------------------------------------
    def ueberschrift(self, text: str, erklaerung: str = ""):
        ttk.Label(self.innen, text=text, style="Ueberschrift.TLabel").grid(row=self._zeile, column=0, sticky="w",
                                                                          pady=(0 if self._zeile == 0 else 18, 2))
        self._zeile += 1
        if erklaerung:
            stil.erklaerung(self.innen, erklaerung).grid(row=self._zeile, column=0, sticky="w", pady=(0, 6))
            self._zeile += 1

    def feld(self, name: str, eltern=None, steuer=None) -> ttk.Frame:
        """Zeile für ein Feld: Titel (+ ↻), Eingabe (Standard je Art oder `steuer(rahmen)`), Fehler, Erklärung."""
        f = daten.FELDER[name]
        eltern = eltern or self.innen
        z = ttk.Frame(eltern)
        z.grid(row=self._zeile, column=0, sticky="we", pady=(10, 0))
        self._zeile += 1
        z.columnconfigure(0, weight=1)
        kopf = ttk.Frame(z)
        kopf.grid(row=0, column=0, sticky="w")
        if name not in self.var:
            self.var[name] = tk.BooleanVar() if f.art == "bool" else tk.StringVar()
            self.var[name].trace_add("write", self._geaendert_cb(name))
        if f.art != "bool":
            ttk.Label(kopf, text=f.titel, style="Titel.TLabel").pack(side="left")
        elif steuer is None:  # Schalter steht selbst in der Kopfzeile, Hinweis dahinter
            ttk.Checkbutton(kopf, text=f.titel, variable=self.var[name], style="Switch.TCheckbutton").pack(side="left")
        if f.neustart:
            ttk.Label(kopf, text="  ↻ greift nach Neustart", style="Neustart.TLabel").pack(side="left")
        if steuer is not None:
            steuer(z).grid(row=1, column=0, sticky="w", pady=(4, 0))
        elif f.art == "bool":
            pass  # oben in der Kopfzeile
        elif f.art == "wahl":
            box = ttk.Combobox(z, values=[a for _, a in f.wahl], state="readonly", width=48)
            werte = [w for w, _ in f.wahl]

            def von_box(_e=None, box=box, werte=werte, name=name):
                self.var[name].set(werte[box.current()])

            def zu_box(*_a, box=box, werte=werte, name=name):
                v = self.var[name].get()
                if v in werte and box.current() != werte.index(v):
                    box.current(werte.index(v))
            box.bind("<<ComboboxSelected>>", von_box)
            self.var[name].trace_add("write", zu_box)
            box.grid(row=1, column=0, sticky="w", pady=(4, 0))
        else:
            zeile = ttk.Frame(z)
            zeile.grid(row=1, column=0, sticky="w", pady=(4, 0))
            ttk.Entry(zeile, textvariable=self.var[name], width=12 if f.art == "zahl" else 40).pack(side="left")
            if f.einheit:
                ttk.Label(zeile, text=f.einheit).pack(side="left", padx=(6, 0))
        self._fehler_label[name] = ttk.Label(z, style="Fehler.TLabel")
        self._fehler_label[name].grid(row=2, column=0, sticky="w")
        self._fehler_label[name].grid_remove()  # nur sichtbar, wenn es einen Fehler gibt
        stil.erklaerung(z, f.erklaerung).grid(row=3, column=0, sticky="w")
        self._zeilen[name] = z
        return z

    def _geaendert_cb(self, name):
        def cb(*_):
            if not self._laedt:
                self.angefasst.add(name)
            meldung = self._feldfehler(name)
            if name in self._fehler_label:
                lab = self._fehler_label[name]
                lab.configure(text=meldung or "")
                (lab.grid if meldung else lab.grid_remove)()
            self.melden()
        return cb

    # --- Werte ----------------------------------------------------------------------------------------------------
    def _datei(self) -> Path:
        return self.fenster.dateien["config"]

    def _setze_var(self, name, wert):
        f = daten.FELDER[name]
        if f.art == "bool":
            self.var[name].set(bool(wert))
        elif f.art == "liste":
            self.var[name].set(", ".join(wert))
        elif f.art == "zahl":
            self.var[name].set(f"{wert:g}".replace(".", ","))
        else:
            self.var[name].set(str(wert))

    def wert(self, name):
        """Aktueller Wert aus der Eingabe, umgewandelt in den Typ des Felds (Zahlen bleiben als Text, falls ungültig)."""
        f = daten.FELDER[name]
        roh = self.var[name].get()
        if f.art == "liste":
            return [w.strip() for w in str(roh).split(",") if w.strip()]
        if f.art == "zahl":
            try:
                return daten.zahl(roh)
            except ValueError:
                return roh
        return roh

    def laden(self):
        self.angefasst.clear()
        self._lesen(alle=True, zeige_fehler=True)

    def aktualisieren(self):
        try:
            mtime = self._datei().stat().st_mtime
        except OSError:
            return
        if mtime != self._mtime:
            self._lesen(alle=False, zeige_fehler=False)

    def _lesen(self, alle: bool, zeige_fehler: bool):
        """Werte aus der Datei: `original` immer, Eingaben nur für nicht angefasste Felder (oder alle)."""
        try:
            self._mtime = self._datei().stat().st_mtime
            werte = daten.lies_werte(self._datei().read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            if zeige_fehler:
                self.fenster.zeige_fehler(f"config.toml lässt sich nicht lesen: {e}")
            return
        self._laedt = True
        try:
            for name in self.felder:
                self.original[name] = werte[name]
                if name in self.var and (alle or name not in self.angefasst):
                    self._setze_var(name, werte[name])
        finally:
            self._laedt = False
        self.melden()

    def _feldfehler(self, name) -> str | None:
        return daten.pruefe_wert(name, self.wert(name))

    def aenderungen(self) -> dict[str, object]:
        return {n: self.wert(n) for n in self.felder
                if n in self.var and n in self.angefasst and self.wert(n) != self.original.get(n)}

    def geaendert(self) -> bool:
        return bool(self.aenderungen())

    def fehler(self) -> dict[str, str]:
        return {n: m for n in self.aenderungen() if (m := self._feldfehler(n))}

    def uebernehmen(self) -> list[str]:
        aend = self.aenderungen()
        if not aend:
            return []
        datei = self._datei()
        schreibe_atomar(datei, daten.schreibe_werte(datei.read_text(encoding="utf-8"), aend))
        self.original.update(aend)
        self.angefasst.clear()
        self._mtime = datei.stat().st_mtime
        self.melden()
        return list(aend)


class Fenster:
    def __init__(self, root: tk.Tk, dateien: dict[str, Path] | None = None):
        self.root = root
        self.dateien = {**STANDARD_DATEIEN, **(dateien or {})}
        root.title(TITEL)
        breite = min(stil.px(900), int(root.winfo_screenwidth() * 0.9))
        hoehe = min(stil.px(720), int(root.winfo_screenheight() * 0.85))
        root.geometry(f"{breite}x{hoehe}")
        root.minsize(stil.px(700), stil.px(480))
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(12, 0))
        self.reiter: list[Reiter] = []
        for modul, klasse in REITER:
            try:
                k = getattr(importlib.import_module(f"diktat.einstellungen.{modul}"), klasse)
            except ModuleNotFoundError:
                continue
            r = k(self.notebook, self)
            self.reiter.append(r)
            self.notebook.add(r, text=r.titel)
        unten = ttk.Frame(root, padding=12)
        unten.pack(fill="x")
        self.status = ttk.Label(unten, style="Erklaerung.TLabel")
        self.status.pack(side="left")
        ttk.Button(unten, text="Abbrechen", command=self.schliessen).pack(side="right")
        ttk.Button(unten, text="Übernehmen", command=self.uebernehmen).pack(side="right", padx=(0, 8))
        ttk.Button(unten, text="OK", style="Accent.TButton", command=self.ok).pack(side="right", padx=(0, 8))
        root.protocol("WM_DELETE_WINDOW", self.schliessen)
        root.report_callback_exception = self._callback_fehler
        for r in self.reiter:
            r.laden()
        self._auffrischen()

    def _callback_fehler(self, art, wert, tb):
        """Fehler in einem Klick: ins Log und anzeigen, statt still nichts zu tun."""
        log.error("Fehler im Einstellungsfenster", exc_info=(art, wert, tb))
        self.zeige_fehler(f"Da ist etwas schiefgegangen:\n{wert}\n\nDetails stehen in logs\\einstellungen.log.")

    def _auffrischen(self):
        """Alle 2 s: Hat jemand (Symbol-Menü, merke Textfeld, Editor) die Dateien geändert? Dann nicht angefasste
        Werte im Fenster nachziehen."""
        for r in self.reiter:
            try:
                r.aktualisieren()
            except Exception:  # noqa: BLE001
                log.exception("Auffrischen fehlgeschlagen")
        try:
            self.root.after(2000, self._auffrischen)
        except tk.TclError:
            pass

    def zeige_reiter(self, titel: str) -> None:
        for r in self.reiter:
            if r.titel.lower() == titel.lower():
                self.notebook.select(r)

    # --- für Tests ersetzbar ---------------------------------------------------------------------------------------
    def frage(self, titel: str, text: str) -> bool | None:
        return messagebox.askyesnocancel(titel, text, parent=self.root)

    def zeige_fehler(self, text: str) -> None:
        messagebox.showerror("Einstellungen", text, parent=self.root)

    def zeige_info(self, text: str) -> None:
        messagebox.showinfo("Einstellungen", text, parent=self.root)

    # --- Ablauf ---------------------------------------------------------------------------------------------------
    def markiere(self, reiter: Reiter) -> None:
        if reiter not in self.reiter:
            return
        self.notebook.tab(reiter, text=reiter.titel + (" •" if reiter.geaendert() else ""))

    def uebernehmen(self) -> bool:
        for r in self.reiter:
            r.aktualisieren()  # gegen den aktuellen Dateistand vergleichen
        fehler = {f"{r.titel}: {daten.FELDER[n].titel if n in daten.FELDER else n}": m
                  for r in self.reiter for n, m in r.fehler().items()}
        if fehler:
            self.zeige_fehler("Bitte zuerst korrigieren:\n\n" + "\n".join(f"• {k} – {m}" for k, m in fehler.items()))
            return False
        geaendert, gespeichert = [], False
        for r in self.reiter:
            if not r.geaendert():
                continue
            gespeichert = True
            try:
                geaendert += r.uebernehmen()
            except (OSError, ValueError) as e:
                log.exception("Speichern fehlgeschlagen")
                self.zeige_fehler(f"{r.titel} konnte nicht gespeichert werden:\n{e}")
                return False
            self.markiere(r)
        self.status.configure(text="Gespeichert. Das Tool übernimmt die Änderungen in wenigen Sekunden."
                              if gespeichert else "Keine Änderungen.")
        spaeter = [n for n in geaendert if n in daten.FELDER and daten.FELDER[n].neustart]
        if spaeter:
            self.neustart_anbieten(spaeter)
        return True

    def neustart_anbieten(self, felder: list[str]) -> None:
        namen = ", ".join(daten.FELDER[n].titel for n in felder)
        if os.environ.get("DIKTAT_WAECHTER") != "1":
            self.zeige_info(f"{namen}: greift nach einem Neustart von whisper-diktat. Bitte das Tool beenden und "
                            "neu starten.")
            return
        if self.frage("Neu starten?", f"{namen} greift erst nach einem Neustart.\n\nwhisper-diktat jetzt neu "
                      "starten? (dauert ein paar Sekunden)"):
            if not neustart_ausloesen():
                self.zeige_info("whisper-diktat läuft gerade nicht. Die Änderung gilt beim nächsten Start.")

    def ok(self):
        if self.uebernehmen():
            self.root.destroy()

    def schliessen(self):
        if any(r.geaendert() for r in self.reiter):
            antwort = self.frage("Änderungen speichern?", "Es gibt ungespeicherte Änderungen. Speichern?")
            if antwort is None:
                return
            if antwort and not self.uebernehmen():
                return
        self.root.destroy()


def neustart_ausloesen() -> bool:
    """Benanntes Ereignis setzen, auf das das Tool wartet. False, wenn das Tool nicht läuft."""
    k32 = ctypes.windll.kernel32
    k32.OpenEventW.restype = ctypes.c_void_p
    h = k32.OpenEventW(0x0002, False, NEUSTART_EREIGNIS)  # EVENT_MODIFY_STATE
    if not h:
        return False
    try:
        return bool(k32.SetEvent(ctypes.c_void_p(h)))
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))
