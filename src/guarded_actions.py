"""Capa 3 (opcional): minimo privilegio a nivel de herramientas.

Responsable: compartido
Ninguna accion con consecuencias (enviar correo, aprobar solicitud)
se dispara directo desde algo leido en un documento recuperado, sin
un paso adicional de confirmacion.
"""

from __future__ import annotations


def request_action_confirmation(action: str, params: dict) -> bool:
    if not isinstance(action, str) or not action.strip():
        return False

    dangerous_actions = {
        "aprobar_credito",
        "aprobar_solicitud",
        "condonar_mora",
        "enviar_correo",
        "enviar_mensaje",
        "modificar_saldo",
    }

    normalized_action = action.strip().lower()
    if normalized_action not in dangerous_actions:
        return True

    if not isinstance(params, dict):
        return False

    return bool(params.get("confirmado") or params.get("approval_required"))
