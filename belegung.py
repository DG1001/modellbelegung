"""Belegungsstelle für das eine große Modell auf dem GX10.

**Warum es das gibt.** Auf der Maschine passt genau ein großes Modell in den
Speicher. Es gibt aber mehrere Anspruchsteller: der Sprachassistent, die
Gutachten-App, der Pruefstand, kuenftig Agenten aus dem Coder-Arbeitsbereich.
Bisher schaltet jeder um, wann er will -- und am 08.09.2026 hat der Waechter
des Sprachassistenten zweimal mitten in einen laufenden Gutachtenlauf
hineingeschaltet, weil er von ihm nichts wusste.

**Was die Stelle tut und was nicht.** Sie fuehrt Buch, sie schaltet nicht
selbst um. Wer das Modell braucht, meldet sich an; wer ein ANDERES Modell
braucht, bekommt den Wechsel nur, wenn sonst niemand angemeldet ist. Sonst
kommt er in die Warteschlange. Das Umschalten macht weiterhin, wer den
Zuschlag hat -- die Stelle weiss nichts von `model-switch` und muss es nicht.

**Belegungen verfallen.** Ein Klient, der abstuerzt, wuerde das Modell sonst
fuer immer blockieren. Wer laenger braucht, verlaengert.

**Mitbenutzung ist der Normalfall.** Zwei Anspruchsteller, die dasselbe Modell
wollen, stoeren einander nicht -- vLLM bedient mehrere Sitzungen. Nur der
WECHSEL ist der knappe Vorgang, nicht die Benutzung.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WURZEL = Path(__file__).resolve().parent
ZUSTAND = Path(os.environ.get("BELEGUNG_ZUSTAND", WURZEL / "zustand.json"))
MODELLE = Path(os.environ.get("BELEGUNG_MODELLE", WURZEL / "modelle.json"))
BIND = os.environ.get("BELEGUNG_BIND", "127.0.0.1")
PORT = int(os.environ.get("BELEGUNG_PORT", "8930"))

# Vorgabe, wenn niemand eine Dauer nennt. Kurz genug, dass ein abgestuerzter
# Klient nicht lange blockiert; wer laenger braucht, verlaengert.
DAUER_VORGABE = 900
DAUER_MAX = 6 * 3600
# So lange darf ein Wartender vorne stehen, ohne sich zu melden. Danach
# ruecken die anderen auf -- sonst blockiert ein toter Wartender die Schlange.
WARTE_VERFALL = 600

_schloss = threading.RLock()


@dataclass
class Belegung:
    wer: str
    profil: str
    seit: float
    bis: float
    zweck: str = ""
    # "mit"      -- ich nutze, was gerade da ist, und blockiere keinen Wechsel
    # "exklusiv" -- ich brauche GENAU dieses Modell, ein Wechsel wuerde meine
    #               Arbeit abbrechen
    #
    # Der Unterschied ist wesentlich. Der Sprachassistent laeuft dauernd und
    # nimmt, was da ist; die Gutachten-App braucht ihr Modell und muss
    # zwischendurch selbst auf das Bildmodell und zurueck wechseln koennen.
    # Ohne die Unterscheidung haette der stille Mitleser den blockiert, der
    # tatsaechlich arbeitet.
    art: str = "mit"


@dataclass
class Wartend:
    wer: str
    profil: str
    seit: float
    zweck: str = ""


@dataclass
class Zustand:
    # Was tatsaechlich geladen ist. Wird von aussen gemeldet, nicht geraten:
    # die Stelle spricht nicht mit vLLM, damit sie auch dann noch antwortet,
    # wenn der Motor haengt.
    profil: str = ""
    modell: str = ""
    geladen_seit: float = 0.0
    belegungen: list = field(default_factory=list)
    warteschlange: list = field(default_factory=list)


def _laden() -> Zustand:
    try:
        d = json.loads(ZUSTAND.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Zustand()
    z = Zustand(profil=d.get("profil", ""), modell=d.get("modell", ""),
                geladen_seit=d.get("geladen_seit", 0.0))
    z.belegungen = [Belegung(**b) for b in d.get("belegungen", [])]
    z.warteschlange = [Wartend(**w) for w in d.get("warteschlange", [])]
    return z


def _sichern(z: Zustand) -> None:
    d = {"profil": z.profil, "modell": z.modell, "geladen_seit": z.geladen_seit,
         "belegungen": [asdict(b) for b in z.belegungen],
         "warteschlange": [asdict(w) for w in z.warteschlange]}
    tmp = ZUSTAND.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ZUSTAND)          # atomar: ein Absturz beim Schreiben soll
                                  # nicht die halbe Datei hinterlassen


def _aufraeumen(z: Zustand) -> None:
    jetzt = time.time()
    z.belegungen = [b for b in z.belegungen if b.bis > jetzt]
    z.warteschlange = [w for w in z.warteschlange
                       if jetzt - w.seit < WARTE_VERFALL]


def modelle() -> dict:
    try:
        return json.loads(MODELLE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------- Vorgaenge
def status() -> dict:
    with _schloss:
        z = _laden(); _aufraeumen(z); _sichern(z)
        m = modelle().get(z.profil, {})
        jetzt = time.time()
        return {
            "profil": z.profil,
            "modell": z.modell,
            "geladen_seit_s": round(jetzt - z.geladen_seit) if z.geladen_seit else None,
            "beschreibung": m,
            "belegt_von": [{"wer": b.wer, "zweck": b.zweck, "art": b.art,
                            "noch_s": round(b.bis - jetzt)} for b in z.belegungen],
            "warteschlange": [{"wer": w.wer, "profil": w.profil, "zweck": w.zweck,
                               "wartet_s": round(jetzt - w.seit)}
                              for w in z.warteschlange],
            "wechsel_moeglich": not any(b.art == "exklusiv" for b in z.belegungen),
        }


def geladen_melden(profil: str, modell: str) -> dict:
    """Wer umgeschaltet hat, sagt es hier. Die Stelle raet nicht."""
    with _schloss:
        z = _laden(); _aufraeumen(z)
        if profil != z.profil:
            z.profil, z.modell, z.geladen_seit = profil, modell, time.time()
            # Belegungen auf das alte Profil sind gegenstandslos.
            z.belegungen = [b for b in z.belegungen if b.profil == profil]
            z.warteschlange = [w for w in z.warteschlange if w.profil != profil]
        else:
            z.modell = modell or z.modell
        _sichern(z)
        return status()


def belegen(wer: str, profil: str = "", dauer: int = DAUER_VORGABE,
            zweck: str = "", art: str = "mit") -> dict:
    """Anmelden. Gibt zurueck, ob es sofort geht oder ob gewartet wird.

    Drei Faelle:
      - kein Profil genannt oder das laufende gemeint  -> sofort, Mitbenutzung
      - anderes Profil, kein fremdes "exklusiv"        -> Wechsel freigegeben
      - anderes Profil, jemand haelt exklusiv          -> Warteschlange

    `art="exklusiv"` heisst: ein Wechsel wuerde meine Arbeit abbrechen. Wer
    das nicht braucht, meldet "mit" an und blockiert damit niemanden.
    """
    dauer = max(60, min(int(dauer or DAUER_VORGABE), DAUER_MAX))
    art = "exklusiv" if art == "exklusiv" else "mit"
    with _schloss:
        z = _laden(); _aufraeumen(z)
        jetzt = time.time()
        ziel = profil or z.profil

        if not ziel:
            _sichern(z)
            return {"zuschlag": False, "grund": "kein_modell_geladen",
                    "hinweis": "Es ist kein Profil gemeldet. Erst laden, dann melden.",
                    **status()}

        if ziel == z.profil:
            # Mitbenutzung: eigene aeltere Belegung ersetzen, nicht haeufen.
            z.belegungen = [b for b in z.belegungen if b.wer != wer]
            z.belegungen.append(Belegung(wer, ziel, jetzt, jetzt + dauer, zweck, art))
            z.warteschlange = [w for w in z.warteschlange if w.wer != wer]
            _sichern(z)
            return {"zuschlag": True, "wechsel_noetig": False,
                    "bis_s": dauer, **status()}

        # Nur EXKLUSIVE Anmeldungen anderer blockieren einen Wechsel.
        # Mitbenutzer verlieren ihr Modell -- sie haben angemeldet, dass sie
        # nehmen, was da ist.
        fremde = [b for b in z.belegungen if b.wer != wer and b.art == "exklusiv"]
        if not fremde:
            # Wechsel freigegeben. Die Belegung gilt AB JETZT, obwohl das Laden
            # noch zwei Minuten dauert -- sonst faengt der Naechste an
            # umzuschalten, waehrend hier noch geladen wird.
            # Mitbenutzer des ALTEN Profils verlieren es -- sie haben
            # angemeldet, dass sie nehmen, was da ist.
            z.belegungen = [Belegung(wer, ziel, jetzt, jetzt + dauer, zweck, art)]
            z.warteschlange = [w for w in z.warteschlange if w.wer != wer]
            _sichern(z)
            return {"zuschlag": True, "wechsel_noetig": True,
                    "bis_s": dauer,
                    "hinweis": f"Umschalten auf {ziel}, danach /geladen melden.",
                    **status()}

        # Warten. Doppelte Eintraege desselben Anmelders vermeiden.
        if not any(w.wer == wer and w.profil == ziel for w in z.warteschlange):
            z.warteschlange.append(Wartend(wer, ziel, jetzt, zweck))
        _sichern(z)
        vorn = min((b.bis for b in fremde), default=jetzt)
        return {"zuschlag": False, "grund": "belegt",
                "frei_in_s": max(0, round(vorn - jetzt)),
                "platz": [w.wer for w in z.warteschlange].index(wer) + 1,
                **status()}


def verlaengern(wer: str, dauer: int = DAUER_VORGABE) -> dict:
    dauer = max(60, min(int(dauer or DAUER_VORGABE), DAUER_MAX))
    with _schloss:
        z = _laden(); _aufraeumen(z)
        for b in z.belegungen:
            if b.wer == wer:
                b.bis = time.time() + dauer
                _sichern(z)
                return {"ok": True, "bis_s": dauer, **status()}
        _sichern(z)
        return {"ok": False, "grund": "nicht_angemeldet", **status()}


def freigeben(wer: str) -> dict:
    with _schloss:
        z = _laden(); _aufraeumen(z)
        vorher = len(z.belegungen)
        z.belegungen = [b for b in z.belegungen if b.wer != wer]
        z.warteschlange = [w for w in z.warteschlange if w.wer != wer]
        _sichern(z)
        return {"ok": len(z.belegungen) < vorher, **status()}


# ------------------------------------------------------------------ HTTP
class _Griff(BaseHTTPRequestHandler):
    # Kein Zugriffsprotokoll auf stderr -- der Dienst laeuft im Hintergrund,
    # und jede Statusabfrage waere eine Zeile.
    def log_message(self, *_):
        pass

    def _antwort(self, d, code=200):
        leib = json.dumps(d, ensure_ascii=False, indent=1).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(leib)))
        self.end_headers()
        self.wfile.write(leib)

    def _leib(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return {}

    def do_GET(self):
        pfad = self.path.split("?")[0].rstrip("/") or "/"
        if pfad in ("/", "/status"):
            return self._antwort(status())
        if pfad == "/modelle":
            return self._antwort(modelle())
        self._antwort({"fehler": "unbekannter Pfad",
                       "pfade": ["/status", "/modelle", "/belegen",
                                 "/verlaengern", "/freigeben", "/geladen"]}, 404)

    def do_POST(self):
        pfad = self.path.split("?")[0].rstrip("/")
        d = self._leib()
        wer = str(d.get("wer") or "").strip()
        if pfad in ("/belegen", "/verlaengern", "/freigeben") and not wer:
            # Ohne Namen kann die Stelle nicht Buch fuehren -- und genau das
            # ist ihre einzige Aufgabe.
            return self._antwort({"fehler": "wer fehlt"}, 400)
        if pfad == "/belegen":
            return self._antwort(belegen(wer, str(d.get("profil") or ""),
                                         d.get("dauer") or DAUER_VORGABE,
                                         str(d.get("zweck") or ""),
                                         str(d.get("art") or "mit")))
        if pfad == "/verlaengern":
            return self._antwort(verlaengern(wer, d.get("dauer") or DAUER_VORGABE))
        if pfad == "/freigeben":
            return self._antwort(freigeben(wer))
        if pfad == "/geladen":
            return self._antwort(geladen_melden(str(d.get("profil") or ""),
                                                str(d.get("modell") or "")))
        self._antwort({"fehler": "unbekannter Pfad"}, 404)


def main():
    # Nie an 0.0.0.0: die Maschine hat eine weltweit geroutete IPv6 ohne NAT
    # davor, und dieser Dienst entscheidet, wer das Modell bekommt.
    srv = ThreadingHTTPServer((BIND, PORT), _Griff)
    print(f"Belegungsstelle auf http://{BIND}:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
