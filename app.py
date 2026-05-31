"""Score portal Flask application."""

import json
import os
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
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
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import HTTPException

import store

APP_TITLE = "Score Store"
UPLOAD_SCORE_LABEL = "Upload score"
SCORE_LIST_TITLE = "Scores"
SESSION_USER_KEY = "user_id"
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


def bootstrap_maestro() -> None:
    username = os.environ.get("BOOTSTRAP_MAESTRO_USER")
    password = os.environ.get("BOOTSTRAP_MAESTRO_PASSWORD")
    if not username or not password:
        return
    users = store.load_users()
    if any(u["role"] == "maestro" for u in users):
        return
    users.append({
        "id": store.new_id("u-"),
        "display_name": "Maestro",
        "username": username.strip().lower(),
        "password_hash": generate_password_hash(password),
        "role": "maestro",
    })
    store.save_users(users)
    store.load_library(store.GLOBAL_LIBRARY_ID)


def encode_ctx(score_ids: list[str], index: int) -> str:
    return _ctx_serializer().dumps({"ids": score_ids, "i": index})


def decode_ctx(token: str) -> tuple[list[str], int] | None:
    try:
        data = _ctx_serializer().loads(token)
        return data["ids"], int(data["i"])
    except (BadSignature, KeyError, TypeError, ValueError):
        return None


def library_id_for_user(user: dict, ctx: str | None = None) -> str:
    if ctx and ctx.startswith("user:"):
        if user["role"] == "maestro":
            return ctx.split(":", 1)[1]
    if user["role"] == "maestro" and request.args.get("library"):
        return request.args.get("library")
    if user["role"] == "maestro":
        return store.GLOBAL_LIBRARY_ID
    return user["id"]


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


def resolve_score_view_ids(user: dict, score_id: str) -> list[str]:
    ctx_token = request.args.get("ctx")
    if ctx_token:
        decoded = decode_ctx(ctx_token)
        if decoded:
            score_ids, _ = decoded
            if score_id in score_ids:
                return score_ids
    nav = score_view_nav_params_from_request()
    library_ctx = nav.get("lib")
    if not library_ctx:
        library_ctx = "global" if user["role"] == "maestro" else f"user-{user['id']}"
    try:
        library_id = _resolve_library_ctx(user, library_ctx)
    except HTTPException:
        return []
    scores = library_scores(library_id, nav.get("q", ""), nav.get("tag") or None)
    return [score["id"] for score in scores if score.get("id")]


def build_score_view_url(score_id: str, score_ids: list[str], nav_query: dict) -> str:
    params = dict(nav_query)
    if score_id in score_ids:
        params["ctx"] = encode_ctx(score_ids, score_ids.index(score_id))
    return url_for("score_view", score_id=score_id, **params)


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
    }
    panel["view_nav"] = score_view_nav_params_from_panel(panel)
    return panel


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


_bootstrap_done = False
_SETUP_EXEMPT = frozenset({"setup", "static"})


@app.before_request
def _setup_and_bootstrap():
    global _bootstrap_done
    if request.endpoint in _SETUP_EXEMPT:
        return
    if store.env_bootstrap_configured() and not _bootstrap_done:
        store.ensure_data_dirs()
        bootstrap_maestro()
        _bootstrap_done = True
    if store.needs_setup():
        return redirect(url_for("setup"))
    store.ensure_data_dirs()
    if not _bootstrap_done:
        bootstrap_maestro()
        _bootstrap_done = True


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
                store.complete_setup(username, password, Path(data_dir), generate_password_hash)
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


@app.context_processor
def inject_globals():
    return {"app_title": APP_TITLE, "current_user": current_user()}


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = store.get_user_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            session[SESSION_USER_KEY] = user["id"]
            nxt = request.args.get("next") or url_for("index")
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
    is_choir = user["role"] == "choir"
    can_upload = user["role"] == "singer"
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
        can_upload=can_upload,
        can_manage_folders=can_upload and not is_choir,
        panel_class="desktop-panel-page",
    )
    return render_template(
        "library.html",
        library_id=lib_id,
        library_panel=library_panel,
        can_upload=can_upload,
        is_choir=is_choir,
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
        can_upload=True,
        can_manage_folders=True,
        draggable_score=True,
    )
    user_library_panel = None
    if selected_user and user_lib:
        user_library_panel = build_library_panel(
            panel_title="User library",
            lib=user_lib,
            scores=user_scores,
            all_tags=user_tags,
            library_ctx=f"user-{selected_user}",
            nav_endpoint="maestro",
            preserve=user_preserve,
            query=query,
            active_tag=tag,
            can_upload=False,
            can_manage_folders=True,
            draggable_score=True,
            assign_user=selected_user,
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
    uid = store.new_id("u-")
    users.append({
        "id": uid,
        "display_name": display_name,
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": role,
    })
    store.save_users(users)
    store.load_library(uid)
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
        user["password_hash"] = generate_password_hash(password)
    users = store.load_users()
    for i, u in enumerate(users):
        if u["id"] == user_id:
            users[i] = user
            break
    store.save_users(users)
    flash("User updated", "success")
    return redirect(url_for("maestro", user=request.args.get("user")))


@app.post("/maestro/users/<user_id>/delete")
@role_required("maestro")
def maestro_user_delete(user_id):
    users = store.load_users()
    target = store.get_user(user_id)
    if not target:
        abort(404)
    users = [u for u in users if u["id"] != user_id]
    store.save_users(users)
    flash("User deleted", "success")
    return redirect(url_for("maestro"))


@app.post("/maestro/assign")
@role_required("maestro")
def maestro_assign():
    data = request.get_json(silent=True) or {}
    score_id = data.get("score_id")
    user_id = data.get("user_id")
    assign = data.get("assign", True)
    if not score_id or not user_id:
        return json_error("score_id and user_id required")
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Score not found", 404)
    lib = store.load_library(user_id)
    if assign:
        if score_id not in lib["score_order"]:
            lib["score_order"].append(score_id)
        lib["score_folders"].setdefault(score_id, store.ROOT_FOLDER_ID)
        assigned = set(meta.get("assigned_user_ids", []))
        assigned.add(user_id)
        meta["assigned_user_ids"] = list(assigned)
        store.save_score_meta(score_id, meta)
    else:
        store.remove_score_from_library(user_id, score_id)
        assigned = [x for x in meta.get("assigned_user_ids", []) if x != user_id]
        meta["assigned_user_ids"] = assigned
        store.save_score_meta(score_id, meta)
    store.save_library(user_id, lib)
    return jsonify({"ok": True})


@app.post("/library/<library_ctx>/folders/new")
@login_required
def folder_new(library_ctx):
    user = current_user()
    lib_id = _resolve_library_ctx(user, library_ctx)
    if not _can_manage_library(user, lib_id):
        abort(403)
    name = request.form.get("name", "").strip()
    if not name:
        return json_error("Name required")
    lib = store.load_library(lib_id)
    fid = store.new_id("fld-")
    lib["folders"].append({"id": fid, "name": name})
    store.save_library(lib_id, lib)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"id": fid, "name": name})
    return redirect(request.referrer or url_for("index"))


@app.post("/library/<library_ctx>/folders/<folder_id>/delete")
@login_required
def folder_delete(library_ctx, folder_id):
    user = current_user()
    lib_id = _resolve_library_ctx(user, library_ctx)
    if not _can_manage_library(user, lib_id):
        abort(403)
    if folder_id == store.ROOT_FOLDER_ID:
        return json_error("Cannot delete root folder")
    lib = store.load_library(lib_id)
    lib["folders"] = [f for f in lib["folders"] if f["id"] != folder_id]
    for sid, fid in list(lib["score_folders"].items()):
        if fid == folder_id:
            lib["score_folders"][sid] = store.ROOT_FOLDER_ID
    store.save_library(lib_id, lib)
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


def _can_manage_library(user: dict, lib_id: str) -> bool:
    if user["role"] == "maestro":
        return True
    return user["role"] == "singer" and lib_id == user["id"]


@app.post("/library/<library_ctx>/scores/new")
@login_required
def score_new(library_ctx):
    user = current_user()
    lib_id = _resolve_library_ctx(user, library_ctx)
    if not _can_manage_library(user, lib_id):
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
        meta = store.create_score_from_upload(lib_id, folder_id, upload, metadata, user["id"])
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
    if not store.user_can_edit_score(user, meta):
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
    if not meta or not store.user_can_edit_score(user, meta):
        abort(403)
    data = request.get_json(silent=True) or request.form
    folder_id = data.get("folder_id", store.ROOT_FOLDER_ID)
    lib = store.load_library(lib_id)
    if folder_id not in {f["id"] for f in lib.get("folders", [])}:
        return json_error("Unknown folder")
    store.assign_score_to_folder(lib_id, score_id, folder_id)
    return jsonify({"ok": True})


@app.post("/scores/<score_id>/files")
@login_required
def score_add_file(score_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    if not store.user_can_edit_score(user, meta):
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
    if not meta or not store.user_can_edit_score(user, meta):
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
    if not meta or not store.user_can_edit_score(user, meta):
        abort(403)
    data = request.get_json(silent=True) or request.form
    try:
        f = store.update_file_name(score_id, file_id, data.get("name", ""))
    except ValueError as e:
        return json_error(str(e))
    return jsonify({"ok": True, "file": file_json(f)})


@app.post("/scores/<score_id>/files/<file_id>/alias")
@login_required
def score_file_alias(score_id, file_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    if not store.user_can_view_score(user, meta, user["id"]):
        abort(403)
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    lib = store.load_library(user["id"])
    lib.setdefault("file_aliases", {}).setdefault(user["id"], {})[file_id] = name
    store.save_library(user["id"], lib)
    return jsonify({"ok": True})


@app.post("/scores/<src_id>/files/<file_id>/move")
@login_required
def score_file_move(src_id, file_id):
    user = current_user()
    src = store.load_score_meta(src_id)
    if not src or not store.user_can_edit_score(user, src):
        abort(403)
    data = request.get_json(silent=True) or {}
    dst_id = data.get("to_score_id")
    if not dst_id:
        return json_error("to_score_id required")
    dst = store.load_score_meta(dst_id)
    if not dst or not store.user_can_edit_score(user, dst):
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
    if not src or not store.user_can_edit_score(user, src):
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
        meta = store.split_file_to_new_score(src_id, file_id, lib_id, folder_id, metadata, user["id"])
    except ValueError as e:
        return json_error(str(e))
    return jsonify({"ok": True, "score": meta})


@app.post("/scores/<score_id>/delete")
@login_required
def score_delete(score_id):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        return json_error("Not found", 404)
    if user["role"] == "maestro" or meta.get("owner_id") == user["id"]:
        store.delete_score(score_id)
        for lib_file in store.LIBRARIES_DIR.glob("*.json"):
            store.remove_score_from_library(lib_file.stem, score_id)
        return jsonify({"ok": True})
    abort(403)


@app.route("/files/<score_id>/<stored_name>")
@login_required
def serve_file(score_id, stored_name):
    user = current_user()
    meta = store.load_score_meta(score_id)
    if not meta:
        abort(404)
    if not store.user_can_view_score(user, meta, user["id"]):
        abort(403)
    if not any(f.get("stored_name") == stored_name for f in meta.get("files", [])):
        abort(404)
    ext = store.extension_of(stored_name)
    if ext not in store.MAIN_EXTENSIONS | store.AUX_EXTENSIONS:
        abort(403)
    path = store.stored_file_path(score_id, stored_name)
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
    if not store.user_can_view_score(user, meta, user["id"]):
        abort(403)
    main = store.get_main_file(meta)
    if not main or not main.get("stored_name"):
        return json_error("No downloadable file", 404)
    if store.extension_of(main["stored_name"]) not in store.MAIN_EXTENSIONS:
        return json_error("No downloadable file", 404)
    path = store.stored_file_path(score_id, main["stored_name"])
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
            if isinstance(score_ids, list) and score_id in score_ids:
                return score_ids
    return resolve_score_view_ids(user, score_id)


def build_viewer_payload(user: dict, meta: dict, score_id: str, score_ids: list[str]) -> dict:
    lib_id = user["id"] if user["role"] != "maestro" else store.GLOBAL_LIBRARY_ID
    files = []
    for f in meta.get("files", []):
        display = store.file_display_name(meta, f["id"], user["id"], lib_id)
        entry = {
            "id": f["id"],
            "display_name": display,
            "media": f.get("media"),
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
    if not store.user_can_view_score(user, meta, user["id"]):
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
    if not store.user_can_view_score(user, meta, user["id"]):
        abort(403)
    nav_query = score_view_nav_params_from_request()
    back_url = build_library_back_url(user, nav_query)
    sep = "&" if "?" in back_url else "?"
    return redirect(f"{back_url}{sep}view_score={score_id}")


if __name__ == "__main__":
    if not store.needs_setup():
        store.ensure_data_dirs()
        bootstrap_maestro()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
