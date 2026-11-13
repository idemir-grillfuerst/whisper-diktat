"""Globaler Push-to-Talk-Shortcut über einen Win32-Tastatur-Hook (WH_KEYBOARD_LL).

Warum kein RegisterHotKey: Es meldet nur das Drücken, nicht das Loslassen.

Wichtig: Windows entfernt einen Low-Level-Hook still, wenn die Callback-Funktion zu lange braucht.
Die Callback-Funktion tut deshalb nur das Nötigste und reicht Ereignisse über einen Callback weiter,
der sofort zurückkehren muss (z. B. queue.put_nowait). Aufwendige Arbeit (Whisper) läuft in einem eigenen
Prozess, damit der GIL den Hook nie blockiert.

Ereignisse: "press" (Aufnahme starten), "release" (stoppen), "cancel" (verwerfen).
"""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_QUIT = 0x12
WM_ERNEUERN = 0x8000 + 1  # WM_APP + 1: Hook neu setzen
LLKHF_INJECTED = 0x10
LRESULT = ctypes.c_ssize_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

# Zusatztasten: Gruppe -> virtuelle Tastencodes (allgemein, links, rechts)
MODIFIER = {
    "ctrl": (0x11, 0xA2, 0xA3),
    "shift": (0x10, 0xA0, 0xA1),
    "alt": (0x12, 0xA4, 0xA5),
    "win": (0x5B, 0x5C),
}
VK_ZU_GRUPPE = {vk: g for g, vks in MODIFIER.items() for vk in vks}
ALIASE = {"strg": "ctrl", "control": "ctrl", "umschalt": "shift", "menu": "alt"}
SONDERTASTEN = {"space": 0x20, "leertaste": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
                "pause": 0x13, "insert": 0x2D, "einfg": 0x2D, "capslock": 0x14,
                # für Sprachbefehle (befehle.toml)
                "backspace": 0x08, "delete": 0x2E, "entf": 0x2E, "left": 0x25, "up": 0x26, "right": 0x27,
                "down": 0x28, "home": 0x24, "pos1": 0x24, "end": 0x23, "ende": 0x23, "pageup": 0x21,
                "pagedown": 0x22, ".": 0xBE}


def parse_shortcut(text: str) -> tuple[frozenset, int | None]:
    """'ctrl+y' -> ({'ctrl'}, 0x59); 'ctrl+shift' -> ({'ctrl','shift'}, None)."""
    mods, key = set(), None
    for teil in text.lower().replace(" ", "").split("+"):
        teil = ALIASE.get(teil, teil)
        if teil in MODIFIER:
            mods.add(teil)
        elif key is not None:
            raise ValueError(f"Shortcut '{text}': nur eine normale Taste erlaubt")
        elif len(teil) == 1 and teil.isalnum():
            key = ord(teil.upper())
        elif teil.startswith("f") and teil[1:].isdigit() and 1 <= int(teil[1:]) <= 24:
            key = 0x6F + int(teil[1:])
        elif teil in SONDERTASTEN:
            key = SONDERTASTEN[teil]
        else:
            raise ValueError(f"Shortcut '{text}': unbekannte Taste '{teil}'")
    if key is None and len(mods) < 2:
        raise ValueError(f"Shortcut '{text}': nur Zusatztasten geht erst ab zwei Tasten (z. B. ctrl+shift)")
    return frozenset(mods), key


VK_MASKE = 0xE8           # von Windows nicht belegte Taste
KEYEVENTF_KEYUP = 0x0002


def startmenue_unterdruecken() -> None:
    """Schickt eine unbelegte Taste (Druck + Loslassen), während die Windows-Taste gehalten wird.

    Windows öffnet das Startmenü, wenn die Win-Taste ohne eine weitere Taste losgelassen wird. Bei Shortcuts nur aus
    Zusatztasten (z. B. Strg+Win) sieht Windows sonst genau das. Die Maske zählt als „weitere Taste“, Programme
    ignorieren sie (gleiche Technik wie AutoHotkey). Unser eigener Hook ignoriert sie, weil sie injiziert ist.
    """
    user32.keybd_event(VK_MASKE, 0, 0, 0)
    user32.keybd_event(VK_MASKE, 0, KEYEVENTF_KEYUP, 0)


def _gedrueckt(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def gedrueckte_modifier(ausser_vk: int | None = None) -> set:
    """Welche Zusatztasten-Gruppen gerade physisch gedrückt sind."""
    return {g for g, vks in MODIFIER.items() if any(_gedrueckt(v) for v in vks if v != ausser_vk)}


class PushToTalk:
    def __init__(self, shortcut: str, callback):
        self.mods, self.key = parse_shortcut(shortcut)
        self.callback = callback
        self.aktiv = False          # gerade wird aufgenommen
        self.eingeschaltet = True   # False = pausiert, Tasten gehen normal durch
        self.hook_ausfaelle = 0     # wie oft der Wachhund einen toten Hook bemerkt hat
        self._vom_wachhund = False  # press kam vom Wachhund statt vom Hook
        self._taste_schlucken = False  # Haupttaste nach Diktat-Ende noch gedrückt: Wiederholungen bis Loslassen schlucken
        self._laeuft = False
        self._thread = None
        self._wachhund_thread = None
        self._thread_id = None
        self._hook = None
        self._proc = HOOKPROC(self._hook_proc)  # Referenz halten, sonst räumt Python sie weg
        self._startmenue_unterdruecken = startmenue_unterdruecken  # in Tests austauschbar

    # --- Hook-Callback: muss schnell sein -------------------------------------------------
    def _hook_proc(self, n_code, w_param, l_param):
        try:
            if n_code == 0 and self.eingeschaltet:
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not kb.flags & LLKHF_INJECTED:  # eigene Eingaben (Tippen/Strg+V) ignorieren
                    unten = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    if self._verarbeite(kb.vkCode, unten):
                        return 1  # Taste schlucken
        except Exception:  # niemals eine Ausnahme in den Hook laufen lassen
            log.exception("Fehler im Tastatur-Hook")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _melde(self, ereignis):
        try:
            self.callback(ereignis)
        except Exception:
            log.exception("Fehler beim Weiterreichen von %s", ereignis)

    def _verarbeite(self, vk: int, unten: bool) -> bool:
        gruppe = VK_ZU_GRUPPE.get(vk)

        if self.key is not None:  # Variante: Zusatztasten + normale Taste (z. B. Strg+Y)
            if vk == self.key:
                if self._taste_schlucken:
                    # Strg wurde vor Y losgelassen: Die Y-Wiederholungen dürfen nicht als „yyyy“ im Text landen
                    if not unten:
                        self._taste_schlucken = False
                    return True
                if unten:
                    if self.aktiv:
                        return True  # Tastenwiederholung beim Halten schlucken
                    if gedrueckte_modifier() == set(self.mods):
                        self.aktiv = True
                        self._melde("press")
                        return True
                    return False
                if self.aktiv:
                    self.aktiv = False
                    self._vom_wachhund = False
                    self._melde("release")
                    return True
                return False
            if gruppe in self.mods and not unten and self.aktiv:
                # Zusatztaste vor der Haupttaste losgelassen: Aufnahme beenden, Zusatztaste durchlassen,
                # die noch gehaltene Haupttaste bis zu ihrem Loslassen schlucken
                self.aktiv = False
                self._vom_wachhund = False
                self._taste_schlucken = _gedrueckt(self.key)
                self._melde("release")
            return False

        # Variante: nur Zusatztasten (z. B. Strg+Umschalt). Nie schlucken.
        if gruppe is not None:
            if unten and not self.aktiv:
                if gedrueckte_modifier(ausser_vk=vk) | {gruppe} == set(self.mods):
                    self.aktiv = True
                    if "win" in self.mods:
                        self._startmenue_unterdruecken()
                    self._melde("press")
            elif not unten and self.aktiv and gruppe in self.mods:
                self.aktiv = False
                self._vom_wachhund = False
                self._melde("release")
        elif unten and self.aktiv:
            # Andere Taste gedrückt (z. B. Strg+Umschalt+T): war kein Diktat
            self.aktiv = False
            self._melde("cancel")
        return False

    # --- Thread mit Nachrichtenschleife -------------------------------------------------------
    def _setze_hook(self) -> bool:
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            log.error("Tastatur-Hook konnte nicht gesetzt werden (Fehler %s)", ctypes.get_last_error())
            return False
        return True

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        if not self._setze_hook():
            return
        log.info("Tastatur-Hook aktiv")
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_ERNEUERN:
                # Windows entfernt Low-Level-Hooks still, wenn sie einmal zu langsam waren. Darum regelmäßig
                # neu setzen: erst den neuen setzen, dann den alten entfernen, damit keine Lücke entsteht.
                alt = self._hook
                if self._setze_hook():
                    user32.UnhookWindowsHookEx(alt)
                    log.debug("Tastatur-Hook erneuert")
                else:
                    self._hook = alt
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        log.info("Tastatur-Hook entfernt")

    def erneuern(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_ERNEUERN, 0, 0)

    # --- Wachhund: erkennt einen still entfernten Hook --------------------------------------
    def _kombi_gedrueckt(self) -> bool:
        """Ist der Shortcut gerade physisch gedrückt? (direkt am Tastaturzustand, unabhängig vom Hook)"""
        if gedrueckte_modifier() != set(self.mods):
            return False
        return self.key is None or _gedrueckt(self.key)

    def _wachhund_schritt(self, gedrueckt: bool, seit: float | None, jetzt: float) -> float | None:
        """Ein Prüfschritt. Gibt den neuen 'seit'-Zeitpunkt zurück (separat für Tests)."""
        if self._taste_schlucken:
            # Nachlauf der gehaltenen Haupttaste: keinen toten Hook vermuten. Ist die Taste physisch los,
            # aber das Loslassen kam nie beim Hook an, Schlucken beenden (sonst wäre „y“ dauerhaft blockiert).
            if self.key is None or not _gedrueckt(self.key):
                self._taste_schlucken = False
            return None
        if not self.eingeschaltet:
            return None
        if self.aktiv:
            if self._vom_wachhund and not gedrueckt:  # Hook tot: Loslassen selbst erkennen
                self.aktiv = False
                self._vom_wachhund = False
                self._melde("release")
            return None
        if not gedrueckt:
            return None
        if seit is None:
            return jetzt
        if jetzt - seit >= 0.25:
            # Shortcut gedrückt, aber der Hook hat nichts gemeldet: Windows hat ihn entfernt.
            self.hook_ausfaelle += 1
            log.warning("Tastatur-Hook reagiert nicht (Ausfall %d) – setze ihn neu und starte die Aufnahme",
                        self.hook_ausfaelle)
            self.erneuern()
            self.aktiv = True
            self._vom_wachhund = True
            self._melde("press")
            return None
        return seit

    def _wachhund(self):
        seit = None
        while self._laeuft:
            time.sleep(0.1)
            try:
                seit = self._wachhund_schritt(self._kombi_gedrueckt(), seit, time.monotonic())
            except Exception:  # noqa: BLE001
                log.exception("Fehler im Hotkey-Wachhund")

    def start(self):
        self._laeuft = True
        self._thread = threading.Thread(target=self._run, name="hotkey", daemon=True)
        self._thread.start()
        self._wachhund_thread = threading.Thread(target=self._wachhund, name="hotkey-wachhund", daemon=True)
        self._wachhund_thread.start()

    def stop(self):
        self._laeuft = False
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)
