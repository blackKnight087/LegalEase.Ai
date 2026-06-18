import re
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "app.py"
text = p.read_text(encoding="utf-8")
new = '''def _logo_data_uri() -> str:
    """Embed LegalEase scales logo for cinematic iframe."""
    logo_path = BASE_DIR / "assets" / "legalease_scales_logo.png"
    if not logo_path.exists():
        return ""
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return "data:image/png;base64," + encoded


def _cinematic_login_scene_html() -> str:
    """Load 8-12s ultra-cinematic login atmosphere (iframe)."""
    template_path = BASE_DIR / "assets" / "cinematic_login_scene.html"
    if not template_path.exists():
        return "<html><body style='background:#03060c'></body></html>"
    html = template_path.read_text(encoding="utf-8")
    return html.replace("__LOGO_URI__", _logo_data_uri())


'''
text, n = re.subn(
    r"def _cinematic_login_scene_html\(\) -> str:.*?(?=\ndef render_cinematic_login)",
    new,
    text,
    count=1,
    flags=re.DOTALL,
)
print("replaced", n)
p.write_text(text, encoding="utf-8")
