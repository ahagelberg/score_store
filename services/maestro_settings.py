"""Maestro library config and appearance updates from HTTP forms."""

from werkzeug.datastructures import FileStorage, ImmutableMultiDict

import store

FORM_CHECKBOX_ON = "1"
FORM_REMOVE_LOGOTYPE = "remove_logotype"
FORM_ENABLE_PRINTING = "enable_printing"
FORM_ENABLE_DOWNLOAD = "enable_download"
FORM_SITE_TITLE = "site_title"
FORM_SHOW_SITE_TITLE = "show_site_title"
FORM_THEME_CSS_TEXT = "theme_css_text"
FORM_THEME_CSS_FILE = "theme_css"
FORM_LOGOTYPE = "logotype"


def apply_library_config(maestro_username: str, form: ImmutableMultiDict) -> dict:
    cfg = store.load_maestro_config(maestro_username)
    cfg[FORM_ENABLE_PRINTING] = store.form_show_site_title_checked(form.get(FORM_ENABLE_PRINTING))
    cfg[FORM_ENABLE_DOWNLOAD] = store.form_show_site_title_checked(form.get(FORM_ENABLE_DOWNLOAD))
    store.save_maestro_config(maestro_username, cfg)
    return cfg


def save_logotype_upload(maestro_username: str, upload: FileStorage | None) -> str | None:
    if not upload or not upload.filename:
        return None
    ext = store.extension_of(upload.filename)
    if ext not in store.LOGOTYPE_EXTENSIONS:
        return None
    dest = (
        store.maestro_data_dir(maestro_username)
        / store.MAESTRO_ASSETS_DIRNAME
        / f"{store.LOGOTYPE_STORED_BASENAME}.{ext}"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    upload.save(dest)
    return f"{store.MAESTRO_ASSETS_DIRNAME}/{store.LOGOTYPE_STORED_BASENAME}.{ext}"


def save_theme_from_form(maestro_username: str, form: ImmutableMultiDict, files) -> None:
    theme_text = form.get(FORM_THEME_CSS_TEXT, "")
    if theme_text.strip():
        store.maestro_theme_path(maestro_username).write_text(theme_text, encoding="utf-8")
    theme_upload = files.get(FORM_THEME_CSS_FILE)
    if theme_upload and theme_upload.filename:
        theme_upload.save(store.maestro_theme_path(maestro_username))


def apply_appearance(
    maestro_username: str,
    title_fallback: str,
    form: ImmutableMultiDict,
    files,
    *,
    preserve_site_title_if_empty: bool = False,
) -> dict:
    cfg = store.load_maestro_config(maestro_username)
    site_title = form.get(FORM_SITE_TITLE, "").strip()
    if site_title:
        cfg[FORM_SITE_TITLE] = site_title
    elif not preserve_site_title_if_empty:
        cfg[FORM_SITE_TITLE] = title_fallback
    cfg[FORM_SHOW_SITE_TITLE] = store.form_show_site_title_checked(form.get(FORM_SHOW_SITE_TITLE))
    save_theme_from_form(maestro_username, form, files)
    logotype_rel = save_logotype_upload(maestro_username, files.get(FORM_LOGOTYPE))
    if logotype_rel:
        cfg["logotype"] = logotype_rel
    if form.get(FORM_REMOVE_LOGOTYPE) == FORM_CHECKBOX_ON:
        cfg["logotype"] = ""
    store.save_maestro_config(maestro_username, cfg)
    return cfg
