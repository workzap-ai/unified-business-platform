# ruff: noqa: E501  (one language per line reads better than wrapped word lists)
"""Who is sick, with what, and what to give: the veterinary and medical advice gate for any word
order, any spelling and the 8 priority languages (English, Roman Urdu, Urdu script, Arabic, Hindi,
French, Persian, Spanish).

Live chat 2026-10-26 16:25: "meri bhens beemar hai kya dawai doon?" was not stopped because the old
patterns only knew a few fixed phrases ("bimar bhains", "konsi dawai"). Three word sets are checked
together instead, so the order and the spelling stop mattering:

  an animal (cow, buffalo, goat, hen...)  +  a sign of illness  +  a treatment or an ask for one
  -> veterinary advice;
  a sign of illness  +  a treatment  +  the shape of a question, and no animal -> medical advice.

A business that only deals in these things is not stopped: "meri bhainson mein bimari se doodh kam
hai" has no treatment, and "dawai ki sales kam hain" has no sign of illness or question."""

import re
import unicodedata

from app.modules.pi.safety import Advice

ANIMAL = (
    r"cows?|buffal(?:o|oes)|goats?|sheep|camels?|horses?|animals?|hens?|chickens?|poultry|dogs?|cats?|calf|calves|bulls?|oxen|ox|"
    r"bhens|bhain|bhains|bhaisen|bhainsen|bhainse|gai|gaye|gaay|bakri|bakriyan|bakre|unt|ghora|ghore|janwar|janwaron|murghi|murghiyan|kutta|kutte|billi|bachra|bachri|saand|bail|dumba|bher|bheD|"
    r"بھینس|بھینسیں|بھینسوں|گائے|گایوں|بکری|بکریاں|اونٹ|گھوڑا|گھوڑے|جانور|جانوروں|مرغی|مرغیاں|کتا|کتے|بلی|بچھڑا|"
    r"भैंस|गाय|बकरी|ऊंट|ऊँट|घोड़ा|जानवर|मुर्गी|कुत्ता|बिल्ली|बछड़ा|"
    r"بقرة|بقرتي|أبقار|جاموس|ماعز|شاة|غنم|جمل|حصان|حيوان|حيوانات|دجاج|كلب|قطة|عجل|"
    r"vaches?|buffles?|chèvres?|moutons?|chameaux|chameau|chevaux|cheval|animaux|animal|poules?|poulets?|chiens?|chats?|veaux|veau|"
    r"vacas?|búfalos?|cabras?|ovejas?|camellos?|caballos?|animales|gallinas?|pollos?|perros?|gatos?|terneros?|"
    r"گاو|گاوها|بوفالو|بز|گوسفند|شتر|اسب|حیوان|حیوانات|مرغ|سگ|گربه|گوساله"
)
SICK = (
    r"sick|ill|unwell|injured|injury|fever|diarrh?o?ea|bleeding|limping|wound|vomit\w*|infection|infected|pain|"
    r"beemar|bimar|bimaar|bemar|bemaar|bimari|beemari|bukhar|zakhmi|zakham|ulti|dast|langra|lang|dard|chot|sust|nahi kha|"
    r"بیمار|بیماری|بخار|زخمی|زخم|الٹی|دست|لنگڑ|درد|چوٹ|سست|"
    r"बीमार|बीमारी|बुखार|घायल|उल्टी|दस्त|लंगड़|दर्द|चोट|सुस्त|"
    r"مريض|مريضة|مرض|حمى|مصاب|مصابة|جرح|قيء|إسهال|ألم|عرج|"
    r"malades?|maladie|blessé\w*|fièvre|diarrhée|plaie|douleur|boite|"
    r"enferm[oa]s?|enfermedad|herid[oa]s?|fiebre|diarrea|herida|dolor|cojea|"
    r"بیمار|بیماری|تب|زخمی|زخم|استفراغ|اسهال|درد|لنگ"
)
TREAT = (
    r"medicines?|medication|drugs?|dos(?:e|age)|injections?|antibiotics?|tablets?|pills?|syrup|treat(?:ment)?|cure|remedy|what should i give|give (?:it|him|her|them)|"
    r"dawai|dawa|dawaiyan|davai|dawayi|inject|ilaj|ilaaj|goli|doon|dun|den|dein|lagaun|lagwaun|khilaun|pilaun|"
    r"دوا|دوائی|انجکشن|علاج|گولی|ٹیبلٹ|سیرپ|دوں|"
    r"दवा|दवाई|इंजेक्शन|इलाज|गोली|टैबलेट|सिरप|दूँ|दूं|"
    r"دواء|علاج|حقنة|مضاد حيوي|جرعة|حبوب|أعطي|"
    r"médicaments?|traitement|soigner|antibiotiques?|comprimés?|sirop|que donner|quoi donner|"
    r"medicinas?|medicamentos?|tratamiento|curar|inyecci[oó]n|antibi[oó]ticos?|dosis|pastillas?|jarabe|qu[eé] darle|"
    r"دارو|دارویی|داروی|درمان|آمپول|آنتی[‌ ]?بیوتیک|دوز|قرص|شربت|چه بدهم"
)
ASKY = (
    r"[?؟]|\b(?:kya|kaun|konsi|kaunsi|kon si|which|what|how|can i|should i|doon|dun|den|dein|dena|kaise|kitni|kitna|"
    r"quel|quelle|quoi|comment|que|cu[aá]l|c[oó]mo)\b|क्या|कौन|कैसे|کیا|کون|کیسے|هل|ماذا|كيف|آیا|چه|چگونه"
)


def _has(words: str, text: str) -> bool:
    # an Arabic article ("البقرة") sticks to the word, so it is allowed in front
    return bool(re.search(rf"(?<![\w])(?:ال)?(?:{words})(?![\w])", text, re.IGNORECASE))


def treatment_asked(text: str) -> Advice | None:
    said = unicodedata.normalize("NFC", " ".join((text or "").split()))
    if not said or not _has(TREAT, said):
        return None
    sick = _has(SICK, said)
    asked = bool(re.search(ASKY, said, re.IGNORECASE))
    if _has(ANIMAL, said) and (sick or asked):
        return Advice.VETERINARY
    if sick and asked:
        return Advice.MEDICAL
    return None
