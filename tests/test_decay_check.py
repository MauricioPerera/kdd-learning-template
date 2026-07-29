#!/usr/bin/env python3
"""
Oracle congelado para scripts/decay_check.py.

Usa fixtures .md temporales en un directorio temporal creado por testfixture.
NUNCA toca knowledge/ real ni corre --apply contra el arbol del proyecto.

Cubre:
  - regex de status / last_verified / review_after_days
  - calculo de vencimiento por fecha (limite exacto >=, dia antes, vencido inmediato)
  - escritura con --apply (incluido el bug del str.replace ciego vs regex tolerante)
  - skip de nodos no-verified, last_verified null/invalido, campos faltantes,
    review_after_days no numerico
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

# Importar decay_check desde scripts/
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, os.path.abspath(_SCRIPTS))
import decay_check  # noqa: E402


def _frontmatter(extra):
    """Frontmatter minimo de un subskill. extra sobreescribe/anade campos."""
    base = {
        "id": "x",
        "type": "subskill",
        "status": "verified",
        "review_after_days": "14",
        "last_verified": (date.today() - timedelta(days=30)).isoformat(),
    }
    base.update(extra)
    lines = ["---"]
    for k, v in base.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append("## Qué es")
    lines.append("")
    lines.append("Prosa de prueba.")
    return "\n".join(lines) + "\n"


def _run(knowledge_dir, apply=False):
    argv = ["decay_check", str(knowledge_dir)] + (["--apply"] if apply else [])
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = decay_check.main(argv)
    return rc, buf.getvalue()


class DecayCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self._mkdtemp_safe())
        (self.tmp / "sub").mkdir(exist_ok=True)

    def _mkdtemp_safe(self):
        import tempfile
        return tempfile.mkdtemp(prefix="decay_test_")

    def _write(self, name, content):
        p = self.tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    # --- computo de fecha ---

    def test_exact_limit_is_due(self):
        """hoy - last_verified == review_after_days => vencido (>= inclusivo)."""
        rad = 14
        lv = (date.today() - timedelta(days=rad)).isoformat()
        self._write("a.md", _frontmatter({"review_after_days": str(rad), "last_verified": lv}))
        rc, out = _run(self.tmp)
        self.assertEqual(rc, 0)
        self.assertIn("1 nodo(s)", out)

    def test_one_day_before_limit_not_due(self):
        """hoy - last_verified == review_after_days - 1 => NO vencido."""
        rad = 14
        lv = (date.today() - timedelta(days=rad - 1)).isoformat()
        self._write("a.md", _frontmatter({"review_after_days": str(rad), "last_verified": lv}))
        rc, out = _run(self.tmp)
        self.assertEqual(rc, 0)
        self.assertIn("ningun nodo vencido", out)

    def test_review_after_days_zero_immediately_due(self):
        """review_after_days: 0 => vencido inmediato (by-design)."""
        lv = date.today().isoformat()
        self._write("a.md", _frontmatter({"review_after_days": "0", "last_verified": lv}))
        rc, out = _run(self.tmp)
        self.assertEqual(rc, 0)
        self.assertIn("1 nodo(s)", out)

    # --- apply / dry-run ---

    def test_dry_run_does_not_modify(self):
        p = self._write("a.md", _frontmatter({}))
        before = p.read_text(encoding="utf-8")
        rc, out = _run(self.tmp, apply=False)
        self.assertEqual(rc, 0)
        self.assertEqual(before, p.read_text(encoding="utf-8"))
        self.assertIn("dry-run", out)

    def test_apply_updates_verified_due_node(self):
        p = self._write("a.md", _frontmatter({}))
        rc, out = _run(self.tmp, apply=True)
        self.assertEqual(rc, 0)
        text = p.read_text(encoding="utf-8")
        self.assertIn("status: needs_review", text)
        self.assertNotIn("status: verified", text)
        self.assertIn("actualizados", out)

    def test_apply_on_needs_review_not_touched(self):
        """Nodo ya needs_review (vencido) no debe ser tocado."""
        p = self._write(
            "a.md",
            _frontmatter({"status": "needs_review"}),
        )
        before = p.read_text(encoding="utf-8")
        rc, out = _run(self.tmp, apply=True)
        self.assertEqual(rc, 0)
        self.assertEqual(before, p.read_text(encoding="utf-8"))
        self.assertIn("ningun nodo vencido", out)

    # --- el bug del str.replace ciego vs regex tolerante ---

    def test_apply_spacing_mismatch_still_updates(self):
        """status con dos espacios: el regex matchea, el apply debe reescribir.

        Bug demostrado: con str.replace('status: verified', ..., 1) el replace
        no encontraba la subcadena (spacing distinto) y dejaba el archivo intacto
        aun reportandolo como actualizado. El fix opera sobre el span del grupo.
        """
        rad = 14
        lv = (date.today() - timedelta(days=rad)).isoformat()
        content = (
            "---\n"
            "id: x\n"
            "type: subskill\n"
            f"status:  verified\n"  # dos espacios
            f"review_after_days: {rad}\n"
            f"last_verified: {lv}\n"
            "---\n\nProsa.\n"
        )
        p = self._write("a.md", content)
        rc, out = _run(self.tmp, apply=True)
        self.assertEqual(rc, 0)
        text = p.read_text(encoding="utf-8")
        self.assertIn("needs_review", text)
        self.assertNotRegex(text, r"status:\s+verified\b")
        self.assertIn("actualizados", out)

    def test_apply_value_on_next_line_still_updates(self):
        """Valor en la linea siguiente: \\s* traga newline, apply debe reescribir."""
        rad = 14
        lv = (date.today() - timedelta(days=rad)).isoformat()
        content = (
            "---\n"
            "id: x\n"
            "type: subskill\n"
            "status:\n"
            "  verified\n"
            f"review_after_days: {rad}\n"
            f"last_verified: {lv}\n"
            "---\n\nProsa.\n"
        )
        p = self._write("a.md", content)
        rc, out = _run(self.tmp, apply=True)
        self.assertEqual(rc, 0)
        text = p.read_text(encoding="utf-8")
        self.assertIn("needs_review", text)
        # el valor del campo status ya no es 'verified' (last_verified lo contiene,
        # por eso no podemos assertNotRegex global de 'verified')
        self.assertRegex(text, r"(?m)^\s*needs_review\s*$")

    def test_prose_status_verified_not_touched(self):
        """Subcadena 'status: verified' en prosa no debe ser alterada por apply."""
        rad = 14
        lv = (date.today() - timedelta(days=rad)).isoformat()
        content = (
            "---\n"
            "id: x\n"
            "type: subskill\n"
            "status: verified\n"
            f"review_after_days: {rad}\n"
            f"last_verified: {lv}\n"
            "---\n\n"
            "## Notas\n\n"
            "El campo status: verified indica verificacion previa.\n"
        )
        p = self._write("a.md", content)
        rc, out = _run(self.tmp, apply=True)
        self.assertEqual(rc, 0)
        text = p.read_text(encoding="utf-8")
        # frontmatter actualizado
        self.assertRegex(text, r"(?m)^status: needs_review$")
        # prosa conservada literal
        self.assertIn("El campo status: verified indica verificacion previa.", text)

    # --- skips / filtros ---

    def test_non_verified_status_ignored(self):
        for st in ("draft", "practicing", "needs_review"):
            with self.subTest(status=st):
                d = Path(self._mkdtemp_safe())
                (d / "a.md").write_text(
                    _frontmatter({"status": st}), encoding="utf-8"
                )
                rc, out = _run(d)
                self.assertEqual(rc, 0)
                self.assertIn("ningun nodo vencido", out)

    def test_last_verified_null_skipped(self):
        self._write("a.md", _frontmatter({"last_verified": "null"}))
        rc, out = _run(self.tmp)
        self.assertEqual(rc, 0)
        self.assertIn("ningun nodo vencido", out)

    def test_last_verified_none_and_empty_skipped(self):
        for val in ("None", ""):
            with self.subTest(val=val):
                d = Path(self._mkdtemp_safe())
                content = _frontmatter({"last_verified": val or " "})
                if val == "":
                    # frontmatter vacio: reescribimos la linea a last_verified: (vacio)
                    content = content.replace("last_verified:  ", "last_verified:\n")
                (d / "a.md").write_text(content, encoding="utf-8")
                rc, out = _run(d)
                self.assertEqual(rc, 0)
                self.assertIn("ningun nodo vencido", out)

    def test_invalid_last_verified_skipped_no_crash(self):
        self._write("a.md", _frontmatter({"last_verified": "not-a-date"}))
        rc, out = _run(self.tmp)
        self.assertEqual(rc, 0)
        self.assertIn("ningun nodo vencido", out)

    def test_invalid_date_value_skipped_no_crash(self):
        """Fecha ISO con mes/dia invalido => fromisoformat ValueError => skip."""
        self._write("a.md", _frontmatter({"last_verified": "2024-13-45"}))
        rc, out = _run(self.tmp)
        self.assertEqual(rc, 0)
        self.assertIn("ningun nodo vencido", out)

    def test_review_after_days_non_numeric_skipped(self):
        self._write("a.md", _frontmatter({"review_after_days": "soon"}))
        rc, out = _run(self.tmp)
        self.assertEqual(rc, 0)
        self.assertIn("ningun nodo vencido", out)

    def test_missing_fields_skipped(self):
        # sin review_after_days
        content = (
            "---\n"
            "id: x\n"
            "type: subskill\n"
            "status: verified\n"
            f"last_verified: {(date.today() - timedelta(days=30)).isoformat()}\n"
            "---\n\nProsa.\n"
        )
        self._write("a.md", content)
        rc, out = _run(self.tmp)
        self.assertEqual(rc, 0)
        self.assertIn("ningun nodo vencido", out)

    def test_non_subskill_ignored(self):
        """Archivo sin 'type: subskill' se salta de entrada."""
        content = (
            "---\n"
            "id: x\n"
            "type: mental_model\n"
            "status: verified\n"
            "review_after_days: 14\n"
            f"last_verified: {(date.today() - timedelta(days=30)).isoformat()}\n"
            "---\n\nProsa.\n"
        )
        self._write("a.md", content)
        rc, out = _run(self.tmp)
        self.assertEqual(rc, 0)
        self.assertIn("ningun nodo vencido", out)

    def test_multiple_files_only_due_flagged(self):
        rad = 14
        due_lv = (date.today() - timedelta(days=rad)).isoformat()
        fresh_lv = (date.today() - timedelta(days=rad - 5)).isoformat()
        self._write("due.md", _frontmatter({"last_verified": due_lv}))
        self._write("fresh.md", _frontmatter({"last_verified": fresh_lv}))
        rc, out = _run(self.tmp)
        self.assertEqual(rc, 0)
        self.assertIn("1 nodo(s)", out)
        self.assertIn("due.md", out)
        self.assertNotIn("fresh.md", out)


if __name__ == "__main__":
    unittest.main()