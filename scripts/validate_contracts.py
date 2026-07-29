#!/usr/bin/env python3
"""
Validador deterministico de FORMA para knowledge/ y contracts/.

Importante: esto NO valida si una subhabilidad fue realmente lograda. Eso es imposible de
determinar de forma mecanica en la mayoria de los casos (ver docs/REFERENCIA.md, seccion verification_type).
Lo unico que este script puede verificar sin interpretacion humana es que la ESPECIFICACION este
bien formada: campos requeridos presentes, tipos permitidos, referencias validas, y que un
criterio no use lenguaje vago cuando declara instrumented o proxy.

Sin dependencias externas (stdlib solamente), sin red, sin LLM. Exit code 0 = todo OK, 1 = hay
errores.
"""
import sys
import re
from datetime import date, datetime
from pathlib import Path

VAGUE_WORDS = [
    "comodo", "cómodo", "bien", "mejor", "suficientemente", "razonablemente",
    "un poco", "mas o menos", "más o menos", "adecuado", "aceptable",
]

# Match por limite de palabra (\b) para evitar falsos positivos por substring: sin esto,
# "bien" matchearia dentro de "también", "mejor" dentro de "mejorar", "adecuado" dentro de
# "inadecuado", "un poco" dentro de "algun poco", etc.
_VAGUE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in VAGUE_WORDS) + r")\b",
    re.IGNORECASE,
)

VALID_VERIFICATION_TYPES = {"instrumented", "proxy", "human_rubric"}
VALID_DOMAIN_TYPES = {"ai_mediated", "physical", "cognitive_abstract"}
VALID_SUBSKILL_STATUS = {"draft", "practicing", "verified", "needs_review"}
VALID_SESSION_STATUS = {"draft", "attempted", "verified"}
# FEAT-DISCONTINUED: nuevo estado TERMINAL. Significa que el compromiso o
# seguimiento se cerro SIN haber llegado al checkpoint. No es "abandoned": este
# sistema no juzga que elegis aprender ni que elegis dejar, y "abandonado"
# arrastra una connotacion de fracaso que el proyecto no quiere emitir. Es un
# hecho, no un reproche. Como checkpoint_done, es terminal: lo que sigue no se
# mide contra el criterio congelado porque la persona decidio cerrarlo.
VALID_SKILL_CONTRACT_STATUS = {"draft", "active", "checkpoint_done", "discontinued"}

# BUG 2 (H1): cota superior a review_after_days. Mas de un anio equivale a "nunca"
# en un sistema de aprendizaje personal y contradice que la verificacion caduque: un
# verified con review_after_days=999999 vence en el ano 4761, el nodo immortal que H1
# venia a eliminar, con el papeleo en regla. El fix anterior valido la FORMA del campo
# ("entero positivo") en vez de la PROPIEDAD que debia garantizar ("caduca de verdad").
# 365 dias = un anio completo; lo que esta fuera de eso no es "caduca despues de un
# tiempo", es "no caduca".
MAX_REVIEW_AFTER_DAYS = 365

# Marcador del error "no empieza con ---" que devuelve parse_frontmatter. main() lo usa
# para distinguir un archivo que NO es un nodo (sin frontmatter -> se omite, H6) de un
# nodo roto (frontmatter mal cerrado -> sigue siendo error). Distincion clave: omitir lo
# segundo seria enmascarar corrupcion real.
NO_FRONTMATTER_MARKER = "falta frontmatter YAML (no empieza con ---)"

REQUIRED_FIELDS = {
    "subskill": ["id", "type", "skill", "domain_type", "verification_type", "status"],
    "mental_model": ["id", "type", "scope"],
    "failure_mode": ["id", "type", "scope"],
    "tool": ["id", "type", "enables_verification"],
    "skill_contract": ["id", "type", "skill", "goal", "domain_type", "verification_type",
                        "criterio", "instrument_frozen", "baseline_date", "checkpoint_date",
                        "status"],
    "session_contract": ["id", "type", "skill", "subskill", "status", "criterio"],
    "skill_index": ["id", "type", "domain_type"],
}


def _has_displaced_frontmatter_marker(text):
    """True si el primer delimitador de frontmatter `---` del texto esta precedido
    UNICAMENTE por lineas en blanco o espacios en blanco. Ese es el caso estrecho
    que este chequeo debe capturar: frontmatter desplazado hacia abajo por blanks
    iniciales -> nodo MAL FORMADO -> error explicito (no omision silenciosa).

    El chequeo anterior (BUG 1b de H6, refinado aca) miraba CUALQUIER linea `---`
    en el archivo. Pero `---` significa dos cosas distintas en un .md: el
    delimitador estructural de frontmatter (obligatoriamente en la primera linea)
    y una LINEA HORIZONTAL de markdown (presentacional, en cualquier parte). En
    prosa, un `---` es casi siempre lo segundo. Tratar toda aparicion como lo
    primero producia falsos errores en archivos que no pretenden tener frontmatter.

    Regla afinada: si hay CONTENIDO REAL antes del primer `---`, ese `---` es una
    linea horizontal y el archivo NO es un nodo -> se omite (lo cuenta main()).
    Solo si todo lo que precede al primer `---` es blank/espacios es frontmatter
    desplazado -> error. Apunta a la PROPIEDAD (frontmatter mal arrancado), no a
    la FORMA (aparece un `---` en algun lado)."""
    for line in text.splitlines():
        if line.rstrip() == "---":
            # llegamos a un `---` con solo blanks antes: frontmatter desplazado.
            return True
        if line.strip() != "":
            # hay contenido real antes de cualquier `---`: es linea horizontal,
            # no delimitador. El archivo no es un nodo.
            return False
    # no hay `---` en ninguna linea: no-nodo clasico.
    return False


def parse_frontmatter(path):
    # BUG 1 (H6): utf-8-sig descarta un BOM inicial (﻿) si esta presente. Un .md
    # con BOM + frontmatter ES un nodo; sin esto, startswith("---") da False por el
    # BOM, el nodo se clasificaba "sin frontmatter" y se OMITIA en silencio,
    # enmascarando corrupcion real (justo lo que H6 garantiza no hacer). El BOM es un
    # artefacto de encoding que agregan varios editores, no contenido.
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        # BUG 1b (H6): distinguir "no es un nodo" de "nodo mal formado". La spec YAML
        # exige `---` en la primera linea. Si el archivo NO empieza con `---` pero
        # contiene una linea delimitadora `---` mas abajo, el frontmatter no arranca
        # en la primera posicion: es un nodo MAL FORMADO -> error explicito, no
        # omision silenciosa. Solo si no hay `---` en ninguna linea es un no-nodo y
        # se omite. Regla general: no-nodo -> se omite; nodo roto -> error. Nunca
        # omision silenciosa de algo que parece un nodo.
        if _has_displaced_frontmatter_marker(text):
            return None, (
                f"{path}: frontmatter no empieza en la primera linea "
                f"(el delimitador `---` esta desplazado por lineas en blanco "
                f"iniciales)"
            )
        return None, f"{path}: {NO_FRONTMATTER_MARKER}"
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, f"{path}: frontmatter YAML mal cerrado"
    raw = parts[1]
    data = {}
    for line in raw.strip().splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        # solo parsea nivel 1 (listas simples entre corchetes o escalares); suficiente para
        # los templates de este scaffold, no es un parser YAML completo a proposito.
        if line.startswith(("  ", "\t")):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        # Comentario inline estilo YAML: recortar ANTES de strip de comillas y
        # ANTES de parsear listas (ver _strip_inline_comment). El strip previo
        # normaliza para que "abre el valor" (i==0) cubra `key:   # nota`; el
        # strip posterior limpia los espacios que quedaron entre el valor y
        # el `#` recortado (`draft   # nota` -> `draft   ` -> `draft`).
        value = _strip_inline_comment(value.strip()).strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [v.strip().strip('"').strip("'") for v in inner.split(",") if v.strip()]
        else:
            data[key] = value.strip('"').strip("'")
    return data, None


def _strip_inline_comment(value):
    """Recorta un comentario inline estilo YAML del valor de un campo.

    Un `#` inicia comentario SOLO si esta precedido por espacio en blanco o
    abre el valor (es el primer caracter, tras el strip). Dentro de comillas
    (simple o doble) el `#` es literal y se conserva. Esto es lo que falta en
    parse_frontmatter: antes de este fix, `domain_type: physical   # nota`
    se parseaba como `physical   # nota` y reventaba las plantillas de
    templates/, que usan justamente esa sintaxis para explicar cada campo.

    ORDER QUE IMPORTA: este recorte va ANTES de quitar comillas y ANTES de
    parsear listas (lo llama parse_frontmatter justo ahi). Si se hiciera al
    final, `"algo # nota"` se rompe (el # dentro de comillas es literal) y el
    `#` de `depends_on: [a, b]   # ids` no se limpia antes de parsear los
    corchetes.

    Apunta a la PROPIEDAD (el valor que el campo queria declarar), no a la
    FORMA: un split('#') ingenuo recortaria `criterio: "a #1"` a `a ` y
    `id: abc#def` a `abc`, perdiendo datos legitimos. Por eso se escanea con
    estado de comillas, no con regex/split.

    Tabla de casos (ver tests/test_validate_contracts.py):
      `draft   # nota`            -> `draft`
      `abc#def`                   -> `abc#def` (sin espacio antes: no es comentario)
      `"20 rodajas, #1 y #2"`     -> `"20 rodajas, #1 y #2"` (# literal dentro de comillas)
      `"algo"   # nota`           -> `"algo"` (comentario recortado tras cerrar comillas)
      `[a, b]   # ids`            -> `[a, b]` (recortado antes de parsear corchetes)
      `# solo comentario`         -> `` (abre el valor -> comentario -> vacio)
    """
    out = []
    quote = None  # None = fuera de comillas; '"' o "'" = dentro de ese tipo
    for i, ch in enumerate(value):
        if quote is not None:
            # dentro de comillas: todo literal hasta la comilla que abrio
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            continue
        if ch == "#":
            # `#` inicia comentario si abre el valor (i == 0) o si lo precede
            # un espacio en blanco. Sin esto, `abc#def` y `draft# x` se
            # recortarian a `abc`/`draft` perdiendo datos.
            prev = value[i - 1] if i > 0 else ""
            if i == 0 or prev in (" ", "\t"):
                break  # inicia comentario: cortar aca
            out.append(ch)
            continue
        out.append(ch)
    return "".join(out)


def has_number_or_threshold(text):
    return bool(re.search(r"\d", text or ""))


def contains_vague_word(text):
    m = _VAGUE_RE.search(text or "")
    return m.group(0) if m else None


def _parse_date_flexible(value):
    """Acepta tanto 'YYYY-MM-DD' como un ISO con hora
    ('YYYY-MM-DDTHH:MM:SS'), normalizando a date para comparar.

    BUG 4 (H5): unifica el criterio de fecha entre last_verified (que usaba
    datetime.fromisoformat y aceptaba hora) y baseline_date/checkpoint_date (que
    usaban date.fromisoformat y la rechazaban). Mismo sistema, dos criterios era
    inconsistente; se unifica hacia lo PERMISIVO. No endurece last_verified: los
    nodos existentes que ya usan hora siguen pasando, y ahora baseline/checkpoint
    tambien la aceptan. Devuelve date o lanza ValueError/TypeError si no parsea."""
    return datetime.fromisoformat(str(value)).date()


def _validate_verified_subskill(path, data, errors):
    """Chequea los 3 requisitos de H1+H3 para subskill status=verified.

    last_verified: presente, no vacio/null/None, parseable como fecha ISO (mismo
    criterio que decay_check: datetime.fromisoformat(...).date()).
    review_after_days: presente, entero positivo (> 0) y <= MAX_REVIEW_AFTER_DAYS
    (mas de un anio equivale a "nunca caducar", BUG 2).
    ratified_by: 'human' siempre valido; 'instrument' solo si verification_type es
    'instrumented' (una verificacion objetiva se ratifica a si misma); cualquier
    otro valor (ai/llm/claude/proxy/...) es error: el sistema rechaza una promocion
    a verified hecha por una lectura de IA.
    """
    # last_verified
    last_verified = data.get("last_verified")
    if last_verified in (None, "", "null", "None"):
        errors.append(
            f"{path}: status verified requiere last_verified con fecha ISO valida "
            f"(no null/vacio)"
        )
    else:
        try:
            lv_date = _parse_date_flexible(last_verified)
        except (ValueError, TypeError):
            errors.append(
                f"{path}: last_verified no es fecha ISO valida '{last_verified}'"
            )
        else:
            # BUG 3 (H1): last_verified es "desde cuando" (pasado). Una fecha futura
            # pasa la validacion de forma y ademas nunca decae (decay_check obtiene
            # dias negativos). El fix anterior valido la FORMA ("fecha ISO") en vez
            # de la PROPIEDAD ("es pasada"). Solo aplica a last_verified:
            # checkpoint_date es legítimamente futura por diseño y baseline_date puede
            # ser hoy; a esos NO se les aplica esta regla.
            if lv_date > date.today():
                errors.append(
                    f"{path}: last_verified '{last_verified}' es futura; debe ser "
                    f"<= hoy (es 'desde cuando', una fecha pasada)"
                )

    # review_after_days
    review = data.get("review_after_days")
    if review in (None, "", "null", "None"):
        errors.append(f"{path}: status verified requiere review_after_days entero positivo")
    else:
        try:
            review_int = int(str(review))
        except (ValueError, TypeError):
            errors.append(f"{path}: review_after_days no es entero '{review}'")
        else:
            if review_int <= 0:
                errors.append(f"{path}: review_after_days debe ser positivo (> 0)")
            elif review_int > MAX_REVIEW_AFTER_DAYS:
                errors.append(
                    f"{path}: review_after_days={review_int} excede el maximo de "
                    f"{MAX_REVIEW_AFTER_DAYS} dias (mas de un anio equivale a "
                    f"'nunca' caducar)"
                )

    # ratified_by
    ratified = data.get("ratified_by")
    if ratified in (None, "", "null", "None"):
        errors.append(
            f"{path}: status verified requiere ratified_by (human, o instrument si "
            f"verification_type=instrumented)"
        )
    elif ratified == "human":
        pass  # valido para cualquier verification_type
    elif ratified == "instrument":
        if data.get("verification_type") != "instrumented":
            errors.append(
                f"{path}: ratified_by=instrument solo es valido con "
                f"verification_type=instrumented"
            )
    else:
        errors.append(
            f"{path}: ratified_by invalido '{ratified}' (una lectura de IA no ratifica "
            f"verified; usar human, o instrument si verification_type=instrumented)"
        )


def validate_node(path, data, errors):
    node_type = data.get("type")
    if node_type not in REQUIRED_FIELDS:
        errors.append(f"{path}: type '{node_type}' desconocido")
        return

    for field in REQUIRED_FIELDS[node_type]:
        if field not in data or data[field] in ("", None):
            errors.append(f"{path}: falta campo requerido '{field}'")

    if node_type == "subskill":
        if data.get("domain_type") not in VALID_DOMAIN_TYPES:
            errors.append(f"{path}: domain_type invalido '{data.get('domain_type')}'")
        if data.get("verification_type") not in VALID_VERIFICATION_TYPES:
            errors.append(f"{path}: verification_type invalido '{data.get('verification_type')}'")
        if data.get("status") not in VALID_SUBSKILL_STATUS:
            errors.append(f"{path}: status invalido '{data.get('status')}'")

        # H1+H3: un nodo que afirma estar verificado debe declarar desde cuando
        # (last_verified), por cuanto tiempo (review_after_days) y quien lo ratifico
        # (ratified_by). Sin esto un verified sin campos de caducidad es immortal
        # (decay_check lo saltea en silencio) y una lectura de IA puede autoproclamarlo
        # verified sin respaldo. Es requisito CONDICIONAL al status: un draft/practicing
        # no lo necesita. Coherente con decay_check --apply, que reescribe verified ->
        # needs_review dejando estos campos intactos: el nodo resultante sigue validando.
        if data.get("status") == "verified":
            _validate_verified_subskill(path, data, errors)

    if node_type in ("skill_contract", "session_contract"):
        criterio = data.get("criterio", "")
        vt = data.get("verification_type")
        if node_type == "skill_contract" and vt not in VALID_VERIFICATION_TYPES:
            errors.append(f"{path}: verification_type invalido '{vt}'")

        vague = contains_vague_word(criterio)
        if vague:
            errors.append(
                f"{path}: criterio usa lenguaje vago ('{vague}'); "
                f"reemplazar por algo observable y, si aplica, con umbral numerico"
            )
        # si el nodo es instrumented o proxy (via skill_contract) exigimos umbral numerico
        if node_type == "skill_contract" and vt in ("instrumented", "proxy"):
            if not has_number_or_threshold(criterio):
                errors.append(
                    f"{path}: verification_type={vt} pero el criterio no tiene umbral numerico"
                )

    if node_type == "skill_contract":
        if data.get("status") not in VALID_SKILL_CONTRACT_STATUS:
            errors.append(f"{path}: status invalido '{data.get('status')}'")
        if data.get("instrument_frozen") not in ("true", "True"):
            errors.append(f"{path}: instrument_frozen debe ser true (el instrumento no se elige a posteriori)")
        # H5: baseline_date y checkpoint_date deben ser fechas ISO validas y checkpoint debe
        # ser ESTRICTAMENTE posterior a baseline (una ventana de cero dias no permite medir
        # un delta). Ambos campos ya son requeridos mas arriba; si estan ausentes el chequeo
        # de formato no aplica para no duplicar ese error.
        #
        # FEAT-SIN-FECHA-LIMITE: checkpoint_date: null significa seguimiento abierto, sin
        # fecha limite. El campo SIGUE siendo requerido (chequeo de arriba): escribir
        # `null` a proposito es un acto deliberado, distinto de omitir el campo, y este
        # proyecto trata los actos deliberados como deliberados. Apunta a la PROPIEDAD,
        # no a la FORMA: con null no hay nada que ordenar contra el baseline, asi que el
        # chequeo de "checkpoint posterior al baseline" no aplica. Todo lo demas del
        # contrato se valida igual. baseline_date sigue siendo obligatorio y una fecha
        # real: es el punto desde el cual se cuenta el tiempo y la evidencia.
        baseline = data.get("baseline_date")
        checkpoint = data.get("checkpoint_date")
        baseline_d = None
        if baseline not in (None, ""):
            try:
                # BUG 4 (H5): parse permisivo (acepta YYYY-MM-DD y ISO con hora),
                # mismo criterio que last_verified.
                baseline_d = _parse_date_flexible(baseline)
            except (ValueError, TypeError):
                errors.append(f"{path}: baseline_date no es fecha ISO valida '{baseline}'")
        if checkpoint in (None, ""):
            # ausente -> el chequeo de campo requerido de arriba ya lo reporto; no se
            # duplica aca.
            pass
        elif checkpoint in ("null", "None"):
            # seguimiento abierto: sin fecha limite, nada que ordenar contra el baseline.
            pass
        else:
            try:
                checkpoint_d = _parse_date_flexible(checkpoint)
            except (ValueError, TypeError):
                errors.append(f"{path}: checkpoint_date no es fecha ISO valida '{checkpoint}'")
            else:
                if baseline_d is not None and checkpoint_d <= baseline_d:
                    errors.append(
                        f"{path}: checkpoint_date debe ser posterior a baseline_date "
                        f"(baseline={baseline}, checkpoint={checkpoint})"
                    )

    if node_type == "session_contract":
        if data.get("status") not in VALID_SESSION_STATUS:
            errors.append(f"{path}: status invalido '{data.get('status')}'")

    if node_type == "skill_index":
        # BUG 4 (FIX-CONFIRM-S): el id de un skill_index debe coincidir con el
        # nombre del directorio que contiene el archivo (convencion
        # <id>/index.md). Sin esto, una divergencia silenciosa como la de BUG 12
        # de init_skill (carpeta 'news' en disco con id 'news.' por un punto
        # final stripueado por el OS) pasa desapercibida para el validador, y lo
        # mismo un rename manual de carpeta que se olvido de actualizar el id.
        # Es la misma clase de fallo que esta auditoria caza: el fix anterior
        # valido la FORMA del campo (id presente) en vez de la PROPIEDAD que
        # debia garantizar (id == directorio). Solo se compara si id esta
        # presente; si falta, el chequeo de campo requerido de arriba ya lo
        # reporto.
        nid = data.get("id")
        if nid not in ("", None):
            parent_name = Path(path).parent.name
            if nid != parent_name:
                errors.append(
                    f"{path}: skill_index con id '{nid}' dentro del directorio "
                    f"'{parent_name}': el id debe coincidir con el nombre del "
                    f"directorio que contiene el archivo"
                )


def collect_known_ids(all_data):
    return {d.get("id") for d in all_data if d.get("id")}


def validate_references(path, data, known_ids, errors):
    for field in ("depends_on", "applies_mental_models", "applies_failure_modes",
                  "required_tools", "applies_to", "subskills", "tools_needed"):
        refs = data.get(field)
        if not refs:
            continue
        for ref in refs:
            if ref not in known_ids:
                errors.append(f"{path}: referencia '{ref}' en '{field}' no existe como id conocido")

    for field in ("subskill", "skill_contract"):
        ref = data.get(field)
        if ref and ref not in ("null", None) and ref not in known_ids:
            errors.append(f"{path}: referencia '{ref}' en '{field}' no existe como id conocido")


def validate_session_criterio_matches_skill_contract(parsed, errors):
    """H2: si un session_contract referencia por skill_contract: a un nodo conocido de
    type skill_contract, su criterio debe ser IDENTICO al del contrato padre. El criterio
    ES el instrumento; si diverge, el delta baseline->checkpoint no significa nada (ver
    docs/REFERENCIA.md, Compromiso baseline/checkpoint). Hasta hoy solo se validaba el cartel
    instrument_frozen: true; ahora se valida el instrumento mismo.

    Comparacion exacta de strings sobre el valor ya normalizado por parse_frontmatter
    (strip de comillas y espacios exteriores), SIN normalizacion adicional: dos criterios
    que difieren en algo tan sutil como el espaciado interno SON un cambio del instrumento
    y se reportan. Es deliberado que sea estricto.

    No aplica (no es error) cuando: el session_contract no tiene campo skill_contract o su
    valor es null; el id referenciado no existe como id conocido (validate_references ya lo
    reporta, no se duplica); o el id existe pero no es de type skill_contract (p.ej. apunta
    a una subskill por error: fuera de alcance de este chequeo)."""
    by_id = {}
    for _path, data in parsed:
        nid = data.get("id")
        if nid and nid not in by_id:
            by_id[nid] = data

    for path, data in parsed:
        if data.get("type") != "session_contract":
            continue
        ref = data.get("skill_contract")
        if not ref or ref in ("null", None):
            continue
        parent = by_id.get(ref)
        if parent is None:
            continue  # id desconocido: validate_references ya lo reporta
        if parent.get("type") != "skill_contract":
            continue  # apunta a un no-skill_contract: fuera de alcance
        parent_criterio = parent.get("criterio", "")
        # BUG 5 (H2): si el padre no tiene criterio declarado (campo requerido
        # ausente o vacio), NO emitir el error de divergencia. La causa raiz es el
        # skill_contract roto (validate_node ya lo reporta como "falta campo requerido
        # 'criterio'"); comparar contra el default "" y agregar un error de
        # divergencia encima es ruido: dos errores por una sola causa.
        if not parent_criterio:
            continue
        own_criterio = data.get("criterio", "")
        if own_criterio != parent_criterio:
            errors.append(
                f"{path}: criterio de sesion diverge del skill_contract '{ref}' "
                f"(padre='{parent_criterio}', sesion='{own_criterio}')"
            )


def main(argv):
    if len(argv) < 2:
        print("uso: validate_contracts.py <knowledge_dir> <contracts_dir> [...]")
        return 1

    roots = [Path(p) for p in argv[1:]]
    md_files = []
    for root in roots:
        if not root.exists():
            print(f"AVISO: {root} no existe, se omite")
            continue
        md_files.extend(sorted(root.rglob("*.md")))

    parsed = []
    errors = []
    omitted_non_nodes = 0
    for path in md_files:
        if path.name.startswith("README") or "templates" in path.parts:
            continue
        data, err = parse_frontmatter(path)
        if err:
            # H6: un .md que NO empieza con --- no es un nodo -> se omite y se cuenta (no es
            # error). Un .md que SI empieza con --- pero cierra mal el frontmatter SIGUE
            # siendo error: es un nodo roto, no un no-nodo; enmascararlo seria omision
            # silenciosa de corrupcion real.
            if NO_FRONTMATTER_MARKER in err:
                omitted_non_nodes += 1
                continue
            errors.append(err)
            continue
        if data:
            parsed.append((path, data))

    known_ids = collect_known_ids([d for _, d in parsed])

    # collect_known_ids colapsa ids duplicados en un set y los silencia; acá reportamos la
    # colision explicitamente porque dos nodos con el mismo id rompen el matching de referencias.
    seen_ids = {}
    for path, data in parsed:
        nid = data.get("id")
        if not nid:
            continue
        if nid in seen_ids:
            errors.append(f"{path}: id duplicado '{nid}' (ya definido en {seen_ids[nid]})")
        else:
            seen_ids[nid] = path

    for path, data in parsed:
        validate_node(path, data, errors)
        validate_references(path, data, known_ids, errors)

    # H2: chequeo cross-archivo (como el de ids duplicados): el criterio de un
    # session_contract que referencia un skill_contract conocido debe ser identico al del
    # padre. Necesita ver todos los nodos parseados a la vez.
    validate_session_criterio_matches_skill_contract(parsed, errors)

    if errors:
        print(f"FALLO: {len(errors)} error(es)\n")
        for e in errors:
            print(f"  - {e}")
        return 1

    # H6: el conteo de archivos omitidos por no ser nodos se reporta explicitamente. Un
    # conteo que no se reporta es una omision silenciosa. Si no se omitio ninguno, el
    # mensaje es EXACTAMENTE el historico (tests y verificaciones del PM dependen de esa
    # cadena literal).
    if omitted_non_nodes:
        if omitted_non_nodes == 1:
            suffix = "(1 archivo omitido por no tener frontmatter)"
        else:
            suffix = f"({omitted_non_nodes} archivos omitidos por no tener frontmatter)"
        print(f"OK: {len(parsed)} nodo(s)/contrato(s) validados sin errores de forma {suffix}")
    else:
        print(f"OK: {len(parsed)} nodo(s)/contrato(s) validados sin errores de forma")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
