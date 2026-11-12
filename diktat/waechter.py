"""Wächter: startet das Diktier-Tool und startet es nach einem Absturz neu.

Exit-Codes des Tools:
  0 = regulär beendet (Menü „Beenden“)  -> Wächter hört auf
  3 = läuft schon (zweite Instanz)      -> Wächter hört auf
  4 = Neustart gewünscht (Menü)         -> sofort neu starten
  alles andere = Absturz                -> nach kurzer Pause neu starten
Mehr als 5 Abstürze in 10 Minuten: Der Wächter gibt auf (sonst Endlosschleife), siehe logs/waechter.log.
"""
import ctypes
import logging
import os
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import PROJEKT

EXIT_OK, EXIT_LAEUFT_SCHON, EXIT_NEUSTART = 0, 3, 4
MAX_ABSTUERZE, FENSTER_S = 5, 600
CREATE_NO_WINDOW = 0x08000000
MUTEX_NAME = "Local\\whisper-diktat-waechter"  # Tests setzen einen eigenen Namen
LOG_NAME = "waechter.log"
log = logging.getLogger("waechter")


def pythonw() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def main() -> None:
    (PROJEKT / "logs").mkdir(exist_ok=True)
    h = RotatingFileHandler(PROJEKT / "logs" / LOG_NAME, maxBytes=200_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[h])

    ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:
        log.info("Wächter läuft schon – beende mich")
        return

    env = dict(os.environ, DIKTAT_WAECHTER="1")
    abstuerze: list[float] = []
    log.info("Wächter gestartet")
    while True:
        t0 = time.monotonic()
        proc = subprocess.Popen([pythonw(), "-m", "diktat"], cwd=PROJEKT, env=env, creationflags=CREATE_NO_WINDOW)
        rc = proc.wait()
        lief_s = time.monotonic() - t0
        if rc == EXIT_OK:
            log.info("Tool regulär beendet (lief %.0f s) – Wächter endet", lief_s)
            return
        if rc == EXIT_LAEUFT_SCHON:
            log.info("Tool läuft bereits außerhalb des Wächters – Wächter endet")
            return
        if rc == EXIT_NEUSTART:
            log.info("Neustart gewünscht")
            continue
        jetzt = time.monotonic()
        abstuerze = [t for t in abstuerze if jetzt - t < FENSTER_S] + [jetzt]
        log.error("Tool abgestürzt (Exit-Code %s, lief %.0f s) – Absturz %d/%d in 10 min",
                  rc, lief_s, len(abstuerze), MAX_ABSTUERZE)
        if len(abstuerze) >= MAX_ABSTUERZE:
            log.error("Zu viele Abstürze – gebe auf. Details in logs/diktat.log")
            return
        time.sleep(3 * len(abstuerze))


if __name__ == "__main__":
    main()
