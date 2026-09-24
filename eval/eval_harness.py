"""Arnes de evaluacion: corre ataques y controles, calcula metricas.

Responsable: Persona D
Corre el mismo set de preguntas (ataques + controles legitimos)
contra distintas configuraciones de capas, y calcula:
  - ASR (tasa de exito del ataque)
  - tasa de recuperacion del documento malicioso
  - tasa de falsos positivos
  - utilidad preservada
  - latencia adicional por capa
Guarda resultados en eval/results/ como CSV.
"""


def run_evaluation(config: dict) -> dict:
    raise NotImplementedError


if __name__ == "__main__":
    run_evaluation({
        "use_sanitizer": False,
        "use_prompt_guard": False,
        "use_privilege_guard": False,
    })
