"""Ingesta de documentos hacia ChromaDB.

Responsable: Persona B
Recorre docs/legitimos y docs/envenenados, trocea cada documento,
calcula embeddings y los guarda en la coleccion de ChromaDB.
Cada chunk debe conservar en metadata:
  - is_poisoned: bool
  - canal: "archivo" | "correo" | "web"
  - source_file: str
"""


def ingest_documents(docs_path: str, collection_name: str = "novacred_docs"):
    raise NotImplementedError


if __name__ == "__main__":
    ingest_documents("docs/")
