"""Oracle para scripts/commitment_status.py.

Black-box sobre main() con logs y contratos en directorios temporales.
NUNCA toca logs/progress.md real (evidencia append-only) ni knowledge/ ni
contracts/ reales. stdlib solamente: unittest + tempfile + io + contextlib.

Las fechas se construyen relativas a date.today() para que los conteos
(dias transcurridos, restantes, hace cuantos dias la ultima) sean
deterministas sin inyectar un reloj: el script usa date.today() y los
fixtures usan el mismo date.today(), asi pasa cualquier dia.
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

# Hacer importable el modulo scripts/commitment_status.py
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import commitment_status as cs  # noqa: E402


def _contract(nid, skill, status, baseline, checkpoint, extra=None):
    """Frontmatter minimo de un skill_contract. extra anade/sobreescribe."""
    data = {
        "id": nid,
        "type": "skill_contract",
        "skill": skill,
        "status": status,
        "baseline_date": baseline,
        "checkpoint_date": checkpoint,
        "instrument_frozen": "true",
        "criterio": "x",
    }
    if extra:
        data.update(extra)
    lines = ["---"]
    for k, v in data.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append("## Compromiso de prueba.")
    return "\n".join(lines) + "\n"


def _write_contracts(specs):
    """Crea un dir temporal con contratos. specs: lista de (subpath, content).
    Devuelve el Path del root temporal."""
    root = Path(tempfile.mkdtemp(prefix="cs_test_"))
    for subpath, content in specs:
        p = root / subpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _run(log_lines, contract_specs, extra_roots=None, logname="progress.md"):
    """Escribe un log temporal + arbol de contratos temporal, corre cs.main.
    Devuelve (rc, stdout). log_lines se unen con newline."""
    root = _write_contracts(contract_specs)
    fd, logpath = tempfile.mkstemp(suffix=".md", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines) + "\n")
        argv = ["commitment_status", logpath, str(root)]
        if extra_roots:
            argv += [str(r) for r in extra_roots]
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cs.main(argv)
        return rc, buf.getvalue()
    finally:
        os.remove(logpath)


def _ev_line(skill, day, notes='"ok"'):
    """Linea de evidencia del log para un skill en un dia dado (date)."""
    return (
        f"{day.isoformat()}T18:00:00 | skill={skill} | subskill=s "
        f'| session=x | event=attempted | result=partial | notes={notes}'
    )


TODAY = date.today()


class CommitmentStatusTests(unittest.TestCase):

    # --- contrato active con evidencia reciente -> conteos correctos, sin avisos, exit 0 ---

    def test_active_con_evidencia_hoy_conteos_correctos_sin_avisos(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", "", _ev_line("ukulele", TODAY)],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("compromiso 'c' (skill: ukulele)", out)
        self.assertIn("ventana: {} -> {} (30 dias)".format(
            baseline.isoformat(), checkpoint.isoformat()), out)
        self.assertIn("transcurridos: 0 dias | restantes: 30 dias", out)
        self.assertIn("evidencia desde baseline: 1 sesion(es)", out)
        self.assertIn("ultima sesion: {} (hace 0 dias)".format(
            TODAY.isoformat()), out)
        self.assertNotIn("AVISOS", out)
        self.assertIn("OK: 1 compromiso(s) activo(s) reportado(s)", out)

    # --- contrato active sin ninguna evidencia desde el baseline -> aviso, exit 0 ---

    def test_active_sin_evidencia_aviso_exit_0(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log vacio de evidencia", ""],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("evidencia desde baseline: 0 sesion(es)", out)
        self.assertIn("ultima sesion: ninguna desde el baseline", out)
        self.assertIn("AVISOS: 1", out)
        self.assertIn("sin evidencia desde el baseline", out)
        # checkpoint NO pasado -> solo el aviso de sin evidencia
        self.assertNotIn("ya paso y el contrato sigue en active", out)

    # --- checkpoint_date ya pasado con contrato aun active -> aviso, exit 0 ---

    def test_checkpoint_pasado_con_active_aviso_exit_0(self):
        baseline = TODAY - timedelta(days=40)
        checkpoint = TODAY - timedelta(days=10)
        rc, out = _run(
            ["# Log", "", _ev_line("ukulele", TODAY - timedelta(days=20))],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("AVISOS: 1", out)
        self.assertIn("ya paso y el contrato sigue en active", out)
        self.assertIn("la ventana se cerro sin registrar el checkpoint", out)
        # hay evidencia -> no dispara el aviso de sin evidencia
        self.assertNotIn("sin evidencia desde el baseline", out)

    def test_checkpoint_pasado_y_sin_evidencia_dos_avisos(self):
        # Ambas condiciones a la vez: ventana cerrada Y sin evidencia -> 2 avisos.
        baseline = TODAY - timedelta(days=40)
        checkpoint = TODAY - timedelta(days=10)
        rc, out = _run(
            ["# Log sin evidencia", ""],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("AVISOS: 2", out)

    # --- contrato en draft y en checkpoint_done -> omitidos y contados ---

    def test_draft_y_checkpoint_done_se_omiten_y_cuentan(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", ""],
            [
                ("contracts/skill/draft.md",
                 _contract("draft-c", "ukulele", "draft",
                           baseline.isoformat(), checkpoint.isoformat())),
                ("contracts/skill/done.md",
                 _contract("done-c", "ukulele", "checkpoint_done",
                           baseline.isoformat(), checkpoint.isoformat())),
            ],
        )
        self.assertEqual(rc, 0)
        self.assertIn("no hay compromisos activos", out)
        self.assertIn("2 contratos no-active omitidos", out)
        # los omitidos no se reportan como bloque de compromiso
        self.assertNotIn("compromiso 'draft-c'", out)
        self.assertNotIn("compromiso 'done-c'", out)

    def test_un_omitido_mensaje_singular(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", ""],
            [("contracts/skill/draft.md",
              _contract("draft-c", "ukulele", "draft",
                        baseline.isoformat(), checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("1 contrato no-active omitido", out)

    def test_active_y_omitido_conviven(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", "", _ev_line("ukulele", TODAY)],
            [
                ("contracts/skill/act.md",
                 _contract("act", "ukulele", "active",
                           baseline.isoformat(), checkpoint.isoformat())),
                ("contracts/skill/draft.md",
                 _contract("draft", "ukulele", "draft",
                           baseline.isoformat(), checkpoint.isoformat())),
            ],
        )
        self.assertEqual(rc, 0)
        self.assertIn("compromiso 'act'", out)
        self.assertIn("1 contrato no-active omitido", out)

    # --- evidencia ANTERIOR al baseline_date -> NO cuenta ---

    def test_evidencia_anterior_al_baseline_no_cuenta(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        # una linea anterior al baseline y una el dia del baseline
        rc, out = _run(
            ["# Log",
             _ev_line("ukulele", TODAY - timedelta(days=5)),
             _ev_line("ukulele", TODAY)],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("evidencia desde baseline: 1 sesion(es)", out)
        self.assertIn("ultima sesion: {} (hace 0 dias)".format(
            TODAY.isoformat()), out)

    def test_evidencia_toda_anterior_al_baseline_dispara_aviso(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", _ev_line("ukulele", TODAY - timedelta(days=5))],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("evidencia desde baseline: 0 sesion(es)", out)
        self.assertIn("AVISOS: 1", out)
        self.assertIn("sin evidencia desde el baseline", out)

    # --- evidencia de OTRA skill -> no cuenta ---

    def test_evidencia_de_otra_skill_no_cuenta(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", _ev_line("bateria", TODAY)],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("evidencia desde baseline: 0 sesion(es)", out)
        self.assertIn("AVISOS: 1", out)
        self.assertIn("sin evidencia desde el baseline", out)

    # --- una nota con pipes que contenga skill= -> no se cuela como evidencia ---
    # Regresion del bug ya cerrado en adherence.py / validate_evidence.py:
    # notes= es TERMINAL, el skill= dentro de la nota no pisa ni inyecta.

    def test_notes_con_pipes_y_skill_no_cuela_evidencia_falsa(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        # La linea es de skill=bateria, pero la nota menciona skill=ukulele.
        # El contrato es de ukulele: la nota NO debe colarse como evidencia de
        # ukulele. Resultado: 0 sesiones para ukulele -> aviso.
        rc, out = _run(
            ['# Log',
             '2026-07-28T18:00:00 | skill=bateria | event=attempted '
             '| notes="compare con skill=ukulele de ayer"'],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("evidencia desde baseline: 0 sesion(es)", out)
        self.assertIn("AVISOS: 1", out)
        # la evidencia real de ukulele seria la del baseline; forzamos una
        # linea real de ukulele el dia de hoy para que el conteo no sea 0 por
        # la nota y si sea 0 por ausencia real -> ya cubierto arriba. Aca
        # confirmamos que la nota sola no genera una sesion fantasma.

    def test_notes_con_skill_no_pisa_skill_real_valido(self):
        # Linea real de skill=ukulele (hoy); la nota inyecta skill=otro.
        # El conteo para ukulele debe ser 1, no 0 (la nota no pisa el real).
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ['# Log',
             '{} | skill=ukulele | event=attempted '
             '| notes="x | skill=otro"'.format(TODAY.isoformat() + "T18:00:00")],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("evidencia desde baseline: 1 sesion(es)", out)
        self.assertNotIn("AVISOS", out)

    # --- log inexistente -> exit 1 ---

    def test_log_inexistente_exit_1(self):
        root = _write_contracts([
            ("contracts/skill/c.md",
             _contract("c", "ukulele", "active",
                       TODAY.isoformat(), (TODAY + timedelta(days=30)).isoformat())),
        ])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cs.main([
                "commitment_status",
                os.path.join(tempfile.gettempdir(), "no_existe_12345.md"),
                str(root),
            ])
        self.assertEqual(rc, 1)
        self.assertIn("no existe", buf.getvalue())

    # --- argumentos faltantes -> exit 1 ---

    def test_args_insuficientes_exit_1(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cs.main(["commitment_status", "algo.md"])
        self.assertEqual(rc, 1)
        self.assertIn("uso:", buf.getvalue())

    def test_args_sin_nada_exit_1(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cs.main(["commitment_status"])
        self.assertEqual(rc, 1)
        self.assertIn("uso:", buf.getvalue())

    # --- directorio inexistente -> exit 1 (fallo operativo) ---

    def test_dir_inexistente_exit_1(self):
        fd, logpath = tempfile.mkstemp(suffix=".md", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("# Log\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cs.main([
                    "commitment_status", logpath,
                    os.path.join(tempfile.gettempdir(), "dir_que_no_existe_12345"),
                ])
            self.assertEqual(rc, 1)
            self.assertIn("no existe", buf.getvalue())
        finally:
            os.remove(logpath)

    # --- multiples directorios se combinan (knowledge + contracts) ---

    def test_multiples_dirs_se_combinan(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        root = _write_contracts([
            ("contracts/skill/c.md",
             _contract("c", "ukulele", "active", baseline.isoformat(),
                       checkpoint.isoformat())),
        ])
        # otro root con un contrato active de otra skill
        other = _write_contracts([
            ("mas/d.md",
             _contract("d", "bateria", "active", baseline.isoformat(),
                       checkpoint.isoformat())),
        ])
        rc, out = _run(
            ["# Log", _ev_line("ukulele", TODAY), _ev_line("bateria", TODAY)],
            [],  # no usa el root por defecto; pasamos los dos explicitos abajo
            extra_roots=[root, other],
        )
        # _run con [] crea un root vacio y lo pasa primero; los contratos estan
        # en root y other. Pasar ambos resuelve los dos compromisos activos.
        self.assertEqual(rc, 0)
        self.assertIn("compromiso 'c'", out)
        self.assertIn("compromiso 'd'", out)
        self.assertIn("OK: 2 compromiso(s) activo(s) reportado(s)", out)

    # --- nodos que no son skill_contract se ignoran (no cuentan como omitidos) ---

    def test_nodos_no_skill_contract_se_ignoran_no_cuentan(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        subskill = (
            "---\nid: chord-transitions\ntype: subskill\nskill: ukulele\n"
            "domain_type: physical\nverification_type: proxy\nstatus: draft\n"
            "---\n\n## subskill\n"
        )
        rc, out = _run(
            ["# Log", _ev_line("ukulele", TODAY)],
            [
                ("contracts/skill/c.md",
                 _contract("c", "ukulele", "active", baseline.isoformat(),
                           checkpoint.isoformat())),
                ("knowledge/ukulele/subskills/chord-transitions.md", subskill),
            ],
        )
        self.assertEqual(rc, 0)
        # el subskill no es contrato -> no cuenta como omitido
        self.assertNotIn("omitido", out)
        self.assertIn("OK: 1 compromiso(s) activo(s) reportado(s)", out)

    # --- contratos se ordenan por id ---

    def test_contratos_ordenados_por_id(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", _ev_line("ukulele", TODAY), _ev_line("bateria", TODAY)],
            [
                ("contracts/skill/zzz.md",
                 _contract("zzz", "bateria", "active", baseline.isoformat(),
                           checkpoint.isoformat())),
                ("contracts/skill/aaa.md",
                 _contract("aaa", "ukulele", "active", baseline.isoformat(),
                           checkpoint.isoformat())),
            ],
        )
        self.assertEqual(rc, 0)
        self.assertLess(out.index("compromiso 'aaa'"), out.index("compromiso 'zzz'"))

    # --- la fecha del timestamp se compara por DIA contra baseline_date ---

    def test_evidencia_mismo_dia_que_baseline_cuenta(self):
        # timestamp con hora, mismo dia que baseline -> cuenta (>= por dia).
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", _ev_line("ukulele", TODAY)],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("evidencia desde baseline: 1 sesion(es)", out)


class SinFechaLimiteTests(unittest.TestCase):
    """FEAT-SIN-FECHA-LIMITE: checkpoint_date: null = seguimiento abierto, sin
    fecha limite. Formato nuevo ("seguimiento", "desde", sin "restantes"),
    aviso de checkpoint vencido que NUNCA aplica, y resumen que distingue
    compromisos con ventana de seguimientos abiertos. Clase agrupada, sin
    tocar los oraculos congelados existentes."""

    # --- seguimiento abierto activo con evidencia -> formato nuevo, exit 0 ---

    def test_abierto_con_evidencia_formato_nuevo_sin_restantes(self):
        baseline = TODAY - timedelta(days=12)
        last = TODAY - timedelta(days=2)
        rc, out = _run(
            ["# Log", _ev_line("ukulele", last)],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(), "null"))],
        )
        self.assertEqual(rc, 0)
        # se lee "seguimiento", no "compromiso"
        self.assertIn("seguimiento 'c' (skill: ukulele) -- sin fecha limite", out)
        # dias desde el baseline, evidencia acumulada, ultima sesion
        self.assertIn(f"desde: {baseline.isoformat()} (12 dias)", out)
        self.assertIn("evidencia desde el baseline: 1 sesion(es)", out)
        self.assertIn(f"ultima sesion: {last.isoformat()} (hace 2 dias)", out)
        # no hay ventana ni restantes (no hay fecha tope)
        self.assertNotIn("ventana:", out)
        self.assertNotIn("transcurridos:", out)
        self.assertNotIn("restantes:", out)
        # con evidencia -> sin avisos
        self.assertNotIn("AVISOS", out)

    # --- seguimiento abierto SIN evidencia -> aviso de sin evidencia, exit 0 ---

    def test_abierto_sin_evidencia_aviso_exit_0(self):
        baseline = TODAY
        rc, out = _run(
            ["# Log vacio", ""],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(), "null"))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("seguimiento 'c'", out)
        self.assertIn("evidencia desde el baseline: 0 sesion(es)", out)
        self.assertIn("ultima sesion: ninguna desde el baseline", out)
        # el aviso de sin evidencia SI aplica igual (sigue siendo util)
        self.assertIn("AVISOS: 1", out)
        self.assertIn("sin evidencia desde el baseline", out)
        # y no hay restantes que reportar
        self.assertNotIn("restantes", out)

    # --- el aviso de "checkpoint ya paso" NUNCA se dispara en abiertos ---

    def test_abierto_nunca_dispara_aviso_de_checkpoint_vencido(self):
        # baseline muy atrasado: si tuviera checkpoint, ya estaria vencido.
        # Pero es abierto: no hay fecha tope que pueda pasar -> sin ese aviso.
        baseline = TODAY - timedelta(days=400)
        rc, out = _run(
            ["# Log", _ev_line("ukulele", TODAY)],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(), "null"))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("seguimiento 'c'", out)
        # con evidencia -> 0 avisos; en particular nunca "ya paso"
        self.assertNotIn("AVISOS", out)
        self.assertNotIn("ya paso y el contrato sigue en active", out)
        self.assertNotIn("la ventana se cerro", out)

    def test_abierto_sin_evidencia_tampoco_dispara_checkpoint_vencido(self):
        # even sin evidencia: el unico aviso es el de sin evidencia, nunca el
        # de checkpoint vencido (no puede dispararse en un abierto).
        baseline = TODAY - timedelta(days=400)
        rc, out = _run(
            ["# Log vacio", ""],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(), "null"))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("AVISOS: 1", out)
        self.assertIn("sin evidencia desde el baseline", out)
        self.assertNotIn("ya paso y el contrato sigue en active", out)

    # --- un contrato con ventana conserva su formato de siempre ---

    def test_compromiso_con_ventana_conserva_formato_historico(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", _ev_line("ukulele", TODAY)],
            [("contracts/skill/c.md",
              _contract("c", "ukulele", "active", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        # sigue diciendo "compromiso", no "seguimiento"
        self.assertIn("compromiso 'c' (skill: ukulele)", out)
        self.assertNotIn("seguimiento 'c'", out)
        self.assertIn("ventana: {} -> {} (30 dias)".format(
            baseline.isoformat(), checkpoint.isoformat()), out)
        self.assertIn("transcurridos: 0 dias | restantes: 30 dias", out)
        self.assertIn("evidencia desde baseline: 1 sesion(es)", out)
        # resumen historico exacto (cero abiertos -> sin distincion)
        self.assertIn("OK: 1 compromiso(s) activo(s) reportado(s)", out)
        self.assertNotIn("seguimiento abierto", out)

    # --- la linea de resumen distingue compromisos con ventana de abiertos ---

    def test_resumen_distingue_ventana_y_abierto(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", _ev_line("ukulele", TODAY), _ev_line("bateria", TODAY)],
            [
                ("contracts/skill/win.md",
                 _contract("win", "ukulele", "active", baseline.isoformat(),
                           checkpoint.isoformat())),
                ("contracts/skill/open.md",
                 _contract("open", "bateria", "active", baseline.isoformat(), "null")),
            ],
        )
        self.assertEqual(rc, 0)
        # ambos se reportan
        self.assertIn("compromiso 'win'", out)
        self.assertIn("seguimiento 'open'", out)
        # el resumen nombra los dos tipos con su conteo (1 y 1)
        self.assertIn("1 compromiso con ventana", out)
        self.assertIn("1 seguimiento abierto", out)

    def test_resumen_solo_abiertos_distingue(self):
        # todos abiertos (cero con ventana): el resumen igual lo explicita.
        baseline = TODAY
        rc, out = _run(
            ["# Log", _ev_line("ukulele", TODAY)],
            [("contracts/skill/a.md",
              _contract("a", "ukulele", "active", baseline.isoformat(), "null"))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("0 compromisos con ventana", out)
        self.assertIn("1 seguimiento abierto", out)


class DiscontinuedTests(unittest.TestCase):
    """FEAT-DISCONTINUED: un contrato `discontinued` (estado terminal: el
    compromiso se cerro SIN llegar al checkpoint) se OMITE como draft y
    checkpoint_done y se cuenta en la linea de omitidos. NO genera ningun
    aviso, ni siquiera el de "sin evidencia desde el baseline": la persona ya
    lo cerro, no hay nada que senalarle. Conviviendo con uno active, el active
    se reporta normal y el resumen los cuenta bien. Clase agrupada, sin tocar
    los oraculos congelados existentes."""

    def test_discontinued_se_omite_y_se_cuenta(self):
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", ""],
            [("contracts/skill/d.md",
              _contract("d", "ukulele", "discontinued", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        self.assertIn("no hay compromisos activos", out)
        self.assertIn("1 contrato no-active omitido", out)
        # no se reporta como bloque de compromiso
        self.assertNotIn("compromiso 'd'", out)
        self.assertNotIn("seguimiento 'd'", out)

    def test_discontinued_no_avisa_ni_sin_evidencia(self):
        # contrato discontinued SIN evidencia desde el baseline: el aviso de
        # "sin evidencia" NO se dispara (la persona ya lo cerro).
        baseline = TODAY - timedelta(days=30)
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log vacio", ""],
            [("contracts/skill/d.md",
              _contract("d", "ukulele", "discontinued", baseline.isoformat(),
                        checkpoint.isoformat()))],
        )
        self.assertEqual(rc, 0)
        # el contrato esta omitido: nunca llego a report_contract, asi que no
        # hay avisos derivados de el.
        self.assertNotIn("AVISOS", out)
        self.assertNotIn("sin evidencia desde el baseline", out)
        self.assertIn("1 contrato no-active omitido", out)

    def test_discontinued_con_active_el_active_se_reporta_normal(self):
        # conviven uno discontinued (omitido) y uno active (reportado): el
        # active se reporta con su formato de siempre y el resumen los cuenta.
        baseline = TODAY
        checkpoint = TODAY + timedelta(days=30)
        rc, out = _run(
            ["# Log", "", _ev_line("ukulele", TODAY)],
            [
                ("contracts/skill/act.md",
                 _contract("act", "ukulele", "active", baseline.isoformat(),
                           checkpoint.isoformat())),
                ("contracts/skill/disc.md",
                 _contract("disc", "bateria", "discontinued",
                           baseline.isoformat(), checkpoint.isoformat())),
            ],
        )
        self.assertEqual(rc, 0)
        # el active se reporta normal
        self.assertIn("compromiso 'act' (skill: ukulele)", out)
        self.assertIn("evidencia desde baseline: 1 sesion(es)", out)
        # el discontinued no se reporta ni avisa
        self.assertNotIn("compromiso 'disc'", out)
        self.assertNotIn("seguimiento 'disc'", out)
        # resumen: 1 activo + 1 omitido
        self.assertIn("OK: 1 compromiso(s) activo(s) reportado(s)", out)
        self.assertIn("1 contrato no-active omitido", out)

    def test_discontinued_abierto_tampoco_avisa(self):
        # discontinued con seguimiento abierto (checkpoint null): igual se
        # omite y no avisa. El null solo cambia el formato del reporte, pero un
        # discontinued ni siquiera se reporta.
        baseline = TODAY - timedelta(days=30)
        rc, out = _run(
            ["# Log vacio", ""],
            [("contracts/skill/d.md",
              _contract("d", "ukulele", "discontinued", baseline.isoformat(),
                        "null"))],
        )
        self.assertEqual(rc, 0)
        self.assertNotIn("AVISOS", out)
        self.assertIn("1 contrato no-active omitido", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)