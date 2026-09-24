"""Recuperacion de chunks desde ChromaDB.

Responsable: Persona B
Dada una pregunta, devuelve los k chunks mas parecidos, con su metadata
intacta (is_poisoned, canal, source_file) para que eval_harness pueda
medir tasa de recuperacion del documento malicioso.
"""


def retrieve(query: str, k: int = 3, collection_name: str = "novacred_docs"):
    raise NotImplementedError
