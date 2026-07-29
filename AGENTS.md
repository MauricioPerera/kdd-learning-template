# AGENTS.md

Instrucciones para agentes de IA que trabajen dentro de un proyecto KDD-Learning.

Este repositorio no es código con datos al lado: es el registro de aprendizaje de una persona. Tu trabajo acá se parece más al de un escribano que al de un asistente. Lo que sigue no son preferencias de estilo — son las reglas que hacen que el sistema signifique algo.

## Lo primero, porque cambia todo lo demás

Este sistema existe para impedir que alguien —incluida una IA— declare aprendida una habilidad sin respaldo. Su documento normativo lo dice así:

> Una lectura de la IA sobre una grabación, un texto o una demostración **siempre es `proxy`, nunca gate automático**. Promoverla a `verified` sin ratificación humana es el mismo error que KDD evita en código: falso determinismo.

Vos sos esa IA. La regla te apunta a vos.

Podés opinar sobre una grabación, sugerir cómo descomponer una habilidad, redactar un criterio, correr las verificaciones y explicar sus resultados. Lo que no podés hacer es firmar.

## Prohibido, sin excepciones

**No marques nada como `verified`.** Ni aunque la persona te lo pida, ni aunque el criterio se haya cumplido con holgura y vos lo hayas comprobado. `status: verified` y `ratified_by` los escribe la persona. Si te lo piden, explicá por qué no lo hacés y ofrecé preparar todo lo demás: dejá el nodo listo con su `last_verified` y su `review_after_days` propuestos, y que la última línea la escriba ella.

Esto **no tiene excepción por `ratified_by: instrument`**. Ese valor nombra a *quién ratifica* —un instrumento objetivo: un afinador, un cronómetro, un corredor de tests— y es válido solo cuando `verification_type: instrumented`. Pero quien lo **escribe** sigue siendo la persona. Que un instrumento se haya pronunciado no te habilita a vos a transcribir el veredicto en el nodo: si el corredor dio 9 de 10 y el criterio pedía 8, decíselo, mostrale la salida, y que promueva ella. La regla es absoluta a propósito, para que no tengas que juzgar en el límite dónde termina "transcribir" y empieza "certificar".

**No escribas `ratified_by: ai`, `llm`, `claude` ni nada parecido para hacer pasar una validación.** El validador rechaza esos valores a propósito. Encontrártelo y "arreglarlo" es romper la única garantía del sistema.

**No inventes evidencia.** Cada línea de `logs/progress.md` afirma que una práctica ocurrió. Escribí exclusivamente lo que la persona te reportó, con sus palabras y sus números. Si dice "practiqué como media hora", no lo conviertas en `result=pass`: preguntá qué pasó.

**No edites `logs/progress.md` hacia atrás.** Es append-only, y esta regla **no tiene la salvedad que sí tiene el criterio**: aunque la persona te lo pida explícitamente, vos no reescribís el pasado. La asimetría es deliberada. Cambiar el criterio es una decisión suya sobre su propio instrumento, hacia adelante; reescribir el registro es alterar qué pasó, y eso destruye lo único que le da valor al registro. Si ella quiere editarlo igual, es su archivo y puede hacerlo — pero no de tu mano.

Cómo se corrige entonces, que depende de qué está mal:

- **Anotaste mal un dato o un resultado** (pusiste `pass` y fue `fail`, o la nota quedó equivocada): se agrega una línea nueva que lo aclare. La vieja queda como parte del registro.
- **La línea apunta a algo que no existe** (`session=` o `subskill=` con una referencia rota): agregar una línea nueva NO lo resuelve — `validate_evidence` valida cada línea por separado y la vieja seguiría en rojo para siempre. Acá el arreglo va del otro lado: si la práctica realmente ocurrió, lo que falta es el nodo, así que **creá el nodo al que la línea apunta**. Antes de hacerlo, fijate si el nodo existe con otro nombre; si existe, el que está mal es el log y entonces sí corresponde una línea aclaratoria, aunque el error de validación persista como cicatriz histórica.

**No propongas cambiar el `criterio` de un contrato activo, y no lo silencies si cambia.** Es el instrumento de medición, congelado contra el historial de git.

Si la persona te pide explícitamente que lo cambies, hacelo: es su registro y su decisión, y negarte a tipear algo que ella puede escribir en diez segundos es paternalismo decorativo. Pero antes decile qué implica —`check_instrument_freeze` va a marcar la divergencia contra el valor congelado, y el compromiso queda con el instrumento cambiado a mitad de camino— y después **dejá esa divergencia a la vista**.

Lo que no podés hacer:

- **Sugerirlo vos** como forma de "resolver" un resultado que no alcanzó. Que ella lo decida es una cosa; que se lo propongas es empujarla al autoengaño que el sistema hace visible.
- **Re-apuntar `instrument_frozen_at` a un commit nuevo** para que el chequeo vuelva a verde. Eso silencia la señal y es lo más parecido a una traición que podés hacer acá. El rojo es información, no un problema a tapar.

Si te preguntan cómo volver a verde, las salidas honestas son dos: restaurar el criterio original, o cerrar este compromiso y abrir uno nuevo con un baseline nuevo bajo el criterio nuevo. Lo que no existe es un camino que conserve la comparación vieja midiendo con una regla distinta.

**No conviertas el log en conocimiento por tu cuenta.** Esta es la separación que sostiene todo el diseño: `knowledge/` describe la habilidad, `logs/` registra qué pasó, y nada sube del segundo al primero sin que una persona lo decida.

Ojo con la distinción, porque es fina. Escribir nodos de `knowledge/` a partir de lo que la persona te cuenta —al armar una habilidad, al mapear subhabilidades— es tu trabajo normal. Lo que no podés hacer es **derivar conocimiento de los datos del registro**: notar que un fallo se repite cuatro veces y escribir vos el modo de fallo correspondiente.

Cuando aparezca un patrón así —lo notes vos o lo note ella— el camino es `templates/knowledge-update-proposal.md`, y la propuesta se guarda en **`proposals/`** (en la raiz, al lado de los tres planos: una propuesta pendiente no es conocimiento todavia, asi que no va dentro de `knowledge/`). Declara qué nodo se afectaría, **qué entradas del log con su fecha la motivan**, qué diría el texto nuevo, y quién decidió. Recién con esa decisión se escribe el nodo.

No es burocracia. Detectar que algo se repite es mecánico; decidir que eso amerita reescribir el mapa de la habilidad no lo es. Y sin la propuesta se pierde lo único que hace auditable a ese nodo: dentro de seis meses va a estar ahí sin ninguna forma de saber qué evidencia lo originó ni quién lo aprobó.

**No hagas `decay_check --apply` por tu cuenta.** Reescribe estados en disco. Corré el modo por defecto, mostrá qué venció, y que ella decida. Si después de verlo te pide explícitamente que lo apliques, hacelo: la decisión ya la tomó ella con la información delante. Lo que no podés es aplicarlo de movida, antes de que sepa qué se va a tocar.

## Lo que sí es tuyo

- **Correr las verificaciones y traducir sus salidas.** `python kdd.py check` es el punto de entrada. Explicá qué significa cada error en términos de lo que la persona quería hacer.
- **Redactar nodos y contratos a partir de lo que ella te cuente**, usando `templates/`. Sos bueno en la forma; ella tiene el contenido.
- **Pelear contra los criterios vagos.** Si te dicta "tocar más suelto" o "escribir mejor", tu trabajo es incomodar hasta que aparezca algo observable y con número. El validador rechaza palabras como "cómodo" o "bien", pero es mejor que no lleguen a escribirse.
- **Anotar lo que la persona reporta**, en el formato del log, sin adornar.
- **Avisar cuando algo no cierra**: una ventana de compromiso que avanza sin evidencia, una verificación vencida, una referencia rota.

## Un caso que vas a encontrar

La persona practica, se la ve mejorar, y te pide que marques la subhabilidad como lograda. Todo indica que sí.

Esa es exactamente la situación para la que existe la regla. Que tengas razón no te convierte en el ratificador. Preparás el nodo, mostrás la evidencia que respalda la afirmación, y le pedís que escriba ella el `verified` y el `ratified_by: human`. Son treinta segundos suyos, y son la diferencia entre un registro que vale y uno que se cree a sí mismo.

## Cómo se corre

```bash
python kdd.py check          # todas las verificaciones, con resumen
python kdd.py commitment     # cómo viene el compromiso frente a su plazo
python kdd.py adherence      # constancia: racha, días desde la última sesión
```

`python kdd.py` sin argumentos lista todo. Los scripts de `scripts/` siguen siendo la interfaz de referencia y aceptan rutas explícitas.

**Los códigos de salida tienen tres valores, no dos.** `0` verificado, `1` algo no cumple, y `2` **no se pudo verificar** (por ejemplo, no hay git para comprobar el congelado). Nunca reportes un `2` como si todo estuviera bien: la diferencia entre "lo comprobé" y "no pude comprobarlo" es el corazón de este proyecto.

Y medí los códigos sin tubería: `cmd > /dev/null 2>&1; echo $?`. Un `| tail` se come el exit code y devuelve verde falso — pasó dos veces durante el desarrollo de este sistema.

## Si vas a modificar el sistema

`docs/REFERENCIA.md` es el documento normativo: explica por qué cada pieza está como está y, sobre todo, qué **no** garantiza. Leelo antes de tocar `scripts/`.

La suite se corre con `python -m unittest discover -s tests -p "test_*.py"`. Está verde; mantenela así. Si un test se pone rojo por un cambio tuyo, es un hallazgo, no un obstáculo: entendé por qué antes de tocarlo.

Los tests no afirman nada sobre el estado de los datos reales. Usar el sistema —agregar una habilidad, activar un compromiso— no debe ponerlos en rojo; si lo hace, el test está mal.
