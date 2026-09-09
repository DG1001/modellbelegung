# Eine Anwendung an die Belegungsstelle anbinden

Für Sessions, die eine App betreuen, die das große Modell auf dem GX10 nutzt.

## Worum es geht

Auf dem GX10 passt **ein** großes Modell in den Speicher (121 GiB). Mehrere
Anwendungen wollen es: der Sprachassistent kihiwi, die Gutachten-App, der
LLM-Prüfstand, künftig Agenten aus dem Coder-Arbeitsbereich. Umgeschaltet wird
mit `model-switch <profil>`, und das dauert **rund zwei Minuten**.

Bisher schaltete jeder um, wann er wollte. Am 08.09.2026 hat der Wächter des
Sprachassistenten deshalb zweimal mitten in einen laufenden Gutachtenlauf
hineingeschaltet — die Arbeit war weg.

Die Belegungsstelle (`http://127.0.0.1:8930`) führt darüber Buch. Sie schaltet
**nicht selbst** um; sie sagt nur, ob du darfst.

## Die eine Regel

> **Mitbenutzung ist frei, der Wechsel ist knapp.**

Zwei Anwendungen, die dasselbe Modell benutzen, stören einander nicht — vLLM
bedient mehrere Sitzungen gleichzeitig. Nur das **Umschalten** ist der
ausschließende Vorgang.

## Zwei Arten von Anmeldung

| | wann | blockiert einen Wechsel |
|---|---|---|
| `mit` (Vorgabe) | du nimmst, was gerade geladen ist | nein |
| `exklusiv` | ein Wechsel würde deine Arbeit abbrechen | **ja** |

**Eine Batch-Anwendung meldet `exklusiv` an.** Damit kann niemand sonst
umschalten, solange sie läuft. Sie selbst darf trotzdem wechseln — die eigene
Anmeldung blockiert nicht.

## Der kürzeste Weg (Shell)

```bash
K=~/Developer/github.com/modellbelegung/belegung-klient.sh

# anmelden, exklusiv, für eine Stunde
"$K" belegen gutachten qwen38 exklusiv 3600 "Arbeiten bewerten"
case $? in
  0)  : ;;                       # Zuschlag, richtiges Modell läuft schon
  10) model-switch qwen38 ;;     # Zuschlag, aber DU musst umschalten
  20) echo "belegt, später"; exit 1 ;;
  30) : ;;                       # Stelle nicht erreichbar -> weitermachen
esac

# ... Arbeit ...

"$K" freigeben gutachten
```

`model-switch` meldet den Wechsel selbst an die Stelle. Du musst nach dem
Umschalten nichts extra tun.

## Aus Python

```python
import urllib.request, json

B = "http://127.0.0.1:8930"

def belegung(pfad, **d):
    """Gibt None zurück, wenn die Stelle nicht erreichbar ist —
    dann arbeitet man weiter wie zuvor."""
    try:
        r = urllib.request.Request(f"{B}/{pfad}", data=json.dumps(d).encode(),
                                   headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(r, timeout=5))
    except Exception:
        return None

# Am Anfang
a = belegung("belegen", wer="gutachten", profil="qwen38", art="exklusiv",
             dauer=3600, zweck="Bachelorarbeiten bewerten")
if a and not a["zuschlag"]:
    print(f"Modell belegt von {[x['wer'] for x in a['belegt_von']]}, "
          f"frei in {a.get('frei_in_s')} s")
    raise SystemExit(1)
if a and a["wechsel_noetig"]:
    subprocess.run(["model-switch", "qwen38"], check=True)

# Zwischendurch auf das Bildmodell und zurück — geht ohne Rückfrage,
# solange die eigene Anmeldung steht:
belegung("belegen", wer="gutachten", profil="qwenvl30", art="exklusiv")
subprocess.run(["model-switch", "qwenvl30"], check=True)
# ... Abbildungen lesen ...
belegung("belegen", wer="gutachten", profil="qwen38", art="exklusiv")
subprocess.run(["model-switch", "qwen38"], check=True)

# Am Ende — wichtig, sonst blockiert die Anmeldung bis zum Verfall
belegung("freigeben", wer="gutachten")
```

## Vier Dinge, die man leicht falsch macht

**Freigeben vergessen.** Belegungen verfallen zwar (Vorgabe 15 min, Höchstwert
6 h), aber bis dahin wartet der Nächste. Bei langen Läufen `verlaengern`
aufrufen statt eine große Dauer anzugeben — dann gibt ein Absturz das Modell
nach 15 Minuten frei statt nach sechs Stunden.

**Die Stelle als Erlaubnisinstanz missverstehen.** Ist sie nicht erreichbar
(HTTP-Fehler, Rückgabe `30`), heißt das **nicht** „verboten". Dann arbeitet man
weiter wie vor ihrer Einführung. Eine ausgefallene Buchführung darf die
Maschine nicht lahmlegen.

**`exklusiv` aus Gewohnheit setzen.** Wer nur benutzt, was ohnehin läuft, nimmt
`mit` — sonst blockiert man andere ohne Not.

**Vergessen, dass ein Wechsel zwei Minuten kostet.** Wer im Wechsel Text- und
Bildmodell braucht, sollte die Arbeit bündeln: erst alle Abbildungen, dann
alles Textliche. Zehnmal hin und her sind zwanzig Minuten Ladezeit.

## Was gerade läuft, ansehen

```bash
curl -s http://127.0.0.1:8930/status | python3 -m json.tool
```

`/status` liefert auch eine Beschreibung des geladenen Modells — Durchsatz,
Fähigkeiten, bekannte Schwächen, alles gemessen. **Vor einem Wechsel lohnt der
Blick:** oft taugt das, was schon da ist.
