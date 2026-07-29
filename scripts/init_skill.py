#!/usr/bin/env python3
"""Crea la carpeta knowledge/<skill>/ con index.md a partir del skill dado."""
import re
import sys
import argparse
from pathlib import Path

VALID_DOMAIN_TYPES = {"ai_mediated", "physical", "cognitive_abstract"}

# Caracteres no permitidos en un nombre de skill: separadores de path y los
# caracteres ilegales en nombres de archivo/directorio en Windows (< > : " / \
# \ | ? * y controles). Sin esto, un nombre como "../../evil" escapa del root y
# escribe index.md FUERA del directorio previsto (con exit 0, reportando exito),
# y un nombre vacio o "." escribe directamente dentro del root (contaminando el
# knowledge/ real cuando se usa el default --root knowledge). Ver reports/AUDIT-E-INIT-SKILL-REPORT.md.
_INVALID_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Nombres de dispositivo reservados de Windows. Un directorio llamado CON, PRN,
# AUX, NUL, COM1-9 o LPT1-9 (case-insensitive, con o sin extension: CON.txt es
# reservado igual) no se puede crear/abrir como directorio normal en Windows: el
# SO lo trata como el dispositivo. Se rechazan en TODA plataforma, no solo en
# Windows: el repo puede clonarse en Windows y una skill llamada CON creada en
# Linux volveria ese directorio inclonable alla. Ver reports/CONFIRM-O-REPORT.md, BUG 11.
_WIN_RESERVED_NAMES = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def validate_name(name):
    """Devuelve un mensaje de error si name no es un unico componente de path
    seguro, o None si es valido. No es un chequeo de seguridad (el script es
    un scaffold local de uso personal): es un chequeo de correctitud para que
    el scaffold no escriba silenciosamente fuera de <root>/<name>."""
    if not name or not name.strip():
        return "nombre vacio"
    if name in (".", ".."):
        return f"nombre invalido '{name}': no puede ser '.' ni '..'"
    if _INVALID_NAME_RE.search(name):
        return (f"nombre invalido '{name}': contiene separadores de path o "
                f"caracteres no permitidos en nombres de directorio")
    # <name> debe ser un unico componente (sin subdirectorios). ../ y a/b tienen
    # mas de un componente.
    if len(Path(name).parts) != 1:
        return (f"nombre invalido '{name}': debe ser un unico componente, "
                f"sin separadores de subdirectorio")
    # Nombres de dispositivo reservados de Windows. Se comparan por la base
    # (antes del primer punto) case-insensitive: 'CON', 'con', 'CON.txt' y
    # 'con.md' son todos reservados. Ver reports/CONFIRM-O-REPORT.md, BUG 11.
    base = name.split(".", 1)[0].upper()
    if base in _WIN_RESERVED_NAMES:
        return (f"nombre invalido '{name}': es un nombre de dispositivo "
                f"reservado de Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9); "
                f"se rechaza en toda plataforma porque el repo puede clonarse "
                f"en Windows y una skill con ese nombre volveria el directorio "
                f"inclonable")
    # Punto o espacio final: Windows stripuea esos caracteres del nombre real
    # en disco, asi que 'news.' crea un directorio llamado 'news' mientras el
    # index.md declara id: news. -> divergencia silenciosa que el validador no
    # ve (ver reports/CONFIRM-O-REPORT.md, BUG 12, y BUG 4 en validate_contracts). Se
    # rechaza para que el resultado sea exactamente lo que el usuario pidio.
    if name[-1] in (".", " "):
        return (f"nombre invalido '{name}': termina en '{name[-1]}' (punto o "
                f"espacio); el SO normaliza esos caracteres finales y el "
                f"directorio real deja de llamarse como se pidio, divergiendo "
                f"en silencio del id declarado")
    return None

INDEX_TEMPLATE = """---
id: {skill}
type: skill_index
domain_type: {domain_type}
---

# {skill}

Mapa de subhabilidades para esta skill. Los nodos de subskills se escriben DESPUES de una
exploracion libre del tema con IA (conversacion no estructurada, sin plantilla), como destilado
de esa exploracion, no en paralelo a ella: primero se entiende el territorio, despues se fija el
mapa.

## Subhabilidades

<listar aca a medida que se creen en subskills/>
"""


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--domain-type", required=True, choices=sorted(VALID_DOMAIN_TYPES))
    ap.add_argument("--root", default="knowledge")
    args = ap.parse_args(argv[1:])

    err = validate_name(args.name)
    if err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    # --root vacio o solo espacios: se rechaza. Path("") / <name> resuelve a
    # <name> relativo al cwd, asi que el scaffold se crea SILENCIOSAMENTE en el
    # directorio actual con exit 0 y el mensaje de exito habitual -- el script
    # obedece algo que nadie le pidio sin decir una palabra. La diferencia con
    # "--root ." / "--root ./" (invocaciones LEGITIMAS, crear explicitamente en
    # el cwd) es que ahi la persona lo pidio; con el string vacio, no. Se valida
    # la PROPIEDAD (el root que el usuario quizo), no la FORMA (Path("") no lanza).
    # exit 2, mismo codigo que los demas rechazos de validacion de este script.
    # Ver reports/FIX-ROOT-VACIO-REPORT.md.
    if not args.root or not args.root.strip():
        print(f"error: --root '{args.root}' esta vacio (o es solo espacios): "
              f"eso crearia el scaffold en el directorio actual sin un root "
              f"explicito; use '.' para crear aca a proposito", file=sys.stderr)
        return 2

    # --root debe ser un directorio (o no existir, en cuyo caso se crea). Si
    # apunta a un ARCHIVO existente, mkdir(parents=True) sobre <archivo>/<name>
    # explota con un FileExistsError crudo (WinError 183). Se detecta aca para
    # salir con mensaje limpio y exit 2, mismo codigo que "nombre invalido".
    # Ver reports/CONFIRM-O-REPORT.md, BUG 13.
    root = Path(args.root)
    if root.exists() and root.is_file():
        print(f"error: --root '{args.root}' es un archivo, no un directorio",
              file=sys.stderr)
        return 2

    base = root / args.name
    for sub in ("subskills", "mental_models", "failure_modes", "tools"):
        (base / sub).mkdir(parents=True, exist_ok=True)

    # shared/ cuelga de <root>, NO de <root>/<skill>: es hermano de la skill y guarda
    # mental_models/failure_modes/tools genericos a cualquier habilidad (ver
    # docs/REFERENCIA.md, "Reutilizacion entre habilidades"). Se crea idempotente para que el scaffold no
    # deje al usuario creandolo a mano y adivinando ubicacion/convencion. Directorios
    # vacios no aportan nodos (validate_contracts los ignora) y git no los trackea, asi
    # que crearlos no rompe nada.
    shared = root / "shared"
    for sub in ("mental_models", "failure_modes", "tools"):
        (shared / sub).mkdir(parents=True, exist_ok=True)

    index_path = base / "index.md"
    if index_path.exists():
        print(f"ya existe {index_path}, no se sobrescribe")
        return 1

    index_path.write_text(
        INDEX_TEMPLATE.format(skill=args.name, domain_type=args.domain_type),
        encoding="utf-8",
    )
    print(f"creado {base}/ con index.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
