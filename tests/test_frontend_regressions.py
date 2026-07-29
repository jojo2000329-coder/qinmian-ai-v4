from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_password_change_keeps_form_reference_across_await():
    source = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert "const form = event.currentTarget;" in source
    assert "form.reset();" in source
    assert "event.currentTarget.reset();" not in source
