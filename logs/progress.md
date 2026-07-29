# Log de evidencia

Formato append-only. Una línea por evento. Nunca editar líneas existentes, solo agregar.

Formato: `<iso-timestamp> | skill=<slug> | subskill=<slug> | session=<session-id> | event=<attempted|verified|needs_review> | result=<pass|partial|fail|pending> | notes="<texto libre>"`

`result=pending` es para cuando la práctica ocurrió pero todavía no se evaluó contra el criterio — típico en `human_rubric` y `proxy`, donde practicar y evaluar son dos momentos distintos. Sin ese valor habría que elegir entre `partial` y `fail` para algo que nadie midió, y eso es inventar un resultado.

