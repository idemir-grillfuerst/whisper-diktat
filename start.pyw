"""Startet whisper-diktat mit Wächter, ohne Konsolenfenster.

Normaler Weg: die Verknüpfung „Whisper Diktat starten“ (ruft pythonw.exe der Umgebung mit dieser Datei auf).
Wird auch vom Autostart benutzt.

Doppelklick auf diese Datei geht auch: Läuft sie mit einem Python ohne die nötigen Pakete, sucht sie die
Umgebung selbst (Umgebungsvariable WHISPER_DIKTAT_VENV, sonst %USERPROFILE%\\.venvs\\whisper) und startet
sich dort neu.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

projekt = Path(__file__).resolve().parent


def umgebung() -> Path:
    return Path(os.environ.get("WHISPER_DIKTAT_VENV") or Path.home() / ".venvs" / "whisper")


if importlib.util.find_spec("openvino_genai") is None:
    pythonw = umgebung() / "Scripts" / "pythonw.exe"
    if pythonw.exists() and Path(sys.executable).resolve() != pythonw.resolve():
        subprocess.Popen([str(pythonw), str(Path(__file__).resolve())], cwd=projekt)
        sys.exit(0)
    import ctypes
    ctypes.windll.user32.MessageBoxW(
        None, f"Python-Umgebung nicht gefunden: {pythonw}\n\nBitte zuerst install.ps1 ausführen (siehe INSTALL.md).",
        "whisper-diktat", 0x10)
    sys.exit(1)

sys.path.insert(0, str(projekt))
os.chdir(projekt)

from diktat.waechter import main  # noqa: E402

main()
