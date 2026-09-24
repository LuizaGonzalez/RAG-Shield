"""Capa 2: separacion explicita entre datos e instrucciones.

Responsable: Persona C
Envuelve cada chunk sanitizado en delimitadores claros y agrega un
system prompt que indica que todo lo que este dentro de esos
delimitadores es informacion, nunca una orden a seguir.
"""


def build_prompt(query: str, sanitized_chunks: list) -> str:
    raise NotImplementedError
