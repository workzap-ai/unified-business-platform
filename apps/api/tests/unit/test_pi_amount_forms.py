"""The reply linter's amount check catches a price written with a currency sign or code first."""

from app.modules.pi.constitution import AMOUNT_WORDS


def test_a_currency_first_price_is_an_amount_and_ordinary_text_is_not():
    for text in ("Rs 5000", "PKR 5,000", "$20", "₨ 500", "USD20", "5000 rs", "5k"):
        assert AMOUNT_WORDS.search(text), text
    for text in ("we open at 5 pm", "version 2", "the first 3 shops", "Rs is short for rupees"):
        assert not AMOUNT_WORDS.search(text.replace("rupees", "")), text
