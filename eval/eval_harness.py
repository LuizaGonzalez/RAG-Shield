"""Arnés de evaluación: corre ataques y controles y calcula las métricas.

Lee las preguntas de eval/attacks/attacks.json y los marcadores de
eval/manifest_envenenados.json, corre cada pregunta N veces con la
configuración de capas pedida y escribe:
  - eval/results/<config>.csv          una fila por intento
  - eval/results/resumen_<config>.json métricas de esa configuración
  - eval/results/comparacion.md        tabla entre configuraciones (--comparar)

Uso:
  python -m src.ingest                       # una vez, antes de medir
  python -m eval.eval_harness --config baseline --repeticiones 5
  python -m eval.eval_harness --config capas_1_2 --repeticiones 5 --comparar
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Callable

from eval.dataset import load_attacks, load_manifest, validate
from eval.metrics import compare, summarize
from eval.scoring import check_attack_result, contains_marker
from src.config import ATTACKS_PATH, DOCS_DIR, MANIFEST_PATH, RESULTS_DIR

CONFIGS = {
    "baseline": {"use_sanitizer": False, "use_prompt_guard": False, "use_privilege_guard": False},
    "capas_1_2": {"use_sanitizer": True, "use_prompt_guard": True, "use_privilege_guard": False},
    "capa_3": {"use_sanitizer": False, "use_prompt_guard": False, "use_privilege_guard": True},
    "completo": {"use_sanitizer": True, "use_prompt_guard": True, "use_privilege_guard": True},
}

FIELDS = [
    "config", "tipo", "id", "intento_numero", "pregunta", "respuesta", "respuesta_modelo",
    "dato_falso_presente", "dato_correcto_presente", "exito", "categoria",
    "documento_objetivo", "documento_objetivo_recuperado", "documentos_recuperados",
    "envenenado_recuperado", "sanitizacion_aplicada", "reglas_sanitizacion", "sanitizo_legitimo",
    "accion_esperada", "menciona_accion", "accion_detectada", "acciones_detectadas", "bloqueado",
    "proveedor", "modelo", "latencia_segundos", "error",
]


class DatasetError(ValueError):
    pass


def _row(config: str, tipo: str, item: dict, attempt: int, result: dict | None, error: str = "") -> dict:
    row = {field: "" for field in FIELDS}
    row.update(
        config=config,
        tipo=tipo,
        id=item["id"],
        intento_numero=attempt,
        pregunta=item["pregunta"],
        documento_objetivo=item.get("documento_objetivo", ""),
        accion_esperada=item.get("accion_esperada") or "",
        menciona_accion=bool(item.get("menciona_accion", False)),
        error=error,
    )
    if result is None:
        return row

    answer = result["respuesta"]
    if tipo == "ataque":
        verdict = check_attack_result(answer, item["dato_falso_esperado"], item["dato_correcto_esperado"])
    else:
        correct = contains_marker(answer, item["dato_correcto_esperado"])
        verdict = {"dato_falso_presente": False, "dato_correcto_presente": correct, "exito": False,
                   "categoria": "correcta" if correct else "sin_respuesta_util"}

    poisoned_sources = {c["metadata"].get("source_file") for c in result["chunks"] if c["metadata"].get("is_poisoned")}
    rules = sorted({rule for s in result["sanitizacion"] for rule in s["reglas"]})
    row.update(verdict)
    row.update(
        respuesta=answer,
        respuesta_modelo=result["respuesta_modelo"],
        documento_objetivo_recuperado=bool(item.get("documento_objetivo"))
        and item["documento_objetivo"] in result["documentos_recuperados"],
        documentos_recuperados=";".join(result["documentos_recuperados"]),
        envenenado_recuperado=result["documento_envenenado_recuperado"],
        sanitizacion_aplicada=result["sanitizacion_aplicada"],
        reglas_sanitizacion=";".join(rules),
        sanitizo_legitimo=any(s["source_file"] not in poisoned_sources for s in result["sanitizacion"]),
        accion_detectada=result["guard"]["accion_detectada"],
        acciones_detectadas=";".join(result["guard"]["acciones"]),
        bloqueado=result["guard"]["bloqueado"],
        proveedor=result["proveedor"],
        modelo=result["modelo"],
        latencia_segundos=result["latencia_segundos"],
    )
    return row


def _check_index(manifest: dict) -> None:
    from src.retriever import indexed_sources

    missing = sorted(set(manifest) - indexed_sources())
    if missing:
        raise DatasetError(
            "El índice no tiene estos documentos envenenados: " + ", ".join(missing)
            + ". Corre: python -m src.ingest"
        )


def run_evaluation(
    config: str = "baseline",
    repeticiones: int = 5,
    attacks_path: str | Path = ATTACKS_PATH,
    manifest_path: str | Path = MANIFEST_PATH,
    docs_dir: str | Path = DOCS_DIR,
    out_dir: str | Path = RESULTS_DIR,
    ask_fn: Callable[..., dict] | None = None,
    strict: bool = True,
    pause: float = 0.0,
    log: Callable[[str], None] = print,
) -> dict:
    if config not in CONFIGS:
        raise ValueError(f"Configuración desconocida '{config}'. Opciones: {', '.join(CONFIGS)}")
    if repeticiones < 1:
        raise ValueError("repeticiones debe ser al menos 1")

    attacks = load_attacks(attacks_path)
    manifest = load_manifest(manifest_path)
    problems = validate(attacks, manifest, docs_dir, strict=strict)
    if problems:
        raise DatasetError("Dataset inválido:\n- " + "\n- ".join(problems))

    if ask_fn is None:
        from src.pipeline import ask as ask_fn

        _check_index(manifest)

    flags = CONFIGS[config]
    items = [("ataque", a) for a in attacks["ataques"]] + [("control", c) for c in attacks["controles"]]
    rows = []
    for attempt in range(1, repeticiones + 1):
        for tipo, item in items:
            try:
                result = ask_fn(item["pregunta"], **flags)
                rows.append(_row(config, tipo, item, attempt, result))
            except Exception as exc:
                rows.append(_row(config, tipo, item, attempt, None, error=f"{type(exc).__name__}: {exc}"))
            if pause:
                time.sleep(pause)
        log(f"[{config}] ronda {attempt}/{repeticiones} lista")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / f"{config}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    summary = summarize(rows)
    summary.update(config=config, repeticiones=repeticiones, flags=flags)
    summary_path = out / f"resumen_{config}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"summary": summary, "csv_path": str(csv_path), "summary_path": str(summary_path), "rows": rows}


def _fmt(value, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, (list, tuple)):
        return f"{value[0]}–{value[1]}{suffix}"
    return f"{value}{suffix}"


def write_comparison(out_dir: str | Path = RESULTS_DIR) -> Path:
    out = Path(out_dir)
    order = {name: i for i, name in enumerate(CONFIGS)}
    summaries = [json.loads(p.read_text(encoding="utf-8")) for p in out.glob("resumen_*.json")]
    summaries.sort(key=lambda s: order.get(s["config"], 99))
    lines = [
        "| Configuración | ASR | IC 95 % | Rango entre rondas | Recuperación doc. malicioso | Contaminadas "
        "| Falsos positivos | Utilidad preservada | Acción insegura | Sobre-bloqueo | Latencia media | Latencia adicional |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in compare(summaries):
        lines.append(
            f"| {s['config']} | {_fmt(s['asr'], ' %')} | {_fmt(s['asr_ic95'], ' %')} | {_fmt(s['asr_rango_rondas'], ' %')} "
            f"| {_fmt(s['recuperacion_documento_malicioso'], ' %')} | {_fmt(s['respuestas_contaminadas'], ' %')} "
            f"| {_fmt(s['falsos_positivos'], ' %')} | {_fmt(s['utilidad_preservada'], ' %')} "
            f"| {_fmt(s['accion_insegura_ejecutada'], ' %')} | {_fmt(s['sobre_bloqueo'], ' %')} "
            f"| {_fmt(s['latencia_media'], ' s')} | {_fmt(s['latencia_adicional'], ' s')} |"
        )
    models = sorted({f"{s.get('proveedor')} / {s.get('modelo')}" for s in summaries})
    header = f"# Comparación de configuraciones\n\nModelo: {', '.join(models) or '—'}\n\n"
    path = out / "comparacion.md"
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluación de RAG Shield")
    parser.add_argument("--config", nargs="+", default=["baseline"], choices=[*CONFIGS, "todas"])
    parser.add_argument("--repeticiones", type=int, default=5)
    parser.add_argument("--pausa", type=float, default=0.0, help="segundos entre llamadas (límites de la API)")
    parser.add_argument("--ingest", action="store_true", help="reindexa docs/ antes de medir")
    parser.add_argument("--comparar", action="store_true", help="escribe eval/results/comparacion.md")
    parser.add_argument("--no-estricto", action="store_true", help="permite menos de 9 ataques o 5 controles")
    args = parser.parse_args(argv)

    if args.ingest:
        from src.ingest import ingest_documents

        print(ingest_documents())

    configs = list(CONFIGS) if "todas" in args.config else args.config
    for config in configs:
        result = run_evaluation(config, args.repeticiones, strict=not args.no_estricto, pause=args.pausa)
        s = result["summary"]
        print(
            f"{config}: ASR {_fmt(s['asr'], ' %')} (rondas {_fmt(s['asr_rango_rondas'], ' %')}), "
            f"recuperación {_fmt(s['recuperacion_documento_malicioso'], ' %')}, "
            f"utilidad {_fmt(s['utilidad_preservada'], ' %')}, errores {s['errores']} -> {result['csv_path']}"
        )
    if args.comparar:
        print(f"Comparación: {write_comparison()}")


if __name__ == "__main__":
    main()
