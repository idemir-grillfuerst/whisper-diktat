"""Symbol in der Taskleiste mit Menü. Die Farbe zeigt den Zustand."""
import pystray
from PIL import Image, ImageDraw

FARBEN = {
    "laedt": ((70, 130, 230), "lädt Modell …"),
    "bereit": ((140, 140, 140), "bereit"),
    "aufnahme": ((220, 40, 40), "Aufnahme läuft"),
    "verarbeitet": ((235, 170, 20), "transkribiert …"),
    "pausiert": ((190, 190, 190), "pausiert"),
    "fehler": ((40, 40, 40), "Fehler – siehe Log"),
}

STUFEN_TEXT = {
    "schnell": "Schnell – Grafik (Standard)",
    "leise": "Leise – NPU, sparsam",
    "genau": "Genau – großes Modell",
    "notfall": "Notfall – nur CPU",
}


def _bild(zustand) -> Image.Image:
    farbe = FARBEN[zustand][0]
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=farbe)
    weiss = "white"
    d.rounded_rectangle((24, 13, 40, 38), radius=8, fill=weiss)
    d.arc((17, 22, 47, 46), start=0, end=180, fill=weiss, width=4)
    d.line((32, 46, 32, 52), fill=weiss, width=4)
    d.line((24, 52, 40, 52), fill=weiss, width=4)
    if zustand == "pausiert":
        d.line((12, 52, 52, 12), fill=(200, 30, 30), width=7)
    return img


class Tray:
    """aktionen: Objekt mit stufe (str), stufen (list), pausiert (bool), unter_waechter (bool) und den Methoden
    waehle_stufe(name), umschalten_pause(), oeffne_fachwoerter(), oeffne_einstellungen(), oeffne_log(),
    autostart_aktiv(), umschalten_autostart(), neustart(), beenden()."""

    def __init__(self, aktionen, shortcut: str):
        self.a = aktionen
        self.shortcut = shortcut
        self._bilder = {k: _bild(k) for k in FARBEN}
        self.zustand = "laedt"
        self.detail = ""
        self.icon = pystray.Icon("whisper-diktat", self._bilder["laedt"], self._titel(), self._menue())

    def _stufen_menue(self):
        def eintrag(name):
            return pystray.MenuItem(
                STUFEN_TEXT.get(name, name),
                lambda icon, item: self.a.waehle_stufe(name),
                checked=lambda item: self.a.stufe == name,
                radio=True,
            )
        return pystray.Menu(*[eintrag(n) for n in self.a.stufen])

    def _menue(self):
        return pystray.Menu(
            pystray.MenuItem(lambda _: f"Status: {FARBEN[self.zustand][1]}", None, enabled=False),
            pystray.MenuItem(lambda _: self.detail or f"{self.shortcut.upper()} halten zum Diktieren",
                             None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda _: "Fortsetzen" if self.a.pausiert else "Pausieren",
                             lambda icon, item: self.a.umschalten_pause()),
            pystray.MenuItem("Stufe", self._stufen_menue()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Fachwörter bearbeiten …", lambda icon, item: self.a.oeffne_fachwoerter()),
            pystray.MenuItem("Einstellungen öffnen …", lambda icon, item: self.a.oeffne_einstellungen()),
            pystray.MenuItem("Log öffnen", lambda icon, item: self.a.oeffne_log()),
            pystray.MenuItem("Mit Windows starten", lambda icon, item: self.a.umschalten_autostart(),
                             checked=lambda item: self.a.autostart_aktiv()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Neu starten", lambda icon, item: self.a.neustart(),
                             visible=self.a.unter_waechter),
            pystray.MenuItem("Beenden", lambda icon, item: self.a.beenden()),
        )

    def _titel(self) -> str:
        stufe = STUFEN_TEXT.get(self.a.stufe, self.a.stufe).split(" –")[0]
        return f"Whisper-Diktat: {FARBEN[self.zustand][1]} · {stufe}"[:127]

    def setze(self, zustand: str, detail: str | None = None) -> None:
        self.zustand = zustand
        if detail is not None:
            self.detail = detail
        self.icon.icon = self._bilder[zustand]
        self.icon.title = self._titel()
        try:
            self.icon.update_menu()
        except Exception:  # noqa: BLE001  (Menü evtl. noch nicht da)
            pass

    def run(self, setup=None) -> None:
        self.icon.run(setup=setup)

    def stop(self) -> None:
        self.icon.stop()
