---
id: <slug-unico>
type: subskill
skill: <skill-slug>
domain_type: physical            # ai_mediated | physical | cognitive_abstract
verification_type: proxy         # instrumented | proxy | human_rubric
status: draft                    # draft | practicing | verified | needs_review
depends_on: []                   # ids de otras subskills, si las hay
applies_mental_models: []        # ids de nodos mental_model (shared o del skill)
applies_failure_modes: []        # ids de nodos failure_mode (shared o del skill)
required_tools: []               # ids de nodos tool
review_after_days: 14
last_verified: null
# ratified_by: NO viene prellenado a proposito. Se AGREGA recien al promover el
# nodo a status: verified, y escribirlo es el acto de ratificar: declara quien se
# hace cargo de esa afirmacion. Si viniera por defecto, la ratificacion se
# heredaria de una plantilla en vez de decidirse. Valores: human (siempre valido)
# o instrument (solo si verification_type: instrumented).
---

## Qué es

<Descripción breve de la subhabilidad y por qué está en el 20% clave.>

## Criterio de suficiencia

<Cómo se sabe que esta subhabilidad está lograda, en términos observables. Si verification_type
es instrumented o proxy, incluir un umbral numérico. Si es human_rubric, incluir una escala
explícita, nunca una palabra vaga como "bien" o "cómodo".>
