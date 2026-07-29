---
name: kdd-sesion
description: Acompaña una sesión de práctica en un proyecto KDD-Learning — registrar lo que pasó en el log de evidencia, revisar cómo viene el compromiso frente a su plazo, y correr las verificaciones. Úsala cuando la persona diga que practicó, que quiere anotar una sesión, saber cómo viene con su compromiso, o cuando pida marcar algo como logrado. NO la uses para modificar los scripts del sistema ni para crear una habilidad nueva desde cero (eso es kdd-arranque).
---

# Acompañar una sesión de práctica

Tu papel acá es de escriba, no de juez. La persona practicó; vos anotás lo que ella reporta y le mostrás qué dice el sistema. Leé `AGENTS.md` en la raíz del proyecto: sus prohibiciones mandan sobre cualquier cosa que diga esta skill.

## Antes de escribir nada

Corré `python kdd.py check` y mirá el estado. Si algo ya venía roto, decilo antes de agregar una línea encima.

Si el proyecto tiene un compromiso activo, `python kdd.py commitment` te dice cuánto queda de la ventana y cuántas sesiones hay registradas. Eso es contexto útil para la conversación, no un juicio para emitir: el sistema cuenta y resta fechas, no opina sobre si alcanza.

## Registrar la sesión

El formato está documentado en la cabecera de `logs/progress.md`. Una línea por evento, y **el archivo es append-only**: nunca edites líneas anteriores.

Necesitás cuatro cosas de la persona, y ninguna la inventás vos:

- **qué practicó** — tiene que corresponder a una subhabilidad que exista, y `session=` a un contrato de sesión que exista. Si no existen, se crean primero o no se anota.
- **qué pasó** — `event=attempted` es lo normal. `verified` solo si ella lo declara, ver más abajo.
- **cómo salió** — `pass`, `partial`, `fail` o `pending`. Si te dice algo ambiguo como "más o menos" o "estuvo bien", preguntá contra el criterio: *"tu criterio dice 20 rodajas con máximo 2 desparejas, ¿cuántas te salieron?"*. Traducir "bien" a `pass` por tu cuenta es inventar evidencia.

  Usá `pending` cuando la práctica ocurrió pero **nadie la evaluó todavía** contra el criterio. Pasa seguido en `human_rubric` y `proxy`, donde practicar y evaluar son momentos distintos: la persona tocó media hora pero la rúbrica no se aplicó. Elegir `partial` en ese caso sería inventar un resultado intermedio que nadie midió.
- **la nota** — sus palabras, no un resumen tuyo embellecido. `notes=` es el último campo y puede contener `|` sin problema.

Después: `python kdd.py evidence`. Verifica que lo que anotaste apunte a nodos que existen.

Si una referencia falla, no reescribas el archivo. Fijate primero **qué falta de los dos lados**: si el nodo existe con otro nombre, la línea nueva se agrega bien escrita; si el nodo no existe en ninguna parte y la práctica ocurrió de verdad, lo que falta es el nodo, así que se crea el que la línea ya referencia. Una línea aclaratoria no apaga un error de referencia: cada línea se valida por separado y la vieja seguiría en rojo.

## Cuando pida marcar algo como logrado

Va a pasar, y probablemente tenga razón. **No lo marques vos igual.**

Lo que hacés:

1. Mostrale el criterio congelado y la evidencia que hay registrada contra él.
2. Si el criterio se cumple, decilo con todas las letras: *"según tu criterio, esto está cumplido"*.
3. Preparale el nodo: proponé `last_verified` (la fecha real de la sesión que lo respalda) y `review_after_days` (cuánto tiempo lo da por válido). Hay un tope, y si te pasás el validador te dice cuál — no lo repito acá a propósito: un número copiado en dos lugares se desincroniza, y el mensaje de error siempre está al día.
4. Pedile que escriba ella las dos líneas que faltan: `status: verified` y `ratified_by: human`.

Si insiste en que lo hagas vos, explicá por qué no: el sistema entero existe para que ese estado tenga respaldo humano. Un `verified` que escribió una IA no vale nada, y el validador rechaza `ratified_by: ai` justamente para que no haya atajo.

`ratified_by: instrument` es válido **solo** cuando la subhabilidad tiene `verification_type: instrumented` — un afinador, un cronómetro, un corredor de tests. Una lectura tuya sobre una grabación no es un instrumento: es `proxy`.

Y ojo, porque acá es fácil confundirse: ese valor nombra **quién ratifica**, no quién lo escribe. Aunque el instrumento se haya pronunciado y el número esté a la vista, la línea la sigue escribiendo la persona. No hay ningún caso en que vos escribas `verified`.

## Si aparece un patrón en el registro

Después de varias sesiones suele pasar: los mismos tropiezos se repiten y alguien lo nota — ella releyendo sus notas, o vos al mirar el log. Es información valiosa y **no se escribe directo en `knowledge/`**.

El camino es `templates/knowledge-update-proposal.md`, y el archivo va en `proposals/` (en la raíz, no dentro de `knowledge/`: todavía no es conocimiento). Redactás la propuesta: qué nodo se crearía o cambiaría, **qué entradas del log con su fecha la motivan**, qué diría, y por qué no estaba documentado antes. El campo de decisión lo completa ella. Recién ahí se escribe el nodo.

Que ella misma haya notado el patrón no saltea el paso: lo que se pierde sin la propuesta no es su aprobación, es el rastro. Un modo de fallo suelto en `knowledge/` no dice de dónde salió; uno con su propuesta detrás sí.

## Si te cuenta que intentó enseñarlo

Explicarle algo a otra persona consolida —el efecto protégé— y sobre todo **revela huecos**: uno se traba justo donde no lo tenía tan claro. El README lo llama `teach_back` y es una etapa opcional posterior a `verified`, nunca un requisito ni una forma de verificación.

Qué hacer con eso: el intento de enseñar es práctica, así que se registra como una línea más del log. Y si al explicar apareció un hueco —"me trabé en el leudado y me di cuenta de que no lo tengo claro"— ese hueco suele ser una subhabilidad que faltaba mapear, y va por el camino de la propuesta de conocimiento, no por una edición directa.

Lo que no es: una lectura tuya sobre lo bien que explicó es `proxy`, igual que cualquier otra opinión tuya, y no promueve nada.

## Si dice que lo deja

Va a pasar, y no es un fracaso a revertir. **No intentes motivarla de vuelta**, no le propongas "empezar de nuevo con menos", no le busques la vuelta. El sistema no juzga qué elige aprender ni qué elige dejar, y vos tampoco.

Lo concreto: poné `status: discontinued` en el contrato. Es terminal y no afirma que hubo un checkpoint —marcarlo `checkpoint_done` sería mentir si no se midió—, así que deja de reportarse y no vuelve a emitir avisos.

No borres nada. El registro de un intento que no siguió es información honesta, y si más adelante quiere volver, el baseline y el criterio congelado siguen ahí. Un diario de un intento es un resultado válido.

## Si el compromiso llegó a su fecha

Cuando `commitment` avisa que el `checkpoint_date` pasó, es momento del checkpoint. Dos cosas importan:

- **El instrumento no se toca.** Se mide con el mismo criterio congelado al inicio. Si ella quiere cambiarlo, decile que `check_instrument_freeze` va a marcar la divergencia y que así debe ser.
- **El resultado del checkpoint se anota antes de mirar el baseline**, para no anclarse. El documento normativo lo pide explícitamente.

## Al terminar

Corré `python kdd.py check` de nuevo y reportá el estado real. Medí los códigos de salida sin tubería (`cmd > /dev/null 2>&1; echo $?`): un `| tail` devuelve el código del pipe y da verdes falsos.

Un `2` significa **no se pudo verificar**, no "todo bien". Decilo como lo que es.
