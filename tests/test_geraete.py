"""Tests für die Auswahl von Recheneinheit und Mikrofon (Menü „Recheneinheit“ / „Mikrofon“).
Keine echten Tastatureingaben, config.toml wird nicht verändert.

Aufruf (im Projektordner):  %USERPROFILE%\\.venvs\\whisper\\Scripts\\python.exe -m tests.test_geraete
"""
import sys
import time

import diktat.__main__ as hauptmodul
from diktat import geraete
from diktat.recorder import RATE, Recorder

FEHLER = []


def pruefe(name, bedingung):
    print(("OK    " if bedingung else "FEHLER"), name)
    if not bedingung:
        FEHLER.append(name)


def test_aufloesen():
    alle = [("GPU", "Arc"), ("NPU", "AI Boost"), ("CPU", "Core")]
    nur_cpu = [("CPU", "Ryzen")]
    zwei_gpu = [("GPU.0", "Iris"), ("GPU.1", "Arc A770"), ("CPU", "Core")]
    pruefe("auto -> GPU, wenn vorhanden", geraete.loese_geraet("auto", alle) == "GPU")
    pruefe("auto -> CPU ohne Grafik", geraete.loese_geraet("auto", nur_cpu) == "CPU")
    pruefe("auto -> erste Grafik bei zwei Grafikkarten", geraete.loese_geraet("auto", zwei_gpu) == "GPU.0")
    pruefe("Gewählte NPU wird genommen", geraete.loese_geraet("NPU", alle) == "NPU")
    pruefe("Gewählte, aber fehlende Grafik -> automatisch (CPU)", geraete.loese_geraet("GPU", nur_cpu) == "CPU")
    pruefe("Anzeigename", geraete.art("GPU") == "Grafik" and geraete.art("GPU.1") == "Grafik 1")


def test_echte_geraete():
    r = geraete.recheneinheiten()
    ids = [g for g, _ in r]
    print(f"      Recheneinheiten: {r}")
    pruefe("Dieser Laptop: Grafik, NPU und CPU erkannt", {"GPU", "NPU", "CPU"} <= set(ids))
    pruefe("Reihenfolge: Grafik zuerst, CPU zuletzt", ids[0].startswith("GPU") and ids[-1] == "CPU")
    m = geraete.mikrofone()
    print(f"      Mikrofone: {m}")
    pruefe("Mindestens ein Mikrofon, ohne Windows-Weiterleitungen",
           len(m) >= 1 and not any(n.startswith(geraete.KEINE_MIKROFONE) for n in m))


def test_mikrofon_waehlen():
    namen = geraete.mikrofone()
    r = Recorder(mikrofon=namen[0])
    r.start()
    time.sleep(0.3)
    gewaehlt = r._stream.device  # noqa: SLF001
    a = r.stop()
    pruefe("Gewähltes Mikrofon wird geöffnet", gewaehlt == geraete.mikrofon_nummer(namen[0]) and len(a) > 0)

    r = Recorder(mikrofon="Gibt es nicht (abgezogen)")
    r.start()
    time.sleep(0.3)
    a = r.stop()
    pruefe("Fehlendes Mikrofon: nimmt Windows-Standard und merkt es sich", r.mikrofon_fehlt and len(a) > 0)
    r.waehle("")
    pruefe("Zurück auf Windows-Standard", r.mikrofon == "" and not r.mikrofon_fehlt)

    r = Recorder(offen_halten=True, mikrofon="")
    r.bereit_machen()
    vorher = r._stream  # noqa: SLF001
    r.waehle(namen[0])
    pruefe("Offen gehaltenes Mikrofon wird beim Wechsel neu geöffnet",
           r._stream is not None and r._stream is not vorher and r._stream.active)  # noqa: SLF001
    r.schliessen()


def test_menue():
    for f in ("speichere_modell", "speichere_geraet", "speichere_mikrofon", "speichere_modus"):
        setattr(hauptmodul, f, lambda *a: None)
    app = hauptmodul.App()
    menue = app.tray.icon.menu
    oben = [str(getattr(i, "text", "")) for i in menue.items]
    pruefe("Menü hat Modell, Recheneinheit, Mikrofon, Bedienung",
           all(x in oben for x in ("Modell", "Recheneinheit", "Mikrofon", "Bedienung")))
    unter = {i.text: [str(u.text) for u in i.submenu.items] for i in menue.items if i.submenu}
    print(f"      Recheneinheit: {unter['Recheneinheit']}")
    print(f"      Mikrofon:      {unter['Mikrofon']}")
    pruefe("Recheneinheit: Automatisch + alle erkannten Einheiten",
           unter["Recheneinheit"][0].startswith("Automatisch")
           and len(unter["Recheneinheit"]) == 1 + len(app.recheneinheiten))
    pruefe("Mikrofon: Windows-Standard + alle Mikrofone",
           unter["Mikrofon"][0].startswith("Windows-Standard")
           and len(unter["Mikrofon"]) == 1 + len(app.mikrofone()))
    pruefe("Modell: Turbo und Large-v3", len(unter["Modell"]) == 2)

    app.recorder.mikrofon = "Headset (abgezogen)"
    app.tray.menue_neu_bauen()
    mik = [str(u.text) for i in app.tray.icon.menu.items if i.text == "Mikrofon" for u in i.submenu.items]
    pruefe("Gewähltes, aber abgezogenes Mikrofon steht mit Hinweis im Menü",
           any("Headset (abgezogen)" in t and "nicht angeschlossen" in t for t in mik))


if __name__ == "__main__":
    test_aufloesen()
    test_echte_geraete()
    test_mikrofon_waehlen()
    test_menue()
    print(f"\n{len(FEHLER)} Fehler" + (": " + ", ".join(FEHLER) if FEHLER else ""))
    sys.exit(1 if FEHLER else 0)
