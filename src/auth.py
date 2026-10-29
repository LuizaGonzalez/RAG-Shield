"""Usuarios, roles y permisos (mínimo privilegio).

Dos roles, uno por cada tipo de pantalla del diseño:
  - laboratorio: jurado y profesora. Ve el experimento completo: enciende y
    apaga capas, ve la cuarentena, sube documentos e importa correos (IMAP)
    a la base, aprueba propuestas, ve resultados y auditoría.
  - empleado: analista de un departamento. Solo consulta al asistente con
    las tres capas siempre activas, solo recupera documentos aprobados de
    su departamento, adjunta archivos que viven en su sesión y puede
    proponer un documento, que entra en cuarentena.

Los permisos se revisan en el servidor antes de cada acción (`require`),
no solo escondiendo botones. Las contraseñas se guardan con PBKDF2-SHA256
en usuarios.json, que no se sube a git. Para crear un usuario:

  python -m src.auth crear --usuario ana.cardenas --nombre "Ana Cárdenas" \
      --rol empleado --departamento cartera
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from src.config import DEPARTMENTS, users_path

ITERATIONS = 200_000
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")

PERMISSIONS: dict[str, frozenset[str]] = {
    "laboratorio": frozenset({
        "ver_laboratorio", "configurar_capas", "ver_cuarentena", "subir_base", "importar_correo", "reindexar",
        "revisar_propuestas", "ver_resultados", "ver_auditoria",
    }),
    "empleado": frozenset({"consultar_asistente", "adjuntar_sesion", "proponer_documento"}),
}
ROLE_LABELS = {"laboratorio": "Laboratorio", "empleado": "Empleado"}


@dataclass(frozen=True)
class User:
    usuario: str
    nombre: str
    rol: str
    departamento: str | None = None

    @property
    def iniciales(self) -> str:
        return "".join(p[0] for p in self.nombre.split()[:2]).upper() or self.usuario[:2].upper()


class AuthError(ValueError):
    pass


def can(user: User | None, permission: str) -> bool:
    return user is not None and permission in PERMISSIONS.get(user.rol, frozenset())


def require(user: User | None, permission: str) -> None:
    if not can(user, permission):
        raise PermissionError(f"El rol '{user.rol if user else 'anónimo'}' no tiene permiso para {permission}.")


def hash_password(password: str, salt: bytes | None = None, iterations: int = ITERATIONS) -> dict:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {"salt": salt.hex(), "hash": digest.hex(), "iteraciones": iterations}


def _verify(password: str, record: dict) -> bool:
    expected = hash_password(password, bytes.fromhex(record["salt"]), int(record["iteraciones"]))["hash"]
    return hmac.compare_digest(expected, record["hash"])


def load_users(path: str | Path | None = None) -> dict:
    path = Path(path or users_path())
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("usuarios", {})


def _validate(usuario: str, rol: str, departamento: str | None) -> None:
    if not USERNAME.match(usuario):
        raise AuthError("El usuario debe tener 3-40 caracteres: minúsculas, números, punto, guion o guion bajo.")
    if rol not in PERMISSIONS:
        raise AuthError(f"Rol inválido '{rol}'. Usa: {', '.join(PERMISSIONS)}")
    if rol == "empleado" and departamento not in DEPARTMENTS:
        raise AuthError(f"Un empleado necesita departamento: {', '.join(DEPARTMENTS)}")
    if rol != "empleado" and departamento:
        raise AuthError("Solo los empleados tienen departamento.")


def create_user(usuario: str, nombre: str, rol: str, password: str, departamento: str | None = None,
                path: str | Path | None = None) -> User:
    _validate(usuario, rol, departamento)
    if len(password) < 8:
        raise AuthError("La contraseña debe tener al menos 8 caracteres.")
    path = Path(path or users_path())
    users = load_users(path)
    users[usuario] = {"nombre": nombre, "rol": rol, "departamento": departamento, **hash_password(password)}
    path.write_text(json.dumps({"usuarios": users}, ensure_ascii=False, indent=2), encoding="utf-8")
    return User(usuario, nombre, rol, departamento)


def authenticate(usuario: str, password: str, path: str | Path | None = None) -> User | None:
    record = load_users(path).get((usuario or "").strip().lower())
    if not record or not password:
        # Igual se calcula un hash para no revelar por tiempo si el usuario existe.
        hash_password(password or "", b"\0" * 16)
        return None
    if not _verify(password, record):
        return None
    try:
        _validate(usuario.strip().lower(), record.get("rol", ""), record.get("departamento"))
    except AuthError:
        return None
    return User(usuario.strip().lower(), record.get("nombre") or usuario, record["rol"], record.get("departamento"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Usuarios de RAG Shield")
    sub = parser.add_subparsers(dest="cmd", required=True)
    crear = sub.add_parser("crear", help="crea o reemplaza un usuario")
    crear.add_argument("--usuario", required=True)
    crear.add_argument("--nombre", required=True)
    crear.add_argument("--rol", required=True, choices=list(PERMISSIONS))
    crear.add_argument("--departamento", choices=list(DEPARTMENTS))
    sub.add_parser("listar", help="lista los usuarios sin mostrar contraseñas")
    args = parser.parse_args(argv)

    if args.cmd == "listar":
        for name, record in sorted(load_users().items()):
            print(f"{name}\t{record.get('rol')}\t{record.get('departamento') or '—'}\t{record.get('nombre')}")
        return

    password = getpass.getpass("Contraseña: ")
    if password != getpass.getpass("Repite la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden.")
    try:
        user = create_user(args.usuario, args.nombre, args.rol, password, args.departamento)
    except AuthError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Usuario {user.usuario} ({user.rol}) guardado en {users_path()}")


if __name__ == "__main__":
    main()
