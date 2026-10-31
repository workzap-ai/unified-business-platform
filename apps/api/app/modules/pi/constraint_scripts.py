"""L2-1: read an option written in Urdu script, Arabic or Hindi (Devanagari) as English concepts.

Pure: no database, no model, no network, no import from `evalkit` or `constraint_check`. The words
below are a READING aid, not a gate: they turn an option's verbs and objects into the English
words `constraint_check` already enforces limits with. They never make an option acceptable:
  * a word that is not in the tables is left as it is and counted as UNREAD; the caller never
    returns `ok` for an option that has an unread word;
  * an option with no recognised verb stays unreadable (`unknown`);
  * negation ("نہیں", "لا", "नहीं"), "instead of" and learn-first words map to the same English
    words the English rules already guard with.

`build(canon)` folds every key with the caller's text canonicaliser, so a key matches however the
text was typed (Arabic yeh and heh forms, Devanagari nukta). Light verbs (کریں, करें) read as
nothing; "رکھیں / रखें" is "hire" next to a person word and "keep" otherwise.
"""

import re
from collections.abc import Callable

HIRE_OR_KEEP = "@keep"  # Urdu and Hindi "to keep / to put in a job"
HIRE_OR_USE = "@use"  # Arabic "استخدام": hiring a person or using a thing

_URDU = """
رکھیں=@keep رکھنا=@keep رکھو=@keep رکھ=@keep بھرتی=hire ملازم=employee ملازمین=employees عملہ=staff
کلرک=clerk کیشیئر=cashier ڈرائیور=driver مینیجر=manager سیلزمین=salesman اسٹاف=staff سٹاف=staff
کارکن=worker کارکنان=workers لوگ=people بندے=people شخص=person افراد=people ٹیکنیشن=technician
اکاؤنٹنٹ=accountant ڈیزائنر=designer
نکالیں=fire نکالنا=fire نکال=fire برخاست=fire
خریدیں=buy خریدنا=buy خریدو=buy خرید=buy خرچ=spend بند=close
بدلیں=change بدلنا=change بدل=change بدلو=change تبدیل=change تبدیلی=change
بڑھائیں=raise بڑھانا=raise بڑھا=raise کم=cut گھٹائیں=cut
قیمت=price قیمتیں=prices قیمتوں=prices دام=price ڈیلیوری=delivery پہنچائیں=deliver پہنچانا=deliver
روکیں=stop روکنا=stop روک=stop کھولیں=open کھولنا=open کھول=open شامل=add اضافہ=add
نیا=new نئی=new نئے=new مزید=more اور=and نہیں=not نہ=not مت=don't
جانچیں=check جانچ=check جائزہ=check ناپیں=measure
سسٹم=system ایپ=app سافٹ=software دکان=shop برانچ=branch ٹیبلیٹ=tablet کورئیر=courier کوریئر=courier
جگہ=ki_jagah بجائے=ki_jagah
کریں="" کرنا="" کرو="" کیجئے="" کیجیے="" دیں="" لیں="" لینا="" لے="" جائے="" ویئر="" کر=""
"""
_ARABIC = """
توظيف=hire تعيين=hire وظف=hire نوظف=hire استخدام=@use استخدم=use موظف=employee موظفين=employees
عامل=worker عمال=workers كاتب=clerk محاسب=accountant مندوب=rep سائق=driver مدير=manager
طاقم=staff فريق=team اشخاص=people شخص=person
شراء=buy اشتري=buy اشتر=buy انفاق=spend اغلاق=close اغلق=close
تغيير=change غير=change استبدال=replace استبدل=replace بدل=replace
رفع=raise زيادة=raise خفض=cut تخفيض=cut تقليل=cut
سعر=price اسعار=prices توصيل=delivery فصل=fire طرد=fire ايقاف=stop وقف=stop
افتح=open فتح=open اضافة=add اضف=add جديد=new جديدة=new اكثر=more مزيد=more
لا=not لن=not ليس=not عدم=not تجنب=avoid قيم=check اختبر=check افحص=check تحقق=check تقييم=check
نظام=system تطبيق=app برنامج=software متجر=shop فرع=branch
"""
_HINDI = """
रखें=@keep रखना=@keep रखो=@keep रख=@keep भर्ती=hire नियुक्त=hire नियुक्ति=hire
कर्मचारी=employee कर्मचारियों=employees स्टाफ=staff क्लर्क=clerk कैशियर=cashier ड्राइवर=driver
मैनेजर=manager सेल्समैन=salesman कार्यकर्ता=worker लोग=people व्यक्ति=person आदमी=person
निकालें=fire निकालना=fire निकाल=fire बर्खास्त=fire
खरीदें=buy खरीदना=buy खरीदो=buy खरीद=buy खर्च=spend बंद=close
बदलें=change बदलना=change बदल=change बदलाव=change
बढ़ाएं=raise बढ़ाएँ=raise बढ़ाना=raise बढ़ा=raise घटाएं=cut घटाएँ=cut घटाना=cut कम=cut
कीमत=price कीमतें=prices कीमतों=prices दाम=price डिलीवरी=delivery पहुँचाएँ=deliver
रोकें=stop रोकना=stop रोक=stop खोलें=open खोलना=open खोल=open जोड़ें=add जोड़ना=add जोड़=add
नया=new नई=new नए=new और=and नहीं=not न=not मत=don't जाँचें=check जांचें=check जाँच=check
जांच=check सिस्टम=system ऐप=app सॉफ्टवेयर=software दुकान=shop टैबलेट=tablet कूरियर=courier
जगह=ki_jagah बजाय=ki_jagah
करें="" करना="" करो="" कीजिए="" दें="" दीजिए="" लें="" लेना=""
"""
_STOP = """
کی کا کے پر میں سے کو تو ہی بھی ہے ہیں یہ وہ اس ان کہ تاکہ اگر لیکن ہم آپ ہمیں ہمارا ہمارے
کیا کوئی ہو ہوں گا گی گے پھر
की का के पर में से को तो ही भी है हैं यह वह इस उन कि ताकि अगर लेकिन हम आप हमें हमारा हमारे
क्या कोई हो हूँ गा गी गे फिर
في من على الى عن هذا هذه ذلك تلك ان او ثم لكن مع نحن انت هو هي هم كان
"""
_PUNCT = {"۔": ".", "،": ",", "؟": "?", "؛": ";", "।": "."}
_PREFIXES = ("وال", "بال", "لل", "ال", "و", "ب", "ل", "ف")
_MARKS = "ऀ-ःऺ-ॏ॑-ॗॢॣ"
_PIECE = re.compile(rf"\d+(?:\.\d+)?|(?:[^\W\d_]|[{_MARKS}]|')+|[;:!?.,\n]|\S")


def build(canon: Callable[[str], str]) -> tuple[dict[str, str], frozenset[str]]:
    table: dict[str, str] = {}
    for spec in (_URDU, _ARABIC, _HINDI):
        for pair in spec.split():
            word, _, token = pair.partition("=")
            table[canon(word)] = token.strip('"').replace("_", " ")
    stop = frozenset(canon(w) for w in _STOP.split())
    return table, stop


def _lookup(word: str, table: dict[str, str]) -> str | None:
    if word in table:
        return table[word]
    for prefix in _PREFIXES:  # Arabic: al-, wa-, bi-, li-, fa- glued to the word
        if word.startswith(prefix) and len(word) > len(prefix) + 1:
            rest = word[len(prefix) :]
            if rest in table:
                return table[rest]
    return None


def to_english(
    text: str,
    table: dict[str, str],
    stop: frozenset[str],
    *,
    is_known: Callable[[str], bool],
    is_person: Callable[[str], bool],
    is_verb: Callable[[str], bool],
) -> tuple[str, int, int]:
    """(the text with recognised words replaced by English, recognised count, unread count).

    `text` is already normalised. `is_known` says a word is fine to leave (a number word or a
    currency word); every other word that is not in the tables is unread."""
    for src, dst in _PUNCT.items():
        text = text.replace(src, dst)
    out: list[str] = []
    recognised = unread = 0
    for piece in _PIECE.findall(text):
        if not piece[0].isalpha() or piece.isascii():
            out.append(piece)
            continue
        token = _lookup(piece, table)
        if token is not None:
            recognised += 1
            if token:
                out.extend(token.split())
        elif piece in stop or is_known(piece):
            out.append(piece)
        else:
            out.append(piece)
            unread += 1
    person = any(is_person(w) for w in out)
    out = [("hire" if person else "keep") if w == HIRE_OR_KEEP else w for w in out]
    out = [("hire" if person else "use") if w == HIRE_OR_USE else w for w in out]
    # "رکھنا نہیں": the negation follows the verb in these languages; English puts it before
    for i in range(len(out) - 1):
        if out[i + 1] in {"not", "don't"} and is_verb(out[i]):
            out[i], out[i + 1] = out[i + 1], out[i]
    return " ".join(out), recognised, unread
