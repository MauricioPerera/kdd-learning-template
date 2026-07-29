---
name: kdd-arranque
description: Guía a una persona para poner en marcha una habilidad nueva en KDD-Learning, de cero hasta el compromiso activo con su instrumento congelado — explorar el tema, escribir las subhabilidades, redactar un criterio medible y activar el compromiso con el flujo de dos commits. Úsala cuando alguien quiera empezar a documentar una habilidad, no sepa por dónde arrancar, o tenga el proyecto recién clonado y vacío. Para registrar prácticas de una habilidad ya montada, usá kdd-sesion.
---

# Poner en marcha una habilidad

El orden importa más que el contenido, y es lo único que las plantillas no pueden explicar. Leé `AGENTS.md` en la raíz antes de empezar: sus prohibiciones mandan sobre esta skill.

## 1. Explorar antes de estructurar

La tentación es abrir la plantilla y empezar a llenar campos. No lo hagas todavía.

Primero conversá sobre la habilidad: qué quiere lograr concretamente, para qué le sirve, dónde se traba hoy. Las subhabilidades son el **destilado** de esa conversación, no su punto de partida. Un mapa escrito antes de entender el territorio termina siendo una lista de categorías genéricas que no ayudan a nadie.

Buscá el 20% que desbloquea el resto. Si quiere tocar canciones, cambiar de acorde sin cortar el pulso importa más que memorizar veinte acordes.

## 2. Crear el esqueleto

```bash
python kdd.py init <nombre> --domain-type <tipo>
```

El `domain_type` condiciona qué se puede verificar, así que no es una etiqueta cosmética:

- `physical` — instrumento, deporte, destreza motora. Lo instrumentable se reduce a lo que mida un sensor: afinación, tempo, tiempo.
- `ai_mediated` — herramientas, código, automatización. Acá una IA participa de la ejecución misma y el rango de verificación objetiva es amplio.
- `cognitive_abstract` — negociación, escritura, criterio de diseño. Casi todo cae en rúbrica humana.

## 3. Escribir las subhabilidades

Desde `templates/subskill.md`, una por archivo, en `knowledge/<habilidad>/subskills/`. Los modelos mentales, modos de fallo y herramientas reutilizables van en `knowledge/shared/`, referenciados por `id` en vez de copiados.

`python kdd.py contracts` valida la forma. Corrélo seguido; cada error dice qué falta.

## 4. El criterio: acá se juega todo

Esta es la parte donde tu ayuda vale más, y donde tenés que ser incómodo.

La persona va a proponer algo como *"tocar más suelto"*, *"escribir más claro"*, *"que me salga natural"*. Ninguno sirve: son frases que se acomodan al resultado. Dentro de un mes, cualquier cosa que pase va a poder llamarse "más suelto".

Tu trabajo es preguntar hasta que aparezca algo observable, con número, que un tercero pudiera medir:

> — Quiero cortar verdura más parejo.
> — ¿Cómo lo medirías? Si cortás veinte rodajas ahora y veinte en un mes, ¿qué mirarías para saber que mejoraste?
> — Que sean todas del mismo grosor.
> — ¿Qué grosor, y cuánta diferencia aceptás?
> — Tres milímetros, más o menos uno.
> — ¿Y cuántas desparejas de veinte te parece que ya no cuenta como logrado?

De ahí sale: *"20 rodajas de 3 mm ±1 mm, medidas con regla, máximo 2 desparejas"*.

El validador rechaza palabras vagas como "cómodo" o "bien", pero es mejor que no lleguen a escribirse. Y si la habilidad es `human_rubric` y no hay número posible, exigí al menos una escala explícita: qué es un 1 y qué es un 5.

**El mismo criterio, textual, va en el contrato de habilidad y en el de sesión.** El validador compara carácter por carácter, espacios incluidos: son el mismo instrumento y divergir lo invalida.

### ¿Con fecha límite o sin ella?

Preguntáselo, no lo asumas. Si la persona quiere medir un progreso entre dos momentos, poné `checkpoint_date` y queda un compromiso con ventana. Si solo quiere registrar su práctica sin plazo —que es perfectamente válido y muy común—, poné `checkpoint_date: null` y queda un seguimiento abierto.

No la empujes hacia la fecha. Una ventana sirve cuando se quiere comparar un antes y un después; no es un requisito para usar el sistema, y ofrecerla como si lo fuera contradice que esto no busca presionar a nadie.

## 5. Registrar el baseline

La primera práctica se anota en `logs/progress.md` como una línea más. Es la medición inicial contra la cual se va a comparar todo.

En este punto `python kdd.py evidence` va a avisar que hay evidencia contra un contrato en `draft`. Es esperado en este orden y se cierra en el paso siguiente.

## 6. Activar y congelar

Dos commits, y el orden no es negociable:

```bash
# 1. status: draft -> active en el contrato, y commitear
git add contracts/ && git commit -m "activa el compromiso"

# 2. escribir el sha DE ESE commit en instrument_frozen_at, y commitear
git rev-parse HEAD          # copiá este sha
git add contracts/ && git commit -m "congela el instrumento"
```

Tiene que ser un **sha de commit**, no `HEAD` ni un nombre de rama: una referencia móvil se mueve con cada commit, así que el "criterio congelado" seguiría al puntero y aflojar la rúbrica pasaría como verificado. El script rechaza esas formas.

`python kdd.py freeze` confirma que quedó bien.

## 7. Cerrar

`python kdd.py check` debe dar verde entero. A partir de acá, cada práctica se registra con la skill `kdd-sesion`.

Antes de despedirte, decile dos cosas:

- **Cuándo es el checkpoint** y qué se comprometió a hacer hasta entonces.
- **Que el criterio ya no se toca.** Si dentro de tres semanas no llega, la tentación de bajarlo va a ser real — y ahora queda registrada en el historial. Esa incomodidad es la función del sistema, no un defecto.
