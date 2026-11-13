"""Probe für den Sprachbefehl „Textfeld“: zeigt, welche Eingabefelder das Tool in einem Fenster sieht und welches es
wählen würde. Nur lesend: kein Fokus, keine Eingaben.

Aufruf (im Projektordner):
    %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.textfeld_probe            (3 s warten, dann Fenster vorne)
    %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.textfeld_probe --prozess ms-teams
"""
import ctypes
import sys
import time
from ctypes import wintypes

from diktat import textfeld, uia

user32 = ctypes.WinDLL("user32", use_last_error=True)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def hauptfenster(prozess: str) -> int:
    """Größtes sichtbares Fenster mit Titel des Prozesses."""
    gefunden = []

    def rueckruf(h, _):
        if user32.IsWindowVisible(h) and user32.GetWindowTextLengthW(h) and uia.prozessname(h) == prozess:
            l, o, r, u = uia.fenster_rect(h)
            gefunden.append(((r - l) * (u - o), h))
        return True
    user32.EnumWindows(WNDENUMPROC(rueckruf), 0)
    return max(gefunden)[1] if gefunden else 0


def zeige(hwnd: int) -> None:
    prozess = uia.prozessname(hwnd)
    schl = textfeld.schluessel(prozess, uia.adresse(hwnd) if prozess in textfeld.BROWSER else None)
    rect = uia.fenster_rect(hwnd)
    t = time.perf_counter()
    liste = uia.kandidaten(hwnd)
    ms = (time.perf_counter() - t) * 1000
    print(f"Schlüssel {schl}, Fenster {rect}, {len(liste)} Kandidaten in {ms:.0f} ms")
    for k, _ in liste:
        print(f"  {textfeld.bewerte(k, rect):6.1f}  {k.typ:8} name='{k.name[:40]}' id='{k.automation_id[:30]}' "
              f"klasse='{k.klasse[:25]}' fokus={k.fokus} {k.rect}" + ("  [Adressleiste]" if textfeld.ist_adressleiste(k) else ""))
    beste = textfeld.waehle([k for k, _ in liste], rect)
    print("  -> Wahl:", f"{beste.typ} '{beste.name}'" if beste else "keine")


if __name__ == "__main__":
    uia.thread_dpi_bewusst()
    if "--prozess" in sys.argv:
        name = sys.argv[sys.argv.index("--prozess") + 1]
        h = hauptfenster(name)
        if not h:
            sys.exit(f"Kein Fenster von {name} gefunden")
        for durchgang in (1, 2):  # Chromium schaltet die Bedienungshilfe erst bei der ersten Abfrage ein
            print(f"[{name}, Abfrage {durchgang}]")
            zeige(h)
            time.sleep(1)
    else:
        print("Fenster in 3 s nach vorne holen …")
        time.sleep(3)
        zeige(uia.fenster_vorne())
