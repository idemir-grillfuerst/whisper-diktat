"""Mikrofonaufnahme mit 16 kHz mono.

Zwei Betriebsarten (config.toml: mikrofon_offen_halten):
- false (Standard): Das Mikrofon ist nur offen, solange die Taste gedrückt ist.
- true: Das Mikrofon bleibt dauerhaft offen, und die letzten ~0,4 s vor dem Tastendruck werden mitgenommen
  (Vorlauf). Hilft, falls das Funkheadset nach einer Pause den Anfang verschluckt. Nachteil: Windows zeigt
  dauerhaft „Mikrofon in Verwendung“, und das Headset bleibt aktiv (Akku).

Headset-Wechsel: PortAudio merkt sich die Geräteliste beim Start. geraete_neu_laden() liest sie neu ein
(nur, wenn gerade nicht aufgenommen wird).
"""
import logging
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)
RATE = 16000
BLOCK = 800  # 50 ms


class Recorder:
    def __init__(self, offen_halten: bool = False, vorlauf_s: float = 0.4):
        self.offen_halten = offen_halten
        self._vorlauf = deque(maxlen=max(1, int(vorlauf_s * RATE / BLOCK)))
        self._stream = None
        self._aufnahme = False
        self._chunks = []
        self._lock = threading.RLock()
        self.geraet = ""

    def _cb(self, indata, frames, t, status):
        if status:
            log.debug("Audio-Status: %s", status)
        block = indata[:, 0].copy()
        if self._aufnahme:
            self._chunks.append(block)
        elif self.offen_halten:
            self._vorlauf.append(block)

    def _oeffne(self):
        t0 = time.perf_counter()
        self._stream = sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK,
                                      callback=self._cb)
        self._stream.start()
        try:
            self.geraet = sd.query_devices(self._stream.device)["name"]
        except Exception:  # noqa: BLE001
            self.geraet = "?"
        return (time.perf_counter() - t0) * 1000

    def _schliesse(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                log.debug("Stream schließen fehlgeschlagen", exc_info=True)
            self._stream = None

    def bereit_machen(self):
        """Im Modus 'offen halten': Mikrofon jetzt öffnen."""
        with self._lock:
            if self.offen_halten and self._stream is None:
                ms = self._oeffne()
                log.info("Mikrofon dauerhaft offen: %s (%.0f ms)", self.geraet, ms)

    def start(self):
        with self._lock:
            if self._aufnahme:
                return
            if self._stream is None or not self._stream.active:
                self._schliesse()
                self._chunks = []
                ms = self._oeffne()
                log.info("Aufnahme gestartet: %s (Mikrofon nach %.0f ms offen)", self.geraet, ms)
            else:
                self._chunks = list(self._vorlauf)
                log.info("Aufnahme gestartet (mit %.1f s Vorlauf)", len(self._chunks) * BLOCK / RATE)
            self._vorlauf.clear()
            self._aufnahme = True

    def stop(self) -> np.ndarray:
        with self._lock:
            if not self._aufnahme:
                return np.zeros(0, dtype=np.float32)
            self._aufnahme = False
            if not self.offen_halten:
                self._schliesse()  # wartet, bis der letzte Block da ist
            chunks, self._chunks = self._chunks, []
            return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)

    @property
    def laeuft(self) -> bool:
        return self._aufnahme

    def geraete_neu_laden(self) -> bool:
        """Geräteliste neu einlesen (Headset gewechselt, nach Standby). False, wenn gerade aufgenommen wird."""
        with self._lock:
            if self._aufnahme:
                return False
            war_offen = self._stream is not None
            self._schliesse()
            sd._terminate()  # noqa: SLF001  (öffentliche API dafür gibt es nicht)
            sd._initialize()  # noqa: SLF001
            if self.offen_halten and war_offen:
                self._oeffne()
            return True

    def standard_geraet(self) -> str:
        try:
            return sd.query_devices(kind="input")["name"]
        except Exception:  # noqa: BLE001
            return "?"

    def gesund(self) -> None:
        """Im Modus 'offen halten': abgebrochenen Stream (Headset weg) wieder öffnen."""
        with self._lock:
            if self.offen_halten and not self._aufnahme and (self._stream is None or not self._stream.active):
                log.warning("Mikrofon-Stream war weg, öffne neu")
                self._schliesse()
                try:
                    self.geraete_neu_laden()
                    if self._stream is None:
                        self._oeffne()
                except Exception:  # noqa: BLE001
                    log.exception("Mikrofon konnte nicht geöffnet werden")

    def schliessen(self):
        with self._lock:
            self._aufnahme = False
            self._schliesse()
