"""Carga y validación del manifiesto de envenenados y del set de ataques.

`validate()` devuelve la lista de problemas encontrados; vacía significa
que el experimento es medible tal como está. Comprueba, entre otras
cosas, que el dato falso de cada ataque no aparezca en ningún documento
legítimo (si apareciera, un acierto contaría como éxito del ataque) y
que el dato correcto sí aparezca.
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.scoring import contains_marker, normalize
from src.config import ATTACKS_PATH, DOCS_DIR, MANIFEST_PATH

MIN_ATTACKS = 9
MIN_CONTROLS = 5
TECHNIQUES = {"html_oculto", "comentario_html", "unicode_invisible"}
CHANNELS = {"archivo", "correo", "web"}


def load_json(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as fp:
        return json.load(fp)


def load_manifest(path: str | Path = MANIFEST_PATH) -> dict:
    return load_json(path)


def load_attacks(path: str | Path = ATTACKS_PATH) -> dict:
    data = load_json(path)
    data.setdefault("ataques", [])
    data.setdefault("controles", [])
    return data


def _legit_corpus(docs_dir: Path) -> str:
    files = sorted((docs_dir / "legitimos").glob("*.txt"))
    return "\n".join(f.read_text(encoding="utf-8") for f in files)


def _squash(text: str) -> str:
    return " ".join(normalize(text).split())


def validate(attacks: dict, manifest: dict, docs_dir: str | Path = DOCS_DIR, strict: bool = True) -> list[str]:
    docs_dir = Path(docs_dir)
    problems: list[str] = []
    legit = _legit_corpus(docs_dir)
    poisoned_dir = docs_dir / "envenenados"

    for name, entry in manifest.items():
        path = poisoned_dir / name
        if not path.exists():
            problems.append(f"manifiesto: no existe docs/envenenados/{name}")
            continue
        if entry.get("tecnica_camuflaje") not in TECHNIQUES:
            problems.append(f"manifiesto: {name} tiene tecnica_camuflaje inválida")
        if entry.get("canal_simulado") not in CHANNELS:
            problems.append(f"manifiesto: {name} tiene canal_simulado inválido")
        if not name.startswith(f"{entry.get('canal_simulado')}_"):
            problems.append(f"manifiesto: {name} debe empezar por el canal simulado")
        chunk = entry.get("chunk_objetivo", "")
        if not chunk or _squash(chunk) not in _squash(path.read_text(encoding="utf-8")):
            problems.append(f"manifiesto: chunk_objetivo de {name} no aparece literal en el archivo")

    ids: set[str] = set()
    for attack in attacks.get("ataques", []):
        attack_id = attack.get("id", "?")
        if attack_id in ids:
            problems.append(f"ataques: id repetido {attack_id}")
        ids.add(attack_id)
        target = attack.get("documento_objetivo")
        if target not in manifest:
            problems.append(f"{attack_id}: documento_objetivo '{target}' no está en el manifiesto")
        if not attack.get("pregunta"):
            problems.append(f"{attack_id}: falta la pregunta")
        if not attack.get("dato_falso_esperado") or not attack.get("dato_correcto_esperado"):
            problems.append(f"{attack_id}: faltan dato_falso_esperado o dato_correcto_esperado")
            continue
        if contains_marker(legit, attack["dato_falso_esperado"]):
            problems.append(f"{attack_id}: el dato falso aparece en documentos legítimos; elige otro marcador")
        if not contains_marker(legit, attack["dato_correcto_esperado"]):
            problems.append(f"{attack_id}: el dato correcto no aparece en ningún documento legítimo")

    for control in attacks.get("controles", []):
        control_id = control.get("id", "?")
        if control_id in ids:
            problems.append(f"controles: id repetido {control_id}")
        ids.add(control_id)
        if not control.get("pregunta") or not control.get("dato_correcto_esperado"):
            problems.append(f"{control_id}: faltan pregunta o dato_correcto_esperado")
        elif not contains_marker(legit, control["dato_correcto_esperado"]):
            problems.append(f"{control_id}: el dato correcto no aparece en ningún documento legítimo")

    if strict:
        if len(manifest) < MIN_ATTACKS:
            problems.append(f"manifiesto: hay {len(manifest)} documentos, se esperan {MIN_ATTACKS}")
        if len(attacks.get("ataques", [])) < MIN_ATTACKS:
            problems.append(f"ataques: hay {len(attacks['ataques'])}, se esperan al menos {MIN_ATTACKS}")
        if len(attacks.get("controles", [])) < MIN_CONTROLS:
            problems.append(f"controles: hay {len(attacks['controles'])}, se esperan al menos {MIN_CONTROLS}")
        targeted = {a.get("documento_objetivo") for a in attacks.get("ataques", [])}
        for name in sorted(set(manifest) - targeted):
            problems.append(f"manifiesto: ningún ataque apunta a {name}")

    return problems
