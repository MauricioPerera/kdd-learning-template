# KDD-Learning (nombre provisional)

Adaptación de [KDD (Knowledge-Driven Development)](https://github.com/MauricioPerera/KDD) para adquisición de habilidades y autoaprendizaje. Toma prestada la estructura de contratos y separación de conocimiento/evidencia de KDD, pero **no pretende el mismo determinismo**: en software un test corre y falla objetivamente, en adquisición de habilidades la mayoría de las veces no hay compilador. Este documento es la referencia normativa de por qué el sistema está armado como está.

No reemplaza a un instructor humano, en especial en habilidades con riesgo físico real. Mide suficiencia práctica, no maestría.

## Qué supone de vos

Este sistema no busca que estudies. Supone que sos una persona adulta que ya decidió qué quiere aprender y por qué, y que no necesita que un programa la empuje.

Tampoco juzga **qué** elegiste aprender. Que sea útil, rentable, ambicioso o un capricho es asunto tuyo: trata igual a quien prepara una certificación profesional y a quien quiere aprender a hacer nudos.

No busca que te sientas incómodo por no haber practicado. No hay rachas que defender, insignias, ni nada que te reclame. Cuando la ventana de un compromiso avanza sin evidencia nueva, te lo dice como te lo diría un GPS: no para retarte, sino porque preferís saber dónde estás.

Y no te impide hacer trampa, porque no hay contra quién hacerla. Podés registrar sesiones que no ocurrieron, o aflojar el criterio hasta que cualquier resultado lo cumpla. Nadie va a auditarte. Lo único que se rompe es tu propio instrumento de medición, y el único que se queda sin saber cómo viene es quien lo usa.

Por eso el objetivo nunca fue que el sistema *crea* que aprendiste. Un registro con todo en verde no vale nada por sí mismo. Lo que vale es que puedas hacer aquello para lo que practicaste — y para eso conviene que el registro diga la verdad, no que apruebe.

Esto explica por qué las verificaciones tienen la forma que tienen. El congelado del instrumento no existe para atarte las manos: podés cambiar el criterio cuando quieras, y el sistema simplemente hace que ese cambio quede a la vista en vez de pasar inadvertido. La diferencia no es entre poder y no poder, sino entre saber y no saber.



## Los tres planos

- **Conocimiento** (`knowledge/`): qué es la habilidad, cómo se descompone. Persiste entre sesiones, no se regenera cada vez.
- **Contrato** (`contracts/`): qué se va a practicar y con qué criterio se sabrá si se logró. Dos niveles: `skill/` (compromiso, nivel proyecto) y `sessions/` (una práctica puntual).
- **Evidencia** (`logs/`): qué pasó realmente. Registro append-only, nunca interpretación.

Ningún dato fluye directo de evidencia a conocimiento. Si un patrón se repite en los logs y no está documentado en `knowledge/`, se redacta como propuesta manual (ver `templates/knowledge-update-proposal.md`) y una persona decide si se promueve. Esto es deliberado: detectar "un patrón se repitió 3 veces" es mecánico, decidir si eso amerita reescribir el mapa de la habilidad no lo es.

Las propuestas viven en **`proposals/`**, en la raíz, al lado de los tres planos y no dentro de ninguno. Una propuesta pendiente no es conocimiento —es justamente lo que todavía no se decidió si lo será— y guardarla en `knowledge/` difuminaría la separación que existe para proteger. Una vez aceptada, el nodo se escribe donde corresponda y la propuesta queda como el rastro de por qué está ahí: qué entradas del log lo motivaron, y quién lo decidió.

Que la evidencia no *ascienda* sola a conocimiento es distinto de no verificar que *apunte* a algo real: `scripts/validate_evidence.py` comprueba que cada `skill=`, `subskill=` y `session=` del log exista como nodo **del tipo correspondiente**. Un `subskill=` que apunta a un `skill_index` es un error aunque ese id exista. Es aritmética de identificadores, sin interpretación. Sin ese chequeo, un slug mal tipeado no produce un error sino una racha calculada sobre un fantasma, o un cero que se lee como "no practiqué".

El formato canónico del log está documentado en la cabecera del propio `logs/progress.md`, y ahí se queda: repetir acá la lista de campos y valores sería otro número copiado en dos lugares esperando a desincronizarse. Este documento explica el porqué; el archivo dice el cómo.

Dos detalles de ese formato importan más de lo que parecen. `notes=` es el **último** campo: todo lo que viene después le pertenece, pipes incluidos, así que una nota puede contener `|` sin partir la línea en campos falsos. Y una clave repetida en la misma línea (`skill=a | skill=b`) es un error, no algo a resolver por precedencia: la línea es ambigua y no hay forma de saber cuál se quiso decir. Antes de esto, una nota inocente con un pipe podía reasignar en silencio una sesión a otra habilidad.

El mismo script emite un **aviso** (no un error: no cambia el exit code) cuando hay evidencia registrada contra un `skill_contract` que sigue en `draft`. Puede ser legítimo practicar antes de activar formalmente el compromiso; el sistema lo señala y deja la decisión a la persona.

## `domain_type`

Condiciona qué es siquiera posible verificar:

- `ai_mediated`: herramientas, código, automatización. La IA participa en la ejecución misma (revisa logs de error, valida que un flujo corrió). Rango amplio de `instrumented`.
- `physical`: instrumento, deporte, destreza motora. `instrumented` se reduce a lo que un sensor mida (afinación, tempo). El resto cae en `proxy` o `human_rubric`.
- `cognitive_abstract`: negociación, escritura, criterio de diseño. Casi todo `human_rubric`, con algún `proxy` posible vía análisis de texto.

## `verification_type` (por subhabilidad, no por skill entera)

- `instrumented`: hay una prueba objetiva sin margen de interpretación (compilador, afinador, conteo de errores). El contrato puede tener un `test_command` real.
- `proxy`: hay una herramienta o la IA da una lectura, pero con margen de error declarado. El umbral de aceptación lo fija el humano de antemano, no el script.
- `human_rubric`: no hay instrumento posible. La verificación de contenido es 100% humana. El gate automático se limita a validar que la rúbrica exista y tenga escala definida, nunca a evaluar si se cumplió.

Una lectura de la IA sobre una grabación, un texto o una demostración **siempre es `proxy`, nunca gate automático**. Promoverla a `verified` sin ratificación humana es el mismo error que KDD evita en código: falso determinismo.

Un `skill_contract` también declara un `verification_type`, y no significa lo mismo ni se cruza contra el de sus subhabilidades. El de una subhabilidad describe cómo se verifica **esa** competencia; el del contrato describe qué clase de instrumento es el `criterio` congelado con el que se comparan baseline y checkpoint. Son escalas distintas: un compromiso puede medirse con una sola rúbrica humana aunque cubra una subhabilidad `instrumented` y otra `human_rubric`. Por eso nada valida que coincidan — exigir consistencia entre ambos bloquearía combinaciones legítimas y forzaría a inventar un criterio de agregación que no existe. Al completar un contrato, la pregunta correcta no es "qué tipo son mis subhabilidades" sino "qué clase de instrumento es la rúbrica que estoy congelando".

## Ciclo de vida de una subhabilidad

`draft` → `practicing` → `verified` → (si vence `review_after_days` sin nueva evidencia) → `needs_review`

`needs_review` no es un retroceso a `draft`: reconoce que hubo verificación real en el pasado pero que el sistema no puede asumir que sigue vigente sin evidencia nueva.

El estado `verified` es afirmable, no auto-promovible. El validador de forma exige, solo cuando `status: verified`, tres campos que respaldan la afirmación: `last_verified` (fecha ISO desde cuándo), `review_after_days` (entero positivo, por cuánto) y `ratified_by` (quién). `last_verified` no puede ser futura (es "desde cuándo") y `review_after_days` tiene un tope de 365: más de un año equivale a no caducar nunca, que es justo lo que estos campos existen para impedir. `ratified_by: human` es siempre válido; `ratified_by: instrument` solo vale cuando `verification_type: instrumented` (una verificación objetiva se ratifica a sí misma). Cualquier otro valor —en particular `ai`, `llm`, `claude` o `proxy`— es rechazado: una lectura de IA nunca ratifica por sí sola un `verified`. Es la materialización, como dato auditable, de la regla de `verification_type`: promover a `verified` sin ratificación humana es el falso determinismo que este sistema rechaza. Un nodo que decae a `needs_review` conserva estos campos y sigue siendo válido; no se les exigen de nuevo.

## Ciclo de vida de un contrato de sesión

`draft` → `attempted` → `verified`

Es más corto que el de una subhabilidad y significa otra cosa. Una sesión es un evento puntual: se planifica (`draft`), se practica (`attempted`), y si esa práctica alcanzó el criterio, se cierra (`verified`). No caduca — lo que caduca es la competencia que la subhabilidad afirma, no el hecho de que una tarde alguien haya practicado.

`attempted` es el estado más común y el que se queda: la mayoría de las sesiones son intentos que aportan evidencia sin cerrar nada por sí solos.

## Adherencia vs. competencia: ejes separados que se cruzan

Adherencia (frecuencia, racha, días desde la última sesión) es aritmética pura sobre timestamps, no requiere IA ni interpretación. Competencia es lo que mide `verification_type`. Nunca se combinan en un solo número. Su valor real aparece cruzados en un compromiso baseline/checkpoint:

| Delta | Adherencia | Lectura |
|---|---|---|
| alto | alta | el plan funcionó como estaba diseñado |
| bajo | alta | se cumplió la presencia, el método no fue efectivo — revisar deconstrucción o mental models |
| alto | baja | el umbral de la subhabilidad era menor al estimado, o las pocas sesiones fueron de alta calidad |
| bajo | baja | el compromiso no se cumplió en ninguna dimensión |

`scripts/commitment_status.py` es el eje de adherencia hecho herramienta: por cada compromiso `active` reporta cuánto lleva abierta la ventana, cuánto falta, cuántas sesiones se registraron desde el baseline y hace cuánto fue la última. Avisa —sin cambiar el exit code— cuando el `checkpoint_date` ya pasó y el contrato sigue activo, o cuando no hay ninguna evidencia desde que empezó. Sin esto, un compromiso podía llegar a su checkpoint sin que nada señalara que la ventana avanzó en silencio.

Lo que **no** hace, y es deliberado: no verifica la frecuencia comprometida. Un contrato que dice "practicar 4 veces por semana" lo dice en prosa, no en un campo, y agregar ese campo para que un script pudiera compararlo sería mover al lado mecánico un juicio que es de la persona. El script cuenta y resta fechas; si eso alcanza o no lo decidís vos. Por la misma razón no es un gate: practicar poco no es un estado inválido, es un hecho sobre tu proceso.

## Compromiso baseline/checkpoint

Para que el delta signifique algo, baseline y checkpoint deben usar **el mismo instrumento, congelado de antemano** (`instrument_frozen: true` en el contrato de skill). Elegir la rúbrica después de ver el resultado invalida la comparación. La evaluación del checkpoint se registra sin ver el resultado del baseline hasta después de anotar el puntaje nuevo, para evitar anclaje.

### `baseline_date` es la fecha de la medición, no la de la planificación

El campo se escribe cuando armás el contrato, pero lo que declara es **cuándo tomaste el baseline**: la primera medición real contra el criterio. Mientras el contrato está en `draft` podés corregirlo tantas veces como haga falta — todavía no hay nada congelado ni nada que comparar. Cuando lo pasás a `active` debería reflejar la fecha en que efectivamente mediste, porque a partir de ahí es el origen desde el cual se cuentan el tiempo y la evidencia.

### Dejar algo por la mitad

Un compromiso puede terminar sin checkpoint: la persona lo deja, cambia de interés, o simplemente no era el momento. Para eso está `status: discontinued`, que es terminal como `checkpoint_done` pero no afirma que hubo medición final.

Se llama `discontinued` y no `abandoned` a propósito. El sistema no juzga qué elegís aprender, y tampoco qué elegís dejar: es un hecho sobre el registro, no un reproche. Un compromiso discontinuado deja de reportarse y no vuelve a emitir avisos — un GPS no insiste con un destino que decidiste no visitar.

Lo que no cambia es lo que ya estaba a la vista: si el criterio había divergido de su congelado, cerrar el compromiso no lo esconde.

### Seguimiento sin fecha límite

No todo aprendizaje necesita una fecha tope. Un `skill_contract` puede declarar `checkpoint_date: null` y queda como **seguimiento abierto**: se mide contra un criterio congelado, se acumula evidencia y se cuenta el tiempo desde el baseline, pero no hay plazo que venza ni delta programado.

El campo sigue siendo obligatorio: hay que escribir `null` a propósito. Declarar que no querés fecha es una decisión; olvidarte el campo es un descuido, y el sistema no los trata igual.

Lo que cambia: `commitment_status` los reporta como *seguimiento* y no como *compromiso*, sin días restantes, y el aviso de checkpoint vencido no puede dispararse. Lo que no cambia: el instrumento se congela igual, y sin fecha tope eso importa más, no menos — un criterio puede derivar durante meses sin que nadie lo mire.

Esta modalidad es la más consistente con lo que el sistema dice de sí mismo. Si no busca empujarte a estudiar, obligarte a fijar una fecha para poder registrar tu práctica era una contradicción.

El validador hace cumplir la mitad espacial de esa invariante: si un `session_contract` referencia un `skill_contract` por `skill_contract:`, el `criterio` de la sesión debe ser idéntico al del contrato padre (comparación exacta, incluido el espaciado interno — dos criterios que difieren en un espacio son un cambio de instrumento). Si divergen, es error.

La mitad temporal la cubre `scripts/check_instrument_freeze.py`, que requiere que el proyecto esté en un repo git. El contrato declara `instrument_frozen_at: <commit-sha>`: el commit en el que se congeló el instrumento. El script recupera el `criterio` del contrato **en ese commit** y lo compara contra el actual. Si alguien afloja la rúbrica después de ver un resultado, el chequeo lo detecta y muestra ambos valores. Es obligatorio desde que el contrato pasa a `active`. Mientras está en `draft` el campo puede estar ausente o en `null` y el chequeo omite ese contrato: el instrumento todavía puede ajustarse, porque la medición no empezó.

Lo que esto garantiza, dicho sin exagerar: **no vuelve imposible cambiar el instrumento, lo vuelve visible.** Quien quiera hacerlo igual tiene que reapuntar `instrument_frozen_at` a un commit nuevo, y esa es una edición explícita que queda en el historial, no un cambio silencioso. Es la misma clase de garantía que da `ratified_by`: convertir un acto invisible en uno auditable. Quien controla el repo puede reescribir la historia, y ninguna herramienta local puede evitarlo.

Por eso el script distingue **tres** desenlaces y no dos: `0` verificado, `1` divergencia o contrato defectuoso, y `2` **no se pudo verificar** (no hay git, o el proyecto no está versionado). Un "no pude comprobarlo" nunca se reporta como éxito: sería la forma exacta de falso determinismo que este sistema existe para evitar.

Flujo para congelar: commitear el contrato con el `criterio` definitivo, y en un segundo commit escribir el sha del primero en `instrument_frozen_at`. Ese segundo commit no toca el `criterio`, así que la comparación cierra.

`instrument_frozen_at` tiene que ser un **sha de commit** (7 a 40 caracteres hexadecimales), no `HEAD`, ni un nombre de rama, ni una etiqueta. El script rechaza esas formas, y el motivo es la razón de ser del chequeo: una referencia móvil se mueve con cada commit, así que el "criterio congelado" seguiría al puntero y editar la rúbrica pasaría como verificado sin tocar el campo. Un congelado que apunta a algo que se mueve no congela nada.

## `teach_back` (documentar y enseñar)

Etapa opcional posterior a `verified`, no requisito de la verificación misma. Consolida por el efecto protégé (explicar algo obliga a organizarlo de una forma que la sola práctica no exige). Si la IA evalúa la calidad de la explicación, esa evaluación es otra lectura `proxy`, no un veredicto.

No tiene maquinaria propia, y es deliberado: un intento de enseñar **es práctica**, así que se registra como una línea más del log. Lo que sí conviene aprovechar es su subproducto más útil — trabarse explicando revela con precisión dónde el entendimiento era más fino de lo que parecía. Ese hueco suele ser una subhabilidad que faltaba mapear, y entra a `knowledge/` por el camino de la propuesta, como cualquier otro aprendizaje derivado del registro.

Que `teach_back` no sea un estado ni un campo es la decisión correcta: convertirlo en un casillero a completar lo transformaría en un requisito, y es justamente lo contrario de lo que es.

## Reutilización entre habilidades

`knowledge/shared/` guarda `mental_models/`, `failure_modes/` y `tools/` genéricos a cualquier habilidad (un mismo modelo mental puede servir para dos habilidades distintas). `knowledge/<skill>/` guarda lo específico de una habilidad y puede referenciar nodos de `shared/` por `id` en vez de duplicarlos. `init_skill.py` crea `<root>/shared/{mental_models,failure_modes,tools}/` junto con el scaffold de la skill (es hermano de `<skill>/`, cuelga de `--root`), de forma idempotente y sin pisar nada existente, para que la ubicación y la convención de nombre de archivo de un nodo (`<id>.md`) no sean algo que el usuario tenga que adivinar.

El criterio para elegir dónde va un nodo: preguntate si seguiría siendo cierto en una habilidad que todavía no empezaste. "Mi horno calienta de abajo" pertenece a la habilidad; "confiar en el resultado en vez de mirar el proceso" sirve para cualquiera. Ante la duda va en la habilidad — moverlo a `shared/` después es trivial, mientras que un `shared/` lleno de cosas que en realidad eran específicas deja de ser reutilizable.

## Uso

```
knowledge/    conocimiento: qué es la habilidad y cómo se descompone
contracts/    compromisos: skill/ (proyecto) y sessions/ (práctica puntual)
logs/         evidencia append-only
templates/    plantillas para crear nodos y contratos nuevos
scripts/      las cinco herramientas de verificación
tests/        suite de los scripts

```

```
python scripts/init_skill.py --name <skill> --domain-type physical|ai_mediated|cognitive_abstract
python scripts/validate_contracts.py knowledge contracts
python scripts/adherence.py logs/progress.md --skill <skill>
python scripts/decay_check.py knowledge          # dry-run, agregar --apply para escribir needs_review
python scripts/validate_evidence.py logs/progress.md knowledge contracts
python scripts/check_instrument_freeze.py contracts     # requiere git; exit 2 = no se pudo verificar
python scripts/commitment_status.py logs/progress.md contracts   # estado de compromisos activos vs. su ventana
```

Hay una CLI de conveniencia, `kdd.py` en la raíz, que envuelve esos scripts con las rutas convencionales del proyecto (`knowledge`, `contracts`, `logs/progress.md`) para no tener que escribirlas a mano. Los comandos largos de arriba siguen siendo válidos y son la interfaz de referencia; la CLI es solo una capa fina que les arma los argumentos.

```
python kdd.py init <skill> --domain-type physical|ai_mediated|cognitive_abstract
python kdd.py contracts          # = validate_contracts knowledge contracts
python kdd.py evidence           # = validate_evidence logs/progress.md knowledge contracts
python kdd.py decay [--apply]    # = decay_check knowledge
python kdd.py freeze             # = check_instrument_freeze contracts (requiere git; exit 2 = no se pudo verificar)
python kdd.py adherence [--skill X] [--subskill Y]   # = adherence logs/progress.md [--skill X] [--subskill Y]
python kdd.py commitment         # = commitment_status logs/progress.md contracts
python kdd.py check              # corre todas las verificaciones y resume una línea por herramienta
```

Cualquier comando acepta rutas explícitas en lugar de las convencionales, pero funciona sin argumentos desde la raíz del proyecto. Si se corre desde un directorio que no es la raíz de un proyecto KDD-Learning (faltan `knowledge/` o `contracts/`), el error es claro y el exit es distinto de cero, no un traceback.

`kdd check` agrega los exit codes de las herramientas sin aplastar la semántica de `check_instrument_freeze`: si alguna herramienta devolvió 1, devuelve 1; si ninguna devolvió 1 pero alguna devolvió 2, devuelve 2; si todas devolvieron 0, devuelve 0. El resumen dice explícitamente qué herramienta devolvió qué, para que un 2 (“no se pudo verificar”) nunca se lea como un éxito: es el falso determinismo que este sistema entero existe para evitar.

`validate_contracts.py` valida los nodos `.md` de los directorios que se le pasen. Un archivo sin frontmatter no es un nodo: se omite y se informa cuántos se omitieron, en vez de reportarse como error. Un archivo que **abre** frontmatter y no lo cierra sí es error: eso es un nodo roto, no un archivo ajeno. Lo mismo si el `---` está desplazado hacia abajo por líneas en blanco: es frontmatter mal puesto, no otra cosa. En cambio un `---` que aparece **después de contenido** es una línea horizontal de markdown, no un delimitador, y el archivo simplemente no es un nodo: se omite. La distinción importa porque un separador en una nota o en el propio log no debería producir un error sobre un frontmatter que nadie quiso escribir. La regla es que nada que parezca un nodo se omita en silencio: un BOM invisible al principio del archivo no lo excluye de la validación, porque un nodo corrupto que se saltea por un byte que nadie ve es peor que un error de más. Además de la forma de cada campo, verifica que `baseline_date` y `checkpoint_date` sean fechas ISO y que el checkpoint sea posterior al baseline — una ventana invertida o de cero días no permite medir ningún delta.

El `id` de un `skill_index` debe coincidir con el nombre de su directorio. Suena redundante hasta que no lo es: un renombre de carpeta que olvidó actualizar el `id`, o un nombre que el sistema operativo normalizó por detrás, dejan la carpeta y el nodo diciendo cosas distintas. Por eso `init_skill.py` también rechaza nombres que el SO cambiaría en silencio: punto o espacio final, y los nombres de dispositivo reservados de Windows (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`) — estos últimos en cualquier plataforma, porque una skill así creada en Linux vuelve el repositorio inclonable en Windows.

## Campos requeridos por tipo de nodo

Esta tabla es la referencia de qué campos exige `scripts/validate_contracts.py` para cada tipo de nodo. Es la misma `REQUIRED_FIELDS` del script, no una especificación paralela: un test (`tests/test_readme_required_fields.py`) la parsea y falla si difiere del código en cualquier tipo o campo, así que la tabla no puede desincronizarse de `validate_contracts.py` sin que la suite lo descubra. El nombre de archivo de un nodo es `<id>.md` (convención que `init_skill.py` aplica al generar el `index.md` de una skill y que se mantiene para todo nodo suelto).

<!-- BEGIN REQUIRED_FIELDS -->
| Tipo de nodo | Campos requeridos |
|---|---|
| `subskill` | `id` `type` `skill` `domain_type` `verification_type` `status` |
| `mental_model` | `id` `type` `scope` |
| `failure_mode` | `id` `type` `scope` |
| `tool` | `id` `type` `enables_verification` |
| `skill_contract` | `id` `type` `skill` `goal` `domain_type` `verification_type` `criterio` `instrument_frozen` `baseline_date` `checkpoint_date` `status` |
| `session_contract` | `id` `type` `skill` `subskill` `status` `criterio` |
| `skill_index` | `id` `type` `domain_type` |
<!-- END REQUIRED_FIELDS -->

Ninguno de estos scripts evalúa si una habilidad fue realmente lograda: verifican forma, fechas, referencias y vencimientos. La competencia la juzga `verification_type`, y en `proxy` y `human_rubric` esa lectura es humana.



La plantilla se entrega con las carpetas de instancia vacías: para empezar, seguí la sección "De cero a verde" más abajo como camino de entrada.


## De cero a verde

El orden importa más que el contenido, y es lo único que las plantillas no pueden decirte. Para una habilidad nueva:

1. `init_skill.py --name <skill> --domain-type <tipo>` — crea `knowledge/<skill>/` con su `index.md`, y `knowledge/shared/` si no existía.
2. Explorá el tema libremente **antes** de escribir subhabilidades. Los nodos son el destilado de esa exploración, no el punto de partida.
3. Escribí las subhabilidades en `knowledge/<skill>/subskills/` desde `templates/subskill.md`, y los nodos reutilizables en `knowledge/shared/{mental_models,failure_modes,tools}/`. Un nodo por archivo, nombrado `<id>.md`. Listalos en el `index.md`.
4. `validate_contracts.py knowledge contracts` — hasta que quede en verde. Cada error dice qué campo falta o qué valor no es válido.
5. Escribí el `skill_contract` en `draft` desde su plantilla, con el `criterio` ya definitivo: es el instrumento, y a partir de acá no debería cambiar.
6. Escribí el `session_contract` de la primera práctica, con el `criterio` **idéntico** al del contrato padre.
7. Registrá la práctica como una línea en `logs/progress.md`, respetando el formato de su cabecera.
8. `validate_evidence.py logs/progress.md knowledge contracts` — verifica que esa línea apunte a nodos que existen. Acá vas a ver un aviso de que hay evidencia contra un contrato en `draft`: es esperado en este orden y se cierra solo en el paso siguiente.
9. Cuando el baseline esté tomado, activá el compromiso: `status: active`, commit. Después escribí el sha de **ese** commit en `instrument_frozen_at` y volvé a commitear.
10. `check_instrument_freeze.py contracts` y `commitment_status.py logs/progress.md contracts`.

Los pasos 5 a 9 son los que más se equivocan: el `criterio` se decide una vez y se congela, y el congelado se hace después del baseline, no antes.

## Tests del propio tooling

```
python -m unittest discover -s tests -p "test_*.py"
```

Cubren los cinco scripts. Conviene saber qué significan y qué no: verifican que los scripts hagan lo que dicen, no que el sistema de aprendizaje funcione. Y una suite en verde no es prueba de corrección — es prueba de que los casos que a alguien se le ocurrieron funcionan. Varios de los chequeos que hoy existen nacieron de rondas de auditoría que atacaron a propósito garantías ya dadas por buenas, y encontraron que el código validaba la *forma* de un campo en vez de la *propiedad* que ese campo debía asegurar: "entero positivo" en vez de "caduca de verdad", "una fecha ISO" en vez de "una fecha pasada", "un sha" en vez de "una referencia inmutable".

Los tests no afirman nada sobre el estado de los datos reales del proyecto (cuántos nodos hay, en qué punto del ciclo está un contrato). Usar el sistema —agregar una habilidad, activar un compromiso— no debe poner la suite en rojo; si lo hace, el test está mal, no los datos.


