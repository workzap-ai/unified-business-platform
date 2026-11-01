"""language_script.py (agent 8): detection, pin, reply language, business terms, cues.

Scripted tests: they prove the wiring, the spec rules and the labelled sets, not real accuracy.
Spec: platform v1.6 2.5 (languages and scripts), RLANG02/RLANG09 (10.3), RVOICE04, 2.5.1."""

import dataclasses
import importlib.util
import inspect
from pathlib import Path

import pytest

from app.modules.pi import language_script as ls
from app.modules.pi import language_script_lexicon as lex

_spec = importlib.util.spec_from_file_location(
    "language_script_eval_lib", Path(__file__).parent / "language_script_data" / "eval_lib.py"
)
assert _spec is not None and _spec.loader is not None
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

ROMAN_CHAT = [
    "Mera dhanda nahi chal raha aur meri kuch dukaanain hain defense mein",
    "Samajh liya. Kaunsi cheez ki dukaanain hain?",
]
URDU_CHAT = ["ہمارے کلینک میں استقبالیہ پر قطار بہت بے ترتیب ہے اس لیے مریض ناراض ہوتے ہیں"]
ENGLISH_CHAT = ["Our shops have no footfall and the staff come late every week"]


# ---------------------------------------------------------------- labelled sets


def test_labelled_set_has_more_than_300_sentences_and_every_required_language():
    rows = ev.load_labelled()
    assert len(rows) >= 300
    labels = {r[0] for r in rows}
    # spec 2.5 languages plus fixed_lines/language.py extras
    assert {
        "en",
        "roman_ur",
        "ur",
        "ar",
        "hi",
        "fa",
        "fr",
        "es",
        "ps",
        "sd",
        "pa",
        "tl",
        "bn",
        "ta",
        "ml",
    } <= labels


def test_labelled_precision_and_recall_for_the_languages_with_enough_sentences():
    report = ev.labelled_report()
    for lang in ("en", "roman", "ur", "ar", "hi", "fa", "fr", "es"):
        assert report[lang]["n"] >= 15, lang
        assert report[lang]["recall"] >= 0.9, (lang, report[lang])
        assert report[lang]["precision"] >= 0.95, (lang, report[lang])
    # und: short and ambiguous messages must come back uncertain
    assert report["und"]["recall"] >= 0.95, report["und"]


def test_small_languages_are_only_smoke_tested_not_measured():
    report = ev.labelled_report()
    for lang in ("ps", "sd", "pa", "bn", "ta", "ml", "de", "id", "tr", "tl"):
        assert report[lang]["n"] < 10  # honest: too few sentences to claim a rate
        assert report[lang]["recall"] >= 0.6, (lang, report[lang])


def test_code_switching_present_languages_are_found():
    rep = ev.present_report()
    assert rep["n"] >= 10
    assert rep["precision"] >= 0.9 and rep["recall"] >= 0.75, rep


# ---------------------------------------------------------------- PS-0 development turns


def test_ps0_development_owner_turns_all_four_languages_plus_english():
    rep = ev.ps0_report()
    assert set(rep) == {"en", "roman_ur", "ur", "ar", "hi"}
    for lang, r in rep.items():
        assert r["n"] >= 24
        assert r["wrong"] == 0, (lang, r)  # a wrong language is the failure that matters most
        assert r["correct"] / r["n"] >= 0.97, (lang, r)


def test_ps0_no_case_flips_script_when_walked_message_by_message():
    assert ev.ps0_sequence_flips() == []


# ---------------------------------------------------------------- script separation


@pytest.mark.parametrize(
    "text,code",
    [
        ("ہمارے پاس صرف تین لوگ ہیں اور سب دیر سے آتے ہیں", "ur"),
        ("لدي متجر صغير وعدد الموظفين قليل جدا", "ar"),
        ("من یک فروشگاه کوچک دارم و تعداد کارکنان خیلی کم است", "fa"),
        ("زه یو کوچنی دوکان لرم او زما کارکوونکي ډیر لږ دي", "ps"),
        ("مون وٽ هڪ ننڍي دڪان آهي ۽ اسٽاف تمام گهٽ آهي", "sd"),
        ("मेरी दुकान में तीन लोग काम करते हैं लेकिन सब देर से आते हैं", "hi"),
        ("আমার একটি ছোট দোকান আছে এবং কর্মী খুব কম", "bn"),
        ("என்னிடம் ஒரு சிறிய கடை உள்ளது ஊழியர்கள் மிகவும் குறைவு", "ta"),
        ("എനിക്ക് ഒരു ചെറിയ കടയുണ്ട് ജീവനക്കാർ വളരെ കുറവാണ്", "ml"),
    ],
)
def test_script_alone_never_decides_arabic_urdu_persian_pashto_sindhi(text, code):
    d = ls.detect_message_language(text)
    assert d.code == code and not d.uncertain
    assert d.script == ls.SCRIPT_OF_CODE[code]


def test_urdu_script_owner_with_a_stray_english_word_stays_urdu_and_lists_english():
    d = ls.detect_message_language("ہمارا stock ختم ہو جاتا ہے اور delivery بھی لیٹ ہوتی ہے")
    assert d.code == "ur" and d.script == "arabic"
    assert "en" in d.present


def test_english_message_with_an_urdu_script_tail_is_english_with_urdu_present():
    d = ls.detect_message_language("We have a problem with the staff, ہمارا اسٹاف late آتا ہے")
    assert d.code == "en" and "ur" in d.present


def test_arabic_indic_digits_and_ya_kaf_point_to_arabic_not_urdu():
    assert ls.detect_message_language("لدينا ٣ فروع ولا أحد يتابع المخزون").code == "ar"


def test_persian_zwnj_verb_forms_are_persian():
    assert ls.detect_message_language("ما رزروها را در واتساپ می‌گیریم").code == "fa"


def test_persian_written_without_zwnj_is_still_persian():
    assert (
        ls.detect_message_language(
            "قیمت کالاها هر هفته تغییر میکند و ما نمیتوانیم دنبالش کنیم"
        ).code
        == "fa"
    )


def test_punjabi_shahmukhi_is_found_by_its_own_words_and_asks_once():
    d = ls.detect_message_language("میں اک چھوٹی جئی دکان چلاندا واں تے میرے کول سٹاف بہت گھٹ اے")
    assert d.code == "pa" and d.needs_clarification and d.clarify_key == ls.CLARIFY_URDU_OR_ENGLISH
    again = ls.detect_message_language(
        "میں اک چھوٹی جئی دکان چلاندا واں تے میرے کول سٹاف بہت گھٹ اے",
        asked=[ls.CLARIFY_URDU_OR_ENGLISH],
    )
    assert again.code == "pa" and not again.needs_clarification  # ask once


def test_urdu_text_is_not_mistaken_for_punjabi():
    assert (
        ls.detect_message_language("ہمارے پاس دو برانچیں ہیں اور اسٹاک کا حساب کبھی نہیں ملتا").code
        == "ur"
    )


# ---------------------------------------------------------------- Roman Urdu / Hindi / English


def test_roman_urdu_vs_english_by_function_words_and_spelling_variants():
    for text in (
        "kia ap meray liye document bana saktay hain?",
        "mujhe nhi pata kya krna hai",
        "Boooht saray log phone kartay hain",
    ):
        assert ls.detect_message_language(text).code in ls.ROMAN_INDIC, text
    assert (
        ls.detect_message_language("Can you tell me what you can do for a small clinic?").code
        == "en"
    )


def test_roman_urdu_markers_give_roman_ur_and_hindi_markers_roman_hi():
    assert ls.detect_message_language("Shukriya, ab mujhe samajh aa gaya hai").code == "roman_ur"
    assert ls.detect_message_language("Dhanyavaad, ab mujhe samajh aa gaya hai").code == "roman_hi"


def test_indistinguishable_roman_text_is_labelled_honestly():
    d = ls.detect_message_language("Hamari dukaan mein teen log kaam karte hain")
    assert d.code == "roman_hi_or_ur" and not d.uncertain
    assert "urdu_vs_hindi_unresolved" in d.evidence


def test_indistinguishable_roman_text_prefers_the_pinned_choice():
    d = ls.detect_message_language("Hamari dukaan mein teen log kaam karte hain", pinned="roman_ur")
    assert d.code == "roman_ur" and d.reason == "indic_family_unresolved_pin_kept"
    d2 = ls.detect_message_language(
        "Hamari dukaan mein teen log kaam karte hain", pinned="roman_hi"
    )
    assert d2.code == "roman_hi"


def test_dropped_spaces_from_a_voice_transcript_are_recovered():
    d = ls.detect_message_language("mujhekyahaikuchnahipata", voice=True)
    assert d.code in ls.ROMAN_INDIC


def test_repeated_letters_and_shouting_do_not_change_the_language():
    assert ls.detect_message_language("THAAANKS, THAAAT MAKES SENSE TO ME NOW").code == "en"
    assert ls.detect_message_language("BOOOHAT SARAY LOG PHONE KARTAY HAIN").code in ls.ROMAN_INDIC


def test_code_switch_dominant_language_is_chosen_and_both_listed():
    d = ls.detect_message_language("Salam bhai stock khatam ho jata hai aur sale bhi kam hai")
    assert d.code in ls.ROMAN_INDIC and "en" in d.present
    d = ls.detect_message_language("Our shop has stock problems and the delivery is late, bhai")
    assert d.code == "en"


def test_other_latin_languages():
    for text, code in (
        ("Nos clients demandent sans cesse où est leur commande", "fr"),
        ("Nuestros clientes preguntan todo el tiempo dónde está su pedido", "es"),
        ("Unsere Kunden fragen ständig, wo ihre Bestellung ist", "de"),
        ("Pelanggan kami terus bertanya di mana pesanan mereka", "id"),
        ("Müşterilerimiz siparişlerinin nerede olduğunu sürekli soruyor", "tr"),
        ("Ang mga customer namin ay laging nagtatanong kung nasaan ang order nila", "tl"),
    ):
        assert ls.detect_message_language(text).code == code


def test_traps_that_look_like_another_language_stay_english():
    for text in (
        "Hi Ali, how are you doing today",
        "Do you do delivery for small shops",
        "To be or not to be that is the question",
        "The main street shop has a bar and a sale",
    ):
        d = ls.detect_message_language(text)
        assert d.code == "en", (text, d)


def test_names_only_is_uncertain_not_guessed():
    for text in ("Ali Khan Traders", "Main street shop", "Karachi Lahore Islamabad"):
        d = ls.detect_message_language(text)
        assert d.uncertain and d.code == "und", (text, d)


# ---------------------------------------------------------------- stickiness (RLANG09)


@pytest.mark.parametrize(
    "latest",
    [
        "no",
        "ok",
        "yes",
        "haan",
        "hmm",
        "5",
        "👍",
        "yes please",
        "theek hai",
        "thanks",
        "nahi",
        "ji",
        "100",
    ],
)
@pytest.mark.parametrize(
    "chat,code", [(ROMAN_CHAT, "roman_ur"), (URDU_CHAT, "ur"), (ENGLISH_CHAT, "en")]
)
def test_a_short_or_ambiguous_message_never_switches_the_pin(latest, chat, code):
    state = ls.LanguagePin().pin(chat)
    d = ls.detect_message_language(latest, history=chat)
    assert d.uncertain
    assert d.code == state.code
    plan_code, plan_script = ls.reply_language_for(d, None, chat)
    assert (plan_code, plan_script) == ls.reply_language_for(d, state, chat)
    assert plan_script == ls.SCRIPT_OF_CODE.get(
        state.code if state.code != "roman_hi_or_ur" else "roman_ur"
    )


@pytest.mark.parametrize(
    "short",
    ["ہاں", "نہیں", "ٹھیک", "लا", "जी", "ok", "oui", "sí", "no no", "👍👍", "...", "hmm ok"],
)
def test_short_messages_of_any_script_keep_a_roman_pin(short):
    d = ls.detect_message_language(short, pinned="roman_ur")
    assert d.uncertain and d.code == "roman_ur"


def test_voice_transcripts_count_as_substantive_however_short():
    d = ls.detect_message_language("stock khatam hai", pinned="en", voice=True)
    assert not d.uncertain and d.code in ls.ROMAN_INDIC
    d2 = ls.detect_message_language("stock khatam hai", pinned="en")
    assert not d2.uncertain and d2.code in ls.ROMAN_INDIC  # 3 words typed: substantive
    d3 = ls.detect_message_language("khatam hai", pinned="en")
    assert d3.uncertain and d3.code == "en"  # 2 words typed: keeps the pin
    d4 = ls.detect_message_language("khatam hai", pinned="en", voice=True)
    assert not d4.uncertain and d4.code in ls.ROMAN_INDIC


def test_pin_is_the_last_substantive_message_of_three_words_or_more():
    hist = [*ROMAN_CHAT, "ok", "haan", "5"]
    assert ls.LanguagePin().pin(hist).code in ls.ROMAN_INDIC
    hist2 = [*ROMAN_CHAT, "Please send me the quote for all of these together"]
    assert (
        ls.LanguagePin().pin(hist2).code == "en"
    )  # RLANG02: a substantive switch switches (spec default)


def test_one_stray_word_of_another_language_does_not_move_the_pin():
    hist = [*ROMAN_CHAT, "Aap ka quote kitne din mein aayega please"]
    assert ls.LanguagePin().pin(hist).code in ls.ROMAN_INDIC
    hist = [*URDU_CHAT, "ہمیں invoice بنانے میں بہت وقت لگتا ہے"]
    state = ls.LanguagePin().pin(hist)
    assert (state.code, state.script) == ("ur", "arabic")


def test_deliberate_script_switch_for_two_messages_with_switch_after_two():
    pin2 = ls.LanguagePin(switch_after=2)
    one = [*URDU_CHAT, "Hamari delivery boht late hoti hai aur gahak naraz hain"]
    two = [*one, "Mujhe quote chahiye pehle, phir faisla karunga"]
    assert pin2.pin(one).code == "ur"
    assert pin2.pin(two).code in ls.ROMAN_INDIC
    assert ls.LanguagePin().pin(one).code in ls.ROMAN_INDIC  # spec default: switches at once


def test_pin_with_no_history_defaults_to_english():
    state = ls.LanguagePin().pin([])
    assert (state.code, state.script, state.basis) == ("en", "latin", "default")


def test_pin_refines_an_unresolved_roman_family_when_a_marker_arrives():
    hist = ["Hamari dukaan mein teen log kaam karte hain", "Shukriya, ab mujhe samajh aa gaya hai"]
    state = ls.LanguagePin().pin(hist)
    assert state.code == "roman_ur"


def test_history_accepts_message_rows_dicts_and_turns_and_skips_ai_rows():
    class Row:
        def __init__(self, body, sender="customer", kind="text"):
            self.body, self.sender_type, self.message_type = body, sender, kind

    hist = [
        Row("Our shops have no footfall and the staff come late every week"),
        Row(
            "Mera dhanda nahi chal raha aur meri dukaanain hain", "ai"
        ),  # pi's own words never count
        {"text": "ok"},
        ls.HistoryTurn("hmm"),
        Row("voice", kind="audio"),
    ]
    assert ls.LanguagePin().pin(hist).code == "en"


# ---------------------------------------------------------------- reply language and script


def test_urdu_script_owner_always_gets_urdu_script_and_roman_owner_roman():
    d = ls.detect_message_language("ٹھیک", history=URDU_CHAT)
    assert ls.reply_language_for(d, None, URDU_CHAT) == ("ur", "arabic")
    d = ls.detect_message_language("haan", history=ROMAN_CHAT)
    code, script = ls.reply_language_for(d, None, ROMAN_CHAT)
    assert code == "roman_ur" and script == "latin"


def test_clear_substantive_message_switches_the_reply_language():
    d = ls.detect_message_language(
        "ہمارے پاس دو برانچیں ہیں اور اسٹاک کا حساب کبھی نہیں ملتا", history=ROMAN_CHAT
    )
    assert ls.reply_language_for(d, None, ROMAN_CHAT) == ("ur", "arabic")
    d = ls.detect_message_language(
        "My staff are late again and I cannot track it", history=URDU_CHAT
    )
    assert ls.reply_language_for(d, None, URDU_CHAT) == ("en", "latin")


def test_reply_switch_after_two_waits_for_a_second_message():
    d = ls.detect_message_language(
        "ہمارے پاس دو برانچیں ہیں اور اسٹاک کا حساب کبھی نہیں ملتا", history=ROMAN_CHAT
    )
    assert ls.reply_language_for(d, None, ROMAN_CHAT, switch_after=2)[1] == "latin"
    hist = [*ROMAN_CHAT, "ہمیں invoice بنانے میں بہت وقت لگتا ہے"]
    assert ls.reply_language_for(d, None, hist, switch_after=2) == ("ur", "arabic")


def test_default_with_no_pin_and_nothing_known_is_english():
    d = ls.detect_message_language("ok")
    assert ls.reply_language_for(d) == ("en", "latin")


def test_punjabi_sindhi_pashto_get_urdu_or_roman_urdu_and_the_question_once():
    d = ls.detect_message_language("زه یو کوچنی دوکان لرم او زما کارکوونکي ډیر لږ دي")
    plan = ls.reply_plan(d)
    assert (plan.code, plan.script, plan.ask_key) == ("ur", "arabic", ls.CLARIFY_URDU_OR_ENGLISH)
    assert ls.CLARIFY_TEXT[ls.CLARIFY_URDU_OR_ENGLISH] == "Urdu ya English mein baat karein?"


@pytest.mark.parametrize(
    "text",
    [
        "Ang mga customer namin ay laging nagtatanong kung nasaan ang order nila",
        "আমার একটি ছোট দোকান আছে এবং কর্মী খুব কম",
        "என்னிடம் ஒரு சிறிய கடை உள்ளது ஊழியர்கள் மிகவும் குறைவு",
        "എനിക്ക് ഒരു ചെറിയ കടയുണ്ട് ജീവനക്കാർ വളരെ കുറവാണ്",
    ],
)
def test_uae_workforce_languages_get_english_plus_an_offer_and_a_profile_note(text):
    plan = ls.reply_plan(ls.detect_message_language(text))
    assert (plan.code, plan.script, plan.offer_english) == ("en", "latin", True)
    assert plan.profile_note and plan.profile_note.startswith("owner_language=")


def test_priority_languages_are_answered_in_themselves():
    for text, code in (
        ("Nous perdons plusieurs factures chaque mois et personne ne s'en rend compte", "fr"),
        ("Perdemos varias facturas cada mes y nadie se da cuenta", "es"),
        ("ما رزروها را در واتساپ می‌گیریم و در دفتر می‌نویسیم", "fa"),
        ("نستقبل الحجوزات عبر واتساب ونكتبها في دفتر ورقي", "ar"),
        ("मेरी दुकान में तीन लोग काम करते हैं लेकिन सब देर से आते हैं", "hi"),
    ):
        d = ls.detect_message_language(text)
        assert ls.reply_language_for(d)[0] == code


def test_roman_hindi_family_replies_in_roman_urdu_when_unresolved():
    d = ls.detect_message_language("Hamari dukaan mein teen log kaam karte hain")
    assert ls.reply_language_for(d) == ("roman_ur", "latin")


def test_fixed_line_key_maps_to_the_keys_fixed_lines_has():
    from app.modules.pi import fixed_lines

    for code in ("en", "roman_ur", "ur", "ar", "hi", "fr", "fa", "es"):
        assert ls.fixed_line_key(code) == code
        assert ls.fixed_line_key(code) in fixed_lines.LINES["opening"] or code == "hi"
    assert ls.fixed_line_key("roman_hi") == "roman_ur" == ls.fixed_line_key("roman_hi_or_ur")
    assert (
        ls.fixed_line_key("ps", "arabic") == "ur" and ls.fixed_line_key("ps", "latin") == "roman_ur"
    )
    assert ls.fixed_line_key("tl") == ls.fixed_line_key("de") == "en"


# ---------------------------------------------------------------- uncertain and clarification


def test_unclear_substantive_message_without_a_pin_asks_which_language():
    d = ls.detect_message_language("Zyx qwv plm rtk bnm")
    assert d.uncertain and d.needs_clarification and d.clarify_key == ls.CLARIFY_WHICH_LANGUAGE
    d = ls.detect_message_language("Zyx qwv plm rtk bnm", asked=[ls.CLARIFY_WHICH_LANGUAGE])
    assert not d.needs_clarification


def test_unclear_message_with_a_pin_keeps_the_pin_and_does_not_ask():
    d = ls.detect_message_language("Zyx qwv plm rtk bnm", pinned="roman_ur")
    assert d.uncertain and d.code == "roman_ur" and not d.needs_clarification


def test_only_digits_emoji_punctuation_have_no_letters():
    for text in ("", "   ", "123 456", "😀😀", "?!?!", None):
        d = ls.detect_message_language(text, pinned="en")
        assert d.uncertain and d.reason == "no_letters" and d.code == "en"


def test_balanced_mix_is_uncertain():
    d = ls.detect_message_language("the shop hai", pinned="roman_ur")
    assert d.uncertain


def test_decision_fields_are_complete():
    d = ls.detect_message_language("Mujhe orders ka masla hai, customer bar bar poochte hain")
    assert isinstance(d, ls.LanguageDecision)
    assert d.script == "latin" and 0.5 <= d.confidence <= 1.0 and d.evidence and d.reason == "ok"
    assert "roman_hi_or_ur" in d.present or "roman_ur" in d.present


# ---------------------------------------------------------------- business terms


def test_lexicon_has_300_plus_concepts_and_1500_plus_variants():
    assert len({v for v in ls._TERMS.values()}) >= 300
    assert len(ls._TERMS) >= 1500


def test_no_variant_belongs_to_two_concepts():
    assert ls.TERM_COLLISIONS == []


def test_never_map_words_are_never_mapped():
    assert not [w for w in lex.NEVER_MAP if ls._lookup_term(w)]


def test_no_english_vocabulary_word_is_mapped_to_a_different_concept():
    bad = [
        (k, c)
        for k, c in ls._TERMS.items()
        if k in ls._EN_ALL
        and k != c
        and k.rstrip("s") != c
        and k not in ("quotation", "branches", "enquiries")
    ]
    assert bad == []


@pytest.mark.parametrize(
    "variants,concept",
    [
        (["order", "orders", "ordar", "aarder", "آرڈر", "آرڈرز", "ऑर्डर", "طلبات"], "order"),
        (["delivery", "dilevery", "dilivery", "ڈیلیوری", "डिलीवरी", "توصيل"], "delivery"),
        (["stock", "stok", "اسٹاک", "سٹاک", "स्टॉक", "مخزون"], "stock"),
        (["staff", "stuff", "اسٹاف", "स्टाफ", "عملہ", "موظفين"], "staff"),
        (
            ["customer", "customers", "gahak", "grahak", "گاہک", "عميل", "ग्राहक", "الزبائن"],
            "customer",
        ),
        (["payment", "adaigi", "ادائیگی", "भुगतान", "مدفوعات"], "payment"),
        (["salary", "tankhwah", "tankhwa", "تنخواہ", "तनख्वाह", "الراتب"], "salary"),
        (["invoice", "invois", "انوائس", "فاتورة"], "invoice"),
        (["delivary", "deliveri", "deliveries"], "delivery"),
        (["tenant", "tenants", "kirayadar", "किरायेदार", "مستأجر"], "tenant"),
    ],
)
def test_spelling_variants_map_to_one_concept_id(variants, concept):
    for v in variants:
        assert ls.business_term_normalise(v) == [concept], (v, ls.business_term_normalise(v))


def test_unknown_tokens_pass_through_exactly_as_written():
    toks = ls.business_term_normalise("Zyx QWV Delivery-ish ABC123")
    assert toks[0] == "Zyx" and toks[1] == "QWV" and "ABC123" in toks


def test_negations_and_quantities_are_untouched():
    out = ls.business_term_normalise(
        "no stock, nahi orders, 5 orders, 120 customers, نہیں اسٹاک, کوئی آرڈر"
    )
    assert out[:2] == ["no", "stock"] and "nahi" in out and "5" in out and "120" in out
    assert "نہیں" in out and "کوئی" in out
    assert out.count("order") == 3


def test_plural_and_arabic_article_forms():
    assert ls.business_term_normalise("الطلبات والمخزون") == ["order", "stock"]
    assert ls.business_term_normalise("orders invoices customers") == [
        "order",
        "invoice",
        "customer",
    ]


def test_voice_noise_in_business_terms():
    assert ls.business_term_normalise("staaaf ka salry") == ["staff", "ka", "salary"]


def test_business_term_matches_report_index_original_and_concept():
    hits = ls.business_term_matches("hamare staff ki salary late hoti hai")
    assert [(i, c) for i, _t, c in hits] == [(1, "staff"), (3, "salary")]


def test_business_normalise_never_raises_on_garbage():
    for junk in (None, "", "\x00\x01", "😀" * 50, "a" * 100000, "ال" * 3000):
        assert isinstance(ls.business_term_normalise(junk), list)


# ---------------------------------------------------------------- correction / withdrawal cues


@pytest.mark.parametrize(
    "text,language,kind",
    [
        ("I take that back", "en", "withdrawal"),
        ("never mind, forget it", "en", "withdrawal"),
        ("scratch that", "en", "withdrawal"),
        ("ignore what I said earlier", "en", "withdrawal"),
        ("Sorry, I meant 80 tenants, not 8", "en", "correction"),
        ("let me correct that", "en", "correction"),
        ("no wait, it was 15", "en", "correction"),
        ("typo, 100", "en", "correction"),
        ("That is not what I said", "en", "rejection"),
        ("you got that wrong", "en", "rejection"),
        ("that's wrong", "en", "rejection"),
        ("it's the opposite, actually", "en", "contradiction"),
        ("not anymore, that has changed", "en", "contradiction"),
        ("maine galat kaha tha", "roman_ur", "correction"),
        ("mera matlab 80 tha", "roman_ur", "correction"),
        ("galti se likh diya", "roman_ur", "correction"),
        ("wo baat wapas le raha hoon", "roman_ur", "withdrawal"),
        ("bhool jao ye sab", "roman_ur", "withdrawal"),
        ("chor do isko", "roman_ur", "withdrawal"),
        ("rehne do", "roman_ur", "withdrawal"),
        ("ye sahi nahi hai", "roman_ur", "rejection"),
        ("maine aisa nahi kaha", "roman_ur", "rejection"),
        ("bilkul ulta hai", "roman_ur", "contradiction"),
        ("نہیں میرا مطلب 80 تھا", "ur", "correction"),
        ("میں نے غلط کہا تھا", "ur", "correction"),
        ("غلطی سے لکھ دیا", "ur", "correction"),
        ("اسے بھول جائیں", "ur", "withdrawal"),
        ("رہنے دیں", "ur", "withdrawal"),
        ("یہ درست نہیں ہے", "ur", "rejection"),
        ("بالکل برعکس ہے", "ur", "contradiction"),
        ("ليس هذا ما قصدته", "ar", "rejection"),
        ("أقصد ثمانين وليس ثمانية", "ar", "correction"),
        ("عفوا، قصدت العكس", "ar", "correction"),
        ("انس ذلك", "ar", "withdrawal"),
        ("تجاهل ما قلته", "ar", "withdrawal"),
        ("هذا غير صحيح", "ar", "rejection"),
        ("على العكس تماما", "ar", "contradiction"),
        ("मैंने गलत कहा", "hi", "correction"),
        ("मेरा मतलब 80 था", "hi", "correction"),
        ("वो बात वापस ले रहा हूँ", "hi", "withdrawal"),
        ("भूल जाइए", "hi", "withdrawal"),
        ("यह सही नहीं है", "hi", "rejection"),
        ("बिल्कुल उल्टा है", "hi", "contradiction"),
    ],
)
def test_cues_in_five_languages(text, language, kind):
    r = ls.has_correction_or_withdrawal_cue(text, language)
    assert r.kind == kind and r.found and r.evidence, (text, r)
    assert kind in r.kinds


@pytest.mark.parametrize(
    "text",
    [
        "We have 80 tenants and 3 branches",
        "ok",
        "hamari dukaan mein teen log hain",
        "ہمارے پاس تین لوگ ہیں",
        "لدينا ثلاثة فروع",
        "मेरी दुकान में तीन लोग हैं",
        "The delivery is late",
        "",
    ],
)
def test_no_cue_in_plain_statements(text):
    assert not ls.has_correction_or_withdrawal_cue(text).found


def test_cue_search_without_a_language_tries_all():
    assert ls.has_correction_or_withdrawal_cue("نہیں میرا مطلب").kind == "correction"
    assert ls.has_correction_or_withdrawal_cue("ليس هذا ما قصدته").kind == "rejection"


def test_withdrawal_outranks_correction_and_all_kinds_are_listed():
    r = ls.has_correction_or_withdrawal_cue("sorry I meant 80, forget the rest", "en")
    assert r.kind == "withdrawal" and r.kinds == ("withdrawal", "correction")


def test_cue_inside_reported_speech_is_not_the_owners():
    assert not ls.has_correction_or_withdrawal_cue("he said I meant 80", "en").found
    assert not ls.has_correction_or_withdrawal_cue("usne kaha mera matlab ye tha", "roman_ur").found


def test_cue_with_voice_noise_and_stretched_letters():
    assert ls.has_correction_or_withdrawal_cue("sooorry I meaaant 80", "en").kind == "correction"
    assert (
        ls.has_correction_or_withdrawal_cue("maine galaaat kaha tha", "roman_ur").kind
        == "correction"
    )
    assert ls.has_correction_or_withdrawal_cue("نَہیں مِیرا مَطلَب", "ur").kind == "correction"


# ---------------------------------------------------------------- contract


def test_public_interface_signatures():
    sig = inspect.signature(ls.detect_message_language)
    assert list(sig.parameters) == ["text", "history", "pinned", "voice", "asked"]
    assert sig.parameters["history"].kind is inspect.Parameter.KEYWORD_ONLY
    assert list(inspect.signature(ls.reply_language_for).parameters) == [
        "decision",
        "pinned",
        "history",
        "switch_after",
    ]
    assert list(inspect.signature(ls.business_term_normalise).parameters) == ["text", "language"]
    assert list(inspect.signature(ls.has_correction_or_withdrawal_cue).parameters) == [
        "text",
        "language",
    ]
    assert [f.name for f in ls.LanguageDecision.__dataclass_fields__.values()][:6] == [
        "code",
        "script",
        "confidence",
        "evidence",
        "uncertain",
        "reason",
    ]


def test_decision_is_immutable_and_json_friendly():
    d = ls.detect_message_language("Mera dhanda nahi chal raha aur meri dukaanain hain")
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.code = "en"  # type: ignore[misc]
    assert isinstance(d.evidence, tuple) and isinstance(d.present, tuple)


def test_module_never_imports_evalkit_or_a_model():
    src = Path(ls.__file__).read_text(encoding="utf8")
    assert "evalkit" not in src and "openai" not in src.lower() and "anthropic" not in src.lower()
