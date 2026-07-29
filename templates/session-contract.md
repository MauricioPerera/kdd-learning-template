---
id: session-<yyyy-mm-dd>-<subskill-slug>
type: session_contract
skill: <skill-slug>
subskill: <subskill-slug>        # debe existir como nodo en knowledge/<skill>/subskills/
checkpoint: null                 # null | baseline | final -- solo si pertenece a un skill_contract
skill_contract: null             # id del skill_contract, si checkpoint no es null
status: draft                    # draft -> attempted -> verified
criterio: "<criterio binario u observable, con umbral si aplica>"   # debe coincidir exactamente con el criterio del skill_contract referenciado (el criterio es el instrumento; divergir invalida el delta baseline/checkpoint)
tools_needed: []                 # ids de nodos tool
---
