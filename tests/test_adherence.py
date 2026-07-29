"""Oracle congelado para scripts/adherence.py.

Black-box sobre main() con logs temporales. No toca logs/progress.md real.
stdlib solamente: unittest + tempfile + io + contextlib.
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta

# Hacer importable el modulo scripts/adherence.py
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import adherence  # noqa: E402


def run_main(lines, extra_args=None, fake_now=None):
    """Escribe `lines` a un temp log, corre adherence.main, devuelve (rc, stdout)."""
    extra_args = extra_args or []
    fd, path = tempfile.mkstemp(suffix=".log", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        argv = ["adherence", path] + extra_args
        buf = io.StringIO()
        target = adherence.datetime if fake_now is None else _FakeDateTime(fake_now)
        orig_datetime = adherence.datetime
        adherence.datetime = target
        try:
            with redirect_stdout(buf):
                rc = adherence.main(argv)
        finally:
            adherence.datetime = orig_datetime
        return rc, buf.getvalue()
    finally:
        os.remove(path)


class _FakeDateTime:
    """Reemplaza datetime en adherence para fijar `now()` en tests."""

    def __init__(self, now_dt):
        self._now = now_dt

    def now(self):
        return self._now

    # Re-exportar lo que adherence usa directamente.
    fromisoformat = staticmethod(datetime.fromisoformat)
    date = datetime.date


def parse_stdout(out):
    """Convierte la salida de adherence en un dict de campos."""
    d = {}
    for line in out.strip().splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            d[k.strip()] = v.strip()
    return d


class AdherenceTests(unittest.TestCase):
    # --- parse_log_line / descarte de lineas invalidas ---

    def test_linea_que_empieza_con_2_pero_no_es_timestamp_se_descarta(self):
        # "20 cosas para practicar" empieza con "2" pero no es ISO.
        # Debe descartarse sin crashear; la otra entrada valida se cuenta.
        rc, out = run_main([
            "20 cosas para practicar",
            "2026-07-28T18:00:00 | skill=ukulele | event=attempted",
        ])
        self.assertEqual(rc, 0)
        d = parse_stdout(out)
        self.assertEqual(d["sesiones registradas"], "1")

    def test_linea_vacia_y_encabezado_se_descartan(self):
        rc, out = run_main([
            "# Log de evidencia",
            "",
            "Formato: algo",
            "2026-07-28T18:00:00 | skill=ukulele | event=attempted",
        ])
        self.assertEqual(rc, 0)
        self.assertEqual(parse_stdout(out)["sesiones registradas"], "1")

    # --- racha / best_streak ---

    def test_dos_sesiones_mismo_dia_cuentan_como_1_dia(self):
        rc, out = run_main([
            "2026-07-28T09:00:00 | skill=u | event=attempted",
            "2026-07-28T20:00:00 | skill=u | event=attempted",
        ], fake_now=datetime(2026, 7, 28, 23, 0))
        self.assertEqual(rc, 0)
        d = parse_stdout(out)
        self.assertEqual(d["sesiones registradas"], "2")
        self.assertEqual(d["dias distintos con actividad"], "1")
        self.assertEqual(d["racha mas larga (dias consecutivos)"], "1")

    def test_racha_corta_en_gap_y_best_streak_es_la_mas_larga(self):
        # Run de 3 dias (28,29,30), gap de 2 dias, run de 2 dias (02,03).
        # best_streak debe ser 3, no 2 (la ultima) ni 5 (inflada).
        rc, out = run_main([
            "2026-07-28T09:00:00 | skill=u | event=attempted",
            "2026-07-29T09:00:00 | skill=u | event=attempted",
            "2026-07-30T09:00:00 | skill=u | event=attempted",
            "2026-08-02T09:00:00 | skill=u | event=attempted",
            "2026-08-03T09:00:00 | skill=u | event=attempted",
        ], fake_now=datetime(2026, 8, 3, 23, 0))
        self.assertEqual(rc, 0)
        d = parse_stdout(out)
        self.assertEqual(d["dias distintos con actividad"], "5")
        self.assertEqual(d["racha mas larga (dias consecutivos)"], "3")

    def test_un_solo_dia_de_actividad_best_streak_es_1(self):
        rc, out = run_main([
            "2026-07-28T18:00:00 | skill=u | event=attempted",
        ], fake_now=datetime(2026, 7, 28, 23, 0))
        self.assertEqual(rc, 0)
        d = parse_stdout(out)
        self.assertEqual(d["racha mas larga (dias consecutivos)"], "1")
        self.assertEqual(d["dias distintos con actividad"], "1")

    def test_log_no_ordenado_se_ordena_cronologicamente(self):
        # Entradas desordenadas; la ultima sesion debe ser la mayor fecha.
        rc, out = run_main([
            "2026-07-30T09:00:00 | skill=u | event=attempted",
            "2026-07-28T09:00:00 | skill=u | event=attempted",
            "2026-07-29T09:00:00 | skill=u | event=attempted",
        ], fake_now=datetime(2026, 7, 30, 23, 0))
        self.assertEqual(rc, 0)
        d = parse_stdout(out)
        self.assertEqual(d["ultima sesion"], "2026-07-30 (0 dias atras)")
        self.assertEqual(d["racha mas larga (dias consecutivos)"], "3")

    # --- timezones mixtos (BUG real: sort crasheaba) ---

    def test_timestamps_mixtos_aware_y_naive_no_crashean(self):
        # Una naive y otra con +00:00 en dias distintos. Antes del fix,
        # entries.sort() levantaba TypeError al comparar aware vs naive.
        rc, out = run_main([
            "2026-07-27T18:00:00 | skill=u | event=attempted",
            "2026-07-28T10:00:00+00:00 | skill=u | event=attempted",
        ], fake_now=datetime(2026, 7, 28, 23, 0))
        self.assertEqual(rc, 0)
        d = parse_stdout(out)
        self.assertEqual(d["dias distintos con actividad"], "2")
        self.assertEqual(d["racha mas larga (dias consecutivos)"], "2")
        self.assertEqual(d["ultima sesion"], "2026-07-28 (0 dias atras)")

    def test_timestamp_aware_unico_funciona(self):
        rc, out = run_main([
            "2026-07-28T10:00:00+00:00 | skill=u | event=attempted",
        ], fake_now=datetime(2026, 7, 28, 23, 0))
        self.assertEqual(rc, 0)
        d = parse_stdout(out)
        self.assertEqual(d["ultima sesion"], "2026-07-28 (0 dias atras)")

    # --- filtros ---

    def test_filtro_skill_que_no_matchea_imprime_sin_entradas_y_rc0(self):
        rc, out = run_main([
            "2026-07-28T18:00:00 | skill=ukulele | event=attempted",
        ], extra_args=["--skill=nope"])
        self.assertEqual(rc, 0)
        self.assertIn("sin entradas", out)

    def test_filtro_skill_matchea_solo_esa_entrada(self):
        rc, out = run_main([
            "2026-07-28T18:00:00 | skill=ukulele | subskill=chords | event=attempted",
            "2026-07-28T19:00:00 | skill=piano | subskill=scales | event=attempted",
        ], extra_args=["--skill=piano"])
        self.assertEqual(rc, 0)
        self.assertEqual(parse_stdout(out)["sesiones registradas"], "1")

    def test_filtro_subskill_funciona(self):
        rc, out = run_main([
            "2026-07-28T18:00:00 | skill=u | subskill=chords | event=attempted",
            "2026-07-28T19:00:00 | skill=u | subskill=scales | event=attempted",
        ], extra_args=["--subskill=scales"])
        self.assertEqual(rc, 0)
        self.assertEqual(parse_stdout(out)["sesiones registradas"], "1")

    # --- days_since_last ---

    def test_dias_desde_ultima_sesion(self):
        rc, out = run_main([
            "2026-07-25T18:00:00 | skill=u | event=attempted",
        ], fake_now=datetime(2026, 7, 28, 23, 0))
        self.assertEqual(rc, 0)
        self.assertEqual(parse_stdout(out)["ultima sesion"], "2026-07-25 (3 dias atras)")

    # --- archivo inexistente ---

    def test_log_inexistente_rc1(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = adherence.main(["adherence", os.path.join(tempfile.gettempdir(), "no_existe_12345.log")])
        self.assertEqual(rc, 1)


    # --- CONFIRM-N bug 4: `notes` inyecta un campo y corrompe el filtro ---
    # notes= es TERMINAL: todo lo que sigue (pipes incluidos) es texto libre
    # y NO genera campos. Una nota con `| key=valor` no debe corromper el
    # filtro --skill/--subskill.

    def test_notes_con_pipe_no_corrompe_filtro_skill(self):
        # El campo LEGITIMO es skill=real; el skill=otro inyectado en notes
        # NO debe contar. Antes: --skill real -> "sin entradas" (corrupto).
        lineas = ['2026-07-28T10:00:00 | skill=real | notes="me trabe | skill=otro"']
        rc_real, out_real = run_main(lineas, extra_args=["--skill=real"])
        rc_otro, out_otro = run_main(lineas, extra_args=["--skill=otro"])
        self.assertEqual(rc_real, 0)
        self.assertEqual(parse_stdout(out_real)["sesiones registradas"], "1")
        self.assertEqual(rc_otro, 0)
        self.assertIn("sin entradas", out_otro)

    def test_notes_con_varios_pipes_no_inyecta_campos(self):
        lineas = ['2026-07-28T10:00:00 | skill=real | notes="a | b | c | skill=otro | session=x"']
        rc_real, out_real = run_main(lineas, extra_args=["--skill=real"])
        rc_otro, out_otro = run_main(lineas, extra_args=["--skill=otro"])
        self.assertEqual(parse_stdout(out_real)["sesiones registradas"], "1")
        self.assertEqual(rc_otro, 0)
        self.assertIn("sin entradas", out_otro)

    def test_notes_que_contiene_subskill_no_corrompe_filtro_subskill(self):
        lineas = ['2026-07-28T10:00:00 | skill=u | subskill=chords | notes="x | subskill=scales"']
        rc_chords, out_chords = run_main(lineas, extra_args=["--subskill=chords"])
        rc_scales, out_scales = run_main(lineas, extra_args=["--subskill=scales"])
        self.assertEqual(parse_stdout(out_chords)["sesiones registradas"], "1")
        self.assertEqual(rc_scales, 0)
        self.assertIn("sin entradas", out_scales)

    def test_notes_con_comillas_y_pipes_se_respeta_como_texto(self):
        lineas = ['2026-07-28T10:00:00 | skill=real | notes="ella dijo \'hola\' | skill=otro | session=x"']
        rc, out = run_main(lineas, extra_args=["--skill=real"])
        self.assertEqual(rc, 0)
        self.assertEqual(parse_stdout(out)["sesiones registradas"], "1")

    def test_linea_valida_con_notes_con_pipes_cuenta_normal(self):
        rc, out = run_main([
            '2026-07-28T18:00:00 | skill=u | event=attempted | notes="a | b | c"',
        ], fake_now=datetime(2026, 7, 28, 23, 0))
        self.assertEqual(rc, 0)
        self.assertEqual(parse_stdout(out)["sesiones registradas"], "1")

    # --- CONFIRM-N bug 3: clave repetida, "ultimo gana" invierte el filtro ---
    # adherence no interpreta ni falla (aritmetica pura): regla determinista y
    # documentada -> gana la PRIMERA ocurrencia. Predecible, no invertido.

    def test_skill_repetido_gana_primera_ocurrencia(self):
        # skill=primero | skill=segundo -> gana "primero". Antes (ultimo gana)
        # el filtro --skill primero daba "sin entradas" y --skill segundo daba
        # 1 (filtro silenciosamente invertido).
        lineas = ['2026-07-28T10:00:00 | skill=primero | skill=segundo | event=attempted']
        rc1, out1 = run_main(lineas, extra_args=["--skill=primero"])
        rc2, out2 = run_main(lineas, extra_args=["--skill=segundo"])
        self.assertEqual(rc1, 0)
        self.assertEqual(parse_stdout(out1)["sesiones registradas"], "1")
        self.assertEqual(rc2, 0)
        self.assertIn("sin entradas", out2)

    def test_subskill_repetido_gana_primera_ocurrencia(self):
        lineas = ['2026-07-28T10:00:00 | skill=u | subskill=a | subskill=b | event=attempted']
        rc_a, out_a = run_main(lineas, extra_args=["--subskill=a"])
        rc_b, out_b = run_main(lineas, extra_args=["--subskill=b"])
        self.assertEqual(parse_stdout(out_a)["sesiones registradas"], "1")
        self.assertEqual(rc_b, 0)
        self.assertIn("sin entradas", out_b)

    def test_clave_repetida_mas_notes_inyectando_gana_primera(self):
        # skill=primero | skill=segundo (duplicado real) y notes inyecta
        # skill=tercero. notes terminal -> tercero no cuenta como tercera
        # ocurrencia. Gana la primera: --skill primero -> 1, los demas -> 0.
        lineas = [
            '2026-07-28T10:00:00 | skill=primero | skill=segundo | notes="z | skill=tercero"',
        ]
        rc1, out1 = run_main(lineas, extra_args=["--skill=primero"])
        rc2, out2 = run_main(lineas, extra_args=["--skill=segundo"])
        rc3, out3 = run_main(lineas, extra_args=["--skill=tercero"])
        self.assertEqual(parse_stdout(out1)["sesiones registradas"], "1")
        self.assertEqual(rc2, 0)
        self.assertIn("sin entradas", out2)
        self.assertEqual(rc3, 0)
        self.assertIn("sin entradas", out3)

    def test_clave_repetida_no_crashea_y_sigue_rc0(self):
        # adherence reporta hechos, no falla: un log ambiguo no eleva exit.
        lineas = [
            '2026-07-28T10:00:00 | skill=primero | skill=segundo | event=attempted',
        ]
        rc, out = run_main(lineas, fake_now=datetime(2026, 7, 28, 23, 0))
        self.assertEqual(rc, 0)
        self.assertIn("sesiones registradas: 1", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)