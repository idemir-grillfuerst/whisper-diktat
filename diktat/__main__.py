"""Startpunkt:  %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m diktat   (im Projektordner)

Ablauf: Shortcut halten -> Aufnahme, loslassen -> Whisper (eigener Prozess) -> Text an der Cursorposition.
Menü im Taskleisten-Symbol: Pausieren, Modell, Recheneinheit, Mikrofon, Bedienung, Fachwörter/Einstellungen/Log,
Autostart, Beenden.
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
from .config import (CONFIG_DATEI, FACHWORT_DATEI, aus_vorlage, fachwort_prompt, lade_config, speichere_modus,
                     speichere_geraet, speichere_mikrofon, speichere_modell)
from . import geraete
from .engine import Engine
from .hotkey import PushToTalk
from .maus import MausTaste, parse_maustaste
from .inserter import fuege_ein
from .recorder import RATE, Recorder
from .tray import Tray

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
        self.modelle = self.cfg.modelle
        self.modell = self.cfg.modell
        self.geraet_wahl = self.cfg.geraet              # "auto" oder ein OpenVINO-Gerät
        self.recheneinheiten = geraete.recheneinheiten()  # vor dem Tastatur-Hook: Import dauert ~0,5 s
        self.pausiert = False
        self.unter_waechter = os.environ.get("DIKTAT_WAECHTER") == "1"
        self.exit_code = EXIT_OK
        self.recorder = Recorder(offen_halten=self.cfg.mikrofon_offen_halten, mikrofon=self.cfg.mikrofon)
        self._mikrofone = geraete.mikrofone()
        self.engine = self._neue_engine()
        self._engine_lock = threading.Lock()
        self.ereignisse: queue.Queue = queue.Queue()
        self.auftraege: queue.Queue = queue.Queue()
        self.hotkey = PushToTalk(self.cfg.shortcut, self.ereignisse.put_nowait)
        taste = parse_maustaste(self.cfg.maustaste)
        self.maus = (MausTaste(taste, self.ereignisse.put_nowait, halten_s=self.cfg.tipp_grenze_s,
                               max_s=self.cfg.max_aufnahme_s) if taste else None)
        self.eingaben = [self.hotkey] + ([self.maus] if self.maus else [])
        self._maus_aufnahme = False     # laufende Aufnahme kam von der Maustaste
        self.modus = self.cfg.modus
        self._autostart: bool | None = None
        self.tray = Tray(self, self.cfg.shortcut)
        self._start_zeit = 0.0          # Beginn der laufenden Aufnahme
        self._druck_zeit = 0.0          # Zeitpunkt des letzten Tastendrucks
        self._dauer_aktiv = False       # Daueraufnahme (Umschalten) läuft
        self._release_ignorieren = False  # das Loslassen nach dem Stopp-Tippen gehört zu nichts
        self._entladen = False          # Modell wegen Leerlauf entladen
        self._letzte_aktivitaet = time.monotonic()
        self._laeuft = True

    # --- Modell / Recheneinheit / Mikrofon ---------------------------------------------------
    @property
    def geraet(self) -> str:
        """Tatsächlich genutzte Recheneinheit ('auto' aufgelöst)."""
        return geraete.loese_geraet(self.geraet_wahl, self.recheneinheiten)

    @property
    def mikrofon(self) -> str:
        return self.recorder.mikrofon

    def beschreibung(self) -> str:
        return f"{self.modelle[self.modell].titel.split(' –')[0]} auf {geraete.art(self.geraet)}"

    def _neue_engine(self) -> Engine:
        return Engine(self.modelle[self.modell].repo, self.geraet, self.cfg.sprache)

    def _lade(self, engine: Engine, versuche: int = 5):
        """Lädt eine Engine im Hintergrund. Wurde sie inzwischen ersetzt, wird sie wieder beendet.
        Schlägt das Laden fehl (z. B. Grafiktreiber direkt nach der Anmeldung noch nicht bereit), wird es
        mit wachsender Pause erneut versucht."""
        hinweis = "NPU: erstes Laden kann einige Minuten dauern" if engine.geraet.startswith("NPU") else None
        for versuch in range(1, versuche + 1):
            if engine is not self.engine or self.pausiert or not self._laeuft:
                engine.stop()
                return
            self._zeige_laden(hinweis or f"Lade {self.beschreibung()} …")
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
                self._zeige_laden(f"Laden fehlgeschlagen, neuer Versuch in {10 * versuch} s")
                time.sleep(10 * versuch)
        if engine is not self.engine or self.pausiert:
            engine.stop()
            return
        self._zurueck_zu_bereit(detail=f"{self.beschreibung()} geladen")

    def _zeige_laden(self, detail: str):
        """Lade-Hinweis zeigen, ohne das rote Aufnahme-Symbol zu überdecken (Laden nach Leerlauf läuft,
        während schon gesprochen wird)."""
        if self.recorder.laeuft or self.tray.zustand == "verarbeitet":
            self.tray.detail = detail
        else:
            self.tray.setze("laedt", detail)

    # --- Leerlauf: Modell entladen und beim nächsten Diktat wieder laden ------------------------
    def _pruefe_leerlauf(self, jetzt: float) -> bool:
        """True, wenn das Modell jetzt wegen Leerlauf entladen wurde."""
        if self.cfg.leerlauf_minuten <= 0 or self.pausiert or self._entladen:
            return False
        if self.recorder.laeuft or not self.auftraege.empty() or not self.engine.bereit:
            return False
        if jetzt - self._letzte_aktivitaet < self.cfg.leerlauf_minuten * 60:
            return False
        log.info("Seit %.0f min kein Diktat – entlade das Modell", (jetzt - self._letzte_aktivitaet) / 60)
        self._entladen = True
        with self._engine_lock:
            alt = self.engine
            self.engine = self._neue_engine()
        threading.Thread(target=alt.stop, name="stoppen", daemon=True).start()
        self.tray.setze("ruht", "Modell entladen (Leerlauf) – lädt beim nächsten Diktat")
        return True

    def _aufwecken(self):
        if not self._entladen or self.pausiert:
            return
        self._entladen = False
        log.info("Diktat nach Leerlauf – lade das Modell")
        self._starte_engine()

    def _engine_neu_starten(self, grund: str, warten: bool = False):
        log.warning("Starte Whisper neu: %s", grund)
        with self._engine_lock:
            alt = self.engine
            self.engine = self._neue_engine()
        threading.Thread(target=alt.stop, name="stoppen", daemon=True).start()
        if self.pausiert:
            return
        if warten:
            self._lade(self.engine)
        else:
            self._starte_engine()

    def _starte_engine(self):
        threading.Thread(target=self._lade, args=(self.engine,), name="laden", daemon=True).start()

    def _wechsle(self, modell: str | None = None, geraet_wahl: str | None = None):
        """Modell und/oder Recheneinheit wechseln: alte Engine weg, neue laden, Wahl in config.toml speichern."""
        neu_modell = modell or self.modell
        neu_wahl = geraet_wahl or self.geraet_wahl
        neu_geraet = geraete.loese_geraet(neu_wahl, self.recheneinheiten)
        gleiche_engine = (neu_modell == self.modell and neu_geraet == self.geraet)
        log.info("Wechsle: %s/%s -> %s/%s", self.modell, self.geraet_wahl, neu_modell, neu_wahl)
        with self._engine_lock:
            alt = self.engine
            self.modell, self.geraet_wahl = neu_modell, neu_wahl
            if not gleiche_engine:
                self.engine = self._neue_engine()
        try:
            if modell:
                speichere_modell(neu_modell)
            if geraet_wahl:
                speichere_geraet(neu_wahl)
        except Exception:  # noqa: BLE001
            log.exception("Auswahl konnte nicht in config.toml gespeichert werden")
        if gleiche_engine and (alt.bereit or self.tray.zustand == "laedt" or self.pausiert):
            self.tray.setze(self.tray.zustand)  # z. B. "auto" -> "GPU": gleiche Einheit, nur Anzeige
            return
        if gleiche_engine:  # z. B. nach einem Fehler: neu laden
            with self._engine_lock:
                self.engine = self._neue_engine()
        threading.Thread(target=alt.stop, name="stoppen", daemon=True).start()
        self.hooks_erneuern()
        self._entladen = False
        self._letzte_aktivitaet = time.monotonic()
        if not self.pausiert:
            self._starte_engine()
        else:
            self.tray.setze("pausiert")

    def waehle_modell(self, name: str):
        if name in self.modelle:
            self._wechsle(modell=name)

    def waehle_geraet(self, wahl: str):
        self._wechsle(geraet_wahl=wahl)

    def mikrofone(self) -> list[str]:
        return self._mikrofone

    def aktuelles_mikrofon(self) -> str:
        """Name des Mikrofons, das bei der nächsten Aufnahme benutzt wird."""
        if self.recorder.mikrofon and self.recorder.mikrofon in self._mikrofone:
            return self.recorder.mikrofon
        return self.recorder.standard_geraet()

    def waehle_mikrofon(self, name: str):
        if name == self.recorder.mikrofon:
            return
        log.info("Mikrofon: %s -> %s", self.recorder.mikrofon or "Windows-Standard", name or "Windows-Standard")
        try:
            self.recorder.waehle(name)
        except Exception:  # noqa: BLE001
            log.exception("Mikrofon konnte nicht geöffnet werden")
        try:
            speichere_mikrofon(name)
        except Exception:  # noqa: BLE001
            log.exception("Mikrofon konnte nicht in config.toml gespeichert werden")
        self.tray.setze(self.tray.zustand)

    def _mikrofone_aktualisieren(self):
        neu = geraete.mikrofone()
        if neu != self._mikrofone:
            log.info("Mikrofone: %s", ", ".join(neu) or "keine")
            self._mikrofone = neu
            self.tray.menue_neu_bauen()

    def waehle_modus(self, modus: str):
        if modus == self.modus:
            return
        log.info("Bedienung: %s -> %s", self.modus, modus)
        self.modus = modus
        try:
            speichere_modus(modus)
        except Exception:  # noqa: BLE001
            log.exception("Modus konnte nicht in config.toml gespeichert werden")
        self.tray.setze(self.tray.zustand)

    def bedien_hinweis(self) -> str:
        k = self.cfg.shortcut.upper()
        text = {"halten": f"{k} halten zum Diktieren",
                "umschalten": f"{k} tippen = Start/Stopp",
                "beides": f"{k} halten oder kurz tippen"}[self.modus]
        if self.maus:
            text += " · " + {"mitte": "Mausrad", "x1": "Maustaste 4", "x2": "Maustaste 5"}[self.maus.taste] + " halten"
        return text

    def hooks_erneuern(self):
        for e in self.eingaben:
            e.erneuern()

    def umschalten_pause(self):
        if self.pausiert:
            log.info("Fortsetzen")
            self.pausiert = False
            self._entladen = False
            self._letzte_aktivitaet = time.monotonic()
            for e in self.eingaben:
                e.eingeschaltet = True
            self.hooks_erneuern()
            with self._engine_lock:
                self.engine = self._neue_engine()
            self._starte_engine()
        else:
            log.info("Pausieren: Shortcut aus, Modell entladen")
            self.pausiert = True
            for e in self.eingaben:
                e.eingeschaltet = False
                e.aktiv = False
                e._vom_wachhund = False  # noqa: SLF001
            self._maus_aufnahme = False
            self._dauer_aktiv = False
            self._release_ignorieren = False
            self._entladen = False
            if self.recorder.laeuft:
                self.recorder.stop()
            self.engine.stop()
            self.tray.setze("pausiert", "Shortcut aus, Modell entladen")

    # --- Menüpunkte ------------------------------------------------------------------------
    def oeffne_fachwoerter(self):
        aus_vorlage(FACHWORT_DATEI)
        oeffne_im_editor(FACHWORT_DATEI)  # wird bei jedem Diktat neu gelesen

    def oeffne_einstellungen(self):
        oeffne_im_editor(CONFIG_DATEI)  # Änderungen greifen nach Neustart

    def oeffne_log(self):
        oeffne_im_editor(LOG_DATEI)

    def autostart_aktiv(self) -> bool:
        """Wird bei jedem Öffnen des Menüs gefragt: einmal abfragen, danach zwischenspeichern."""
        if self._autostart is None:
            try:
                self._autostart = autostart.ist_aktiv()
            except Exception:  # noqa: BLE001
                self._autostart = False
        return self._autostart

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
        self._autostart = None  # neu abfragen
        self.tray.setze(self.tray.zustand)

    def neustart(self):
        self.exit_code = EXIT_NEUSTART
        self.beenden()

    # --- Wartung: Standby, Headset-Wechsel, Hook, abgestürzter Whisper-Prozess -----------------
    def _wartungs_schleife(self):
        letzte_wand = time.time()
        letzte_hook = letzte_geraete = letztes_lebenszeichen = time.monotonic()
        gestartet = time.monotonic()
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
                    self.hooks_erneuern()
                    if untaetig:
                        self.recorder.geraete_neu_laden()
                    if not self.pausiert and not self._entladen:
                        self._engine_neu_starten("nach Standby")
                    letzte_hook = letzte_geraete = jetzt
                letzte_wand = jetzt_wand
                if jetzt - letztes_lebenszeichen >= 3600:
                    # Damit man im Log sieht, bis wann das Tool lief, falls es einmal spurlos verschwindet
                    zustand = ("pausiert" if self.pausiert else "Modell entladen" if self._entladen
                               else "Modell geladen" if self.engine.bereit else "Modell lädt")
                    log.info("Lebenszeichen: läuft seit %.1f h, %s, %s, Hook-Ausfälle %d",
                             (jetzt - gestartet) / 3600, zustand, self.beschreibung(), sum(e.hook_ausfaelle for e in self.eingaben))
                    letztes_lebenszeichen = jetzt
                if jetzt - letzte_hook > 300:
                    self.hooks_erneuern()
                    letzte_hook = jetzt
                if jetzt - letzte_geraete > 60 and untaetig:
                    if self.recorder.geraete_neu_laden():
                        neu = self.recorder.standard_geraet()
                        if neu != geraet:
                            log.info("Windows-Standardmikrofon gewechselt: %s -> %s", geraet, neu)
                            geraet = neu
                        self._mikrofone_aktualisieren()
                    letzte_geraete = jetzt
                self.recorder.gesund()
                self._pruefe_leerlauf(jetzt)
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
                e = None
            try:
                if e is None:
                    self._pruefe_max_dauer(time.monotonic())
                elif not self.pausiert:
                    self._behandle_ereignis(e, time.monotonic())
            except Exception as ex:  # noqa: BLE001
                log.exception("Fehler bei %s", e)
                self.tray.setze("fehler", f"Mikrofon: {ex}"[:100])

    def _behandle_ereignis(self, e: str, jetzt: float):
        """Bedienlogik für press/release/cancel je nach Modus (halten, umschalten, beides).
        Maustaste (maus_*): immer „halten“, unabhängig vom Modus."""
        if e == "maus_press":
            if self.recorder.laeuft:  # läuft schon eine Aufnahme über die Tastatur: Maus ignorieren
                return
            self._maus_aufnahme = True
            self._letzte_aktivitaet = self._druck_zeit = self._start_zeit = jetzt
            self.recorder.start()
            self.tray.setze("aufnahme", "")
            self._aufwecken()
            return
        if e in ("maus_release", "maus_cancel"):
            if not self._maus_aufnahme:
                return
            self._maus_aufnahme = False
            if e == "maus_release":
                self._abschliessen(jetzt)
            else:  # kurzer Klick: war kein Diktat, Klick wird nachgereicht
                self.recorder.stop()
                log.debug("Mausklick, kein Diktat")
                self._zurueck_zu_bereit()
            return
        if self._maus_aufnahme:  # Tastatur während einer Maus-Aufnahme: ignorieren
            return
        if e == "press":
            self._letzte_aktivitaet = jetzt
            if self._dauer_aktiv:  # Tippen während einer Daueraufnahme = Stopp
                self._dauer_aktiv = False
                self._release_ignorieren = True
                self._abschliessen(jetzt)
                return
            self._druck_zeit = self._start_zeit = jetzt
            self.recorder.start()
            self.tray.setze("aufnahme", "")
            self._aufwecken()  # nach Leerlauf: Modell lädt, während gesprochen wird
        elif e == "release":
            if self._release_ignorieren:
                self._release_ignorieren = False
                return
            if not self.recorder.laeuft:
                return
            gedrueckt = jetzt - self._druck_zeit
            if self.modus == "umschalten" or (self.modus == "beides" and gedrueckt < self.cfg.tipp_grenze_s):
                self._dauer_aktiv = True
                log.info("Daueraufnahme läuft – %s tippen zum Beenden", self.cfg.shortcut)
                self.tray.setze("aufnahme", f"Daueraufnahme – {self.cfg.shortcut.upper()} tippen zum Beenden")
                return
            self._abschliessen(jetzt)
        elif e == "cancel":
            self._dauer_aktiv = self._release_ignorieren = False
            self.recorder.stop()
            log.info("Aufnahme abgebrochen (andere Taste gedrückt)")
            self._zurueck_zu_bereit()

    def _abschliessen(self, jetzt: float):
        audio = self.recorder.stop()
        dauer = jetzt - self._start_zeit
        if dauer < self.cfg.min_dauer_s:
            log.info("Aufnahme verworfen (%.2f s)", dauer)
            self._zurueck_zu_bereit()
            return
        self.auftraege.put(audio)
        self.tray.setze("verarbeitet")

    def _pruefe_max_dauer(self, jetzt: float):
        if self._dauer_aktiv and jetzt - self._start_zeit >= self.cfg.max_aufnahme_s:
            log.info("Daueraufnahme nach %.0f s automatisch beendet", jetzt - self._start_zeit)
            self._dauer_aktiv = False
            self._abschliessen(jetzt)

    def _zurueck_zu_bereit(self, detail: str | None = None):
        if self.pausiert:
            self.tray.setze("pausiert")
        elif self.recorder.laeuft:
            return
        elif self._entladen and not self.engine.bereit:
            self.tray.setze("ruht", detail)
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
            finally:
                self._letzte_aktivitaet = time.monotonic()
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
        self._aufwecken()  # Sicherheitsnetz, falls das Modell im Leerlauf entladen ist
        # Falls das Modell noch lädt (Start, Stufenwechsel, Leerlauf): warten statt verwerfen
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
        log.info("%.1f s Audio in %.2f s (%s) -> %d Zeichen%s", dauer, sek, self.beschreibung(), len(text),
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
        for e in self.eingaben:
            e.start()
        try:
            self.recorder.bereit_machen()
        except Exception:  # noqa: BLE001
            log.exception("Mikrofon konnte nicht vorab geöffnet werden")
        self._starte_engine()
        for ziel, name in ((self._ereignis_schleife, "ereignisse"),
                           (self._transkriptions_schleife, "transkription"),
                           (self._wartungs_schleife, "wartung")):
            threading.Thread(target=ziel, name=name, daemon=True).start()
        log.info("Bereit: %s (Bedienung %s, %s, Mikrofon %s, Leerlauf %s min%s)", self.bedien_hinweis(),
                 self.modus, self.beschreibung(), self.aktuelles_mikrofon(), self.cfg.leerlauf_minuten or "aus",
                 ", mit Wächter" if self.unter_waechter else "")

    def beenden(self):
        log.info("Beende …" if self.exit_code != EXIT_NEUSTART else "Neustart …")
        self._laeuft = False
        for e in self.eingaben:
            e.stop()
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
