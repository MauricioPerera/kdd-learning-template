#!/usr/bin/env python3
"""Tests de kdd.py (CLI de conveniencia sobre scripts/).

Verifican:
  - cada comando delega en el script correcto con los argumentos correctos
    (se monkeypatchea kdd._script para capturar el argv que se le arma a cada
    main, sin tocar los scripts reales);
  - kdd check con todo bien -> exit 0;
  - kdd check con una herramienta en 1 -> exit 1;
  - kdd check con una herramienta en 2 y ninguna en 1 -> exit 2 (caso critico:
    un 2 de check_instrument_freeze no debe aplastarse a exito);
  - correr desde un directorio que no es un proyecto -> error claro, exit != 0;
  - --help y sin argumentos listan los comandos.

Los tests que usan rutas convencionales corren desde la raiz del repo (cwd del
suite), donde knowledge/, contracts/ y logs/progress.md existen.
"""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import kdd  # noqa: E402  (kdd.py vive en la raiz del repo, no es paquete)


class FakeScript:
    """Sustituto de un modulo de script: registra el argv que le llega a main
    y devuelve un exit code prefijado."""

    def __init__(self, name, code=0):
        self.name = name
        self.code = code
        self.calls = []

    def main(self, argv):
        self.calls.append(list(argv))
        return self.code


def _patch_scripts(codes):
    """Devuelve un patcher de kdd._script que entrega un FakeScript por nombre.

    `codes` es un dict {script_name: exit_code}. Captura los FakeScript en el
    atributo `.fakes` del mock para inspeccionar las llamadas."""
    fakes = {name: FakeScript(name, code) for name, code in codes.items()}

    def fake(name):
        if name not in fakes:
            fakes[name] = FakeScript(name, 0)
        return fakes[name]

    patcher = mock.patch.object(kdd, "_script", side_effect=fake)
    patcher.fakes = fakes
    return patcher


class DelegacionTest(unittest.TestCase):
    """Cada comando arma el argv correcto para el script que envuelve."""

    def _run_with_codes(self, argv, codes):
        patcher = _patch_scripts(codes)
        patcher.start()
        self.addCleanup(patcher.stop)
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            code = kdd.main(argv)
        return code, patcher.fakes

    def test_init_inyecta_name_posicional(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "init", "foo", "--domain-type", "physical"],
            {"init_skill": 0},
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["init_skill"].calls,
            [["init_skill", "--name", "foo", "--domain-type", "physical"]],
        )

    def test_contracts_defaults(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "contracts"], {"validate_contracts": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["validate_contracts"].calls,
            [["validate_contracts", "knowledge", "contracts"]],
        )

    def test_contracts_rutas_explicitas_se_reenvian(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "contracts", "/a", "/b"], {"validate_contracts": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["validate_contracts"].calls,
            [["validate_contracts", "/a", "/b"]],
        )

    def test_evidence_defaults(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "evidence"], {"validate_evidence": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["validate_evidence"].calls,
            [["validate_evidence", "logs/progress.md", "knowledge", "contracts"]],
        )

    def test_evidence_rutas_explicitas(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "evidence", "/log", "/k", "/c"],
            {"validate_evidence": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["validate_evidence"].calls,
            [["validate_evidence", "/log", "/k", "/c"]],
        )

    def test_decay_defaults_sin_apply(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "decay"], {"decay_check": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["decay_check"].calls, [["decay_check", "knowledge"]])

    def test_decay_apply_default_dir(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "decay", "--apply"], {"decay_check": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["decay_check"].calls,
            [["decay_check", "knowledge", "--apply"]])

    def test_decay_dir_explicito_con_apply(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "decay", "--apply", "/k"], {"decay_check": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["decay_check"].calls,
            [["decay_check", "/k", "--apply"]])

    def test_freeze_defaults(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "freeze"], {"check_instrument_freeze": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["check_instrument_freeze"].calls,
            [["check_instrument_freeze", "contracts"]])

    def test_freeze_ruta_explicita(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "freeze", "/c"], {"check_instrument_freeze": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["check_instrument_freeze"].calls,
            [["check_instrument_freeze", "/c"]])

    def test_adherence_defaults_sin_logfile(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "adherence", "--skill", "ukulele"],
            {"adherence": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["adherence"].calls,
            [["adherence", "logs/progress.md", "--skill", "ukulele"]])

    def test_adherence_logfile_explicito(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "adherence", "/mylog", "--skill", "x", "--subskill", "y"],
            {"adherence": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["adherence"].calls,
            [["adherence", "/mylog", "--skill", "x", "--subskill", "y"]])

    def test_adherence_skill_pegado_igual(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "adherence", "--skill=ukulele"], {"adherence": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["adherence"].calls,
            [["adherence", "logs/progress.md", "--skill", "ukulele"]])

    def test_commitment_defaults(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "commitment"], {"commitment_status": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["commitment_status"].calls,
            [["commitment_status", "logs/progress.md", "contracts"]])

    def test_commitment_rutas_explicitas(self):
        code, fakes = self._run_with_codes(
            ["kdd.py", "commitment", "/log", "/c"],
            {"commitment_status": 0})
        self.assertEqual(code, 0)
        self.assertEqual(
            fakes["commitment_status"].calls,
            [["commitment_status", "/log", "/c"]])


class CheckTest(unittest.TestCase):
    """kdd check: agregado de exit codes y resumen."""

    ALL = {
        "validate_contracts": 0,
        "validate_evidence": 0,
        "decay_check": 0,
        "check_instrument_freeze": 0,
        "adherence": 0,
        "commitment_status": 0,
    }

    def _run_check(self, codes):
        patcher = _patch_scripts(codes)
        patcher.start()
        self.addCleanup(patcher.stop)
        buf = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            code = kdd.main(["kdd.py", "check"])
        return code, buf.getvalue(), err.getvalue(), patcher.fakes

    def test_check_todo_bien_devuelve_0(self):
        code, out, _, fakes = self._run_check(dict(self.ALL))
        self.assertEqual(code, 0)
        # corrio las 6 herramientas en orden, con sus args convencionales
        self.assertEqual(
            fakes["validate_contracts"].calls,
            [["validate_contracts", "knowledge", "contracts"]])
        self.assertEqual(
            fakes["validate_evidence"].calls,
            [["validate_evidence", "logs/progress.md", "knowledge", "contracts"]])
        self.assertEqual(
            fakes["decay_check"].calls, [["decay_check", "knowledge"]])
        self.assertEqual(
            fakes["check_instrument_freeze"].calls,
            [["check_instrument_freeze", "contracts"]])
        self.assertEqual(
            fakes["adherence"].calls, [["adherence", "logs/progress.md"]])
        self.assertEqual(
            fakes["commitment_status"].calls,
            [["commitment_status", "logs/progress.md", "contracts"]])
        # resumen con una linea por herramienta, todas ok
        self.assertIn("resumen:", out)
        for label in ("contracts", "evidence", "decay", "freeze",
                      "adherence", "commitment"):
            self.assertIn(f"{label}: ok (exit 0)", out)

    def test_check_una_herramienta_en_1_devuelve_1(self):
        codes = dict(self.ALL)
        codes["validate_contracts"] = 1
        code, out, _, _ = self._run_check(codes)
        self.assertEqual(code, 1)
        self.assertIn("contracts: fallo (exit 1)", out)

    def test_check_una_en_2_y_ninguna_en_1_devuelve_2(self):
        # CASO CRITICO: freeze devuelve 2 (no se pudo verificar, sin git) y el
        # resto 0. El agregado debe devolver 2, no 0: un 2 no es exito.
        codes = dict(self.ALL)
        codes["check_instrument_freeze"] = 2
        code, out, _, _ = self._run_check(codes)
        self.assertEqual(code, 2)
        # el resumen etiqueta el 2 explicitamente como no-exito
        self.assertIn("freeze: no se pudo verificar (no es exito) (exit 2)", out)
        # las demas siguen ok y NO se reportan como fallo
        self.assertIn("contracts: ok (exit 0)", out)

    def test_check_un_1_aplasta_al_2(self):
        # si hay un 1 Y un 2, gana el 1 (fallo real sobre no-se-pudo-verificar).
        codes = dict(self.ALL)
        codes["validate_contracts"] = 1
        codes["check_instrument_freeze"] = 2
        code, out, _, _ = self._run_check(codes)
        self.assertEqual(code, 1)

    def test_check_rutas_explicitas_se_propagan(self):
        codes = dict(self.ALL)
        patcher = _patch_scripts(codes)
        patcher.start()
        self.addCleanup(patcher.stop)
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            code = kdd.main(["kdd.py", "check", "/K", "/C", "/L"])
        self.assertEqual(code, 0)
        fakes = patcher.fakes
        self.assertEqual(
            fakes["validate_contracts"].calls,
            [["validate_contracts", "/K", "/C"]])
        self.assertEqual(
            fakes["validate_evidence"].calls,
            [["validate_evidence", "/L", "/K", "/C"]])
        self.assertEqual(
            fakes["commitment_status"].calls,
            [["commitment_status", "/L", "/C"]])

    def test_check_numero_incorrecto_de_rutas_falla(self):
        buf = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(err):
            code = kdd.main(["kdd.py", "check", "/K", "/C"])
        self.assertNotEqual(code, 0)
        self.assertIn("0 rutas", err.getvalue())


class RaizTest(unittest.TestCase):
    """Deteccion de raiz: fuera de un proyecto, error claro y exit != 0."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp(prefix="kdd_cli_")

    def tearDown(self):
        os.chdir(self._cwd)
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_contracts_fuera_de_proyecto_error_claro(self):
        os.chdir(self._tmp)  # tempdir vacio: sin knowledge/ ni contracts/
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = kdd.main(["kdd.py", "contracts"])
        self.assertNotEqual(code, 0)
        msg = err.getvalue()
        self.assertIn("no parece la raiz de un proyecto KDD-Learning", msg)
        self.assertIn("falta", msg)

    def test_check_fuera_de_proyecto_error_claro(self):
        os.chdir(self._tmp)
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = kdd.main(["kdd.py", "check"])
        self.assertNotEqual(code, 0)
        self.assertIn("no parece la raiz de un proyecto KDD-Learning",
                      err.getvalue())

    def test_adherence_sin_logfile_fuera_de_proyecto_error_claro(self):
        os.chdir(self._tmp)
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = kdd.main(["kdd.py", "adherence"])
        self.assertNotEqual(code, 0)
        self.assertIn("falta", err.getvalue())


class AyudaTest(unittest.TestCase):
    def test_sin_argumentos_lista_comandos(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = kdd.main(["kdd.py"])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        for cmd in ("init", "contracts", "evidence", "decay", "freeze",
                    "adherence", "commitment", "check"):
            self.assertIn(cmd, out)

    def test_help_lista_comandos(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = kdd.main(["kdd.py", "--help"])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("check", out)
        self.assertIn("comandos", out)

    def test_comando_desconocido_falla(self):
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = kdd.main(["kdd.py", "noexiste"])
        self.assertNotEqual(code, 0)
        self.assertIn("comando desconocido", err.getvalue())


if __name__ == "__main__":
    unittest.main()