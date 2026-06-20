"""Score portal Flask application."""

import json
import os
import secrets
import signal
import subprocess
import sys
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode

from flask import (
    Flask,
    Response,
    abort,
    flash,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeSerializer, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException

import store
import policy
import user_handout

APP_TITLE = "Score Store"
UPLOAD_SCORE_LABEL = "Upload score"
SCORE_LIST_TITLE = "Scores"
VIEWER_MAIN_FILE_LABEL = "Score"
SESSION_USER_KEY = "user_id"
CSRF_SESSION_KEY = "_csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRFToken"
CTX_TOKEN_SALT = "score-nav-ctx"
PREVIEW_TOKEN_SALT = "score-admin-preview"
PREVIEW_TOKEN_PARAM = "preview"
PREVIEW_TOKEN_MAX_AGE_SEC = 3600
SCORE_VIEW_NAV_KEYS = ("lib", "q", "tag", "user", "maestro", PREVIEW_TOKEN_PARAM)
LIBRARY_CTX_USER_PREFIX = "user-"
ADMIN_SCOPE_QUERY_KEYS = ("maestro", "user", "lib")
REQUEST_SCOPE_QUERY_KEYS = (*ADMIN_SCOPE_QUERY_KEYS, PREVIEW_TOKEN_PARAM)
NAV_PRESERVE_BY_ENDPOINT = {
    "admin": ("q", "tag", "maestro", "user", "lib"),
    "maestro": ("q", "tag", "user", "lib"),
    "library": ("q", "tag"),
}
DEFAULT_HTTP_PORT = 5000
DEFAULT_GUNICORN_WORKERS = 4
GUNICORN_BIND_HOST = "0.0.0.0"
DEV_MODE_ENV = "FLASK_DEBUG"
DEV_MODE_CLI_FLAG = "--dev"
GUNICORN_WORKERS_ENV = "GUNICORN_WORKERS"
GUNICORN_SHUTDOWN_WAIT_SEC = 5

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
if os.environ.get("USE_HTTPS") == "1":
    app.config["SESSION_COOKIE_SECURE"] = True


def _ctx_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(app.secret_key, salt=CTX_TOKEN_SALT)


def _preview_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.secret_key, salt=PREVIEW_TOKEN_SALT)


def session_user() -> dict | None:
    """Real logged-in account (ignores ?preview=). Use for @role_required and account admin."""
    uid = session.get(SESSION_USER_KEY)
    if not uid:
        return None
    return store.get_user(uid)


def current_user() -> dict | None:
    """Effective user for library/score UI and permissions; honors admin ?preview= impersonation."""
    token = request.args.get(PREVIEW_TOKEN_PARAM, "")
    if token:
        admin = session_user()
        if admin and policy.is_admin(admin):
            preview_uid = decode_preview_token(token)
            if preview_uid:
                target = store.get_user(preview_uid)
                if target and policy.admin_can_preview_user(admin, target):
                    return target
    return session_user()


def account_user() -> dict | None:
    """Alias for session_user(); use on password changes and account CRUD routes."""
    return session_user()


def encode_preview_token(user_id: str) -> str:
    return _preview_serializer().dumps({"user_id": user_id})


def decode_preview_token(token: str) -> str | None:
    try:
        data = _preview_serializer().loads(token, max_age=PREVIEW_TOKEN_MAX_AGE_SEC)
        user_id = data.get("user_id")
        return user_id if isinstance(user_id, str) and user_id else None
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        return None


def preview_request_active() -> bool:
    token = request.args.get(PREVIEW_TOKEN_PARAM, "")
    if not token:
        return False
    admin = session_user()
    if not admin or not policy.is_admin(admin):
        return False
    preview_uid = decode_preview_token(token)
    if not preview_uid:
        return False
    target = store.get_user(preview_uid)
    return bool(target and policy.admin_can_preview_user(admin, target))


def preview_mutations_blocked() -> bool:
    if not preview_request_active():
        return False
    actor = maestro_management_actor()
    return not (actor and policy.is_maestro(current_user()))


def maestro_management_actor() -> dict | None:
    session = session_user()
    if session and policy.is_maestro(session):
        return session
    if preview_request_active():
        effective = current_user()
        if effective and policy.is_maestro(effective):
            return effective
    return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def safe_redirect_target(url: str | None, default: str) -> str:
    if not url:
        return default
    if not url.startswith("/") or url.startswith("//"):
        return default
    if "\\" in url or "\n" in url or "\r" in url:
        return default
    return url


def ensure_csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_hex(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf() -> None:
    expected = session.get(CSRF_SESSION_KEY)
    if not expected:
        abort(403)
    supplied = request.form.get(CSRF_FORM_FIELD) or request.headers.get(CSRF_HEADER)
    if not supplied or not secrets.compare_digest(supplied, expected):
        abort(403)


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user = account_user()
            if not user or user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def maestro_scope_required(view):
    """Maestro UI routes that allow admin ?preview= impersonation."""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not policy.is_maestro(current_user()):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def password_secret() -> str:
    return app.secret_key


def home_url_for_user(user: dict) -> str:
    if policy.is_admin(user):
        return url_for("admin")
    if policy.is_maestro(user):
        return url_for("maestro")
    return url_for("library")


def nav_preserve_keys(endpoint: str) -> tuple[str, ...]:
    keys = NAV_PRESERVE_BY_ENDPOINT.get(endpoint, ("q", "tag"))
    if has_request_context() and request.args.get(PREVIEW_TOKEN_PARAM):
        if PREVIEW_TOKEN_PARAM not in keys:
            return (*keys, PREVIEW_TOKEN_PARAM)
    return keys


def nav_preserve_from_request(endpoint: str) -> dict:
    return {key: request.args.get(key) for key in nav_preserve_keys(endpoint) if request.args.get(key)}


def preview_query_param() -> dict:
    if has_request_context() and request.args.get(PREVIEW_TOKEN_PARAM):
        return {PREVIEW_TOKEN_PARAM: request.args.get(PREVIEW_TOKEN_PARAM)}
    return {}


def library_id_from_ctx(library_ctx: str) -> str:
    if library_ctx == "global":
        return store.GLOBAL_LIBRARY_ID
    if library_ctx.startswith(LIBRARY_CTX_USER_PREFIX):
        return library_ctx[len(LIBRARY_CTX_USER_PREFIX):]
    return library_ctx


def encode_ctx(score_ids: list[str], index: int) -> str:
    return _ctx_serializer().dumps({"ids": score_ids, "i": index})


def decode_ctx(token: str) -> tuple[list[str], int] | None:
    try:
        data = _ctx_serializer().loads(token)
        return data["ids"], int(data["i"])
    except (BadSignature, KeyError, TypeError, ValueError):
        return None


def json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def file_json(file_entry: dict) -> dict:
    return {**file_entry, "type_label": store.aux_file_type_label(file_entry)}


def score_metadata_from_data(data, user: dict | None = None) -> dict:
    metadata = {
        "title": data.get("title", ""),
        "composer": data.get("composer", ""),
        "arranger": data.get("arranger", ""),
        "description": data.get("description", ""),
        "tags": data.get("tags", "[]"),
    }
    if user and policy.user_can_edit_score_year(user):
        metadata["year"] = data.get("year", "")
    return metadata


def library_scores(library_id: str, query: str, tag: str | None) -> list[dict]:
    return store.scores_for_library_sorted(library_id, query, tag)


def score_view_nav_params_from_request() -> dict:
    params = {key: request.args.get(key) for key in SCORE_VIEW_NAV_KEYS if request.args.get(key)}
    params.update(preview_query_param())
    return params


def score_view_nav_params_from_panel(library_panel: dict) -> dict:
    params = {"lib": library_panel["library_ctx"]}
    if library_panel.get("query"):
        params["q"] = library_panel["query"]
    if library_panel.get("active_tag"):
        params["tag"] = library_panel["active_tag"]
    for key, value in (library_panel.get("preserve") or {}).items():
        if value and key not in params:
            params[key] = value
    params.update(preview_query_param())
    return params


def view_library_id(user: dict) -> str:
    nav = score_view_nav_params_from_request()
    library_ctx = nav.get("lib")
    if not library_ctx:
        if policy.is_maestro(user):
            library_ctx = "global"
        elif policy.is_admin(user):
            library_ctx = "global"
        else:
            library_ctx = f"{LIBRARY_CTX_USER_PREFIX}{user['id']}"
    return _resolve_library_ctx(user, library_ctx)


def notes_storage_for_user(user: dict | None) -> str:
    if not user:
        return "none"
    if policy.is_admin(user) and not preview_request_active():
        return "none"
    if policy.is_choir(user):
        return "local"
    if policy.is_singer(user) or policy.is_maestro(user):
        return "server"
    return "none"


def resolve_score_view_ids(user: dict, score_id: str) -> list[str]:
    ctx_token = request.args.get("ctx")
    if ctx_token:
        decoded = decode_ctx(ctx_token)
        if decoded:
            score_ids, _ = decoded
            if score_id in score_ids:
                try:
                    lib_id = view_library_id(user)
                except HTTPException:
                    return []
                return filter_viewable_score_ids(user, score_ids, score_id, lib_id)
    try:
        library_id = view_library_id(user)
    except HTTPException:
        return []
    nav = score_view_nav_params_from_request()
    scores = library_scores(library_id, nav.get("q", ""), nav.get("tag") or None)
    return [score["id"] for score in scores if score.get("id")]


def filter_viewable_score_ids(
    user: dict,
    score_ids: list,
    current_score_id: str,
    library_id: str,
) -> list[str]:
    if current_score_id not in score_ids:
        return []
    viewable = []
    for sid in score_ids:
        if not isinstance(sid, str) or not sid:
            continue
        meta = store.load_score_meta(sid)
        if meta and policy.user_can_view_score(user, meta, library_id):
            viewable.append(sid)
    if current_score_id not in viewable:
        return []
    return viewable


def build_library_back_url(user: dict, nav_query: dict) -> str:
    if policy.is_admin(user):
        endpoint = "admin"
        params = {key: nav_query[key] for key in nav_preserve_keys(endpoint) if nav_query.get(key)}
    elif policy.is_maestro(user):
        endpoint = "maestro"
        params = {key: nav_query[key] for key in nav_preserve_keys(endpoint) if nav_query.get(key)}
        library_ctx = nav_query.get("lib", "")
        if library_ctx.startswith(LIBRARY_CTX_USER_PREFIX) and "user" not in params:
            params["user"] = library_ctx[len(LIBRARY_CTX_USER_PREFIX):]
    else:
        endpoint = "library"
        params = {key: nav_query[key] for key in nav_preserve_keys(endpoint) if nav_query.get(key)}
    return url_for(endpoint, **params)


def build_library_panel(
    *,
    panel_title: str,
    lib: dict,
    scores: list,
    all_tags: list,
    library_ctx: str,
    nav_endpoint: str,
    preserve: dict,
    query: str,
    active_tag: str | None,
    can_upload: bool = False,
    can_manage_folders: bool = False,
    draggable_score: bool = False,
    panel_hint: str | None = None,
    panel_class: str = "",
    show_header_actions: bool | None = None,
    assign_user: str | None = None,
    summary_opens_viewer: bool = False,
    disk_usage: dict | None = None,
) -> dict:
    if show_header_actions is None:
        show_header_actions = can_upload
    panel = {
        "panel_title": panel_title,
        "panel_hint": panel_hint,
        "panel_class": panel_class,
        "show_header_actions": show_header_actions,
        "lib": lib,
        "scores": scores,
        "all_tags": all_tags,
        "library_ctx": library_ctx,
        "lib_id": library_id_from_ctx(library_ctx),
        "folder_id": store.ROOT_FOLDER_ID,
        "nav_endpoint": nav_endpoint,
        "preserve": preserve,
        "query": query,
        "active_tag": active_tag or "",
        "can_upload": can_upload,
        "can_manage_folders": can_manage_folders,
        "draggable_score": draggable_score,
        "upload_label": UPLOAD_SCORE_LABEL,
        "scores_title": SCORE_LIST_TITLE,
        "score_ids": [s["id"] for s in scores if s.get("id")],
        "assign_user": assign_user,
        "summary_opens_viewer": summary_opens_viewer,
        "folders": lib.get("folders", []),
        "folder_tree": store.build_folder_tree(lib),
    }
    if disk_usage:
        panel["disk_usage"] = disk_usage
    panel["view_nav"] = score_view_nav_params_from_panel(panel)
    return panel


def resolve_library_panel(
    *,
    actor: dict,
    library_ctx: str,
    nav_endpoint: str,
    preserve: dict | None = None,
    query: str = "",
    active_tag: str | None = None,
    panel_title: str | None = None,
    panel_hint: str | None = None,
    panel_class: str = "",
    draggable_score: bool = False,
    assign_user: str | None = None,
    summary_opens_viewer: bool = False,
    include_disk_usage: bool = False,
) -> dict:
    lib_id = library_id_from_ctx(library_ctx)
    lib = store.load_library(lib_id)
    scores = library_scores(lib_id, query, active_tag)
    tags = store.collect_tags(lib.get("score_order", []))
    caps = policy.library_panel_capabilities(actor, lib_id)
    title = panel_title or lib.get("display_name") or "Library"
    disk_usage = store.disk_usage_stats() if include_disk_usage else None
    return build_library_panel(
        panel_title=title,
        lib=lib,
        scores=scores,
        all_tags=tags,
        library_ctx=library_ctx,
        nav_endpoint=nav_endpoint,
        preserve=dict(preserve or {}),
        query=query,
        active_tag=active_tag,
        can_upload=caps["can_upload"],
        can_manage_folders=caps["can_manage_folders"],
        draggable_score=draggable_score,
        panel_hint=panel_hint,
        panel_class=panel_class,
        assign_user=assign_user,
        summary_opens_viewer=summary_opens_viewer,
        disk_usage=disk_usage,
        show_header_actions=caps["can_upload"],
    )


def build_user_tree(ctx: dict) -> list[dict]:
    nodes: list[dict] = []
    query = ctx.get("query", "")
    active_tag = ctx.get("active_tag")
    selected_maestro = ctx.get("selected_maestro")
    selected_user = ctx.get("selected_user")
    selected_lib = ctx.get("selected_lib")
    if ctx.get("show_maestro_nodes"):
        for maestro in store.get_maestro_accounts():
            uname = maestro["username"]
            stats = store.maestro_stats(uname)
            children: list[dict] = []
            if ctx.get("show_global_library_nodes"):
                children.append({
                    "kind": "global_library",
                    "id": store.GLOBAL_LIBRARY_ID,
                    "display_name": store.GLOBAL_LIBRARY_DISPLAY_NAME,
                    "maestro_username": uname,
                    "active": selected_maestro == uname and selected_lib == "global",
                })
            for sub in store.get_users_for_maestro(maestro["id"]):
                children.append({
                    "kind": "user",
                    "id": sub["id"],
                    "username": sub["username"],
                    "display_name": sub["display_name"],
                    "role": sub["role"],
                    "maestro_username": uname,
                    "active": selected_maestro == uname and selected_user == sub["id"],
                })
            maestro_cfg = store.load_maestro_config(uname)
            nodes.append({
                "kind": "maestro",
                "id": maestro["id"],
                "username": uname,
                "display_name": maestro["display_name"],
                "site_title": maestro_cfg.get("site_title", ""),
                "show_site_title": maestro_cfg.get("show_site_title", store.DEFAULT_SHOW_SITE_TITLE),
                "logotype_url": admin_maestro_logotype_url(uname),
                "stats": stats,
                "children": children,
                "active": selected_maestro == uname and not selected_user,
            })
        return nodes
    maestro_id = ctx["maestro_id"]
    for sub in store.get_users_for_maestro(maestro_id):
        entry = {
            "kind": "user",
            "id": sub["id"],
            "username": sub["username"],
            "display_name": sub["display_name"],
            "role": sub["role"],
            "active": selected_user == sub["id"],
        }
        if ctx.get("show_user_edit"):
            entry["password"] = store.password_for_display(sub)
        nodes.append(entry)
    return nodes


def user_tree_node_url(endpoint: str, node: dict, query: str = "", active_tag: str | None = None) -> str:
    preserve = {}
    kind = node.get("kind")
    if kind == "maestro":
        preserve["maestro"] = node["username"]
    elif kind == "global_library":
        preserve["maestro"] = node["maestro_username"]
        preserve["lib"] = "global"
    elif kind == "user":
        if node.get("maestro_username"):
            preserve["maestro"] = node["maestro_username"]
        preserve["user"] = node["id"]
    return build_nav_url(endpoint, query=query, active_tag=active_tag or "", preserve=preserve)


def resolve_maestro_brand(user: dict | None) -> dict | None:
    if not user:
        return None
    if policy.is_admin(user):
        maestro_param = request.args.get("maestro", "").strip().lower()
        if not maestro_param or not policy.admin_can_view_maestro(user, maestro_param):
            return None
        username = maestro_param
    else:
        try:
            username = store.maestro_folder_username(user)
        except ValueError:
            return None
    cfg = store.load_maestro_config(username)
    logotype_path = store.maestro_logotype_path(username)
    logotype_url = None
    if logotype_path:
        logotype_url = append_scope_query_params(url_for("maestro_logotype", maestro_username=username))
    theme_url = None
    if store.maestro_has_theme(username):
        theme_url = append_scope_query_params(url_for("maestro_theme_css", maestro_username=username))
    has_logotype = bool(logotype_path)
    return {
        "username": username,
        "site_title": cfg.get("site_title", ""),
        "show_site_title": store.maestro_header_show_title(cfg, has_logotype),
        "logotype_url": logotype_url,
        "theme_url": theme_url,
        "has_theme": bool(theme_url),
    }


def scope_query_params() -> dict:
    params = {}
    if not has_request_context():
        return params
    for key in REQUEST_SCOPE_QUERY_KEYS:
        value = request.args.get(key)
        if value:
            params[key] = value
    return params


def activate_maestro_for_user(user: dict) -> None:
    if policy.is_maestro(user):
        store.activate_maestro_data(user["username"])
        return
    if user.get("role") in store.SUB_ACCOUNT_ROLES:
        try:
            store.activate_maestro_data(store.maestro_folder_username(user))
        except ValueError:
            pass


def append_scope_query_params(url: str) -> str:
    extra = scope_query_params()
    if not extra:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urlencode(extra)}"


def admin_maestro_logotype_url(maestro_username: str) -> str | None:
    uname = maestro_username.strip().lower()
    if not store.maestro_logotype_path(uname):
        return None
    return url_for("maestro_logotype", maestro_username=uname, maestro=uname)


def _maestro_asset_allowed(actor: dict, maestro_username: str) -> bool:
    uname = maestro_username.strip().lower()
    if preview_request_active():
        try:
            return store.maestro_folder_username(actor) == uname
        except ValueError:
            return False
    if policy.is_admin(actor):
        preview = request.args.get("maestro", "").strip().lower()
        return preview == uname and policy.admin_can_view_maestro(actor, uname)
    try:
        return store.maestro_folder_username(actor) == uname
    except ValueError:
        return False


@app.template_global()
def user_can_edit_score(user, score):
    return policy.user_can_edit_score(user, score)


@app.template_global()
def user_can_edit_score_year(user):
    return policy.user_can_edit_score_year(user)


@app.template_global()
def score_subtitle_line(score):
    return store.score_subtitle_line(score)


@app.template_global()
def user_can_hard_delete_score(user, score, library_id=None):
    return policy.user_can_hard_delete_score(user, score, library_id)


@app.template_global()
def user_can_remove_score(user, score, library_id):
    return policy.user_can_remove_score(user, score, library_id)


@app.template_global()
def view_ctx_token(score_ids, score_id):
    if not score_id or not score_ids or score_id not in score_ids:
        return ""
    return encode_ctx(score_ids, score_ids.index(score_id))


@app.template_global()
def score_view_url(score_id, library_panel):
    params = score_view_nav_params_from_panel(library_panel)
    ctx = view_ctx_token(library_panel["score_ids"], score_id)
    if ctx:
        params["ctx"] = ctx
    return url_for("score_view", score_id=score_id, **params)


@app.template_global()
def aux_file_type_label(file_entry):
    return store.aux_file_type_label(file_entry)


@app.template_global()
def file_extension(stored_name):
    return store.extension_of(stored_name or "")


@app.template_global()
def serve_file_url(score_id, stored_name):
    return append_scope_query_params(url_for("serve_file", score_id=score_id, stored_name=stored_name))


@app.template_global()
def score_download_url(score_id):
    return append_scope_query_params(url_for("score_download", score_id=score_id))


@app.template_global()
def build_nav_url(endpoint, query="", active_tag="", preserve=None):
    params = dict(preserve or {})
    params.update(preview_query_param())
    if query:
        params["q"] = query
    if active_tag:
        params["tag"] = active_tag
    return url_for(endpoint, **params)


def preview_redirect_url(user: dict) -> str:
    token = encode_preview_token(user["id"])
    role = user.get("role", "")
    if role == store.MAESTRO_ROLE:
        return url_for("maestro", **{PREVIEW_TOKEN_PARAM: token})
    if role in store.SUB_ACCOUNT_ROLES:
        return url_for("library", **{PREVIEW_TOKEN_PARAM: token})
    return url_for("admin", **{PREVIEW_TOKEN_PARAM: token})


@app.template_global()
def user_tree_node_url_global(endpoint, node, query="", active_tag=""):
    return user_tree_node_url(endpoint, node, query=query, active_tag=active_tag or None)


@app.template_global()
def admin_preview_user_url(user_id):
    return url_for("admin_preview_user", user_id=user_id)


@app.template_global()
def csrf_token():
    return ensure_csrf_token()


_SETUP_EXEMPT = frozenset({"setup", "static"})
PREVIEW_ALLOWED_POST_ENDPOINTS = frozenset({"mint_viewer_ctx"})


@app.before_request
def _setup_and_bootstrap():
    if request.endpoint in _SETUP_EXEMPT:
        return
    if store.ensure_data_ready(password_secret()):
        return redirect(url_for("setup"))


@app.before_request
def _activate_maestro_data_scope():
    if request.endpoint in _SETUP_EXEMPT:
        return
    actor = session_user()
    if not actor:
        return
    if policy.is_admin(actor):
        maestro_param = request.args.get("maestro", "").strip().lower()
        if maestro_param and policy.admin_can_view_maestro(actor, maestro_param):
            store.activate_maestro_data(maestro_param)
            return
        if preview_request_active():
            target = current_user()
            if target:
                activate_maestro_for_user(target)
        return
    activate_maestro_for_user(actor)


@app.before_request
def _block_preview_mutations():
    if request.method not in ("POST", "PUT"):
        return
    if request.endpoint in _SETUP_EXEMPT or request.endpoint == "static":
        return
    if preview_mutations_blocked() and request.endpoint not in PREVIEW_ALLOWED_POST_ENDPOINTS:
        abort(403)


@app.before_request
def _csrf_protect():
    if request.method != "POST":
        return
    if request.endpoint == "static":
        return
    validate_csrf()


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if not store.needs_setup():
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", store.DEFAULT_ADMIN_USERNAME)
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        data_dir = request.form.get("data_dir", "")
        if password != password_confirm:
            flash("Passwords do not match", "error")
        else:
            try:
                store.complete_setup(username, password, Path(data_dir), password_secret())
                flash("Setup complete. Sign in with your admin account.", "success")
                return redirect(url_for("login"))
            except ValueError as e:
                flash(str(e), "error")
            except OSError as e:
                flash(f"Cannot use storage path: {e}", "error")
    return render_template(
        "setup.html",
        default_username=store.DEFAULT_ADMIN_USERNAME,
        default_data_dir=store.default_setup_data_dir_display(),
        password_min_len=store.SETUP_PASSWORD_MIN_LEN,
    )


@app.template_filter("user_password_display")
def user_password_display(user):
    return store.password_for_display(user)


@app.context_processor
def inject_globals():
    user = current_user()
    brand = resolve_maestro_brand(user)
    browser_title = APP_TITLE
    if brand and brand.get("site_title"):
        browser_title = brand["site_title"]
    elif user:
        browser_title = f"{APP_TITLE} - {user['display_name']}"
    preview_mode = preview_request_active()
    preview_user = user if preview_mode else None
    return {
        "app_title": APP_TITLE,
        "browser_title": browser_title,
        "current_user": user,
        "password_min_len": store.SETUP_PASSWORD_MIN_LEN,
        "maestro_brand": brand,
        "preview_mode": preview_mode,
        "preview_user": preview_user,
        "notes_storage": notes_storage_for_user(user),
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    user = current_user()
    if user:
        return redirect(home_url_for_user(user))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = store.get_user_by_username(username)
        secret = password_secret()
        if user and store.verify_user_password(user, password, secret):
            session[SESSION_USER_KEY] = user["id"]
            nxt = safe_redirect_target(request.args.get("next"), home_url_for_user(user))
            return redirect(nxt)
        flash("Invalid username or password", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop(SESSION_USER_KEY, None)
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    user = current_user()
    return redirect(home_url_for_user(user))


@app.route("/library")
@login_required
def library():
    user = current_user()
    if policy.is_admin(user) or policy.is_maestro(user):
        abort(403)
    lib_id = user["id"]
    query = request.args.get("q", "")
    tag = request.args.get("tag")
    caps = policy.library_panel_capabilities(user, lib_id)
    library_panel = resolve_library_panel(
        actor=user,
        library_ctx=f"{LIBRARY_CTX_USER_PREFIX}{lib_id}",
        nav_endpoint="library",
        query=query,
        active_tag=tag,
        panel_title="My library",
        panel_class="desktop-panel-page",
        summary_opens_viewer=True,
    )
    return render_template(
        "library.html",
        library_id=lib_id,
        library_panel=library_panel,
        can_upload=caps["can_upload"],
        is_choir=caps["is_choir"],
    )


@app.get("/admin/preview/<user_id>")
@role_required(store.ADMIN_ROLE)
def admin_preview_user(user_id):
    admin = session_user()
    target = store.get_user(user_id)
    if not target or not admin or not policy.admin_can_preview_user(admin, target):
        abort(404)
    return redirect(preview_redirect_url(target))


@app.route("/admin")
@role_required(store.ADMIN_ROLE)
def admin():
    user = session_user()
    query = request.args.get("q", "")
    tag = request.args.get("tag")
    selected_maestro = request.args.get("maestro", "").strip().lower() or None
    selected_user = request.args.get("user")
    selected_lib = request.args.get("lib")
    if not selected_maestro and not selected_user:
        maestros = store.get_maestro_accounts()
        if len(maestros) == 1:
            params = {"maestro": maestros[0]["username"]}
            if query:
                params["q"] = query
            if tag:
                params["tag"] = tag
            return redirect(url_for("admin", **params))
    tree_ctx = {
        "show_maestro_nodes": True,
        "show_global_library_nodes": False,
        "show_user_edit": False,
        "show_maestro_actions": True,
        "show_user_preview": True,
        "drop_target_users": False,
        "nav_endpoint": "admin",
        "query": query,
        "active_tag": tag,
        "selected_maestro": selected_maestro,
        "selected_user": selected_user,
        "selected_lib": selected_lib,
    }
    user_tree = build_user_tree(tree_ctx)
    library_panel = None
    maestro_stats = None
    if selected_maestro and policy.admin_can_view_maestro(user, selected_maestro):
        maestro_stats = store.maestro_stats(selected_maestro)
        preserve = nav_preserve_from_request("admin")
        if selected_user:
            target = store.get_user(selected_user)
            if not target or target.get("maestro_id") != store.get_user_by_username(selected_maestro)["id"]:
                abort(403)
            library_panel = resolve_library_panel(
                actor=user,
                library_ctx=f"{LIBRARY_CTX_USER_PREFIX}{selected_user}",
                nav_endpoint="admin",
                preserve=preserve,
                query=query,
                active_tag=tag,
                draggable_score=False,
                summary_opens_viewer=True,
            )
        else:
            library_panel = resolve_library_panel(
                actor=user,
                library_ctx="global",
                nav_endpoint="admin",
                preserve=preserve,
                query=query,
                active_tag=tag,
                panel_title=store.GLOBAL_LIBRARY_DISPLAY_NAME,
                include_disk_usage=True,
            )
    return render_template(
        "admin.html",
        user_tree=user_tree,
        tree_ctx=tree_ctx,
        library_panel=library_panel,
        maestro_stats=maestro_stats,
        query=query,
        active_tag=tag,
        selected_maestro=selected_maestro,
    )


@app.route("/maestro")
@maestro_scope_required
def maestro():
    user = current_user()
    query = request.args.get("q", "")
    tag = request.args.get("tag")
    selected_user = request.args.get("user")
    preserve = nav_preserve_from_request("maestro")
    global_library_panel = resolve_library_panel(
        actor=user,
        library_ctx="global",
        nav_endpoint="maestro",
        preserve=preserve,
        query=query,
        active_tag=tag,
        panel_title=store.GLOBAL_LIBRARY_DISPLAY_NAME,
        draggable_score=True,
        include_disk_usage=True,
    )
    user_library_panel = None
    if selected_user:
        target = store.get_user(selected_user)
        if not target or not policy.user_owns_sub_account(user, target):
            abort(403)
        user_library_panel = resolve_library_panel(
            actor=user,
            library_ctx=f"{LIBRARY_CTX_USER_PREFIX}{selected_user}",
            nav_endpoint="maestro",
            preserve=preserve,
            query=query,
            active_tag=tag,
            draggable_score=True,
            assign_user=selected_user,
        )
    can_manage_users = maestro_management_actor() is not None
    tree_ctx = {
        "show_maestro_nodes": False,
        "show_global_library_nodes": False,
        "show_user_edit": can_manage_users,
        "show_maestro_actions": False,
        "show_user_preview": False,
        "drop_target_users": can_manage_users,
        "nav_endpoint": "maestro",
        "maestro_id": user["id"],
        "query": query,
        "active_tag": tag,
        "selected_user": selected_user,
    }
    user_tree = build_user_tree(tree_ctx)
    return render_template(
        "maestro.html",
        global_library_panel=global_library_panel,
        user_library_panel=user_library_panel,
        user_tree=user_tree,
        tree_ctx=tree_ctx,
        query=query,
        active_tag=tag,
        selected_user=selected_user,
    )


@app.post("/maestro/users/new")
@login_required
def maestro_user_new():
    actor = maestro_management_actor()
    if not actor:
        abort(403)
    display_name = request.form.get("display_name", "").strip()
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", policy.SINGER_ROLE)
    if not display_name or not username or not password:
        flash("All fields required", "error")
        return redirect(url_for("maestro"))
    if role not in store.SUB_ACCOUNT_ROLES:
        flash("Invalid role", "error")
        return redirect(url_for("maestro"))
    try:
        store.create_sub_account(display_name, username, password, role, actor["id"], password_secret())
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("maestro"))
    flash("User created", "success")
    return redirect(url_for("maestro"))


@app.post("/maestro/users/<user_id>/edit")
@login_required
def maestro_user_edit(user_id):
    actor = maestro_management_actor()
    if not actor:
        abort(403)
    user = store.get_user(user_id)
    if not user or not policy.user_owns_sub_account(actor, user):
        abort(404)
    display_name = request.form.get("display_name", "").strip()
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", user["role"])
    if not display_name or not username:
        flash("Display name and username required", "error")
        return redirect(url_for("maestro"))
    if role not in store.SUB_ACCOUNT_ROLES:
        flash("Invalid role", "error")
        return redirect(url_for("maestro"))
    existing = store.get_user_by_username(username)
    if existing and existing["id"] != user_id:
        flash("Username taken", "error")
        return redirect(url_for("maestro"))
    user["display_name"] = display_name
    user["username"] = username
    user["role"] = role
    user["maestro_id"] = actor["id"]
    if password:
        store.set_user_password(user, password, password_secret())
    else:
        store.finalize_user_role(user, password_secret())
    new_id = store.rename_user_id(user_id, username)
    user["id"] = new_id
    users = store.load_users()
    for i, u in enumerate(users):
        if u["id"] in (user_id, new_id):
            users[i] = user
            break
    store.save_users(users)
    store.ensure_library(new_id)
    flash("User updated", "success")
    selected = request.args.get("user")
    if selected == user_id:
        selected = new_id
    return redirect(url_for("maestro", user=selected))


@app.post("/maestro/users/<user_id>/delete")
@login_required
def maestro_user_delete(user_id):
    actor = maestro_management_actor()
    if not actor:
        abort(403)
    target = store.get_user(user_id)
    if not target or not policy.user_owns_sub_account(actor, target):
        abort(404)
    try:
        store.delete_user(user_id)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("maestro", user=request.args.get("user")))
    flash("User deleted", "success")
    selected = request.args.get("user")
    if selected == user_id:
        return redirect(url_for("maestro"))
    return redirect(url_for("maestro", user=selected))


@app.post("/admin/maestros")
@role_required(store.ADMIN_ROLE)
def admin_maestro_new():
    display_name = request.form.get("display_name", "").strip()
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    site_title = request.form.get("site_title", "").strip()
    if not display_name or not username or not password:
        flash("Display name, username, and password required", "error")
        return redirect(url_for("admin"))
    try:
        user = store.create_maestro_account(display_name, username, password, password_secret())
        show_site_title = store.form_show_site_title_checked(request.form.get("show_site_title"))
        store.save_maestro_config(username, {
            "site_title": site_title or display_name,
            "logotype": "",
            "show_site_title": show_site_title,
        })
        theme_upload = request.files.get("theme_css")
        if theme_upload and theme_upload.filename:
            theme_upload.save(store.maestro_theme_path(username))
        logotype_upload = request.files.get("logotype")
        if logotype_upload and logotype_upload.filename:
            ext = store.extension_of(logotype_upload.filename)
            if ext in store.LOGOTYPE_EXTENSIONS:
                dest = store.maestro_data_dir(username) / store.MAESTRO_ASSETS_DIRNAME / f"{store.LOGOTYPE_STORED_BASENAME}.{ext}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                logotype_upload.save(dest)
                rel = f"{store.MAESTRO_ASSETS_DIRNAME}/{store.LOGOTYPE_STORED_BASENAME}.{ext}"
                cfg = store.load_maestro_config(username)
                cfg["site_title"] = site_title or display_name
                cfg["logotype"] = rel
                store.save_maestro_config(username, cfg)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin"))
    flash("Maestro created", "success")
    return redirect(url_for("admin", maestro=user["username"]))


@app.post("/admin/maestros/<maestro_id>")
@role_required(store.ADMIN_ROLE)
def admin_maestro_edit(maestro_id):
    target = store.get_user(maestro_id)
    if not target or target.get("role") != store.MAESTRO_ROLE:
        abort(404)
    old_username = target["username"]
    display_name = request.form.get("display_name", "").strip()
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    site_title = request.form.get("site_title", "").strip()
    if not display_name or not username:
        flash("Display name and username required", "error")
        return redirect(url_for("admin", maestro=old_username))
    existing = store.get_user_by_username(username)
    if existing and existing["id"] != maestro_id:
        flash("Username taken", "error")
        return redirect(url_for("admin", maestro=old_username))
    if username != old_username:
        try:
            store.rename_maestro_folder(old_username, username)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("admin", maestro=old_username))
    target["display_name"] = display_name
    target["username"] = username
    if password:
        store.set_user_password(target, password, password_secret())
    users = store.load_users()
    for i, entry in enumerate(users):
        if entry["id"] == maestro_id:
            users[i] = target
            break
    store.save_users(users)
    cfg = store.load_maestro_config(username)
    if site_title:
        cfg["site_title"] = site_title
    cfg["show_site_title"] = store.form_show_site_title_checked(request.form.get("show_site_title"))
    theme_text = request.form.get("theme_css_text", "")
    if theme_text.strip():
        store.maestro_theme_path(username).write_text(theme_text, encoding="utf-8")
    theme_upload = request.files.get("theme_css")
    if theme_upload and theme_upload.filename:
        theme_upload.save(store.maestro_theme_path(username))
    logotype_upload = request.files.get("logotype")
    if logotype_upload and logotype_upload.filename:
        ext = store.extension_of(logotype_upload.filename)
        if ext in store.LOGOTYPE_EXTENSIONS:
            dest = store.maestro_data_dir(username) / store.MAESTRO_ASSETS_DIRNAME / f"{store.LOGOTYPE_STORED_BASENAME}.{ext}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            logotype_upload.save(dest)
            cfg["logotype"] = f"{store.MAESTRO_ASSETS_DIRNAME}/{store.LOGOTYPE_STORED_BASENAME}.{ext}"
    if request.form.get("remove_logotype") == "1":
        cfg["logotype"] = ""
    store.save_maestro_config(username, cfg)
    flash("Maestro updated", "success")
    return redirect(url_for("admin", maestro=username))


@app.delete("/admin/maestros/<maestro_id>")
@role_required(store.ADMIN_ROLE)
def admin_maestro_delete(maestro_id):
    try:
        store.delete_maestro_account(maestro_id)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("admin"))
    flash("Maestro deleted", "success")
    return redirect(url_for("admin"))


@app.post("/admin/password")
@role_required(store.ADMIN_ROLE)
def admin_change_password():
    user = account_user()
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("new_password_confirm", "")
    if not current_password or not new_password:
        flash("Current and new password required", "error")
        return redirect(safe_redirect_target(request.referrer, url_for("admin")))
    if new_password != confirm_password:
        flash("New passwords do not match", "error")
        return redirect(safe_redirect_target(request.referrer, url_for("admin")))
    if len(new_password) < store.SETUP_PASSWORD_MIN_LEN:
        flash(f"Password must be at least {store.SETUP_PASSWORD_MIN_LEN} characters", "error")
        return redirect(safe_redirect_target(request.referrer, url_for("admin")))
    stored = store.get_user(user["id"])
    secret = password_secret()
    if not stored or not store.verify_user_password(stored, current_password, secret):
        flash("Current password is wrong", "error")
        return redirect(safe_redirect_target(request.referrer, url_for("admin")))
    store.set_user_password(stored, new_password, secret)
    users = store.load_users()
    for i, entry in enumerate(users):
        if entry["id"] == stored["id"]:
            users[i] = stored
            break
    store.save_users(users)
    flash("Password updated", "success")
    return redirect(safe_redirect_target(request.referrer, url_for("admin")))


@app.route("/maestro/appearance", methods=["GET", "POST"])
@role_required(store.MAESTRO_ROLE)
def maestro_appearance():
    user = current_user()
    username = user["username"]
    if request.method == "POST":
        if not policy.user_can_edit_maestro_config(user, username):
            abort(403)
        site_title = request.form.get("site_title", "").strip()
        cfg = store.load_maestro_config(username)
        cfg["site_title"] = site_title or user["display_name"]
        cfg["show_site_title"] = store.form_show_site_title_checked(request.form.get("show_site_title"))
        theme_text = request.form.get("theme_css_text", "")
        if theme_text.strip():
            store.maestro_theme_path(username).write_text(theme_text, encoding="utf-8")
        theme_upload = request.files.get("theme_css")
        if theme_upload and theme_upload.filename:
            theme_upload.save(store.maestro_theme_path(username))
        logotype_upload = request.files.get("logotype")
        if logotype_upload and logotype_upload.filename:
            ext = store.extension_of(logotype_upload.filename)
            if ext in store.LOGOTYPE_EXTENSIONS:
                dest = store.maestro_data_dir(username) / store.MAESTRO_ASSETS_DIRNAME / f"{store.LOGOTYPE_STORED_BASENAME}.{ext}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                logotype_upload.save(dest)
                cfg["logotype"] = f"{store.MAESTRO_ASSETS_DIRNAME}/{store.LOGOTYPE_STORED_BASENAME}.{ext}"
        if request.form.get("remove_logotype") == "1":
            cfg["logotype"] = ""
        store.save_maestro_config(username, cfg)
        flash("Appearance saved", "success")
        return redirect(url_for("maestro_appearance"))
    cfg = store.load_maestro_config(username)
    theme_css = ""
    theme_path = store.maestro_theme_path(username)
    if theme_path.is_file():
        theme_css = theme_path.read_text(encoding="utf-8")
    return render_template(
        "maestro_appearance.html",
        config=cfg,
        theme_css=theme_css,
    )


@app.get("/maestro-assets/<maestro_username>/theme.css")
@login_required
def maestro_theme_css(maestro_username):
    actor = current_user()
    if not _maestro_asset_allowed(actor, maestro_username):
        abort(403)
    path = store.maestro_theme_path(maestro_username)
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype="text/css")


@app.get("/maestro-assets/<maestro_username>/logotype")
@login_required
def maestro_logotype(maestro_username):
    actor = current_user()
    if not _maestro_asset_allowed(actor, maestro_username):
        abort(403)
    path = store.maestro_logotype_path(maestro_username)
    if not path:
        abort(404)
    return send_file(path)


@app.post("/maestro/password")
@role_required(store.MAESTRO_ROLE)
def maestro_change_password():
    user = account_user()
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("new_password_confirm", "")
    if not current_password or not new_password:
        flash("Current and new password required", "error")
        return redirect(safe_redirect_target(request.referrer, url_for("maestro")))
    if new_password != confirm_password:
        flash("New passwords do not match", "error")
        return redirect(safe_redirect_target(request.referrer, url_for("maestro")))
    if len(new_password) < store.SETUP_PASSWORD_MIN_LEN:
        flash(f"Password must be at least {store.SETUP_PASSWORD_MIN_LEN} characters", "error")
        return redirect(safe_redirect_target(request.referrer, url_for("maestro")))
    stored = store.get_user(user["id"])
    secret = password_secret()
    if not stored or not store.verify_user_password(stored, current_password, secret):
        flash("Current password is wrong", "error")
        return redirect(safe_redirect_target(request.referrer, url_for("maestro")))
    store.set_user_password(stored, new_password, secret)
    users = store.load_users()
    for i, entry in enumerate(users):
        if entry["id"] == stored["id"]:
            users[i] = stored
            break
    store.save_users(users)
    flash("Password updated", "success")
    return redirect(safe_redirect_target(request.referrer, url_for("maestro")))


def _user_handout_context(user_id: str) -> dict:
    actor = maestro_management_actor()
    if not actor:
        abort(403)
    user = store.get_user(user_id)
    if not user or user.get("role") not in store.SUB_ACCOUNT_ROLES:
        abort(404)
    if not policy.user_owns_sub_account(actor, user):
        abort(403)
    site_url = request.url_root.rstrip("/")
    password_plain = store.password_for_display(user)
    return user_handout.handout_context(user, site_url, APP_TITLE, password_plain)


@app.get("/maestro/users/<user_id>/handout")
@maestro_scope_required
def maestro_user_handout(user_id):
    ctx = _user_handout_context(user_id)
    return render_template("partials/user_handout_content.html", **ctx)


@app.get("/maestro/users/<user_id>/handout.pdf")
@maestro_scope_required
def maestro_user_handout_pdf(user_id):
    ctx = _user_handout_context(user_id)
    try:
        pdf_bytes, filename = user_handout.build_handout_pdf(ctx)
    except FileNotFoundError:
        abort(503, "PDF font not available on server")
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.post("/maestro/assign")
@login_required
def maestro_assign():
    user = maestro_management_actor()
    if not user or not policy.user_can_assign_scores(user):
        abort(403)
    data = request.get_json(silent=True) or {}
    score_id = data.get("score_id")
    user_id = data.get("user_id")
    assign = data.get("assign", True)
    if not score_id or not user_id:
        return json_error("score_id and user_id required")
    target = store.get_user(user_id)
    if not target or not policy.user_owns_sub_account(user, target):
        return json_error("User not found", 404)
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Score not found", 404)
    if assign:
        store.assign_score_to_folder(user_id, score_id, store.ROOT_FOLDER_ID)
    else:
        store.remove_score_from_library(user_id, score_id)
        return jsonify({"ok": True})
    return jsonify({"ok": True, "score": meta})


@app.post("/library/<library_ctx>/folders/new")
@login_required
def folder_new(library_ctx):
    user = current_user()
    lib_id = _resolve_library_ctx(user, library_ctx)
    if not policy.user_can_manage_folders_in_library(user, lib_id):
        abort(403)
    name = request.form.get("name", "").strip()
    if not name:
        return json_error("Name required")
    parent_id = request.form.get("parent_id", store.ROOT_FOLDER_ID) or store.ROOT_FOLDER_ID
    try:
        folder = store.create_folder(lib_id, name, parent_id)
    except ValueError as e:
        return json_error(str(e))
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(folder)
    return redirect(safe_redirect_target(request.referrer, url_for("library")))


@app.post("/library/<library_ctx>/folders/<folder_id>/delete")
@login_required
def folder_delete(library_ctx, folder_id):
    user = current_user()
    lib_id = _resolve_library_ctx(user, library_ctx)
    if not policy.user_can_manage_folders_in_library(user, lib_id):
        abort(403)
    try:
        store.delete_folder(lib_id, folder_id)
    except ValueError as e:
        return json_error(str(e))
    return jsonify({"ok": True})


def _resolve_library_ctx(user: dict, library_ctx: str) -> str:
    if library_ctx == "global":
        if policy.is_admin(user):
            if not store.current_maestro_data():
                abort(403)
            return store.GLOBAL_LIBRARY_ID
        if policy.is_maestro(user):
            return store.GLOBAL_LIBRARY_ID
        abort(403)
    if library_ctx.startswith(LIBRARY_CTX_USER_PREFIX):
        uid = library_ctx[len(LIBRARY_CTX_USER_PREFIX):]
        target = store.get_user(uid)
        if not target:
            abort(404)
        if policy.is_admin(user):
            maestro_param = request.args.get("maestro", "").strip().lower()
            owner = store.get_user_by_username(maestro_param) if maestro_param else None
            if not owner or target.get("maestro_id") != owner["id"]:
                abort(403)
            return uid
        if policy.is_maestro(user):
            if policy.user_owns_sub_account(user, target):
                return uid
            abort(403)
        if user["id"] == uid:
            return uid
        abort(403)
    if policy.is_maestro(user):
        return store.GLOBAL_LIBRARY_ID
    return user["id"]


@app.post("/library/<library_ctx>/scores/new")
@login_required
def score_new(library_ctx):
    user = current_user()
    lib_id = _resolve_library_ctx(user, library_ctx)
    if not policy.user_can_upload_to_library(user, lib_id):
        abort(403)
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return json_error("PDF file required")
    folder_id = request.form.get("folder_id", store.ROOT_FOLDER_ID)
    metadata = score_metadata_from_data(request.form)
    try:
        meta = store.create_score_from_upload(lib_id, folder_id, upload, metadata, store.score_owner_id(user))
    except ValueError as e:
        return json_error(str(e))
    return jsonify({"ok": True, "score": meta})


@app.post("/scores/<score_id>/edit")
@login_required
def score_edit(score_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    if not policy.user_can_edit_score(user, meta):
        abort(403)
    data = request.get_json(silent=True) or request.form
    metadata = score_metadata_from_data(data, user)
    try:
        meta = store.update_score_metadata(score_id, metadata, allow_year=policy.user_can_edit_score_year(user))
    except ValueError as e:
        return json_error(str(e))
    return jsonify({"ok": True, "score": meta})


@app.post("/library/<library_ctx>/scores/<score_id>/folder")
@login_required
def score_set_folder(library_ctx, score_id):
    user = current_user()
    lib_id = _resolve_library_ctx(user, library_ctx)
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    if not policy.user_can_set_score_folder(user, meta, lib_id):
        abort(403)
    data = request.get_json(silent=True) or request.form
    folder_id = data.get("folder_id", store.ROOT_FOLDER_ID)
    lib = store.load_library(lib_id)
    if folder_id not in store.library_folder_ids(lib):
        return json_error("Unknown folder")
    try:
        store.set_score_folder(lib_id, score_id, folder_id)
    except ValueError as e:
        return json_error(str(e))
    return jsonify({"ok": True})


@app.post("/scores/<score_id>/files")
@login_required
def score_add_file(score_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    if not policy.user_can_edit_score(user, meta):
        abort(403)
    if request.is_json:
        data = request.get_json()
        try:
            entry = store.add_youtube_aux(score_id, data.get("url", ""), data.get("name", ""))
        except ValueError as e:
            return json_error(str(e))
        return jsonify({"ok": True, "file": file_json(entry)})
    upload = request.files.get("file")
    if not upload:
        return json_error("File required")
    try:
        entry = store.add_aux_file(score_id, upload)
    except ValueError as e:
        return json_error(str(e))
    return jsonify({"ok": True, "file": file_json(entry)})


@app.post("/scores/<score_id>/files/<file_id>/remove")
@login_required
def score_remove_file(score_id, file_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta or not policy.user_can_edit_score(user, meta):
        abort(403)
    try:
        store.remove_aux_file(score_id, file_id)
    except ValueError as e:
        return json_error(str(e))
    return jsonify({"ok": True})


@app.post("/scores/<score_id>/files/<file_id>/name")
@login_required
def score_file_name(score_id, file_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta or not policy.user_can_edit_score(user, meta):
        abort(403)
    data = request.get_json(silent=True) or request.form
    try:
        f = store.update_file_name(score_id, file_id, data.get("name", ""))
    except ValueError as e:
        return json_error(str(e))
    return jsonify({"ok": True, "file": file_json(f)})


@app.post("/scores/<src_id>/files/<file_id>/move")
@login_required
def score_file_move(src_id, file_id):
    user = current_user()
    src = store.load_score_meta(src_id)
    if not src or not policy.user_can_edit_score(user, src):
        abort(403)
    data = request.get_json(silent=True) or {}
    dst_id = data.get("to_score_id")
    if not dst_id:
        return json_error("to_score_id required")
    dst = store.load_score_meta(dst_id)
    if not dst or not policy.user_can_edit_score(user, dst):
        abort(403)
    try:
        store.move_file_between_scores(src_id, file_id, dst_id)
    except ValueError as e:
        return json_error(str(e))
    return jsonify({"ok": True})


@app.post("/scores/<src_id>/files/<file_id>/split")
@login_required
def score_file_split(src_id, file_id):
    user = current_user()
    src = store.load_score_meta(src_id)
    if not src or not policy.user_can_edit_score(user, src):
        abort(403)
    data = request.get_json(silent=True) or request.form
    library_ctx = data.get("library_ctx", "global")
    lib_id = _resolve_library_ctx(user, library_ctx)
    folder_id = data.get("folder_id", store.ROOT_FOLDER_ID)
    metadata = score_metadata_from_data(data)
    try:
        meta = store.split_file_to_new_score(src_id, file_id, lib_id, folder_id, metadata, store.score_owner_id(user))
    except ValueError as e:
        return json_error(str(e))
    source = store.load_score_meta(src_id)
    return jsonify({"ok": True, "score": meta, "source_score": source})


@app.post("/scores/<score_id>/delete")
@login_required
def score_delete(score_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    data = request.get_json(silent=True) or {}
    library_id = data.get("library_id") or user["id"]
    if not policy.user_can_remove_score(user, meta, library_id):
        abort(403)
    if policy.user_can_hard_delete_score(user, meta, library_id):
        store.delete_score(score_id)
        return jsonify({"ok": True, "deleted": True})
    store.remove_score_from_library(library_id, score_id)
    return jsonify({"ok": True, "removed": True})


@app.route("/files/<score_id>/<stored_name>")
@login_required
def serve_file(score_id, stored_name):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        abort(404)
    if not policy.user_can_view_score(user, meta, view_library_id(user)):
        abort(403)
    if not any(f.get("stored_name") == stored_name for f in meta.get("files", [])):
        abort(404)
    ext = store.extension_of(stored_name)
    if ext not in store.MAIN_EXTENSIONS | store.AUX_EXTENSIONS:
        abort(403)
    try:
        path = store.stored_file_path(score_id, stored_name)
    except ValueError:
        abort(404)
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=False, download_name=stored_name)


@app.route("/scores/<score_id>/download")
@login_required
def score_download(score_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        abort(404)
    if not policy.user_can_view_score(user, meta, view_library_id(user)):
        abort(403)
    main = store.get_main_file(meta)
    if not main or not main.get("stored_name"):
        return json_error("No downloadable file", 404)
    if store.extension_of(main["stored_name"]) not in store.MAIN_EXTENSIONS:
        return json_error("No downloadable file", 404)
    try:
        path = store.stored_file_path(score_id, main["stored_name"])
    except ValueError:
        abort(404)
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=store.file_download_name(main))


def build_viewer_payload(user: dict, meta: dict, score_id: str, score_ids: list[str]) -> dict:
    files = []
    for f in meta.get("files", []):
        display = store.file_display_name(meta, f["id"])
        if f.get("role") == "main":
            display = VIEWER_MAIN_FILE_LABEL
        entry = {
            "id": f["id"],
            "display_name": display,
            "media": f.get("media"),
            "type_label": store.aux_file_type_label(f),
        }
        if f.get("media") == "youtube":
            entry["embed_url"] = store.youtube_embed_url(f.get("url", ""))
        elif f.get("stored_name"):
            entry["serve_url"] = append_scope_query_params(
                url_for("serve_file", score_id=score_id, stored_name=f["stored_name"])
            )
        files.append(entry)
    main = store.get_main_file(meta)
    selected_file_id = main["id"] if main else (files[0]["id"] if files else None)
    nav = {
        "index": None,
        "total": None,
        "prev_id": None,
        "next_id": None,
        "prev_title": None,
        "next_title": None,
    }
    if score_id in score_ids:
        idx = score_ids.index(score_id)
        nav["index"] = idx + 1
        nav["total"] = len(score_ids)
        if idx > 0:
            nav["prev_id"] = score_ids[idx - 1]
            prev_meta = store.load_score_meta(nav["prev_id"])
            nav["prev_title"] = prev_meta.get("title") if prev_meta else None
        if idx < len(score_ids) - 1:
            nav["next_id"] = score_ids[idx + 1]
            next_meta = store.load_score_meta(nav["next_id"])
            nav["next_title"] = next_meta.get("title") if next_meta else None
    download_url = append_scope_query_params(url_for("score_download", score_id=score_id)) if main else None
    return {
        "score": {
            "id": score_id,
            "title": meta.get("title"),
            "composer": meta.get("composer"),
            "year": meta.get("year", ""),
            "subtitle": store.score_subtitle_line(meta),
        },
        "files": files,
        "selected_file_id": selected_file_id,
        "nav": nav,
        "score_ids": score_ids,
        "download_url": download_url,
    }


@app.post("/scores/<score_id>/viewer-ctx")
@login_required
def mint_viewer_ctx(score_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    if not policy.user_can_view_score(user, meta, view_library_id(user)):
        abort(403)
    payload = request.get_json(silent=True) or {}
    score_ids = payload.get("score_ids")
    if not isinstance(score_ids, list):
        return json_error("Invalid score_ids", 400)
    try:
        lib_id = view_library_id(user)
    except HTTPException:
        abort(403)
    filtered = filter_viewable_score_ids(user, score_ids, score_id, lib_id)
    if not filtered:
        return json_error("Forbidden", 403)
    return jsonify({"ctx": encode_ctx(filtered, filtered.index(score_id))})


@app.get("/scores/<score_id>/viewer")
@login_required
def score_viewer_data(score_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    if not policy.user_can_view_score(user, meta, view_library_id(user)):
        abort(403)
    score_ids = resolve_score_view_ids(user, score_id)
    return jsonify(build_viewer_payload(user, meta, score_id, score_ids))


@app.get("/scores/<score_id>/notes")
@login_required
def score_notes_get(score_id):
    user = current_user()
    if notes_storage_for_user(user) != "server":
        abort(403)
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    if not policy.user_can_view_score(user, meta, view_library_id(user)):
        abort(403)
    return jsonify(store.get_score_notes(user["id"], score_id))


@app.put("/scores/<score_id>/notes")
@login_required
def score_notes_put(score_id):
    user = current_user()
    if notes_storage_for_user(user) != "server":
        abort(403)
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    if not policy.user_can_view_score(user, meta, view_library_id(user)):
        abort(403)
    payload = request.get_json(silent=True) or {}
    files = payload.get("files")
    if not isinstance(files, dict):
        return json_error("Invalid notes payload", 400)
    store.set_score_notes(user["id"], score_id, {"files": files})
    return jsonify({"ok": True})


@app.route("/scores/<score_id>/view")
@login_required
def score_view(score_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        abort(404)
    if not policy.user_can_view_score(user, meta, view_library_id(user)):
        abort(403)
    nav_query = score_view_nav_params_from_request()
    view_ctx = request.args.get("ctx", "")
    back_url = build_library_back_url(user, nav_query)
    main = store.get_main_file(meta)
    main_file_url = None
    if main and main.get("stored_name"):
        main_file_url = append_scope_query_params(
            url_for("serve_file", score_id=score_id, stored_name=main["stored_name"])
        )
    download_url = append_scope_query_params(url_for("score_download", score_id=score_id)) if main else None
    return render_template(
        "score_view.html",
        score=meta,
        view_ctx=view_ctx,
        view_nav=nav_query,
        back_url=back_url,
        download_url=download_url,
        main_file=main,
        main_file_url=main_file_url,
    )


def http_port() -> int:
    return int(os.environ.get("PORT", DEFAULT_HTTP_PORT))


def gunicorn_worker_count() -> int:
    return int(os.environ.get(GUNICORN_WORKERS_ENV, DEFAULT_GUNICORN_WORKERS))


def dev_mode_enabled(argv: list[str] | None = None) -> bool:
    if os.environ.get(DEV_MODE_ENV) == "1":
        return True
    args = argv if argv is not None else sys.argv[1:]
    return DEV_MODE_CLI_FLAG in args


def run_dev_server() -> None:
    try:
        app.run(host=GUNICORN_BIND_HOST, port=http_port(), debug=True)
    except KeyboardInterrupt:
        raise SystemExit(0) from None


def run_production_server() -> None:
    cmd = [
        sys.executable,
        "-m",
        "gunicorn",
        "-w",
        str(gunicorn_worker_count()),
        "-b",
        f"{GUNICORN_BIND_HOST}:{http_port()}",
        "app:app",
    ]
    proc = subprocess.Popen(cmd)
    try:
        status = proc.wait()
    except KeyboardInterrupt:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=GUNICORN_SHUTDOWN_WAIT_SEC)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        status = 0
    raise SystemExit(status)


if __name__ == "__main__":
    store.ensure_data_ready(password_secret())
    if dev_mode_enabled():
        run_dev_server()
    else:
        run_production_server()
