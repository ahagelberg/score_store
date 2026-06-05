"""Score portal Flask application."""

import json
import os
import secrets
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from itsdangerous import BadSignature, URLSafeSerializer
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
SWIPE_THRESHOLD_PX = 50
SCORE_VIEW_NAV_KEYS = ("lib", "q", "tag", "user")
LIBRARY_CTX_USER_PREFIX = "user-"
LIBRARY_BACK_KEYS_MAESTRO = ("q", "tag", "user")
LIBRARY_BACK_KEYS_INDEX = ("q", "tag")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
if os.environ.get("USE_HTTPS") == "1":
    app.config["SESSION_COOKIE_SECURE"] = True


def _ctx_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(app.secret_key, salt=CTX_TOKEN_SALT)


def current_user() -> dict | None:
    uid = session.get(SESSION_USER_KEY)
    if not uid:
        return None
    return store.get_user(uid)


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
            user = current_user()
            if user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def password_secret() -> str:
    return app.secret_key


def bootstrap_maestro() -> None:
    username = os.environ.get("BOOTSTRAP_MAESTRO_USER")
    password = os.environ.get("BOOTSTRAP_MAESTRO_PASSWORD")
    if not username or not password:
        return
    users = store.load_users()
    if any(u["role"] == "maestro" for u in users):
        return
    user = {
        "id": store.user_id_from_username(username.strip().lower()),
        "display_name": "Maestro",
        "username": username.strip().lower(),
        "role": store.MAESTRO_ROLE,
    }
    store.set_user_password(user, password, password_secret())
    users.append(user)
    store.save_users(users)
    store.ensure_library(store.GLOBAL_LIBRARY_ID)


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


def library_scores(library_id: str, query: str, tag: str | None) -> list[dict]:
    return store.scores_for_library_sorted(library_id, query, tag)


def score_view_nav_params_from_request() -> dict:
    return {key: request.args.get(key) for key in SCORE_VIEW_NAV_KEYS if request.args.get(key)}


def score_view_nav_params_from_panel(library_panel: dict) -> dict:
    params = {"lib": library_panel["library_ctx"]}
    if library_panel.get("query"):
        params["q"] = library_panel["query"]
    if library_panel.get("active_tag"):
        params["tag"] = library_panel["active_tag"]
    for key, value in (library_panel.get("preserve") or {}).items():
        if value and key not in params:
            params[key] = value
    return params


def view_library_id(user: dict) -> str:
    nav = score_view_nav_params_from_request()
    library_ctx = nav.get("lib")
    if not library_ctx:
        library_ctx = "global" if user["role"] == "maestro" else f"{LIBRARY_CTX_USER_PREFIX}{user['id']}"
    return _resolve_library_ctx(user, library_ctx)


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
    if user["role"] == "maestro":
        endpoint = "maestro"
        params = {key: nav_query[key] for key in LIBRARY_BACK_KEYS_MAESTRO if nav_query.get(key)}
        library_ctx = nav_query.get("lib", "")
        if library_ctx.startswith(LIBRARY_CTX_USER_PREFIX) and "user" not in params:
            params["user"] = library_ctx[len(LIBRARY_CTX_USER_PREFIX):]
    else:
        endpoint = "index"
        params = {key: nav_query[key] for key in LIBRARY_BACK_KEYS_INDEX if nav_query.get(key)}
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


def library_id_from_ctx(library_ctx: str) -> str:
    if library_ctx == "global":
        return store.GLOBAL_LIBRARY_ID
    if library_ctx.startswith(LIBRARY_CTX_USER_PREFIX):
        return library_ctx[len(LIBRARY_CTX_USER_PREFIX):]
    return library_ctx


@app.template_global()
def user_can_edit_score(user, score):
    return policy.user_can_edit_score(user, score)


@app.template_global()
def user_can_hard_delete_score(user, score):
    return policy.user_can_hard_delete_score(user, score)


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
def score_download_url(score_id):
    return url_for("score_download", score_id=score_id)


@app.template_global()
def build_nav_url(endpoint, query="", active_tag="", preserve=None):
    params = dict(preserve or {})
    if query:
        params["q"] = query
    if active_tag:
        params["tag"] = active_tag
    return url_for(endpoint, **params)


@app.template_global()
def user_select_url(user_id, query="", active_tag=""):
    return build_nav_url("maestro", query=query, active_tag=active_tag, preserve={"user": user_id})


@app.template_global()
def csrf_token():
    return ensure_csrf_token()


_bootstrap_done = False
_storage_init_done = False
_SETUP_EXEMPT = frozenset({"setup", "static"})


@app.before_request
def _setup_and_bootstrap():
    global _bootstrap_done, _storage_init_done
    if request.endpoint in _SETUP_EXEMPT:
        return
    if not _storage_init_done:
        store.ensure_data_dirs()
        store.run_storage_migrations()
        _storage_init_done = True
    if store.env_bootstrap_configured() and not _bootstrap_done:
        bootstrap_maestro()
        _bootstrap_done = True
    if store.needs_setup():
        return redirect(url_for("setup"))
    if not _bootstrap_done:
        bootstrap_maestro()
        _bootstrap_done = True


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
        username = request.form.get("username", store.DEFAULT_MAESTRO_USERNAME)
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
        default_username=store.DEFAULT_MAESTRO_USERNAME,
        default_data_dir=store.default_setup_data_dir_display(),
        password_min_len=store.SETUP_PASSWORD_MIN_LEN,
    )


@app.template_filter("user_password_display")
def user_password_display(user):
    return store.password_for_display(user)


@app.context_processor
def inject_globals():
    user = current_user()
    browser_title = APP_TITLE
    if user:
        browser_title = f"{APP_TITLE} - {user['display_name']}"
    return {"app_title": APP_TITLE, "browser_title": browser_title, "current_user": user, "password_min_len": store.SETUP_PASSWORD_MIN_LEN}


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = store.get_user_by_username(username)
        secret = password_secret()
        if user and store.verify_user_password(user, password, secret):
            session[SESSION_USER_KEY] = user["id"]
            nxt = safe_redirect_target(request.args.get("next"), url_for("index"))
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
    if user["role"] == "maestro":
        return redirect(url_for("maestro"))
    lib_id = user["id"]
    lib = store.load_library(lib_id)
    query = request.args.get("q", "")
    tag = request.args.get("tag")
    scores = library_scores(lib_id, query, tag)
    tags = store.collect_tags(lib.get("score_order", []))
    caps = policy.library_panel_capabilities(user, lib_id)
    library_panel = build_library_panel(
        panel_title="My library",
        lib=lib,
        scores=scores,
        all_tags=tags,
        library_ctx=f"user-{lib_id}",
        nav_endpoint="index",
        preserve={},
        query=query,
        active_tag=tag,
        can_upload=caps["can_upload"],
        can_manage_folders=caps["can_manage_folders"],
        panel_class="desktop-panel-page",
    )
    return render_template(
        "library.html",
        library_id=lib_id,
        library_panel=library_panel,
        can_upload=caps["can_upload"],
        is_choir=caps["is_choir"],
    )


@app.route("/maestro")
@role_required("maestro")
def maestro():
    user = current_user()
    selected_user = request.args.get("user")
    lib_global = store.load_library(store.GLOBAL_LIBRARY_ID)
    query = request.args.get("q", "")
    tag = request.args.get("tag")
    scores = library_scores(store.GLOBAL_LIBRARY_ID, query, tag)
    tags = store.collect_tags(lib_global.get("score_order", []))
    users = [u for u in store.load_users() if u["role"] != "maestro"]
    user_lib = None
    user_scores = []
    user_tags = []
    if selected_user:
        user_lib = store.load_library(selected_user)
        user_scores = library_scores(selected_user, query, tag)
        user_tags = store.collect_tags(user_lib.get("score_order", []))
    global_preserve = {}
    user_preserve = {}
    if selected_user:
        global_preserve["user"] = selected_user
        user_preserve["user"] = selected_user
    global_caps = policy.library_panel_capabilities(user, store.GLOBAL_LIBRARY_ID)
    global_library_panel = build_library_panel(
        panel_title="Global library",
        lib=lib_global,
        scores=scores,
        all_tags=tags,
        library_ctx="global",
        nav_endpoint="maestro",
        preserve=global_preserve,
        query=query,
        active_tag=tag,
        can_upload=global_caps["can_upload"],
        can_manage_folders=global_caps["can_manage_folders"],
        draggable_score=True,
        disk_usage=store.disk_usage_stats(),
    )
    user_library_panel = None
    if selected_user and user_lib:
        selected = store.get_user(selected_user)
        user_panel_title = user_lib.get("display_name") or (selected["display_name"] if selected else "User library")
        user_caps = policy.library_panel_capabilities(user, selected_user)
        user_library_panel = build_library_panel(
            panel_title=user_panel_title,
            lib=user_lib,
            scores=user_scores,
            all_tags=user_tags,
            library_ctx=f"user-{selected_user}",
            nav_endpoint="maestro",
            preserve=user_preserve,
            query=query,
            active_tag=tag,
            can_upload=False,
            can_manage_folders=user_caps["can_manage_folders"],
            draggable_score=True,
            assign_user=selected_user,
            summary_opens_viewer=True,
        )
    return render_template(
        "maestro.html",
        global_library_panel=global_library_panel,
        user_library_panel=user_library_panel,
        query=query,
        active_tag=tag,
        users=users,
        selected_user=selected_user,
    )


@app.route("/maestro/mobile")
@role_required("maestro")
def maestro_mobile():
    lib = store.load_library(store.GLOBAL_LIBRARY_ID)
    query = request.args.get("q", "")
    tag = request.args.get("tag")
    scores = store.scores_for_library(store.GLOBAL_LIBRARY_ID, None, query, tag)
    users = [u for u in store.load_users() if u["role"] != "maestro"]
    all_meta = {s["id"]: s for s in scores}
    for sid in lib.get("score_order", []):
        if sid not in all_meta:
            m = store.load_score_meta(sid)
            if m and store.score_matches_filter(m, query, tag):
                all_meta[sid] = m
    tags = store.collect_tags(lib.get("score_order", []))
    scores_list = list(all_meta.values())
    user_library_scores = {u["id"]: store.user_library_score_ids(u["id"]) for u in users}
    mobile_panel = build_library_panel(
        panel_title="Share scores",
        lib=lib,
        scores=scores_list,
        all_tags=tags,
        library_ctx="global",
        nav_endpoint="maestro_mobile",
        preserve={},
        query=query,
        active_tag=tag,
    )
    return render_template(
        "maestro_mobile.html",
        scores=scores_list,
        users=users,
        user_library_scores=user_library_scores,
        library_panel=mobile_panel,
    )


@app.post("/maestro/users/new")
@role_required("maestro")
def maestro_user_new():
    display_name = request.form.get("display_name", "").strip()
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "singer")
    if not display_name or not username or not password:
        flash("All fields required", "error")
        return redirect(url_for("maestro"))
    if role not in ("singer", "choir", "maestro"):
        flash("Invalid role", "error")
        return redirect(url_for("maestro"))
    if store.get_user_by_username(username):
        flash("Username taken", "error")
        return redirect(url_for("maestro"))
    users = store.load_users()
    uid = store.user_id_from_username(username)
    user = {
        "id": uid,
        "display_name": display_name,
        "username": username,
        "role": role,
    }
    store.set_user_password(user, password, password_secret())
    users.append(user)
    store.save_users(users)
    store.ensure_library(uid)
    flash("User created", "success")
    return redirect(url_for("maestro"))


@app.post("/maestro/users/<user_id>/edit")
@role_required("maestro")
def maestro_user_edit(user_id):
    user = store.get_user(user_id)
    if not user:
        abort(404)
    display_name = request.form.get("display_name", "").strip()
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", user["role"])
    if not display_name or not username:
        flash("Display name and username required", "error")
        return redirect(url_for("maestro"))
    existing = store.get_user_by_username(username)
    if existing and existing["id"] != user_id:
        flash("Username taken", "error")
        return redirect(url_for("maestro"))
    user["display_name"] = display_name
    user["username"] = username
    user["role"] = role
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
@role_required("maestro")
def maestro_user_delete(user_id):
    actor = current_user()
    if actor["id"] == user_id:
        flash("Cannot delete your own account", "error")
        return redirect(url_for("maestro"))
    target = store.get_user(user_id)
    if not target:
        abort(404)
    if target["role"] == "maestro":
        maestro_count = sum(1 for u in store.load_users() if u["role"] == "maestro")
        if maestro_count <= 1:
            flash("Cannot delete the last maestro", "error")
            return redirect(url_for("maestro", user=request.args.get("user")))
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


@app.post("/maestro/password")
@role_required("maestro")
def maestro_change_password():
    user = current_user()
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("new_password_confirm", "")
    if not current_password or not new_password:
        flash("Current and new password required", "error")
        return redirect(request.referrer or url_for("maestro"))
    if new_password != confirm_password:
        flash("New passwords do not match", "error")
        return redirect(request.referrer or url_for("maestro"))
    if len(new_password) < store.SETUP_PASSWORD_MIN_LEN:
        flash(f"Password must be at least {store.SETUP_PASSWORD_MIN_LEN} characters", "error")
        return redirect(request.referrer or url_for("maestro"))
    stored = store.get_user(user["id"])
    secret = password_secret()
    if not stored or not store.verify_user_password(stored, current_password, secret):
        flash("Current password is wrong", "error")
        return redirect(request.referrer or url_for("maestro"))
    store.set_user_password(stored, new_password, secret)
    users = store.load_users()
    for i, entry in enumerate(users):
        if entry["id"] == stored["id"]:
            users[i] = stored
            break
    store.save_users(users)
    flash("Password updated", "success")
    return redirect(request.referrer or url_for("maestro"))


def _user_handout_context(user_id: str) -> dict:
    user = store.get_user(user_id)
    if not user or store.is_maestro_role(user.get("role", "")):
        abort(404)
    site_url = request.url_root.rstrip("/")
    password_plain = store.password_for_display(user)
    return user_handout.handout_context(user, site_url, APP_TITLE, password_plain)


@app.get("/maestro/users/<user_id>/handout")
@role_required("maestro")
def maestro_user_handout(user_id):
    ctx = _user_handout_context(user_id)
    return render_template("partials/user_handout_content.html", **ctx)


@app.get("/maestro/users/<user_id>/handout.pdf")
@role_required("maestro")
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
@role_required("maestro")
def maestro_assign():
    user = current_user()
    if not policy.user_can_assign_scores(user):
        abort(403)
    data = request.get_json(silent=True) or {}
    score_id = data.get("score_id")
    user_id = data.get("user_id")
    assign = data.get("assign", True)
    if not score_id or not user_id:
        return json_error("score_id and user_id required")
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
    return redirect(request.referrer or url_for("index"))


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
        if user["role"] != "maestro":
            abort(403)
        return store.GLOBAL_LIBRARY_ID
    if library_ctx.startswith("user-"):
        uid = library_ctx[5:]
        if user["role"] == "maestro" or user["id"] == uid:
            return uid
        abort(403)
    if user["role"] == "maestro":
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
    metadata = {
        "title": request.form.get("title", ""),
        "composer": request.form.get("composer", ""),
        "arranger": request.form.get("arranger", ""),
        "description": request.form.get("description", ""),
        "tags": request.form.get("tags", "[]"),
    }
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
    metadata = {
        "title": data.get("title", ""),
        "composer": data.get("composer", ""),
        "arranger": data.get("arranger", ""),
        "description": data.get("description", ""),
        "tags": data.get("tags", "[]"),
    }
    try:
        meta = store.update_score_metadata(score_id, metadata)
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
    metadata = {
        "title": data.get("title", ""),
        "composer": data.get("composer", ""),
        "arranger": data.get("arranger", ""),
        "description": data.get("description", ""),
        "tags": data.get("tags", "[]"),
    }
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
    if not policy.user_can_remove_score(user, meta, user["id"]):
        abort(403)
    if policy.user_can_hard_delete_score(user, meta):
        store.delete_score(score_id)
        return jsonify({"ok": True, "deleted": True})
    store.remove_score_from_library(user["id"], score_id)
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
    from flask import send_file
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
    from flask import send_file
    return send_file(path, as_attachment=True, download_name=store.file_download_name(main))


def score_ids_for_viewer(user: dict, score_id: str) -> list[str]:
    raw = request.args.get("score_ids")
    if raw:
        try:
            score_ids = json.loads(raw)
        except json.JSONDecodeError:
            score_ids = None
        else:
            if isinstance(score_ids, list):
                try:
                    lib_id = view_library_id(user)
                except HTTPException:
                    lib_id = None
                if lib_id is not None:
                    filtered = filter_viewable_score_ids(user, score_ids, score_id, lib_id)
                    if filtered:
                        return filtered
    return resolve_score_view_ids(user, score_id)


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
            entry["serve_url"] = url_for("serve_file", score_id=score_id, stored_name=f["stored_name"])
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
    download_url = url_for("score_download", score_id=score_id) if main else None
    return {
        "score": {
            "id": score_id,
            "title": meta.get("title"),
            "composer": meta.get("composer"),
        },
        "files": files,
        "selected_file_id": selected_file_id,
        "nav": nav,
        "score_ids": score_ids,
        "download_url": download_url,
    }


@app.get("/scores/<score_id>/viewer")
@login_required
def score_viewer_data(score_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    if not policy.user_can_view_score(user, meta, view_library_id(user)):
        abort(403)
    score_ids = score_ids_for_viewer(user, score_id)
    return jsonify(build_viewer_payload(user, meta, score_id, score_ids))


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
    score_ids = score_ids_for_viewer(user, score_id)
    back_url = build_library_back_url(user, nav_query)
    main = store.get_main_file(meta)
    main_file_url = None
    if main and main.get("stored_name"):
        main_file_url = url_for("serve_file", score_id=score_id, stored_name=main["stored_name"])
    download_url = url_for("score_download", score_id=score_id) if main else None
    return render_template(
        "score_view.html",
        score=meta,
        score_ids=score_ids,
        view_nav=nav_query,
        back_url=back_url,
        download_url=download_url,
        main_file=main,
        main_file_url=main_file_url,
    )


if __name__ == "__main__":
    if not store.needs_setup():
        store.ensure_data_dirs()
        store.run_storage_migrations()
        bootstrap_maestro()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
