"""AI replies reach WhatsApp in WhatsApp's own formatting, not Markdown."""

from app.modules.pi.guard import validate_reply, whatsapp_text


def test_markdown_becomes_whatsapp_formatting():
    text = (
        "## Options\n\nAap ke liye:\n- **Inventory** tracking\n* Orders\n  - Stock\n\n\n\nKaunsa?"
    )
    assert whatsapp_text(text) == (
        "*Options*\n\nAap ke liye:\n\u2022 *Inventory* tracking\n\u2022 Orders\n"
        "  \u2022 Stock\n\nKaunsa?"
    )


def test_plain_text_and_whatsapp_bold_are_unchanged():
    text = "Ji zaroor. *Website* ke liye kaunsa feature chahiye? 2*3 = 6"
    assert whatsapp_text(text) == text


def test_validate_reply_sends_the_formatted_text():
    assert validate_reply("- **Orders**\n- Stock", [], 1000) == "\u2022 *Orders*\n\u2022 Stock"
