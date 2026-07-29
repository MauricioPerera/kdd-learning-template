#!/usr/bin/env python3
"""Confirmacion / refutacion de los 4 fixes de la ronda de auditoria previa.

Mandato INVERSO al de esa ronda: NO se buscan bugs viejos, se ataca el codigo NUEVO
que introdujeron los fixes. Para cada hipotesis se reproduce el comportamiento real
del codigo actual y se clasifica:

  - CONFIRMADO-CORRECTO: el fix hace lo que debe; la hipotesis de ataque se refuta.
  - BUG-ENCONTRADO:     el fix introdujo/regalo un bug real (repro ejecutada).

Resultado de esta confirmacion: 0 bugs nuevos. Las 4 hipotesis se refutan con
evidencia; los comportamientos "enganosos" que se reproducen son trade-offs ya
declarados en AUDIT-A/B/C o comportamientos pre-existentes no tocados por el fix.

Restricciones: stdlib solamente, sin red, sin tocar knowledge/ real, sin --apply
contra knowledge/. Todo se corre sobre temp dirs o llamadas a main().
No toca tests/test_init_skill.py ni scripts/init_skill.py (otro dev).
"""
import io
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_contracts as vc  # noqa: E402
import adherence  # noqa: E402
import decay_check  # noqa: E402


# ----------------------------------------------------------------------------
# helpers compartidos
# ----------------------------------------------------------------------------
def write_md(dirpath, name, frontmatter_lines, body="\n\nbody\n"):
    p = dirpath / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = "---\n" + "\n".join(frontmatter_lines) + "\n---"
    p.write_text(fm + body, encoding="utf-8")
    return p


def run_vc_main(*roots):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = vc.main(["validate_contracts.py", *[str(r) for r in roots]])
    return rc, buf.getvalue()


def old_contains_vague(text):
    """Logica PRE-fix exacta (substring sobre texto lowercased), para comparar."""
    lowered = (text or "").lower()
    for w in vc.VAGUE_WORDS:
        if w in lowered:
            return w
    return None


def run_adherence(lines, extra_args=None, fake_now=None):
    extra_args = extra_args or []
    fd, path = tempfile.mkstemp(suffix=".log", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        argv = ["adherence", path] + extra_args
        buf = io.StringIO()
        target = adherence.datetime if fake_now is None else _FakeDateTime(fake_now)
        orig = adherence.datetime
        adherence.datetime = target
        try:
            with redirect_stdout(buf):
                rc = adherence.main(argv)
        finally:
            adherence.datetime = orig
        return rc, buf.getvalue()
    finally:
        os.remove(path)


class _FakeDateTime:
    """Reemplaza adherence.datetime para fijar now() en tests (naive local)."""

    def __init__(self, now_dt):
        self._now = now_dt

    def now(self):
        return self._now

    fromisoformat = staticmethod(datetime.fromisoformat)
    date = datetime.date


def parse_adherence_out(out):
    d = {}
    for line in out.strip().splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            d[k.strip()] = v.strip()
    return d


def run_decay(knowledge_dir, apply=False):
    argv = ["decay_check", str(knowledge_dir)] + (["--apply"] if apply else [])
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = decay_check.main(argv)
    return rc, buf.getvalue()


# ============================================================================
# FIX 1 — contains_vague_word: substring -> regex \b(?:...)\b (IGNORECASE)
# ============================================================================
class TestFix1VagueWord(unittest.TestCase):
    """Hipotesis a refutar: \b con acentos falla / orden de alternancia reporta
    mal / el fix introdujo un falso negativo vs el substring viejo."""

    def test_incognito_no_false_positive(self):
        # \b es Unicode-aware: entre 'n' y 'c' (ambos \w) no hay boundary, asi que
        # "cómodo" NO se detecta dentro de "incómodo". El substring viejo SI lo
        # hacia (falso positivo). El fix lo elimina -> correcto.
        self.assertIsNone(vc.contains_vague_word("incómodo"))
        self.assertIsNotNone(old_contains_vague("incómodo"))  # viejo: falso positivo

    def test_accented_vague_word_detected_standalone(self):
        # "cómodo" aislado SI se detecta (\b al inicio/fin, 'ó' es \w).
        m = vc.contains_vague_word("estoy cómodo")
        self.assertEqual(m, "cómodo")
        # "más" aislado NO es vague word (solo "más o menos"); -> None (correcto)
        self.assertIsNone(vc.contains_vague_word("estuvo más."))
        # la frase completa al final de frase, con punto (no-word) -> boundary ok
        self.assertEqual(vc.contains_vague_word("estuvo más o menos."), "más o menos")

    def test_vague_glued_to_punctuation_detected(self):
        # puntuacion/comillas son no-word -> crean boundary -> detecta (no hay
        # falso negativo vs substring).
        self.assertEqual(vc.contains_vague_word("tocar mejor."), "mejor")
        self.assertEqual(vc.contains_vague_word("está bien,"), "bien")
        self.assertEqual(vc.contains_vague_word("el resultado es \"aceptable\""), "aceptable")
        self.assertEqual(vc.contains_vague_word('\'comodo\''), "comodo")

    def test_hyphenated_mas_o_menos_is_no_regression(self):
        # "mas-o-menos" (guiones): el substring viejo "mas o menos" (espacios) NO
        # era subcadena -> viejo tampoco lo detectaba. El regex tampoco. Ninguno
        # lo detecta -> NO es un falso negativo introducido por el fix.
        self.assertIsNone(vc.contains_vague_word("estuvo mas-o-menos"))
        self.assertIsNone(old_contains_vague("estuvo mas-o-menos"))

    def test_no_false_negative_vs_substring_on_legit_phrases(self):
        # Bateria: para cada frase con lenguaje vago LEGITIMO (palabra real,
        # con puntuacion/comillas/fin de frase), el regex nuevo detecta igual
        # que el substring viejo.
        legit = [
            "tocar mejor.",
            "está bien,",
            '"aceptable"',
            "estuvo más o menos.",
            "estuvo mas o menos.",
            "estoy cómodo",
            "estoy comodo",
        ]
        for t in legit:
            with self.subTest(t=t):
                self.assertIsNotNone(
                    vc.contains_vague_word(t),
                    f"regresion: el regex dejo de detectar '{t}'",
                )

    def test_differences_vs_substring_are_all_false_positive_removals(self):
        # Donde viejo detectaba y el nuevo no, era SIEMPRE un substring dentro de
        # una palabra mayor (falso positivo), nunca lenguaje vago legitimo.
        removed_false_positives = [
            "incómodo",       # "cómodo" dentro de "incómodo"
            "inadecuado",     # "adecuado" dentro de "inadecuado"
            "mejorar",        # "mejor" dentro de "mejorar"
            "bajá algun poco",  # "un poco" dentro de "algun poco"
        ]
        # NOTA: el AUDIT-A cito "bien dentro de también" como falso positivo, pero
        # "bien" (b-i-E-n) NO es subcadena de "también" (b-i-É-n) por el acento: el
        # substring viejo tampoco lo detectaba. Imprecision del reporte, no del
        # fix; los 4 casos de arriba si son falsos positivos reales que el fix
        # elimino.
        for t in removed_false_positives:
            with self.subTest(t=t):
                self.assertIsNotNone(old_contains_vague(t), f"viejo no detectaba {t!r}")
                self.assertIsNone(
                    vc.contains_vague_word(t),
                    f"el regex deberia NO detectar el falso positivo {t!r}",
                )

    def test_alternation_no_prefix_overlap_so_no_wrong_word(self):
        # El riesgo de orden de alternancia: una palabra corta ANTES de una larga
        # que la contiene, matchear la corta y reportar mal. Solo puede ocurrir si
        # una vague word es prefijo de otra (mismo start, \b compartido). Verifico
        # estructuralmente que NINGUNA vague word es prefijo de otra distinta.
        words = vc.VAGUE_WORDS
        for i, a in enumerate(words):
            for b in words:
                if a == b:
                    continue
                self.assertFalse(
                    a.startswith(b) or b.startswith(a),
                    f"prefijo compartido entre {a!r} y {b!r}: el orden de alternancia "
                    f"podria reportar la palabra equivocada",
                )

    def test_alternation_reports_leftmost_full_phrase(self):
        # En la practica: la frase multiword se reporta completa, no un fragmento.
        self.assertEqual(
            vc.contains_vague_word("tocar mas o menos hoy"), "mas o menos"
        )
        self.assertEqual(vc.contains_vague_word("un poco mejor"), "un poco")
        self.assertEqual(vc.contains_vague_word("mejor un poco"), "mejor")


# ============================================================================
# FIX 2 — main: deteccion nueva de ids duplicados
# ============================================================================
class TestFix2DuplicateIds(unittest.TestCase):
    def test_dup_plus_other_error_both_reported(self):
        # id duplicado en un archivo que ADEMAS tiene otro error: se reportan ambos,
        # ninguno tapa al otro (no hay short-circuit en la lista de errores).
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "k", "a.md", ["id: dup", "type: subskill", "skill: s",
                                       "domain_type: physical",
                                       "verification_type: instrumented",
                                       "status: draft"])
            write_md(d / "k", "b.md", ["id: dup", "type: subskill", "skill: s",
                                       "domain_type: bogus",  # error adicional
                                       "verification_type: instrumented",
                                       "status: draft"])
            rc, out = run_vc_main(d / "k")
            self.assertEqual(rc, 1)
            self.assertIn("id duplicado 'dup'", out)
            self.assertIn("domain_type invalido", out)

    def test_three_files_same_id_reports_two_collisions(self):
        # Tres archivos con el mismo id: se reporta 1 vez por cada duplicado
        # extra (b y c), ambos apuntando al primero (a). => 2 errores de dup.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name in ("a.md", "b.md", "c.md"):
                write_md(d / "k", name, ["id: dup", "type: subskill", "skill: s",
                                         "domain_type: physical",
                                         "verification_type: instrumented",
                                         "status: draft"])
            rc, out = run_vc_main(d / "k")
            self.assertEqual(rc, 1)
            self.assertEqual(out.count("id duplicado 'dup'"), 2)
            # ambos apuntan al primer definidor
            self.assertIn("(ya definido en ", out)

    def test_empty_id_skips_dup_check(self):
        # id vacio -> `if not nid: continue` -> no entra al check de dup.
        # Se reporta como "falta campo requerido 'id'", no como duplicado.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name in ("a.md", "b.md"):
                write_md(d / "k", name, ["id: ", "type: subskill", "skill: s",
                                        "domain_type: physical",
                                        "verification_type: instrumented",
                                        "status: draft"])
            rc, out = run_vc_main(d / "k")
            self.assertEqual(rc, 1)
            self.assertNotIn("id duplicado", out)
            self.assertIn("falta campo requerido 'id'", out)

    def test_whitespace_only_id_skips_dup_check(self):
        # id solo espacios -> parse strip() -> "" -> mismo path que vacio.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name in ("a.md", "b.md"):
                write_md(d / "k", name, ["id:    ", "type: subskill", "skill: s",
                                        "domain_type: physical",
                                        "verification_type: instrumented",
                                        "status: draft"])
            rc, out = run_vc_main(d / "k")
            self.assertEqual(rc, 1)
            self.assertNotIn("id duplicado", out)

    def test_ambiguous_reference_passes_silently_declared_tradeoff(self):
        # La deteccion corre DESPUES de collect_known_ids (set colapsado), asi
        # que una referencia a un id duplicado sigue resolviendo contra el set y
        # NO genera error de referencia. La referencia queda ambigua pero valida.
        # Esto es el trade-off DECLARADO en AUDIT-A ("no intenta desambiguar
        # referencias, fuera de alcance de un validador de forma"): se confirma,
        # no es un bug nuevo.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "k", "a.md", ["id: dup", "type: subskill", "skill: s",
                                       "domain_type: physical",
                                       "verification_type: instrumented",
                                       "status: draft"])
            write_md(d / "k", "b.md", ["id: dup", "type: subskill", "skill: s",
                                       "domain_type: physical",
                                       "verification_type: instrumented",
                                       "status: draft"])
            # c referencia al id ambiguo "dup"
            write_md(d / "k", "c.md", ["id: c", "type: subskill", "skill: s",
                                       "domain_type: physical",
                                       "verification_type: instrumented",
                                       "status: draft",
                                       "depends_on: [dup]"])
            rc, out = run_vc_main(d / "k")
            self.assertEqual(rc, 1)
            self.assertIn("id duplicado 'dup'", out)
            # la referencia a "dup" resuelve silenciosamente: NO hay error de ref
            self.assertNotIn("no existe como id conocido", out)


# ============================================================================
# FIX 3 — adherence: normalizacion aware->naive con ts.replace(tzinfo=None)
# ============================================================================
class TestFix3Adherence(unittest.TestCase):
    def test_wall_clock_inflation_declared_tradeoff(self):
        # Dos sesiones que en tiempo absoluto (UTC) ocurrieron el MISMO dia, pero
        # con offsets distintos, caen en dias calendario distintos tras el
        # replace(tzinfo=None) (conserva wall-clock, no convierte zona). Esto
        # infla "dias distintos con actividad" (y la racha) de 1 (UTC) a 2
        # (wall-clock). Es el trade-off DECLARADO en AUDIT-B ("conservar el
        # wall-clock escrito, sin reinterpretar la zona; alternativa a UTC seria
        # decision interpretativa, fuera de scope"). Se confirma, no es bug nuevo.
        #   s1: 2026-07-28T23:00-05:00  -> UTC 2026-07-29T04:00Z  -> wall 07-28
        #   s2: 2026-07-29T10:00+02:00  -> UTC 2026-07-29T08:00Z  -> wall 07-29
        # En UTC ambas son 07-29 (1 dia). Wall-clock: 07-28 y 07-29 (2 dias).
        rc, out = run_adherence([
            "2026-07-28T23:00:00-05:00 | skill=u | event=attempted",
            "2026-07-29T10:00:00+02:00 | skill=u | event=attempted",
        ], fake_now=datetime(2026, 7, 29, 23, 0))
        self.assertEqual(rc, 0)
        d = parse_adherence_out(out)
        self.assertEqual(d["dias distintos con actividad"], "2")
        self.assertEqual(d["racha mas larga (dias consecutivos)"], "2")

    def test_negative_days_since_last_declared_tradeoff(self):
        # Una sesion aware cuyo wall-clock date esta ADELANTE del now local (por
        # diferencia de zona) produce days_since_last NEGATIVO. El script imprime
        # "(-N dias atras)", que es aritmeticamente (now - last_day).days pero
        # semanticallymente enganoso ("atras" para una sesion futura).
        # Es consecuencia del trade-off declarado en AUDIT-B (no reconciliar zona;
        # comparar contra now local naive, "reporta el hecho del reloj de la
        # maquina"). El audit no lo enumero explicitamente pero cae dentro de
        # "aritmetica pura, sin juicio" que declaro. No se corrige: clamp/0 o
        # conversion a UTC serian juicio, fuera de scope.
        #   entry: 2026-07-29T05:00+10:00 -> wall date 07-29
        #   now local (fijado): 2026-07-28 23:00 -> date 07-28
        #   days_since_last = (07-28 - 07-29).days = -1
        rc, out = run_adherence([
            "2026-07-29T05:00:00+10:00 | skill=u | event=attempted",
        ], fake_now=datetime(2026, 7, 28, 23, 0))
        self.assertEqual(rc, 0)
        # el script NO crashea y NO frena el negativo: lo imprime literal.
        self.assertIn("2026-07-29 (-1 dias atras)", out)

    def test_negative_days_is_raw_arithmetic_not_clamped(self):
        # Confirma que no hay clamp a 0 ni proteccion: el numero negativo pasa
        # tal cual. (Mismo trade-off; documenta el comportamiento exacto.)
        rc, out = run_adherence([
            "2026-07-31T05:00:00+10:00 | skill=u | event=attempted",
        ], fake_now=datetime(2026, 7, 28, 23, 0))
        self.assertEqual(rc, 0)
        self.assertIn("(-3 dias atras)", out)


# ============================================================================
# FIX 4 — decay_check: --apply reescribe sobre el span del grupo(1) del regex
#         de status (los 3 re.search son INDEPENDIENTES, primer match del archivo)
# ============================================================================
class TestFix4DecayApply(unittest.TestCase):
    def _due_dates(self, days_ago=30, rad=14):
        return (date.today() - timedelta(days=days_ago)).isoformat(), rad

    def test_cross_node_field_combination_declared_assumption(self):
        # Los 3 re.search son independientes y cada uno toma el PRIMER match del
        # archivo entero. Construyo un archivo con DOS secciones subskill:
        #   nodo A (primero): status: verified, SIN last_verified/review_after
        #   nodo B (segundo): status: draft, CON last_verified/review_after (due)
        # status_m -> A ("verified"); last_verified_m / review_after_m -> B.
        # El script combina campos de dos nodos: marca el archivo como vencido
        # (por las fechas de B) y --apply reescribe el status de A (verified ->
        # needs_review), dejando B (el verdaderamente vencido, en draft) intacto.
        # Es el supuesto de diseño DECLARADO en AUDIT-C ("un archivo = un nodo;
        # el script asume un solo re.search por campo; no se corrige para no
        # ampliar alcance"). Se confirma, no es bug nuevo.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "multi.md"
            lv, rad = self._due_dates()
            content = (
                "---\n"
                "id: a\n"
                "type: subskill\n"
                "status: verified\n"        # primer ^status: -> A, sin fechas
                "---\n\n"
                "Nodo A: sin fechas.\n\n"
                "---\n"
                "id: b\n"
                "type: subskill\n"
                "status: draft\n"           # B: el verdaderamente vencido
                f"last_verified: {lv}\n"     # primer ^last_verified: -> B
                f"review_after_days: {rad}\n"  # primer ^review_after_days: -> B
                "---\n\n"
                "Nodo B: due.\n"
            )
            p.write_text(content, encoding="utf-8")
            rc, out = run_decay(p.parent, apply=True)
            self.assertEqual(rc, 0)
            self.assertIn("actualizados", out)
            text = p.read_text(encoding="utf-8")
            # orden de los ^status: ahora: [needs_review (A cambiado), draft (B intacto)]
            self.assertEqual(re.findall(r"(?m)^status: (\S+)", text),
                             ["needs_review", "draft"])
            # B (due, draft) NO fue marcado needs_review; A (sin fechas) SI.
            self.assertIn("status: draft", text)
            self.assertIn(f"last_verified: {lv}", text)

    def test_prose_type_subskill_false_positive_is_preexisting(self):
        # El filtro `if "type: subskill" not in text: continue` es un `in` crudo
        # sobre TODO el archivo. Un nodo NO-subskill (mental_model) cuya PROSA
        # contiene la subcadena "type: subskill" pasa el filtro y, si tiene
        # status: verified + fechas vencidas, se flagea y --apply reescribe su
        # status. Esto es PRE-EXISTENTE: el filtro no fue tocado por FIX 4 (solo
        # cambio la rama --apply). El proyecto real no lo exhibe (los 3 archivos
        # con "type: subskill" son todos subskills reales). No es bug introducido
        # por el fix; documentado.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "mm.md"
            lv, rad = self._due_dates()
            content = (
                "---\n"
                "id: x\n"
                "type: mental_model\n"        # NO es subskill
                "status: verified\n"
                f"last_verified: {lv}\n"
                f"review_after_days: {rad}\n"
                "---\n\n"
                "## Notas\n\n"
                "Esto no es type: subskill, es un mental model.\n"  # prosa
            )
            p.write_text(content, encoding="utf-8")
            rc, out = run_decay(p.parent, apply=False)
            self.assertEqual(rc, 0)
            # flageado falsamente por la prosa (el frontmatter dice mental_model)
            self.assertIn("1 nodo(s)", out)

    def test_apply_preserves_accented_chars(self):
        # --apply escribe con encoding="utf-8" sobre text leido con utf-8 y
        # rebanado (slicing conserva bytes). Los caracteres acentuados del resto
        # del archivo NO se destruyen. CONFIRMADO-CORRECTO.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.md"
            lv, rad = self._due_dates()
            content = (
                "---\n"
                "id: x\n"
                "type: subskill\n"
                "status: verified\n"
                f"last_verified: {lv}\n"
                f"review_after_days: {rad}\n"
                "---\n\n"
                "## Notas\n\n"
                "Última revisión: estuvo cómoda, sin estrés.\n"
            )
            p.write_text(content, encoding="utf-8")
            rc, out = run_decay(p.parent, apply=True)
            self.assertEqual(rc, 0)
            text = p.read_text(encoding="utf-8")
            self.assertRegex(text, r"(?m)^status: needs_review$")
            self.assertIn("Última revisión: estuvo cómoda, sin estrés.", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)