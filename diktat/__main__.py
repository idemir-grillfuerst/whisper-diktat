"""Startpunkt:  %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m diktat   (im Projektordner)

Ablauf: Shortcut halten -> Aufnahme, loslassen -> Whisper (eigener Prozess) -> Text an der Cursorposition.
Menü im Taskleisten-Symbol: Pausieren, Stufe wechseln, Fachwörter/Einstellungen/Log öffnen, Beenden.
"""
import ctypes
import faulthandler
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
import wave
from datetime import datetime
from logging.handlers import RotatingFileHandler

import numpy as np

from . import PROJEKT, autostart
from .waechter import EXIT_LAEUFT_SCHON, EXIT_NEUSTART, EXIT_OK
from .config import CONFIG_DATEI, FACHWORT_DATEI, fachwort_prompt, lade_config, speichere_stufe
from .engine import Engine
from .hotkey import PushToTalk
from .inserter import fuege_ein
from .recorder import RATE, Recorder
from .tray import STUFEN_TEXT, Tray

log = logging.getLogger("diktat")
LOG_DATEI = PROJEKT / "logs" / "diktat.log"

# Typische Whisper-Halluzinationen bei Stille oder am Ende (aus Untertitel-Trainingsdaten)
HALLUZINATIONEN = re.compile(
    r"\s*(Untertitel(ung)? (des|im Auftrag des) (ZDF|ZDF für funk)[^.]*\.?|Copyright WDR \d{4}\.?|"
    r"Vielen Dank fürs Zuschauen!?\.?)\s*$",
    re.IGNORECASE,
)
NUR_FUELLWORT = {"", "vielen dank.", "vielen dank", "danke.", "tschüss.", "...", "."}


def richte_logging_ein() -> None:
    LOG_DATEI.parent.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    datei = RotatingFileHandler(LOG_DATEI, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    datei.setFormatter(fmt)
    handler = [datei]
    if sys.stdout is not None:  # unter pythonw gibt es keine Konsole
        konsole = logging.StreamHandler(sys.stdout)
        konsole.setFormatter(fmt)
        handler.append(konsole)
    logging.basicConfig(level=logging.INFO, handlers=handler)


def nur_eine_instanz() -> bool:
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\whisper-diktat")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


# Dieselbe Wortfolge (mind. 2 Wörter) 3-mal oder öfter direkt hintereinander -> nur einmal behalten
WIEDERHOLUNG = re.compile(r"(\b\S+(?:\s+\S+)+?[,.!?]?)(?:\s+\1){2,}", re.IGNORECASE)
WIEDERHOLUNG_WORT = re.compile(r"\b(\S+)(?:[,\s]+\1\b){4,}", re.IGNORECASE)  # ein Wort 5x und öfter
# Mehr Zeichen pro Sekunde kann niemand sprechen (normal sind ca. 12–18)
MAX_ZEICHEN_PRO_S, ZEICHEN_PUFFER = 30, 40


def bereinige(text: str) -> str:
    text = HALLUZINATIONEN.sub("", text).strip()
    alt = None
    while alt != text:  # mehrfach, bis nichts mehr zu kürzen ist
        alt = text
        text = WIEDERHOLUNG_WORT.sub(r"\1", text)  # erst Einzelwörter, sonst bleibt "okay okay" übrig
        text = WIEDERHOLUNG.sub(r"\1", text)
    return "" if text.lower() in NUR_FUELLWORT else text


def max_tokens_fuer(dauer_s: float) -> int | None:
    """Obergrenze für Whisper-Token. Bis 30 s Audio passt alles in ein Fenster (max. 448 Token)."""
    if dauer_s > 30:
        return None
    return min(440, int(dauer_s * 12) + 30)


def zu_lang(text: str, dauer_s: float) -> bool:
    return len(text) > MAX_ZEICHEN_PRO_S * dauer_s + ZEICHEN_PUFFER


def oeffne_im_editor(pfad) -> None:
    subprocess.Popen(["notepad.exe", str(pfad)])


class App:
    def __init__(self):
        self.cfg = lade_config()
        self.stufen = list(self.cfg.stufen)
        self.stufe = self.cfg.stufe.name
        self.pausiert = False
        self.unter_waechter = os.environ.get("DIKTAT_WAECHTER") == "1"
        self.exit_code = EXIT_OK
        self.recorder = Recorder(offen_halten=self.cfg.mikrofon_offen_halten)
        self.engine = self._neue_engine(self.stufe)
        self._engine_lock = threading.Lock()
        self.ereignisse: queue.Queue = queue.Queue()
        self.auftraege: queue.Queue = queue.Queue()
        self.hotkey = PushToTalk(self.cfg.shortcut, self.ereignisse.put_nowait)
        self.tray = Tray(self, self.cfg.shortcut)
        self._start_zeit = 0.0
        self._laeuft = True

    # --- Modell / Stufe --------------------------------------------------------------------
    def _neue_engine(self, name: str) -> Engine:
        s = self.cfg.stufen[name]
        return Engine(s.repo, s.geraet, self.cfg.sprache)

    def _lade(self, engine: Engine, versuche: int = 5):
        """Lädt eine Engine im Hintergrund. Wurde sie inzwischen ersetzt, wird sie wieder beendet.
        Schlägt das Laden fehl (z. B. Grafiktreiber direkt nach der Anmeldung noch nicht bereit), wird es
        mit wachsender Pause erneut versucht."""
        s = self.cfg.stufen[self.stufe]
        hinweis = "NPU: erstes Laden kann einige Minuten dauern" if s.geraet == "NPU" else None
        for versuch in range(1, versuche + 1):
            if engine is not self.engine or self.pausiert or not self._laeuft:
                engine.stop()
                return
            self.tray.setze("laedt", hinweis or f"Lade {STUFEN_TEXT.get(self.stufe, self.stufe)} …")
            try:
                engine.start()
                break
            except Exception as e:  # noqa: BLE001
                if engine is not self.engine or self.pausiert or engine.gestoppt:
                    return
                log.error("Modell konnte nicht geladen werden (Versuch %d/%d): %s", versuch, versuche, e)
                if versuch == versuche:
                    self.tray.setze("fehler", f"Modell: {e}"[:100])
                    return
                self.tray.setze("laedt", f"Laden fehlgeschlagen, neuer Versuch in {10 * versuch} s")
                time.sleep(10 * versuch)
        if engine is not self.engine or self.pausiert:
            engine.stop()
            return
        self._zurueck_zu_bereit(detail=f"{STUFEN_TEXT.get(self.stufe, self.stufe)} geladen")

    def _engine_neu_starten(self, grund: str, warten: bool = False):
        log.warning("Starte Whisper neu: %s", grund)
        with self._engine_lock:
            alt = self.engine
            self.engine = self._neue_engine(self.stufe)
        threading.Thread(target=alt.stop, name="stoppen", daemon=True).start()
        if self.pausiert:
            return
        if warten:
            self._lade(self.engine)
        else:
            self._starte_engine()

    def _starte_engine(self):
        threading.Thread(target=self._lade, args=(self.engine,), name="laden", daemon=True).start()

    def waehle_stufe(self, name: str):
        if name == self.stufe and (self.engine.bereit or self.tray.zustand == "laedt"):
            return
        log.info("Wechsle Stufe: %s -> %s", self.stufe, name)
        with self._engine_lock:
            alt = self.engine
            self.stufe = name
            self.engine = self._neue_engine(name)
        threading.Thread(target=alt.stop, name="stoppen", daemon=True).start()
        self.hotkey.erneuern()
        try:
            speichere_stufe(name)
        except Exception:  # noqa: BLE001
            log.exception("Stufe konnte nicht in config.toml gespeichert werden")
        if not self.pausiert:
            self._starte_engine()
        else:
            self.tray.setze("pausiert")

    def umschalten_pause(self):
        if self.pausiert:
            log.info("Fortsetzen")
            self.pausiert = False
            self.hotkey.eingeschaltet = True
            self.hotkey.erneuern()
            with self._engine_lock:
                self.engine = self._neue_engine(self.stufe)
            self._starte_engine()
        else:
            log.info("Pausieren: Shortcut aus, Modell entladen")
            self.pausiert = True
            self.hotkey.eingeschaltet = False
            self.hotkey.aktiv = False
            self.hotkey._vom_wachhund = False  # noqa: SLF001
            if self.recorder.laeuft:
                self.recorder.stop()
            self.engine.stop()
            self.tray.setze("pausiert", "Shortcut aus, Modell entladen")

    # --- Menüpunkte ------------------------------------------------------------------------
    def oeffne_fachwoerter(self):
        oeffne_im_editor(FACHWORT_DATEI)  # wird bei jedem Diktat neu gelesen

    def oeffne_einstellungen(self):
        oeffne_im_editor(CONFIG_DATEI)  # Änderungen greifen nach Neustart

    def oeffne_log(self):
        oeffne_im_editor(LOG_DATEI)

    def autostart_aktiv(self) -> bool:
        try:
            return autostart.ist_aktiv()
        except Exception:  # noqa: BLE001
            return False

    def umschalten_autostart(self):
        try:
            if autostart.ist_aktiv():
                autostart.deaktivieren()
                log.info("Autostart ausgeschaltet")
            else:
                autostart.aktivieren()
                log.info("Autostart eingeschaltet: %s", autostart.befehl())
        except Exception:  # noqa: BLE001
            log.exception("Autostart konnte nicht geändert werden")
        self.tray.setze(self.tray.zustand)

    def neustart(self):
        self.exit_code = EXIT_NEUSTART
        self.beenden()

    # --- Wartung: Standby, Headset-Wechsel, Hook, abgestürzter Whisper-Prozess -----------------
    def _wartungs_schleife(self):
        letzte_wand = time.time()
        letzte_hook = letzte_geraete = time.monotonic()
        geraet = self.recorder.standard_geraet()
        while self._laeuft:
            time.sleep(5)
            jetzt_wand, jetzt = time.time(), time.monotonic()
            try:
                untaetig = not self.recorder.laeuft and self.auftraege.empty()
                # Standby/Ruhezustand: Die Schleife schläft nur 5 s. Springt die Uhrzeit um mehr als 30 s,
                # war der Rechner dazwischen im Standby (oder die Uhr wurde gestellt, dann schadet es nicht).
                if jetzt_wand - letzte_wand > 30:
                    log.info("Aufgewacht nach %.0f s (Standby?)", jetzt_wand - letzte_wand)
                    self.hotkey.erneuern()
                    if untaetig:
                        self.recorder.geraete_neu_laden()
                    if not self.pausiert:
                        self._engine_neu_starten("nach Standby")
                    letzte_hook = letzte_geraete = jetzt
                letzte_wand = jetzt_wand
                if jetzt - letzte_hook > 300:
                    self.hotkey.erneuern()
                    letzte_hook = jetzt
                if jetzt - letzte_geraete > 60 and untaetig:
                    if self.recorder.geraete_neu_laden():
                        neu = self.recorder.standard_geraet()
                        if neu != geraet:
                            log.info("Mikrofon gewechselt: %s -> %s", geraet, neu)
                            geraet = neu
                    letzte_geraete = jetzt
                self.recorder.gesund()
                e = self.engine
                if e.bereit and e._proc is not None and not e._proc.is_alive():  # noqa: SLF001
                    self._engine_neu_starten("Whisper-Prozess unerwartet beendet")
            except Exception:  # noqa: BLE001
                log.exception("Fehler in der Wartung")

    # --- Threads ---------------------------------------------------------------------------
    def _ereignis_schleife(self):
        """Reagiert auf den Shortcut. Startet/stoppt nur das Mikrofon."""
        while self._laeuft:
            try:
                e = self.ereignisse.get(timeout=0.5)
            except queue.Empty:
                continue
            if self.pausiert:
                continue
            try:
                if e == "press":
                    self._start_zeit = time.monotonic()
                    self.recorder.start()
                    self.tray.setze("aufnahme")
                elif e in ("release", "cancel"):
                    audio = self.recorder.stop()
                    dauer = time.monotonic() - self._start_zeit
                    if e == "cancel" or dauer < self.cfg.min_dauer_s:
                        log.info("Aufnahme verworfen (%s, %.2f s)", e, dauer)
                        self._zurueck_zu_bereit()
                    else:
                        self.auftraege.put(audio)
                        self.tray.setze("verarbeitet")
            except Exception as ex:  # noqa: BLE001
                log.exception("Fehler bei %s", e)
                self.tray.setze("fehler", f"Mikrofon: {ex}"[:100])

    def _zurueck_zu_bereit(self, detail: str | None = None):
        if self.pausiert:
            self.tray.setze("pausiert")
        elif self.recorder.laeuft:
            return
        elif not self.engine.bereit:
            if self.tray.zustand != "fehler":
                self.tray.setze("laedt", detail)
        elif self.auftraege.empty():
            self.tray.setze("bereit", detail)

    def _transkriptions_schleife(self):
        while self._laeuft:
            try:
                audio = self.auftraege.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._verarbeite(audio)
            except Exception as ex:  # noqa: BLE001
                log.exception("Transkription fehlgeschlagen")
                self.tray.setze("fehler", str(ex)[:100])
                continue
            self._zurueck_zu_bereit()

    def _verarbeite(self, audio: np.ndarray):
        dauer = len(audio) / RATE
        spitze = float(np.abs(audio).max()) if len(audio) else 0.0
        if self.cfg.aufnahmen_speichern:
            self._speichere(audio)
        if spitze < 0.01:
            log.info("Aufnahme stumm (%.1f s, Spitze %.4f, Gerät %s) – Mikrofon stummgeschaltet oder "
                     "Headset wacht gerade auf?", dauer, spitze, self.recorder.geraet)
            self.tray.detail = "Aufnahme war stumm – nochmal versuchen / Mikrofon prüfen"
            return
        # Falls das Modell noch lädt (Start, Stufenwechsel): warten statt verwerfen
        ende = time.monotonic() + 600
        while not self.engine.bereit and time.monotonic() < ende:
            if self.pausiert or self.tray.zustand == "fehler":
                log.info("Diktat verworfen: Tool pausiert oder Modell fehlerhaft")
                return
            time.sleep(0.2)
        grenze = max_tokens_fuer(dauer)
        try:
            roh, sek = self.engine.transkribiere(audio, fachwort_prompt(), grenze)
        except Exception as e:  # noqa: BLE001
            # z. B. Grafiktreiber nach Standby: Whisper neu starten und einmal wiederholen
            log.warning("Transkription fehlgeschlagen (%s) – starte Whisper neu und versuche es erneut", e)
            self.tray.setze("laedt", "Whisper wird neu gestartet …")
            self._engine_neu_starten(str(e), warten=True)
            if not self.engine.bereit:
                raise
            roh, sek = self.engine.transkribiere(audio, fachwort_prompt(), grenze)
        text = bereinige(roh)
        if zu_lang(text, dauer):
            # Whisper hängt in einer Schleife fest (oft durch die Fachwortliste ausgelöst): ohne Liste wiederholen
            log.warning("Unplausibel lang: %d Zeichen für %.1f s Audio – wiederhole ohne Fachwortliste",
                        len(text), dauer)
            roh2, sek2 = self.engine.transkribiere(audio, None, grenze)
            sek += sek2
            text2 = bereinige(roh2)
            if zu_lang(text2, dauer):
                log.warning("Auch ohne Fachwortliste zu lang (%d Zeichen) – verwerfe das Diktat", len(text2))
                self.tray.detail = "Whisper hat sich verhaspelt – bitte nochmal diktieren"
                return
            text, roh = text2, roh2
        log.info("%.1f s Audio in %.2f s (%s) -> %d Zeichen%s", dauer, sek, self.stufe, len(text),
                 "" if text == roh.strip() else " (bereinigt)")
        if not text:
            self.tray.detail = "Nichts erkannt"
            return
        if self.cfg.leerzeichen_danach:
            text += " "
        fuege_ein(text, self.cfg.einfuegen)
        self.tray.detail = f"Letztes Diktat: {dauer:.1f} s Audio, {sek:.1f} s Whisper"

    def _speichere(self, audio):
        ordner = PROJEKT / "aufnahmen"
        ordner.mkdir(exist_ok=True)
        pfad = ordner / f"diktat_{datetime.now():%Y%m%d_%H%M%S}.wav"
        with wave.open(str(pfad), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())

    # --- Start / Ende ----------------------------------------------------------------------
    def _setup(self, icon):
        icon.visible = True
        self.hotkey.start()
        try:
            self.recorder.bereit_machen()
        except Exception:  # noqa: BLE001
            log.exception("Mikrofon konnte nicht vorab geöffnet werden")
        self._starte_engine()
        for ziel, name in ((self._ereignis_schleife, "ereignisse"),
                           (self._transkriptions_schleife, "transkription"),
                           (self._wartungs_schleife, "wartung")):
            threading.Thread(target=ziel, name=name, daemon=True).start()
        log.info("Bereit: %s gedrückt halten zum Diktieren (Stufe %s%s)", self.cfg.shortcut, self.stufe,
                 ", mit Wächter" if self.unter_waechter else "")

    def beenden(self):
        log.info("Beende …" if self.exit_code != EXIT_NEUSTART else "Neustart …")
        self._laeuft = False
        self.hotkey.stop()
        self.recorder.schliessen()
        self.engine.stop()
        self.tray.stop()

    def run(self) -> int:
        self.tray.run(setup=self._setup)
        return self.exit_code


def main() -> int:
    richte_logging_ein()
    faulthandler.enable(open(LOG_DATEI.with_name("absturz.log"), "a", encoding="utf-8"))  # harte Abstürze
    if not nur_eine_instanz():
        log.warning("whisper-diktat läuft bereits – zweiter Start beendet sich")
        return EXIT_LAEUFT_SCHON
    log.info("Starte whisper-diktat")
    try:
        code = App().run()
    except Exception:
        log.exception("Unerwarteter Fehler – Tool beendet sich")
        return 1
    log.info("Beendet (Code %s)", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
