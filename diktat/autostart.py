"""Autostart bei der Windows-Anmeldung über HKCU\\...\\Run (keine Adminrechte nötig).

Gestartet wird start.pyw (Wächter -> Tool), ohne Konsolenfenster.
Aufruf von Hand:  python -m diktat.autostart [an|aus|status]

Hinweis: Aus der Claude-App heraus können Registry-Schreibzugriffe umgeleitet werden. Deshalb über das Menü
des laufenden Tools oder in einem normalen Terminal ausführen, nicht im Hintergrund-Shell der App.
"""
import sys
import winreg

from . import PROJEKT
from .waechter import pythonw

SCHLUESSEL = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "whisper-diktat"


def befehl() -> str:
    return f'"{pythonw()}" "{PROJEKT / "start.pyw"}"'


def ist_aktiv() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SCHLUESSEL) as k:
            wert, _ = winreg.QueryValueEx(k, NAME)
            return wert == befehl()
    except FileNotFoundError:
        return False


def aktivieren() -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SCHLUESSEL, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, befehl())


def deaktivieren() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SCHLUESSEL, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NAME)
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    if arg == "an":
        aktivieren()
    elif arg == "aus":
        deaktivieren()
    print(f"Autostart: {'AN' if ist_aktiv() else 'AUS'}  ({befehl()})")
