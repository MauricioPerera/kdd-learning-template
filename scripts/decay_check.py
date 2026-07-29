#!/usr/bin/env python3
"""
Compara last_verified + review_after_days contra hoy. Si vencio, propone pasar el nodo de
'verified' a 'needs_review'. Esto SI es determinismo real: es comparacion de fechas, no una
medicion de si la habilidad realmente se degrado.

'needs_review' no es un retroceso a 'draft': reconoce que hubo una verificacion real en el
pasado pero que el sistema no puede asumir que sigue vigente sin evidencia nueva.

Dry-run por defecto (solo reporta). --apply reescribe el campo status en el archivo.
"""
import sys
import re
import argparse
from datetime import datetime
from pathlib import Path


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("knowledge_dir")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv[1:])

    root = Path(args.knowledge_dir)
    today = datetime.now().date()
    flagged = []

    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        if "type: subskill" not in text:
            continue

        status_m = re.search(r"^status:\s*(\S+)", text, re.MULTILINE)
        last_verified_m = re.search(r"^last_verified:\s*(\S+)", text, re.MULTILINE)
        review_after_m = re.search(r"^review_after_days:\s*(\d+)", text, re.MULTILINE)

        if not (status_m and last_verified_m and review_after_m):
            continue
        if status_m.group(1) != "verified":
            continue
        if last_verified_m.group(1) in ("null", "None", ""):
            continue

        try:
            last_verified = datetime.fromisoformat(last_verified_m.group(1)).date()
        except ValueError:
            continue

        review_after_days = int(review_after_m.group(1))
        due = (today - last_verified).days >= review_after_days

        if due:
            flagged.append(path)
            if args.apply:
                # Reemplaza SOLO el valor del campo status que matcheo el regex
                # (anclado a ^status:), usando su span. Antes se usaba
                # text.replace("status: verified", ..., 1): str.replace ciego que
                # exige la forma exacta "status: verified" (un espacio, misma linea).
                # El regex en cambio tolera spacing variable (\s* traga espacios,
                # tabs y hasta un newline) y el valor en la linea siguiente. Esa
                # discrepancia provocaba un no-op silencioso con --apply: el nodo se
                # reportaba como actualizado pero el archivo quedaba intacto. Operar
                # sobre el span del grupo(1) reescribe exactamente el valor matcheado,
                # sin importar el whitespace y sin tocar prosa que contenga la
                # subcadena "status: verified".
                new_text = text[:status_m.start(1)] + "needs_review" + text[status_m.end(1):]
                path.write_text(new_text, encoding="utf-8")

    if not flagged:
        print("ningun nodo vencido")
        return 0

    action = "actualizados a needs_review" if args.apply else "vencidos (dry-run, usar --apply para escribir)"
    print(f"{len(flagged)} nodo(s) {action}:")
    for p in flagged:
        print(f"  - {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
