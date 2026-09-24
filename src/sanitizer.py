"""Capa 1: sanitizacion basada en reglas del contenido recuperado.

Responsable: Persona C
Limpia cada chunk antes de que llegue al prompt:
  - comentarios y tags HTML ocultos (BeautifulSoup)
  - caracteres Unicode invisibles o de ancho cero (unicodedata)
  - frases que imitan instrucciones de sistema (regex)
Debe devolver tambien un flag/log de que fue neutralizado, para
que el front pueda mostrar el aviso de bloqueo.
"""


def sanitize(chunk: str) -> str:
    raise NotImplementedError
