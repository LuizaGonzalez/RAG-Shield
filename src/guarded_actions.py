"""Capa 3 (opcional): minimo privilegio a nivel de herramientas.

Responsable: compartido
Ninguna accion con consecuencias (enviar correo, aprobar solicitud)
se dispara directo desde algo leido en un documento recuperado, sin
un paso adicional de confirmacion.
"""


def request_action_confirmation(action: str, params: dict) -> bool:
    raise NotImplementedError
