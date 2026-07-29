#!/usr/bin/env python3
"""CLI de conveniencia que envuelve los 7 scripts de scripts/.

ESTA ES UNA CAPA DE CONVENIENCIA, NO LA INTERFAZ DE REFERENCIA. Los scripts de
scripts/ siguen siendo la interfaz estable: tienen 321 tests encima, siguen
funcionando con su invocacion larga de siempre, y no se refactorizan aca. Esta
CLI solo importa sus main() y les arma los argumentos con las rutas
convencionales del proyecto (knowledge, contracts, logs/progress.md) para que
no haya que escribirlas a mano.

Cada comando acepta rutas explicitas si alguien las pasa (se las reenvia al
script tal cual), pero funciona sin argumentos desde la raiz del proyecto.

`kdd check` corre todas las verificaciones en orden, cada una con su encabezado,
y termina con un resumen de una linea por herramienta. El exit code agregado
respetando la semantica de check_instrument_freeze (0 = verificado, 1 = fallo,
2 = no se pudo verificar):
  - si alguna herramienta devolvio 1 -> kdd check devuelve 1;
  - si ninguna devolvio 1 pero alguna devolvio 2 -> devuelve 2;
  - si todas devolvieron 0 -> devuelve 0.
El resumen dice explicitamente cual herramienta devolvio que, para que un 2
("no se pudo verificar") nunca se lea como un exito: es el falso determinismo
que este proyecto entero existe para evitar.

stdlib solamente. Sin red. Sin LLM.
"""
import sys
import importlib.util
from pathlib import Path

# Los scripts viven en scripts/, al lado de este archivo. Se cargan por ruta
# (no son un paquete) y se invoca su main(argv) con un argv sintetico donde
# argv[0] es el nombre del script y argv[1:] son los argumentos que cada script
# espera. No se toca ni se refactoriza ningun script: la CLI los envuelve.
_SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
_SCRIPTS = {}


def _script(name):
    """Carga (y cachea) el modulo de un script de scripts/ por su ruta."""
    if name not in _SCRIPTS:
        path = _SCRIPTS_DIR / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"kdd_cli.{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _SCRIPTS[name] = mod
    return _SCRIPTS[name]


def _run(script_name, args):
    """Invoca main(argv) del script con argv = [script_name] + args.

    Cada script de este proyecto sigue la convencion main(argv) donde argv[1:]
    son los argumentos reales (los que usan argparse o los posicionales). Se les
    pasa un argv[0] nominal para que argparse y los conteos por len(argv) sean
    los mismos que en su invocacion directa."""
    return _script(script_name).main([script_name] + list(args))


# Rutas convencionales del proyecto, relativas al directorio de trabajo. Son el
# punto de toda esta CLI: no deberian escribirse a mano nunca.
def _conventional_paths():
    return {
        "knowledge": Path("knowledge"),
        "contracts": Path("contracts"),
        "logfile": Path("logs") / "progress.md",
    }


def _require(needed):
    """Verifica que las rutas convencionales pedidas existan en el cwd.

    Devuelve (True, None) si todas existen, o (False, mensaje) si falta alguna.
    Es la deteccion de raiz: correr desde un subdirectorio o un lugar que no es
    un proyecto KDD-Learning se reporta claro y de entrada, no como un traceback
    o un fallo raro rio abajo."""
    paths = _conventional_paths()
    missing = [str(paths[k]) for k in needed if not paths[k].exists()]
    if missing:
        return False, (
            "no parece la raiz de un proyecto KDD-Learning: falta "
            + ", ".join(missing)
        )
    return True, None


def cmd_init(args):
    # kdd init <nombre> --domain-type <tipo> [--root <dir>]
    # El nombre es posicional en la CLI pero --name en init_skill; se inyecta.
    if not args:
        print("uso: kdd init <nombre> --domain-type <tipo> [--root <dir>]",
              file=sys.stderr)
        return 2
    name = args[0]
    return _run("init_skill", ["--name", name] + list(args[1:]))


def cmd_contracts(args):
    if args:
        return _run("validate_contracts", args)
    ok, msg = _require(["knowledge", "contracts"])
    if not ok:
        print(msg, file=sys.stderr)
        return 1
    return _run("validate_contracts", ["knowledge", "contracts"])


def cmd_evidence(args):
    if args:
        return _run("validate_evidence", args)
    ok, msg = _require(["logfile", "knowledge", "contracts"])
    if not ok:
        print(msg, file=sys.stderr)
        return 1
    return _run("validate_evidence", ["logs/progress.md", "knowledge", "contracts"])


def cmd_decay(args):
    # kdd decay [--apply] [knowledge_dir]
    apply_flag = "--apply" in args
    positional = [a for a in args if a != "--apply"]
    if positional:
        kdir = positional[0]
    else:
        ok, msg = _require(["knowledge"])
        if not ok:
            print(msg, file=sys.stderr)
            return 1
        kdir = "knowledge"
    run_args = [kdir] + (["--apply"] if apply_flag else [])
    return _run("decay_check", run_args)


def cmd_freeze(args):
    if args:
        return _run("check_instrument_freeze", args)
    ok, msg = _require(["contracts"])
    if not ok:
        print(msg, file=sys.stderr)
        return 1
    return _run("check_instrument_freeze", ["contracts"])


def cmd_adherence(args):
    # kdd adherence [logfile] [--skill X] [--subskill Y]
    # Si no se pasa logfile, se usa el convencional (logs/progress.md). Hay que
    # separar el logfile posicional de los flags --skill/--subskill (con valor
    # pegado por '=' o separado) para saber si el usuario lo dio o no.
    skill = None
    subskill = None
    logfile = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--skill" and i + 1 < len(args):
            skill = args[i + 1]
            i += 2
        elif a == "--subskill" and i + 1 < len(args):
            subskill = args[i + 1]
            i += 2
        elif a.startswith("--skill="):
            skill = a.split("=", 1)[1]
            i += 1
        elif a.startswith("--subskill="):
            subskill = a.split("=", 1)[1]
            i += 1
        elif logfile is None and not a.startswith("-"):
            logfile = a
            i += 1
        else:
            i += 1
    if logfile is None:
        ok, msg = _require(["logfile"])
        if not ok:
            print(msg, file=sys.stderr)
            return 1
        logfile = "logs/progress.md"
    run_args = [logfile]
    if skill is not None:
        run_args += ["--skill", skill]
    if subskill is not None:
        run_args += ["--subskill", subskill]
    return _run("adherence", run_args)


def cmd_commitment(args):
    # kdd commitment [logfile] [contracts_dir ...]
    if args:
        return _run("commitment_status", args)
    ok, msg = _require(["logfile", "contracts"])
    if not ok:
        print(msg, file=sys.stderr)
        return 1
    return _run("commitment_status", ["logs/progress.md", "contracts"])


# Orden de `kdd check`: forma (contracts) -> integridad referencial (evidence)
# -> decaimiento temporal (decay) -> congelamiento del instrumento (freeze) ->
# adherencia (adherence) -> ventana del compromiso (commitment).
CHECK_PLAN = [
    ("contracts", "validate_contracts", ["knowledge", "contracts"]),
    ("evidence", "validate_evidence",
     ["logs/progress.md", "knowledge", "contracts"]),
    ("decay", "decay_check", ["knowledge"]),
    ("freeze", "check_instrument_freeze", ["contracts"]),
    ("adherence", "adherence", ["logs/progress.md"]),
    ("commitment", "commitment_status", ["logs/progress.md", "contracts"]),
]


def _outcome(code):
    """Etiqueta legible del exit code de una herramienta, para el resumen.
    El 2 se etiqueta explicitamente como 'no se pudo verificar' y se aclara que
    no es exito: es lo que evita que un 2 se lea como verde."""
    if code == 0:
        return "ok"
    if code == 1:
        return "fallo"
    if code == 2:
        return "no se pudo verificar (no es exito)"
    return f"exit {code}"


def cmd_check(args):
    # kdd check [knowledge_dir contracts_dir logfile]
    # 0 rutas -> convencionales (con deteccion de raiz); 3 -> explicitas.
    defaults = _conventional_paths()
    if len(args) == 0:
        ok, msg = _require(["knowledge", "contracts", "logfile"])
        if not ok:
            print(msg, file=sys.stderr)
            return 1
        knowledge = str(defaults["knowledge"])
        contracts = str(defaults["contracts"])
        logfile = "logs/progress.md"
    elif len(args) == 3:
        knowledge, contracts, logfile = args
    else:
        print("kdd check espera 0 rutas (usa knowledge, contracts, "
              "logs/progress.md) o 3 (knowledge contracts logfile)",
              file=sys.stderr)
        return 2

    plan = [
        ("contracts", "validate_contracts", [knowledge, contracts]),
        ("evidence", "validate_evidence", [logfile, knowledge, contracts]),
        ("decay", "decay_check", [knowledge]),
        ("freeze", "check_instrument_freeze", [contracts]),
        ("adherence", "adherence", [logfile]),
        ("commitment", "commitment_status", [logfile, contracts]),
    ]

    results = []
    for label, script, run_args in plan:
        print(f"\n=== {label} ===")
        code = _run(script, run_args)
        results.append((label, code))

    print("\nresumen:")
    for label, code in results:
        print(f"  {label}: {_outcome(code)} (exit {code})")

    if any(c == 1 for _, c in results):
        return 1
    if any(c == 2 for _, c in results):
        return 2
    return 0


COMMANDS = {
    "init": cmd_init,
    "contracts": cmd_contracts,
    "evidence": cmd_evidence,
    "decay": cmd_decay,
    "freeze": cmd_freeze,
    "adherence": cmd_adherence,
    "commitment": cmd_commitment,
    "check": cmd_check,
}

USAGE = """\
kdd.py <comando> [args]

capa de conveniencia sobre los scripts de scripts/. los comandos largos
(python scripts/<x>.py ...) siguen siendo validos y son la interfaz de
referencia; esta CLI solo les arma las rutas convencionales del proyecto.

comandos:
  init <nombre> --domain-type <tipo>   crea el esqueleto de una habilidad nueva
  contracts                            valida la forma de cada nodo
  evidence                             valida que el log apunte a nodos que existen
  decay [--apply]                      verifica cuales subhabilidades vencieron
  freeze                               verifica que el criterio no se haya aflojado (requiere git)
  adherence [--skill X] [--subskill Y] reporta racha y dias desde la ultima sesion
  commitment                           reporta el estado de los compromisos activos
  check                                corre todas las verificaciones y resume

los defaults son knowledge, contracts, logs/progress.md; cualquier comando
acepta rutas explicitas en su lugar. kdd check devuelve 1 si alguna herramienta
fallo, 2 si ninguna fallo pero alguna no se pudo verificar, 0 si todas ok.
"""


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(USAGE)
        return 0
    cmd = argv[1]
    if cmd not in COMMANDS:
        print(f"comando desconocido: {cmd}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    return COMMANDS[cmd](argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))