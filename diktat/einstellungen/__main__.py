"""Start des Einstellungsfensters: python -m diktat.einstellungen [--reiter Name]
(das Tool startet es über das Symbol-Menü).

Nur ein Fenster gleichzeitig: Ist es schon offen, kommt das vorhandene nach vorne und dieser Prozess endet.
"""
import ctypes
import sys
import tkinter as tk

from . import stil
from .fenster import TITEL, Fenster

MUTEX = "Local\\whisper-diktat-einstellungen"
_mutexe = []  # Handles offen halten, solange der Prozess läuft


def _mutex_belegt(name: str) -> bool:
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = ctypes.c_void_p
    h = k32.CreateMutexW(None, False, name)
    belegt = k32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    _mutexe.append(h)
    return belegt


def einzige_instanz() -> bool:
    return not _mutex_belegt(MUTEX)


def nach_vorne() -> None:
    u = ctypes.windll.user32
    u.FindWindowW.restype = ctypes.c_void_p
    h = u.FindWindowW(None, TITEL)
    if h:
        u.ShowWindow(ctypes.c_void_p(h), 9)  # SW_RESTORE
        u.SetForegroundWindow(ctypes.c_void_p(h))


def _symbol(root: tk.Tk) -> None:
    try:
        from PIL import ImageTk
        from ..tray import _bild
        root._symbol = ImageTk.PhotoImage(_bild("bereit"))  # Referenz halten
        root.iconphoto(True, root._symbol)
    except Exception:  # noqa: BLE001
        pass


def _logging() -> None:
    """Eigenes Log für das Fenster (unter pythonw gäbe es sonst keine Fehlerausgabe)."""
    import logging
    from logging.handlers import RotatingFileHandler
    from .. import PROJEKT
    try:
        (PROJEKT / "logs").mkdir(exist_ok=True)
        h = RotatingFileHandler(PROJEKT / "logs" / "einstellungen.log", maxBytes=500_000, backupCount=1,
                                encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        logging.basicConfig(level=logging.INFO, handlers=[h])
    except OSError:
        pass


def main() -> int:
    _logging()
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # scharfe Schrift bei 150 %
    except (AttributeError, OSError):
        pass
    if not einzige_instanz():
        nach_vorne()
        return 0
    root = tk.Tk()
    stil.einrichten(root)
    _symbol(root)
    f = Fenster(root)
    if "--reiter" in sys.argv[1:-1]:  # z. B. --reiter Befehle
        f.zeige_reiter(sys.argv[sys.argv.index("--reiter") + 1])
    root.lift()
    root.focus_force()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
