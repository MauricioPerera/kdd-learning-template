#!/usr/bin/env python3
"""Oraculo congelado para scripts/init_skill.py.

Sin dependencias externas (stdlib solamente), igual que el script bajo prueba.
Cubre: validacion de nombre (anti-contaminacion/escape de root), creacion del
scaffold, no-sobrescritura, idempotencia de subdirectorios, exit codes, y el
contrato implicito con scripts/validate_contracts.py (el index.md generado
debe pasar la validacion de forma).

IMPORTANTE: nunca corre init_skill.py contra el knowledge/ real del proyecto;
todos los --root apuntan a directorios temporales (tempfile.TemporaryDirectory).
El unico caso que toca la raiz relativa "knowledge" lo hace tras cambiar el cwd
a un temp dir.
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import init_skill  # noqa: E402
import validate_contracts as vc  # noqa: E402


def run_main(argv):
    """Invoca init_skill.main(argv) capturando stdout/stderr. Devuelve (rc, out, err).
    Atrapa SystemExit (argparse llama a sys.exit(2) ante args invalidos/faltantes)
    y lo convierte en rc, preservando el mensaje a stderr."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            rc = init_skill.main(["init_skill.py", *argv])
        except SystemExit as e:
            rc = e.code if e.code is not None else 0
    return rc, out.getvalue(), err.getvalue()


class TestValidateName(unittest.TestCase):
    """Validacion de nombre: anti-contaminacion del root y anti-escape.

    No es un chequeo de seguridad (scaffold local de uso personal): es un
    chequeo de correctitud para que el scaffold no escriba silenciosamente
    fuera de <root>/<name>. Ver reports/AUDIT-E-INIT-SKILL-REPORT.md, hallazgo A.
    """

    def test_valid_simple_name_ok(self):
        for nm in ("ukulele", "n8n", "bateria_3", "foo-bar"):
            self.assertIsNone(init_skill.validate_name(nm), f"{nm!r} deberia ser valido")

    def test_empty_string_rejected(self):
        self.assertIsNotNone(init_skill.validate_name(""))

    def test_whitespace_only_rejected(self):
        for nm in ("   ", "\t", " \n "):
            self.assertIsNotNone(init_skill.validate_name(nm))

    def test_dot_and_dotdot_rejected(self):
        self.assertIsNotNone(init_skill.validate_name("."))
        self.assertIsNotNone(init_skill.validate_name(".."))

    def test_path_separator_slash_rejected(self):
        for nm in ("con/barra", "a/b/c", "/abs", "trailing/"):
            self.assertIsNotNone(init_skill.validate_name(nm))

    def test_backslash_separator_rejected(self):
        self.assertIsNotNone(init_skill.validate_name("a\\b"))

    def test_traversal_rejected(self):
        for nm in ("../../evil", "../x", "..\\..\\evil"):
            self.assertIsNotNone(init_skill.validate_name(nm))

    def test_windows_invalid_chars_rejected(self):
        # Sin validacion, estos disparan un OSError WinError 123 no atrapado
        # (traceback feo). Se rechazan limpiamente antes de tocar el FS.
        for ch in (":", "*", "?", '"', "<", ">", "|"):
            self.assertIsNotNone(init_skill.validate_name(f"bad{ch}"))

    def test_error_message_mentions_name(self):
        msg = init_skill.validate_name("../../evil")
        self.assertIn("../../evil", msg)


class TestMainScaffold(unittest.TestCase):
    """Camino feliz: crea subdirectorios + index.md, exit 0."""

    def test_creates_four_subdirs_and_index(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err = run_main(["--name", "myskill", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 0)
            self.assertEqual(err, "")
            self.assertIn("creado", out)
            base = Path(d) / "myskill"
            for sub in ("subskills", "mental_models", "failure_modes", "tools"):
                self.assertTrue((base / sub).is_dir(), f"falta subdirectorio {sub}")
            self.assertTrue((base / "index.md").is_file())

    def test_index_md_frontmatter_has_required_fields(self):
        # skill_index requiere id, type, domain_type (validate_contracts.REQUIRED_FIELDS).
        with tempfile.TemporaryDirectory() as d:
            run_main(["--name", "news", "--domain-type", "ai_mediated", "--root", d])
            text = (Path(d) / "news" / "index.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---"))
            data, err = vc.parse_frontmatter(Path(d) / "news" / "index.md")
            self.assertIsNone(err)
            self.assertEqual(data["id"], "news")
            self.assertEqual(data["type"], "skill_index")
            self.assertEqual(data["domain_type"], "ai_mediated")

    def test_index_md_uses_name_and_domain_type_in_template(self):
        with tempfile.TemporaryDirectory() as d:
            run_main(["--name", "foo", "--domain-type", "cognitive_abstract", "--root", d])
            text = (Path(d) / "foo" / "index.md").read_text(encoding="utf-8")
            self.assertIn("domain_type: cognitive_abstract", text)
            self.assertIn("# foo", text)

    def test_generated_skill_passes_validate_contracts(self):
        # Contrato implicito entre init_skill y validate_contracts: el scaffold
        # generado nace valido. End-to-end: generar + validar en temp.
        with tempfile.TemporaryDirectory() as d:
            run_main(["--name", "news", "--domain-type", "ai_mediated", "--root", d])
            contracts = Path(d) / "contracts"
            contracts.mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vc.main(["validate_contracts.py", str(Path(d)), str(contracts)])
            self.assertEqual(rc, 0, buf.getvalue())
            self.assertIn("1 nodo", buf.getvalue())

    def test_three_domain_types_all_accepted(self):
        for dt in ("physical", "ai_mediated", "cognitive_abstract"):
            with tempfile.TemporaryDirectory() as d:
                rc, out, err = run_main(["--name", f"s_{dt}", "--domain-type", dt, "--root", d])
                self.assertEqual(rc, 0, f"{dt}: {err}")
                self.assertEqual(err, "")


class TestNoOverwrite(unittest.TestCase):
    """Si index.md ya existe, rc=1 y no se sobrescribe."""

    def test_existing_index_returns_1(self):
        with tempfile.TemporaryDirectory() as d:
            run_main(["--name", "dupe", "--domain-type", "physical", "--root", d])
            rc, out, err = run_main(["--name", "dupe", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 1)
            self.assertIn("ya existe", out)
            self.assertEqual(err, "")

    def test_existing_index_content_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            run_main(["--name", "dupe", "--domain-type", "physical", "--root", d])
            idx = Path(d) / "dupe" / "index.md"
            original = idx.read_text(encoding="utf-8")
            # segunda corrida con domain_type distinto: no debe mutar el archivo
            run_main(["--name", "dupe", "--domain-type", "ai_mediated", "--root", d])
            self.assertEqual(idx.read_text(encoding="utf-8"), original)

    def test_collision_with_real_skill_name_pattern(self):
        # Simula colisionar con un nombre ya existente en knowledge/ (ukulele,
        # n8n) pero en un root temporal. Debe respetar el "no sobrescribe".
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "ukulele"
            base.mkdir()
            (base / "index.md").write_text("ORIGINAL_PROTECTED", encoding="utf-8")
            rc, out, err = run_main(["--name", "ukulele", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 1)
            self.assertEqual((base / "index.md").read_text(encoding="utf-8"),
                             "ORIGINAL_PROTECTED")

    def test_subdirs_recreated_idempotently_on_existing_skill(self):
        # Hallazgo B (no es bug, es tolerable): el mkdir de los 4 subdirs ocurre
        # ANTES del chequeo de index.md. Sobre una skill existente, los subdirs
        # se re-crean (exist_ok=True, idempotente) y el index.md queda intacto.
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "dupe"
            run_main(["--name", "dupe", "--domain-type", "physical", "--root", d])
            # borrarmos un subdir a mano para simular un estado inconsistente
            import shutil
            shutil.rmtree(base / "tools")
            self.assertFalse((base / "tools").exists())
            rc, out, err = run_main(["--name", "dupe", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 1)  # ya existe -> 1
            # el subdir faltante se re-crea (autocura idempotente), index.md intacto
            self.assertTrue((base / "tools").is_dir())
            self.assertIn("# dupe", (base / "index.md").read_text(encoding="utf-8"))


class TestInvalidNameViaMain(unittest.TestCase):
    """Nombres invalidos via main: rc=2, mensaje limpio, NADA creado en root."""

    def _assert_rejected_clean(self, name):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err = run_main(["--name", name, "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 2, f"{name!r} deberia rc=2, vino {rc}")
            self.assertNotEqual(err, "")  # mensaje de error a stderr
            self.assertNotIn("creado", out)  # no reporta exito
            # nada creado bajo el root
            self.assertEqual(os.listdir(d), [],
                             f"{name!r} creo entradas en el root: {os.listdir(d)}")

    def test_empty_name_no_contamination(self):
        self._assert_rejected_clean("")

    def test_dot_name_no_contamination(self):
        self._assert_rejected_clean(".")

    def test_dotdot_name_no_contamination(self):
        self._assert_rejected_clean("..")

    def test_traversal_no_escape(self):
        # Sin validacion, ../../evil escribe index.md FUERA del root con rc=0.
        # Ahora se rechaza y el root queda vacio.
        with tempfile.TemporaryDirectory() as d:
            rc, out, err = run_main(["--name", "../../evil", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 2)
            self.assertEqual(os.listdir(d), [])
            # y nada dos niveles arriba del root
            self.assertFalse((Path(d) / ".." / ".." / "evil").exists())

    def test_slash_in_name_rejected(self):
        self._assert_rejected_clean("con/barra")

    def test_backslash_in_name_rejected(self):
        self._assert_rejected_clean("a\\b")

    def test_windows_invalid_char_rejected_no_traceback(self):
        # Sin validacion esto disparaba un OSError WinError 123 no atrapado.
        for ch in (":", "*", "?", '"', "<", ">", "|"):
            with self.subTest(ch=ch):
                with tempfile.TemporaryDirectory() as d:
                    rc, out, err = run_main(["--name", f"bad{ch}", "--domain-type", "physical", "--root", d])
                    self.assertEqual(rc, 2)
                    self.assertNotIn("Traceback", err)
                    self.assertEqual(os.listdir(d), [])


class TestExitCodesAndInterface(unittest.TestCase):
    """Exit codes coherentes y CLI sin cambios."""

    def test_success_exit_zero(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, _ = run_main(["--name", "x", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 0)

    def test_already_exists_exit_one(self):
        with tempfile.TemporaryDirectory() as d:
            run_main(["--name", "x", "--domain-type", "physical", "--root", d])
            rc, _, _ = run_main(["--name", "x", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 1)

    def test_invalid_name_exit_two(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, _ = run_main(["--name", "", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 2)

    def test_missing_required_args_exits_nonzero(self):
        # --name y --domain-type son required; argparse exit 2 si faltan.
        rc, _, _ = run_main(["--root", "ignored"])
        self.assertNotEqual(rc, 0)

    def test_invalid_domain_type_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, _ = run_main(["--name", "x", "--domain-type", "bogus", "--root", d])
            self.assertNotEqual(rc, 0)

    def test_default_root_is_knowledge(self):
        # El flag --root sigue existiendo y su default sigue siendo "knowledge".
        # Verifico el default sin tocar el knowledge/ real: chdir a un temp.
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            try:
                os.chdir(d)
                rc, out, err = run_main(["--name", "x", "--domain-type", "physical"])
                self.assertEqual(rc, 0)
                self.assertTrue((Path(d) / "knowledge" / "x" / "index.md").is_file())
            finally:
                os.chdir(old)


class TestConfirmSFixes(unittest.TestCase):
    """Cobertura de los bugs confirmados en reports/CONFIRM-O-REPORT.md para
    scripts/init_skill.py (fix S, severidad BAJA): nombres de dispositivo
    reservados de Windows (BUG 11), punto/espacio final (BUG 12) y --root
    apuntando a un archivo (BUG 13). Una clase agrupada, sin tocar los
    oraculos congelados existentes."""

    def _assert_rejected_clean(self, name):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err = run_main(["--name", name, "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 2, f"{name!r} deberia rc=2, vino {rc}")
            self.assertNotEqual(err, "")
            self.assertNotIn("creado", out)
            self.assertEqual(os.listdir(d), [],
                             f"{name!r} creo entradas en el root: {os.listdir(d)}")
            return err

    # --- BUG 11: nombres de dispositivo reservados de Windows ---

    def test_reserved_device_names_rejected(self):
        for nm in ("CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"):
            with self.subTest(nm=nm):
                self.assertIsNotNone(init_skill.validate_name(nm), f"{nm!r} deberia rechazarse")

    def test_reserved_device_names_case_insensitive(self):
        for nm in ("con", "prn", "aux", "nul", "com1", "lpt9", "Con", "AuX"):
            with self.subTest(nm=nm):
                self.assertIsNotNone(init_skill.validate_name(nm), f"{nm!r} deberia rechazarse")

    def test_reserved_device_names_with_extension_rejected(self):
        # CON.txt, con.md, PRN.md son reservados igual que sin extension:
        # Windows mira la base antes del primer punto.
        for nm in ("CON.txt", "con.md", "PRN.md", "NUL.log", "COM1.dat", "lpt1.bak"):
            with self.subTest(nm=nm):
                self.assertIsNotNone(init_skill.validate_name(nm), f"{nm!r} deberia rechazarse")

    def test_reserved_device_name_rejected_via_main_clean(self):
        for nm in ("CON", "con", "PRN", "COM1"):
            with self.subTest(nm=nm):
                err = self._assert_rejected_clean(nm)
                self.assertNotIn("Traceback", err)

    def test_com10_lpt10_NOT_reserved(self):
        # Solo COM1-COM9 y LPT1-LPT9 son reservados; COM10/LPT10 son nombres
        # validos. Verificar que NO se rechazan por la regla de reservados.
        for nm in ("COM10", "LPT10"):
            with self.subTest(nm=nm):
                self.assertIsNone(init_skill.validate_name(nm), f"{nm!r} no deberia rechazarse")

    def test_reserved_error_message_mentions_inclonable(self):
        msg = init_skill.validate_name("CON")
        self.assertIn("reservado", msg)
        self.assertIn("inclonable", msg)

    # --- BUG 12: punto o espacio final ---

    def test_trailing_dot_rejected(self):
        for nm in ("news.", "v1.", "a.", "news.."):
            with self.subTest(nm=nm):
                self.assertIsNotNone(init_skill.validate_name(nm), f"{nm!r} deberia rechazarse")

    def test_trailing_space_rejected(self):
        for nm in ("news ", "a ", "news  "):
            with self.subTest(nm=nm):
                self.assertIsNotNone(init_skill.validate_name(nm), f"{nm!r} deberia rechazarse")

    def test_trailing_dot_via_main_clean(self):
        err = self._assert_rejected_clean("news.")
        self.assertNotIn("Traceback", err)

    def test_trailing_space_via_main_clean(self):
        err = self._assert_rejected_clean("news ")
        self.assertNotIn("Traceback", err)

    def test_internal_dot_still_accepted(self):
        # v1.2 CONTIENE un punto pero NO termina en punto: debe seguir siendo
        # aceptado (comportamiento pre-existente que NO se cambia). Verificado
        # antes del fix: validate_name('v1.2') -> None.
        self.assertIsNone(init_skill.validate_name("v1.2"))
        self.assertIsNone(init_skill.validate_name("v1.2.3"))
        self.assertIsNone(init_skill.validate_name("foo-bar.baz"))

    def test_trailing_dot_error_message_explains_why(self):
        msg = init_skill.validate_name("news.")
        self.assertIn("termina", msg)
        # explica la causa (el OS normaliza) y el efecto (diverge del id)
        self.assertTrue("normaliza" in msg or "strips" in msg, msg)

    # --- BUG 13: --root apuntando a un archivo ---

    def test_root_is_file_exit_two_no_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            archivo = Path(d) / "soyarchivo.txt"
            archivo.write_text("x", encoding="utf-8")
            rc, out, err = run_main(["--name", "news", "--domain-type", "physical",
                                     "--root", str(archivo)])
            self.assertEqual(rc, 2, f"deberia rc=2, vino {rc}")
            self.assertNotIn("Traceback", err)
            self.assertIn("archivo", err)
            # no se reporta exito ni se crea nada dentro del archivo
            self.assertNotIn("creado", out)

    def test_root_nonexistent_dir_still_created(self):
        # --root a ruta inexistente sigue creandola (comportamiento intencional,
        # CONFIRM-O R9): no se rompe con el nuevo chequeo de archivo.
        with tempfile.TemporaryDirectory() as d:
            rc, out, err = run_main(["--name", "news", "--domain-type", "physical",
                                     "--root", str(Path(d) / "nuevo" / "sub")])
            self.assertEqual(rc, 0, err)
            self.assertIn("creado", out)


class TestSharedScaffold(unittest.TestCase):
    """init_skill tambien crea <root>/shared/{mental_models,failure_modes,tools}/.

    shared/ cuelga de --root (es hermano de <skill>/), NO de <root>/<skill>/. Ver
    docs/REFERENCIA.md "Reutilizacion entre habilidades". Es idempotente (exist_ok=True) y no
    pisa nada existente. Directorios vacios no aportan nodos a validate_contracts y
    git no los trackea, asi que crearlos no rompe nada.
    """

    def test_creates_shared_three_subdirs_at_root(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err = run_main(["--name", "myskill", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 0, err)
            shared = Path(d) / "shared"
            for sub in ("mental_models", "failure_modes", "tools"):
                self.assertTrue((shared / sub).is_dir(), f"falta shared/{sub}")
            # NO hay subskills/ dentro de shared: solo los 3 genericos.
            self.assertFalse((shared / "subskills").exists(),
                             "shared/ no deberia tener subskills/ (especifico de skill)")

    def test_shared_is_sibling_of_skill_not_inside(self):
        with tempfile.TemporaryDirectory() as d:
            run_main(["--name", "myskill", "--domain-type", "physical", "--root", d])
            # shared es hermano de myskill, cuelga de <root>:
            self.assertTrue((Path(d) / "shared").is_dir())
            # y NO cuelga de myskill:
            self.assertFalse((Path(d) / "myskill" / "shared").exists(),
                             "shared/ se creo DENTRO de <skill>/; debe colgar de <root>")

    def test_shared_idempotent_does_not_preset_existing(self):
        # Si shared/ ya existe con contenido, no se pisa.
        with tempfile.TemporaryDirectory() as d:
            shared_mm = Path(d) / "shared" / "mental_models"
            shared_mm.mkdir(parents=True)
            marker = shared_mm / "ancla_metrónomo.md"
            marker.write_text("ORIGINAL", encoding="utf-8")
            rc, out, err = run_main(["--name", "myskill", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 0, err)
            self.assertEqual(marker.read_text(encoding="utf-8"), "ORIGINAL")
            # los otros dos subdirs se crean igual
            self.assertTrue((Path(d) / "shared" / "failure_modes").is_dir())
            self.assertTrue((Path(d) / "shared" / "tools").is_dir())

    def test_shared_recreated_idempotently_on_existing_skill(self):
        # Sobre una skill existente (rc=1 por index ya existente), shared/ sigue
        # re-creandose idempotente, igual que los subdirs de la skill.
        with tempfile.TemporaryDirectory() as d:
            run_main(["--name", "dupe", "--domain-type", "physical", "--root", d])
            import shutil
            shutil.rmtree(Path(d) / "shared" / "tools")
            self.assertFalse((Path(d) / "shared" / "tools").exists())
            rc, out, err = run_main(["--name", "dupe", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 1)  # ya existe -> 1, index intacto
            self.assertTrue((Path(d) / "shared" / "tools").is_dir())  # autocura

    def test_generated_skill_with_shared_passes_validate_contracts(self):
        # shared/ vacio no aporta nodos: la skill generada sigue validando y el
        # conteo de nodos no cambia por la presencia de shared/.
        with tempfile.TemporaryDirectory() as d:
            run_main(["--name", "news", "--domain-type", "ai_mediated", "--root", d])
            contracts = Path(d) / "contracts"
            contracts.mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vc.main(["validate_contracts.py", str(Path(d)), str(contracts)])
            self.assertEqual(rc, 0, buf.getvalue())
            self.assertIn("1 nodo", buf.getvalue())  # solo el index.md, shared no suma

    def test_shared_not_created_when_name_rejected(self):
        # shared/ se crea DESPUES de validar el nombre: un nombre invalido no debe
        # dejar shared/ (ni nada) en el root.
        with tempfile.TemporaryDirectory() as d:
            rc, out, err = run_main(["--name", "", "--domain-type", "physical", "--root", d])
            self.assertEqual(rc, 2)
            self.assertFalse((Path(d) / "shared").exists(),
                             "shared/ se creo pese a nombre invalido")
            self.assertEqual(os.listdir(d), [])


class TestRootVacioFijado(unittest.TestCase):
    """FIX-ROOT-VACIO: --root vacio o solo espacios se rechaza (exit 2) y NADA
    se crea en el cwd. La trampa es que Path("") / <name> resuelve a <name>
    relativo al cwd, asi que el scaffold se creaba SILENCIOSAMENTE en el
    directorio actual con exit 0 y mensaje de exito. Mismo principio que los
    demas rechazos de este script: el script hacia algo DISTINTO de lo pedido,
    en silencio. Ver reports/FIX-ROOT-VACIO-REPORT.md.

    Importante: --root "." y --root "./" son invocaciones LEGITIMAS (crear
    explicitamente en el cwd) y DEBEN seguir funcionando. La diferencia con el
    string vacio es que ahi la persona lo pidio; con "", no. Todos los casos
    que crean cosas usan un directorio temporal como cwd, NUNCA el repo real.
    """

    def test_root_empty_rejected_exit_two_no_contamination(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            try:
                os.chdir(d)  # cwd es el temp; el scaffold contaminaria aca
                rc, out, err = run_main(["--name", "x", "--domain-type", "physical",
                                         "--root", ""])
                self.assertEqual(rc, 2, f"deberia rc=2, vino {rc}")
                self.assertNotEqual(err, "")  # mensaje claro a stderr
                self.assertNotIn("creado", out)  # no reporta exito
                # NADA creado en el cwd (no solo por el exit code: listando)
                self.assertEqual(os.listdir(d), [],
                                 f"--root '' creo entradas en el cwd: {os.listdir(d)}")
            finally:
                os.chdir(old)

    def test_root_whitespace_only_rejected_exit_two(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            try:
                os.chdir(d)
                rc, out, err = run_main(["--name", "x", "--domain-type", "physical",
                                         "--root", "   "])
                self.assertEqual(rc, 2, f"deberia rc=2, vino {rc}")
                self.assertNotEqual(err, "")
                self.assertNotIn("creado", out)
                self.assertEqual(os.listdir(d), [],
                                 f"--root '   ' creo entradas en el cwd: {os.listdir(d)}")
            finally:
                os.chdir(old)

    def test_root_dot_still_works_creates_in_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            try:
                os.chdir(d)
                rc, out, err = run_main(["--name", "y", "--domain-type", "physical",
                                         "--root", "."])
                self.assertEqual(rc, 0, err)
                self.assertIn("creado", out)
                # crea el scaffold explicitamente en el cwd
                self.assertTrue((Path(d) / "y" / "index.md").is_file())
                self.assertTrue((Path(d) / "shared" / "tools").is_dir())
            finally:
                os.chdir(old)

    def test_root_dot_slash_still_works_creates_in_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            try:
                os.chdir(d)
                rc, out, err = run_main(["--name", "z", "--domain-type", "physical",
                                         "--root", "./"])
                self.assertEqual(rc, 0, err)
                self.assertIn("creado", out)
                self.assertTrue((Path(d) / "z" / "index.md").is_file())
                self.assertTrue((Path(d) / "shared" / "tools").is_dir())
            finally:
                os.chdir(old)

    def test_root_empty_error_message_is_clear(self):
        # El mensaje debe explicar el problema y sugerir '.' como alternativa legitima.
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            try:
                os.chdir(d)
                rc, out, err = run_main(["--name", "x", "--domain-type", "physical",
                                         "--root", ""])
                self.assertIn("root", err)
                self.assertIn("vacio", err)
                # menciona la alternativa legitima para no dejar al usuario atascado
                self.assertIn(".", err)
            finally:
                os.chdir(old)


class TestRealProjectUncontaminated(unittest.TestCase):
    """El knowledge/ real del proyecto no debe tener skills de test."""

    def test_no_test_skill_in_real_knowledge(self):
        # Nombres que este suite podria llegar a crear por error en knowledge/.
        # Deliberadamente NO se listan nombres genericos como "news", "foo" o
        # "x": son slugs plausibles para una skill real, y la guarda acusaria
        # "contaminacion" por un uso legitimo del sistema. Solo se vigilan
        # nombres inequivocamente de test.
        for name in ("myskill", "dupe", "ukulele_test", "evil", "s_physical"):
            self.assertFalse((ROOT / "knowledge" / name).exists(),
                            f"contaminacion: knowledge/{name} existe")


if __name__ == "__main__":
    unittest.main(verbosity=2)