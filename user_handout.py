"""Printable account handout for singers and choir accounts."""

from io import BytesIO
from pathlib import Path

from fpdf import FPDF

APP_ROOT = Path(__file__).resolve().parent
FONT_CANDIDATES = (
    APP_ROOT / "static" / "fonts" / "DejaVuSans.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
)
FONT_BOLD_CANDIDATES = (
    APP_ROOT / "static" / "fonts" / "DejaVuSans-Bold.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
)

PDF_FONT_NAME = "DejaVuSans"
PDF_MARGIN_MM = 20
PDF_TITLE_SIZE = 18
PDF_HEADING_SIZE = 14
PDF_BODY_SIZE = 12
PDF_LABEL_SIZE = 11
PDF_LINE_HEIGHT = 7
PDF_SECTION_GAP = 4

USER_ROLE_LABELS = {
    "singer": "Singer",
    "choir": "Choir",
    "maestro": "Maestro",
}


def user_role_label(role: str) -> str:
    return USER_ROLE_LABELS.get(role, role)


def handout_context(user: dict, site_url: str, app_title: str, password_plain: str) -> dict:
    return {
        "app_title": app_title,
        "display_name": user.get("display_name", ""),
        "username": user.get("username", ""),
        "role_label": user_role_label(user.get("role", "")),
        "password": password_plain,
        "password_available": bool(password_plain),
        "site_url": site_url,
    }


def _font_path() -> Path:
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("DejaVuSans.ttf not found")


def _font_bold_path() -> Path:
    for candidate in FONT_BOLD_CANDIDATES:
        if candidate.is_file():
            return candidate
    return _font_path()


def _pdf_filename(display_name: str) -> str:
    stem = display_name.strip() or "account"
    safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in stem)
    return f"{safe.strip()} account.pdf"


def build_handout_pdf(context: dict) -> tuple[bytes, str]:
    pdf = FPDF()
    pdf.set_margins(PDF_MARGIN_MM, PDF_MARGIN_MM, PDF_MARGIN_MM)
    pdf.set_auto_page_break(auto=True, margin=PDF_MARGIN_MM)
    pdf.add_page()
    font_path = _font_path()
    font_bold_path = _font_bold_path()
    pdf.add_font(PDF_FONT_NAME, "", str(font_path))
    pdf.add_font(PDF_FONT_NAME, "B", str(font_bold_path))
    pdf.set_font(PDF_FONT_NAME, "B", PDF_TITLE_SIZE)
    pdf.cell(0, PDF_LINE_HEIGHT + 2, context["app_title"], new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(PDF_SECTION_GAP)
    pdf.set_font(PDF_FONT_NAME, "B", PDF_HEADING_SIZE)
    pdf.cell(0, PDF_LINE_HEIGHT, "Your account", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(PDF_SECTION_GAP + 2)
    rows = [
        ("Name", context["display_name"]),
        ("Username", context["username"]),
    ]
    if context["password_available"]:
        rows.append(("Password", context["password"]))
    rows.extend([
        ("Account type", context["role_label"]),
        ("Address", context["site_url"]),
    ])
    label_width = 42
    for label, value in rows:
        pdf.set_font(PDF_FONT_NAME, "B", PDF_LABEL_SIZE)
        pdf.cell(label_width, PDF_LINE_HEIGHT, f"{label}:", new_x="RIGHT", new_y="TOP")
        pdf.set_font(PDF_FONT_NAME, "", PDF_BODY_SIZE)
        pdf.multi_cell(0, PDF_LINE_HEIGHT, value or "—")
        pdf.ln(PDF_SECTION_GAP)
    if not context["password_available"]:
        pdf.set_font(PDF_FONT_NAME, "", PDF_LABEL_SIZE)
        pdf.multi_cell(
            0,
            PDF_LINE_HEIGHT,
            "Password not on file. Ask your maestro for your login password.",
        )
        pdf.ln(PDF_SECTION_GAP)
    pdf.ln(PDF_SECTION_GAP)
    pdf.set_font(PDF_FONT_NAME, "B", PDF_BODY_SIZE)
    pdf.cell(0, PDF_LINE_HEIGHT, "How to sign in", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font(PDF_FONT_NAME, "", PDF_BODY_SIZE)
    steps = [
        f"1. Open {context['site_url']} in your web browser.",
        f"2. Enter username “{context['username']}” and your password.",
        "3. Open your assigned scores from your library.",
    ]
    for step in steps:
        pdf.multi_cell(0, PDF_LINE_HEIGHT, step)
        pdf.ln(1)
    buffer = BytesIO()
    pdf.output(buffer)
    return buffer.getvalue(), _pdf_filename(context["display_name"])
