"""Whisper über OpenVINO GenAI in einem eigenen Prozess.

Warum ein eigener Prozess:
- Der Python-GIL kann den Tastatur-Hook nicht blockieren (sonst entfernt Windows den Hook).
- Ein Absturz im Grafiktreiber reißt nicht das ganze Tool mit.
- Modell wechseln oder pausieren = Prozess beenden; GPU-Speicher wird sicher frei.
"""
import logging
import multiprocessing as mp
import threading
import time

import numpy as np

from . import PROJEKT

log = logging.getLogger(__name__)
OV_CACHE = PROJEKT / ".ov_cache"


def _worker(conn, repo: str, geraet: str, sprache: str):
    """Läuft im Kindprozess: Modell laden, dann Aufträge abarbeiten."""
    try:
        import openvino_genai as ov_genai
        from huggingface_hub import snapshot_download

        t0 = time.perf_counter()
        try:
            model_dir = snapshot_download(repo, local_files_only=True)
        except Exception:
            model_dir = snapshot_download(repo)  # erstes Mal: herunterladen
        pipe = ov_genai.WhisperPipeline(model_dir, geraet, CACHE_DIR=str(OV_CACHE))
        basis = pipe.get_generation_config()
        basis.language = f"<|{sprache}|>"
        basis.task = "transcribe"
        pipe.generate(np.zeros(16000, dtype=np.float32).tolist(), basis)  # Aufwärmen
        conn.send({"bereit": True, "laden_s": round(time.perf_counter() - t0, 1)})
    except Exception as e:  # noqa: BLE001
        conn.send({"bereit": False, "fehler": f"{type(e).__name__}: {e}"})
        return

    while True:
        try:
            auftrag = conn.recv()
        except EOFError:
            return
        if auftrag is None:
            return
        try:
            audio = np.frombuffer(auftrag["audio"], dtype=np.float32)
            cfg = pipe.get_generation_config()
            cfg.language = f"<|{sprache}|>"
            cfg.task = "transcribe"
            cfg.return_timestamps = len(audio) > 30 * 16000  # nötig für Audio über 30 s
            if auftrag.get("prompt"):
                cfg.initial_prompt = auftrag["prompt"]
            if auftrag.get("max_tokens"):
                cfg.max_new_tokens = int(auftrag["max_tokens"])  # bremst Wiederholungsschleifen
            t0 = time.perf_counter()
            res = pipe.generate(audio.tolist(), cfg)
            if res.chunks:
                text = " ".join(c.text.strip() for c in res.chunks)
            else:
                text = str(res.texts[0]).strip()
            conn.send({"text": text, "sek": round(time.perf_counter() - t0, 2)})
        except Exception as e:  # noqa: BLE001
            conn.send({"fehler": f"{type(e).__name__}: {e}"})


class Engine:
    """Steuert den Whisper-Prozess aus dem Hauptprogramm."""

    def __init__(self, repo: str, geraet: str, sprache: str):
        self.repo, self.geraet, self.sprache = repo, geraet, sprache
        self._proc = None
        self._conn = None
        self._stop_lock = threading.Lock()
        self.gestoppt = False  # eine Engine wird nur einmal benutzt; nach stop() nie wieder starten
        self.bereit = False

    def start(self, timeout_s: float = 600) -> None:
        """Startet den Prozess und wartet, bis das Modell geladen ist (NPU braucht beim ersten Mal Minuten)."""
        ctx = mp.get_context("spawn")
        conn, kind = ctx.Pipe()
        proc = ctx.Process(target=_worker, args=(kind, self.repo, self.geraet, self.sprache),
                           name="whisper-engine", daemon=True)
        with self._stop_lock:
            if self.gestoppt:
                raise RuntimeError("Laden abgebrochen")
            self._conn, self._proc = conn, proc
            proc.start()
        kind.close()
        try:  # stop() aus einem anderen Thread (Stufenwechsel/Pause) beendet den Prozess -> EOFError
            if not conn.poll(timeout_s):
                self.stop()
                raise RuntimeError(f"Modell nicht nach {timeout_s:.0f} s geladen")
            antwort = conn.recv()
        except (EOFError, OSError):
            raise RuntimeError("Laden abgebrochen") from None
        if not antwort.get("bereit"):
            self.stop()
            raise RuntimeError(antwort.get("fehler", "unbekannter Fehler"))
        self.bereit = True
        log.info("Modell %s auf %s geladen (%.1f s)", self.repo, self.geraet, antwort["laden_s"])

    def transkribiere(self, audio: np.ndarray, prompt: str | None,
                      max_tokens: int | None = None) -> tuple[str, float]:
        conn, proc = self._conn, self._proc
        if not self.bereit or conn is None or proc is None or not proc.is_alive():
            raise RuntimeError("Whisper-Prozess läuft nicht")
        try:
            conn.send({"audio": audio.astype(np.float32).tobytes(), "prompt": prompt, "max_tokens": max_tokens})
            timeout = 60 + len(audio) / 16000  # großzügig, auch für CPU
            if not conn.poll(timeout):
                self.stop()
                raise RuntimeError("Whisper antwortet nicht (Zeitüberschreitung)")
            antwort = conn.recv()
        except (EOFError, OSError) as e:
            raise RuntimeError(f"Verbindung zu Whisper verloren: {e}") from None
        if "fehler" in antwort:
            raise RuntimeError(antwort["fehler"])
        return antwort["text"], antwort["sek"]

    def stop(self) -> None:
        # Kann gleichzeitig aus mehreren Threads kommen (Pause + Ladethread): Referenzen erst lokal übernehmen
        with self._stop_lock:
            self.gestoppt = True
            self.bereit = False
            conn, proc = self._conn, self._proc
            self._conn = self._proc = None
        if conn is not None:
            try:
                conn.send(None)
            except Exception:  # noqa: BLE001
                pass
        if proc is not None:
            proc.join(timeout=3)
            if proc.is_alive():
                proc.kill()
