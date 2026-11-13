"""Verfügbare Recheneinheiten (OpenVINO) und Mikrofone ermitteln."""
import logging
import re

import sounddevice as sd

log = logging.getLogger(__name__)

ART = {"GPU": "Grafik", "NPU": "NPU", "CPU": "CPU"}
# Diese Einträge sind keine echten Mikrofone, sondern Weiterleitungen auf den Windows-Standard
KEINE_MIKROFONE = ("Microsoft Soundmapper", "Primärer Soundaufnahmetreiber", "Primary Sound Capture")


def _kuerzen(name: str) -> str:
    return re.sub(r"\s+", " ", name.replace("(R)", "").replace("(TM)", "").replace("®", "")).strip()


def recheneinheiten() -> list[tuple[str, str]]:
    """[(OpenVINO-Gerät, Anzeigename)], z. B. [("CPU", "Intel Core Ultra 7 255H"), ("GPU", "Intel Arc 140T GPU …")].
    Wird einmal beim Start abgefragt (Import von OpenVINO dauert ~1 s)."""
    try:
        import openvino as ov

        core = ov.Core()
        liste = []
        for g in core.available_devices:
            try:
                name = _kuerzen(core.get_property(g, "FULL_DEVICE_NAME"))
            except Exception:  # noqa: BLE001
                name = g
            liste.append((g, name))
        reihenfolge = {"GPU": 0, "NPU": 1, "CPU": 2}
        return sorted(liste, key=lambda x: (reihenfolge.get(x[0].split(".")[0], 9), x[0]))
    except Exception:  # noqa: BLE001
        log.exception("Recheneinheiten konnten nicht ermittelt werden – nehme CPU")
        return [("CPU", "CPU")]


def loese_geraet(wahl: str, verfuegbar: list[tuple[str, str]]) -> str:
    """'auto' -> erste Grafik, sonst CPU. Eine gewählte, aber nicht (mehr) vorhandene Einheit -> wie 'auto'."""
    ids = [g for g, _ in verfuegbar]
    if wahl != "auto" and wahl in ids:
        return wahl
    if wahl != "auto":
        log.warning("Recheneinheit %s ist nicht vorhanden (%s) – nehme automatisch", wahl, ", ".join(ids))
    for g in ids:
        if g.split(".")[0] == "GPU":
            return g
    return "CPU" if "CPU" in ids or not ids else ids[0]


def art(geraet: str) -> str:
    """'GPU.1' -> 'Grafik 1', 'NPU' -> 'NPU'."""
    basis, _, nr = geraet.partition(".")
    return ART.get(basis, basis) + (f" {nr}" if nr else "")


def mikrofone() -> list[str]:
    """Namen aller Eingabegeräte der Standard-Audioschnittstelle (MME), ohne die Windows-Weiterleitungen.
    Die Namen sind bei MME auf 31 Zeichen gekürzt, aber stabil, anders als die Gerätenummern."""
    try:
        api = sd.default.hostapi
        namen = []
        for d in sd.query_devices():
            if d["max_input_channels"] > 0 and d["hostapi"] == api and not d["name"].startswith(KEINE_MIKROFONE):
                if d["name"] not in namen:
                    namen.append(d["name"])
        return namen
    except Exception:  # noqa: BLE001
        log.exception("Mikrofone konnten nicht ermittelt werden")
        return []


def mikrofon_nummer(name: str) -> int | None:
    """Gerätenummer zum Namen (nur Standard-Audioschnittstelle), None wenn nicht vorhanden."""
    if not name:
        return None
    api = sd.default.hostapi
    for i, d in enumerate(sd.query_devices()):
        if d["name"] == name and d["max_input_channels"] > 0 and d["hostapi"] == api:
            return i
    return None
