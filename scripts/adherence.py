#!/usr/bin/env python3
"""
Adherencia = aritmetica sobre logs/progress.md, nada de interpretacion ni IA.

Reporta hechos (racha, dias desde ultima sesion, total de sesiones) sin emitir juicio sobre
si eso es "suficiente" o "poco". Ese juicio, si se hace, lo hace la persona a partir del cruce
con competencia (ver docs/REFERENCIA.md, tabla delta x adherencia), no este script.
"""
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

LINE_PREFIX_RE = None


def parse_log_line(line):
    """Parsea una linea de datos del log. Una linea de datos empieza con el
    anio ISO (digito '2'); todo lo demas se descarta devolviendo None. Devuelve
    un dict campo->valor, o None.

    Reglas de parseo (corrigen CONFIRM-N bugs 3 y 4, mismo fallo que
    validate_evidence.py porque ambos parsean el mismo formato de log):

    1. `notes=` es TERMINAL. El campo `notes` es texto libre por diseño y va
       ultimo en el formato documentado; una nota puede contener `|` y `key=`.
       El split por `|` no protege ese contenido, asi que al encontrar
       `notes=` se reconstruye la nota juntando ese parte y todos los
       siguientes con `|`, y se deja de procesar mas campos. Antes, una nota
       inocente con un `|` (ej. `notes="me trabe | skill=otro"`) inyectaba un
       `skill=` falso y corrompia en silencio el filtro `--skill`.

    2. Clave repetida: gana la PRIMERA ocurrencia (determinista). adherence es
       aritmetica pura, no interpreta ni emite juicios (no puede fallar ante
       un log ambiguo), asi que aplica una regla fija y predecible en vez del
       viejo "ultimo gana" que invertia silenciosamente el resultado del
       filtro. Coherencia con validate_evidence.py: un log con claves
       repetidas es invalido para validar (alla se rechaza) y, mientras
       tanto, predecible para adherencia (aca gana la primera).
    """
    line = line.strip()
    if not line or not line.startswith("2"):  # las lineas de datos empiezan con el año ISO
        return None
    fields = {}
    parts = [p.strip() for p in line.split("|")]
    fields["timestamp"] = parts[0].strip()
    for i, part in enumerate(parts[1:], start=1):
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        # notes= es TERMINAL: todo lo que sigue (pipes incluidos) es texto
        # libre de la nota. Reconstruimos la nota juntando este parte y los
        # restantes; las comillas no protegen su contenido del split por '|'.
        if k == "notes":
            remainder = v
            if i + 1 < len(parts):
                remainder = "|".join([remainder] + parts[i + 1:])
            fields["notes"] = remainder.strip().strip('"')
            break
        # Clave repetida: gana la PRIMERA ocurrencia (determinista, no "ultimo
        # gana"). No se emite error: este script reporta hechos, no interpreta.
        if k not in fields:
            fields[k] = v.strip().strip('"')
    return fields


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("logfile")
    ap.add_argument("--skill", default=None)
    ap.add_argument("--subskill", default=None)
    args = ap.parse_args(argv[1:])

    path = Path(args.logfile)
    if not path.exists():
        print(f"no existe {path}")
        return 1

    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_log_line(line)
        if not parsed:
            continue
        if args.skill and parsed.get("skill") != args.skill:
            continue
        if args.subskill and parsed.get("subskill") != args.subskill:
            continue
        try:
            ts = datetime.fromisoformat(parsed["timestamp"])
        except (KeyError, ValueError):
            continue
        # Normalizar a naive: mezclar aware (ej. "+00:00") con naive hace
        # crashear el sort posterior con TypeError. El log real es naive, asi
        # que esto no cambia el caso real; solo hace comparables los mixtos.
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        entries.append((ts, parsed))

    if not entries:
        print("sin entradas para el filtro dado")
        return 0

    entries.sort(key=lambda e: e[0])
    days_with_activity = sorted({e[0].date() for e in entries})

    streak = 1
    best_streak = 1
    for i in range(1, len(days_with_activity)):
        if (days_with_activity[i] - days_with_activity[i - 1]) == timedelta(days=1):
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 1

    last_day = days_with_activity[-1]
    days_since_last = (datetime.now().date() - last_day).days

    print(f"sesiones registradas: {len(entries)}")
    print(f"dias distintos con actividad: {len(days_with_activity)}")
    print(f"racha mas larga (dias consecutivos): {best_streak}")
    print(f"ultima sesion: {last_day.isoformat()} ({days_since_last} dias atras)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
