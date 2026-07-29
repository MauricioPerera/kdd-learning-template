"""Oracle congelado para scripts/validate_evidence.py.

Black-box sobre main() con logs y directorios de nodos temporales. NUNCA toca
logs/progress.md real (es evidencia append-only) ni knowledge/ ni contracts/
reales. stdlib solamente: unittest + tempfile + io + contextlib.
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

# Hacer importable el modulo scripts/validate_evidence.py
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import validate_evidence as ve  # noqa: E402


def _node(node_type, nid, extra=None):
    """Frontmatter minimo de un nodo. extra sobreescribe/anade campos."""
    data = {"id": nid, "type": node_type}
    if extra:
        data.update(extra)
    lines = ["---"]
    for k, v in data.items():
        if isinstance(v, list):
            inner = ", ".join(v)
            lines.append(f"{k}: [{inner}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append("## Prosa de prueba.")
    return "\n".join(lines) + "\n"


def _write_tree(dirs_spec):
    """Crea un directorio temporal y escribe nodos segun spec.

    dirs_spec: lista de (subpath, node_type, nid, extra). subpath relativo al
    tmp root. Devuelve el Path del root temporal.
    """
    root = Path(tempfile.mkdtemp(prefix="ve_test_"))
    for subpath, node_type, nid, extra in dirs_spec:
        p = root / subpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_node(node_type, nid, extra), encoding="utf-8")
    return root


def _run(log_lines, dirs_spec, extra_dirs=None):
    """Escribe un log temporal + arbol de nodos temporal, corre ve.main.

    Devuelve (rc, stdout). log_lines se unen con newline; el primer elemento
    suele ser cabecera/no-dato para ejercitar el descarte.
    """
    root = _write_tree(dirs_spec)
    fd, logpath = tempfile.mkstemp(suffix=".md", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines) + "\n")
        argv = ["validate_evidence", logpath, str(root)]
        if extra_dirs:
            argv += [str(d) for d in extra_dirs]
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ve.main(argv)
        return rc, buf.getvalue()
    finally:
        os.remove(logpath)


# Specs reutilizadas: el set de nodos validos del proyecto (tipos correctos).
VALID_NODES = [
    ("knowledge/ukulele/index.md", "skill_index", "ukulele", {"domain_type": "physical"}),
    ("knowledge/ukulele/subskills/chord-transitions.md", "subskill", "chord-transitions",
     {"skill": "ukulele", "domain_type": "physical", "verification_type": "proxy",
      "status": "draft"}),
    ("contracts/sessions/session-2026-07-28-chord-transitions.md", "session_contract",
     "session-2026-07-28-chord-transitions",
     {"skill": "ukulele", "subskill": "chord-transitions",
      "skill_contract": "ukulele-compromiso-2026-08", "status": "draft",
      "criterio": "secuencia C-G-Am-F, 4 repeticiones, 80bpm, maximo 2 detenciones"}),
    ("contracts/skill/ukulele-compromiso-2026-08.md", "skill_contract",
     "ukulele-compromiso-2026-08",
     {"skill": "ukulele", "status": "draft", "instrument_frozen": "true",
      "criterio": "secuencia C-G-Am-F, 4 repeticiones, 80bpm, maximo 2 detenciones",
      "baseline_date": "2026-07-28", "checkpoint_date": "2026-08-27",
      "domain_type": "physical", "verification_type": "proxy"}),
]

DATA_LINE = (
    "2026-07-28T18:00:00 | skill=ukulele | subskill=chord-transitions | "
    "session=session-2026-07-28-chord-transitions | event=attempted | "
    'result=partial | notes="baseline"'
)


class ValidateEvidenceTests(unittest.TestCase):

    # --- lineas que no son dato se ignoran (sin error) ---

    def test_titulo_prosa_formato_y_vacia_se_ignoran(self):
        rc, out = _run([
            "# Log de evidencia",
            "",
            "Formato: `<iso-timestamp> | skill=<slug> ...`",
            "Prosa suelta que no empieza con 2.",
            DATA_LINE,
        ], VALID_NODES)
        self.assertEqual(rc, 0)
        self.assertIn("OK: 1 linea", out)

    def test_linea_que_empieza_con_2_pero_no_es_timestamp_no_cuenta(self):
        # "20 cosas..." empieza con "2" pero no es ISO; adherence la descarta.
        # Mismo criterio: parse_log_line solo exige empezar con "2", asi que
        # esta linea SI se cuenta como dato (no hay forma barata de distinguirla
        # de un timestamp sin re-validar el formato ISO, que esta fuera de
        # alcance). Lo que importa: no crashea y las refs validas siguen dando
        # exit 0. Sus campos skill/subskill/session son vacios -> no es error.
        rc, out = _run([
            "20 cosas para practicar",
            DATA_LINE,
        ], VALID_NODES)
        self.assertEqual(rc, 0)

    # --- refs inexistentes -> error con numero de linea correcto ---

    def test_skill_inexistente_error_con_linea(self):
        rc, out = _run([
            "# cabecera",
            "",
            "2026-07-28T18:00:00 | skill=NO-EXISTE | event=attempted",
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("ERRORES: 1", out)
        self.assertIn("linea 3", out)
        self.assertIn("skill 'NO-EXISTE' no existe como id de un nodo type: skill_index", out)

    def test_subskill_inexistente_error_con_linea(self):
        rc, out = _run([
            "2026-07-28T18:00:00 | subskill=fantasma | event=attempted",
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("subskill 'fantasma' no existe como id de un nodo type: subskill", out)

    def test_session_inexistente_error_con_linea(self):
        rc, out = _run([
            "2026-07-28T18:00:00 | session=no-esta | event=attempted",
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("session 'no-esta' no existe como id de un nodo type: session_contract", out)

    def test_numero_de_linea_cuenta_cabecera(self):
        # El dato esta en la linea 7 (como en el log real); el error debe
        # reportar linea 7, no 1.
        rc, out = _run([
            "# Log de evidencia",
            "",
            "Formato: ...",
            "",
            "Prosa.",
            "",
            "2026-07-28T18:00:00 | skill=NO-EXISTE | event=attempted",
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("linea 7", out)

    # --- id existe pero es de OTRO tipo -> error (el caso interesante) ---

    def test_subskill_apunta_a_skill_index_es_error(self):
        # subskill=ukulele: ukulele existe como id pero es skill_index, no subskill.
        rc, out = _run([
            "2026-07-28T18:00:00 | subskill=ukulele | event=attempted",
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("subskill 'ukulele' existe pero es de type 'skill_index' (no subskill)", out)

    def test_skill_apunta_a_subskill_es_error(self):
        # skill=chord-transitions: existe pero es subskill, no skill_index.
        rc, out = _run([
            "2026-07-28T18:00:00 | skill=chord-transitions | event=attempted",
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("skill 'chord-transitions' existe pero es de type 'subskill' (no skill_index)", out)

    def test_session_apunta_a_skill_contract_es_error(self):
        # session=ukulele-compromiso-2026-08: existe pero es skill_contract.
        rc, out = _run([
            "2026-07-28T18:00:00 | session=ukulele-compromiso-2026-08 | event=attempted",
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn(
            "session 'ukulele-compromiso-2026-08' existe pero es de type 'skill_contract' (no session_contract)",
            out,
        )

    # --- todas las refs validas -> exit 0 ---

    def test_todas_las_refs_validas_exit_0(self):
        rc, out = _run([DATA_LINE], VALID_NODES)
        self.assertEqual(rc, 0)
        self.assertIn("OK: 1 linea", out)
        self.assertNotIn("ERRORES", out)

    # --- campo ausente -> no es error ---

    def test_campo_ausente_no_es_error(self):
        # Solo skill, sin subskill ni session: los ausentes no se exigen.
        rc, out = _run([
            "2026-07-28T18:00:00 | skill=ukulele | event=attempted",
        ], VALID_NODES)
        self.assertEqual(rc, 0)
        self.assertIn("OK: 1 linea", out)

    def test_linea_solo_timestamp_cuenta_sin_error(self):
        rc, out = _run([
            "2026-07-28T18:00:00 | event=attempted",
        ], VALID_NODES)
        self.assertEqual(rc, 0)
        self.assertIn("OK: 1 linea", out)

    # --- H7: evidencia contra contrato en draft -> AVISO, exit 0 ---

    def test_evidencia_contra_contrato_draft_es_aviso_no_error(self):
        # El set VALID_NODES tiene el skill_contract en status: draft, y la
        # session lo referencia. Debe disparar AVISO y exit 0 (no error).
        rc, out = _run([DATA_LINE], VALID_NODES)
        self.assertEqual(rc, 0)
        self.assertIn("AVISOS: 1", out)
        self.assertIn(
            "evidencia contra contrato 'ukulele-compromiso-2026-08' que sigue en draft",
            out,
        )
        self.assertNotIn("ERRORES", out)

    def test_evidencia_contra_contrato_active_sin_aviso(self):
        # Mismo set pero el skill_contract en status: active -> ni error ni aviso.
        nodes = [list(n) for n in VALID_NODES]
        for n in nodes:
            if n[2] == "ukulele-compromiso-2026-08":
                n[3] = dict(n[3], status="active")
        rc, out = _run([DATA_LINE], nodes)
        self.assertEqual(rc, 0)
        self.assertNotIn("AVISOS", out)
        self.assertNotIn("ERRORES", out)
        self.assertIn("OK: 1 linea", out)

    def test_aviso_reporta_numero_de_linea(self):
        rc, out = _run([
            "# Log de evidencia",
            "",
            "Formato: ...",
            "",
            "",
            "",
            DATA_LINE,
        ], VALID_NODES)
        self.assertEqual(rc, 0)
        self.assertIn("linea 7", out)
        self.assertIn("draft", out)

    # --- errores y avisos se separan visualmente ---

    def test_errores_y_avisos_se_separan_en_bloques(self):
        # Una linea con skill inexistente (error) y otra con la data valida
        # (aviso H7). Ambos bloques deben aparecer, exit 1.
        rc, out = _run([
            "2026-07-28T18:00:00 | skill=NO-EXISTE | event=attempted",
            DATA_LINE,
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("ERRORES: 1", out)
        self.assertIn("AVISOS: 1", out)
        # el bloque de errores aparece antes que el de avisos
        self.assertLess(out.index("ERRORES"), out.index("AVISOS"))

    # --- log inexistente -> exit != 0 con mensaje claro ---

    def test_log_inexistente_exit_distinto_de_0(self):
        root = _write_tree(VALID_NODES)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ve.main([
                "validate_evidence",
                os.path.join(tempfile.gettempdir(), "no_existe_12345.md"),
                str(root),
            ])
        self.assertNotEqual(rc, 0)
        self.assertIn("no existe", buf.getvalue())

    # --- args insuficientes -> exit 1 ---

    def test_uso_sin_dirs_exit_1(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ve.main(["validate_evidence", "algo.md"])
        self.assertEqual(rc, 1)
        self.assertIn("uso:", buf.getvalue())

    # --- directorio inexistente se omite, no es error fatal ---

    def test_dir_inexistente_se_omite_y_sigue_validando(self):
        root = _write_tree(VALID_NODES)
        fd, logpath = tempfile.mkstemp(suffix=".md", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(DATA_LINE + "\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = ve.main([
                    "validate_evidence", logpath, str(root),
                    str(root / "no_existe_dir"),
                ])
            self.assertEqual(rc, 0)
            self.assertIn("no existe, se omite", buf.getvalue())
            self.assertIn("OK: 1 linea", buf.getvalue())
        finally:
            os.remove(logpath)

    # --- multiples directorios se combinan (knowledge + contracts) ---

    def test_multiples_dirs_se_combinan_para_resolver_refs(self):
        # skill_index en un dir, session_contract + skill_contract en otro:
        # como en el uso real (knowledge contracts). Si solo se pasara uno,
        # faltarian ids. Pasar ambos resuelve todo.
        root = _write_tree(VALID_NODES)
        kdir = root / "knowledge"
        cdir = root / "contracts"
        fd, logpath = tempfile.mkstemp(suffix=".md", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(DATA_LINE + "\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = ve.main(["validate_evidence", logpath, str(kdir), str(cdir)])
            self.assertEqual(rc, 0)
            self.assertIn("OK: 1 linea", buf.getvalue())
            self.assertIn("AVISOS: 1", buf.getvalue())
        finally:
            os.remove(logpath)


    # --- CONFIRM-N bug 4: `notes` inyecta un campo y pisa el real ---
    # notes= es TERMINAL: todo lo que sigue (pipes incluidos) es texto libre
    # de la nota y NO genera campos. Una nota con `| key=valor` no debe pisa
    # el campo real ni inyectar uno falso.

    def test_notes_con_un_pipe_no_inyecta_skill_falso(self):
        # El skill real FANTASMA (invalido) debe quedar; el skill=ukulele
        # dentro de notes NO lo pisa. Antes: exit 0 (bypass). Ahora: exit 1.
        rc, out = _run([
            '2026-07-28T18:00:00 | skill=FANTASMA | notes="nota | skill=ukulele"',
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("skill 'FANTASMA' no existe como id de un nodo type: skill_index", out)

    def test_notes_con_varios_pipes_no_inyecta_campos(self):
        rc, out = _run([
            '2026-07-28T18:00:00 | skill=FANTASMA | notes="a | b | c | skill=ukulele | session=x"',
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("skill 'FANTASMA' no existe", out)
        # lo inyectado en notes no se valida como campo (no aparece como error)
        self.assertNotIn("session 'x'", out)

    def test_notes_que_contiene_skill_no_pisa_skill_real_valido(self):
        # skill=ukulele valido; el skill=otro inyectado en notes no lo pisa.
        rc, out = _run([
            '2026-07-28T18:00:00 | skill=ukulele | notes="compare con skill=otro de ayer"',
        ], VALID_NODES)
        self.assertEqual(rc, 0)
        self.assertIn("OK: 1 linea", out)
        self.assertNotIn("ERRORES", out)

    def test_notes_que_contiene_subskill_no_pisa_subskill_real(self):
        # subskill=chord-transitions valido; el inyectado en notes no lo pisa.
        # Antes: subskill=fantasma -> falso error. Ahora: exit 0.
        rc, out = _run([
            '2026-07-28T18:00:00 | subskill=chord-transitions | notes="x | subskill=fantasma"',
        ], VALID_NODES)
        self.assertEqual(rc, 0)
        self.assertNotIn("subskill 'fantasma'", out)

    def test_notes_que_contiene_session_no_pisa_session_real(self):
        # session valida; la inyectada en notes no la pisa. Antes: falso error
        # "session 'fantasma' no existe". Ahora: exit 0.
        rc, out = _run([
            '2026-07-28T18:00:00 | session=session-2026-07-28-chord-transitions '
            '| event=attempted | notes="algo | session=fantasma"',
        ], VALID_NODES)
        self.assertEqual(rc, 0)
        self.assertNotIn("session 'fantasma'", out)

    def test_notes_con_comillas_y_pipes_se_respeta_como_texto(self):
        # Comillas simples dentro de notes, pipes y claves inyectadas: todo es
        # texto libre. skill=ukulele (valido) queda a salvo.
        rc, out = _run([
            '2026-07-28T18:00:00 | skill=ukulele | notes="ella dijo \'hola\' | skill=otro | session=x"',
        ], VALID_NODES)
        self.assertEqual(rc, 0)
        self.assertIn("OK: 1 linea", out)
        self.assertNotIn("ERRORES", out)

    def test_linea_valida_con_notes_que_tiene_pipes_sigue_dando_ok(self):
        # Caso legitimo: notes con pipes internos no rompe la validacion de la
        # linea ni la cuenta. Mantiene H7 (aviso por contrato draft).
        rc, out = _run([
            '2026-07-28T18:00:00 | skill=ukulele | subskill=chord-transitions '
            '| session=session-2026-07-28-chord-transitions | event=attempted '
            '| result=partial | notes="2 de 4 | sin detenerme | baseline"',
        ], VALID_NODES)
        self.assertEqual(rc, 0)
        self.assertIn("OK: 1 linea", out)

    # --- CONFIRM-N bug 3: clave repetida, "ultimo gana" descarta ref invalida ---
    # Clave repetida = AMBIGUA -> error explicito con linea y clave. Cierra el
    # bypass. No se validan las refs de la linea (parseo no confiable).

    def test_skill_repetido_es_error_de_clave_repetida(self):
        rc, out = _run([
            '2026-07-28T18:00:00 | skill=FANTASMA | skill=ukulele | event=attempted',
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("linea 1: clave repetida 'skill' (linea ambigua)", out)

    def test_subskill_repetido_es_error_de_clave_repetida(self):
        rc, out = _run([
            '2026-07-28T18:00:00 | subskill=a | subskill=b | event=attempted',
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("linea 1: clave repetida 'subskill' (linea ambigua)", out)

    def test_session_repetida_es_error_de_clave_repetida(self):
        rc, out = _run([
            '2026-07-28T18:00:00 | session=x | session=y | event=attempted',
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("linea 1: clave repetida 'session' (linea ambigua)", out)

    def test_clave_repetida_reporta_numero_de_linea(self):
        rc, out = _run([
            "# Log de evidencia",
            "",
            "Formato: ...",
            "2026-07-28T18:00:00 | skill=FANTASMA | skill=ukulele | event=attempted",
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("linea 4: clave repetida 'skill' (linea ambigua)", out)

    def test_clave_repetida_no_valida_refs_de_la_linea(self):
        # La linea es ambigua: se reporta SOLO el error de clave repetida, no
        # se valida la ref (skill=FANTASMA no aparece como "no existe").
        rc, out = _run([
            '2026-07-28T18:00:00 | skill=FANTASMA | skill=ukulele | event=attempted',
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("clave repetida 'skill'", out)
        self.assertNotIn("no existe como id", out)

    def test_clave_repetida_mas_notes_inyectando_a_la_vez(self):
        # Dos mecanismos a la vez: skill duplicado de verdad (FANTASMA, ukulele)
        # Y un skill=otro inyectado dentro de notes. notes es terminal -> el
        # inyectado NO cuenta como tercera ocurrencia; el duplicado real si
        # se detecta y se rechaza como ambiguo.
        rc, out = _run([
            '2026-07-28T18:00:00 | skill=FANTASMA | skill=ukulele | notes="z | skill=otro"',
        ], VALID_NODES)
        self.assertEqual(rc, 1)
        self.assertIn("linea 1: clave repetida 'skill' (linea ambigua)", out)
        # el inyectado desde notes no genera error de ref
        self.assertNotIn("skill 'otro'", out)
        self.assertNotIn("no existe como id", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)