#!/usr/bin/env python3
"""
Chequeo de congelamiento TEMPORAL del instrumento (mitad temporal de H2).

H2 cerro la mitad espacial: el criterio de un session_contract debe ser identico
al del skill_contract que referencia (validate_contracts.py). Esto congela el
instrumento en el espacio (todos los contratos que miden lo mismo declaran lo
mismo) pero no en el tiempo: nada impide editar el criterio del skill_contract
y el de sus sesiones a la vez, despues de ver un resultado.

Este script cierra esa mitad temporal via el historial de git. Un skill_contract
declara `instrument_frozen_at: <commit-sha>`: el commit en el que se congelo el
instrumento. Se recupera el contenido del PROPIO archivo del contrato en ese
commit (`git show <sha>:<path-relativo-al-repo>`), se extrae su campo `criterio`
y se compara EXACTO contra el `criterio` actual del archivo. Si difieren, el
instrumento se modifico despues de congelado -> error.

Vive aparte de validate_contracts.py a proposito: ese script es stdlib puro, sin
subprocess, y debe seguir funcionando en una carpeta suelta que NO sea un repo
git. Este chequeo es una capa mas fuerte y opcional que requiere git.

Tres desenlaces con exit codes DISTINTOS (la distincion es el corazon de la
tarea; no colapsarlos):

  exit 0 = VERIFICADO: todo lo chequeable se chequeo y esta bien.
  exit 1 = DIVERGENCIA / CONTRATO DEFECTUOSO: se pudo verificar y NO cumple.
           Entran: criterio divergente; falta instrument_frozen_at en un
           contrato active/checkpoint_done; el sha no existe en el repo; el
           archivo no existia en ese commit. Un contrato que afirma estar
           congelado en un commit invalido hace una afirmacion no verificable:
           es un defecto del contrato, no una limitacion del entorno.
  exit 2 = NO SE PUDO VERIFICAR (limitacion del ENTORNO, no del contrato): no
           estamos en un repo git, o git no esta instalado/no ejecutable.

QUE GARANTIZA Y QUE NO: convertir una edicion silenciosa del instrumento en un
acto auditable y visible en el historial. Para hacer trampa hay que apuntar
instrument_frozen_at a un commit mas nuevo, y eso es una edicion explicita del
archivo, visible en git. NO garantiza imposibilidad: la persona es duena del
repo y puede reescribir historia (amend, rebase, force-push). No se exagera la
garantia; se ofrece exactamente esta y se la declara.

Sin dependencias externas (stdlib solamente, subprocess incluido que es el
punto del script). Sin red. Sin LLM.
"""
import os
import re
import sys
import subprocess
from pathlib import Path

# Statuses que afirman un compromiso activo: el instrumento debe estar
# congelado, instrument_frozen_at es OBLIGATORIO. Si falta -> error (un
# compromiso activo sin instrumento congelado es precisamente el agujero).
FROZEN_REQUIRED_STATUS = ("active", "checkpoint_done")
# draft: la medicion todavia no arranco, el instrumento se puede ajustar. Si el
# campo esta ausente se omite (no es error). Si esta presente se verifica igual:
# congelar temprano es opt-in legitimo y se honra.
#
# FEAT-DISCONTINUED: discontinued es TERMINAL (el compromiso se cerro SIN
# llegar al checkpoint). NO exige instrument_frozen_at: pudo cerrarse sin que
# jamas se congelara nada (p.ej. venia de draft). Si el campo AUSENTE se omite
# (no es error). PERO si el campo ESTA presente se verifica igual: cerrar algo
# no es motivo para dejar de mostrar una divergencia que ya existia. No se
# esconde informacion que ya estaba a la vista. (Comportamiento identico al de
# draft, explicito a proposito para no dejarlo implicito.)
DRAFT_STATUS = "draft"
DISCONTINUED_STATUS = "discontinued"


def parse_frontmatter_text(text):
    """Parser de frontmatter plano de nivel 1 (escalares y listas inline).

    Es el mismo criterio de parseo simple que usa validate_contracts.py: solo
    nivel 1, no es un parser YAML completo. Se DUPLICA a proposito en vez de
    importarse: (1) validate_contracts.py es otro perimetro y el brief pide no
    importarlo ni modificarlo; (2) ese parser lee desde un Path en disco, y aca
    necesitamos parsear el texto que devuelve `git show` (un string), asi que
    hace falta una variante sobre string de todas formas. La logica duplicada
    es deliberada y acotada a este uso.

    Devuelve (data, None) o (None, mensaje_error).
    """
    if not text.startswith("---"):
        return None, "falta frontmatter YAML (no empieza con ---)"
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, "frontmatter YAML mal cerrado"
    raw = parts[1]
    data = {}
    for line in raw.strip().splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        # solo nivel 1 (listas inline entre corchetes o escalares); suficiente
        # para los contratos de este scaffold, no es un parser YAML completo.
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


def _field_present(value):
    """True si el campo tiene un valor util (no ausente/vacio/null/None)."""
    return value not in (None, "", "null", "None")


def git_available():
    """True si git esta instalado y ejecutable."""
    try:
        r = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True,
        )
        return r.returncode == 0
    except (FileNotFoundError, OSError):
        return False


def repo_root(path, cache):
    """Devuelve el toplevel del repo git que contiene a `path`, o None si no
    esta en un repo. Cachea por directorio padre para no repetir rev-parse."""
    parent = path.resolve().parent
    if parent in cache:
        return cache[parent]
    r = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(parent), capture_output=True, text=True, encoding="utf-8",
    )
    if r.returncode != 0:
        cache[parent] = None
    else:
        cache[parent] = Path(r.stdout.strip()).resolve()
    return cache[parent]


# `instrument_frozen_at` debe ser una referencia INMUTABLE a un commit. La
# forma minima es hex de 7 a 40 chars (menos de 7 es ambiguo); la propiedad
# que vela esta regex es solo la primera valla. La valla de fondo es
# `resolve_frozen_at`: el valor debe resolver a un commit y el sha completo
# resuelto debe EMPEZAR con el valor declarado. Eso es lo que descarta HEAD,
# ramas y tags moviles: un nombre de ref no es prefijo hex de su propio sha,
# asi que un ref movil nunca pasa la valla de la propiedad aunque tenga pinta
# de "algo que git acepta" (git cat-file -e HEAD da rc=0, pero no es inmutable).
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
SHORT_HEX_RE = re.compile(r"^[0-9a-f]{1,6}$")


def _resolves_as_ref(value, root):
    """True si `value` resuelve como una ref git (HEAD/rama/tag) sin ser sha.

    Se usa solo para distinguir una ref movil (no-hex pero git la resuelve) de
    un valor que no es sha ni ref. Un sha hex valido nunca llega aca: se filtra
    antes por SHA_RE.
    """
    r = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", value],
        cwd=str(root), capture_output=True, text=True,
    )
    return r.returncode == 0


def resolve_frozen_at(value, root):
    """Valida y resuelve `instrument_frozen_at` a un commit sha inmutable.

    Devuelve (full_sha, None) o (None, mensaje_error). La garantia es la
    PROPIEDAD (referencia inmutable a un commit existente), no la forma: que el
    valor sea hex no alcanza, tiene que ser prefijo del sha completo del commit
    al que resuelve. Esa es la valla que derrotaba HEAD/master: git las acepta
    y resuelven al commit actual, pero su sha completo no empieza con 'HEAD' ni
    'master', asi que se rechazan como refs moviles.
    """
    raw = (value or "").strip()
    lower = raw.lower()

    # Valla 1 (forma): hex 7-40. Menos de 7 es ambiguo.
    if SHA_RE.match(lower):
        # Resuelve a un commit (peeling ^{commit} rechaza blobs/trees/tags-objeto).
        r = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{lower}^{{commit}}"],
            cwd=str(root), capture_output=True, text=True,
        )
        if r.returncode != 0:
            return None, f"instrument_frozen_at '{raw}' no es un commit del repo"
        full = r.stdout.strip().lower()
        # Valla 2 (propiedad): el sha completo resuelto debe empezar con el
        # valor declarado. Para un hex puro esto siempre vale; se deja como
        # defensa: cualquier cosa que colara el regex sin ser prefijo del sha
        # real seria un ref disfrazado, y se rechaza igual que un ref movil.
        if not full.startswith(lower):
            return None, (
                f"instrument_frozen_at '{raw}' no es una referencia inmutable "
                f"a un commit (el sha resuelto '{full[:7]}' no empieza con el "
                f"valor declarado); debe ser un sha de commit inmutable"
            )
        return full, None

    # No es hex 7-40. Si git lo resuelve como ref, es una ref movil (HEAD/rama/
    # tag): pasa la FORMA de "algo que git acepta" pero no la PROPIEDAD de ser
    # inmutable. Es el error que mas probablemente cometa quien sigue docs/REFERENCIA.md.
    if _resolves_as_ref(raw, root):
        return None, (
            f"instrument_frozen_at '{raw}' es una ref movil (HEAD, rama o tag); "
            f"debe ser un sha de commit inmutable. Una ref movil se mueve con "
            f"cada commit, asi que el 'criterio congelado' seguiria al puntero y "
            f"un editar-el-criterio+commitear pasaria como verificado sin tocar "
            f"el campo: justo el cambio silencioso que este chequeo existe para "
            f"evitar. Usar el sha del commit (>=7 hex)."
        )

    # No hex, no ref. Si es hex corto (<7) -> ambiguo.
    if SHORT_HEX_RE.match(lower):
        return None, (
            f"instrument_frozen_at '{raw}' es ambiguo (muy corto); usar >=7 "
            f"caracteres hex del sha para identificar el commit de forma univoca"
        )

    return None, f"instrument_frozen_at '{raw}' no es un sha de commit valido"


def file_at_commit(sha, relpath, root):
    """Devuelve (contenido, None) del archivo <relpath> en el commit <sha>, o
    (None, stderr) si git show falla (el archivo no existia en ese commit)."""
    r = subprocess.run(
        ["git", "show", f"{sha}:{relpath}"],
        cwd=str(root), capture_output=True, text=True, encoding="utf-8",
    )
    if r.returncode != 0:
        return None, r.stderr.strip()
    return r.stdout, None


def _relpath(path, root):
    """Path relativo al repo, con separadores '/' que es lo que git show espera."""
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        # fallback por diferencias de casing/normalizacion entre el path en
        # disco y el toplevel que devolvio git (raro, pero no cuelga el chequeo).
        return os.path.relpath(str(path.resolve()), str(root)).replace(os.sep, "/")


def main(argv):
    if len(argv) < 2:
        print("uso: check_instrument_freeze.py <contracts_dir> [...]")
        return 1

    roots = [Path(p) for p in argv[1:]]
    md_files = []
    for root in roots:
        if not root.exists():
            print(f"AVISO: {root} no existe, se omite")
            continue
        md_files.extend(sorted(root.rglob("*.md")))

    # Recolectar nodos type: skill_contract. Este script NO valida forma de
    # frontmatter (eso es perimetro de validate_contracts.py); un .md sin
    # frontmatter o mal cerrado se omite, no es error aca.
    contracts = []
    for path in md_files:
        if path.name.startswith("README") or "templates" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        data, _err = parse_frontmatter_text(text)
        if data and data.get("type") == "skill_contract":
            contracts.append((path, data))

    errors = []
    verificados = 0
    omitidos = 0
    need_git = []  # (path, data, sha): contratos que requieren verificar contra git

    for path, data in contracts:
        status = data.get("status")
        sha = data.get("instrument_frozen_at")
        sha_present = _field_present(sha)

        if status in FROZEN_REQUIRED_STATUS:
            if not sha_present:
                errors.append(
                    f"{path}: status {status} requiere instrument_frozen_at "
                    f"(commit donde se congelo el instrumento)"
                )
                continue
            need_git.append((path, data, sha))
        else:
            # draft o discontinued (o status no reconocido): sin el campo se
            # omite, con el campo se verifica. Para discontinued esto es lo que
            # mas importa: cerrar no exige congelar, PERO si el campo esta no se
            # esconde una divergencia que ya estaba (no se borra lo que ya estaba
            # a la vista).
            if not sha_present:
                omitidos += 1
                continue
            need_git.append((path, data, sha))

    # Solo se necesita git si hay algo que verificar. Si todo se omitio (p.ej.
    # todos draft sin el campo) no hay nada que comprobar -> exit 0 sin tocar
    # git, incluso en una maquina sin git instalado.
    if need_git:
        if not git_available():
            print("no se pudo verificar: git no esta disponible o no es ejecutable")
            print("(el chequeo de congelado requiere git; limitacion del entorno, no del contrato)")
            return 2

        repo_cache = {}
        for path, data, sha in need_git:
            root = repo_root(path, repo_cache)
            if root is None:
                print(f"no se pudo verificar: {path} no esta dentro de un repo git")
                print("(el chequeo de congelado requiere git; limitacion del entorno, no del contrato)")
                return 2

            rel = _relpath(path, root)

            # instrument_frozen_at debe ser una ref INMUTABLE a un commit
            # existente (sha hex >=7 que prefije al sha completo). Una ref
            # movil (HEAD/rama/tag) se rechaza aca: si no, el "congelado"
            # seguira al puntero y un edita+commitea pasaria como verificado
            # sin comparar de verdad. Defecto del contrato -> exit 1.
            full_sha, sha_err = resolve_frozen_at(sha, root)
            if full_sha is None:
                errors.append(f"{path}: {sha_err}")
                continue

            content, _git_err = file_at_commit(full_sha, rel, root)
            if content is None:
                # El archivo no existia en ese commit (renombre/movido despues
                # del congelado, o el path nunca existio). Mensaje DISTINTO al
                # de "criterio diverge": un renombre legitimo no es un cambio de
                # instrumento y no se reporta igual.
                errors.append(f"{path}: el archivo no existia en el commit {full_sha[:7]}")
                continue

            frozen_data, perr = parse_frontmatter_text(content)
            if perr or frozen_data is None:
                errors.append(f"{path}: el archivo en el commit {full_sha[:7]} no tenia frontmatter valido")
                continue

            frozen_criterio = frozen_data.get("criterio", "")
            current_criterio = data.get("criterio", "")
            # Comparacion EXACTA, misma estrictez que H2: un espacio de
            # diferencia es un cambio de instrumento. Sin normalizacion extra.
            if current_criterio != frozen_criterio:
                errors.append(
                    f"{path}: criterio diverge del congelado en {full_sha[:7]} "
                    f"(congelado='{frozen_criterio}', actual='{current_criterio}')"
                )
                continue

            verificados += 1

    if errors:
        print(f"FALLO: {len(errors)} error(es)\n")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK: {verificados} verificado(s), {omitidos} omitido(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))