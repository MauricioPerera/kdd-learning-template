---
id: <skill-slug>-compromiso-<yyyy-mm>
type: skill_contract
skill: <skill-slug>
goal: "<meta de desempeño en una sola oración>"
subskills: []                    # ids de subskills bajo este compromiso
domain_type: physical            # ai_mediated | physical | cognitive_abstract
verification_type: proxy         # instrumento fijado, mismo para baseline y checkpoint
criterio: "<criterio binario u observable, con umbral si aplica>"
instrument_frozen: true          # no debe cambiar entre baseline y checkpoint
instrument_frozen_at: <commit-sha>   # commit donde se congelo el instrumento; obligatorio si status es active o checkpoint_done (ver scripts/check_instrument_freeze.py)
baseline_date: <yyyy-mm-dd>
checkpoint_date: <yyyy-mm-dd>   # null = seguimiento abierto sin fecha limite (el campo sigue siendo requerido)
status: draft                    # draft -> active -> checkpoint_done; discontinued = se cerro sin llegar al checkpoint (terminal)
---

## Compromiso

<Qué se compromete la persona a hacer en la ventana entre baseline y checkpoint.
No incluir aquí el resultado del baseline una vez tomado, para no anclar la evaluación
del checkpoint.>
