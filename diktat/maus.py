"""Push-to-Talk mit einer Maustaste über einen Win32-Maus-Hook (WH_MOUSE_LL).

Gedacht für das Mausrad (mittlere Taste), geht auch mit den Seitentasten (x1/x2 = „Zurück/Vor“).

Bedienung: Taste **halten** = Aufnahme, loslassen = Text einfügen. Ein kurzer Klick (unter `halten_s`) ist kein
Diktat: Die Aufnahme wird verworfen und der Klick an Windows nachgereicht. So öffnet ein Mittelklick weiter Links
in einem neuen Tab oder schließt Tabs. Was wegfällt: das automatische Scrollen per gehaltenem Mausrad.

Die Aufnahme startet sofort beim Drücken, damit kein Wortanfang verloren geht. Bei einem kurzen Klick ist das
Mikrofon also für einen Moment offen. Diese Aufnahme wird verworfen und nirgends gespeichert.

Ereignisse an den Callback: "maus_press", "maus_release" (gehalten: einfügen), "maus_cancel" (kurzer Klick).
"""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

from .hotkey import LRESULT, WM_ERNEUERN, WM_QUIT, kernel32, user32

log = logging.getLogger(__name__)

WH_MOUSE_LL = 14
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C
LLMHF_INJECTED = 0x01

# Name -> (Ereignis unten, Ereignis oben, X-Taste-Nummer, virtueller Tastencode, mouse_event unten, oben, Daten)
TASTEN = {
    "mitte": (WM_MBUTTONDOWN, WM_MBUTTONUP, 0, 0x04, 0x0020, 0x0040, 0),
    "x1": (WM_XBUTTONDOWN, WM_XBUTTONUP, 1, 0x05, 0x0080, 0x0100, 1),
    "x2": (WM_XBUTTONDOWN, WM_XBUTTONUP, 2, 0x06, 0x0080, 0x0100, 2),
}
ALIASE = {"maus3": "mitte", "mausrad": "mitte", "middle": "mitte", "maus4": "x1", "maus5": "x2"}


def parse_maustaste(text: str) -> str | None:
    """'' -> None (aus); 'mitte'/'mausrad'/'maus3' -> 'mitte'; 'maus4'/'x1', 'maus5'/'x2'."""
    t = (text or "").strip().lower()
    if not t or t in ("aus", "nein", "keine"):
        return None
    t = ALIASE.get(t, t)
    if t not in TASTEN:
        raise ValueError(f"maustaste '{text}' unbekannt (erlaubt: mitte, x1, x2 oder leer)")
    return t


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


MOUSEPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


def klick_nachreichen(taste: str) -> None:
    """Den verschluckten kurzen Klick an Windows nachreichen (injiziert, der eigene Hook ignoriert ihn)."""
    _, _, _, _, runter, hoch, daten = TASTEN[taste]
    user32.mouse_event(runter, 0, 0, daten, 0)
    user32.mouse_event(hoch, 0, 0, daten, 0)


class MausTaste:
    """Gleiche Schnittstelle wie hotkey.PushToTalk: start, stop, erneuern, eingeschaltet, aktiv, hook_ausfaelle."""

    def __init__(self, taste: str, callback, halten_s: float = 0.4, max_s: float = 300):
        self.taste = taste
        self.callback = callback
        self.halten_s = halten_s
        self.max_s = max_s
        self._zustand_gesehen = False
        self.aktiv = False
        self.eingeschaltet = True
        self.hook_ausfaelle = 0
        self._vom_wachhund = False   # Kompatibilität mit PushToTalk (wird beim Pausieren zurückgesetzt)
        self._seit = 0.0             # Zeitpunkt des Drückens
        self._laeuft = False
        self._thread = self._wachhund_thread = None
        self._thread_id = None
        self._hook = None
        self._proc = MOUSEPROC(self._hook_proc)
        self._nachreichen = klick_nachreichen  # in Tests austauschbar
        self._jetzt = time.monotonic

    # --- Hook-Callback: muss schnell sein -------------------------------------------------
    def _passt(self, w_param: int, maus_daten: int) -> str | None:
        unten, oben, x_nr = TASTEN[self.taste][:3]
        if w_param not in (unten, oben):
            return None
        if x_nr and (maus_daten >> 16) & 0xFFFF != x_nr:
            return None
        return "unten" if w_param == unten else "oben"

    def _verarbeite(self, richtung: str) -> bool:
        """True = Klick schlucken."""
        if richtung == "unten":
            if self.aktiv:
                return True
            self.aktiv = True
            self._seit = self._jetzt()
            self._melde("maus_press")
            return True
        if not self.aktiv:
            return False  # Loslassen ohne unser Drücken (z. B. vor dem Pausieren gedrückt): durchlassen
        self.aktiv = False
        if self._jetzt() - self._seit < self.halten_s:
            self._melde("maus_cancel")
            threading.Thread(target=self._nachreichen, args=(self.taste,), name="maus-klick", daemon=True).start()
        else:
            self._melde("maus_release")
        return True

    def _hook_proc(self, n_code, w_param, l_param):
        try:
            if n_code == 0 and self.eingeschaltet:
                ms = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if not ms.flags & LLMHF_INJECTED:
                    richtung = self._passt(w_param, ms.mouseData)
                    if richtung and self._verarbeite(richtung):
                        return 1
        except Exception:  # niemals eine Ausnahme in den Hook laufen lassen
            log.exception("Fehler im Maus-Hook")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _melde(self, ereignis):
        try:
            self.callback(ereignis)
        except Exception:
            log.exception("Fehler beim Weiterreichen von %s", ereignis)

    # --- Thread mit Nachrichtenschleife -------------------------------------------------------
    def _setze_hook(self) -> bool:
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            log.error("Maus-Hook konnte nicht gesetzt werden (Fehler %s)", ctypes.get_last_error())
            return False
        return True

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        if not self._setze_hook():
            return
        log.info("Maus-Hook aktiv (Taste %s halten)", self.taste)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_ERNEUERN:
                alt = self._hook
                if self._setze_hook():
                    user32.UnhookWindowsHookEx(alt)
                else:
                    self._hook = alt
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        log.info("Maus-Hook entfernt")

    def erneuern(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_ERNEUERN, 0, 0)

    # --- Wachhund: verlorenes Loslassen erkennen ----------------------------------------------
    def _wachhund_schritt(self, gedrueckt: bool, jetzt: float) -> None:
        """Ob GetAsyncKeyState eine vom Hook verschluckte Maustaste als gedrückt meldet, ist nicht garantiert.
        Darum zählt „los“ nur, wenn der Zustand während dieses Drückens schon einmal „gedrückt“ war.
        Sonst greift nur die Höchstdauer."""
        if not self.aktiv:
            self._zustand_gesehen = False
            return
        if gedrueckt:
            self._zustand_gesehen = True
        verloren = (self._zustand_gesehen and not gedrueckt and jetzt - self._seit > 1.0) \
            or jetzt - self._seit > self.max_s
        if verloren:
            # Taste ist los, aber das Loslassen kam nie beim Hook an (Hook entfernt?)
            self.aktiv = False
            self._zustand_gesehen = False
            self.hook_ausfaelle += 1
            log.warning("Maus-Hook hat das Loslassen verpasst (Ausfall %d) – setze ihn neu", self.hook_ausfaelle)
            self.erneuern()
            self._melde("maus_release")

    def _wachhund(self):
        vk = TASTEN[self.taste][3]
        while self._laeuft:
            time.sleep(0.2)
            try:
                self._wachhund_schritt(bool(user32.GetAsyncKeyState(vk) & 0x8000), self._jetzt())
            except Exception:  # noqa: BLE001
                log.exception("Fehler im Maus-Wachhund")

    def start(self):
        self._laeuft = True
        self._thread = threading.Thread(target=self._run, name="maus", daemon=True)
        self._thread.start()
        self._wachhund_thread = threading.Thread(target=self._wachhund, name="maus-wachhund", daemon=True)
        self._wachhund_thread.start()

    def stop(self):
        self._laeuft = False
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)
