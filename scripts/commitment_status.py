#!/usr/bin/env python3
"""
Reporta el estado de los compromisos ACTIVOS respecto de su ventana
baseline/checkpoint.

Para cada nodo `type: skill_contract` con `status: active` encontrado en los
directorios que se le pasen, reporta hechos deterministas sobre la ventana y
sobre la evidencia registrada desde el baseline:

  - dias transcurridos desde `baseline_date` y dias restantes hasta
    `checkpoint_date` (y el total de la ventana).
  - cuantas lineas de evidencia del log cumplen: `skill=` igual al `skill:` del
    contrato Y timestamp >= `baseline_date`. Regla simple y determinista; no
    hay otra.
  - hace cuantos dias fue la ultima de esas lineas, o que no hay ninguna.

Emite AVISOS (no cambian el exit code, que sigue 0) cuando:
  - el `checkpoint_date` ya paso y el contrato sigue en `active`: la ventana se
    cerro y nadie registro el checkpoint.
  - no hay ninguna evidencia desde el baseline.

Los contratos `skill_contract` que NO estan en `active` (draft, checkpoint_done,
discontinued) se omiten y se informa cuantos se omitieron (nada de omision
silenciosa), igual que validate_contracts.py con los no-nodos.

FEAT-DISCONTINUED: `discontinued` es un estado TERMINAL (el compromiso o
seguimiento se cerro SIN llegar al checkpoint). Se omite igual que draft y
checkpoint_done y NO emite ningun aviso, ni siquiera el de "sin evidencia desde
el baseline": la persona ya lo cerro, no hay nada que senalarle. Es el GPS que
deja de insistir con un destino que decidiste no visitar.

QUE NO GARANTIZA (limites declarados, como todos los scripts de este proyecto):

  - NO evalua si la practica fue suficiente ni de calidad. Solo cuenta
    sesiones y resta fechas. El compromiso de frecuencia ("practicar al menos
    4 veces por semana") vive en PROSA en el cuerpo del contrato, no en un
    campo; este script NO agrega estructura (tipo `sessions_per_week`) para
    que la maquina pueda opinar sobre el. La comparacion contra el compromiso
    la hace la persona. Es la linea que docs/REFERENCIA.md traza entre adherencia
    (aritmetica pura sobre timestamps) y competencia (lo que mide
    verification_type): nunca se combinan en un solo numero.

  - NO es un gate ni juzga. No hay errores por "practicaste poco": eso no es
    invalido, es un hecho sobre el proceso. Exit 1 se reserva para fallos
    operativos (log inexistente, argumentos faltantes, directorio
    inexistente). El resto es exit 0, con avisos si aplica. No inventa un
    umbral de "suficiente".

  - NO valida la forma de los contratos (campos requeridos, fechas ISO
    validas, ventana invertida, etc.): eso es trabajo de validate_contracts.py.
    Si un contrato activo no tiene `baseline_date`/`checkpoint_date` o no son
    fechas parseables, no se puede medir la ventana: se emite un aviso y se
    saltea su reporte (no se adivina).

  - NO duplica ni importa otros scripts. adherence.py hace aritmetica sobre el
    log y no sabe de contratos; validate_evidence.py cruza evidencia con
    contratos para integridad referencial. El parseo del log y del frontmatter
    se reimplementa aca, minimo, a proposito.

OJO con el formato del log (mismo fallo ya cerrado en adherence.py y
validate_evidence.py): `notes=` es TERMINAL (todo lo que sigue, pipes
incluidos, es texto libre de la nota) y una clave repetida hace la linea
ambigua. El parseo de aca reproduce esas dos reglas para no reintroducir el
bypass donde una nota con `| skill=otro` se colaba como evidencia de otra
habilidad.

stdlib solamente, sin red, sin dependencias externas. Exit 0 = reporte emitido
(puede haber avisos); exit 1 = fallo operativo.

Uso:
  python scripts/commitment_status.py <logfile> <dir> [<dir> ...]
"""
import sys
from datetime import date, datetime
from pathlib import Path


def parse_log_line(line):
    """Parsea una linea de datos del log. Mismo criterio que
    adherence.parse_log_line y validate_evidence.parse_log_line: una linea de
    datos empieza con el anio ISO (digito '2'); todo lo demas (titulo
    markdown, prosa, la linea que documenta el formato, lineas vacias) se
    descarta devolviendo None. Devuelve un dict campo->valor, o None.

    Reglas de parseo (reproducen las de adherence.py / validate_evidence.py
    para no reintroducir un bug ya cerrado):

    1. `notes=` es TERMINAL. El campo `notes` es texto libre por diseno y va
       ultimo en el formato documentado; una nota puede contener `|` y `key=`.
       El split por `|` no protege ese contenido, asi que al encontrar
       `notes=` se reconstruye la nota juntando ese parte y todos los
       siguientes con `|`, y se deja de procesar mas campos. Antes, una nota
       inocente con un `|` (ej. `notes="... | skill=otro"`) inyectaba un
       `skill=` falso y una sesion de otra habilidad se contaba como evidencia
       de la que no era.

    2. Clave repetida: gana la PRIMERA ocurrencia (determinista). Este script
       reporta hechos, no interpreta ni es un gate, asi que aplica una regla
       fija y predecible (coherente con adherence.py) en vez de fallar ante un
       log ambiguo.
    """
    line = line.strip()
    if not line or not line.startswith("2"):  # las lineas de datos empiezan con el anio ISO
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


def parse_frontmatter(path):
    """Parser frontmatter YAML minimo, mismo approach que
    validate_evidence.parse_frontmatter y validate_contracts.parse_frontmatter:
    solo nivel 1 (escalares y listas simples entre corchetes). No es un parser
    YAML completo a proposito; alcanza para leer id, type, status, skill,
    baseline_date y checkpoint_date, que son los unicos campos que este script
    necesita. Descarta un BOM inicial (utf-8-sig) para no clasificar un nodo
    real como no-nodo. Devuelve (data, None) o (None, err). Se duplica en vez
    de importar para no acoplar este script a archivos que se editan en
    paralelo.
    """
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        return None, "sin frontmatter"
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, "frontmatter mal cerrado"
    raw = parts[1]
    data = {}
    for line in raw.strip().splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        if line.startswith(("  ", "\t")):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [v.strip().strip('"').strip("'") for v in inner.split(",") if v.strip()]
        else:
            data[key] = value.strip('"').strip("'")
    return data, None


def _parse_iso_date(value):
    """Parsea una fecha ISO (YYYY-MM-DD). Devuelve un date o None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _is_open_tracking(contract):
    """True si el contrato es un seguimiento abierto (sin fecha limite).

    FEAT-SIN-FECHA-LIMITE: `checkpoint_date: null` (literal YAML `null`, que el
    parser minimal deja como la cadena "null"/"None") significa seguimiento
    abierto. Es un acto deliberado, distinto de omitir el campo (que
    validate_contracts.py ya rechaza): declarar "sin fecha" no es olvidarse.
    Apunta a la PROPIEDAD (no hay fecha tope) y no a la forma: un `null`
    explicito no es una fecha invalida que no se pudo parsear, es la decision
    de no tener plazo. Un valor ausente o None NO cuenta como abierto: sigue
    siendo el caso "no se puede medir la ventana" de siempre.
    """
    cp = contract.get("checkpoint_date")
    if cp is None:
        return False
    return str(cp).strip().strip('"').strip("'") in ("null", "None")


def collect_active_contracts(roots):
    """Recorre los directorios y devuelve (active, omitted_count, skipped_dirs).

    `active` es la lista de frontmatters de nodos `type: skill_contract` con
    `status: active`, ordenada por id. `omitted_count` cuenta los
    skill_contract que NO estan en active (draft, checkpoint_done, discontinued
    o cualquier otro status): se omiten y se informa, nada de omision
    silenciosa. Otros tipos de nodo simplemente no son contratos y se ignoran
    (no se cuentan como omitidos). Saltea README* y todo lo bajo templates/,
    igual que validate_contracts.py.
    """
    active = []
    omitted = 0
    skipped_dirs = []
    for root in roots:
        if not root.exists():
            skipped_dirs.append(root)
            continue
        for path in sorted(root.rglob("*.md")):
            if path.name.startswith("README") or "templates" in path.parts:
                continue
            data, _err = parse_frontmatter(path)
            if not data:
                continue
            if data.get("type") != "skill_contract":
                continue
            if data.get("status") == "active":
                active.append(data)
            else:
                omitted += 1
    active.sort(key=lambda d: str(d.get("id", "")))
    return active, omitted, skipped_dirs


def collect_evidence(logfile):
    """Devuelve la lista de (skill, fecha) de cada linea de datos del log con
    skill y timestamp parseables. La fecha es la componente de dia del
    timestamp (naive). Lineas sin skill o con timestamp invalido se descartan:
    este script no valida la forma del log (eso es validate_evidence.py),
    solo cuenta lo que puede contar de forma determinista.
    """
    evidence = []
    for line in logfile.read_text(encoding="utf-8").splitlines():
        fields = parse_log_line(line)
        if fields is None:
            continue
        skill = fields.get("skill")
        if not skill:
            continue
        try:
            ts = datetime.fromisoformat(fields["timestamp"])
        except (KeyError, ValueError):
            continue
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        evidence.append((skill, ts.date()))
    return evidence


def report_contract(contract, evidence, today, warnings):
    """Imprime el bloque de reporte de un contrato activo y acumula avisos.

    Devuelve True si pudo medir la ventana, False si la salteo por no poder
    parsear baseline/checkpoint (ya emitio un aviso en ese caso).

    FEAT-SIN-FECHA-LIMITE: un seguimiento abierto (checkpoint_date: null) usa
    un formato distinto y la palabra "seguimiento" en vez de "compromiso": no
    hay ventana ni "restantes", y reportar restantes: None/-1 seria basura. Los
    compromisos con fecha conservan EXACTAMENTE el formato historico (hay tests
    congelados encima). El aviso de "checkpoint ya paso" nunca aplica a un
    abierto (no puede dispararse: no hay fecha que pase); el de "sin evidencia
    desde el baseline" si aplica igual.
    """
    cid = contract.get("id", "?")
    skill = contract.get("skill", "?")
    baseline = _parse_iso_date(contract.get("baseline_date"))
    open_tracking = _is_open_tracking(contract)
    checkpoint = None if open_tracking else _parse_iso_date(contract.get("checkpoint_date"))

    # Encabezado: los abiertos se leen distinto de los compromisos con ventana.
    if open_tracking:
        print(f"seguimiento '{cid}' (skill: {skill}) -- sin fecha limite")
    else:
        print(f"compromiso '{cid}' (skill: {skill})")

    if baseline is None:
        # baseline_date es obligatorio y es el punto desde el que se cuenta
        # todo; sin el no hay nada que medir. La forma del contrato es perimetro
        # de validate_contracts.py; aca solo senalamos y salteamos el bloque.
        if open_tracking:
            print("  no se puede medir: baseline_date faltante o invalida")
            warnings.append(
                f"seguimiento '{cid}': no se puede medir "
                f"(baseline_date faltante o invalida)"
            )
        else:
            print("  no se puede medir la ventana: baseline_date o checkpoint_date "
                  "faltante o invalida")
            warnings.append(
                f"compromiso '{cid}': no se puede medir la ventana "
                f"(baseline_date o checkpoint_date faltante o invalida)"
            )
        return False

    # Evidencia desde el baseline: lineas del log cuyo skill coincide con el
    # del contrato Y cuyo timestamp (fecha) >= baseline_date. Regla simple y
    # determinista; no se inventa otra. Sirve igual para un seguimiento
    # abierto: sigue siendo informacion util saber si practico desde el inicio.
    sessions = [d for s, d in evidence if s == skill and d >= baseline]

    if open_tracking:
        # Seguimiento abierto: no hay ventana ni "restantes". Solo cuanto
        # paso desde el baseline y la evidencia acumulada.
        elapsed = (today - baseline).days
        print(f"  desde: {baseline.isoformat()} ({elapsed} dias)")
        print(f"  evidencia desde el baseline: {len(sessions)} sesion(es)")
        if sessions:
            last = max(sessions)
            days_since = (today - last).days
            print(f"  ultima sesion: {last.isoformat()} (hace {days_since} dias)")
        else:
            print("  ultima sesion: ninguna desde el baseline")
        # El aviso de "checkpoint ya paso" no aplica aca por diseño: no hay
        # fecha tope que pueda pasar. El de "sin evidencia" si aplica igual.
        if not sessions:
            warnings.append(
                f"seguimiento '{cid}': sin evidencia desde el baseline "
                f"({baseline.isoformat()})"
            )
        return True

    # --- Compromiso con ventana (checkpoint real): formato historico, sin cambios ---
    if checkpoint is None:
        # checkpoint presente pero no parseable (no es null): no se puede medir
        # la ventana. No es gate; se senala y se saltea.
        print("  no se puede medir la ventana: baseline_date o checkpoint_date "
              "faltante o invalida")
        warnings.append(
            f"compromiso '{cid}': no se puede medir la ventana "
            f"(baseline_date o checkpoint_date faltante o invalida)"
        )
        return False

    total = (checkpoint - baseline).days
    elapsed = (today - baseline).days
    remaining = (checkpoint - today).days
    print(f"  ventana: {baseline.isoformat()} -> {checkpoint.isoformat()} "
          f"({total} dias)")
    print(f"  transcurridos: {elapsed} dias | restantes: {remaining} dias")

    print(f"  evidencia desde baseline: {len(sessions)} sesion(es)")
    if sessions:
        last = max(sessions)
        days_since = (today - last).days
        print(f"  ultima sesion: {last.isoformat()} (hace {days_since} dias)")
    else:
        print("  ultima sesion: ninguna desde el baseline")

    # Avisos (no cambian el exit code).
    if today > checkpoint:
        warnings.append(
            f"compromiso '{cid}': el checkpoint_date ({checkpoint.isoformat()}) "
            f"ya paso y el contrato sigue en active (la ventana se cerro sin "
            f"registrar el checkpoint)"
        )
    if not sessions:
        warnings.append(
            f"compromiso '{cid}': sin evidencia desde el baseline "
            f"({baseline.isoformat()})"
        )
    return True


def main(argv):
    if len(argv) < 3:
        print("uso: commitment_status.py <logfile> <dir> [<dir> ...]")
        return 1

    logfile = Path(argv[1])
    if not logfile.exists():
        print(f"no existe {logfile}")
        return 1

    roots = [Path(p) for p in argv[2:]]
    for root in roots:
        if not root.exists():
            print(f"no existe {root}")
            return 1

    active, omitted, skipped_dirs = collect_active_contracts(roots)
    # skipped_dirs no deberia ocurrir (ya validamos existencia arriba), pero por
    # robustez frente a races lo senalamos en vez de callarlo.
    for s in skipped_dirs:
        print(f"AVISO: {s} no existe, se omite")

    # FEAT-SIN-FECHA-LIMITE: distinguir compromisos con ventana de seguimientos
    # abiertos, para que no se confundan al contarlos. Son cosas distintas y
    # conviene que se lean distinto.
    open_count = sum(1 for c in active if _is_open_tracking(c))
    windowed_count = len(active) - open_count

    evidence = collect_evidence(logfile)
    today = date.today()
    warnings = []

    if not active:
        print("no hay compromisos activos")
    else:
        for contract in active:
            report_contract(contract, evidence, today, warnings)
            print()  # linea en blanco entre bloques, estilo validate_evidence

    if warnings:
        print(f"AVISOS: {len(warnings)}\n")
        for w in warnings:
            print(f"  - {w}")

    # Linea de resumen. Si no hay seguimientos abiertos, el mensaje es
    # EXACTAMENTE el historico (tests y verificaciones del PM dependen de esa
    # cadena literal). Solo cuando hay abiertos se distinguen ambos tipos.
    if open_count == 0:
        if omitted:
            if omitted == 1:
                suffix = "(1 contrato no-active omitido)"
            else:
                suffix = f"({omitted} contratos no-active omitidos)"
            print(f"OK: {len(active)} compromiso(s) activo(s) reportado(s) {suffix}")
        else:
            print(f"OK: {len(active)} compromiso(s) activo(s) reportado(s)")
    else:
        wtxt = ("1 compromiso con ventana" if windowed_count == 1
                else f"{windowed_count} compromisos con ventana")
        otxt = ("1 seguimiento abierto" if open_count == 1
                else f"{open_count} seguimientos abiertos")
        if omitted:
            if omitted == 1:
                suffix = "(1 contrato no-active omitido)"
            else:
                suffix = f"({omitted} contratos no-active omitidos)"
            print(f"OK: {wtxt} y {otxt} reportado(s) {suffix}")
        else:
            print(f"OK: {wtxt} y {otxt} reportado(s)")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))