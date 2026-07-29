#!/usr/bin/env python3
"""Oracle congelado para scripts/validate_contracts.py.

Sin dependencias externas (stdlib solamente), igual que el script bajo prueba.
Cubre: parseo de frontmatter, campos requeridos por tipo de nodo, listas de
referencias, deteccion de lenguaje vago en criterio, umbral numerico, y
deteccion de ids duplicados.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

# importar el script bajo prueba (scripts/ no es paquete)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_contracts as vc  # noqa: E402


def write_md(dirpath, name, frontmatter_lines, body="\n\nbody\n"):
    """Escribe un .md con frontmatter dado como lista de lineas."""
    p = dirpath / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = "---\n" + "\n".join(frontmatter_lines) + "\n---"
    p.write_text(fm + body, encoding="utf-8")
    return p


class TestParseFrontmatter(unittest.TestCase):
    def test_valid_frontmatter_scalar_and_list(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = write_md(d, "n.md", [
                "id: x",
                "type: subskill",
                "required_tools: [a, b, c]",
            ])
            data, err = vc.parse_frontmatter(p)
            self.assertIsNone(err)
            self.assertEqual(data["id"], "x")
            self.assertEqual(data["type"], "subskill")
            self.assertEqual(data["required_tools"], ["a", "b", "c"])

    def test_no_frontmatter(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "n.md"
            p.write_text("sin frontmatter\n", encoding="utf-8")
            data, err = vc.parse_frontmatter(p)
            self.assertIsNone(data)
            self.assertIsNotNone(err)
            self.assertIn("falta frontmatter", err)

    def test_mal_cerrado_single_delimiter(self):
        # solo un "---" inicial, nunca se cierra
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "n.md"
            p.write_text("---\nid: x\ntype: subskill\nbody sin cerrar\n", encoding="utf-8")
            data, err = vc.parse_frontmatter(p)
            self.assertIsNone(data)
            self.assertIn("mal cerrado", err)

    def test_empty_list_parsed_as_empty(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = write_md(d, "n.md", ["id: x", "depends_on: []"])
            data, _ = vc.parse_frontmatter(p)
            self.assertEqual(data["depends_on"], [])

    def test_whitespace_only_value_stripped_to_empty(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = write_md(d, "n.md", ["id: x", "status:    "])
            data, _ = vc.parse_frontmatter(p)
            self.assertEqual(data["status"], "")

    def test_id_with_spaces_stripped(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = write_md(d, "n.md", ["id:   x y  ", "type: subskill"])
            data, _ = vc.parse_frontmatter(p)
            self.assertEqual(data["id"], "x y")

    def test_indented_lines_ignored_deliberate(self):
        # diseño deliberado: el parser solo lee nivel 1 (comentario lineas 57-58).
        # Una lista YAML multilinea no se popula; es comportamiento documentado, no bug.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "n.md"
            p.write_text(
                "---\nid: x\napplies_to:\n  - a\n  - b\n---\n",
                encoding="utf-8",
            )
            data, _ = vc.parse_frontmatter(p)
            self.assertEqual(data["id"], "x")
            # las lineas indentadas se ignoran: applies_to queda como "" (no lista)
            self.assertEqual(data.get("applies_to"), "")

    def test_comments_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = write_md(d, "n.md", ["# comentario", "id: x", "type: subskill"])
            data, _ = vc.parse_frontmatter(p)
            self.assertNotIn("# comentario", data)
            self.assertEqual(data["id"], "x")

    def test_quotes_stripped(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = write_md(d, "n.md", ['id: x', 'goal: "tocar bien"'])
            data, _ = vc.parse_frontmatter(p)
            self.assertEqual(data["goal"], "tocar bien")


class TestContainsVagueWord(unittest.TestCase):
    def test_detects_real_vague_word(self):
        self.assertIsNotNone(vc.contains_vague_word("tocar mejor que antes"))
        self.assertIsNotNone(vc.contains_vague_word("estoy comodo"))
        self.assertIsNotNone(vc.contains_vague_word("estoy cómodo"))

    def test_no_false_positive_substring_mejorar(self):
        # "mejor" dentro de "mejorar" NO debe disparar
        self.assertIsNone(vc.contains_vague_word("mejorar la transicion entre acordes"))

    def test_no_false_positive_substring_tambien(self):
        # "bien" dentro de "también" NO debe disparar
        self.assertIsNone(vc.contains_vague_word("también grabar la sesion"))

    def test_no_false_positive_substring_inadecuado(self):
        # "adecuado" dentro de "inadecuado" NO debe disparar
        self.assertIsNone(vc.contains_vague_word("resultado inadecuado descartado"))

    def test_no_false_positive_substring_algun_poco(self):
        # "un poco" dentro de "algun poco" NO debe disparar
        self.assertIsNone(vc.contains_vague_word("bajá algun poco el tempo"))

    def test_none_text(self):
        self.assertIsNone(vc.contains_vague_word(None))


class TestHasNumberOrThreshold(unittest.TestCase):
    def test_has_digit(self):
        self.assertTrue(vc.has_number_or_threshold("80bpm y 4 repeticiones"))

    def test_no_digit(self):
        self.assertFalse(vc.has_number_or_threshold("secuencia sin numeros"))

    def test_none(self):
        self.assertFalse(vc.has_number_or_threshold(None))


class TestValidateNode(unittest.TestCase):
    def _validate(self, data, node_type):
        errors = []
        vc.validate_node("p.md", {"type": node_type, **data}, errors)
        return errors

    def test_missing_required_field(self):
        errs = self._validate({}, "subskill")  # faltan todos
        self.assertTrue(any("falta campo requerido 'id'" in e for e in errs))

    def test_whitespace_only_required_field_caught(self):
        # status presente pero solo espacios -> parse lo deja "" -> requerido falta
        errs = self._validate({
            "id": "x", "type": "subskill", "skill": "s", "domain_type": "physical",
            "verification_type": "instrumented", "status": "",
        }, "subskill")
        self.assertTrue(any("falta campo requerido 'status'" in e for e in errs))

    def test_invalid_domain_type(self):
        errs = self._validate({
            "id": "x", "type": "subskill", "skill": "s", "domain_type": "bogus",
            "verification_type": "instrumented", "status": "draft",
        }, "subskill")
        self.assertTrue(any("domain_type invalido" in e for e in errs))

    def test_invalid_verification_type(self):
        errs = self._validate({
            "id": "x", "type": "subskill", "skill": "s", "domain_type": "physical",
            "verification_type": "bogus", "status": "draft",
        }, "subskill")
        self.assertTrue(any("verification_type invalido" in e for e in errs))

    def test_invalid_subskill_status(self):
        errs = self._validate({
            "id": "x", "type": "subskill", "skill": "s", "domain_type": "physical",
            "verification_type": "instrumented", "status": "bogus",
        }, "subskill")
        self.assertTrue(any("status invalido" in e for e in errs))

    def test_unknown_type(self):
        errors = []
        vc.validate_node("p.md", {"type": "bogus"}, errors)
        self.assertTrue(any("desconocido" in e for e in errors))

    def test_vague_word_in_criterio_skill_contract(self):
        errs = self._validate({
            "id": "x", "type": "skill_contract", "skill": "s", "goal": "g",
            "domain_type": "physical", "verification_type": "human_rubric",
            "criterio": "tocar mejor que antes",
            "instrument_frozen": "true", "baseline_date": "2026-01-01",
            "checkpoint_date": "2026-02-01", "status": "draft",
        }, "skill_contract")
        self.assertTrue(any("lenguaje vago" in e for e in errs))

    def test_no_vague_word_clean_criterio(self):
        errs = self._validate({
            "id": "x", "type": "skill_contract", "skill": "s", "goal": "g",
            "domain_type": "physical", "verification_type": "proxy",
            "criterio": "secuencia C-G-Am-F, 4 repeticiones, 80bpm, maximo 2 detenciones",
            "instrument_frozen": "true", "baseline_date": "2026-01-01",
            "checkpoint_date": "2026-02-01", "status": "draft",
        }, "skill_contract")
        self.assertFalse([e for e in errs if "lenguaje vago" in e])

    def test_threshold_required_for_instrumented(self):
        errs = self._validate({
            "id": "x", "type": "skill_contract", "skill": "s", "goal": "g",
            "domain_type": "physical", "verification_type": "instrumented",
            "criterio": "secuencia sin numeros",
            "instrument_frozen": "true", "baseline_date": "2026-01-01",
            "checkpoint_date": "2026-02-01", "status": "draft",
        }, "skill_contract")
        self.assertTrue(any("umbral numerico" in e for e in errs))

    def test_threshold_present_no_error(self):
        errs = self._validate({
            "id": "x", "type": "skill_contract", "skill": "s", "goal": "g",
            "domain_type": "physical", "verification_type": "instrumented",
            "criterio": "4 repeticiones a 80bpm",
            "instrument_frozen": "true", "baseline_date": "2026-01-01",
            "checkpoint_date": "2026-02-01", "status": "draft",
        }, "skill_contract")
        self.assertFalse([e for e in errs if "umbral numerico" in e])

    def test_instrument_frozen_not_true(self):
        errs = self._validate({
            "id": "x", "type": "skill_contract", "skill": "s", "goal": "g",
            "domain_type": "physical", "verification_type": "human_rubric",
            "criterio": "criterio observable",
            "instrument_frozen": "false", "baseline_date": "2026-01-01",
            "checkpoint_date": "2026-02-01", "status": "draft",
        }, "skill_contract")
        self.assertTrue(any("instrument_frozen" in e for e in errs))

    def test_skill_contract_invalid_status(self):
        errs = self._validate({
            "id": "x", "type": "skill_contract", "skill": "s", "goal": "g",
            "domain_type": "physical", "verification_type": "human_rubric",
            "criterio": "criterio observable",
            "instrument_frozen": "true", "baseline_date": "2026-01-01",
            "checkpoint_date": "2026-02-01", "status": "bogus",
        }, "skill_contract")
        self.assertTrue(any("status invalido" in e for e in errs))

    def test_session_contract_no_threshold_check(self):
        # session_contract no exige umbral numerico (no tiene verification_type); deliberado.
        errs = self._validate({
            "id": "x", "type": "session_contract", "skill": "s",
            "subskill": "y", "status": "draft", "criterio": "sin numeros",
        }, "session_contract")
        self.assertFalse([e for e in errs if "umbral numerico" in e])

    def test_session_contract_invalid_status(self):
        errs = self._validate({
            "id": "x", "type": "session_contract", "skill": "s",
            "subskill": "y", "status": "bogus", "criterio": "criterio observable",
        }, "session_contract")
        self.assertTrue(any("status invalido" in e for e in errs))


class TestValidateReferences(unittest.TestCase):
    def _refs(self, data):
        errors = []
        vc.validate_references("p.md", data, {"known1", "known2"}, errors)
        return errors

    def test_empty_list_no_error(self):
        self.assertEqual(self._refs({"depends_on": []}), [])

    def test_absent_field_no_error(self):
        self.assertEqual(self._refs({}), [])

    def test_known_list_refs_no_error(self):
        self.assertEqual(self._refs({"applies_to": ["known1", "known2"]}), [])

    def test_unknown_list_ref_error(self):
        errs = self._refs({"depends_on": ["known1", "ghost"]})
        self.assertEqual(len(errs), 1)
        self.assertIn("ghost", errs[0])
        self.assertIn("depends_on", errs[0])

    def test_scalar_subskill_null_ok(self):
        self.assertEqual(self._refs({"subskill": "null"}), [])

    def test_scalar_subskill_known_ok(self):
        self.assertEqual(self._refs({"subskill": "known1"}), [])

    def test_scalar_subskill_unknown_error(self):
        errs = self._refs({"subskill": "ghost"})
        self.assertEqual(len(errs), 1)
        self.assertIn("subskill", errs[0])

    def test_scalar_skill_contract_unknown_error(self):
        errs = self._refs({"skill_contract": "ghost"})
        self.assertEqual(len(errs), 1)
        self.assertIn("skill_contract", errs[0])


class TestDuplicateIds(unittest.TestCase):
    def test_duplicate_ids_reported_in_main(self):
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
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vc.main(["validate_contracts.py", str(d / "k")])
            self.assertEqual(rc, 1)
            self.assertIn("id duplicado 'dup'", buf.getvalue())

    def test_no_duplicate_error_on_unique_ids(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "k", "a.md", ["id: a", "type: subskill", "skill: s",
                                       "domain_type: physical",
                                       "verification_type: instrumented",
                                       "status: draft"])
            write_md(d / "k", "b.md", ["id: b", "type: subskill", "skill: s",
                                       "domain_type: physical",
                                       "verification_type: instrumented",
                                       "status: draft"])
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vc.main(["validate_contracts.py", str(d / "k")])
            self.assertEqual(rc, 0)
            self.assertNotIn("id duplicado", buf.getvalue())


class TestRealProject(unittest.TestCase):
    """Caso real: los nodos del proyecto deben seguir validando en verde.

    Se afirma el exit code, no cuantos nodos hay: agregar una skill con
    init_skill.py es el uso previsto del sistema y no debe romper la suite.
    """

    def test_real_knowledge_and_contracts_pass(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vc.main(["validate_contracts.py",
                          str(ROOT / "knowledge"), str(ROOT / "contracts")])
        self.assertEqual(rc, 0, "los nodos reales del proyecto dejaron de pasar")


class TestVerifiedSubskill(unittest.TestCase):
    """H1+H3: requisitos condicionales a status=verified (draft/practicing no los
    necesitan). Llamadas directas a validate_node."""

    BASE = {
        "id": "x", "type": "subskill", "skill": "s", "domain_type": "physical",
        "verification_type": "proxy", "status": "verified",
    }

    def _validate(self, **overrides):
        errors = []
        data = {**self.BASE, **overrides}
        vc.validate_node("p.md", data, errors)
        return errors

    def test_verified_valid_with_ratified_by_human(self):
        errs = self._validate(last_verified="2026-07-28", review_after_days=14,
                              ratified_by="human")
        self.assertEqual(errs, [])

    def test_verified_valid_human_with_any_verification_type(self):
        # human ratifica sea instrumented, proxy o human_rubric
        for vt in ("instrumented", "proxy", "human_rubric"):
            errs = self._validate(verification_type=vt, last_verified="2026-07-28",
                                  review_after_days=14, ratified_by="human")
            self.assertEqual(errs, [], f"human deberia valer para verification_type={vt}")

    def test_verified_last_verified_null_error(self):
        errs = self._validate(last_verified="null", review_after_days=14,
                              ratified_by="human")
        self.assertTrue(any("last_verified" in e and "requiere" in e for e in errs))

    def test_verified_last_verified_missing_error(self):
        errs = self._validate(review_after_days=14, ratified_by="human")
        self.assertTrue(any("last_verified" in e for e in errs))

    def test_verified_last_verified_garbage_error(self):
        errs = self._validate(last_verified="no-es-una-fecha",
                              review_after_days=14, ratified_by="human")
        self.assertTrue(any("no es fecha ISO valida" in e for e in errs))

    def test_verified_review_after_days_missing_error(self):
        errs = self._validate(last_verified="2026-07-28", ratified_by="human")
        self.assertTrue(any("review_after_days" in e and "requiere" in e for e in errs))

    def test_verified_review_after_days_zero_error(self):
        errs = self._validate(last_verified="2026-07-28", review_after_days=0,
                              ratified_by="human")
        self.assertTrue(any("review_after_days debe ser positivo" in e for e in errs))

    def test_verified_review_after_days_negative_error(self):
        errs = self._validate(last_verified="2026-07-28", review_after_days=-3,
                              ratified_by="human")
        self.assertTrue(any("review_after_days debe ser positivo" in e for e in errs))

    def test_verified_review_after_days_non_numeric_error(self):
        errs = self._validate(last_verified="2026-07-28", review_after_days="dos",
                              ratified_by="human")
        self.assertTrue(any("review_after_days no es entero" in e for e in errs))

    def test_verified_ratified_by_ai_error(self):
        errs = self._validate(last_verified="2026-07-28", review_after_days=14,
                              ratified_by="ai")
        self.assertTrue(any("ratified_by invalido" in e for e in errs))
        self.assertTrue(any("lectura de IA" in e for e in errs))

    def test_verified_ratified_by_llm_error(self):
        errs = self._validate(last_verified="2026-07-28", review_after_days=14,
                              ratified_by="llm")
        self.assertTrue(any("ratified_by invalido" in e for e in errs))

    def test_verified_ratified_by_missing_error(self):
        errs = self._validate(last_verified="2026-07-28", review_after_days=14)
        self.assertTrue(any("ratified_by" in e and "requiere" in e for e in errs))

    def test_verified_instrument_with_instrumented_ok(self):
        errs = self._validate(verification_type="instrumented",
                              last_verified="2026-07-28", review_after_days=14,
                              ratified_by="instrument")
        self.assertEqual(errs, [])

    def test_verified_instrument_with_proxy_error(self):
        errs = self._validate(verification_type="proxy",
                              last_verified="2026-07-28", review_after_days=14,
                              ratified_by="instrument")
        self.assertTrue(any("ratified_by=instrument solo es valido" in e for e in errs))

    def test_verified_instrument_with_human_rubric_error(self):
        errs = self._validate(verification_type="human_rubric",
                              last_verified="2026-07-28", review_after_days=14,
                              ratified_by="instrument")
        self.assertTrue(any("ratified_by=instrument solo es valido" in e for e in errs))

    def test_verified_multiple_errors_all_reported(self):
        # los 3 campos mal a la vez -> 3 errores
        errs = self._validate(last_verified="null", review_after_days=0,
                              ratified_by="ai")
        self.assertTrue(any("last_verified" in e for e in errs))
        self.assertTrue(any("review_after_days" in e for e in errs))
        self.assertTrue(any("ratified_by" in e for e in errs))


class TestVerifiedSubskillMain(unittest.TestCase):
    """Cobertura end-to-end via main(): el caso comun (draft) sigue valido y el
    ciclo decay_check --apply sobre verified deja un needs_review que sigue validando."""

    def _run_main(self, knowledge_dir):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vc.main(["validate_contracts.py", str(knowledge_dir)])
        return rc, buf.getvalue()

    def test_draft_without_verified_fields_still_valid(self):
        # caso comun: draft sin last_verified/review_after_days/ratified_by no rompe
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d, "n.md", [
                "id: x", "type: subskill", "skill: s", "domain_type: physical",
                "verification_type: instrumented", "status: draft",
                "depends_on: []", "applies_mental_models: []", "applies_failure_modes: []",
                "required_tools: []", "review_after_days: 14", "last_verified: null",
            ])
            rc, out = self._run_main(d)
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)

    def test_needs_review_without_verified_fields_still_valid(self):
        # un nodo que decayo conserva ratified_by/last_verified pero no se le exige nada nuevo
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d, "n.md", [
                "id: x", "type: subskill", "skill: s", "domain_type: physical",
                "verification_type: proxy", "status: needs_review",
                "review_after_days: 14", "last_verified: 2026-07-01",
                "ratified_by: human",
            ])
            rc, out = self._run_main(d)
            self.assertEqual(rc, 0, out)

    def test_decay_apply_on_verified_keeps_validating(self):
        # ciclo punta a punta: verified valido -> decay_check --apply -> needs_review
        # resultante sigue pasando validate_contracts (coherencia H1 con decay_check).
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d, "n.md", [
                "id: x", "type: subskill", "skill: s", "domain_type: physical",
                "verification_type: proxy", "status: verified",
                "review_after_days: 1", "last_verified: 2020-01-01",
                "ratified_by: human",
            ])
            # 1. validated como verified
            rc1, out1 = self._run_main(d)
            self.assertEqual(rc1, 0, out1)

            # 2. decay_check --apply reescribe verified -> needs_review
            import decay_check as dc
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc_dc = dc.main(["decay_check.py", str(d), "--apply"])
            self.assertEqual(rc_dc, 0, buf.getvalue())
            self.assertIn("actualizados a needs_review", buf.getvalue())

            # 3. el nodo reescrito sigue validando (needs_review no exige los 3 campos)
            rc2, out2 = self._run_main(d)
            self.assertEqual(rc2, 0, out2)
            self.assertIn("OK", out2)


class TestSessionCriterioMatch(unittest.TestCase):
    """H2: si un session_contract referencia un skill_contract conocido, su criterio
    debe ser identico al del padre. Chequeo cross-archivo via main(), como TestDuplicateIds.
    Llamadas directas a validate_node no alcanzan (necesita todos los nodos a la vez)."""

    SC_ID = "ukulele-compromiso-2026-08"
    SUB_ID = "chord-transitions"
    CRITERIO = "secuencia C-G-Am-F, 4 repeticiones, 80bpm, maximo 2 detenciones"

    def _subskill(self):
        return [
            f"id: {self.SUB_ID}", "type: subskill", "skill: ukulele",
            "domain_type: physical", "verification_type: instrumented",
            "status: draft",
        ]

    def _skill_contract(self, criterio=CRITERIO, sc_id=SC_ID, status="draft",
                        verification_type="proxy"):
        return [
            f"id: {sc_id}", "type: skill_contract", "skill: ukulele",
            "goal: tocar 3 canciones", "subskills: []",
            "domain_type: physical", f"verification_type: {verification_type}",
            f'criterio: "{criterio}"', "instrument_frozen: true",
            "baseline_date: 2026-07-28", "checkpoint_date: 2026-08-27",
            f"status: {status}",
        ]

    def _session_contract(self, criterio=CRITERIO, sc_id=SC_ID, with_skill_contract=True,
                         extra_lines=None):
        lines = [
            "id: session-2026-07-28-chord-transitions", "type: session_contract",
            "skill: ukulele", "subskill: chord-transitions", "checkpoint: baseline",
        ]
        if with_skill_contract:
            lines.append(f"skill_contract: {sc_id}")
        lines.append("status: draft")
        lines.append(f'criterio: "{criterio}"')
        lines.append("tools_needed: []")
        if extra_lines:
            lines.extend(extra_lines)
        return lines

    def _run_main(self, knowledge_dir):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vc.main(["validate_contracts.py", str(knowledge_dir)])
        return rc, buf.getvalue()

    def _error_lines(self, output):
        return [ln.strip()[2:] for ln in output.splitlines()
                if ln.strip().startswith("- ")]

    def _write_fixture(self, d, parent_criterio=CRITERIO, own_criterio=CRITERIO,
                      with_skill_contract=True, sc_id=SC_ID):
        """Escribe subskill + skill_contract + session. Por defecto los criterios son
        identicos -> valido."""
        write_md(d, "sub.md", self._subskill())
        write_md(d, "sc.md", self._skill_contract(criterio=parent_criterio, sc_id=sc_id))
        write_md(d, "session.md", self._session_contract(
            criterio=own_criterio, sc_id=sc_id, with_skill_contract=with_skill_contract))

    def test_criterio_identical_to_parent_ok(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._write_fixture(d)
            rc, out = self._run_main(d)
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)

    def test_criterio_divergent_reports_both_values(self):
        parent = "secuencia C-G-Am-F, 4 repeticiones, 80bpm"
        own = "secuencia C-G-Am-F, 2 repeticiones, 60bpm"
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._write_fixture(d, parent_criterio=parent, own_criterio=own)
            rc, out = self._run_main(d)
            self.assertEqual(rc, 1, out)
            errs = self._error_lines(out)
            # solo el error de divergencia, nada mas
            self.assertEqual(len(errs), 1, out)
            self.assertIn("diverge", errs[0])
            self.assertIn(self.SC_ID, errs[0])
            self.assertIn(parent, errs[0])
            self.assertIn(own, errs[0])

    def test_session_without_skill_contract_field_ok(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._write_fixture(d, with_skill_contract=False)
            rc, out = self._run_main(d)
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)

    def test_session_with_null_skill_contract_ok(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d, "sub.md", self._subskill())
            write_md(d, "sc.md", self._skill_contract())
            write_md(d, "session.md", self._session_contract(
                with_skill_contract=False, extra_lines=["skill_contract: null"]))
            rc, out = self._run_main(d)
            self.assertEqual(rc, 0, out)

    def test_referenced_skill_contract_nonexistent_one_error(self):
        # skill_contract: ghost -> validate_references reporta UN error; el chequeo H2
        # no agrega un segundo error por lo mismo.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d, "sub.md", self._subskill())
            # no creamos el skill_contract padre
            write_md(d, "session.md", self._session_contract(sc_id="ghost"))
            rc, out = self._run_main(d)
            self.assertEqual(rc, 1, out)
            errs = self._error_lines(out)
            self.assertEqual(len(errs), 1, out)
            self.assertIn("skill_contract", errs[0])
            self.assertIn("ghost", errs[0])
            self.assertNotIn("diverge", errs[0])

    def test_subtle_internal_spacing_difference_is_error(self):
        # estricto a proposito: un espacio interno de mas es un cambio del instrumento
        parent = "secuencia C-G-Am-F, 4 repeticiones, 80bpm"
        own = "secuencia C-G-Am-F,  4 repeticiones, 80bpm"  # doble espacio tras la coma
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._write_fixture(d, parent_criterio=parent, own_criterio=own)
            rc, out = self._run_main(d)
            self.assertEqual(rc, 1, out)
            errs = self._error_lines(out)
            self.assertEqual(len(errs), 1, out)
            self.assertIn("diverge", errs[0])

    def test_reference_points_to_non_skill_contract_no_diverge_error(self):
        # apunta por error a una subskill: fuera de alcance, no se compara criterio.
        # El id existe (la subskill) -> sin error de referencia; no es skill_contract ->
        # sin divergencia. Todo valido.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d, "sub.md", self._subskill())
            write_md(d, "sc.md", self._skill_contract())
            write_md(d, "session.md", self._session_contract(sc_id=self.SUB_ID))
            rc, out = self._run_main(d)
            self.assertEqual(rc, 0, out)
            self.assertNotIn("diverge", out)
            self.assertNotIn("no existe como id conocido", out)


class TestSkillContractDates(unittest.TestCase):
    """H5: baseline_date y checkpoint_date deben ser fechas ISO validas y checkpoint debe
    ser ESTRICTAMENTE posterior a baseline. Llamadas directas a validate_node."""

    BASE = {
        "id": "x", "type": "skill_contract", "skill": "s", "goal": "g",
        "domain_type": "physical", "verification_type": "human_rubric",
        "criterio": "criterio observable", "instrument_frozen": "true",
        "status": "draft",
    }

    def _validate(self, **overrides):
        errors = []
        data = {**self.BASE, **overrides}
        vc.validate_node("p.md", data, errors)
        return errors

    def test_valid_ordered_dates_ok(self):
        errs = self._validate(baseline_date="2026-07-28", checkpoint_date="2026-08-27")
        self.assertFalse([e for e in errs if "fecha ISO" in e or "posterior a" in e])

    def test_baseline_garbage_error(self):
        errs = self._validate(baseline_date="no-es-una-fecha",
                              checkpoint_date="2026-08-27")
        self.assertTrue(any("baseline_date no es fecha ISO valida" in e for e in errs))

    def test_checkpoint_garbage_error(self):
        errs = self._validate(baseline_date="2026-07-28",
                              checkpoint_date="no-es-una-fecha")
        self.assertTrue(any("checkpoint_date no es fecha ISO valida" in e for e in errs))

    def test_checkpoint_before_baseline_error(self):
        errs = self._validate(baseline_date="2026-08-27", checkpoint_date="2026-07-28")
        self.assertTrue(any("debe ser posterior a baseline_date" in e for e in errs))

    def test_checkpoint_equal_baseline_error(self):
        # ventana de cero dias: no permite medir un delta -> error
        errs = self._validate(baseline_date="2026-07-28", checkpoint_date="2026-07-28")
        self.assertTrue(any("debe ser posterior a baseline_date" in e for e in errs))

    def test_baseline_garbage_no_order_check(self):
        # si baseline no parsea, no se compara el orden: un solo error de fecha
        errs = self._validate(baseline_date="basura", checkpoint_date="2026-08-27")
        date_errs = [e for e in errs if "fecha ISO" in e or "posterior" in e]
        self.assertEqual(len(date_errs), 1)

    def test_missing_baseline_only_required_error(self):
        # baseline ausente -> solo el error de campo requerido, NO un segundo error de fecha
        errs = self._validate(checkpoint_date="2026-08-27")
        date_errs = [e for e in errs if "fecha ISO" in e or "posterior a" in e]
        self.assertEqual(date_errs, [])
        self.assertTrue(any("falta campo requerido 'baseline_date'" in e for e in errs))


class TestOmitNonNodeFiles(unittest.TestCase):
    """H6: un .md sin frontmatter NO es un nodo -> se omite (no es error) y se cuenta en el
    mensaje final. Un .md con --- inicial pero mal cerrado SIGUE siendo error. Via main()."""

    def _run_main(self, *roots):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vc.main(["validate_contracts.py", *roots])
        return rc, buf.getvalue()

    def _valid_subskill(self, d, name="n.md"):
        write_md(d, name, [
            "id: x", "type: subskill", "skill: s", "domain_type: physical",
            "verification_type: " + "instrumented", "status: draft",
        ])

    def test_md_without_frontmatter_omitted_not_error(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._valid_subskill(d)
            (d / "nota.md").write_text("una nota suelta sin frontmatter\n",
                                       encoding="utf-8")
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertNotIn("FALLO", out)

    def test_omitted_file_counted_in_message(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._valid_subskill(d)
            (d / "nota.md").write_text("nota suelta\n", encoding="utf-8")
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("1 archivo omitido por no tener frontmatter", out)

    def test_multiple_omitted_plural_message(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._valid_subskill(d)
            (d / "a.md").write_text("nota a\n", encoding="utf-8")
            (d / "b.md").write_text("nota b\n", encoding="utf-8")
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("2 archivos omitidos por no tener frontmatter", out)

    def test_no_omission_keeps_exact_historic_message(self):
        # sin archivos omitidos el mensaje es EXACTAMENTE el historico (sin sufijo)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._valid_subskill(d)
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertEqual(
                out.strip(),
                "OK: 1 nodo(s)/contrato(s) validados sin errores de forma",
            )

    def test_unclosed_frontmatter_still_error(self):
        # empieza con --- pero nunca se cierra: nodo roto, NO omision silenciosa
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self._valid_subskill(d)
            (d / "roto.md").write_text("---\nid: y\ntype: subskill\nbody sin cerrar\n",
                                       encoding="utf-8")
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 1, out)
            self.assertIn("mal cerrado", out)

    def test_logs_progress_omitted_real_case(self):
        # Caso real de H6: pasar logs/ junto a knowledge/ y contracts/ no debe
        # dar error; los archivos que no son nodos se omiten y se informan.
        # Se afirma el COMPORTAMIENTO (exit 0 + se informa la omision), no la
        # cantidad exacta: agregar una nota suelta o un segundo log es un uso
        # legitimo del sistema y no debe poner roja la suite. El conteo exacto
        # ya esta cubierto con fixtures temporales en los tests de arriba.
        rc, out = self._run_main(str(ROOT / "knowledge"), str(ROOT / "contracts"),
                                 str(ROOT / "logs"))
        self.assertEqual(rc, 0, out)
        self.assertIn("omitido", out)


class TestConfirmPFixes(unittest.TestCase):
    """Cobertura de los bugs confirmados en CONFIRM-M/CONFIRM-N para
    scripts/validate_contracts.py (fix P). Una clase agrupada, sin tocar los
    oraculos congelados existentes."""

    def _run_main(self, *roots):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vc.main(["validate_contracts.py", *roots])
        return rc, buf.getvalue()

    def _error_lines(self, output):
        return [ln.strip()[2:] for ln in output.splitlines()
                if ln.strip().startswith("- ")]

    # --- BUG 1 (ALTA): BOM UTF-8 no debe enmascarar corrupcion ---

    def test_bom_with_corrupt_node_detects_corruption(self):
        # un .md con BOM + nodo corrupto (type inexistente) debe validarse como
        # nodo y reportar la corrupcion, NO omitirse en silencio.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "bom.md"
            content = (
                "---\n"
                "id: bom-broken\n"
                "type: TIPO_INEXISTENTE\n"
                "skill: fantasma-ref\n"
                "---\n\nprosa\n"
            )
            # escribir con BOM UTF-8 explicito
            p.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 1, out)
            self.assertIn("TIPO_INEXISTENTE", out)
            self.assertIn("desconocido", out)
            # NO se omite como no-nodo
            self.assertNotIn("omitido por no tener frontmatter", out)

    def test_bom_with_valid_node_validates_normally(self):
        # BOM + nodo valido -> se valida y pasa (no se omite)
        # FIX-CONFIRM-S: el skill_index va en un subdir 'x' (id == dir), invariante
        # nueva de BUG 4. Antes estaba suelto en el temp dir de nombre arbitrario.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "x" / "bom.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            content = (
                "---\n"
                "id: x\n"
                "type: skill_index\n"
                "domain_type: physical\n"
                "---\n\nprosa\n"
            )
            p.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)
            # el nodo se conto como validado, no como omitido
            self.assertNotIn("omitido por no tener frontmatter", out)

    # --- BUG 1b (BAJA): `---` no en la primera linea -> error explicito ---

    def test_marker_not_in_first_line_is_error_not_omission(self):
        # leading newline antes del `---`: nodo mal formado -> error explicito
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "blank.md"
            p.write_text(
                "\n---\nid: x\ntype: skill_index\ndomain_type: physical\n---\n\nprosa\n",
                encoding="utf-8",
            )
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 1, out)
            self.assertIn("no empieza en la primera linea", out)
            # NO es omision silenciosa
            self.assertNotIn("omitido por no tener frontmatter", out)

    def test_marker_with_leading_spaces_then_newline_is_error(self):
        # espacios + newline antes del `---`: mismo mecanismo -> error explicito
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "sp.md"
            p.write_text(
                "   \n---\nid: x\ntype: skill_index\ndomain_type: physical\n---\n\nprosa\n",
                encoding="utf-8",
            )
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 1, out)
            self.assertIn("no empieza en la primera linea", out)
            self.assertNotIn("omitido por no tener frontmatter", out)

    def test_pure_prose_without_marker_still_omitted(self):
        # sin `---` en ninguna linea -> sigue siendo no-nodo -> se omite (no error)
        # FIX-CONFIRM-S: el skill_index va en un subdir 'x' (id == dir), invariante
        # nueva de BUG 4. El archivo omitido (nota.md) sigue suelto en el temp dir.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "x", "n.md", ["id: x", "type: skill_index", "domain_type: physical"])
            (d / "nota.md").write_text("una nota suelta sin frontmatter\n",
                                       encoding="utf-8")
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("1 archivo omitido por no tener frontmatter", out)

    # --- FIX-MARKER-SCOPE: `---` como linea horizontal en prosa -> omitido ---

    def test_prose_title_then_horizontal_rule_is_omitted(self):
        # prosa con `# Titulo` y luego una linea `---` (linea horizontal de
        # markdown): hay contenido real antes del `---` -> NO es nodo -> omitido,
        # no error. Antes del fix esto daba un falso "no empieza en la primera
        # linea".
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "x", "n.md", ["id: x", "type: skill_index", "domain_type: physical"])
            (d / "ideas.md").write_text(
                "# Ideas sueltas\n\nAlgo de prosa.\n\n---\n\nMas prosa.\n",
                encoding="utf-8",
            )
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("1 archivo omitido por no tener frontmatter", out)
            self.assertNotIn("no empieza en la primera linea", out)

    def test_horizontal_rule_on_last_line_is_omitted(self):
        # prosa con `---` en la ultima linea del archivo -> omitido (no error).
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "x", "n.md", ["id: x", "type: skill_index", "domain_type: physical"])
            (d / "nota.md").write_text("una nota\n\n---", encoding="utf-8")
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("1 archivo omitido por no tener frontmatter", out)
            self.assertNotIn("no empieza en la primera linea", out)

    def test_fenced_code_block_containing_marker_is_omitted(self):
        # archivo que empieza con un bloque de codigo cercado y contiene `---`
        # adentro: hay contenido real (```) antes del `---` -> omitido.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "x", "n.md", ["id: x", "type: skill_index", "domain_type: physical"])
            (d / "snippet.md").write_text(
                "```\ncodigo\ncodigo\ncodigo\ncodigo\n---\nmas codigo\n```\n",
                encoding="utf-8",
            )
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("1 archivo omitido por no tener frontmatter", out)
            self.assertNotIn("no empieza en la primera linea", out)

    def test_only_blank_lines_before_marker_still_error(self):
        # regresion guard: SOLO lineas en blanco antes del `---` -> frontmatter
        # desplazado -> SIGUE siendo error explicito (no se debilita la garantia).
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "blank.md"
            p.write_text(
                "\n\n\n---\nid: x\ntype: skill_index\ndomain_type: physical\n---\n\nprosa\n",
                encoding="utf-8",
            )
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 1, out)
            self.assertIn("no empieza en la primera linea", out)
            self.assertNotIn("omitido por no tener frontmatter", out)

    def test_bom_plus_blank_lines_before_marker_still_error(self):
        # BOM + lineas en blanco + `---`: el BOM lo descarta utf-8-sig, queda
        # frontmatter desplazado por blanks -> SIGUE siendo error explicito.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "bom_blank.md"
            content = (
                "\n---\nid: x\ntype: skill_index\ndomain_type: physical\n---\n\nprosa\n"
            )
            p.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 1, out)
            self.assertIn("no empieza en la primera linea", out)
            self.assertNotIn("omitido por no tener frontmatter", out)

    def test_valid_node_with_horizontal_rule_in_body_validates(self):
        # nodo normal con `---` en la primera linea Y una linea horizontal `---`
        # en el cuerpo: el `---` del cuerpo no debe romper la validacion.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = d / "x" / "node.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            content = (
                "---\n"
                "id: x\n"
                "type: skill_index\n"
                "domain_type: physical\n"
                "---\n\n"
                "Seccion A\n\n---\n\n"
                "Seccion B\n"
            )
            p.write_text(content, encoding="utf-8")
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)
            self.assertNotIn("omitido por no tener frontmatter", out)

    # --- BUG 2 (ALTA): review_after_days con cota superior ---

    def _verified(self, **overrides):
        errors = []
        data = {
            "id": "x", "type": "subskill", "skill": "s", "domain_type": "physical",
            "verification_type": "proxy", "status": "verified",
            "last_verified": "2020-01-01", "ratified_by": "human",
        }
        data.update(overrides)
        vc.validate_node("p.md", data, errors)
        return errors

    def test_review_after_days_365_ok(self):
        errs = self._verified(review_after_days=365)
        self.assertFalse([e for e in errs if "review_after_days" in e])

    def test_review_after_days_366_error(self):
        errs = self._verified(review_after_days=366)
        self.assertTrue(any("excede el maximo" in e and "365" in e for e in errs))

    def test_review_after_days_999999_error(self):
        errs = self._verified(review_after_days=999999)
        self.assertTrue(any("excede el maximo" in e for e in errs))

    # --- BUG 3 (MEDIA): last_verified futura -> error; hoy -> ok ---

    def test_last_verified_future_error(self):
        errs = self._verified(last_verified="2030-01-01", review_after_days=14)
        self.assertTrue(any("futura" in e and "2030-01-01" in e for e in errs))

    def test_last_verified_today_ok(self):
        from datetime import date
        errs = self._verified(last_verified=date.today().isoformat(),
                              review_after_days=14)
        self.assertFalse([e for e in errs if "futura" in e])

    def test_last_verified_past_ok(self):
        errs = self._verified(last_verified="2020-01-01", review_after_days=14)
        self.assertFalse([e for e in errs if "futura" in e])

    # --- BUG 4 (BAJA): fecha con hora aceptada en los tres campos ---

    def test_last_verified_with_hour_accepted(self):
        errs = self._verified(last_verified="2020-01-01T10:00:00",
                              review_after_days=14)
        self.assertFalse([e for e in errs if "no es fecha ISO" in e or "futura" in e])

    def _skill_contract(self, **overrides):
        errors = []
        data = {
            "id": "x", "type": "skill_contract", "skill": "s", "goal": "g",
            "domain_type": "physical", "verification_type": "human_rubric",
            "criterio": "criterio observable", "instrument_frozen": "true",
            "baseline_date": "2026-07-28", "checkpoint_date": "2026-08-27",
            "status": "draft",
        }
        data.update(overrides)
        vc.validate_node("p.md", data, errors)
        return errors

    def test_baseline_date_with_hour_accepted(self):
        errs = self._skill_contract(baseline_date="2026-07-28T10:00:00",
                                    checkpoint_date="2026-08-27T10:00:00")
        self.assertFalse([e for e in errs if "fecha ISO" in e or "posterior a" in e])

    def test_checkpoint_date_with_hour_accepted(self):
        errs = self._skill_contract(baseline_date="2026-07-28",
                                    checkpoint_date="2026-08-27T10:00:00")
        self.assertFalse([e for e in errs if "fecha ISO" in e or "posterior a" in e])

    def test_baseline_date_garbage_still_rejected(self):
        # la permision es de formato (acepta hora), no de validez: basura sigue error
        errs = self._skill_contract(baseline_date="no-es-fecha",
                                    checkpoint_date="2026-08-27")
        self.assertTrue(any("baseline_date no es fecha ISO valida" in e for e in errs))

    # --- BUG 5 (BAJA): padre sin criterio -> un solo error ---

    def test_parent_without_criterio_single_error(self):
        # skill_contract SIN criterio (campo requerido ausente) + sesion que lo
        # referencia con criterio propio -> UN solo error (falta campo requerido),
        # sin divergencia espuria.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d, "sub.md", [
                "id: sub_x", "type: subskill", "skill: s", "domain_type: physical",
                "verification_type: instrumented", "status: draft",
            ])
            # skill_contract sin el campo criterio
            write_md(d, "sc.md", [
                "id: sk_c", "type: skill_contract", "skill: s", "goal: g",
                "subskills: []", "domain_type: physical",
                "verification_type: human_rubric",
                # criterio ausente a proposito
                "instrument_frozen: true",
                "baseline_date: 2026-07-28", "checkpoint_date: 2026-08-27",
                "status: draft",
            ])
            write_md(d, "session.md", [
                "id: sess1", "type: session_contract", "skill: s",
                "subskill: sub_x", "skill_contract: sk_c", "status: draft",
                'criterio: "tocar 3 acordes sin error"',
                "tools_needed: []",
            ])
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 1, out)
            errs = self._error_lines(out)
            # un solo error: el del campo requerido del padre
            self.assertEqual(len(errs), 1, out)
            self.assertIn("falta campo requerido 'criterio'", errs[0])
            self.assertNotIn("diverge", out)


class TestConfirmSFixes(unittest.TestCase):
    """Cobertura de BUG 4 (FIX-CONFIRM-S) en scripts/validate_contracts.py:
    para nodos type: skill_index, el id debe coincidir con el nombre del
    directorio que contiene el archivo (convencion <id>/index.md). Una clase
    agrupada, sin tocar los oraculos congelados existentes."""

    def _run_main(self, *roots):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vc.main(["validate_contracts.py", *roots])
        return rc, buf.getvalue()

    def _error_lines(self, output):
        return [ln.strip()[2:] for ln in output.splitlines()
                if ln.strip().startswith("- ")]

    def test_skill_index_id_matches_dir_ok(self):
        # id 'news' dentro del dir 'news' -> valido
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "news", "index.md",
                     ["id: news", "type: skill_index", "domain_type: physical"])
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)

    def test_skill_index_id_mismatch_dir_error_reports_both(self):
        # id 'news.' dentro del dir 'news' (el caso BUG 12: el OS stripueo el
        # punto del directorio pero el id lo conserva) -> error con ambos valores
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "news", "index.md",
                     ["id: news.", "type: skill_index", "domain_type: physical"])
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 1, out)
            errs = self._error_lines(out)
            self.assertEqual(len(errs), 1, out)
            self.assertIn("skill_index", errs[0])
            self.assertIn("news.", errs[0])      # el id
            self.assertIn("news", errs[0])        # el directorio
            self.assertIn("coincidir", errs[0])

    def test_skill_index_id_missing_only_required_error(self):
        # si id falta, no se emite el error de id/dir (ya lo reporta el chequeo
        # de campo requerido); un solo error.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "news", "index.md",
                     ["type: skill_index", "domain_type: physical"])
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 1, out)
            errs = self._error_lines(out)
            self.assertEqual(len(errs), 1, out)
            self.assertIn("falta campo requerido 'id'", errs[0])
            self.assertNotIn("coincidir", out)

    def test_skill_index_filename_not_index_still_checks_dir(self):
        # el chequeo es id == directorio, no id == nombre de archivo: un
        # skill_index en <id>/otro.md con id == dir sigue siendo valido.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "ukulele", "otro.md",
                     ["id: ukulele", "type: skill_index", "domain_type: physical"])
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)

    def test_skill_index_rename_dir_without_id_update_caught(self):
        # rename manual de carpeta olvidando actualizar el id: dir 'ukulele2'
        # con id 'ukulele' -> error (caza la clase de divergencia que valida
        # este chequeo mas alla del BUG 12).
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d / "ukulele2", "index.md",
                     ["id: ukulele", "type: skill_index", "domain_type: physical"])
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 1, out)
            errs = self._error_lines(out)
            self.assertEqual(len(errs), 1, out)
            self.assertIn("ukulele", errs[0])
            self.assertIn("ukulele2", errs[0])

    def test_real_skill_indexes_match_their_dirs(self):
        # Caso real: knowledge/ukulele e knowledge/n8n deben seguir en verde
        # (id == dir). Afirmacion explicita de la invariante sobre datos reales.
        rc, out = self._run_main(str(ROOT / "knowledge"), str(ROOT / "contracts"))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("coincidir", out)


class TestInlineComments(unittest.TestCase):
    """FIX-COMENTARIOS-INLINE: parse_frontmatter reconoce comentarios inline
    estilo YAML. Un `#` inicia comentario SOLO si lo precede un espacio en
    blanco o abre el valor; dentro de comillas es literal. El recorte va
    ANTES de quitar comillas y ANTES de parsear listas. Cobertura de la tabla
    de casos del fix mas los casos extra pedidos."""

    def _parse(self, lines):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p = write_md(d, "n.md", lines)
            return vc.parse_frontmatter(p)

    # --- tabla de casos del fix ---

    def test_value_then_inline_comment_stripped(self):
        data, err = self._parse(["id: x", "status: draft   # nota"])
        self.assertIsNone(err)
        self.assertEqual(data["status"], "draft")

    def test_hash_without_preceding_space_is_literal(self):
        # `abc#def`: sin espacio antes del # -> NO es comentario
        data, _ = self._parse(["id: x", "tag: abc#def"])
        self.assertEqual(data["tag"], "abc#def")

    def test_hash_inside_double_quotes_is_literal(self):
        data, _ = self._parse(["id: x", 'criterio: "20 rodajas, #1 y #2"'])
        self.assertEqual(data["criterio"], "20 rodajas, #1 y #2")

    def test_quoted_value_then_inline_comment(self):
        # el comentario se recorta DESPUES de cerrar las comillas
        data, _ = self._parse(["id: x", 'criterio: "algo"   # nota'])
        self.assertEqual(data["criterio"], "algo")

    def test_list_then_inline_comment(self):
        # el recorte va ANTES de parsear los corchetes
        data, _ = self._parse(["id: x", "depends_on: [a, b]   # ids"])
        self.assertEqual(data["depends_on"], ["a", "b"])

    def test_only_comment_yields_empty_value(self):
        # `foo:   # solo comentario` -> valor vacio (las validaciones de
        # campo requerido lo cazan como hoy)
        data, _ = self._parse(["id: x", "foo:   # solo comentario"])
        self.assertEqual(data["foo"], "")

    # --- casos extra pedidos ---

    def test_hash_glued_no_space_not_stripped(self):
        # `draft# x`: el # esta pegado al valor sin espacio -> NO se recorta
        data, _ = self._parse(["id: x", "status: draft# x"])
        self.assertEqual(data["status"], "draft# x")

    def test_multiple_hashes_in_same_line(self):
        # sin comillas: corta en el primer # precedido por espacio
        data, _ = self._parse(["id: x", "status: draft # nota # otra"])
        self.assertEqual(data["status"], "draft")
        # con comillas: los # internos son literales, el externo inicia comentario
        data, _ = self._parse(["id: x", 'criterio: "a #1 y #2" # nota'])
        self.assertEqual(data["criterio"], "a #1 y #2")

    def test_hash_as_first_char_of_value_is_comment(self):
        # el # abre el valor (primer caracter tras el strip) -> comentario -> vacio
        data, _ = self._parse(["id: x", "tag: # encabezado"])
        self.assertEqual(data["tag"], "")

    def test_single_quotes_also_literal(self):
        # comilla simple ademas de doble: el # dentro es literal
        data, _ = self._parse(["id: x", "goal: 'tocar #1 bien' # nota"])
        self.assertEqual(data["goal"], "tocar #1 bien")

    def test_hash_inside_quotes_plus_comment_outside(self):
        # el caso que mas vale: # dentro de comillas (literal) Y comentario afuera
        data, _ = self._parse([
            "id: x",
            'criterio: "20 rodajas, #1 y #2"   # nota externa',
        ])
        self.assertEqual(data["criterio"], "20 rodajas, #1 y #2")

    def test_inline_comment_does_not_break_full_line_comment_skip(self):
        # regresion guard: una linea que empieza con # sigue siendo comentario
        # de linea completa (no se confunde con el inline)
        data, _ = self._parse(["# comentario completo", "id: x", "type: subskill"])
        self.assertNotIn("# comentario completo", data)
        self.assertEqual(data["id"], "x")


class TestTemplatesValidateAfterPlaceholderFill(unittest.TestCase):
    """El punto de todo el fix: copiar una plantilla de templates/ TAL CUAL,
    reemplazar unicamente los placeholders, y que validate_contracts la acepte
    en exit 0. Hoy (pre-fix) esto revienta con ~200 errores porque las
    plantillas usan comentarios inline que el parser no reconocia."""

    def _run_main(self, *roots):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vc.main(["validate_contracts.py", *roots])
        return rc, buf.getvalue()

    def _filled(self, template_name, replacements):
        """Lee una plantilla de templates/ y aplica reemplazos de placeholders.
        replacements es lista de (viejo, nuevo) aplicada en orden."""
        src = ROOT / "templates" / template_name
        text = src.read_text(encoding="utf-8")
        for old, new in replacements:
            text = text.replace(old, new)
        return text

    def test_subskill_template_validates(self):
        # subskill.md: reemplazar solo <slug-unico> y <skill-slug>
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            text = self._filled("subskill.md", [
                ("<slug-unico>", "chord-transitions"),
                ("<skill-slug>", "ukulele"),
            ])
            (d / "sub.md").write_text(text, encoding="utf-8")
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)

    def test_skill_contract_template_validates(self):
        # skill-contract.md: necesita valores reales en fechas y criterio.
        # Las dos fechas usan el mismo placeholder <yyyy-mm-dd>, asi que se
        # reemplazan por el par `campo: <placeholder>` para distinguirlas
        # (str.replace reemplaza TODAS las ocurrencias; dos replaces sueltos
        # dejarian ambas fechas iguales y reventaria el chequeo de orden).
        # <yyyy-mm-dd> se reemplaza antes que <yyyy-mm> para que el prefijo
        # mas corto no canibalice al largo.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            text = self._filled("skill-contract.md", [
                ("baseline_date: <yyyy-mm-dd>", "baseline_date: 2026-07-28"),
                ("checkpoint_date: <yyyy-mm-dd>", "checkpoint_date: 2026-08-27"),
                ("<yyyy-mm>", "2026-08"),
                ("<skill-slug>", "ukulele"),
                ("<commit-sha>", "abc123def"),
                ('<meta de desempeño en una sola oración>', "tocar 3 canciones"),
                ('<criterio binario u observable, con umbral si aplica>',
                 "secuencia C-G-Am-F, 4 repeticiones, 80bpm"),
            ])
            (d / "sc.md").write_text(text, encoding="utf-8")
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)

    def test_session_contract_template_validates(self):
        # session-contract.md: su campo `subskill` referencia un nodo que debe
        # existir. Por eso va acompanado de un subskill (tambien de plantilla)
        # con id coincidente. Reemplazo: <yyyy-mm-dd> antes que nada.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sub_text = self._filled("subskill.md", [
                ("<slug-unico>", "chord-transitions"),
                ("<skill-slug>", "ukulele"),
            ])
            (d / "sub.md").write_text(sub_text, encoding="utf-8")
            sess_text = self._filled("session-contract.md", [
                ("<yyyy-mm-dd>", "2026-07-28"),
                ("<subskill-slug>", "chord-transitions"),
                ("<skill-slug>", "ukulele"),
                ('<criterio binario u observable, con umbral si aplica>',
                 "secuencia C-G-Am-F, 4 repeticiones, 80bpm"),
            ])
            (d / "session.md").write_text(sess_text, encoding="utf-8")
            rc, out = self._run_main(str(d))
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)


class TestSinFechaLimite(unittest.TestCase):
    """FEAT-SIN-FECHA-LIMITE: checkpoint_date: null = seguimiento abierto, sin
    fecha limite. El campo sigue siendo requerido (un null explicito es un acto
    deliberado, distinto de omitirlo). Con null el chequeo de orden no aplica
    (no hay nada que ordenar contra el baseline); todo lo demas del contrato se
    valida igual. Llamadas directas a validate_node + un end-to-end via main().
    Clase agrupada, sin tocar los oraculos congelados existentes."""

    BASE = {
        "id": "x", "type": "skill_contract", "skill": "s", "goal": "g",
        "domain_type": "physical", "verification_type": "human_rubric",
        "criterio": "criterio observable", "instrument_frozen": "true",
        "status": "draft",
    }

    def _validate(self, **overrides):
        errors = []
        data = {**self.BASE, **overrides}
        vc.validate_node("p.md", data, errors)
        return errors

    def _run_main(self, knowledge_dir):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vc.main(["validate_contracts.py", str(knowledge_dir)])
        return rc, buf.getvalue()

    # --- checkpoint_date: null valida (no hay nada que ordenar) ---

    def test_open_checkpoint_null_valid(self):
        errs = self._validate(baseline_date="2026-07-28", checkpoint_date="null")
        self.assertFalse(
            [e for e in errs if "fecha ISO" in e or "posterior a" in e],
            f"checkpoint_date null no deberia dar error de fecha/orden: {errs}",
        )

    def test_open_checkpoint_capital_none_also_valid(self):
        # el parser deja el literal como cadena; aceptamos "None" ademas de "null"
        errs = self._validate(baseline_date="2026-07-28", checkpoint_date="None")
        self.assertFalse(
            [e for e in errs if "fecha ISO" in e or "posterior a" in e],
            f"checkpoint_date None no deberia dar error: {errs}",
        )

    def test_open_checkpoint_quoted_null_valid_via_parser(self):
        # alguien que escribe `checkpoint_date: "null"` (con comillas) tambien
        # declara abierto: parse_frontmatter stripuea las comillas y queda
        # "null". Es un asunto del parser, asi que se prueba end-to-end via
        # main() (que es la ruta real), no con llamada directa a validate_node.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d, "sc.md", [
                "id: abierto-q", "type: skill_contract", "skill: ukulele",
                "goal: tocar 3 canciones", "subskills: []",
                "domain_type: physical", "verification_type: proxy",
                'criterio: "secuencia C-G-Am-F, 4 repeticiones, 80bpm"',
                "instrument_frozen: true",
                "instrument_frozen_at: abc123def",
                "baseline_date: 2026-07-28", 'checkpoint_date: "null"',
                "status: draft",
            ])
            rc, out = self._run_main(d)
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)
            self.assertNotIn("checkpoint_date no es fecha ISO", out)
            self.assertNotIn("posterior a baseline_date", out)

    # --- el chequeo de orden NO se aplica con null ---

    def test_open_checkpoint_skips_order_check(self):
        # baseline "futura" relativa a cualquier checkpoint imaginario: con
        # null no hay contra que ordenar, asi que NO se dispara el de orden.
        errs = self._validate(baseline_date="2030-12-31", checkpoint_date="null")
        self.assertFalse([e for e in errs if "posterior a" in e])

    # --- checkpoint_date AUSENTE sigue siendo error (regresion guard) ---

    def test_open_checkpoint_absent_still_required_error(self):
        # la novedad es `null` valido, NO "el campo es opcional": ausente sigue
        # siendo error como hoy. Declarar "sin fecha" != olvidarse el campo.
        errs = self._validate(baseline_date="2026-07-28")
        self.assertTrue(any("falta campo requerido 'checkpoint_date'" in e for e in errs))

    def test_open_checkpoint_empty_string_still_required_error(self):
        # `checkpoint_date:` sin valor (cadena vacia) != null explicito: es
        # ausencia y se reporta como campo requerido faltante.
        errs = self._validate(baseline_date="2026-07-28", checkpoint_date="")
        self.assertTrue(any("falta campo requerido 'checkpoint_date'" in e for e in errs))

    # --- un contrato con checkpoint real sigue exigiendo el orden ---

    def test_real_checkpoint_still_requires_order(self):
        errs = self._validate(baseline_date="2026-08-27", checkpoint_date="2026-07-28")
        self.assertTrue(any("debe ser posterior a baseline_date" in e for e in errs))

    def test_real_checkpoint_equal_baseline_still_error(self):
        errs = self._validate(baseline_date="2026-07-28", checkpoint_date="2026-07-28")
        self.assertTrue(any("debe ser posterior a baseline_date" in e for e in errs))

    # --- con null, todo lo demas del contrato se valida igual ---

    def test_open_checkpoint_does_not_suppress_vague_criterio(self):
        errs = self._validate(baseline_date="2026-07-28", checkpoint_date="null",
                              criterio="tocar mejor que antes")
        self.assertTrue(any("lenguaje vago" in e for e in errs))

    def test_open_checkpoint_does_not_suppress_missing_baseline_error(self):
        # null en checkpoint no perdona un baseline ausente: baseline sigue
        # siendo obligatorio y una fecha real.
        errs = self._validate(checkpoint_date="null")
        self.assertTrue(any("falta campo requerido 'baseline_date'" in e for e in errs))

    def test_open_checkpoint_baseline_garbage_still_error(self):
        errs = self._validate(baseline_date="no-es-fecha", checkpoint_date="null")
        self.assertTrue(any("baseline_date no es fecha ISO valida" in e for e in errs))
        # y no se agrega un error de orden encima (no hay checkpoint que ordenar)
        self.assertFalse([e for e in errs if "posterior a" in e])

    # --- end-to-end via main(): contrato activo con null en verde ---

    def test_main_active_contract_with_null_checkpoint_validates(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d, "sc.md", [
                "id: abierto-2026", "type: skill_contract", "skill: ukulele",
                "goal: tocar 3 canciones", "subskills: []",
                "domain_type: physical", "verification_type: proxy",
                'criterio: "secuencia C-G-Am-F, 4 repeticiones, 80bpm"',
                "instrument_frozen: true",
                "instrument_frozen_at: abc123def",
                "baseline_date: 2026-07-28", "checkpoint_date: null",
                "status: active",
            ])
            rc, out = self._run_main(d)
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)


class TestDiscontinuedStatus(unittest.TestCase):
    """FEAT-DISCONTINUED: nuevo estado TERMINAL `discontinued` en
    VALID_SKILL_CONTRACT_STATUS. Significa que el compromiso o seguimiento se
    cerro SIN llegar al checkpoint. Valida como cualquier skill_contract:
    sigue exigiendo el resto de los campos requeridos; no es una via para
    esquivar la forma. Llamadas directas a validate_node + un end-to-end via
    main(). Clase agrupada, sin tocar los oraculos congelados existentes."""

    BASE = {
        "id": "x", "type": "skill_contract", "skill": "s", "goal": "g",
        "domain_type": "physical", "verification_type": "human_rubric",
        "criterio": "criterio observable", "instrument_frozen": "true",
        "baseline_date": "2026-07-28", "checkpoint_date": "2026-08-27",
        "status": "discontinued",
    }

    def _validate(self, **overrides):
        errors = []
        data = {**self.BASE, **overrides}
        vc.validate_node("p.md", data, errors)
        return errors

    def _run_main(self, knowledge_dir):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vc.main(["validate_contracts.py", str(knowledge_dir)])
        return rc, buf.getvalue()

    def test_discontinued_status_is_valid(self):
        errs = self._validate()
        self.assertFalse([e for e in errs if "status invalido" in e],
                        f"discontinued es un status valido: {errs}")

    def test_discontinued_still_requires_other_fields(self):
        # discontinued no es una via para esquivar la forma: sigue exigiendo los
        # campos requeridos de cualquier skill_contract.
        data = {"type": "skill_contract", "status": "discontinued"}
        errors = []
        vc.validate_node("p.md", data, errors)
        for field in ("id", "skill", "goal", "domain_type", "verification_type",
                      "criterio", "instrument_frozen", "baseline_date",
                      "checkpoint_date"):
            self.assertTrue(any(f"falta campo requerido '{field}'" in e for e in errors),
                            f"debia exigir '{field}' incluso en discontinued: {errors}")
        # y no hay error de status invalido
        self.assertFalse([e for e in errors if "status invalido" in e])

    def test_discontinued_keeps_date_order_check(self):
        # el chequeo de orden de fechas no depende del status: sigue aplicando
        # con un checkpoint real (no null).
        errs = self._validate(baseline_date="2026-08-27", checkpoint_date="2026-07-28")
        self.assertTrue(any("debe ser posterior a baseline_date" in e for e in errs))

    def test_discontinued_with_null_checkpoint_validates(self):
        # un discontinued de seguimiento abierto (checkpoint_date: null) valida:
        # null es un acto deliberado, no omision, y no hay nada que ordenar.
        errs = self._validate(checkpoint_date="null")
        self.assertFalse(
            [e for e in errs if "fecha ISO" in e or "posterior a" in e],
            f"checkpoint null no deberia dar error de fecha/orden: {errs}",
        )

    def test_main_discontinued_contract_validates(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_md(d, "sc.md", [
                "id: disco-2026", "type: skill_contract", "skill: ukulele",
                "goal: tocar 3 canciones", "subskills: []",
                "domain_type: physical", "verification_type: proxy",
                'criterio: "secuencia C-G-Am-F, 4 repeticiones, 80bpm"',
                "instrument_frozen: true",
                "instrument_frozen_at: abc123def",
                "baseline_date: 2026-07-28", "checkpoint_date: 2026-08-27",
                "status: discontinued",
            ])
            rc, out = self._run_main(d)
            self.assertEqual(rc, 0, out)
            self.assertIn("OK", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)