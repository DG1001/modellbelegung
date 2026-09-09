#!/usr/bin/env bash
# Kleiner Klient fuer Skripte, die kein Python bemuehen wollen.
#
#   belegung-klient.sh belegen  <wer> [profil] [art] [dauer] [zweck]
#   belegung-klient.sh freigeben <wer>
#   belegung-klient.sh geladen  <profil> <modell>
#   belegung-klient.sh status
#
# Rueckgabe bei "belegen":
#   0  Zuschlag, kein Wechsel noetig
#   10 Zuschlag, DU musst umschalten (danach "geladen" melden)
#   20 belegt -- warten
#   30 Belegungsstelle nicht erreichbar
#
# **Nicht erreichbar heisst nicht "verboten".** Wer die Stelle nicht erreicht,
# soll weiterarbeiten koennen -- sonst legt ein Ausfall der Buchfuehrung die
# ganze Maschine lahm. Der Aufrufer entscheidet, was er daraus macht.
set -u
B="${BELEGUNG_URL:-http://127.0.0.1:8930}"

_post() { curl -sf --max-time 5 -X POST "$B/$1" -d "$2" 2>/dev/null; }

case "${1:-status}" in
  belegen)
    a=$(_post belegen "{\"wer\":\"${2:?wer fehlt}\",\"profil\":\"${3:-}\",\"art\":\"${4:-mit}\",\"dauer\":${5:-900},\"zweck\":\"${6:-}\"}") \
      || { echo "belegungsstelle nicht erreichbar" >&2; exit 30; }
    echo "$a"
    python3 -c "
import json,sys
d=json.load(sys.stdin)
sys.exit(0 if d.get('zuschlag') and not d.get('wechsel_noetig')
         else 10 if d.get('zuschlag') else 20)" <<< "$a" ;;
  freigeben) _post freigeben "{\"wer\":\"${2:?wer fehlt}\"}" >/dev/null || exit 30 ;;
  geladen)   _post geladen "{\"profil\":\"${2:?profil fehlt}\",\"modell\":\"${3:-}\"}" >/dev/null || exit 30 ;;
  status)    curl -sf --max-time 5 "$B/status" || { echo "nicht erreichbar" >&2; exit 30; } ;;
  *) echo "belegen | freigeben | geladen | status" >&2; exit 2 ;;
esac
