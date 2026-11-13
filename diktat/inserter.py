"""Text dort einfügen, wo der Cursor steht.

"tippen": Der Text geht als Unicode-Tastatureingabe (SendInput, KEYEVENTF_UNICODE) raus. Das ist schnell,
          und die Zwischenablage bleibt unberührt.
"zwischenablage": Der Text kommt in die Zwischenablage (vom Windows-Verlauf Win+V ausgeschlossen), dann Strg+V,
          danach wird der alte Text wiederhergestellt. Liegt etwas anderes als Text in der Zwischenablage
          (z. B. ein Bild), wird stattdessen getippt, damit nichts verloren geht.
"""
import ctypes
import logging
import time
from ctypes import wintypes

from .hotkey import gedrueckte_modifier, parse_shortcut

log = logging.getLogger(__name__)
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INPUT_KEYBOARD, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 1, 0x2, 0x4
VK_CONTROL, VK_V = 0x11, 0x56
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x2


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.CountClipboardFormats.restype = ctypes.c_int
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

CF_KEIN_VERLAUF = user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")


def _key(vk=0, scan=0, flags=0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, u=_U(ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags)))


def _send(inputs: list) -> None:
    arr = (INPUT * len(inputs))(*inputs)
    gesendet = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if gesendet != len(inputs):
        raise OSError(f"SendInput: nur {gesendet}/{len(inputs)} Eingaben gesendet "
                      f"(Fehler {ctypes.get_last_error()}; Zielprogramm evtl. als Administrator gestartet)")


def warte_bis_tasten_los(max_s: float = 3.0) -> None:
    """Solange Strg/Alt/Umschalt/Win gedrückt sind, würde getippter Text zu Shortcuts werden."""
    ende = time.monotonic() + max_s
    while gedrueckte_modifier() and time.monotonic() < ende:
        time.sleep(0.02)


def tippe(text: str) -> None:
    inputs = []
    raw = text.encode("utf-16-le")
    for i in range(0, len(raw), 2):  # UTF-16-Einheiten, damit auch Emojis/Sonderzeichen gehen
        einheit = int.from_bytes(raw[i:i + 2], "little")
        inputs.append(_key(scan=einheit, flags=KEYEVENTF_UNICODE))
        inputs.append(_key(scan=einheit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    # In Blöcken senden, damit langsame Programme nicht überlaufen
    for i in range(0, len(inputs), 400):
        _send(inputs[i:i + 400])
        if len(inputs) > 400:
            time.sleep(0.01)


def _oeffne_zwischenablage() -> bool:
    for _ in range(20):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def _lies_text() -> tuple[str | None, bool]:
    """(Text oder None, nur_text). nur_text=False, wenn etwas anderes als Text in der Zwischenablage liegt."""
    if not _oeffne_zwischenablage():
        raise OSError("Zwischenablage ist belegt")
    try:
        if user32.CountClipboardFormats() == 0:
            return None, True
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None, False
        h = user32.GetClipboardData(CF_UNICODETEXT)
        p = kernel32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p), True
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def _setze_text(text: str | None) -> None:
    if not _oeffne_zwischenablage():
        raise OSError("Zwischenablage ist belegt")
    try:
        user32.EmptyClipboard()
        if text is None:
            return
        daten = (text + "\0").encode("utf-16-le")
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(daten))
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, daten, len(daten))
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(CF_UNICODETEXT, h)
        # Markierung: nicht in den Zwischenablage-Verlauf (Win+V) und nicht in die Cloud-Synchronisierung
        h2 = kernel32.GlobalAlloc(GMEM_MOVEABLE, 4)
        user32.SetClipboardData(CF_KEIN_VERLAUF, h2)
    finally:
        user32.CloseClipboard()


def ueber_zwischenablage(text: str) -> None:
    alt, nur_text = _lies_text()
    if not nur_text:
        log.info("Zwischenablage enthält Nicht-Text (z. B. Bild): tippe stattdessen")
        tippe(text)
        return
    _setze_text(text)
    _send([_key(VK_CONTROL), _key(VK_V), _key(VK_V, flags=KEYEVENTF_KEYUP),
           _key(VK_CONTROL, flags=KEYEVENTF_KEYUP)])
    time.sleep(0.3)  # Zielprogramm liest die Zwischenablage verzögert
    _setze_text(alt)


MODIFIER_VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B}
MODIFIER_REIHENFOLGE = ("ctrl", "alt", "shift", "win")
# Diese Tasten brauchen das Erweitert-Flag, sonst kommen sie bei manchen Programmen als Ziffernblock an
ERWEITERT = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}
KEYEVENTF_EXTENDEDKEY = 0x0001


def druecke(kombi: str) -> None:
    """Tastenkombination(en) drücken, z. B. "ctrl+z" oder "shift+enter shift+enter" (nacheinander)."""
    warte_bis_tasten_los()  # sonst wird aus Enter bei noch gehaltenem Strg ein Strg+Enter
    for teil in kombi.split():
        mods, key = parse_shortcut(teil)
        if key is None:
            raise ValueError(f"'{teil}': es fehlt eine normale Taste")
        vks = [MODIFIER_VK[m] for m in MODIFIER_REIHENFOLGE if m in mods]
        flag = KEYEVENTF_EXTENDEDKEY if key in ERWEITERT else 0
        inputs = [_key(vk) for vk in vks]
        inputs += [_key(key, flags=flag), _key(key, flags=flag | KEYEVENTF_KEYUP)]
        inputs += [_key(vk, flags=KEYEVENTF_KEYUP) for vk in reversed(vks)]
        _send(inputs)


INPUT_MOUSE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0, 0x0002, 0x0004


def _lies_maus() -> tuple[int, int]:
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def _setze_maus(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))


def klicke(x: int, y: int) -> None:
    """Linksklick an Bildschirmposition (x, y); der Mauszeiger kommt danach an seine alte Stelle zurück."""
    warte_bis_tasten_los()  # sonst wird aus dem Klick bei gehaltenem Strg ein Strg+Klick
    alt = _lies_maus()
    _setze_maus(x, y)
    try:
        _send([INPUT(type=INPUT_MOUSE, u=_U(mi=MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTDOWN))),
               INPUT(type=INPUT_MOUSE, u=_U(mi=MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTUP)))])
    finally:
        _setze_maus(*alt)


def fuege_ein(text: str, modus: str) -> None:
    warte_bis_tasten_los()
    if modus == "zwischenablage":
        ueber_zwischenablage(text)
    else:
        tippe(text)
