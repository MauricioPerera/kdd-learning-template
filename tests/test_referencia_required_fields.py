#!/usr/bin/env python3
"""Test que mantiene la tabla de campos requeridos de docs/REFERENCIA.md
sincronizada con scripts/validate_contracts.REQUIRED_FIELDS.

La tabla "Campos requeridos por tipo de nodo" ES una segunda fuente de verdad
frente a REQUIRED_FIELDS del script. Este proyecto cazo varias veces
documentacion desincronizada del codigo, asi que la tabla no se acepta sola: este
test la parsea y la compara contra REQUIRED_FIELDS, fallando si difieren en
cualquier tipo o campo. Una tabla sin este test es peor que no tener tabla.

Antes vivia en README.md; al separar la BIENVENIDA (README) de la REFERENCIA
(docs/REFERENCIA.md), la tabla normativa se mudo con el resto del contenido y
este test ahora la lee de su nueva ubicacion. (Rename: el archivo se llamaba
test_readme_required_fields.py; ver REPORT del FEAT-SPLIT-DOCS.)

Formato elegido para parseo robusto (ver REPORT original): la tabla vive entre
dos sentinelas HTML `<!-- BEGIN REQUIRED_FIELDS -->` / `<!-- END REQUIRED_FIELDS -->.
La REFERENCIA contiene OTRA tabla markdown (delta/adherencia) que usaria un
parseo naive por `|`; los sentinelas acotan sin ambiguedad cual es la tabla
canonica. Dentro, cada fila de datos tiene el tipo en la primera celda entre
backticks y los campos en la segunda celda entre backticks. El parser no depende
del espaciado exacto entre backticks ni del numero de espacios en la celda: solo
de que cada token de campo este entre backticks y separado por cualquier
whitespace.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_contracts as vc  # noqa: E402

REFERENCIA = ROOT / "docs" / "REFERENCIA.md"

BEGIN = "<!-- BEGIN REQUIRED_FIELDS -->"
END = "<!-- END REQUIRED_FIELDS -->"

# Una fila: | `type` | `campo1` `campo2` ... |
# - celdas separadas por `|`; la primera celda no vacia es el tipo, la segunda los
#   campos. Cada token entre backticks.
_TOKEN = re.compile(r"`([^`]+)`")


def parse_table(text):
    """Devuelve dict {tipo: [campos]} parseado entre los sentinelas.

    raise AssertionError con mensaje util si los sentinelas faltan o la tabla esta
    vacia: esos son fallos de integridad del propio documento, no de sincronizacion."""
    start = text.find(BEGIN)
    end = text.find(END)
    assert start != -1, f"REFERENCIA no tiene el sentinela de inicio '{BEGIN}'"
    assert end != -1, f"REFERENCIA no tiene el sentinela de fin '{END}'"
    assert end > start, "el sentinela END aparece antes que BEGIN en REFERENCIA"
    block = text[start:end]

    result = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|-"):
            continue
        # saltar fila de encabezado/separador: una fila valida de datos tiene al
        # menos dos celdas con contenido entre backticks.
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        tokens = _TOKEN.findall(stripped)
        if len(tokens) < 2:
            continue  # fila de encabezado sin backticks, o separador
        node_type = tokens[0]
        fields = tokens[1:]
        result[node_type] = fields
    assert result, "tabla REQUIRED_FIELDS vacia: no se parseo ninguna fila entre los sentinelas"
    return result


class TestReferenciaRequiredFieldsTable(unittest.TestCase):
    """La tabla de docs/REFERENCIA.md == validate_contracts.REQUIRED_FIELDS, exacto."""

    def setUp(self):
        self.referencia_text = REFERENCIA.read_text(encoding="utf-8")
        self.table = parse_table(self.referencia_text)

    def test_table_has_same_types_as_code(self):
        referencia_types = set(self.table.keys())
        code_types = set(vc.REQUIRED_FIELDS.keys())
        self.assertEqual(
            referencia_types, code_types,
            f"tipos divergen. REFERENCIA-only: {referencia_types - code_types}; "
            f"code-only: {code_types - referencia_types}",
        )

    def test_table_fields_match_code_per_type(self):
        for node_type, code_fields in vc.REQUIRED_FIELDS.items():
            referencia_fields = self.table.get(node_type)
            self.assertIsNotNone(
                referencia_fields, f"tipo '{node_type}' falta en la tabla de REFERENCIA"
            )
            self.assertEqual(
                referencia_fields, code_fields,
                f"campos divergen para '{node_type}': "
                f"REFERENCIA={referencia_fields} codigo={code_fields}",
            )

    def test_table_order_matches_code(self):
        # Orden tambien: un reordenamiento silencioso es un cambio que el test debe
        # cazar (mismo dict, pero la tabla mostro otra cosa).
        referencia_order = list(self.table.keys())
        code_order = list(vc.REQUIRED_FIELDS.keys())
        self.assertEqual(
            referencia_order, code_order,
            f"orden de tipos diverge: REFERENCIA={referencia_order} codigo={code_order}",
        )


# --- Guard del tope de review_after_days -------------------------------------
#
# MAX_REVIEW_AFTER_DAYS vive en scripts/validate_contracts.py y su valor se
# REPITE en prosa en docs/REFERENCIA.md ("`review_after_days` tiene un tope de
# 365"). Un agente que subio el tope actualizo codigo, tests y REFERENCIA, pero
# se le paso otro documento que tambien lo repetia: el numero duplicado se
# desincronizo dentro de una sola corrida. Es el mismo patron de la tabla de
# arriba (segunda fuente de verdad vs el codigo); aplicamos la misma idea al
# valor escalar: parsear el tope que la prosa declara y compararlo contra la
# constante del codigo, fallando con AMBOS valores si difieren.
#
# Anclaje robusto, no fragil de mantener: no atamos a una posicion fija ni a una
# redaccion exacta. Buscamos cada mencion de `review_after_days` y, en una
# ventana alrededor, el patron "tope de <n>". Asi sobrevive a una reescritura
# menor de la frase (cambiar "tiene un tope de" por "esta limitado a", mover la
# frase dentro del parrafo, etc.) mientras el numero siga cerca de la mencion
# del campo. Si el numero NO aparece (el documento normativo dejo de declarar
# el tope), el test FALLA: eso tambien es una regresion, no un caso a ignorar.

_WINDOW = 400  # chars alrededor de cada mencion de review_after_days
_TOPE_NUM = re.compile(r"tope\s+de\s+(\d+)", re.IGNORECASE)
_FIELD_MENTION = re.compile(r"review_after_days")


def extract_review_after_days_tope(text):
    """Devuelve el int que REFERENCIA declara como tope de review_after_days.

    Anclaje: 'tope de N' en proximidad de una mencion de review_after_days.
    AssertionError (mensaje util) si REFERENCIA no menciona el campo, no declara
    ningun tope cerca, o declara varios distintos: los tres son regresiones del
    documento normativo.
    """
    mentions = [m.start() for m in _FIELD_MENTION.finditer(text)]
    assert mentions, (
        "REFERENCIA no menciona 'review_after_days' en ningun lado: el "
        "documento normativo dejo de documentar el campo"
    )
    nums = []
    for pos in mentions:
        lo = max(0, pos - _WINDOW)
        region = text[lo : pos + _WINDOW]
        for m in _TOPE_NUM.finditer(region):
            nums.append(int(m.group(1)))
    # dedupera conservando el orden (menciones cercanas pueden captar el mismo
    # numero desde ventanas solapadas; eso es esperable, no un conflicto).
    seen = set()
    uniq = []
    for n in nums:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    assert uniq, (
        "REFERENCIA menciona 'review_after_days' pero no declara su tope "
        "('tope de N') en proximidad del campo: el documento normativo dejo "
        "de declarar el limite. Esto es una regresion, no un caso a ignorar"
    )
    assert len(uniq) == 1, (
        f"REFERENCIA declara varios valores distintos de tope para "
        f"review_after_days: {uniq}. Debe declarar uno solo"
    )
    return uniq[0]


class TestReferenciaReviewAfterDaysTope(unittest.TestCase):
    """El tope de review_after_days que la prosa de REFERENCIA declara == la
    constante del codigo. Guard contra la deriva del numero duplicado."""

    def test_referencia_tope_matches_code(self):
        text = REFERENCIA.read_text(encoding="utf-8")
        declarado = extract_review_after_days_tope(text)
        codigo = vc.MAX_REVIEW_AFTER_DAYS
        self.assertEqual(
            declarado, codigo,
            f"el tope de review_after_days desincronizado entre docs y codigo: "
            f"REFERENCIA declara {declarado}, codigo MAX_REVIEW_AFTER_DAYS={codigo}",
        )


# --- Guard de los conjuntos de valores validos -------------------------------
#
# VALID_VERIFICATION_TYPES, VALID_DOMAIN_TYPES, VALID_SUBSKILL_STATUS,
# VALID_SESSION_STATUS y VALID_SKILL_CONTRACT_STATUS (en scripts/validate_contracts.py)
# definen que valores acepta el sistema. Sus nombres se repiten en prosa en
# docs/REFERENCIA.md, sin nada que vigile la correspondencia. Cuando se agrego
# `discontinued` hubo que acordarse de tocar tres documentos a mano; salio bien
# por atencion, no por diseño. El PM encontro despues que `attempted` -- estado
# valido de session_contract -- no figuraba en ninguna parte de la referencia:
# su ciclo de vida vivia solo en un comentario de plantilla. Si este guard
# hubiera existido, ya habria pagado.
#
# Direccion decidida (y la direccion importa): NO parseamos la prosa para
# extraer los valores declarados -- eso es fragil, y un guard que falla por una
# reescritura inocente de una frase entrena a la gente a ignorarlo. La direccion
# es la inversa: por cada valor de cada conjunto del codigo, afirmamos que
# aparece en docs/REFERENCIA.md como token entre backticks (`draft`). Es una
# busqueda simple, no entiende de estructura, y caza el modo de fallo real:
# agregar un valor al codigo y olvidarse de documentarlo.
#
# Asumimos conscientemente el falso negativo: un valor mencionado en un
# contexto irrelevante pasaria el chequeo. No importa -- el guard pregunta
# "¿lo documentaste?", no "¿lo explicaste bien?". Un guard que intentara juzgar
# lo segundo seria justamente el fragil que descartamos.

_VALID_SETS = [
    ("VALID_VERIFICATION_TYPES", vc.VALID_VERIFICATION_TYPES),
    ("VALID_DOMAIN_TYPES", vc.VALID_DOMAIN_TYPES),
    ("VALID_SUBSKILL_STATUS", vc.VALID_SUBSKILL_STATUS),
    ("VALID_SESSION_STATUS", vc.VALID_SESSION_STATUS),
    ("VALID_SKILL_CONTRACT_STATUS", vc.VALID_SKILL_CONTRACT_STATUS),
]


class TestReferenciaDocumentaValoresValidos(unittest.TestCase):
    """Cada valor de cada conjunto VALID_* del codigo aparece como token entre
    backticks en docs/REFERENCIA.md. Guard contra "agregue un valor al codigo y
    me olvide de documentarlo" -- el modo de fallo real que esta auditoria
    encontro con `attempted` y casi encuentra con `discontinued`."""

    def test_valores_validos_documentados_con_backticks(self):
        text = REFERENCIA.read_text(encoding="utf-8")
        for set_name, values in _VALID_SETS:
            # sorted para que el orden de los subtests sea deterministico y el
            # fallo nombre siempre el mismo valor primero (util al demostrar que
            # muerde y al leer un CI rojo).
            for value in sorted(values):
                with self.subTest(set=set_name, value=value):
                    # assertTrue y no assertIn: assertIn vuelca el segundo
                    # operando en el fallo, y aca ese operando es REFERENCIA
                    # entera (~29KB de ruido por cada valor faltante). El
                    # mensaje ya dice conjunto y valor, que es todo lo que hace
                    # falta para saber que documentar.
                    self.assertTrue(
                        f"`{value}`" in text,
                        f"el valor '{value}' del conjunto {set_name} no aparece "
                        f"como token entre backticks (`{value}`) en "
                        f"docs/REFERENCIA.md: agregar un valor al codigo sin "
                        f"documentarlo es justo el modo de fallo que este guard "
                        f"existe para cazar",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)