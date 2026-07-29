#!/usr/bin/env python3
"""
Validador de integridad referencial del plano de evidencia (logs/) contra los
otros dos planos (knowledge/ y contracts/).

Valida QUE la evidencia APUNTE a nodos reales: cada linea de datos del log
referencia ids via skill=, subskill= y session=, y este script comprueba que
esos ids existan y sean del TIPO de nodo correcto (skill_index / subskill /
session_contract). Un typo que antes producía una racha computada sobre un
fantasma (ver AUDIT-G, H4) ahora es un error con numero de linea.

Ademas emite un AVISO (no error) de coherencia de ciclo de vida (H7): si una
linea referencia una session_contract que a su vez referencia un skill_contract
que sigue en status: draft, hay evidencia registrada contra un compromiso que
nunca se activo. Es aviso y no error a proposito: puede ser legitimo registrar
una sesion de practica antes de activar formalmente el compromiso; el sistema
lo senala, no lo prohibe.

QUE NO VALIDA (limites declarados, como en validate_contracts.py y adherence.py):
  - NO valida si lo registrado realmente ocurrio. El log es append-only y texto
    libre; este script lee ids, no verifica la verdad de la evidencia.
  - NO promueve nada de evidencia hacia conocimiento. docs/REFERENCIA.md (seccion
    de los tres planos) es tajante: ningun dato fluye de evidencia a conocimiento de
    forma automatica; eso requiere decision humana. Este script no toca
    knowledge/ ni contracts/, solo los lee para construir el conjunto de ids
    conocidos.
  - NO valida la forma de los nodos de knowledge/contracts (campos requeridos,
    lenguaje vago, ids duplicados, etc.): eso es trabajo de validate_contracts.py.
  - NO valida que el criterio de un session_contract coincida con su
    skill_contract padre (H2): tambien es validate_contracts.py.
  - NO exige que una linea tenga los tres campos: valida los que estan; un
    campo ausente no es error.

stdlib solamente, sin red, sin dependencias externas. Exit 0 = sin errores
(puede haber avisos); exit 1 = hay errores.

Uso:
  python scripts/validate_evidence.py <logfile> <dir> [<dir> ...]
"""
import sys
from pathlib import Path


def parse_log_line(line):
    """Parsea una linea de datos del log. Mismo criterio que adherence.parse_log_line:
    una linea de datos empieza con el anio ISO (digito '2'); todo lo demas
    (titulo markdown, prosa, la linea que documenta el formato, lineas vacias)
    se descarta devolviendo None. Devuelve (fields, duplicates): fields es un
    dict campo->valor (o None si la linea no es de datos) y duplicates es la
    lista de claves que aparecen repetidas en la linea (vacia si no hay).

    Se duplica conscientemente el criterio de adherence.py en vez de importarlo:
    adherence.py es de otro perimetro y este script no debe acoplarse a el.

    Reglas de parseo (corrigen CONFIRM-N bugs 3 y 4):

    1. `notes=` es TERMINAL. El campo `notes` es texto libre por diseño y va
       ultimo en el formato documentado; una nota puede contener `|` y `key=`.
       El split por `|` no protege ese contenido, asi que al encontrar
       `notes=` se reconstruye la nota juntando ese parte y todos los
       siguientes con `|`, y se deja de procesar mas campos. Antes, una nota
       con `|` inyectaba campos falsos (ej. `notes="... | skill=<skill>"`
       pisaba el `skill=` real) -> refs invalidas pasaban en silencio.

    2. Clave repetida = AMBIGUA. No se puede saber cual quiso decir la persona,
       asi que este script la rechaza explicitamente (main() emite el error);
       aca solo se detecta y se acumula en `duplicates`. Se conserva la primera
       ocurrencia en `fields` (no se valida: la linea entera se rechaza como
       ambigua en main()). Esto cierra el bypass `skill=fantasma | skill=valido`
       que descartaba la ref invalida en silencio.
    """
    line = line.strip()
    if not line or not line.startswith("2"):
        return None, []
    fields = {}
    duplicates = []
    parts = [p.strip() for p in line.split("|")]
    fields["timestamp"] = parts[0].strip()
    for i, part in enumerate(parts[1:], start=1):
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        # notes= es TERMINAL: todo lo que sigue (pipes incluidos) es texto libre
        # de la nota. Reconstruimos la nota juntando este parte y los restantes.
        if k == "notes":
            remainder = v
            if i + 1 < len(parts):
                remainder = "|".join([remainder] + parts[i + 1:])
            fields["notes"] = remainder.strip().strip('"')
            break
        if k in fields:
            if k not in duplicates:
                duplicates.append(k)
        else:
            fields[k] = v.strip().strip('"')
    return fields, duplicates


def parse_frontmatter(path):
    """Parser frontmatter YAML minimo, mismo approach que validate_contracts.parse_frontmatter:
    solo nivel 1 (escalares y listas simples entre corchetes). No es un parser
    YAML completo a proposito; alcanza para leer id, type, status y skill_contract,
    que son los unicos campos que este script necesita. Devuelve (data, None) o
    (None, err). Se duplica en vez de importar validate_contracts para no
    acoplar este script a un archivo que se edita en paralelo.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None, f"{path}: falta frontmatter YAML (no empieza con ---)"
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


def collect_nodes(roots):
    """Recorre los directorios y devuelve un dict id -> data (frontmatter).
    Saltea README* y todo lo bajo templates/, igual que validate_contracts.py.
    Ante id duplicado se queda con la primera ocurrencia (los duplicados los
    reporta validate_contracts.py, no es perimetro de este script). Directorios
    inexistentes se omiten con aviso, no son error.
    """
    nodes = {}
    skipped = []
    for root in roots:
        if not root.exists():
            skipped.append(root)
            continue
        for path in sorted(root.rglob("*.md")):
            if path.name.startswith("README") or "templates" in path.parts:
                continue
            data, _err = parse_frontmatter(path)
            if not data:
                continue
            nid = data.get("id")
            if nid and nid not in nodes:
                nodes[nid] = data
    return nodes, skipped


def validate_line(lineno, fields, nodes, errors, warnings):
    """Valida una linea de datos ya parseada. Modifica errors y warnings in place."""
    # skill -> debe ser id de un nodo type: skill_index
    v = fields.get("skill")
    if v:
        node = nodes.get(v)
        if node is None:
            errors.append(
                f"linea {lineno}: skill '{v}' no existe como id de un nodo type: skill_index"
            )
        elif node.get("type") != "skill_index":
            errors.append(
                f"linea {lineno}: skill '{v}' existe pero es de type "
                f"'{node.get('type')}' (no skill_index)"
            )

    # subskill -> debe ser id de un nodo type: subskill
    v = fields.get("subskill")
    if v:
        node = nodes.get(v)
        if node is None:
            errors.append(
                f"linea {lineno}: subskill '{v}' no existe como id de un nodo type: subskill"
            )
        elif node.get("type") != "subskill":
            errors.append(
                f"linea {lineno}: subskill '{v}' existe pero es de type "
                f"'{node.get('type')}' (no subskill)"
            )

    # session -> debe ser id de un nodo type: session_contract
    v = fields.get("session")
    if v:
        node = nodes.get(v)
        if node is None:
            errors.append(
                f"linea {lineno}: session '{v}' no existe como id de un nodo "
                f"type: session_contract"
            )
        elif node.get("type") != "session_contract":
            errors.append(
                f"linea {lineno}: session '{v}' existe pero es de type "
                f"'{node.get('type')}' (no session_contract)"
            )
        else:
            # H7: coherencia de ciclo de vida. La session referencia un
            # skill_contract; si ese contrato sigue en draft, hay evidencia
            # registrada contra un compromiso que nunca se activo. AVISO, no
            # error: puede ser legitimo practicar antes de activar formalmente.
            contract_ref = node.get("skill_contract")
            if contract_ref and contract_ref not in ("null", None):
                contract = nodes.get(contract_ref)
                if (
                    contract is not None
                    and contract.get("type") == "skill_contract"
                    and contract.get("status") == "draft"
                ):
                    warnings.append(
                        f"linea {lineno}: evidencia contra contrato "
                        f"'{contract_ref}' que sigue en draft (session '{v}')"
                    )


def main(argv):
    if len(argv) < 3:
        print("uso: validate_evidence.py <logfile> <dir> [<dir> ...]")
        return 1

    logfile = Path(argv[1])
    if not logfile.exists():
        print(f"no existe {logfile}")
        return 1

    roots = [Path(p) for p in argv[2:]]
    nodes, skipped = collect_nodes(roots)
    for s in skipped:
        print(f"AVISO: {s} no existe, se omite")

    errors = []
    warnings = []
    count = 0
    for lineno, line in enumerate(logfile.read_text(encoding="utf-8").splitlines(), start=1):
        fields, duplicates = parse_log_line(line)
        if fields is None:
            continue
        count += 1
        if duplicates:
            # Clave repetida -> la linea es ambigua (no se sabe cual quiso
            # decir la persona). Se rechaza explicitamente con numero de
            # linea y clave repetida, y NO se validan las refs de esa linea:
            # el parseo es no confiable. Cierra el bypass de claves
            # duplicadas (y el de `notes` que inyecta un `key=`).
            for k in duplicates:
                errors.append(
                    f"linea {lineno}: clave repetida '{k}' (linea ambigua)"
                )
            continue
        validate_line(lineno, fields, nodes, errors, warnings)

    if errors:
        print(f"ERRORES: {len(errors)}\n")
        for e in errors:
            print(f"  - {e}")

    if warnings:
        print(f"AVISOS: {len(warnings)}\n")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        return 1

    print(f"OK: {count} linea(s) de evidencia validadas")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))