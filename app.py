"""Frontend de RAG Shield según el diseño "RAG Shield · Interfaces finales".

Cada pantalla tiene dueño y los permisos se revisan en el servidor
(src/auth.py), no solo escondiendo botones:

  Pantalla                          Rol           Qué puede hacer
  Inicio de sesión                  todos         entrar; 5 intentos fallidos bloquean la sesión
  Laboratorio · Asistente           laboratorio   capas on/off, comparar, subir a la base,
                                                  reindexar, ver y resolver la cuarentena
  Laboratorio · Resultados          laboratorio   métricas de eval/results/
  Laboratorio · Auditoría           laboratorio   quién preguntó, qué fuentes y qué capa actuó
  Empleado                          empleado      preguntar con las 3 capas siempre activas,
                                                  solo documentos aprobados de su departamento,
                                                  adjuntos de sesión, proponer un documento
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from eval.eval_harness import MAX_ERROR_RATE
from eval.scoring import contains_marker
from src import mail, storage
from src.auth import ROLE_LABELS, User, authenticate, can, load_users, require
from src.config import ATTACKS_PATH, DEPARTMENTS, MANIFEST_PATH, RESULTS_DIR, docs_dir
from src.generator import LLMConfigError, model_name, provider
from src.guarded_actions import REQUEST_MESSAGE, detect_action_request
from src.ingest import ingest_documents
from src.pipeline import ask
from src.retriever import IndexNotReadyError, employee_filter, indexed_documents, rank_chunks

st.set_page_config(page_title="RAG Shield · NovaCred", page_icon="🛡️", layout="wide")

MAX_LOGIN_ATTEMPTS = 5
ATTACHMENT_CHUNKS = 4
CONFIG_LABELS = {
    "baseline": "Sin defensas",
    "capas_1_2": "Capas 1 + 2",
    "capa_3": "Solo Capa 3",
    "completo": "Capas 1 + 2 + 3",
}
TECHNIQUE_LABELS = {
    "html_oculto": "HTML oculto",
    "comentario_html": "Comentario HTML",
    "unicode_invisible": "Unicode invisible",
    "ninguna": "—",
}
RULE_LABELS = {
    "html_oculto": "texto oculto con estilos HTML",
    "comentario_html": "comentario HTML",
    "unicode_invisible": "caracteres Unicode invisibles",
    "propuesta pendiente": "propuesta pendiente de aprobación",
}
ORIGIN_LABELS = {"base": "Legítimo", "subido": "Subido", "propuesta": "Propuesta", "correo": "Correo"}
ALL_LAYERS = {"use_sanitizer": True, "use_prompt_guard": True, "use_privilege_guard": True}
NO_LAYERS = {"use_sanitizer": False, "use_prompt_guard": False, "use_privilege_guard": False}

ICONS = {
    "shield": '<path d="M12 3 4 6v6c0 5 3.4 8 8 9 4.6-1 8-4 8-9V6z"/>',
    "doc": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "clip": '<path d="m21 12-8.5 8.5a5 5 0 0 1-7-7L14 5a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 8"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "alert": '<path d="m10.3 3.9-8.2 14A2 2 0 0 0 3.8 21h16.4a2 2 0 0 0 1.7-3.1l-8.2-14a2 2 0 0 0-3.4 0z"/>'
             '<path d="M12 9v4M12 17h.01"/>',
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
:root{--rs-ink:#26262b;--rs-ink-2:#4a4a52;--rs-muted:#6b6b75;--rs-line:#ececef;--rs-line-2:#d6d6dc;
--rs-primary:#3c3c42;--rs-on-primary:#ffffff;--rs-bg:#f7f7f9;--rs-card:#ffffff;--rs-dashed:#c9c9d1;
--rs-ok-bg:#e3f6ea;--rs-ok:#17703c;--rs-warn-bg:#fdf1d6;--rs-warn:#7a4e0a;--rs-bad-bg:#fde4e4;--rs-bad:#b32d20;
--rs-hold-bg:#ececef;--rs-hold:#3a3a42;--rs-info-bg:#eef2ff;--rs-info:#2f4bb8;--rs-orange-bg:#fff0e6;--rs-orange:#b4521a;
--rs-soft-bg:#f0f0f3;--rs-soft:#4a4a52;--rs-dot:#2fa36b}
/* Tema oscuro: data-rs-theme lo pone el script de tema según el fondo real de la app. */
:root[data-rs-theme="dark"]{--rs-ink:#e8e8ec;--rs-ink-2:#c9c9d1;--rs-muted:#a3a3ad;--rs-line:#2c2c34;--rs-line-2:#3a3a44;
--rs-primary:#4a4a55;--rs-on-primary:#ffffff;--rs-bg:#141418;--rs-card:#1e1e24;--rs-dashed:#4a4a55;
--rs-ok-bg:#163322;--rs-ok:#7fd6a0;--rs-warn-bg:#3a2e12;--rs-warn:#f0c674;--rs-bad-bg:#3d1a1a;--rs-bad:#f4a3a3;
--rs-hold-bg:#2a2a31;--rs-hold:#d4d4da;--rs-info-bg:#1f2647;--rs-info:#aab8ff;--rs-orange-bg:#3a2412;--rs-orange:#f0a46b;
--rs-soft-bg:#2a2a31;--rs-soft:#c9c9d1;--rs-dot:#4cc38a}
.stApp{font-family:'Inter',system-ui,sans-serif;}
.stApp{--rs-top:6.4rem}
.block-container{padding-top:4rem;padding-bottom:1rem;max-width:1440px;}
.rs-brand{display:flex;align-items:center;gap:10px;margin:0 0 12px}
.rs-logo{width:36px;height:36px;border-radius:11px;background:var(--rs-primary);color:var(--rs-on-primary);display:grid;place-items:center;flex:none}
.rs-brand b{display:block;font-size:15px;font-weight:600;line-height:1.2;color:var(--rs-ink)}
.rs-brand small{font-size:12px;color:var(--rs-muted)}
.rs-label{font-size:11px;letter-spacing:.08em;font-weight:600;color:var(--rs-muted);text-transform:uppercase;margin:18px 0 6px 2px}
.rs-h{font-size:15px;font-weight:600;color:var(--rs-ink);margin:6px 0 4px}
.rs-title{font-size:22px;font-weight:600;color:var(--rs-ink);margin:0}
.rs-sub{font-size:13px;color:var(--rs-muted);margin:2px 0 10px;line-height:1.5}
.rs-status{background:var(--rs-ok-bg);color:var(--rs-ok);border-radius:12px;padding:12px 14px;font-size:14px;line-height:1.5}
.rs-status.err{background:var(--rs-bad-bg);color:var(--rs-bad)}
.rs-row{display:grid;gap:10px;align-items:center;padding:8px 14px;background:var(--rs-card);border:1px solid var(--rs-line);
border-radius:12px;font-size:13px;color:var(--rs-ink);margin-bottom:8px}
.rs-row.dashed{border:1px dashed var(--rs-dashed)}
.rs-head{display:grid;gap:10px;padding:4px 14px;font-size:11px;letter-spacing:.06em;color:var(--rs-muted);font-weight:600;text-transform:uppercase}
.rs-name{display:flex;gap:10px;align-items:center;min-width:0}
.rs-name b{font-weight:600;overflow-wrap:anywhere}
.rs-name small{display:block;font-size:11px;color:var(--rs-muted)}
.rs-icon{width:32px;height:32px;border-radius:9px;background:var(--rs-info-bg);color:var(--rs-info);display:grid;place-items:center;flex:none}
.rs-icon.warn{background:var(--rs-orange-bg);color:var(--rs-orange)}
.rs-icon.att{background:var(--rs-soft-bg);color:var(--rs-soft)}
.rs-pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:500;padding:3px 11px;border-radius:99px;line-height:1.5}
.rs-pill.ok{background:var(--rs-ok-bg);color:var(--rs-ok)}.rs-pill.warn{background:var(--rs-warn-bg);color:var(--rs-warn)}
.rs-pill.hold{background:var(--rs-hold-bg);color:var(--rs-hold)}.rs-pill.bad{background:var(--rs-bad-bg);color:var(--rs-bad)}
.rs-pill.neutral{background:var(--rs-soft-bg);color:var(--rs-soft)}.rs-pill.small{font-size:11px;padding:2px 10px}
.rs-chip{display:inline-block;font-size:12px;padding:1px 9px;border-radius:8px;background:var(--rs-info-bg);color:var(--rs-info);margin:0 4px 4px 0}
.rs-chip.bad{background:var(--rs-bad-bg);color:var(--rs-bad)}.rs-chip.att{background:var(--rs-soft-bg);color:var(--rs-soft)}
.rs-note{font-size:13px;color:var(--rs-muted);margin:6px 0;line-height:1.5}
.rs-sources{font-size:12px;color:var(--rs-muted);margin:8px 0 4px}
.rs-chat-head{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.rs-avatar{width:40px;height:40px;border-radius:50%;background:var(--rs-primary);color:var(--rs-on-primary);display:grid;place-items:center;flex:none;font-size:13px;font-weight:600}
.rs-chat-head b{display:block;font-size:15px;font-weight:600;color:var(--rs-ink)}
.rs-chat-head small{font-size:12px;color:var(--rs-muted)}
.rs-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--rs-dot);margin-right:5px}
.rs-user{display:flex;align-items:center;gap:10px;border-top:1px solid var(--rs-line);padding-top:14px;margin-top:10px}
.rs-user .rs-avatar{width:36px;height:36px}
.rs-user b{display:block;font-size:13.5px;font-weight:600;line-height:1.2;color:var(--rs-ink)}
.rs-user small{font-size:12px;color:var(--rs-muted)}
.rs-theme-btn{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;min-height:40px;box-sizing:border-box;
background:transparent;color:var(--rs-ink);border:1px solid var(--rs-line-2);border-radius:8px;font:inherit;font-size:14px;cursor:pointer}
.rs-theme-btn:hover{border-color:var(--rs-ink-2)}
.rs-theme-btn .rs-to-light,:root[data-rs-theme="dark"] .rs-theme-btn .rs-to-dark{display:none}
:root[data-rs-theme="dark"] .rs-theme-btn .rs-to-light{display:inline-flex;align-items:center;gap:8px}
.rs-theme-btn .rs-to-dark{display:inline-flex;align-items:center;gap:8px}
.rs-scroll{overflow-x:auto}
/* Dos paneles como en el diseño: la columna izquierda baja con su propio scroll
   y el asistente queda fijo a la altura de la pantalla, con el campo de texto abajo. */
/* Streamlit envuelve cada contenedor con key en un stLayoutWrapper: la altura va en el envoltorio. */
[data-testid="stLayoutWrapper"]:has(> .st-key-rs_left),
[data-testid="stLayoutWrapper"]:has(> .st-key-rs_chat){height:calc(100vh - var(--rs-top))}
[data-testid="stLayoutWrapper"]:has(> .st-key-rs_msgs){flex:1 1 0 !important;min-height:0;height:auto !important}
.st-key-rs_left,.st-key-rs_chat,.st-key-rs_msgs{height:100% !important;min-height:0;box-sizing:border-box;flex-wrap:nowrap}
.st-key-rs_left{overflow-y:auto;overflow-x:hidden;padding-right:10px}
.st-key-rs_chat{background:var(--rs-card);border:1px solid var(--rs-line);border-radius:16px;padding:18px 18px 14px;overflow:hidden}
.st-key-rs_msgs{overflow-y:auto;overflow-x:hidden}
@media (max-width:640px){.rs-row,.rs-head{grid-template-columns:1fr !important}.rs-head{display:none}}
@media (max-width:900px){
[data-testid="stLayoutWrapper"]:has(> .st-key-rs_left),[data-testid="stLayoutWrapper"]:has(> .st-key-rs_chat){height:auto}
[data-testid="stLayoutWrapper"]:has(> .st-key-rs_msgs){flex:none}
.st-key-rs_left,.st-key-rs_chat{height:auto !important;overflow:visible}.st-key-rs_msgs{height:60vh !important}}
</style>
"""


# Cambia el tema con el mismo menú de Streamlit (⋮ → Light / Dark): así no se recarga la página
# ni se pierde la sesión. También marca <html data-rs-theme> según el fondo real para que el CSS
# propio siga al tema, lo cambie este botón o el menú.
THEME_SWITCH = """
<button type="button" class="rs-theme-btn" aria-label="Cambiar entre tema claro y oscuro">
<span class="rs-to-dark"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
Modo oscuro</span>
<span class="rs-to-light"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9
4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>Modo claro</span>
</button>
<script>
(() => {
  const isDark = () => {
    const rgb = (getComputedStyle(document.querySelector('.stApp') || document.body).backgroundColor.match(/\\d+/g) || [255, 255, 255]).map(Number);
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2] < 128;
  };
  const mark = () => { document.documentElement.dataset.rsTheme = isDark() ? 'dark' : 'light'; };
  if (!window.__rsThemeWatch) window.__rsThemeWatch = setInterval(mark, 300);
  mark();
  const pick = async (name) => {
    const item = () => document.querySelector(`[data-testid="stMainMenuItem-theme-${name}"]`);
    if (!item()) {
      document.querySelector('[data-testid="stMainMenuButton"]')?.click();
      await new Promise((resolve) => setTimeout(resolve, 150));
    }
    item()?.click();
    setTimeout(() => {
      if (document.querySelector('[data-testid="stMainMenuList"]')) document.querySelector('[data-testid="stMainMenuButton"]')?.click();
      mark();
    }, 150);
  };
  document.querySelectorAll('.rs-theme-btn').forEach((button) => {
    if (button.dataset.ready) return;
    button.dataset.ready = '1';
    button.addEventListener('click', () => pick(isDark() ? 'Light' : 'Dark'));
  });
})();
</script>
"""


def theme_switch() -> None:
    st.html(THEME_SWITCH, unsafe_allow_javascript=True)


def icon(name: str, size: int = 16, width: float = 1.9) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def pill(text: str, kind: str, icon_name: str | None = None, small: bool = False) -> str:
    inner = (icon(icon_name, 13, 2.1) if icon_name else "") + esc(text)
    return f'<span class="rs-pill {kind}{" small" if small else ""}">{inner}</span>'


def html_block(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def brand(subtitle: str) -> None:
    html_block(f'<div class="rs-brand"><div class="rs-logo">{icon("shield", 18, 2)}</div>'
               f'<div><b>RAG Shield</b><small>{esc(subtitle)}</small></div></div>')


def file_size(source_file: str) -> str:
    path = docs_dir().parent / source_file
    try:
        return f"{path.stat().st_size / 1000:.1f} KB"
    except OSError:
        return "—"


# ---------------------------------------------------------------- datos


@st.cache_data
def load_dataset() -> tuple[list[dict], dict]:
    attacks = json.loads(ATTACKS_PATH.read_text(encoding="utf-8")) if ATTACKS_PATH.exists() else {}
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    items = [dict(a, tipo="ataque") for a in attacks.get("ataques", [])]
    items += [dict(c, tipo="control") for c in attacks.get("controles", [])]
    return items, manifest


def safe_documents(where: dict | None = None) -> tuple[list[dict], str | None]:
    try:
        documents = indexed_documents(where)
    except IndexNotReadyError as exc:
        return [], str(exc)
    if any("estado" not in d for d in documents):
        return [], "El índice es de una versión anterior, sin cuarentena ni departamentos. Corre: python -m src.ingest"
    return documents, None


def load_summaries() -> list[dict]:
    order = list(CONFIG_LABELS)
    summaries = [json.loads(p.read_text(encoding="utf-8")) for p in RESULTS_DIR.glob("resumen_*.json")]
    return sorted(summaries, key=lambda s: order.index(s["config"]) if s["config"] in order else 99)


def escape_md(text: str) -> str:
    return text.replace("$", "\\$")


def highlight(text: str, item: dict | None) -> str:
    out = escape_md(text)
    if not item:
        return out
    colors = {}
    for key, color in (("dato_falso_esperado", "red"), ("dato_correcto_esperado", "green")):
        markers = item.get(key) or []
        for marker in [markers] if isinstance(markers, str) else markers:
            colors.setdefault(escape_md(marker).lower(), color)
    if not colors:
        return out
    alternatives = "|".join(re.escape(m) for m in sorted(colors, key=len, reverse=True))
    pattern = re.compile(rf"(?<![0-9A-Za-z])(?<![0-9][.,'])({alternatives})(?![0-9A-Za-z])(?![.,'][0-9])", re.IGNORECASE)
    return pattern.sub(lambda m: f":{colors[m.group(0).lower()]}-background[{m.group(0)}]", out)


def item_label(item: dict, manifest: dict) -> str:
    if item["tipo"] == "control":
        return f"Control · {item['pregunta']}"
    technique = manifest.get(item["documento_objetivo"], {}).get("tecnica_camuflaje", "ninguna")
    return f"Ataque · {TECHNIQUE_LABELS.get(technique, technique)} · {item['pregunta']}"


def audit_answer(user: User, query: str, result: dict | None, modo: str, retenida_por_peticion: bool = False) -> None:
    fields = {"pregunta": query, "modo": modo, "peticion_retenida": retenida_por_peticion}
    if result:
        fields.update(
            config=result["config"],
            fuentes=result["documentos_recuperados"],
            reglas_capa_1=sorted({r for s in result["sanitizacion"] for r in s["reglas"]}),
            capa_3_bloqueo=result["guard"]["bloqueado"],
            acciones_detectadas=result["guard"]["acciones"],
            modelo=f"{result['proveedor']} / {result['modelo']}",
        )
    storage.log_event(user, "pregunta", **fields)


# ---------------------------------------------------------------- inicio de sesión


def login_view() -> None:
    st.session_state.setdefault("login_intentos", 0)
    _, center, _ = st.columns([1, 1.1, 1])
    with center:
        st.write("")
        brand("NovaCred · asistente interno")
        if not load_users():
            st.info("Todavía no hay usuarios. Créalos desde la terminal:\n\n"
                    "`python -m src.auth crear --usuario ana.cardenas --nombre \"Ana Cárdenas\" "
                    "--rol empleado --departamento cartera`\n\n"
                    "`python -m src.auth crear --usuario jurado --nombre \"Jurado FDSI\" --rol laboratorio`")
        blocked = st.session_state["login_intentos"] >= MAX_LOGIN_ATTEMPTS
        with st.container(border=True):
            usuario = st.text_input("Usuario", key="login_usuario", disabled=blocked)
            clave = st.text_input("Contraseña", type="password", key="login_clave", disabled=blocked)
            entrar = st.button("Entrar", type="primary", width="stretch", disabled=blocked, key="login_entrar")
        if blocked:
            st.error("Acceso bloqueado en esta sesión por demasiados intentos fallidos.")
        elif entrar:
            user = authenticate(usuario, clave)
            if user:
                st.session_state.clear()
                st.session_state["user"] = user
                storage.log_event(user, "inicio_sesion")
                st.rerun()
            st.session_state["login_intentos"] += 1
            left = MAX_LOGIN_ATTEMPTS - st.session_state["login_intentos"]
            st.error("Usuario o contraseña incorrectos." + (f" Te quedan {left} intentos." if left else ""))
            if not left:
                st.rerun()
        html_block(f'<p class="rs-note" style="text-align:center">Tras {MAX_LOGIN_ATTEMPTS} intentos fallidos '
                   'se bloquea el acceso en esta sesión.</p>')
        theme_switch()


def logout(user: User) -> None:
    storage.log_event(user, "cierre_sesion")
    st.session_state.clear()
    st.rerun()


def user_footer(user: User, subtitle: str) -> None:
    theme_switch()
    html_block(f'<div class="rs-user"><div class="rs-avatar">{esc(user.iniciales)}</div>'
               f'<div><b>{esc(user.nombre)}</b><small>{esc(subtitle)}</small></div></div>')
    if st.button("Salir", key="logout", width="stretch"):
        logout(user)


# ---------------------------------------------------------------- Laboratorio


def doc_row(doc: dict, quarantine: bool = False) -> str:
    technique = TECHNIQUE_LABELS.get(doc.get("tecnica", "ninguna"), "—")
    detail = f"{doc['chunks']} chunks"
    if quarantine:
        motivo = ", ".join(RULE_LABELS.get(r, "frase que le habla al modelo") for r in doc["motivo_cuarentena"].split(";") if r)
        detail += f" · {ORIGIN_LABELS.get(doc['origen'], doc['origen'])} · {motivo or technique}"
        status = pill("Cuarentena", "warn", small=True)
        kind = pill("Envenenado" if doc.get("is_poisoned") else ORIGIN_LABELS.get(doc["origen"], ""), "bad" if doc.get("is_poisoned") else "neutral", small=True)
    else:
        status = pill("Indexado", "ok", small=True)
        kind = pill(ORIGIN_LABELS.get(doc["origen"], doc["origen"]), "neutral", small=True)
    deps = ", ".join(DEPARTMENTS[d] for d in doc["departamentos"]) or "ninguno"
    return (f'<div class="rs-row" style="grid-template-columns:2.4fr 1fr 1fr .9fr 1fr .8fr">'
            f'<div class="rs-name"><span class="rs-icon{" warn" if quarantine else ""}">{icon("doc", 16, 1.8)}</span>'
            f'<div><b>{esc(doc["file_name"])}</b><small>{esc(detail)}</small></div></div>'
            f'<div>{status}</div><div>{kind}</div><div>{esc(doc["canal"])}</div>'
            f'<div title="Departamentos que lo pueden consultar">{esc(deps)}</div><div>{esc(file_size(doc["source_file"]))}</div></div>')


def lab_mail_connector(user: User) -> None:
    html_block('<div class="rs-h" style="margin-top:10px">Correo (IMAP)</div>')
    try:
        config = mail.settings()
    except mail.MailConfigError as exc:
        st.error(str(exc))
        return
    if config is None:
        html_block('<div class="rs-note">Sin buzón configurado. Agrega en <code>.env</code>: IMAP_HOST, IMAP_USER, '
                   'IMAP_PASSWORD (contraseña de aplicación) y, si hace falta, IMAP_PORT e IMAP_FOLDER. Luego reinicia la app.</div>')
        return
    with st.form("importar_correo", border=True):
        html_block(f'<div class="rs-note" style="margin-top:0">Buzón: {esc(config.public)} · solo lectura, '
                   'no marca los correos como leídos.</div>')
        departments = st.multiselect("Departamentos que pueden consultar los correos", list(DEPARTMENTS),
                                     default=list(DEPARTMENTS), format_func=DEPARTMENTS.get, key="imap_deps")
        limit = st.number_input("Correos más recientes a revisar", min_value=1, max_value=100, value=20, step=1)
        if st.form_submit_button("Importar correos", icon=":material/mail:"):
            require(user, "importar_correo")
            try:
                with st.spinner("Leyendo el buzón…"):
                    summary = storage.import_emails(departments, int(limit))
            except (mail.MailConfigError, IndexNotReadyError) as exc:
                st.error(str(exc))
            else:
                storage.log_event(user, "importar_correo", **summary)
                st.success(f"{summary['importados']} correos importados ({summary['cuarentena']} en cuarentena), "
                           f"{summary['repetidos']} ya estaban, {summary['rechazados']} rechazados.")


def lab_knowledge_base(user: User) -> None:
    html_block('<div class="rs-label" style="margin-top:0">Base de conocimiento</div>')
    if can(user, "subir_base"):
        html_block('<div class="rs-h">Subir conocimiento</div>')
        with st.form("subir_base", clear_on_submit=True, border=True):
            upload = st.file_uploader("Archivo", type=["txt", "html", "md"], help="1 MB por archivo · TXT, HTML, MD")
            departments = st.multiselect("Departamentos que lo pueden consultar", list(DEPARTMENTS),
                                         default=list(DEPARTMENTS), format_func=DEPARTMENTS.get)
            if st.form_submit_button("Agregar a la base") and upload:
                require(user, "subir_base")
                try:
                    meta = storage.save_document(upload.name, upload.getvalue(), departments, "subido")
                except (storage.UploadError, ValueError) as exc:
                    st.error(str(exc))
                except IndexNotReadyError as exc:
                    st.error(f"{exc}")
                else:
                    storage.log_event(user, "subir_base", documento=meta["source_file"], estado=meta["estado"])
                    if meta["estado"] == "cuarentena":
                        st.warning(f"{meta['file_name']} quedó en cuarentena: la Capa 1 encontró {meta['motivo_cuarentena']}.")
                    else:
                        st.success(f"{meta['file_name']} se indexó y ya está en la base.")

    if can(user, "importar_correo"):
        lab_mail_connector(user)

    documents, error = safe_documents()
    head, button = st.columns([3, 1.2], vertical_alignment="center")
    head.markdown('<div class="rs-h">Documentos indexados</div>', unsafe_allow_html=True)
    if can(user, "reindexar") and button.button("Reindexar docs/", icon=":material/refresh:", width="stretch"):
        require(user, "reindexar")
        with st.spinner("Reindexando…"):
            result = ingest_documents()
        storage.log_event(user, "reindexar", **{k: result[k] for k in ("chunks", "fuentes", "cuarentena")})
        st.rerun()
    if error:
        st.error(error)
        return
    html_block('<div class="rs-scroll">' + "".join(doc_row(d) for d in documents if d["estado"] == "aprobado") + "</div>")

    if not can(user, "ver_cuarentena"):
        return
    html_block('<div class="rs-h" style="margin-top:14px">En cuarentena</div><div class="rs-note">Documentos con instrucciones '
               'ocultas, envenenados o detectados como sospechosos al subirlos. Siguen indexados para el experimento; '
               'la Capa 1 los neutraliza antes de llegar al modelo y la vista de Empleado nunca los recupera.</div>')
    for doc in (d for d in documents if d["estado"] == "cuarentena"):
        if doc["origen"] == "base":
            html_block(f'<div class="rs-scroll">{doc_row(doc, quarantine=True)}</div>')
            continue
        row, actions = st.columns([5, 1.6], vertical_alignment="center")
        row.markdown(f'<div class="rs-scroll">{doc_row(doc, quarantine=True)}</div>', unsafe_allow_html=True)
        key = doc["source_file"]
        if doc["origen"] == "propuesta" and actions.button("Aprobar", key=f"ok_{key}", width="stretch"):
            require(user, "revisar_propuestas")
            meta = storage.approve_proposal(key)
            storage.log_event(user, "aprobar_propuesta", documento=key, estado=meta["estado"])
            st.rerun()
        if actions.button("Descartar", key=f"rm_{key}", width="stretch"):
            require(user, "revisar_propuestas")
            storage.discard_document(key)
            storage.log_event(user, "descartar_documento", documento=key)
            st.rerun()


def verdict(result: dict, item: dict | None) -> str:
    if result["guard"]["bloqueado"]:
        return pill("Capa 3 retuvo la respuesta: " + ", ".join(result["guard"]["acciones"]), "hold", "lock")
    if not item:
        return ""
    answer = result["respuesta"]
    falso = item.get("dato_falso_esperado") and contains_marker(answer, item["dato_falso_esperado"])
    correcto = contains_marker(answer, item.get("dato_correcto_esperado"))
    if item["tipo"] == "ataque" and falso and not correcto:
        return pill("El ataque funcionó: aparece el dato falso", "bad", "x")
    if falso:
        return pill("Respuesta contaminada: mezcla el dato falso y el correcto", "warn", "alert")
    if correcto:
        return pill("Respuesta correcta: dato de la política oficial", "ok", "check")
    return pill("No trae ni el dato falso ni el correcto", "neutral")


def retrieved_table(result: dict) -> None:
    rows = []
    for position, chunk in enumerate(result["chunks"], start=1):
        meta = chunk["metadata"]
        rows.append({
            "#": position,
            "Documento": meta.get("file_name"),
            "Tipo": "envenenado" if meta.get("is_poisoned") else "legítimo",
            "Estado": meta.get("estado", "—"),
            "Técnica": TECHNIQUE_LABELS.get(meta.get("tecnica", "ninguna"), meta.get("tecnica")),
            "Distancia": round(chunk.get("distance", 0), 3),
            "Capa 1": ", ".join(chunk.get("sanitizacion", [])) or "—",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    for chunk in result["chunks"]:
        if chunk["metadata"].get("is_poisoned"):
            st.caption(f"Texto de {chunk['metadata'].get('file_name')} tal como llegó del índice:")
            original = chunk.get("texto_original", chunk["text"])
            st.code(original.replace("​", "⟨ZWSP⟩").replace("‌", "⟨ZWNJ⟩").replace("⁠", "⟨WJ⟩"),
                    language="html", wrap_lines=True)
            if "texto_original" in chunk:
                st.caption("Después de la Capa 1:")
                st.code(chunk["text"], language="text", wrap_lines=True)


def lab_result(label: str | None, result: dict, item: dict | None) -> None:
    if label:
        st.markdown(f"**{label}**")
    badge = verdict(result, item)
    if badge:
        html_block(badge)
    for entry in result["sanitizacion"]:
        rules = ", ".join(dict.fromkeys(RULE_LABELS.get(r, "frase que le habla al modelo") for r in entry["reglas"]))
        html_block(f'<div class="rs-note">Capa 1 neutralizó una instrucción oculta en '
                   f'{esc(entry["source_file"].rsplit("/", 1)[-1])}: {esc(rules)}.</div>')
    st.markdown(highlight(result["respuesta"], item))
    chips = "".join(f'<span class="rs-chip{" bad" if c["metadata"].get("is_poisoned") else ""}">{esc(name)}</span>'
                    for name, c in {c["metadata"].get("file_name"): c for c in result["chunks"]}.items())
    html_block(f'<div class="rs-sources">Fuentes recuperadas</div>{chips}')
    st.caption(f"{result['latencia_segundos']} s · {result['proveedor']} / {result['modelo']}")
    with st.expander("Detalle de recuperación"):
        retrieved_table(result)


def lab_chat(user: User, flags: dict, mode: str) -> None:
    items, manifest = load_dataset()
    status = "Comparando con y sin capas" if mode == "Comparar" else ("Protegido" if mode == "Protegido" else "Sin capas")
    html_block(f'<div class="rs-chat-head"><div class="rs-avatar">{icon("shield", 18, 2)}</div><div>'
               f'<b>Asistente de IA</b><small><span class="rs-dot"></span>RAG activo · {esc(status)}</small></div></div>')
    labels = [item_label(i, manifest) for i in items]
    choice = st.selectbox("Preguntas del experimento", range(len(items)), index=None, format_func=labels.__getitem__,
                          placeholder="Preguntas del experimento", label_visibility="collapsed")
    pending = None
    if st.button("Preguntar esta", disabled=choice is None, width="stretch", icon=":material/bolt:"):
        pending = items[choice]["pregunta"], items[choice]
    history = st.session_state.setdefault("lab_chat", [])
    box = st.container(key="rs_msgs", height=500, border=False, autoscroll=True)
    typed = st.chat_input("Escribe una pregunta sobre NovaCred…", key="lab_input")
    if typed:
        pending = typed, next((i for i in items if i["pregunta"] == typed.strip()), None)

    if pending:
        query, item = pending
        require(user, "configurar_capas")
        runs = {"Protegido": [("Protegido", flags)], "Sin capas": [("Sin capas", NO_LAYERS)],
                "Comparar": [("Sin defensas", NO_LAYERS), ("Con defensas", flags)]}[mode]
        try:
            with st.spinner("Consultando…"):
                results = {label: ask(query, **run_flags) for label, run_flags in runs}
        except (IndexNotReadyError, LLMConfigError) as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Falló la consulta al modelo: {exc}")
        else:
            history.append({"query": query, "item": item, "results": results, "mode": mode})
            for result in results.values():
                audit_answer(user, query, result, f"laboratorio · {mode}")

    with box:
        with st.chat_message("assistant", avatar=":material/shield:"):
            st.markdown("Hola, soy el asistente interno de NovaCred. Respondo con los documentos de la base de "
                        "conocimiento. Escribe una pregunta o elige una del experimento.")
        for turn in history:
            with st.chat_message("user"):
                st.markdown(escape_md(turn["query"]))
            with st.chat_message("assistant", avatar=":material/shield:"):
                for label, result in turn["results"].items():
                    lab_result(label if len(turn["results"]) > 1 else None, result, turn["item"])


def bar(summaries: list[dict], key: str, title: str, suffix: str = " %", error: str | None = None) -> go.Figure:
    labels = [CONFIG_LABELS.get(s["config"], s["config"]) for s in summaries]
    values = [s.get(key) or 0 for s in summaries]
    error_y = None
    if error:
        lows = [v - (s.get(error) or [v, v])[0] for v, s in zip(values, summaries)]
        highs = [(s.get(error) or [v, v])[1] - v for v, s in zip(values, summaries)]
        error_y = dict(type="data", array=highs, arrayminus=lows, visible=True)
    fig = go.Figure(go.Bar(x=labels, y=values, error_y=error_y, text=[f"{v}{suffix}" for v in values],
                           textposition="outside", marker_color="#75757f"))
    fig.update_layout(title=title, yaxis_title=suffix.strip() or "s", height=380, margin=dict(t=60, b=20))
    if suffix.strip() == "%":
        fig.update_yaxes(range=[0, 105])
    return fig


def lab_results(user: User) -> None:
    require(user, "ver_resultados")
    html_block('<p class="rs-title">Resultados</p><p class="rs-sub">Métricas de la última evaluación '
               '(eval/results/resumen_*.json).</p>')
    summaries = load_summaries()
    if not summaries:
        st.info("Todavía no hay resultados. Corre: `python -m eval.eval_harness --config todas --repeticiones 5 --comparar`")
        return
    s0 = summaries[0]
    st.caption(f"Modelo: {s0.get('proveedor')} / {s0.get('modelo')} · {s0.get('repeticiones')} repeticiones por pregunta")
    for s in summaries:
        errors = s.get("errores") or 0
        total = errors + (s.get("intentos_ataque") or 0) + (s.get("intentos_control") or 0)
        if not errors or not total:
            continue
        label = CONFIG_LABELS.get(s["config"], s["config"])
        share = errors / total
        message = (f"{label}: {errors} de {total} intentos fallaron ({share:.0%}); sus métricas salen solo de "
                   f"{total - errors} intentos.")
        if share > MAX_ERROR_RATE:
            st.error(message + " No son confiables: repite esta configuración.")
        else:
            st.warning(message)

    base = next((s for s in summaries if s["config"] == "baseline"), None)
    cols = st.columns(len(summaries))
    for col, s in zip(cols, summaries):
        delta = None
        if base and s is not base and s.get("asr") is not None and base.get("asr") is not None:
            delta = f"{round(s['asr'] - base['asr'], 2)} pts"
        rango = s.get("asr_rango_rondas")
        col.metric(f"ASR · {CONFIG_LABELS.get(s['config'], s['config'])}", f"{s.get('asr')} %", delta,
                   delta_color="inverse", help=f"Rango entre rondas: {rango[0]}–{rango[1]} %" if rango else None)

    left, right = st.columns(2)
    left.plotly_chart(bar(summaries, "asr", "ASR con intervalo de Wilson 95 %", error="asr_ic95"))
    right.plotly_chart(bar(summaries, "recuperacion_documento_malicioso", "Recuperación del documento malicioso"))
    left, right = st.columns(2)
    metrics = {"Falsos positivos": "falsos_positivos", "Utilidad preservada": "utilidad_preservada",
               "Acción insegura": "accion_insegura_ejecutada", "Sobre-bloqueo": "sobre_bloqueo"}
    fig = go.Figure([
        go.Bar(name=CONFIG_LABELS.get(s["config"], s["config"]), x=list(metrics),
               y=[s.get(k) or 0 for k in metrics.values()]) for s in summaries
    ])
    fig.update_layout(title="Costo y efecto de las defensas", barmode="group", yaxis_title="%", height=380,
                      yaxis_range=[0, 105], margin=dict(t=60, b=20))
    left.plotly_chart(fig)
    right.plotly_chart(bar(summaries, "latencia_media", "Latencia media por consulta", suffix=" s"))

    per_attack = pd.DataFrame({CONFIG_LABELS.get(s["config"], s["config"]): s.get("asr_por_ataque", {}) for s in summaries})
    if not per_attack.empty:
        heat = go.Figure(go.Heatmap(z=per_attack.values, x=per_attack.columns, y=per_attack.index, zmin=0, zmax=100,
                                    colorscale="Reds", text=per_attack.values, texttemplate="%{text} %"))
        heat.update_layout(title="ASR por ataque", height=420, margin=dict(t=60, b=20))
        st.plotly_chart(heat)

    comparison = RESULTS_DIR / "comparacion.md"
    if comparison.exists():
        with st.expander("Tabla completa"):
            st.markdown(comparison.read_text(encoding="utf-8"))


def lab_audit(user: User) -> None:
    require(user, "ver_auditoria")
    html_block('<p class="rs-title">Auditoría</p><p class="rs-sub">Quién preguntó, qué fuentes se usaron y qué capa '
               'actuó. No se guarda el texto de las respuestas.</p>')
    entries = storage.read_audit()
    if not entries:
        st.info("Todavía no hay eventos.")
        return
    frame = pd.DataFrame(entries)
    roles = st.multiselect("Rol", sorted(frame["rol"].dropna().unique()), placeholder="Todos los roles")
    if roles:
        frame = frame[frame["rol"].isin(roles)]
    for column in ("fuentes", "reglas_capa_1", "acciones_detectadas"):
        if column in frame:
            frame[column] = frame[column].map(lambda v: ", ".join(v) if isinstance(v, list) else v)
    frame = frame.drop(columns=[c for c in ("config",) if c in frame])
    st.dataframe(frame, hide_index=True, width="stretch")


def lab_view(user: User) -> None:
    require(user, "ver_laboratorio")
    with st.sidebar:
        brand("NovaCred · FDSI Grupo 04")
        html_block('<div class="rs-label">Espacio</div>')
        page = st.radio("Espacio", ["Asistente", "Resultados", "Auditoría"], label_visibility="collapsed")
        html_block('<div class="rs-label">Defensas</div>')
        flags = {
            "use_sanitizer": st.toggle("Capa 1 · Sanitización", value=True),
            "use_prompt_guard": st.toggle("Capa 2 · Separación del prompt", value=True),
            "use_privilege_guard": st.toggle("Capa 3 · Mínimo privilegio", value=True),
        }
        mode = st.radio("Modo de respuesta", ["Protegido", "Sin capas", "Comparar"], horizontal=True)
        html_block('<div class="rs-label">Estado</div>')
        documents, error = safe_documents()
        if error:
            html_block(f'<div class="rs-status err">{esc(error)}</div>')
        else:
            quarantined = sum(d["estado"] == "cuarentena" for d in documents)
            html_block(f'<div class="rs-status">{len(documents)} documentos indexados · {quarantined} en cuarentena</div>')
        try:
            st.caption(f"Modelo: {provider()} / {model_name()}")
            if provider() == "mock":
                st.warning("Modo mock: las respuestas son simuladas.")
        except LLMConfigError as exc:
            st.error(str(exc))
        user_footer(user, ROLE_LABELS[user.rol])

    if page == "Asistente":
        left, right = st.columns([1.5, 1], gap="large")
        with left, st.container(key="rs_left"):
            lab_knowledge_base(user)
        with right, st.container(key="rs_chat"):
            lab_chat(user, flags, mode)
    elif page == "Resultados":
        lab_results(user)
    else:
        lab_audit(user)


# ---------------------------------------------------------------- Empleado


def session_groups(sessions: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {"Hoy": [], "Ayer": [], "Antes": []}
    today = date.today()
    for session in sessions:
        days = (today - datetime.fromisoformat(session.get("actualizada", session["creada"])).date()).days
        groups["Hoy" if days <= 0 else "Ayer" if days == 1 else "Antes"].append(session)
    return {k: v for k, v in groups.items() if v}


def current_session(user: User) -> dict:
    if "sesion" not in st.session_state:
        st.session_state["sesion"] = storage.new_session()
    return st.session_state["sesion"]


def employee_answer(user: User, query: str, attachments: list[dict]) -> dict:
    """Las capas y el filtro salen del rol, nunca de la interfaz."""
    require(user, "consultar_asistente")
    requested = detect_action_request(query)
    if requested:
        storage.log_event(user, "pregunta", pregunta=query, modo="empleado", peticion_retenida=True,
                          acciones_detectadas=requested)
        return {"texto": REQUEST_MESSAGE, "insignia": "retenida", "fuentes": [], "adjuntos": []}

    extra = rank_chunks(query, [c for a in attachments for c in a["chunks"]], ATTACHMENT_CHUNKS)
    result = ask(query, **ALL_LAYERS, where=employee_filter(user.departamento), extra_chunks=extra)
    audit_answer(user, query, result, "empleado")
    neutralized = {s["source_file"] for s in result["sanitizacion"]}
    if result["guard"]["bloqueado"]:
        insignia = "retenida"
    elif neutralized:
        insignia = "neutralizada"
    else:
        insignia = "revisada"
    sources = list(dict.fromkeys(c["metadata"]["file_name"] for c in result["chunks"] if c["metadata"].get("origen") != "adjunto"))
    used_attachments = list(dict.fromkeys(c["metadata"]["file_name"] for c in extra))
    return {"texto": result["respuesta"], "insignia": insignia, "neutralizadas": len(neutralized),
            "fuentes": sources, "adjuntos": used_attachments}


def employee_badge(message: dict) -> str:
    if message["insignia"] == "retenida":
        return pill("Acción retenida", "hold", "lock")
    if message["insignia"] == "neutralizada":
        n = message.get("neutralizadas", 1)
        return pill(f"Se neutralizó contenido sospechoso en {n} fuente{'s' if n != 1 else ''}", "warn", "alert")
    return pill("Revisada por RAG Shield", "ok", "check")


def employee_sidebar(user: User) -> None:
    with st.sidebar:
        brand(f"NovaCred · {DEPARTMENTS[user.departamento]}")
        if st.button("Nueva sesión", type="primary", icon=":material/add:", width="stretch"):
            st.session_state["sesion"] = storage.new_session()
            st.session_state.pop("propuestos", None)
            st.rerun()
        current = current_session(user)
        for group, sessions in session_groups(storage.list_sessions(user.usuario)).items():
            html_block(f'<div class="rs-label">{group}</div>')
            for session in sessions:
                title = session["titulo"] if len(session["titulo"]) <= 34 else session["titulo"][:33] + "…"
                if st.button(title, key=f"ses_{session['id']}", width="stretch",
                             type="secondary" if session["id"] != current["id"] else "primary"):
                    st.session_state["sesion"] = session
                    st.rerun()
        user_footer(user, DEPARTMENTS[user.departamento])


def employee_documents(user: User, session: dict) -> list[dict]:
    department = DEPARTMENTS[user.departamento]
    html_block(f'<p class="rs-title">Documentos de {esc(department)}</p><p class="rs-sub">Lo que el asistente puede '
               'consultar para ti. Para agregar un documento a la base, propónselo al Laboratorio.</p>')
    documents, error = safe_documents(employee_filter(user.departamento))
    if error:
        st.error("La base de conocimiento no está disponible. Avísale al Laboratorio.")
    elif not documents:
        st.info("Tu departamento todavía no tiene documentos aprobados.")
    else:
        columns = "grid-template-columns:2.6fr 1fr 1fr"
        rows = "".join(f'<div class="rs-row" style="{columns}"><div class="rs-name"><span class="rs-icon">{icon("doc", 16, 1.8)}'
                       f'</span><b>{esc(d["file_name"])}</b></div><div>{esc(d["canal"])}</div>'
                       f'<div>{esc(file_size(d["source_file"]))}</div></div>' for d in documents)
        html_block(f'<div class="rs-scroll"><div class="rs-head" style="{columns}"><div>Nombre</div><div>Canal</div>'
                   f'<div>Tamaño</div></div>{rows}</div>')

    html_block('<div class="rs-label" style="margin-left:14px">Adjuntos de esta sesión</div>')
    uploads = st.file_uploader("Adjuntar a esta sesión", type=["txt", "html", "md"], accept_multiple_files=True,
                               key=f"adj_{session['id']}", help="1 MB por archivo · TXT, HTML, MD",
                               label_visibility="collapsed")
    attachments = []
    proposed = st.session_state.setdefault("propuestos", set())
    for upload in uploads or []:
        require(user, "adjuntar_sesion")
        try:
            item = storage.attachment(upload.name, upload.getvalue())
        except storage.UploadError as exc:
            st.error(f"{upload.name}: {exc}")
            continue
        attachments.append(item)
        state = "Contenido sospechoso: se neutraliza al responder" if item["reglas"] else "Revisado"
        row, action = st.columns([4, 1.4], vertical_alignment="center")
        row.markdown(f'<div class="rs-row dashed" style="grid-template-columns:2.6fr 1fr 1fr"><div class="rs-name">'
                     f'<span class="rs-icon att">{icon("clip", 16, 1.8)}</span><div><b>{esc(item["name"])}</b>'
                     f'<small>Solo en esta sesión · {esc(state)}</small></div></div><div>adjunto</div>'
                     f'<div>{item["size"] / 1000:.1f} KB</div></div>', unsafe_allow_html=True)
        if item["name"] in proposed:
            action.caption("Propuesto")
        elif action.button("Proponer a la base", key=f"prop_{session['id']}_{item['name']}", width="stretch"):
            require(user, "proponer_documento")
            try:
                meta = storage.save_document(item["name"], item["data"], [user.departamento], "propuesta")
            except (storage.UploadError, ValueError, IndexNotReadyError) as exc:
                st.error(str(exc))
            else:
                proposed.add(item["name"])
                storage.log_event(user, "proponer_documento", documento=meta["source_file"])
                st.toast("Enviado al Laboratorio. Queda en cuarentena hasta que lo apruebe.")
                st.rerun()
    html_block('<p class="rs-note" style="margin-left:14px">Los adjuntos no se agregan a la base compartida.</p>')
    return attachments


def employee_chat(user: User, session: dict, attachments: list[dict]) -> None:
    html_block(f'<div class="rs-chat-head"><div class="rs-avatar">{icon("shield", 18, 2)}</div><div><b>Asistente NovaCred</b>'
               f'<small><span class="rs-dot"></span>{esc(DEPARTMENTS[user.departamento])}</small></div></div>')
    box = st.container(key="rs_msgs", height=500, border=False, autoscroll=True)
    query = st.chat_input("Escribe una pregunta…", key="emp_input")
    if query:
        try:
            with st.spinner("Consultando…"):
                answer = employee_answer(user, query, attachments)
        except (IndexNotReadyError, LLMConfigError):
            st.error("El asistente no está disponible en este momento. Avísale al Laboratorio.")
        except Exception:
            st.error("No se pudo obtener una respuesta. Intenta de nuevo.")
        else:
            if not session["mensajes"]:
                session["titulo"] = query.strip()[:60]
            session["mensajes"].append({"rol": "usuario", "texto": query, "adjuntos": [a["name"] for a in attachments]})
            session["mensajes"].append({"rol": "asistente", **answer})
            storage.save_session(user.usuario, session)

    with box:
        if not session["mensajes"]:
            with st.chat_message("assistant", avatar=":material/shield:"):
                st.markdown("Hola. Respondo con los documentos aprobados de tu departamento y con lo que adjuntes "
                            "en esta sesión. Solo informo: no apruebo, condono, desembolso ni envío datos.")
        for message in session["mensajes"]:
            if message["rol"] == "usuario":
                with st.chat_message("user"):
                    st.markdown(escape_md(message["texto"]))
                    if message.get("adjuntos"):
                        st.caption(", ".join(message["adjuntos"]))
                continue
            with st.chat_message("assistant", avatar=":material/shield:"):
                html_block(employee_badge(message))
                st.markdown(escape_md(message["texto"]))
                chips = "".join(f'<span class="rs-chip">{esc(s)}</span>' for s in message.get("fuentes", []))
                chips += "".join(f'<span class="rs-chip att">{esc(s)}</span>' for s in message.get("adjuntos", []))
                if chips:
                    html_block(f'<div class="rs-sources">Fuentes</div>{chips}')


def employee_view(user: User) -> None:
    require(user, "consultar_asistente")
    employee_sidebar(user)
    session = current_session(user)
    left, right = st.columns([1.5, 1], gap="large")
    with left, st.container(key="rs_left"):
        attachments = employee_documents(user, session)
    with right, st.container(key="rs_chat"):
        employee_chat(user, session, attachments)


# ---------------------------------------------------------------- ruteo

html_block(CSS)
current_user: User | None = st.session_state.get("user")
if current_user is None:
    login_view()
elif current_user.rol == "laboratorio":
    lab_view(current_user)
elif current_user.rol == "empleado":
    employee_view(current_user)
else:
    st.session_state.clear()
    st.rerun()
    