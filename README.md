# modellbelegung

Wer darf das eine große Modell auf dem GX10 laden — und wer muss warten.

## Wozu

Auf der Maschine passt genau **ein** großes Modell in den Speicher. Ansprüche
darauf haben inzwischen mehrere: der Sprachassistent, die Gutachten-App, der
Prüfstand, künftig Agenten aus dem Coder-Arbeitsbereich.

Bisher schaltet jeder um, wann er will. Am 08.09.2026 hat der Wächter des
Sprachassistenten deshalb zweimal mitten in einen laufenden Gutachtenlauf
hineingeschaltet — er wusste von ihm nichts.

## Der Grundsatz

**Mitbenutzung ist frei, der Wechsel ist knapp.** Zwei Anspruchsteller, die
dasselbe Modell wollen, stören einander nicht; vLLM bedient mehrere Sitzungen.
Nur das Umschalten ist der teure, ausschließende Vorgang — und es kostet zwei
Minuten.

Ein Wechsel wird deshalb nur freigegeben, wenn **niemand sonst angemeldet
ist**. Sonst kommt der Anfragende in die Warteschlange.

## Die Stelle führt Buch, sie schaltet nicht

Sie kennt `model-switch` nicht und spricht auch nicht mit vLLM — damit sie
noch antwortet, wenn der Motor hängt. Wer den Zuschlag hat, schaltet selbst um
und meldet danach über `/geladen`, was jetzt läuft.

## Zwei Arten von Anmeldung

| | wer | blockiert einen Wechsel |
|---|---|---|
| `mit` (Vorgabe) | der Sprachassistent — nimmt, was gerade da ist | **nein** |
| `exklusiv` | Gutachten-App, LLM-Prüfstand — braucht genau dieses Modell | ja |

Der Unterschied ist wesentlich. Ohne ihn hätte der stille Mitleser den
blockiert, der tatsächlich arbeitet: der Sprachassistent läuft dauernd, die
Gutachten-App muss zwischendurch selbst auf das Bildmodell wechseln und
zurück. Mit `exklusiv` geht das **ohne Rückfrage**, obwohl ein Mitbenutzer
angemeldet ist.

## Endpunkte

| | |
|---|---|
| `GET /status` | was läuft, wer hat es, wer wartet, **und wozu das Modell taugt** |
| `GET /modelle` | alle Profile mit Fähigkeiten und Messwerten |
| `POST /belegen` | `{wer, profil?, dauer?, zweck?}` → Zuschlag oder Warteplatz |
| `POST /verlaengern` | `{wer, dauer?}` |
| `POST /freigeben` | `{wer}` |
| `POST /geladen` | `{profil, modell}` — nach dem Umschalten melden |

**Belegungen verfallen** (Vorgabe 15 min, Höchstwert 6 h). Ein abgestürzter
Klient blockiert damit nicht für immer; wer länger braucht, verlängert.
Wartende verfallen nach 10 Minuten, sonst blockiert ein toter Wartender die
Schlange.

## Die Modellbeschreibung ist der eigentliche Punkt

`/status` liefert nicht nur „belegt/frei", sondern **wozu das geladene Modell
taugt** — Durchsatz, Fähigkeiten, Eignung, bekannte Schwächen, alles gemessen
und mit Quelle. Ein Agent soll damit *arbeiten* statt zu wechseln:

    Geladen  : Qwen3.8-27B NVFP4 + MTP (dicht, 27B)
    Kontext  : 131072, 20.0 tok/s
    Kann     : werkzeugaufrufe, deutsch, code
    Eignung  : Dichtes Modell, gründlich. Für Aufgaben, bei denen Sorgfalt vor Tempo geht.
    Schwäche : Viermal langsamer als die MoE-Modelle …
    Belegt   : ['gutachten'], Wechsel möglich: False

Ein Wechsel lohnt nur, wenn eine Fähigkeit wirklich fehlt — Bilder etwa kann
nur `qwenvl30`.

## Betrieb

    python3 belegung.py          # http://127.0.0.1:8930

Bindet auf `127.0.0.1`. **Nie an `0.0.0.0`:** die Maschine hat eine weltweit
geroutete IPv6 ohne NAT davor, und dieser Dienst entscheidet, wer das Modell
bekommt.

Übersteuerbar: `BELEGUNG_BIND`, `BELEGUNG_PORT`, `BELEGUNG_ZUSTAND`,
`BELEGUNG_MODELLE`.

## Angebunden

`belegung-klient.sh` ist der Weg für Skripte. Rückgabewerte: `0` Zuschlag,
`10` Zuschlag **mit** Umschaltpflicht, `20` warten, `30` Stelle nicht
erreichbar.

- **`model-switch`** meldet nach jedem Wechsel `/geladen` — es *fragt* nicht.
  Wer es von Hand aufruft, hat sich entschieden; ein Werkzeug, das sich
  weigert, hätte kein Vorbild. Fragen müssen die automatischen Anrufer.
- **Der kihiwi-Wächter** fragt vor jedem Neustart und hält still, wenn jemand
  exklusiv angemeldet ist.

**`30` heißt nicht „verboten".** Fällt die Belegungsstelle aus, arbeiten alle
weiter wie zuvor — sonst legt der Ausfall der Buchführung die Maschine lahm.

## Eine Anwendung anbinden

→ **[ANBINDUNG.md](ANBINDUNG.md)** — Anleitung für Shell und Python, mit den
vier Dingen, die man leicht falsch macht.

## Noch nicht gebaut

- **Die Gutachten-App** trägt sich noch nicht ein.
- **MCP-Server** als Hülle für Agenten.
- **Oberfläche** für die Warteschlange.
