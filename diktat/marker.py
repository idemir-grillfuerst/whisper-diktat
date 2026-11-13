"""Kurzes Bestätigungszeichen am Bildschirm: grüner Haken (ok) oder rotes Kreuz (nicht ok).

Ein rahmenloses Fenster ganz oben, durchklickbar, ohne Fokus und ohne Taskleisten-Eintrag. Es verschwindet nach
`dauer_s` von selbst. Jedes Zeichen läuft in einem eigenen kurzen Thread mit eigener Nachrichtenschleife. Koordinaten
sind echte Bildschirmpixel (der Thread läuft DPI-bewusst wie die UIA-Threads), x/y ist die Mitte des Zeichens.

Probe (zeigt Haken und Kreuz neben dem Mauszeiger):  python -m diktat.marker
"""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

from PIL import Image, ImageChops, ImageDraw

from . import uia

log = logging.getLogger("diktat")
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GRUEN, ROT = (22, 163, 74), (220, 38, 38)
GROESSE_96DPI = 36           # Durchmesser bei 100 % Skalierung
WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOPMOST = 0x00080000, 0x00000020, 0x00000008
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x00000080, 0x08000000
SW_SHOWNOACTIVATE, ULW_ALPHA, AC_SRC_ALPHA, PM_REMOVE = 4, 2, 1, 1
KLASSE = "WhisperDiktatMarker"

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                wintypes.UINT]
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HMONITOR
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte), ("SourceConstantAlpha", ctypes.c_ubyte),
                ("AlphaFormat", ctypes.c_ubyte)]


user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                       wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]

_wndproc = WNDPROC(lambda h, m, w, l: user32.DefWindowProcW(h, m, w, l))  # Referenz halten
_klasse_lock = threading.Lock()
_klasse_da = False


def _klasse() -> None:
    global _klasse_da
    with _klasse_lock:
        if _klasse_da:
            return
        wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=_wndproc,
                         hInstance=kernel32.GetModuleHandleW(None), lpszClassName=KLASSE)
        if not user32.RegisterClassExW(ctypes.byref(wc)) and ctypes.get_last_error() != 1410:  # 1410 = gibt es schon
            raise OSError(f"RegisterClassExW: Fehler {ctypes.get_last_error()}")
        _klasse_da = True


def bild(ok: bool, groesse: int) -> Image.Image:
    """Runder Kreis mit Haken bzw. Kreuz, weiß umrandet, kantengeglättet (4-fach gezeichnet, dann verkleinert)."""
    f = 4
    g = groesse * f
    im = Image.new("RGBA", (g, g), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((f, f, g - f, g - f), fill=(255, 255, 255, 255))
    rand = max(2, g // 14)
    d.ellipse((f + rand, f + rand, g - f - rand, g - f - rand), fill=(*(GRUEN if ok else ROT), 245))
    strich = max(3, g // 9)
    if ok:
        d.line([(g * 0.28, g * 0.53), (g * 0.44, g * 0.68), (g * 0.73, g * 0.36)], fill="white", width=strich,
               joint="curve")
    else:
        d.line([(g * 0.33, g * 0.33), (g * 0.67, g * 0.67)], fill="white", width=strich)
        d.line([(g * 0.67, g * 0.33), (g * 0.33, g * 0.67)], fill="white", width=strich)
    return im.resize((groesse, groesse), Image.LANCZOS)


def _bgra_vormultipliziert(im: Image.Image) -> bytes:
    r, g, b, a = im.split()
    r, g, b = (ImageChops.multiply(k, a) for k in (r, g, b))  # Windows erwartet vormultipliziertes Alpha
    return Image.merge("RGBA", (b, g, r, a)).tobytes()


def _dpi_an(x: int, y: int) -> int:
    try:
        mon = user32.MonitorFromPoint(wintypes.POINT(x, y), 2)  # MONITOR_DEFAULTTONEAREST
        dx, dy = ctypes.c_uint(), ctypes.c_uint()
        ctypes.windll.shcore.GetDpiForMonitor(mon, 0, ctypes.byref(dx), ctypes.byref(dy))
        return dx.value or 96
    except Exception:  # noqa: BLE001
        return 96


def _zeige(x: int, y: int, ok: bool, dauer_s: float) -> None:
    uia.thread_dpi_bewusst()
    _klasse()
    groesse = round(GROESSE_96DPI * _dpi_an(x, y) / 96)
    links, oben = x - groesse // 2, y - groesse // 2
    hwnd = user32.CreateWindowExW(WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
                                  | WS_EX_NOACTIVATE, KLASSE, "", WS_POPUP, links, oben, groesse, groesse,
                                  None, None, kernel32.GetModuleHandleW(None), None)
    if not hwnd:
        raise OSError(f"CreateWindowExW: Fehler {ctypes.get_last_error()}")
    bildschirm = user32.GetDC(None)
    speicher = gdi32.CreateCompatibleDC(bildschirm)
    bits = ctypes.c_void_p()
    kopf = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=groesse, biHeight=-groesse, biPlanes=1,
                            biBitCount=32)
    hbm = gdi32.CreateDIBSection(speicher, ctypes.byref(kopf), 0, ctypes.byref(bits), None, 0)
    try:
        daten = _bgra_vormultipliziert(bild(ok, groesse))
        ctypes.memmove(bits, daten, len(daten))
        alt = gdi32.SelectObject(speicher, hbm)
        user32.UpdateLayeredWindow(hwnd, bildschirm, ctypes.byref(wintypes.POINT(links, oben)),
                                   ctypes.byref(wintypes.SIZE(groesse, groesse)), speicher,
                                   ctypes.byref(wintypes.POINT(0, 0)), 0,
                                   ctypes.byref(BLENDFUNCTION(0, 0, 255, AC_SRC_ALPHA)), ULW_ALPHA)
        gdi32.SelectObject(speicher, alt)
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        ende, msg = time.monotonic() + dauer_s, wintypes.MSG()
        while time.monotonic() < ende:  # Nachrichten abholen, damit Windows das Fenster nicht für hängend hält
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.02)
    finally:
        user32.DestroyWindow(hwnd)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(speicher)
        user32.ReleaseDC(None, bildschirm)


def zeige(x: int, y: int, ok: bool, dauer_s: float = 1.5) -> threading.Thread:
    """Zeichen mit Mitte bei (x, y) zeigen, kehrt sofort zurück. Fehler werden nur geloggt."""
    def lauf():
        try:
            _zeige(int(x), int(y), ok, dauer_s)
        except Exception:  # noqa: BLE001 – ein Hinweiszeichen darf nie etwas anderes stören
            log.exception("Bestätigungszeichen ging nicht")
    t = threading.Thread(target=lauf, name="marker", daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    uia.thread_dpi_bewusst()
    mx, my = uia.maus_position()
    print("Haken und Kreuz neben dem Mauszeiger, je 1,5 s …")
    a = zeige(mx + 40, my, True)
    b = zeige(mx + 90, my, False)
    a.join()
    b.join()
    print("fertig")
