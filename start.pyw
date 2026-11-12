#!%USERPROFILE%\.venvs\whisper\Scripts\pythonw.exe
"""Startet whisper-diktat mit Wächter, ohne Konsolenfenster.

Doppelklick genügt (der Windows-Python-Launcher liest die erste Zeile und nimmt die richtige Umgebung).
Wird auch vom Autostart benutzt.
"""
import os
import sys
from pathlib import Path

projekt = Path(__file__).resolve().parent
sys.path.insert(0, str(projekt))
os.chdir(projekt)

from diktat.waechter import main  # noqa: E402

main()
