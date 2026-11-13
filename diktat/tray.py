"""Symbol in der Taskleiste mit Menü. Die Farbe zeigt den Zustand."""
import logging

import pystray
from PIL import Image, ImageDraw

from .geraete import art

FARBEN = {
    "laedt": ((70, 130, 230), "lädt Modell …"),
    "bereit": ((140, 140, 140), "bereit"),
    "aufnahme": ((220, 40, 40), "Aufnahme läuft"),
    "verarbeitet": ((235, 170, 20), "transkribiert …"),
    "pausiert": ((190, 190, 190), "pausiert"),
    "ruht": ((175, 175, 175), "ruht (Modell entladen)"),
    "fehler": ((40, 40, 40), "Fehler – siehe Log"),
}

MODUS_TEXT = {
    "halten": "Halten – sprechen, solange gedrückt",
    "umschalten": "Umschalten – tippen = Start/Stopp",
    "beides": "Beides – halten oder kurz tippen",
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
    if zustand == "ruht":  # kleiner blauer Mond: schläft, wacht beim nächsten Diktat auf
        d.ellipse((40, 2, 62, 24), fill=(70, 130, 230))
        d.ellipse((47, 0, 66, 19), fill=(0, 0, 0, 0))
    return img


def _anzeige(name: str) -> str:
    return name.replace("®", "").replace("  ", " ")


class Tray:
    """aktionen: Objekt mit
    Attributen: modell, modelle (dict name -> Modell mit .titel), geraet_wahl, geraet, recheneinheiten
    (list[(id, name)]), mikrofon, modus, pausiert, unter_waechter
    Methoden: waehle_modell, waehle_geraet, waehle_mikrofon, mikrofone(), aktuelles_mikrofon(), waehle_modus,
    umschalten_pause, oeffne_fachwoerter, oeffne_einstellungen, oeffne_log, autostart_aktiv,
    umschalten_autostart, neustart, beenden, bedien_hinweis."""

    def __init__(self, aktionen, shortcut: str):
        self.a = aktionen
        self.shortcut = shortcut
        self._bilder = {k: _bild(k) for k in FARBEN}
        self.zustand = "laedt"
        self.detail = ""
        self.icon = pystray.Icon("whisper-diktat", self._bilder["laedt"], self._titel(), self._menue())

    # --- Untermenüs ---------------------------------------------------------------------------
    def _radio(self, text, aktion, ist_aktiv):
        return pystray.MenuItem(text, lambda icon, item: aktion(), checked=lambda item: ist_aktiv(), radio=True)

    def _modell_menue(self):
        return pystray.Menu(*[
            self._radio(m.titel, (lambda n=n: self.a.waehle_modell(n)), (lambda n=n: self.a.modell == n))
            for n, m in self.a.modelle.items()
        ])

    def _geraet_menue(self):
        eintraege = [self._radio(lambda _: f"Automatisch (jetzt {art(self.a.geraet)})",
                                 lambda: self.a.waehle_geraet("auto"), lambda: self.a.geraet_wahl == "auto")]
        for g, name in self.a.recheneinheiten:
            text = f"{art(g)} – {name}" + ("  (erstes Laden dauert Minuten)" if g.startswith("NPU") else "")
            eintraege.append(self._radio(text, (lambda g=g: self.a.waehle_geraet(g)),
                                         (lambda g=g: self.a.geraet_wahl == g)))
        return pystray.Menu(*eintraege)

    def _mikrofon_menue(self):
        eintraege = [self._radio(lambda _: f"Windows-Standard (jetzt {_anzeige(self.a.aktuelles_mikrofon())})",
                                 lambda: self.a.waehle_mikrofon(""), lambda: self.a.mikrofon == "")]
        namen = list(self.a.mikrofone())
        if self.a.mikrofon and self.a.mikrofon not in namen:
            namen.append(self.a.mikrofon)  # gewählt, aber gerade nicht angeschlossen
        for n in namen:
            text = _anzeige(n) + ("  (nicht angeschlossen)" if n not in self.a.mikrofone() else "")
            eintraege.append(self._radio(text, (lambda n=n: self.a.waehle_mikrofon(n)),
                                         (lambda n=n: self.a.mikrofon == n)))
        return pystray.Menu(*eintraege)

    def _modus_menue(self):
        return pystray.Menu(*[
            self._radio(text, (lambda m=m: self.a.waehle_modus(m)), (lambda m=m: self.a.modus == m))
            for m, text in MODUS_TEXT.items()
        ])

    def _menue(self):
        return pystray.Menu(
            pystray.MenuItem(lambda _: f"Status: {FARBEN[self.zustand][1]}", None, enabled=False),
            pystray.MenuItem(lambda _: self.detail or self.a.bedien_hinweis(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda _: "Fortsetzen" if self.a.pausiert else "Pausieren",
                             lambda icon, item: self.a.umschalten_pause()),
            pystray.MenuItem("Modell", self._modell_menue()),
            pystray.MenuItem("Recheneinheit", self._geraet_menue()),
            pystray.MenuItem("Mikrofon", self._mikrofon_menue()),
            pystray.MenuItem("Bedienung", self._modus_menue()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Fachwörter bearbeiten …", lambda icon, item: self.a.oeffne_fachwoerter()),
            pystray.MenuItem("Befehle bearbeiten …", lambda icon, item: self.a.oeffne_befehle()),
            pystray.MenuItem("Einstellungen öffnen …", lambda icon, item: self.a.oeffne_einstellungen()),
            pystray.MenuItem("Log öffnen", lambda icon, item: self.a.oeffne_log()),
            pystray.MenuItem("Mit Windows starten", lambda icon, item: self.a.umschalten_autostart(),
                             checked=lambda item: self.a.autostart_aktiv()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Neu starten", lambda icon, item: self.a.neustart(),
                             visible=self.a.unter_waechter),
            pystray.MenuItem("Beenden", lambda icon, item: self.a.beenden()),
        )

    def menue_neu_bauen(self) -> None:
        """Nach Änderungen an der Geräteliste (Mikrofon angesteckt/abgezogen)."""
        self.icon.menu = self._menue()
        try:
            self.icon.update_menu()
        except Exception:  # noqa: BLE001
            pass

    def _titel(self) -> str:
        modell = self.a.modelle[self.a.modell].titel.split(" –")[0]
        return f"Whisper-Diktat: {FARBEN[self.zustand][1]} · {modell} · {art(self.a.geraet)}"[:127]

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

    def melde(self, text: str) -> None:
        """Windows-Meldung (Benachrichtigung am Symbol) und derselbe Text im Menü."""
        self.detail = text[:120]
        try:
            self.icon.update_menu()
            self.icon.notify(text[:250], "whisper-diktat")
        except Exception:  # noqa: BLE001  (Meldungen sind nur Hinweise)
            logging.getLogger("diktat").exception("Windows-Meldung ging nicht")

    def run(self, setup=None) -> None:
        self.icon.run(setup=setup)

    def stop(self) -> None:
        self.icon.stop()
