"""Zugriff auf die Windows-Bedienungshilfe (UI Automation) und Fensterabfragen für den Sprachbefehl „Textfeld“.

comtypes wird erst beim ersten Aufruf geladen. Fehlt es (alte Installation), kommt UiaFehlt, und nur „Textfeld“
geht nicht. Das UIA-Objekt gilt pro Thread (COM-Apartment), deshalb threading.local.
"""
import ctypes
import os
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]

GA_ROOT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WEBSEITEN_WURZEL = "RootWebArea"   # Document einer ganzen Webseite: kein Eingabefeld
MAX_EBENEN_HOCH = 5

_lokal = threading.local()


class UiaFehlt(RuntimeError):
    """UI Automation ist nicht verfügbar (meist: Paket comtypes fehlt)."""


def _uia():
    """(IUIAutomation, Typbibliothek) für diesen Thread."""
    if not hasattr(_lokal, "uia"):
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED; schon initialisiert ist ok
            import comtypes.client
            m = comtypes.client.GetModule("UIAutomationCore.dll")
            _lokal.uia = comtypes.client.CreateObject(m.CUIAutomation, interface=m.IUIAutomation)
            _lokal.m = m
        except (ImportError, OSError) as e:
            raise UiaFehlt(f"UI Automation nicht verfügbar: {e}") from None
    return _lokal.uia, _lokal.m


# --- Fenster -----------------------------------------------------------------------------------------------------
def fenster_vorne() -> int:
    return user32.GetForegroundWindow() or 0


def maus_position() -> tuple[int, int]:
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def fenster_unter_maus() -> int:
    x, y = maus_position()
    h = user32.WindowFromPoint(wintypes.POINT(x, y))
    return (user32.GetAncestor(h, GA_ROOT) or h or 0) if h else 0


def prozessname(hwnd: int) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        puffer = ctypes.create_unicode_buffer(1024)
        groesse = wintypes.DWORD(len(puffer))
        if not kernel32.QueryFullProcessImageNameW(h, 0, puffer, ctypes.byref(groesse)):
            return ""
        name = os.path.basename(puffer.value).lower()
        return name[:-4] if name.endswith(".exe") else name
    finally:
        kernel32.CloseHandle(h)


def fenster_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


# --- UI Automation -----------------------------------------------------------------------------------------------
def _typ(el, m) -> str | None:
    ct = el.CurrentControlType
    if ct == m.UIA_EditControlTypeId:
        return "Edit"
    if ct == m.UIA_DocumentControlTypeId and el.CurrentAutomationId != WEBSEITEN_WURZEL:
        return "Document"
    return None


def _kandidat(el, m):
    from .textfeld import Kandidat
    typ = _typ(el, m)
    if typ is None:
        return None
    r = el.CurrentBoundingRectangle
    return Kandidat(el.CurrentName or "", el.CurrentAutomationId or "", typ, el.CurrentClassName or "",
                    (r.left, r.top, r.right, r.bottom), bool(el.CurrentHasKeyboardFocus))


def _schreibgeschuetzt(el, m) -> bool:
    try:
        p = el.GetCurrentPattern(m.UIA_ValuePatternId)
        if not p:
            return False
        return bool(p.QueryInterface(m.IUIAutomationValuePattern).CurrentIsReadOnly)
    except Exception:  # noqa: BLE001 – ohne ValuePattern gilt das Feld als beschreibbar
        return False


def kandidaten(hwnd: int) -> list:
    """[(Kandidat, Element)] aller beschreibbaren, sichtbaren, fokussierbaren Edit/Document-Felder des Fensters."""
    uia, m = _uia()
    wurzel = uia.ElementFromHandle(hwnd)
    bedingung = uia.CreateOrCondition(
        uia.CreatePropertyCondition(m.UIA_ControlTypePropertyId, m.UIA_EditControlTypeId),
        uia.CreatePropertyCondition(m.UIA_ControlTypePropertyId, m.UIA_DocumentControlTypeId))
    treffer = wurzel.FindAll(m.TreeScope_Descendants, bedingung)
    liste = []
    for i in range(treffer.Length if treffer else 0):
        el = treffer.GetElement(i)
        try:
            if not el.CurrentIsKeyboardFocusable or el.CurrentIsOffscreen or _schreibgeschuetzt(el, m):
                continue
            k = _kandidat(el, m)
        except Exception:  # noqa: BLE001 – Element ist inzwischen verschwunden
            continue
        if k is not None:
            liste.append((k, el))
    return liste


def adresse(hwnd: int) -> str | None:
    """Inhalt der Browser-Adressleiste (Chrome/Edge: Klasse OmniboxViewViews, Firefox: urlbar-input)."""
    uia, m = _uia()
    try:
        wurzel = uia.ElementFromHandle(hwnd)
        bedingung = uia.CreateOrCondition(
            uia.CreatePropertyCondition(m.UIA_ClassNamePropertyId, "OmniboxViewViews"),
            uia.CreatePropertyCondition(m.UIA_AutomationIdPropertyId, "urlbar-input"))
        el = wurzel.FindFirst(m.TreeScope_Descendants, bedingung)
        if not el:
            return None
        p = el.GetCurrentPattern(m.UIA_ValuePatternId)
        return p.QueryInterface(m.IUIAutomationValuePattern).CurrentValue if p else None
    except Exception:  # noqa: BLE001
        return None


def kandidat_unter_maus():
    """(Kandidat, Element) des Eingabefelds unter dem Mauszeiger (bis 5 Ebenen nach oben) oder None."""
    uia, m = _uia()
    x, y = maus_position()
    try:
        el = uia.ElementFromPoint(m.tagPOINT(x, y))
        walker = uia.ControlViewWalker
        for _ in range(MAX_EBENEN_HOCH + 1):
            if not el:
                return None
            k = _kandidat(el, m)
            if k is not None:
                return k, el
            el = walker.GetParentElement(el)
    except Exception:  # noqa: BLE001
        return None
    return None


def fokussiere(el) -> bool:
    try:
        el.SetFocus()
        for _ in range(5):  # Chromium meldet den Fokus manchmal erst kurz danach
            if el.CurrentHasKeyboardFocus:
                return True
            time.sleep(0.04)
    except Exception:  # noqa: BLE001
        pass
    return False


def mitte(el) -> tuple[int, int]:
    r = el.CurrentBoundingRectangle
    return (r.left + r.right) // 2, (r.top + r.bottom) // 2


def vorwaermen(hwnd: int) -> None:
    """Chromium-Programme schalten ihre Bedienungshilfe erst bei der ersten Abfrage ein. Einmal kurz anfragen."""
    uia, m = _uia()
    wurzel = uia.ElementFromHandle(hwnd)
    wurzel.FindFirst(m.TreeScope_Descendants, uia.CreateTrueCondition())
