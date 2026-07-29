#!/usr/bin/env python3
"""Tests para scripts/check_instrument_freeze.py (mitad temporal de H2).

Necesitan repos git de verdad: se crean repos temporales con `git init`,
configurando user.email/user.name locales al repo para que los commits funcionen
en cualquier entorno, y commiteando fixtures. Si git no esta disponible en el
entorno de test, los tests que lo requieren se saltean con skipUnless en vez de
fallar.

NUNCA se muta el repo real del proyecto: todos los `git init/add/commit` se
ejecutan sobre directorios temporales creados con TemporaryDirectory.
"""
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_instrument_freeze as cif  # noqa: E402


def git_available():
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True)
        return r.returncode == 0
    except (FileNotFoundError, OSError):
        return False


GIT = git_available()


def _git(repo, *args):
    """Corre un comando git dentro de `repo` (cwd=repos). Solo para repos temp."""
    return subprocess.run(
        ["git", *args], cwd=str(repo),
        capture_output=True, text=True, encoding="utf-8",
    )


def init_repo(repo):
    """git init + user.email/user.name locales al repo (para cualquier entorno)."""
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")


def write_contract(path, *, id_="sc-1", status="active", criterio="X",
                   instrument_frozen_at=None, extra_lines=None):
    """Escribe un skill_contract con frontmatter plano. Devuelve el path."""
    lines = [
        "---",
        f"id: {id_}",
        "type: skill_contract",
        "skill: s",
        "goal: tocar 3 canciones",
        "subskills: []",
        "domain_type: physical",
        "verification_type: proxy",
        f'criterio: "{criterio}"',
        "instrument_frozen: true",
    ]
    if instrument_frozen_at is not None:
        lines.append(f"instrument_frozen_at: {instrument_frozen_at}")
    lines += [
        "baseline_date: 2026-07-28",
        "checkpoint_date: 2026-08-27",
        f"status: {status}",
        "---",
        "",
        "## Compromiso",
        "",
        "body",
    ]
    if extra_lines:
        # inserta lineas extra antes del cerrador ---
        close = lines.index("---", 1)
        for ln in extra_lines:
            lines.insert(close, ln)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def commit_all(repo, msg="m"):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg)
    r = _git(repo, "rev-parse", "HEAD")
    return r.stdout.strip()


def run_main(*roots):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cif.main(["check_instrument_freeze.py", *roots])
    return rc, buf.getvalue()


@unittest.skipUnless(GIT, "git no disponible en este entorno")
class TestInstrumentFreezeGit(unittest.TestCase):
    """Casos que requieren un repo git real."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="cif_"))
        init_repo(self.repo)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _freeze_flow(self, status="active", criterio="X",
                     frozen_criterio=None, use_short_sha=False):
        """Flujo base: commitea el contrato sin el campo (sha1), luego agrega
        instrument_frozen_at apuntando a sha1 y commitea de nuevo (sha2). El
        criterio en sha1 es `frozen_criterio` (por defecto igual al actual)."""
        if frozen_criterio is None:
            frozen_criterio = criterio
        sc = self.repo / "contracts" / "sc.md"
        # commit 1: contrato sin instrument_frozen_at, criterio = frozen_criterio
        write_contract(sc, status=status, criterio=frozen_criterio)
        sha1 = commit_all(self.repo, "freeze")
        # commit 2: agrega el campo apuntando a sha1, criterio sigue igual
        sha_ref = sha1[:7] if use_short_sha else sha1
        write_contract(sc, status=status, criterio=criterio,
                        instrument_frozen_at=sha_ref)
        commit_all(self.repo, "add freeze ref")
        return sc, sha1

    # --- exit 0: criterio sin cambios desde el sha ---
    def test_criterio_unchanged_exit0(self):
        self._freeze_flow(status="active", criterio="secuencia C-G-Am-F 80bpm")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 0, out)
        self.assertIn("OK", out)
        self.assertIn("1 verificado", out)

    # --- exit 1: criterio EDITADO despues del sha, muestra ambos valores ---
    def test_criterio_edited_exit1_shows_both(self):
        frozen = "secuencia C-G-Am-F, 4 repeticiones, 80bpm"
        current = "secuencia C-G-Am-F, 2 repeticiones, 60bpm"
        sc, sha1 = self._freeze_flow(status="active", criterio=current,
                                     frozen_criterio=frozen)
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("FALLO", out)
        self.assertIn("diverge", out)
        self.assertIn(frozen, out)
        self.assertIn(current, out)
        self.assertIn(sha1[:7], out)

    # --- exit 1: contrato active SIN instrument_frozen_at ---
    def test_active_missing_field_exit1(self):
        sc = self.repo / "contracts" / "sc.md"
        write_contract(sc, status="active", criterio="X")  # sin el campo
        commit_all(self.repo, "no field")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("requiere instrument_frozen_at", out)
        self.assertIn("active", out)

    # --- exit 0: contrato draft sin el campo -> omitido ---
    def test_draft_missing_field_omitted_exit0(self):
        sc = self.repo / "contracts" / "sc.md"
        write_contract(sc, status="draft", criterio="X")  # sin el campo
        commit_all(self.repo, "draft no field")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 0, out)
        self.assertIn("1 omitido", out)

    # --- exit 1: draft CON el campo y criterio editado (se honra el opt-in) ---
    def test_draft_with_field_edited_exit1(self):
        frozen = "criterio original del draft"
        current = "criterio editado del draft"
        self._freeze_flow(status="draft", criterio=current,
                          frozen_criterio=frozen)
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("diverge", out)
        self.assertIn(frozen, out)
        self.assertIn(current, out)

    # --- exit 1: sha inexistente ---
    def test_nonexistent_sha_exit1(self):
        sc = self.repo / "contracts" / "sc.md"
        write_contract(sc, status="active", criterio="X",
                       instrument_frozen_at="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        commit_all(self.repo, "bogus sha")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("no es un commit del repo", out)

    # --- exit 1: el archivo no existia en ese commit ---
    def test_file_not_in_commit_exit1(self):
        # commit 1: un archivo distinto (otro path)
        other = self.repo / "contracts" / "otro.md"
        write_contract(other, id_="otro", status="active", criterio="Y")
        sha1 = commit_all(self.repo, "otro")
        # ahora creamos sc.md apuntando a sha1, donde sc.md no existia
        sc = self.repo / "contracts" / "sc.md"
        write_contract(sc, status="active", criterio="X",
                       instrument_frozen_at=sha1)
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("no existia en el commit", out)
        self.assertIn(sha1[:7], out)

    # --- sha corto (7 chars) funciona igual que el largo ---
    def test_short_sha_works(self):
        self._freeze_flow(status="active", criterio="X", use_short_sha=True)
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 0, out)
        self.assertIn("1 verificado", out)

    # --- divergencia sutil de espaciado interno es error (estricto como H2) ---
    def test_subtle_spacing_diff_is_error(self):
        frozen = "secuencia C-G-Am-F, 4 repeticiones, 80bpm"
        current = "secuencia C-G-Am-F,  4 repeticiones, 80bpm"  # doble espacio
        self._freeze_flow(status="active", criterio=current,
                          frozen_criterio=frozen)
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("diverge", out)

    # --- checkpoint_done tambien exige el campo ---
    def test_checkpoint_done_missing_field_exit1(self):
        sc = self.repo / "contracts" / "sc.md"
        write_contract(sc, status="checkpoint_done", criterio="X")
        commit_all(self.repo, "no field")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("requiere instrument_frozen_at", out)
        self.assertIn("checkpoint_done", out)

    # ===== FEAT-DISCONTINUED: discontinued no exige el campo, pero si esta
    # presente se verifica (cerrar no esconde una divergencia que ya existia) =====

    # --- discontinued SIN instrument_frozen_at -> omitido, exit 0 ---
    def test_discontinued_missing_field_omitted_exit0(self):
        sc = self.repo / "contracts" / "sc.md"
        write_contract(sc, status="discontinued", criterio="X")  # sin el campo
        commit_all(self.repo, "discontinued no field")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 0, out)
        self.assertIn("1 omitido", out)
        self.assertNotIn("requiere instrument_frozen_at", out)
        self.assertNotIn("discontinued", out)  # no se queja del status

    # --- discontinued CON el campo y criterio divergente -> sigue reportando
    #     la divergencia (exit 1). Ese es el caso que mas importa: cerrar no
    #     borra lo que ya estaba a la vista. ---
    def test_discontinued_with_field_divergent_exit1(self):
        frozen = "secuencia C-G-Am-F, 4 repeticiones, 80bpm"
        current = "secuencia C-G-Am-F, 2 repeticiones, 60bpm"
        sc, sha1 = self._freeze_flow(status="discontinued", criterio=current,
                                     frozen_criterio=frozen)
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("FALLO", out)
        self.assertIn("diverge", out)
        self.assertIn(frozen, out)
        self.assertIn(current, out)
        self.assertIn(sha1[:7], out)

    # --- discontinued CON el campo y criterio SIN cambios -> verificado, exit 0 ---
    def test_discontinued_with_field_unchanged_exit0(self):
        self._freeze_flow(status="discontinued", criterio="secuencia C-G-Am-F 80bpm")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 0, out)
        self.assertIn("1 verificado", out)

    # ===== BUG #1 (GRAVE, CONFIRM-O): refs moviles deben rechazarse =====
    # El fix anterior valido la FORMA ("algo que git acepta") en vez de la
    # PROPIEDAD (referencia inmutable a un commit). HEAD/rama/tag pasaban como
    # verificadas (exit 0) sin comparar de verdad: el "congelado" seguia al
    # puntero. Ahora se rechazan como defecto del contrato (exit 1).

    # --- HEAD (puntero movil simbolico) -> error ---
    def test_head_mobile_ref_rejected_exit1(self):
        sc = self.repo / "contracts" / "sc.md"
        write_contract(sc, status="active", criterio="X",
                       instrument_frozen_at="HEAD")
        commit_all(self.repo, "freeze via HEAD")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("ref movil", out)
        self.assertIn("HEAD", out)

    # --- nombre de rama (puntero movil) -> error ---
    def test_branch_mobile_ref_rejected_exit1(self):
        # el nombre de la rama default (master o main segun el git); lo que
        # sea, es una rama y por tanto movible.
        branch = _git(self.repo, "symbolic-ref", "--short", "HEAD").stdout.strip()
        self.assertTrue(branch)
        sc = self.repo / "contracts" / "sc.md"
        write_contract(sc, status="active", criterio="X",
                       instrument_frozen_at=branch)
        commit_all(self.repo, "freeze via rama")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("ref movil", out)
        self.assertIn(branch, out)

    # --- tag que apunta al commit CORRECTO -> error igual (es movible) ---
    def test_tag_mobile_ref_rejected_exit1(self):
        sc = self.repo / "contracts" / "sc.md"
        write_contract(sc, status="active", criterio="ORIGINAL")
        commit_all(self.repo, "original")
        _git(self.repo, "tag", "v1.0")  # tag apunta al commit correcto
        write_contract(sc, status="active", criterio="ORIGINAL",
                       instrument_frozen_at="v1.0")
        commit_all(self.repo, "freeze via tag")
        rc, out = run_main(str(self.repo / "contracts"))
        # aunque el tag apunta al commit correcto y el criterio coincide, se
        # rechaza: un tag es movible y derrotaria el congelado igual que HEAD.
        self.assertEqual(rc, 1, out)
        self.assertIn("ref movil", out)
        self.assertIn("v1.0", out)

    # --- sha de 4 chars -> error por ambiguo ---
    def test_short_sha_ambiguous_exit1(self):
        sc = self.repo / "contracts" / "sc.md"
        write_contract(sc, status="active", criterio="X",
                       instrument_frozen_at="abcd")
        commit_all(self.repo, "short sha")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("ambiguo", out)

    # --- sha de 40 chars valido -> funciona ---
    def test_full_sha_works(self):
        self._freeze_flow(status="active", criterio="X")  # sha_ref = sha1 (40)
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 0, out)
        self.assertIn("1 verificado", out)

    # --- sha valido pero de un commit donde el archivo no existia: mensaje
    #     DISTINTO al de "criterio cambio" (un renombre no es cambio de
    #     instrumento). Hereda el trade-off declarado (exit 1) pero distingue
    #     el mensaje. ---
    def test_rename_distinct_from_criterion_change(self):
        other = self.repo / "contracts" / "viejo.md"
        write_contract(other, id_="viejo", status="active", criterio="Y")
        sha1 = commit_all(self.repo, "viejo")
        sc = self.repo / "contracts" / "sc.md"
        write_contract(sc, status="active", criterio="X",
                       instrument_frozen_at=sha1)
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("no existia en el commit", out)
        self.assertNotIn("diverge", out)

    # --- escenario completo de manipulacion: congelar con sha INMUTABLE,
    #     aflojar el criterio y commitear -> exit 1 (detectado). Este es el
    #     contrapeso del repro HEAD: con un sha real el edita+commitea NO pasa
    #     silencioso. ---
    def test_manipulation_with_real_sha_detected_exit1(self):
        sc = self.repo / "contracts" / "sc.md"
        # 1. instrumento definitivo + congela apuntando al sha de ese commit.
        write_contract(sc, status="active", criterio="80bpm, maximo 2 detenciones")
        sha1 = commit_all(self.repo, "instrumento definitivo")
        write_contract(sc, status="active", criterio="80bpm, maximo 2 detenciones",
                       instrument_frozen_at=sha1)
        commit_all(self.repo, "congela apuntando al sha")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 0, out)
        self.assertIn("1 verificado", out)
        # 2. tras ver un resultado malo, afloja la rubrica y COMMITEA.
        write_contract(sc, status="active",
                       criterio="30bpm, detenciones ilimitadas",
                       instrument_frozen_at=sha1)
        commit_all(self.repo, "afloja la rubrica")
        rc, out = run_main(str(self.repo / "contracts"))
        self.assertEqual(rc, 1, out)
        self.assertIn("diverge", out)
        self.assertIn("80bpm, maximo 2 detenciones", out)
        self.assertIn("30bpm, detenciones ilimitadas", out)


@unittest.skipUnless(GIT, "git no disponible en este entorno")
class TestNotARepoExit2(unittest.TestCase):
    """directorio que no es repo git -> exit 2, y el mensaje lo dice."""

    def test_non_git_dir_exit2(self):
        d = Path(tempfile.mkdtemp(prefix="cif_nogit_"))
        try:
            # contrato que requiere verificacion (campo presente) pero el dir
            # no es un repo -> limitacion del entorno, no del contrato.
            sc = d / "contracts" / "sc.md"
            write_contract(sc, status="active", criterio="X",
                           instrument_frozen_at="abc1234")
            rc, out = run_main(str(d / "contracts"))
            self.assertEqual(rc, 2, out)
            self.assertIn("no se pudo verificar", out)
            self.assertIn("repo git", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestParseFrontmatterText(unittest.TestCase):
    """Parser sobre string (no requiere git). Cubre la logica duplicada."""

    def test_scalar_and_list(self):
        text = "---\nid: x\ntype: skill_contract\nsubskills: [a, b]\n---\n"
        data, err = cif.parse_frontmatter_text(text)
        self.assertIsNone(err)
        self.assertEqual(data["id"], "x")
        self.assertEqual(data["subskills"], ["a", "b"])

    def test_no_frontmatter(self):
        data, err = cif.parse_frontmatter_text("sin frontmatter\n")
        self.assertIsNone(data)
        self.assertIn("falta frontmatter", err)

    def test_mal_cerrado(self):
        data, err = cif.parse_frontmatter_text("---\nid: x\nbody sin cerrar\n")
        self.assertIsNone(data)
        self.assertIn("mal cerrado", err)

    def test_quotes_stripped(self):
        text = '---\ncriterio: "tocar bien"\n---\n'
        data, _ = cif.parse_frontmatter_text(text)
        self.assertEqual(data["criterio"], "tocar bien")

    def test_field_present_helper(self):
        self.assertFalse(cif._field_present(None))
        self.assertFalse(cif._field_present(""))
        self.assertFalse(cif._field_present("null"))
        self.assertFalse(cif._field_present("None"))
        self.assertTrue(cif._field_present("abc123"))


class TestRealProject(unittest.TestCase):
    """Caso real: el chequeo de congelado PUEDE VERIFICAR en este proyecto.

    La invariante NO es exit 0. Divergir el criterio de un contrato activo es
    uso legitimo del sistema -- es justamente la senal que el congelado existe
    para emitir -- y deja el chequeo en exit 1 a proposito. Un test que exija
    exit 0 se pone rojo cuando alguien usa la feature que el proyecto defiende.

    Tampoco es el reparto entre verificados y omitidos: depende del punto del
    ciclo de vida del contrato (draft se omite, active se verifica).

    Lo que si debe cumplirse siempre es que el chequeo pueda EJECUTARSE: este
    repo esta versionado, asi que nunca corresponde exit 2 ("no se pudo
    verificar"). Eso separa "el entorno funciona" de "los datos hoy cumplen".
    """

    def test_real_contracts_puede_verificar(self):
        rc, out = run_main(str(ROOT / "contracts"))
        self.assertIn(rc, (0, 1), out)
        self.assertNotEqual(
            rc, 2,
            "exit 2 = no se pudo verificar; este repo es git y siempre deberia poder:\n" + out,
        )


class TestUsage(unittest.TestCase):
    def test_no_args_returns1(self):
        rc, out = run_main()
        self.assertEqual(rc, 1)
        self.assertIn("uso:", out)

    def test_nonexistent_dir_omitted_exit0(self):
        # un directorio que no existe se avisa y se omite; sin contratos -> exit 0
        rc, out = run_main(str(Path(tempfile.gettempdir()) / "cif_no_existe_xyz"))
        self.assertEqual(rc, 0, out)
        self.assertIn("AVISO", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)