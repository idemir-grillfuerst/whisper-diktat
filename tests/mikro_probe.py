"""Misst, wie lange das Mikrofon nach dem Öffnen nur Nullen liefert (Headset-Aufwachzeit).

Aufruf: python -m tests.mikro_probe [sekunden]
Öffnet das Standard-Mikrofon zweimal hintereinander und meldet, ab wann echte Signale kommen.
Es wird nichts gespeichert.
"""
import sys
import time

import numpy as np
import sounddevice as sd

RATE = 16000
dauer = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0


def probe(name):
    t0 = time.perf_counter()
    audio = sd.rec(int(dauer * RATE), samplerate=RATE, channels=1, dtype="float32", blocking=True)[:, 0]
    offen = time.perf_counter() - t0 - dauer
    nz = np.flatnonzero(np.abs(audio) > 1e-6)
    erstes = nz[0] / RATE if len(nz) else None
    bloecke = [float(np.abs(audio[i:i + RATE // 4]).max()) for i in range(0, len(audio), RATE // 4)]
    print(f"{name}: erstes Signal nach {erstes if erstes is None else round(erstes, 2)} s | "
          f"Spitze je 0,25 s: {' '.join(f'{b:.3f}' for b in bloecke)}")


print("Standard-Mikrofon:", sd.query_devices(kind="input")["name"])
probe("kalt ")
probe("warm ")
