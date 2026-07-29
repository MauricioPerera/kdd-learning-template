# KDD-Learning

**Una forma de anotar, antes de empezar, qué va a significar exactamente “ya lo sé hacer” — y después comprobarlo sin engañarte.**

Practicar mucho se siente como progresar. Pero la sensación de haber mejorado y haber mejorado de verdad son dos cosas distintas, y sin un criterio fijado de antemano cuesta distinguirlas. Lo que suele pasar es peor: cuando el resultado no alcanza, uno baja el listón sin darse cuenta y se declara satisfecho.

Este sistema no juzga si aprendiste. Hace algo más modesto: te ayuda a decidir el criterio **antes**, lo deja congelado para que cualquier cambio posterior quede a la vista, y te avisa cuando algo no cierra.

No busca obligarte a estudiar ni hacerte sentir mal si no practicaste, y no opina sobre qué elegiste aprender. Supone a un adulto que decide por sí mismo y que prefiere saber cómo viene de verdad. Tampoco te impide hacer trampa: no hay contra quién, y el único que se quedaría sin saber dónde está sos vos. El objetivo no es que el sistema crea que aprendiste — es que puedas aplicar lo que aprendiste.

📖 **[Explicación para cualquiera, con diagramas (ES · EN · PT)](https://mauricioperera.github.io/kdd-learning-template/)**

## Cómo está organizado

Tres cuadernos que nunca se mezclan:

| | |
|---|---|
| `knowledge/` | qué es la habilidad y en qué partes se divide |
| `contracts/` | qué te comprometiste a lograr, y con qué criterio exacto |
| `logs/` | qué pasó de verdad, una línea por sesión |

Y al lado de los tres, `proposals/`: cuando un patrón se repite en el registro y merece pasar a ser conocimiento, se redacta ahí una propuesta con la evidencia que la motiva, y una persona decide. Nada cruza solo.

Nada sube solo de un cuaderno al siguiente. Que hayas practicado veinte veces no convierte una subhabilidad en “dominada”: esa decisión la tomás vos, queda registrado que fuiste vos, y caduca si pasa demasiado tiempo sin evidencia nueva.

## Qué necesitás

Python 3 y Git. Nada más — ninguna dependencia externa, ninguna cuenta, nada que instalar con `pip`.

Hoy se usa escribiendo archivos de texto y corriendo comandos en una terminal. No hay todavía una aplicación con botones.

## Empezar

```bash
python kdd.py init <tu-habilidad> --domain-type physical
python kdd.py check
```

`kdd.py check` corre las siete verificaciones de una y resume una línea por herramienta. `python kdd.py` sin argumentos las lista todas. Los comandos largos (`python scripts/validate_contracts.py knowledge contracts`) siguen siendo válidos y son la interfaz de referencia; la CLI solo les arma las rutas convencionales.

El orden completo —qué escribir primero, cuándo congelar el criterio, cómo registrar una sesión— está en **[De cero a verde](docs/REFERENCIA.md#de-cero-a-verde)**. Es lo único que las plantillas no pueden explicarte.

## Las herramientas

| | |
|---|---|
| `init_skill` | arma el esqueleto de una habilidad nueva |
| `validate_contracts` | valida la forma de cada nodo |
| `adherence` | constancia: racha, días desde la última sesión |
| `decay_check` | qué verificaciones vencieron |
| `validate_evidence` | que el registro apunte a cosas que existen |
| `check_instrument_freeze` | que el criterio no se haya aflojado |
| `commitment_status` | cómo viene un compromiso frente a su plazo |

Ninguna evalúa si aprendiste. Verifican forma, fechas, referencias y vencimientos; el juicio sobre tu progreso es tuyo, y esa frontera es deliberada.

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Documentación

**[docs/REFERENCIA.md](docs/REFERENCIA.md)** es el documento normativo: explica por qué el sistema está armado así, qué garantiza cada pieza y —sobre todo— qué **no** garantiza.

Adaptación de [KDD (Knowledge-Driven Development)](https://github.com/MauricioPerera/KDD) al aprendizaje de habilidades. No reemplaza a un instructor humano, en especial donde hay riesgo físico: mide suficiencia práctica, no maestría.
