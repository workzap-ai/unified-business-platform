# ruff: noqa: E501  (reply texts and patterns read better on one line each)
"""Safety checks that run before the model (pi Brain spec Part 6 and 9.6).

Pure and deterministic: they read the person's words and say what pi must do, in the person's
language. Emergencies stop the flow (R-EMER), card numbers, passwords and ID numbers are taken out
of what is kept (R-PRIV-02), advice that is not pi's to give is turned down (R-ADV), and the questions
about who pi is get the same honest answers every time (R-DISC, R-META-01). None of these needs a
model, so none of them can be talked out of the rule.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# --- where the person is ---------------------------------------------------------------------

NUMBERS = {
    "PK": {"police": "15", "ambulance": "1122", "ambulance_alt": "115", "fire": "16"},
    "AE": {"police": "999", "ambulance": "998", "fire": "997"},
    "CA": {"police": "911", "ambulance": "911", "fire": "911"},
}
ALL_COUNTRIES = (
    "Pakistan 15 (police), 1122 (rescue and ambulance), 115 (ambulance), 16 (fire); UAE 999 (police), 998 "
    "(ambulance), 997 (fire); Canada 911"
)


def country_of(phone: str | None) -> str | None:
    """PK, AE or CA from a WhatsApp number (digits, with or without +), else None."""
    digits = re.sub(r"\D", "", phone or "")
    for prefix, country in (("92", "PK"), ("971", "AE"), ("1", "CA")):
        if digits.startswith(prefix):
            return country
    return None


# --- emergencies (R-EMER-01 to 04) -----------------------------------------------------------


class Emergency(StrEnum):
    FIRE = "fire"
    MEDICAL = "medical"
    VIOLENCE = "violence"
    SELF_HARM = "self_harm"
    GENERIC = "generic"
    SAFEGUARDING = "safeguarding"  # abuse, neglect, a child at risk, harassment (spec Part 7)


EMERGENCY_PATTERNS: tuple[tuple[Emergency, re.Pattern[str]], ...] = (
    (
        Emergency.SELF_HARM,
        re.compile(
            r"\b(?:kill myself|end (?:my life|everything)|suicide|suicidal|want to die|"
            r"don'?t want to live|khudkushi|khud kushi|jaan de (?:dun|doon)|marna chahta|marna chahti|"
            r"zindagi khatam)\b|انتحار|خودکشی|أريد أن أموت|مرنا چاہتا|مرنا چاہتی",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.FIRE,
        re.compile(
            r"\b(?:there(?:'s| is) (?:a )?fire|(?:caught|catching|(?<!sales are )(?<!business is )(?<!sales is )on) fire(?!\s+sales?)|fire (?:in|at|broke out in) "
            r"(?:my|the|our)\b|(?:building|shop|godown|factory|warehouse) is (?:burning|on fire)|"
            r"aag lag(?:i|gayi|gai|ayi)|(?:shop|godown|factory|dukan|dukaan) mein aag)\b|حريق|حریق|آگ لگ",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.VIOLENCE,
        re.compile(
            r"\b(?:(?<!had a )(?<!had an )(?<!after the )(?<!after a )(?<!since the )(?<!last )"
            r"(?:robbery|robbers?|dacoity|daketi|dakaiti|dakoo)"
            r"(?!\s+(?:last|ago|earlier|before|in \d{4}|yesterday|a (?:year|month|week|few)))|"
            r"armed (?:men|man|robbers?)|"
            r"(?:has|have|with) (?:a )?(?:gun|guns|knife)|pointing a gun|they are (?:beating|attacking)|"
            r"attacking (?:us|me|the shop)|threatening to kill|death threat|going to kill me|"
            r"looting (?:the|my) (?:shop|store))\b|سرقة مسلحة|ڈکیتی|ڈاکو",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.MEDICAL,
        re.compile(
            r"\b(?:(?:need|call|send|get) (?:an |the )?ambulance|heart attack|not breathing|"
            r"(?:someone|he|she|worker|staff|guard|driver) "
            r"(?:is |was |got )(?:badly )?(?:hurt|injured|bleeding|unconscious)|accident (?:happened|hua|ho gaya)|"
            r"(?:zakhmi|behosh|khoon beh)\b)|إسعاف",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.GENERIC,
        re.compile(
            r"\b(?:emergency (?:is )?(?:in progress|happening|right now|going on)|mayday|"
            r"(?:in|having) an emergency|crash(?:ed|ing) (?:right )?now|emergency landing)\b",
            re.IGNORECASE,
        ),
    ),
)


# More ways people say it in Arabic, Urdu and Roman Urdu (spec 6.1, R-EMER-01): only phrases that
# clearly describe something happening now, never a word that also appears in ordinary business talk.
EMERGENCY_PATTERNS = EMERGENCY_PATTERNS + (
    (
        Emergency.SELF_HARM,
        re.compile(
            r"(?:أقتل نفسي|اقتل نفسي|أنهي حياتي|انهي حياتي|لا أريد أن أعيش|لا اريد ان اعيش|"
            r"اريد ان اموت|أبغى أموت|ابغى اموت|اپنی جان لے|مر جانا چاہتا|مر جانا چاہتی|"
            r"خود کو ختم|خودکشی|اپنی جان دے|مرنا چاہتا|مرنا چاہتی|جینا نہیں چاہتا|جینا نہیں چاہتی)"
            r"|\b(?:mar jana chahta|mar jana chahti|apni jaan le (?:lun|loon|lunga|lungi)|"
            r"zindagi se tang aa gaya|zindagi se tang aa gayi|khud ko khatam|khudkushi|khud kushi|"
            r"apni jaan de (?:dun|doon|dunga|dungi)|marna chahta|marna chahti|jeena nahi chahta|"
            r"jeena nahi chahti)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.FIRE,
        re.compile(
            r"(?:شعلت النار|اشتعلت النار|اشتعل حريق|النار في|آگ لگی|آگ لگ گئی|آگ بھڑک)"
            r"|\b(?:aag bhadak|aag lag gaye)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.VIOLENCE,
        re.compile(
            r"(?:لصوص|سطو مسلح|إطلاق نار|اطلاق نار|يضربوننا|يهاجمون|چور (?:اندر|گھس)|"
            r"گولی (?:چلی|لگی|مار)|حملہ ہو)"
            r"|\b(?:chor (?:andar|ghus)|chor aa gaye|goli (?:chali|lagi|maar)|hamla ho raha|"
            r"maar rahe hain)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Emergency.MEDICAL,
        re.compile(
            r"(?:مصاب بجروح|أصيب (?:بجروح|بشدة)|فاقد الوعي|ينزف|توقف عن التنفس|حادث (?:سير|مروري|خطير)|"
            r"ایکسیڈنٹ ہو|زخمی ہو|بے ہوش|سانس نہیں)"
            r"|\b(?:accident ho gaya|saans nahi|behosh ho|zakhmi ho)\b",
            re.IGNORECASE,
        ),
    ),
)


def _rx(latin: tuple[str, ...] = (), native: tuple[str, ...] = ()) -> re.Pattern[str]:
    """One case-insensitive pattern: Latin-script alternatives get word boundaries, Urdu and
    Arabic ones are matched as written."""
    parts: list[str] = []
    if latin:
        parts.append(r"\b(?:" + "|".join(latin) + r")\b")
    if native:
        parts.append("(?:" + "|".join(native) + ")")
    return re.compile("|".join(parts), re.IGNORECASE)


_PERSON = (
    r"(?:guest|patient|member|student|customer|child|kid|worker|staff|player|passenger|driver|cook|chef|"
    r"someone|man|woman|boy|girl|person|he|she|resident|trainee|athlete|swimmer|labou?rer|employee|"
    r"teacher|baby|pupil|visitor|diner|climber|diver|rider)"
)
_MACHINE = (
    r"(?:machine|machinery|press|rollers?|conveyor|grinder|blade|saw|cutter|mixer|belt|gear|motor|fan|"
    r"chopper|slicer|mill|crusher|shredder|drill|lathe|compressor|pulley|auger|thresher|chaff cutter)"
)
_PAST = r"(?!\s+(?:last|ago|earlier|before|in \d{4}|yesterday|a (?:year|month|week|few)))"

# Emergencies in every trade (spec Part 7 care rules, R-EMER-01): each phrase describes something
# happening to a person now. Ordinary words ("gas station", "collapse in sales", "drowning in
# paperwork", "lift installation") never match, because every pattern needs the harm itself.
TRADE_EMERGENCY_PATTERNS: tuple[tuple[Emergency, re.Pattern[str]], ...] = (
    (
        # Someone else at risk of harm or a child in danger: stop, refer, flag staff.
        Emergency.SAFEGUARDING,
        _rx(
            (
                r"(?:child|children|kid|kids|boy|girl|student|pupil|baby|minor|resident|patient|elderly|"
                r"inmate|trainee|intern|worker)s?\b[^.?!\n]{0,40}\b(?:(?:is|was|are|were|being|been|got|gets|get)"
                r"\s+(?:badly |regularly |repeatedly |sexually )?(?:abused|beaten|slapped|molested|assaulted|raped|"
                r"neglected|starved|harassed|tortured|trafficked|touched inappropriately))",
                r"(?:teacher|staff|caregiver|carer|nurse|driver|guard|coach|tutor|warden|father|mother|uncle|"
                r"relative|attendant|worker|supervisor|manager|boss|aunt|stepfather|neighbou?r|man|"
                r"stranger)\s+(?:is |was |has been |keeps |kept )?(?:beat|beating|hitting|abusing|molesting|touching|"
                r"harassing|slapping|assaulting|raping|hurting|burning|starving|neglecting|threatening|"
                r"blackmailing)\s+(?:the |a |my |our |his |her )?(?:child|children|kids?|students?|pupils?|girls?|"
                r"boys?|baby|babies|residents?|patients?|elderly|workers?|women|ladies|female staff|interns?|"
                r"trainees?|maid|guests?)",
                r"(?:sexual(?:ly)? (?:abuse[ds]?|assault(?:ed)?|harass\w*)|child abuse|abus(?:ing|es) (?:a |the )?"
                r"(?:child|children)|molest\w*|rape[ds]?|raping|human trafficking|trafficked|"
                r"(?:domestic|family) violence|being harassed|harass(?:ed|ing) (?:me|her|him|them|the (?:girls?|"
                r"women|ladies|female))|(?:beats?|beating) (?:his|her|their|the) (?:wife|child|children|kids))",
                r"(?:child|kid|resident|patient|elderly|baby|student|girl|boy)\b[^.?!\n]{0,45}\b(?:not (?:being )?fed|"
                r"starving|left (?:alone|unattended|without (?:food|care|water))|unattended|bruises|"
                r"burn marks|marks on (?:his|her|their|the) (?:body|back|arms?|legs?)|afraid to go home|"
                r"scared to go home|doesn'?t want to go home|says (?:someone|he|she|dad|father|mother|teacher|"
                r"uncle) (?:hits|hurt|hurts|touches))",
                r"(?:student|pupil|child|girl|boy|kid|classmate|teenager|son|daughter|trainee)\b[^.?!\n]{0,40}\b"
                r"(?:self[- ]?harm\w*|cutting (?:himself|herself|themselves)|wants? to (?:die|kill (?:himself|"
                r"herself))|tried to (?:kill|hang|harm) (?:himself|herself)|suicid\w+|attempted suicide|"
                r"overdos\w+|threatening to (?:jump|kill (?:himself|herself)|end (?:his|her) life)|"
                r"tried to hang|took (?:pills|poison))",
                r"(?:child|kid|baby|toddler|boy|girl|student|pupil)s?\b[^.?!\n]{0,30}\b(?:(?:is|was|has been|got|"
                r"has gone|went)\s+(?:missing|lost|kidnapped|abducted)|left (?:behind|alone|inside|in the "
                r"(?:bus|van|car|vehicle|classroom|pool|room))|locked (?:in|inside)|forgotten (?:in|on|inside)|"
                r"alone in the|taken away|not (?:been )?picked up|wandered off|disappeared|stuck in (?:the )?"
                r"(?:bus|van|car))",
                r"missing (?:child|kid|boy|girl|baby|student|toddler)|lost child|(?:child|kid) (?:left|forgotten) "
                r"(?:on|in) (?:the )?(?:bus|van|car)|kidnap\w*|abduct\w*|(?:unknown|drunk|intoxicated|unsafe|"
                r"suspicious) (?:man|person|adult|driver)\b[^.?!\n]{0,30}(?:pick(?:ing)? up|picked up|take (?:the )?"
                r"child|took the child)|stranger (?:at|near) (?:the )?(?:gate|school|bus)|stranger[^.?!\n]{0,25}"
                r"pick up (?:the )?child",
                r"bach(?:a|e|on|i|chay|chi)\b[^.?!\n]{0,20}\b(?:ko|par|pe|se)\s+(?:maar|peet|pit|jala|bhooka)\w*",
                r"(?:teacher|master|ustad|ustaani|driver|guard|warden|nurse)\b[^.?!\n]{0,15}\bbach\w+\s+ko\s+"
                r"(?:maar|peet|pit)\w*",
                r"bach(?:i|e|a|on)\b[^.?!\n]{0,15}\b(?:ke saath|k saath|sath)\s+(?:zyadti|ziyadti|zulm|galat|"
                r"jinsi|badtameezi)",
                r"jinsi (?:hamla|tashaddud|istehsal|hirasaan\w*|zyadti|ziyadti)|hira(?:a)?san\w*|"
                r"harassment (?:ho|hui|hua|ka shikar)",
                r"(?:bazurg|buzurg|mareez|resident|bachon)\w*\s+(?:ko|par)\s+(?:maar|peet|tashaddud)\w*",
                r"(?:student|talib|bacha|bachi)\b[^.?!\n]{0,25}\b(?:khudkushi|khud kushi|zeher|apni jaan|"
                r"khud ko (?:nuksan|kaat|zakhmi))\w*",
                r"bach(?:a|i|e)\b[^.?!\n]{0,12}\b(?:gum|gumshuda|laapata|lapata|kho gaya|kho gayi|agwa|aghwa|"
                r"ghayab|(?:bus|van|gaari|gadi) (?:mein|me|main) (?:reh|rah|band|so)\w*)",
                r"agwa|aghwa",
            ),
            (
                r"(?:المعلم|المعلمة|المدرس|السائق|الحارس|الممرضة|المشرف|المدير)\s+(?:يضرب|يعتدي|يتحرش|يسيء)",
                r"يضرب(?:ون)?\s+(?:ال)?(?:طفل|أطفال|اطفال|طلاب|طالب|مرضى|مسن|مسنين|نزلاء)",
                r"(?:اعتداء|تحرش|استغلال)\s+(?:جنسي|جنسية)|تحرش|تحرّش|اغتصاب|تعنيف",
                r"إساءة (?:معاملة )?(?:ال)?(?:أطفال|اطفال|مسنين|نزلاء|طفل)|إهمال (?:ال)?(?:طفل|أطفال|مسن)",
                r"عنف (?:أسري|منزلي)|ضرب (?:ال)?(?:طفل|أطفال|طالب|طلاب)",
                r"(?:حاول|محاولة|يريد|حاولت)\s+(?:ال)?(?:طالب|طالبة|طفل|ولد|بنت)?\s*(?:الانتحار|انتحار|أن يموت|قتل نفسه|إيذاء نفسه)",
                r"إيذاء (?:ال)?نفس|يؤذي نفسه",
                r"(?:ال)?طفل\s+(?:ال)?(?:مفقود|مخطوف|منسي|متروك)|(?:نسي|ترك|نسينا|تركنا)\w*\s+(?:ال)?طفل\s+في\s+(?:ال)?"
                r"(?:حافلة|باص|سيارة)|طفل\s+(?:نسي|ترك)\s+في|فقد(?:نا)? (?:ال)?طفل|ضاع (?:ال)?طفل|اختطاف|"
                r"خطف (?:طفل|ولد|بنت)|طفل محبوس",
                r"استاد\s+بچوں\s+کو\s+مار|(?:ٹیچر|استاد|ڈرائیور|گارڈ|نرس|وارڈن)\s+(?:بچوں|بچے|بچی)\s*(?:کو)?\s*(?:مار|پیٹ)",
                r"بچ(?:ی|ے|ہ|وں)\s+(?:کے ساتھ|پر)\s+(?:زیادتی|ظلم|تشدد|غلط)|بچے کو مار|بچوں کو مار|بچے پر تشدد",
                r"جنسی\s+(?:ہراسانی|حملہ|استحصال|تشدد|زیادتی)|ہراسانی|ہراساں|زیادتی",
                r"(?:بزرگ|مریض|بوڑھے)\s+(?:کو|پر)\s+(?:مار|تشدد|پیٹ)",
                r"(?:طالب علم|اسٹوڈنٹ|سٹوڈنٹ|بچہ|بچی|لڑکی|لڑکا)[^.?!\n]{0,25}(?:خودکشی|خود کشی|زہر|خود کو (?:نقصان|زخمی|کاٹ))",
                r"خود کو (?:نقصان|زخمی)|بچ(?:ہ|ی|ے)\s+(?:گم|لاپتہ|اغوا|لاپتا)|بچہ\s+(?:بس|وین|گاڑی)\s+میں\s+(?:رہ|بند)",
                r"اغوا|لاپتہ بچ",
            ),
        ),
    ),
    (
        Emergency.SELF_HARM,
        _rx(
            (
                r"i (?:just )?(?:can'?t|cannot) go on(?!\s+(?:with|without|if|unless|until|selling|working|operating))|no (?:point|reason) (?:in|to) (?:living|"
                r"life|go on|going on)|better off dead|(?:everyone|they|my family|the family|all) (?:would be|are|is) "
                r"better off (?:without me|dead)|want(?:ed)? to disappear forever|self[- ]?harm|"
                r"cutting myself|overdos(?:e|ed|ing) (?:on|myself)|end it all|take my own life",
            ),
            (
                r"لا أستطيع الاستمرار|لا فائدة من الحياة|لا معنى للحياة|لا فائدة من حياتي",
                r"اب جینے کا کوئی فائدہ نہیں|جینے کا مقصد نہیں|اب اور نہیں جی سکتا|اب اور نہیں جی سکتی",
            ),
        ),
    ),
    (
        Emergency.FIRE,
        _rx(
            (
                r"fire (?:has )?broke out|set on fire|(?:explosion|exploded|explodes)"
                + r"(?!\s+(?:in|of)\s+(?:demand|growth|sales|orders|customers|data|popularity|traffic|costs?|prices?|interest|business|content|leads|users|followers))"
                r"|(?:cylinder|boiler|tank|tanker|compressor|gas cylinder|oven|stove|geyser|silo|pipe|transformer|"
                r"battery|kiln|furnace|reactor) (?:blast|blasted|burst|exploded|exploding|explodes|blew up)|"
                r"blast (?:in|at|near) (?:the |our |my )?(?:shop|factory|mill|godown|warehouse|kitchen|plant|site|"
                r"building|market|mine)|dust explosion|"
                r"dhamaka|dhamaaka|cylinder (?:phat|phatt|fatt|blast)|boiler (?:phat|phatt|fatt|blast)|"
                r"(?:smoke|dhuan|dhuaan) (?:is )?(?:coming|aa raha|nikal raha|bhar gaya)|"
                r"short circuit (?:se|and|caused)[^.?!\n]{0,15}(?:aag|fire|sparks?)",
                r""
                + _PERSON
                + r"\s+(?:got|was|is|has been|were|are)\s+(?:badly |severely |seriously )?(?:burn(?:t|ed)|scalded)"
                r"|(?:burn|burns) (?:injur\w+|victim)|third[- ]degree burn|scalded (?:by|with)|"
                r"(?:hand|haath|hath|face|chehra|bacha|bachi|mazdoor|worker)\b[^.?!\n]{0,15}\b(?:jhulas|jal (?:gaya|gayi|gaye))\w*|"
                r"jhulas\w*",
            ),
            (
                r"انفجار(?!\s+(?:في|ال)?\s*(?:الطلب|المبيعات|النمو))|انفجرت|إنفجار|حروق|احترق(?:ت|وا)?\s+(?:ال)?(?:عامل|طفل|طباخ|شخص)",
                r"دھماکہ|دھماکا|سلنڈر (?:پھٹ|بلاسٹ)|بوائلر (?:پھٹ|بلاسٹ)|جھلس|ہاتھ جل|دھواں بھر",
            ),
        ),
    ),
    (
        Emergency.MEDICAL,
        _rx(
            (
                r"(?:stuck|trapped|stranded) (?:in|inside) (?:the |a |an |our |that )?(?:\w+ )?(?:lift|elevator)"
                r"(?!\s+(?:installation|business|market|industry|sales|project|contract|quote|quotes|company))",
                r"(?:lift|elevator) (?:fell|dropped|free ?fall|crashed|cable snapped)",
                r"lift (?:mein|me|main) (?:\w+ ){0,3}(?:phans|phansa|phanse|phans gaye|phans gaya|atak)\w*",
                r"gas (?:leak\w*|leaking|is leaking)(?!\s+(?:detectors?|sensors?|alarms?|cylinders?|business))",
                r"(?:leak(?:ing)?|smell(?:s|ing)? (?:of )?|smell) gas|gas (?:smell|odou?r)|smells? (?:of )?gas",
                r"(?:ammonia|chlorine|refrigerant|co2|carbon monoxide|toxic|poisonous|chemical) (?:gas )?(?:leak|leaking|"
                r"exposure|fumes?|poisoning)",
                r"(?:inhaled|breathed in|swallowed|drank|ingested) (?:the |some )?(?:chlorine|ammonia|fumes?|gas|"
                r"pesticide|poison|acid|bleach|chemical|spray|smoke|kerosene|phenyl|petrol|diesel)",
                r"gas (?:ki|ka) (?:boo|smell|badbu|rissao|leak)|gas (?:leak|lik|rissao) (?:ho|hui|hua)|gas nikal rah\w+",
                r"dam ghut\w*|saans (?:nahi|nahin) aa\w*|can'?t breathe|cannot breathe|difficulty breathing|"
                r"suffocat\w+|carbon monoxide",
                r"electric(?:al)? shock\w*|electrocut\w+|shock(?:ed)? from (?:the |a )?(?:wire|socket|panel|machine|"
                r"current|electricity|cable|fan|geyser|switch)",
                r"(?:current|karant|karrant|karent|karrent) (?:laga|lag gaya|lag gayi|lag gaye|lagg gaya|laag gaya)",
                r"bijli (?:ka|ke|ki) (?:jhatka|jhatke|shock)|(?:bijli|current) se (?:jhatka|shock|jal|mar)",
                r"(?:wall|roof|ceiling|slab|building|shed|marquee|tent|stage|scaffold(?:ing)?|crane|mine|tunnel|"
                r"trench|balcony|shutter|chimney|canopy|structure|bridge|floor|platform|tower|silo|hoarding|"
                r"boundary wall|godown roof) (?:has |have |just )?(?:collapsed|caved in|fell down|came down|gir (?:gayi|gaya|gaye)|"
                r"giri|gira|dhah (?:gayi|gaya)|dhans (?:gayi|gaya))",
                r"(?:building|roof|wall|trench|mine|tunnel|bridge|scaffold(?:ing)?) collapse(?:d)?(?! in (?:sales|"
                r"revenue|demand|prices|margins|orders))",
                r"(?:cave[- ]in|caved in)\b[^.?!\n]{0,20}\b(?:on|over|with) (?:the )?(?:workers?|people|us|him|"
                r"them|guests?|labou?rers?|men)",
                r"(?:trapped|buried|stuck) (?:under|in) (?:the )?(?:rubble|debris|mud|sand|soil|trench|mine|collapsed)",
                r"(?:workers?|labou?rers?|mazdoor|mazdoors|guests?|men) (?:are |is |were )?(?:trapped|buried|dab (?:gaye|gaya))|"
                r"dab gaye|malb(?:a|ay|e)",
                r"(?:chhat|chat|deewar|diwar|dewar|imarat|building|chaat) gir (?:gayi|gaya|gaye|gai)",
                r""
                + _PERSON
                + r"\s+(?:is |was |has |got |were |are )?(?:drown\w*|sinking in|under ?water)"
                r"|(?:drowned|has drowned)(?!\s+in\s+(?:debt|paper\w*|work|orders?))|fell into (?:the )?(?:water|pool|"
                r"tank|canal|well|river|sea|lake)|(?:nearly|almost) drown\w*",
                r"(?:bach(?:a|i|e)|banda|aadmi|aurat|larka|larki|swimmer|mehmaan|guest|member|student|mazdoor|insaan|log|"
                r"machuara|worker)\b[^.?!\n]{0,15}\b(?:doob|dub)\w*|(?:pani|pool|nehar|samandar|kuen|talab) (?:mein|me|main) "
                r"(?:gir|doob|dub)\w*",
                r"snake ?bite|bitten by (?:a |the )?(?:snake|cobra|viper|scorpion|dog|spider)|snake (?:bit|bites)|"
                r"scorpion sting|stung by (?:a |the )?(?:scorpion|bee|wasp|snake)|dog bite|"
                r"(?:saanp|sanp|saamp|bichu|kutte|kutta|bichhu)\s+(?:ne\s+)?(?:kaat|daska|kata|dasa|dank)\w*|"
                r"saanp ke kaatne",
                r"(?:hand|fingers?|arm|leg|foot|hair|clothes|sleeve|thumb|palm) (?:got |was |is |has been |were )?"
                r"(?:stuck|caught|trapped|crushed|cut off|severed|amputated|sucked|pulled|dragged)\s*(?:in|inside|under|by|into)\s+"
                r"(?:the |a |our |that )?" + _MACHINE,
                r"(?:hath|haath|ungli|ungliyan|bazu|taang|pair|haatth)\b[^.?!\n]{0,20}\b"
                + _MACHINE
                + r"\b[^.?!\n]{0,20}\b"
                r"(?:phans|phans gaya|phans gayi|kat|kut|aa gaya|aa gayi|kuchla|kuchal)\w*",
                r"(?:hath|haath|ungli|ungliyan|bazu|taang|pair)\b[^.?!\n]{0,20}\b(?:mashin|machine|press|roller|belt)\b[^.?!\n]{0,20}\b"
                r"(?:phans|kat|kut|aa gaya|aa gayi|kuchla)\w*",
                r"crush(?:ed)? (?:by|under) (?:the |a )?(?:\w+ )?(?:machine|forklift|truck|press|load|pallet|rack|"
                r"container|crane|car|bus|wall|beam|rock|stack)|amputat\w+|severed|"
                r"(?:ungli|haath|hath|bazu|taang|pair) (?:kat|kut)\w*|finger (?:cut|kat) (?:off|gayi|gaya)",
                r"(?:bleeding (?:heavily|badly|a lot|profusely|won'?t stop|nonstop|continuously|too much)|"
                r"heavy bleeding|severe bleeding|lot of blood|losing (?:a lot of )?blood|blood everywhere|"
                r"khoon (?:beh|bah|nikal|nahi ruk|ruk nahi)\w*|bahut khoon|khoon bahut|haemorrhag\w+|hemorrhag\w+)",
                r"(?:poison(?:ed|ing)|pesticide (?:poisoning|exposure)|chemical (?:burn|splash|spill on)|acid (?:burn|"
                r"splash|attack|fell on|spilled on)|(?:swallowed|drank) (?:poison|pesticide|acid|bleach|chemical|"
                r"kerosene|phenyl|insecticide|weedicide|rat poison))",
                r"zehar (?:kha|pi|peena|khaya|pee|piya|chadh|lag)\w*|zeher (?:kha|pi|peena|khaya|pee|piya|chadh|lag)\w*|"
                r"zehreeli|zehreela|spray ka zehar|(?:dawai|spray|keera maar)\b[^.?!\n]{0,20}\b(?:pi liya|pee liya|kha liya)",
                r"(?:road|traffic|vehicle|car|bus|van|truck|bike|motorcycle|taxi|rickshaw|loader|tanker|site|factory|"
                r"workplace|crane|forklift) (?:accident|crash)|accident (?:on|at) (?:the )?(?:highway|road|motorway|site)|"
                r"hit and run|(?:bus|van|truck|car|tanker|coach|vehicle) (?:overturned|rolled over|capsized)|"
                r"ran over|run over (?:a |the )?(?:child|man|woman|person|worker|pedestrian)",
                r"(?:bus|van|truck|car|gaari|gadi|tanker|rickshaw|bike)\s+(?:ka\s+)?(?:accident|ulat|palat)\w*|"
                r"takkar (?:ho gayi|ho gaya|maar di)\b[^.?!\n]{0,25}(?:zakhmi|khoon|behosh)|haad(?:i)?sa (?:ho gaya|hua)",
                r"heat ?stroke|sun ?stroke|heat exhaustion|collapsed from (?:the )?heat|lu lag\w*|garmi se behosh",
                r"chest pain|pain in (?:my |his |her |the )?chest|chest (?:is )?(?:tight|hurting)|seene (?:mein|me|main) "
                r"(?:dard|jakdan)|seene ka dard|dil ka daura|dil (?:mein|me|main) dard|(?:had|having|got|suffered|suffering) "
                r"(?:a )?(?:brain )?stroke|stroke (?:patient|victim)|(?:having|had|got) (?:a )?seizure|seizures? (?:started|began)|"
                r"convuls\w+|mirgi (?:ka )?daura|paralys\w+|fit (?:aa gaya|aa gayi|pad gaya)",
                r"anaphyla\w+|allergic reaction|allergy attack|(?:swelling|swollen) (?:of|in) (?:the |his |her )?"
                r"(?:face|throat|tongue|lips)|throat (?:is )?(?:closing|swelling)|face (?:is )?swelling|epipen|"
                r"adrenaline injection|reaction to (?:the )?(?:injection|food|medicine|peanuts?|nuts?)|"
                r"allergy (?:ka|se) (?:reaction|attack|saans)|gala (?:band|sooj)\w*|chehra sooj\w*|munh sooj\w*",
                r""
                + _PERSON
                + r"\s+(?:has |just |suddenly )?(?:fainted|collapsed|passed out|blacked out|fell unconscious|"
                r"went unconscious|stopped breathing|turned blue|isn'?t waking up|won'?t wake up|"
                r"is having a (?:fit|seizure|stroke|heart attack))|(?:fainted|passed out|collapsed) (?:in|at|during|on) "
                r"(?:the )?(?:gym|pool|class|clinic|ward|site|restaurant|hall|court|ground|field|bus|workshop|factory|"
                r"shop|lab|dialysis|buffet|wedding)",
                r"hosh (?:nahi|nahin|kho)|hosh mein nahi|chakkar (?:kha|aa) kar gir\w*|uth nahi raha|uth nahi rahi|"
                r"hil nahi raha|saans (?:band|ruk)\w*",
                r"(?:crush(?:ed)? (?:in|by) (?:the )?crowd|people (?:are )?(?:being )?(?:crushed|trampled)|trampled|"
                r"crowd (?:crush|surge)|stampede|bhag ?dad)",
                r"(?:stabbed|knifed|shot dead|got shot|was shot|gunshots?|gun ?fire|open(?:ed)? fire)",
            ),
            (
                r"لفٹ[^.?!\n]{0,20}پھنس|پھنس[^.?!\n]{0,20}لفٹ",
                r"گیس (?:لیک|کی بو|رس|کا اخراج|نکل)|امونیا|کلورین (?:لیک|گیس)|زہریلی گیس|دم گھٹ|سانس لینے میں",
                r"کرنٹ لگ|بجلی (?:کا|کے) جھٹکے?|بجلی لگ",
                r"(?:چھت|دیوار|عمارت|مارکی|شیڈ|سلیب|پل)\s+(?:گر|منہدم|بیٹھ)|ملبے|ملبہ|مزدور\s+دب|دب گئے|(?<![؀-ۿ])کان\s+(?:میں|بیٹھ|منہدم)",
                r"(?:بچہ|بچی|آدمی|بندہ|لڑکا|لڑکی)[^.?!\n]{0,15}ڈوب|پانی میں (?:گر|ڈوب)|پول میں (?:گر|ڈوب)",
                r"سانپ (?:نے )?(?:کاٹ|ڈس)|سانپ کاٹ|بچھو (?:نے )?(?:کاٹ|ڈنک)|کتے نے کاٹ",
                r"(?:ہاتھ|انگلی|بازو|ٹانگ|پاؤں)[^.?!\n]{0,20}(?:مشین|پریس|بیلٹ)[^.?!\n]{0,15}(?:پھنس|کٹ)|انگلی کٹ|ہاتھ کٹ|مشین میں پھنس",
                r"خون (?:بہ|نہیں رک)|بہت خون|خون بہنا",
                r"زہر (?:کھا|پی|چڑھ)|زہر خورانی|زہریلی دوا|کیڑے مار دوا (?:پی|کھا)",
                r"لو لگ|ہیٹ سٹروک|لو لگنے",
                r"سینے میں درد|دل کا دورہ|ہارٹ اٹیک|مرگی کا دورہ|فالج",
                r"الرجی (?:کا|سے) (?:شدید )?(?:ری ایکشن|حملہ)|الرجک ری ایکشن|ایلرجی ری ایکشن|گلا بند|چہرہ سوج|منہ سوج",
                r"ہوش (?:نہیں|کھو)|ہوش میں نہیں|چکر کھا کر|بس (?:الٹ|الٹی)|گاڑی الٹ|ٹرک الٹ|ایکسیڈنٹ|حادثہ (?:ہو|پیش)",
                r"بھگدڑ|کچلے گئے",
                r"طعنة|طعن|فائرنگ",
            ),
        ),
    ),
    (
        Emergency.MEDICAL,
        _rx(
            (),
            (
                r"عالق\w*\s+(?:في|داخل)\s+(?:ال)?(?:مصعد|ليفت|أسانسير)|المصعد\s+(?:سقط|هوى)",
                r"تسرب\s+(?:ال)?(?:غاز|أمونيا|امونيا|كلور)|رائحة\s+(?:ال)?غاز|غاز سام|اختناق|ضيق (?:في )?التنفس",
                r"صعق(?:ة)?\s+كهربائي(?:ة)?|صعقه كهربائية|صعقة كهربائية|تعرض لصعقة|صُعق",
                r"انهار(?:ت)?\s+(?:ال)?(?:سقف|جدار|حائط|مبنى|بناء|مظلة|منصة|حفرة|نفق)|انهيار\s+(?:ال)?(?:سقف|جدار|مبنى|حفرة|نفق|منجم)|"
                r"تحت (?:ال)?أنقاض|تحت الانقاض",
                r"(?:ال)?(?:طفل|ولد|شخص|رجل|سباح|طالب|ضيف|عامل)\s+(?:غرق|يغرق|غارق)|غرق(?:ت|وا)?\s+(?:في|ب)\s*(?:ال)?"
                r"(?:مسبح|بحر|نهر|ماء|بركة)|غريق",
                r"لدغ(?:ة|ه|ت)?\s*(?:ال)?(?:ثعبان|أفعى|افعى|عقرب|كلب)|عضة كلب",
                r"(?:يد|يده|يدها|إصبع|أصبع)\w*[^.?!\n]{0,15}(?:ال)?(?:آلة|الة|ماكينة|مكبس)|بتر|بُترت|انحشرت",
                r"نزيف\s+(?:شديد|حاد)|ينزف بشدة|نزيف دم|نزف",
                r"تسمم|ابتلع سم|شرب سم|سم (?:ال)?(?:فئران|حشري)",
                r"انقلاب\s+(?:ال)?(?:حافلة|شاحنة|سيارة|باص)|انقلبت\s+(?:ال)?(?:حافلة|شاحنة|سيارة|باص)|دهس",
                r"ضربة\s+(?:ال)?(?:شمس|حرارة)",
                r"[أا]لم\s+(?:في|بال)\s*(?:ال)?صدر|نوبة قلبية|جلطة|سكتة (?:قلبية|دماغية)|تشنجات",
                r"حساسية (?:شديدة|مفرطة)|صدمة تحسسية|تورم\s+(?:ال)?(?:وجه|حلق|لسان)|تفاعل تحسسي",
                r"أغمي (?:عليه|عليها|على)|اغمي (?:عليه|عليها|على)|مغمى عليه|فقد(?:ت)? الوعي|لا يتنفس|لا تتنفس|توقف قلب",
                r"تدافع|تزاحم شديد",
                r"طعنة|إطلاق النار|اطلاق النار|فتح النار",
            ),
        ),
    ),
    (
        Emergency.VIOLENCE,
        _rx(
            (
                r"(?:are|is|were) being (?:robbed|held up)|being (?:threatened|attacked) by (?:a |the |some )?(?:gang|group of men|men|mob|goons?|gunmen|robbers?|armed)",
                r"threatened by (?:a |the )?(?:gang|group|men|mob|goons?|gunmen|robbers?)|gang (?:is|are) (?:here|outside|"
                r"threatening|attacking|inside)|mob (?:is |are )?(?:attacking|burning|outside|breaking)|hostage|gunman|"
                r"active shooter|terrorist attack|"
                r"(?:bomb|bomb scare|bomb blast|suspicious (?:package|bag|device|parcel)|explosive (?:device|found|planted))|"
                r"bomb (?:threat|planted|found|in)|bomb (?:ki|ka) (?:dhamki|khabar)|bomb dhamki|bomb rakha",
                r"firing (?:ho rahi|ho gayi|started|is happening)|chaaku|chhuri (?:maar|se)|chura (?:maar|se)",
            ),
            (
                r"بم کی دھمکی|بم رکھا|بم دھماکہ|مشکوک (?:بیگ|پیکٹ|پارسل)|یرغمال|گینگ|غنڈے",
                r"تهديد\s+(?:ب)?(?:وجود\s+)?قنبلة|قنبلة|طرد مشبوه|حقيبة مشبوهة|رهينة|إرهابي|عصابة",
            ),
        ),
    ),
    (
        Emergency.GENERIC,
        _rx(
            (
                r"(?:plane|aircraft|helicopter|aeroplane|jet|flight|chopper) (?:has |just )?(?:crash\w*|went down|is going down)|"
                r"plane crash|air ?crash|emergency landing|(?:man|person|passenger|someone|guest|child|crew|swimmer|diver|"
                r"fisherman|worker) (?:has |just |fell |went |is )*overboard|man overboard|"
                r"(?:boat|ship|launch|vessel|ferry|dhow|yacht|trawler) (?:is |has |was |just )*(?:sinking|sank|capsized|"
                r"overturned|taking (?:on )?water|aground)|boat sinking|sinking (?:boat|ship)|capsized",
                r"(?:earthquake|landslide|tsunami|cyclone|tornado|cloudburst) (?:just )?(?:hit|hits|happened|is hitting|struck|has hit)|"
                r"there (?:is|was) an? (?:earthquake|landslide|flood)|(?:earthquake|zalzala) (?:aa gaya|aaya|ho raha)",
                r"jahaz\s+(?:gir|crash)\w*|kashti\s+(?:doob|ult)\w*|boat\s+(?:doob|ult)\w*|samandar mein gir\w*|"
                r"sailab (?:aa|aya)|seelab (?:aa|aya)|zalzala (?:aa|aya)|toofan aa",
            ),
            (
                r"جہاز\s+(?:گر|تباہ|کریش)|طیارہ\s+(?:گر|تباہ)|کشتی\s+(?:ڈوب|الٹ)|بوٹ\s+ڈوب|سمندر میں گر|ایمرجنسی لینڈنگ|سیلاب آ|زلزلہ آ",
                r"تحطم(?:ت)?\s+(?:ال)?طائرة|سقطت\s+(?:ال)?طائرة|هبوط اضطراري|غرق(?:ت)?\s+(?:ال)?(?:قارب|سفينة|مركب)|"
                r"(?:ال)?(?:قارب|سفينة|مركب)\s+(?:يغرق|تغرق|غرق)|انقلب\s+(?:ال)?قارب|سقط\s+(?:شخص\s+)?في البحر|حدث (?:زلزال|فيضان)|فيضان (?:في|داخل)|زلزال (?:ضرب|حدث)",
            ),
        ),
    ),
)
# "flood in the godown" alone must match, "flood insurance" must not: the generic group above
# needs the place, so a bare "flood" is checked here.
_FLOOD = re.compile(
    r"\b(?:flood(?:ing|ed)? (?:in|at|inside|has hit|hit)\b|water (?:is )?(?:rising|entering|inside)|"
    r"sailab (?:aa|agaya|a gaya))",
    re.IGNORECASE,
)
TRADE_EMERGENCY_PATTERNS = TRADE_EMERGENCY_PATTERNS + ((Emergency.GENERIC, _FLOOD),)

# Self-harm and safeguarding are checked first (the person's safety before anything else); the rest
# keep their order after the original patterns.
_SAFE_FIRST = tuple(
    p for p in TRADE_EMERGENCY_PATTERNS if p[0] in (Emergency.SELF_HARM, Emergency.SAFEGUARDING)
)
_SAFE_REST = tuple(
    p for p in TRADE_EMERGENCY_PATTERNS if p[0] not in (Emergency.SELF_HARM, Emergency.SAFEGUARDING)
)
EMERGENCY_PATTERNS = _SAFE_FIRST + EMERGENCY_PATTERNS + _SAFE_REST

EMERGENCY_TEXT = {
    "en": {
        Emergency.FIRE: "I can't help with emergencies. Please call {fire} now.",
        Emergency.MEDICAL: "I can't help with emergencies. Please call {ambulance} for an ambulance now.",
        Emergency.VIOLENCE: "I can't help with emergencies. Please call {police} now and get to safety.",
        Emergency.GENERIC: "I can't help with emergencies. Please call {police} now.",
        Emergency.SAFEGUARDING: (
            "I'm sorry, this needs a person, not me, and I can't help with it. If anyone is in danger "
            "right now, please call {police}. Otherwise please speak to the proper authority today: your "
            "safeguarding lead or child protection service. I've flagged this to the Workzap team. "
            "I'll leave the business side until you tell me it's handled."
        ),
        Emergency.SELF_HARM: (
            "I'm sorry things are this heavy. I'm an AI and can't help with this, but please talk to "
            "someone you trust, or call {police} if you're in danger. I'm here for the business side "
            "whenever you want."
        ),
    },
    "roman_ur": {
        Emergency.FIRE: "Main emergency mein madad nahi kar sakta. Meherbani karke abhi {fire} par call karein.",
        Emergency.MEDICAL: "Main emergency mein madad nahi kar sakta. Meherbani karke abhi ambulance ke liye {ambulance} par call karein.",
        Emergency.VIOLENCE: "Main emergency mein madad nahi kar sakta. Meherbani karke abhi {police} par call karein aur mehfooz jagah par chale jayein.",
        Emergency.GENERIC: "Main emergency mein madad nahi kar sakta. Meherbani karke abhi {police} par call karein.",
        Emergency.SAFEGUARDING: (
            "Mujhe afsos hai, is ke liye insaan chahiye, main madad nahi kar sakta. Agar kisi ko abhi khatra hai "
            "to {police} par call karein. Warna aaj hi munasib idare se baat karein: apne safeguarding lead ya "
            "child protection se. Maine ye Workzap ki team ko bhej diya hai. Jab aap bataein ke masla sambhal "
            "liya gaya hai, tab business ki baat karenge."
        ),
        Emergency.SELF_HARM: (
            "Mujhe afsos hai ke halaat itne bhaari hain. Main AI hoon aur is mein madad nahi kar sakta. "
            "Kisi bharose ke insaan se baat karein, ya khatre mein hon to {police} par call karein. "
            "Business ki taraf main jab chahein haazir hoon."
        ),
    },
    "ar": {
        Emergency.FIRE: "لا أستطيع المساعدة في حالات الطوارئ. يرجى الاتصال بـ {fire} الآن.",
        Emergency.MEDICAL: "لا أستطيع المساعدة في حالات الطوارئ. يرجى الاتصال بـ {ambulance} لطلب الإسعاف الآن.",
        Emergency.VIOLENCE: "لا أستطيع المساعدة في حالات الطوارئ. يرجى الاتصال بـ {police} الآن والانتقال إلى مكان آمن.",
        Emergency.GENERIC: "لا أستطيع المساعدة في حالات الطوارئ. يرجى الاتصال بـ {police} الآن.",
        Emergency.SAFEGUARDING: (
            "يؤسفني ذلك، فهذا الأمر يحتاج إلى شخص وليس إلي ولا أستطيع المساعدة فيه. إن كان أي شخص في خطر "
            "الآن فاتصل بـ {police}. وإلا فتحدث اليوم مع الجهة المختصة: مسؤول الحماية لديكم أو جهة حماية الطفل. "
            "لقد أبلغت فريق Workzap. سأترك الجانب المتعلق بعملك حتى تخبرني أنه تمت معالجة الأمر."
        ),
        Emergency.SELF_HARM: (
            "يؤسفني أن الأمور صعبة إلى هذا الحد. أنا ذكاء اصطناعي ولا أستطيع المساعدة في هذا، "
            "لكن تحدّث مع شخص تثق به، أو اتصل بـ {police} إن كنت في خطر. أنا هنا للجانب المتعلق "
            "بعملك متى شئت."
        ),
    },
}


def emergency(text: str) -> Emergency | None:
    """The kind of emergency the message describes, or None. Self-harm is checked first."""
    said = " ".join((text or "").split())
    for kind, pattern in EMERGENCY_PATTERNS:
        if pattern.search(said):
            return kind
    return None


# Where someone in distress should call (spec X4): Rescue 1122 in Pakistan, 999, 911.
CRISIS_LINE = {"PK": "1122", "AE": "999", "CA": "9-8-8 (or 911 if you're in danger)"}


def emergency_reply(
    kind: Emergency, country: str | None, language: str | None, fixed: str | None = None
) -> str:
    """The fixed emergency answer with the person's local numbers (every country when unknown).
    `fixed` is the language of the person's message among the eight priority languages."""
    from app.modules.pi import fixed_lines

    table = EMERGENCY_TEXT.get(language or "en", EMERGENCY_TEXT["en"])
    template = table[kind]
    own = fixed_lines.EMERGENCY.get(fixed or "")
    if own and kind in (Emergency.FIRE, Emergency.MEDICAL, Emergency.VIOLENCE, Emergency.GENERIC):
        template = own[kind.value]
    if country in NUMBERS:
        numbers = NUMBERS[country]
        police = (
            CRISIS_LINE.get(country, numbers["police"])
            if kind == Emergency.SELF_HARM
            else numbers["police"]
        )
        return template.format(
            fire=f"{numbers['fire']} (fire)",
            ambulance=numbers["ambulance"],
            police=police,
        )
    wide = fixed_lines.LOCAL_NUMBER.get(fixed or "", "your local emergency number ({numbers})")
    wide = wide.format(numbers=ALL_COUNTRIES)
    return template.format(fire=wide, ambulance=wide, police=wide)


# --- personal data (R-PRIV-01 to 03, R-PAY-02, spec 6.3) --------------------------------------


class Pii(StrEnum):
    CARD = "card"
    SECRET = "secret"
    ID = "id"
    ACCOUNT = "account"
    CONTACT = "contact"
    CHILD = "child"
    NAME = "name"  # a third party's name: kept as their role only (R-PRIV-01)


@dataclass
class Redaction:
    text: str
    kinds: list[Pii] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.kinds)


PLACEHOLDER = {
    Pii.CARD: "[card number removed]",
    Pii.SECRET: "[password or code removed]",
    Pii.ID: "[ID number removed]",
    Pii.ACCOUNT: "[account number removed]",
    Pii.CONTACT: "[contact detail removed]",
    Pii.CHILD: "[child detail removed]",
    Pii.NAME: "[name removed]",
}

CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){13,19}(?![\d-])")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,6}(?: ?[A-Z0-9]{1,4})?\b")
ACCOUNT_LABEL = re.compile(
    r"\b(?:account|acct|a/c)\s*(?:number|no\.?|#)?\s*[:=\-]?\s*\d[\d -]{7,}\d", re.IGNORECASE
)
CNIC = re.compile(r"\b\d{5}-\d{7}-\d\b")
CNIC_LABELLED = re.compile(r"\bcnic\W{0,4}\d{13}\b", re.IGNORECASE)
EMIRATES_ID = re.compile(r"\b784-?\d{4}-?\d{7}-?\d\b")
LABELLED_ID = re.compile(
    # The label is a whole word ("sin" is not the start of "since" or "single") and the value holds
    # at least one digit ("my passport is expired" is not a passport number).
    r"\b(?:passport|sin|social insurance)\b(?: (?:no|number|#))?\W{0,4}"
    r"(?=[A-Z0-9 -]{0,13}\d)[A-Z0-9][A-Z0-9 -]{5,12}[A-Z0-9]\b",
    re.IGNORECASE,
)
# "my OTP is 4421", "password: Hunter22" (said outright), or "otp 4421" (a value with a digit).
# Not "password manager" or "pin code of the shop".
_TOKEN = r"[A-Za-z0-9@#$!%^&*._-]{3,}"
SECRET = re.compile(
    r"\b(?:password|passcode|pin|otp|cvv|cvc|one[- ]time (?:code|password))\b"
    rf"(?:\s*(?:is|was|:|=|hai|ye hai)\s*[:=]?\s*({_TOKEN})"
    rf"|\s+((?=[A-Za-z0-9@#$!%^&*._-]*\d){_TOKEN}))",
    re.IGNORECASE,
)
# The same in Arabic and Urdu script: "رمز التحقق 5521", "الرمز: 5521", "پاس ورڈ ہے 8832", "او ٹی پی 4421".
SECRET_NATIVE = re.compile(
    r"(?:رمز(?:\s+التحقق|\s+الدخول|\s+السري)?|كلمة\s+(?:ال)?(?:مرور|سر)|باسورد|پاس\s*ورڈ|پن\s*کوڈ|"
    r"او\s*ٹی\s*پی|اوٹی\s*پی)\s*(?:هو|هي|ہے|:|=)?\s*[:=]?\s*(\d{3,8})(?!\d)"
)
THIRD_PARTY = re.compile(
    r"\b(?:his|her|their|customer'?s|supplier'?s|manager'?s|staff'?s|client'?s|my (?:manager|staff|brother|"
    r"sister|wife|husband|partner|customer|supplier|accountant|driver|cashier))\b[^.\n]{0,40}?"
    r"(?:number|phone|mobile|cell|whatsapp|email|e-mail|contact)\W{0,3}(?:(?:is|are|hai)\W{0,3})?"
    r"(\+?\d[\d ()-]{7,}\d|[\w.+-]+@[\w-]+\.[\w.-]+)",
    re.IGNORECASE,
)
# A child's name ("my son Ali got ...", "my daughter named Sara") and their marks (RT21).
CHILD_NAME = re.compile(
    r"\b(?i:my|our|his|her)\s+(?i:son|daughter|child|kid|student|pupil)\s+(?i:named\s+|called\s+)?"
    r"([A-Z][a-z]{2,})\b(?=\s+(?i:got|gets|scored|is\s+in|studies|has|was|failed|passed|ki|ka)\b|[,.])"
)
CHILD_MARKS = re.compile(
    r"\b(?i:grades?|marks|score[sd]?|got|result)\b[^.\n]{0,15}?(\d{1,3}\s?%|\d{1,3}/\d{2,3}|\b[A-F][+-]?(?=\s|[.,]|$))"
)
# --- more personal data found by the trade audit (R-PRIV-01, R-PRIV-02) ----------------------------
_ID_VALUE = r"(?=[A-Za-z0-9-]*\d)[A-Za-z0-9][A-Za-z0-9-]{4,24}[A-Za-z0-9]"
_NUMBER_WORD = r"(?:no\.?|number|num|#|id)"
# Labels that mean an ID on their own ("visa AB1234567") and labels that need "no" or "number"
# ("meter number 123456"), so "meter reading" or "my licence is valid" are left alone.
ID_STRONG = re.compile(
    r"\b(?:cnic|nicop|nic|passport|visa|pnr|chassis|vin|iqama|emirates id|eid|id card|national id|identity card|"
    rf"labou?r card|work permit)\b(?:\s*{_NUMBER_WORD}\b)?\W{{0,4}}(?:(?:is|was|hai|ye hai)\W{{0,3}})?({_ID_VALUE})",
    re.IGNORECASE,
)
ID_WEAK = re.compile(
    r"\b(?:meter|mr|mrn|reg|registration|plate|number plate|licen[cs]e|driving licen[cs]e|dl|file|policy|consumer|"
    r"reference|booking(?: ref(?:erence)?)?|engine|patient id|medical record|boarding pass)\b"
    rf"\s*{_NUMBER_WORD}\b\W{{0,4}}(?:(?:is|was|hai|ye hai)\W{{0,3}})?({_ID_VALUE})",
    re.IGNORECASE,
)
CNIC_SPACED = re.compile(r"(?<!\d)\d{5}[ -]\d{7}[ -]\d(?!\d)")
CNIC_BARE = re.compile(r"(?<![\d-])\d{13}(?![\d-])")
PHONE = re.compile(
    r"(?<![\w+-])(?:(?:\+|00)?92[ -]?3\d{2}[ -]?\d{7}|03\d{2}[ -]?\d{7}"
    r"|(?:\+|00)?971[ -]?5\d[ -]?\d{3}[ -]?\d{4}|05\d[ -]?\d{3}[ -]?\d{4}"
    r"|(?:\+?1[ -]?)?\(?[2-9]\d{2}\)?[ -]\d{3}[ -]\d{4})(?!\d)"
)
# The person's own number, given so pi can reach them, is theirs to share: it stays.
OWN_NUMBER = re.compile(
    r"(?:\b(?:call|text|msg|message|whatsapp|reach|contact|ring|phone) me\b[^.\n]{0,12}"
    r"|\bmy (?:own |personal )?(?:number|phone|mobile|cell|whatsapp|contact)\b[^.\n]{0,15})$",
    re.IGNORECASE,
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
CARD_EXPIRY = re.compile(
    r"\b(?:exp(?:iry|ires|iration)?|valid (?:thru|till|until))\W{0,3}\d{1,2}\s?/\s?\d{2,4}\b",
    re.IGNORECASE,
)
_NOT_PLATES = (
    r"PKR|USD|AED|CAD|EUR|GBP|SAR|RS|PO|SKU|GST|VAT|FBR|NTN|STRN|NO|ID|ISO|SMS|GB|MB|KB|TB|KG|KW|KVA|MM|CM|HP|PCS|"
    r"QTY|INV|REF|TAX|IBAN|FY|UAE|USA|PAK|JAN|FEB|MAR|APR|JUN|JUL|AUG|SEP|OCT|NOV|DEC|AM|PM|BS|NIC|CNIC|OTP|PIN|"
    r"CVV|CVC|SIN|DL|MR|PNR|CCTV|GPS|USB|LED|SIM|POS|ERP|CRM|API|ATM|UPS|TV|AC|PC|HD|FM|DVR|NVR|IP|SSD|HDD|RAM|"
    r"COVID|WIFI|LAN|WAN|VPN|KPI|ROI|SLA|TAT|MOQ|COD|EMI|ETA|GRN|PRN|LC|TT|DD|CNC|PLC|HVAC"
)
PLATE = re.compile(rf"\b(?!(?:{_NOT_PLATES})\b)[A-Z]{{2,4}}[- ]\d{{2,4}}(?:[- ]\d{{2,4}})?\b")
DOOR_CODE = re.compile(
    r"\b(?:door|gate|entry|access|alarm|safe|locker|lock|keypad|lockbox|key ?box|building|security|garage|"
    r"combination|cabinet|wi-?fi|room)\s*(?:code|pin|passcode|combination|password)\b\W{0,4}"
    r"(?:(?:is|was|hai|:|=)\W{0,3})?((?=[A-Za-z0-9#*-]*\d)[A-Za-z0-9#*-]{3,})",
    re.IGNORECASE,
)
_ROLES = (
    r"patient|guest|student|worker|staff|doctor|nurse|driver|passenger|tenant|resident|client|customer|member|"
    r"employee|labou?rer|teacher|pupil|manager|cashier|supplier|vendor|neighbou?r|parent|guard|cook|chef|coach|"
    r"trainer|pilot|captain|inspector|officer|accountant|engineer|contractor|technician|mechanic|waiter|"
    r"receptionist|nanny|maid|buyer|landlord|mazdoor|mareez|ustad"
)
_NOT_NAMES = (
    r"Service|Services|Support|Records?|Care|Team|Satisfaction|Experience|Retention|Feedback|Complaints?|Data|App|"
    r"Portal|List|Management|Wifi|Room|Rooms|Number|Info|Meetings?|Mode|Policy|Journey|Accounts?|Relations|Loyalty|"
    r"Acquisition|Referral|Engagement|Onboarding|Check|Count|Id|Ids|Booking|Bookings|Card|Cards|Name|Names|Details|"
    r"Profile|Database|Pass|Area|Zone|Lounge|Parking|Wing|Floor|Desk|Hotline|Helpline|Union|Council|Association|"
    r"Committee|Manager|Staff|Worker|Workers|Customer|Customers|Guest|Guests|Patient|Patients|Student|Students|"
    r"Mr|Mrs|Ms|Miss|Dr|Sir|Madam|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|January|February|March|"
    r"April|May|June|July|August|September|October|November|December|The|This|That|These|Those|And|But|Or|If|"
    r"When|Who|What|Why|How|Please|Thanks|Thank"
)
ROLE_NAME = re.compile(
    rf"\b(?P<role>{_ROLES})\s+(?:(?:Mr|Mrs|Ms|Miss|Mx|Dr|Sir|Madam|Haji|Hajji|Sheikh|Syed|Sayed|Mian|Malik|Ch|Rana|"
    rf"Chaudhry|Begum|Sahib|Saheb|Muhammad|Mohammad)\.?\s+)?(?!(?:{_NOT_NAMES})\b)[A-Z][a-z]{{1,}}"
    rf"(?:\s+(?!(?:{_NOT_NAMES})\b)[A-Z][a-z]{{1,}}){{0,2}}"
)
ROMAN_ROLE_NAME = re.compile(
    r"(?P<pre>\b(?i:manager|munshi|accountant|supervisor|staff|employee|mazdoor|driver|cashier|"
    r"waiter|biwi|wife|shohar|husband|bhai|behan|beta|beti|father|mother|boss|malik|supplier|"
    r"customer|client|partner|doctor|nurse|teacher)\s+(?i:ka|ki|ke)\s+(?i:naam|name)\s+"
    r"(?:(?i:hai|he)\s+)?)"
    rf"(?!(?:{_NOT_NAMES})\b)[A-Z][a-z]{{1,}}(?:\s+(?!(?:{_NOT_NAMES})\b)[A-Z][a-z]{{1,}}){{0,2}}"
)
DOCTOR_NAME = re.compile(
    rf"\b(?:Dr\.?|Doctor)\s+(?!(?:{_NOT_NAMES})\b)[A-Z][a-z]{{1,}}(?:\s+[A-Z][a-z]{{1,}})?"
)
_ROMAN_ROLES = {"mazdoor", "mareez", "ustad"}
_DETERMINER_TAIL = re.compile(
    r"\b(?:my|our|the|a|an|his|her|their|this|that|one|each|every|another|any)\s+$", re.IGNORECASE
)

CONTACT_CARD = re.compile(r"\s*Contact card shared:", re.IGNORECASE)
LOCATION_PIN = re.compile(r"^\s*Location shared:.*", re.IGNORECASE | re.DOTALL)
FILLER_WORDS = re.compile(r"\[[^\]]+removed\]")


def luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def redact_pii(text: str) -> Redaction:
    """The text with card numbers, passwords and codes, ID and account numbers, and third parties'
    contact details taken out, and which kinds were found."""
    kinds: list[Pii] = []

    def add(kind: Pii) -> None:
        if kind not in kinds:
            kinds.append(kind)

    # A shared contact card is other people's details (R-PRIV-04, spec 6.10): none of it is kept.
    if CONTACT_CARD.match(text or ""):
        add(Pii.CONTACT)
        return Redaction("[contact card removed]", kinds)
    # A location pin is not kept as exact coordinates either; pi never asks for one.
    text = LOCATION_PIN.sub("[a location was shared]", text or "")

    def cards(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and luhn(digits):
            add(Pii.CARD)
            return PLACEHOLDER[Pii.CARD]
        return match.group()

    clean = CARD.sub(cards, text or "")

    def secret(match: re.Match[str]) -> str:
        value = match.group(1) or match.group(2)
        if value.lower() in {"code", "manager", "reset", "protected", "required"}:
            return match.group()  # "pin code of the shop", "password manager"
        add(Pii.SECRET)
        return match.group().replace(value, PLACEHOLDER[Pii.SECRET])

    clean = SECRET.sub(secret, clean)
    clean = SECRET_NATIVE.sub(secret, clean)
    for pattern, kind in (
        (CNIC, Pii.ID),
        (CNIC_LABELLED, Pii.ID),
        (EMIRATES_ID, Pii.ID),
        (LABELLED_ID, Pii.ID),
        (IBAN, Pii.ACCOUNT),
        (ACCOUNT_LABEL, Pii.ACCOUNT),
    ):
        clean, count = pattern.subn(PLACEHOLDER[kind], clean)
        if count:
            add(kind)

    def third(match: re.Match[str]) -> str:
        add(Pii.CONTACT)
        return match.group().replace(match.group(1), PLACEHOLDER[Pii.CONTACT])

    clean = THIRD_PARTY.sub(third, clean)

    def child(match: re.Match[str]) -> str:
        add(Pii.CHILD)
        return match.group().replace(match.group(1), PLACEHOLDER[Pii.CHILD])

    if CHILD_NAME.search(clean):  # marks only count when the talk is about someone's child
        clean = CHILD_NAME.sub(child, clean)
        clean = CHILD_MARKS.sub(child, clean)

    # More identifiers (labelled in any form, or bare), phones, e-mail, card expiry, plates, codes.
    def labelled(match: re.Match[str]) -> str:
        add(Pii.ID)
        return match.group().replace(match.group(1), PLACEHOLDER[Pii.ID])

    clean, count = CNIC_SPACED.subn(PLACEHOLDER[Pii.ID], clean)
    if count:
        add(Pii.ID)
    clean = ID_STRONG.sub(labelled, clean)
    clean = ID_WEAK.sub(labelled, clean)
    clean, count = CNIC_BARE.subn(PLACEHOLDER[Pii.ID], clean)
    if count:
        add(Pii.ID)

    def phone(match: re.Match[str]) -> str:
        if OWN_NUMBER.search(clean_before(match)):
            return match.group()
        add(Pii.CONTACT)
        return PLACEHOLDER[Pii.CONTACT]

    def clean_before(match: re.Match[str]) -> str:
        return match.string[: match.start()]

    clean = PHONE.sub(phone, clean)
    clean, count = EMAIL.subn(PLACEHOLDER[Pii.CONTACT], clean)
    if count:
        add(Pii.CONTACT)
    if Pii.CARD not in kinds:  # next to a removed card number the date alone is harmless (kept)
        clean, count = CARD_EXPIRY.subn(PLACEHOLDER[Pii.CARD], clean)
        if count:
            add(Pii.CARD)
    clean, count = PLATE.subn(PLACEHOLDER[Pii.ID], clean)
    if count:
        add(Pii.ID)

    def code(match: re.Match[str]) -> str:
        add(Pii.SECRET)
        return match.group().replace(match.group(1), PLACEHOLDER[Pii.SECRET])

    clean = DOOR_CODE.sub(code, clean)

    # A third party introduced by a role keeps only the role: "patient Ayesha Khan" -> "the patient".
    def named(match: re.Match[str]) -> str:
        add(Pii.NAME)
        role = match.groupdict().get("role") or "doctor"
        if role.lower() in _ROMAN_ROLES:
            return role
        if _DETERMINER_TAIL.search(match.string[: match.start()]):
            return role
        return f"the {role}"

    clean = ROLE_NAME.sub(named, clean)
    clean = DOCTOR_NAME.sub(named, clean)

    def roman_named(match: re.Match[str]) -> str:
        add(Pii.NAME)
        return f"{match.group('pre')}[name removed]"

    clean = ROMAN_ROLE_NAME.sub(roman_named, clean)
    return Redaction(clean, kinds)


def substantive(redacted: str) -> bool:
    """Whether anything but the removed details is left to answer (three real words or more)."""
    return len(FILLER_WORDS.sub(" ", redacted).split()) >= 3


PII_TEXT = {
    "en": {
        Pii.CARD: "Please don't send card numbers here. I never need them, and payment never happens in this chat. I've left that out of my notes.",
        Pii.SECRET: "Please don't send passwords, codes or PINs here. I never need them. I've left that out of my notes.",
        Pii.ID: "Please don't send ID numbers here. I don't need them. I've left that out of my notes.",
        Pii.ACCOUNT: "Please don't send bank account numbers here. I don't need them, and bank details only ever come on an approved quote. I've left that out of my notes.",
        Pii.CONTACT: "I don't need other people's contact details here. They can message me directly if they'd like. I've left that out of my notes.",
        Pii.CHILD: "Please don't share children's names or grades here. I only need the business problem, for example how results are tracked. I've left that out of my notes.",
        Pii.NAME: "I only need roles, not people's names, so I've noted it as the role only, for example \"the patient\".",
    },
    "roman_ur": {
        Pii.CARD: "Meherbani karke yahan card number na bhejein. Mujhe in ki zaroorat nahi, aur payment is chat mein kabhi nahi hoti. Maine ise apne notes se nikaal diya hai.",
        Pii.SECRET: "Meherbani karke yahan password, code ya PIN na bhejein. Mujhe in ki zaroorat nahi. Maine ise apne notes se nikaal diya hai.",
        Pii.ID: "Meherbani karke yahan ID number na bhejein. Mujhe in ki zaroorat nahi. Maine ise apne notes se nikaal diya hai.",
        Pii.ACCOUNT: "Meherbani karke yahan bank account number na bhejein. Mujhe in ki zaroorat nahi, bank details sirf approved quote par aati hain. Maine ise apne notes se nikaal diya hai.",
        Pii.CONTACT: "Mujhe doosron ki contact details ki zaroorat nahi. Wo chahein to mujhe seedha message kar sakte hain. Maine ise apne notes se nikaal diya hai.",
        Pii.CHILD: "Meherbani karke yahan bachon ke naam ya marks na bhejein. Mujhe sirf business ka masla chahiye, masalan natayej ka hisaab kaise rakha jata hai. Maine ise apne notes se nikaal diya hai.",
        Pii.NAME: 'Mujhe logon ke naam nahi, sirf unka kirdaar chahiye, is liye maine sirf kirdaar note kiya hai, masalan "the patient".',
    },
}


def pii_notice(
    kinds: list[Pii], told: list[str], language: str | None, fixed: str | None = None
) -> tuple[str, list[str]]:
    """The reminder for kinds not yet reminded in this conversation, and the updated list: one reminder per
    kind per conversation, never a scolding (spec 6.3). `fixed` is the language of the person's message among
    the eight priority languages: the card and ID reminders exist in all of them."""
    from app.modules.pi import fixed_lines

    table = PII_TEXT.get(language or "en", PII_TEXT["en"])
    fresh = [k for k in kinds if k.value not in told]
    own = {Pii.CARD: "card", Pii.ID: "id"}

    def said(kind: Pii) -> str:
        if kind in own and fixed in fixed_lines.LINES[own[kind]]:
            return fixed_lines.LINES[own[kind]][str(fixed)]
        return table[kind]

    return " ".join(said(k) for k in fresh), [*told, *(k.value for k in fresh)]


# --- advice that is not pi's to give (R-ADV-01 to 05) -----------------------------------------


class Advice(StrEnum):
    LEGAL = "legal"
    TAX = "tax"
    FINANCIAL = "financial"
    MEDICAL = "medical"
    VETERINARY = "veterinary"
    ENGINEERING = "engineering"  # structural, electrical, machine-guarding safety
    CHEMICAL = "chemical"  # refrigerant, pool, pesticide dosing
    AGRONOMY = "agronomy"  # crops, fertiliser, animal feed rations
    IMMIGRATION = "immigration"
    CUSTOMS = "customs"  # duty, HS codes, sanctions
    RELIGIOUS = "religious"
    VEHICLE = "vehicle"  # vehicle safety
    VALUATION = "valuation"  # property and asset valuation
    FORMULATION = "formulation"


ADVICE_PATTERNS: tuple[tuple[Advice, re.Pattern[str]], ...] = (
    (
        Advice.VETERINARY,
        re.compile(
            r"\b(?:(?:what|which) injection|injection (?:do|dun|doon|lagao|lagana)|"
            r"(?:cow|buffalo|goat|sheep|camel|horse|animal)s? (?:is|are) sick|sick (?:cow|buffalo|goat|animal)|"
            r"bimar (?:gaye|gai|bhains|bakri|janwar))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.MEDICAL,
        re.compile(
            r"\b(?:what (?:dose|dosage)|which (?:medicine|tablet|drug|antibiotic)|how many (?:tablets|pills)|"
            r"dose (?:kitni|kya)|dawai (?:kaun|konsi)|can i give (?:my |the )?(?:child|baby|kid))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.TAX,
        re.compile(
            r"\b(?:how much (?:vat|tax|fbr|sales tax|gst|income tax|withholding)(?: should| do| must)?|"
            r"which tax|tax (?:rate|slab|treatment)|vat (?:rate|treatment)|tax kitna|"
            r"(?:how|can) (?:do )?i (?:avoid|reduce|save on) (?:tax|vat))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.FINANCIAL,
        re.compile(
            r"\b(?:should i (?:take|get|apply for) (?:a |an )?(?:loan|credit|financing|mortgage)|"
            r"which bank (?:should|is best|do you)|where (?:should|do) i invest|should i invest|"
            r"worth investing|loan le lun|invest kahan)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.LEGAL,
        re.compile(
            r"\b(?:is it (?:legal|illegal|allowed by law)|can i sue|sue (?:him|her|them)|"
            r"(?:fire|sack|terminate) (?:staff|him|her|them|an employee)[^.?!]{0,25}without notice|"
            r"is (?:the|my|this) contract (?:valid|legal)|legal (?:action|notice) against|qanooni|qanoon)\b|"
            r"قانوني|قانونی",
            re.IGNORECASE,
        ),
    ),
)

# Advice questions asked in Arabic, Urdu and Roman Urdu (R-ADV-01, spec 10.2 RT9).
ADVICE_PATTERNS = ADVICE_PATTERNS + (
    (
        Advice.TAX,
        re.compile(
            r"(?:كم (?:يجب|عليّ|علي) (?:أن )?أدفع ضريبة|كيف أتجنب الضريبة|نسبة (?:الضريبة|ضريبة)|"
            r"ٹیکس (?:کتنا|کیسے بچا)|کتنا ٹیکس|ٹیکس (?:چھپا|بچا|چوری|کم کر))"
            r"|\b(?:tax kaise bach\w*|tax kitna (?:dun|doon|dena)|tax bachane ka|"
            r"tax (?:chupa|chhupa|bacha|chori|kam kar)\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.MEDICAL,
        re.compile(
            r"(?:ما (?:هي )?الجرعة|أي دواء|كم حبة|کون سی دوا|دوا کتنی)"
            r"|\b(?:konsi dawai|kaun si dawai|dawai kitni)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Advice.FINANCIAL,
        re.compile(
            r"(?:هل (?:آخذ|اخذ) قرضًا|هل أستثمر|هل استثمر|قرض لینا چاہیے|سرمایہ کاری کروں)"
            r"|\b(?:loan lena chahiye|loan le lun|loan lun ya nahi|invest karun)\b",
            re.IGNORECASE,
        ),
    ),
)

_STRUCT = (
    r"(?:structure|structural|beam|column|slab|wall|roof|foundation|scaffold\w*|crane|lift|building|"
    r"load[- ]bearing|wiring|panel|earthing|cable|transformer|breaker|generator|boiler|pressure vessel|"
    r"rack|racking|shelving|mezzanine|stage|truss|formwork|trench|excavation|ladder|floor|bridge|shed|"
    r"canopy|platform|tower|hoarding)"
)
# Questions that need a licensed professional: the question shape ("is it safe", "how much", "which")
# is part of every pattern, so a business that merely deals in these things is not stopped.
ADVICE_PATTERNS = (
    (
        (
            Advice.ENGINEERING,
            _rx(
                (
                    r"is (?:it|this|the|my|our) (?:\w+ ){0,3}"
                    + _STRUCT
                    + r"\b[^.?!\n]{0,30}\b(?:safe|strong enough|stable|"
                    r"sound|compliant|up to code|overloaded)",
                    r"(?:will|can|does|would) (?:the |this |my |our )?(?:\w+ ){0,3}"
                    + _STRUCT
                    + r"\b[^.?!\n]{0,25}\b(?:hold|"
                    r"carry|support|take|bear|withstand)\b",
                    r"(?:what|which|how (?:big|thick|much|many)) (?:size|gauge|rating|amps?|ampere|kva|kw|mm|thickness|"
                    r"diameter|capacity|load|cable|wire|breaker|fuse|rebar|steel|concrete|mix|ratio|span|spacing)\b[^.?!\n]{0,30}"
                    r"\b(?:cable|wire|breaker|fuse|beam|column|slab|rebar|steel|concrete|foundation|generator|transformer|"
                    r"earthing|mcb|rcd|pipe|duct|panel|machine|motor)\b",
                    r"(?:structural|electrical) (?:safety|load|design|calculation|check)\b",
                    r"load (?:calculation|capacity|bearing)\b|safe working load|how to (?:size|rate|calculate) (?:the |a )?"
                    r"(?:cable|breaker|beam|column|slab|pipe|duct|load)",
                    r"machine guarding[^.?!\n]{0,40}\b(?:compliant|compliance|required|enough|legal|standard|osha|iso)",
                    r"(?:osha|iso 45001|nfpa|bs 7671|nec|ieee)\b[^.?!\n]{0,25}\b(?:compliant|compliance|requirement|require|"
                    r"required|meet)",
                    r"guard(?:s|ing)?\b[^.?!\n]{0,20}\b(?:compliant|compliance|osha|meet(?:s)? (?:the )?standard)",
                    r"(?:bridge|imarat|building|chhat|deewar|beam|column|lintel|slab|shed|stage|rack|crane)\b[^.?!\n]{0,25}"
                    r"\b(?:(?:kitna|kitni|kitne)\s+(?:wazan|load)|(?:load|wazan)\s+(?:kitna|kitni|kitne))\b",
                ),
                (
                    r"(?:هل|ما) (?:هذا|هذه)?\s*(?:ال)?(?:جسر|مبنى|سقف|عارضة|عمود|رف)[^.?!\n]{0,25}(?:آمن|امن|يتحمل)",
                ),
            ),
        ),
        (
            Advice.CHEMICAL,
            _rx(
                (
                    r"how (?:much|many)\s+(?:\w+\s+){0,2}(?:refrigerant|gas charge|chlorine|acid|ph (?:up|down)|chemicals?|"
                    r"pesticide|insecticide|herbicide|fungicide|weedicide|spray|bleach|sanitiser|sanitizer|disinfectant|"
                    r"stabili[sz]er|shock)\b[^.?!\n]{0,40}\b(?:add|put|use|mix|dose|spray|need|per|should)",
                    r"(?:which|what)\s+(?:pesticide|insecticide|herbicide|fungicide|spray|chemical)\b[^.?!\n]{0,30}"
                    r"\b(?:dose|dosage|use|spray|per acre|for)",
                    r"(?:pesticide|spray|chemical|chlorine|refrigerant) (?:dose|dosage|dosing|ratio|mixture|concentration)\b",
                    r"(?:safe|correct|right) (?:level|dose|dosage|concentration|ratio) (?:of|for) (?:chlorine|chemicals?|"
                    r"pesticide|refrigerant|acid)",
                    r"(?:chlorine|chemical|pesticide) (?:kitna|kitni)\b|spray (?:ki )?(?:dose|miqdar)|dawai (?:ka )?spray kitna",
                ),
                (r"(?:كم|ما) (?:كمية|جرعة)\s*(?:ال)?(?:كلور|مبيد|مبيدات|غاز التبريد)",),
            ),
        ),
        (
            Advice.AGRONOMY,
            _rx(
                (
                    r"(?:which|what)\s+(?:fertili[sz]er|seed|variety|crop|pesticide for (?:the )?crop|manure|urea|dap)\b"
                    r"[^.?!\n]{0,30}\b(?:use|apply|plant|sow|grow|for)",
                    r"when (?:should|do|to) (?:i|we)?\s*(?:sow|plant|harvest|irrigate|spray|fertili[sz]e)\b",
                    r"(?:feed|fodder|ration|diet) (?:ration|plan|mix|formula)?\b[^.?!\n]{0,25}\b(?:for my |for our |for the )?"
                    r"(?:cows?|buffalo(?:es)?|goats?|sheep|poultry|chickens?|broilers?|layers?|cattle|fish|dairy|animals?|"
                    r"camels?|horses?)\b|what (?:feed|ration|fodder)\b[^.?!\n]{0,30}\b(?:give|feed)",
                    r"kaun si (?:khaad|khad|fasal|beej)\b|(?:khaad|khad) kitni|fasal (?:kab|kaise) (?:boun|bona|lagaun|lagana)",
                ),
                (r"(?:أي|ما) (?:سماد|بذور|محصول)[^.?!\n]{0,20}(?:أستخدم|أزرع)",),
            ),
        ),
        (
            Advice.IMMIGRATION,
            _rx(
                (
                    r"(?:which|what)\s+visa\b|visa (?:category|type|application|eligibility|requirements?|extension|rules?)\b"
                    r"[^.?!\n]{0,40}\b(?:should|can|do|apply|need|eligible|qualify)|can i (?:get|apply for|sponsor) "
                    r"(?:a |an )?(?:visa|residency|work permit|pr|citizenship)|immigration (?:advice|rules?|law|status)|"
                    r"(?:will|can) (?:my|the) (?:visa|work permit|residency) (?:be )?(?:approved|extended|renewed)|"
                    r"eligible for (?:a )?(?:visa|residency|pr|citizenship)",
                    r"visa (?:kaise|kaun si|lag sakta)\b|visa (?:mil|lag) (?:jayega|sakta)",
                ),
                (
                    r"(?:أي|ما) (?:نوع )?(?:تأشيرة|فيزا)|هل (?:أستطيع|يمكنني) (?:الحصول على|التقديم على) (?:تأشيرة|إقامة)",
                ),
            ),
        ),
        (
            Advice.CUSTOMS,
            _rx(
                (
                    r"(?:what|which) (?:is|are)? ?(?:the )?(?:hs|tariff|harmonised|harmonized) code\b|hs code (?:for|of)\b|"
                    r"(?:how much|what) (?:customs )?(?:duty|duties|tariff)\b[^.?!\n]{0,30}\b(?:pay|import|on|charge|will)|"
                    r"customs (?:duty|valuation|classification|exemption)\b[^.?!\n]{0,30}\b(?:how|what|which|can i|should)|"
                    r"(?:is|are) (?:this|that|the|my) (?:supplier|buyer|company|country|shipment|vessel|bank|party|entity)\b[^.?!\n]{0,25}"
                    r"\b(?:under|on|subject to|affected by) (?:\w+ )?sanctions?|sanctions? (?:check|screening|list)\b[^.?!\n]{0,20}"
                    r"\b(?:should|can|do)|can i (?:export|import|ship) (?:to|from) (?:iran|russia|north korea|syria|cuba|sudan)",
                    r"customs (?:duty|ka|mein) (?:kitna|kitni|kitne)\b|hs code (?:kya|kaun)",
                ),
                (
                    r"(?:كم|ما) (?:الرسوم|رسوم) الجمركية|رمز (?:النظام المنسق|hs)|(?:العقوبات) على (?:المورد|الشركة)",
                ),
            ),
        ),
        (
            Advice.RELIGIOUS,
            _rx(
                (
                    r"is (?:it|this|that|[\w ]{1,30}?) (?:halal|haram|permissible|allowed in islam|permitted in islam|makruh)\b",
                    r"(?:halal or haram|haram or halal)|fatwa\b|(?:islamic|shariah|sharia) (?:ruling|verdict|view on)\b|"
                    r"what does (?:islam|the quran|the bible|shariah) say (?:about|on)\b",
                    r"(?:ye|yeh|is ka|iska)? ?(?:jaiz|jayez|najaiz|najayez|halal|haram) (?:hai|hain|ya)\b|shariat (?:mein|me|main) "
                    r"(?:jaiz|jayez)|fatwa (?:kya|chahiye)",
                ),
                (
                    r"هل (?:هذا|هذه|ذلك)?\s*(?:حلال|حرام|جائز|يجوز شرعا|يجوز شرعاً)|حكم (?:شرعي|الشرع)|فتوى",
                    r"کیا یہ (?:حلال|حرام|جائز)|شرعی حکم|فتویٰ|فتوی",
                ),
            ),
        ),
        (
            Advice.VEHICLE,
            _rx(
                (
                    r"is it safe to (?:drive|ride|use|load|tow)\b[^.?!\n]{0,40}\b(?:worn|bald|faulty|damaged|broken|leaking|"
                    r"cracked|overloaded|with)\b|are (?:these|those|my|our|the) (?:tyres?|tires?|brakes?|brake pads?|"
                    r"seat ?belts?|airbags?|steering|trucks?|buses|vans)\b[^.?!\n]{0,30}\b(?:safe|roadworthy|legal)|"
                    r"(?:vehicle|truck|bus|van|car) (?:safety|roadworthiness) (?:advice|check|standard)\b|"
                    r"is (?:this|my|our|the) (?:truck|bus|van|car|vehicle|tyre|tire|bike)\b[^.?!\n]{0,25}\b(?:safe|roadworthy|"
                    r"overloaded)|how much (?:load|weight)\b[^.?!\n]{0,20}\b(?:can|should) (?:the |this |my )?(?:truck|van|"
                    r"bus|vehicle|trailer)\b[^.?!\n]{0,10}\b(?:carry|take|haul)",
                    r"gaari (?:mehfooz|safe)\b[^.?!\n]{0,15}\bhai|brake (?:theek|safe)\b[^.?!\n]{0,10}\bhai",
                ),
                (),
            ),
        ),
        (
            Advice.VALUATION,
            _rx(
                (
                    r"(?:what|how much)\s+(?:is|are)\s+(?:my|our|this|the)\s+(?:plot|house|property|building|land|flat|"
                    r"apartment|shop|machinery|equipment|business|farm|stock)\b[^.?!\n]{0,15}\bworth|valuation (?:of|for) "
                    r"(?:my |our |this |the )?(?:plot|house|property|building|land|flat|apartment|shop|machinery|equipment|"
                    r"business|farm)|(?:value|valu\w+)\s+(?:my|our|this|the)\s+(?:plot|house|property|land|flat|apartment|"
                    r"shop|machinery|equipment|business|farm)\b|give me a valuation|"
                    r"(?:plot|ghar|zameen|jaidad|dukan)\b[^.?!\n]{0,15}\b(?:ki qeemat|ki value|kitne ka)\b",
                ),
                (),
            ),
        ),
        (
            Advice.FORMULATION,
            _rx(
                (
                    r"(?:what|which|give me (?:a |the )?|suggest (?:a |the )?)\s*(?:formulation|formula|recipe|composition|"
                    r"ingredients? (?:ratio|mix|list))\b[^.?!\n]{0,30}\b(?:should|to use|for (?:this|my|our|the)|use)|"
                    r"formulation (?:for|of) (?:this|my|our|the)\b|how (?:to|do i) (?:formulate|make up)\b[^.?!\n]{0,20}"
                    r"\b(?:shampoo|cream|lotion|detergent|paint|adhesive|perfume|soap|cosmetic|ointment|syrup|medicine)",
                ),
                (),
            ),
        ),
        (
            Advice.MEDICAL,
            _rx(
                (
                    r"(?:what does|what do|can you read|please read|read (?:my|this))\b[^.?!\n]{0,20}\b(?:x-?ray|mri|ct scan|"
                    r"ultrasound|ecg|lab report|blood test|blood report|scan|test results?)\b|"
                    r"what does (?:this|the|my) (?:x-?ray|mri|ct scan|ultrasound|ecg|lab report|blood test|scan)\b[^.?!\n]{0,10}"
                    r"\b(?:show|say|mean|indicate)",
                    r"(?:which|what|are|is|can)\b[^.?!\n]{0,25}\b(?:exercises?|workouts?|yoga|massage|diet|gym|swimming|lifting|"
                    r"cardio|training|fasting|supplements?)\b[^.?!\n]{0,25}\b(?:safe|ok|okay|allowed|suitable|good|should)\b"
                    r"[^.?!\n]{0,25}\b(?:pregnan\w+|expecting|breastfeeding|diabet\w+|heart|hypertension|blood pressure|"
                    r"injur\w+|surgery|elderly|kidney|asthma)|(?:pregnan\w+|breastfeeding|diabet\w+|hypertension|blood pressure)"
                    r"\b[^.?!\n]{0,25}\b(?:exercises?|workouts?|yoga|massage|diet|training|fasting)\b[^.?!\n]{0,20}"
                    r"\b(?:safe|ok|okay|allowed|suitable)|is massage safe\b[^.?!\n]{0,20}\bpregnan\w+|what diet should i give "
                    r"(?:my |the |a )?(?:gym |patient |client |member )",
                    r"x-?ray (?:mein|me|main) kya (?:aaya|hai|nazar)|lab report (?:parh|padh|dekh)",
                ),
                (
                    r"ماذا (?:يظهر|تظهر) (?:في )?(?:ال)?(?:أشعة|اشعة|تحليل)|اقرأ (?:لي )?(?:ال)?(?:تحليل|أشعة)",
                ),
            ),
        ),
        (
            Advice.LEGAL,
            _rx(
                (
                    r"(?:staff|employee|mulazim|mulazmeen|worker)s? ko\s+(?:bina|baghair)\s+notice\s+(?:nikal|fire|barkhast|hata)\w*",
                    r"(?:nikal|barkhast|fire)\b[^.?!\n]{0,20}\b(?:bina|baghair) notice|(?:bina|baghair) notice\b[^.?!\n]{0,20}"
                    r"\b(?:nikal|barkhast)",
                ),
                (
                    r"هل يجوز[^.?!\n]{0,20}(?:فصل|طرد|إنهاء)|فصل الموظف|طرد الموظف",
                    r"(?:ملازم|اسٹاف|سٹاف)\s+کو\s+(?:بغیر|بنا)\s+نوٹس\s+نکال",
                ),
            ),
        ),
        (
            Advice.TAX,
            _rx(
                (
                    r"can (?:i|we) (?:deduct|claim|write off|expense|offset)\b[^.?!\n]{0,40}\b(?:tax|vat|gst|income|return|"
                    r"deduction|from tax)|deduct\w* (?:this |it )?from (?:my |our )?(?:tax|vat|income)|tax[- ]deductible|"
                    r"is (?:this|it) (?:a )?deductible|tax (?:mein|me|main) (?:claim|deduct|minus)",
                ),
                (r"هل (?:يمكن|يمكنني) خصم[^.?!\n]{0,20}(?:من )?(?:ال)?ضريبة",),
            ),
        ),
    )
    + ADVICE_PATTERNS
)  # the specific classes are checked first: "which pesticide, what dose" is chemical, not medical

ADVICE_WHO = {
    "ar": {
        Advice.LEGAL: "محامٍ",
        Advice.TAX: "محاسب",
        Advice.FINANCIAL: "مستشار مالي مؤهل",
        Advice.MEDICAL: "طبيب أو صيدلي",
        Advice.VETERINARY: "طبيب بيطري",
        Advice.ENGINEERING: "مهندس مرخّص",
        Advice.CHEMICAL: "فني مختص مرخّص",
        Advice.AGRONOMY: "مهندس زراعي",
        Advice.IMMIGRATION: "محامٍ أو مستشار هجرة مرخّص",
        Advice.CUSTOMS: "مخلّص جمركي",
        Advice.RELIGIOUS: "عالم دين مؤهل",
        Advice.VEHICLE: "ميكانيكي مؤهل",
        Advice.VALUATION: "مقيّم معتمد",
        Advice.FORMULATION: "كيميائي مؤهل",
    },
    "en": {
        Advice.LEGAL: "a lawyer",
        Advice.TAX: "an accountant",
        Advice.FINANCIAL: "a qualified financial adviser",
        Advice.MEDICAL: "a doctor or pharmacist",
        Advice.VETERINARY: "a vet",
        Advice.ENGINEERING: "a licensed engineer",
        Advice.CHEMICAL: "a licensed technician",
        Advice.AGRONOMY: "an agronomist or livestock nutritionist",
        Advice.IMMIGRATION: "a lawyer or licensed immigration consultant",
        Advice.CUSTOMS: "a customs broker or trade lawyer",
        Advice.RELIGIOUS: "a qualified scholar",
        Advice.VEHICLE: "a qualified mechanic",
        Advice.VALUATION: "a licensed valuer",
        Advice.FORMULATION: "a qualified chemist",
    },
    "roman_ur": {
        Advice.LEGAL: "wakeel",
        Advice.TAX: "accountant",
        Advice.FINANCIAL: "mustanad financial adviser",
        Advice.MEDICAL: "doctor ya pharmacist",
        Advice.VETERINARY: "veterinary doctor",
        Advice.ENGINEERING: "licensed engineer",
        Advice.CHEMICAL: "licensed technician",
        Advice.AGRONOMY: "zarai mahir ya livestock nutritionist",
        Advice.IMMIGRATION: "wakeel ya licensed immigration consultant",
        Advice.CUSTOMS: "customs broker ya trade wakeel",
        Advice.RELIGIOUS: "mustanad aalim",
        Advice.VEHICLE: "mustanad mechanic",
        Advice.VALUATION: "licensed valuer",
        Advice.FORMULATION: "qualified chemist",
    },
}
ADVICE_TEXT = {
    "ar": "لا أستطيع تقديم نصيحة {kind}، و{who} هو الشخص المناسب لذلك. يمكنني تسجيلها كمشكلة في عملك. هل أفعل ذلك؟",
    "en": "I can't give {kind} advice, and {who} is the right person for that. I can note it as a problem in your business. Want me to?",
    "roman_ur": "Mere liye {kind} mashwara dena mumkin nahi, is ke liye {who} sahi insaan hai. Ise aap ke business ki ek problem ke taur par note kiya ja sakta hai. Kya note kar loon?",
}
ADVICE_WORD = {
    "ar": {
        Advice.LEGAL: "قانونية",
        Advice.TAX: "ضريبية",
        Advice.FINANCIAL: "مالية",
        Advice.MEDICAL: "طبية",
        Advice.VETERINARY: "بيطرية",
        Advice.ENGINEERING: "هندسية",
        Advice.CHEMICAL: "كيميائية",
        Advice.AGRONOMY: "زراعية",
        Advice.IMMIGRATION: "متعلقة بالهجرة",
        Advice.CUSTOMS: "جمركية",
        Advice.RELIGIOUS: "دينية",
        Advice.VEHICLE: "متعلقة بسلامة المركبات",
        Advice.VALUATION: "تقييم عقاري",
        Advice.FORMULATION: "تركيبية",
    },
    "roman_ur": {
        Advice.LEGAL: "qanooni",
        Advice.TAX: "tax ka",
        Advice.FINANCIAL: "maali",
        Advice.MEDICAL: "tibbi",
        Advice.VETERINARY: "janwaron ke ilaaj ka",
        Advice.ENGINEERING: "engineering ka",
        Advice.CHEMICAL: "chemical ke istemal ka",
        Advice.AGRONOMY: "zarai",
        Advice.IMMIGRATION: "immigration ka",
        Advice.CUSTOMS: "customs ka",
        Advice.RELIGIOUS: "mazhabi",
        Advice.VEHICLE: "gaari ki safety ka",
        Advice.VALUATION: "jaidad ki qeemat ka",
        Advice.FORMULATION: "formulation ka",
    },
}


def advice_asked(text: str) -> Advice | None:
    from app.modules.pi import safety_advice

    said = " ".join((text or "").split())
    treated = safety_advice.treatment_asked(said)  # who is sick and what to give, any order
    if treated is Advice.VETERINARY:
        return treated  # a sick animal outranks the human "which medicine" patterns
    for kind, pattern in ADVICE_PATTERNS:
        if pattern.search(said):
            return kind
    return treated


def advice_reply(kind: Advice, language: str | None) -> str:
    lang = language if language in ADVICE_TEXT else "en"
    word = ADVICE_WORD.get(lang, {}).get(kind, kind.value)
    return ADVICE_TEXT[lang].format(kind=word, who=ADVICE_WHO[lang][kind])


# R-DISC-04 (spec 6.6): when a person hands the chat back, pi says who it is again, once.
HANDBACK_TEXT = {
    "en": "I'm pi again, the AI from Workzap. Where would you like to carry on?",
    "roman_ur": "Main phir se pi hoon, Workzap ka AI. Aap kahan se baat jari rakhna chahenge?",
    "ar": "أنا pi مرة أخرى، الذكاء الاصطناعي من Workzap. من أين تريد أن نواصل؟",
}


def handback_reply(language: str | None) -> str:
    return HANDBACK_TEXT.get(language or "en", HANDBACK_TEXT["en"])


# R-LANG-08: religious and cultural courtesy, one line, then back to the business.
GREETING_TEXT = {
    "salam": {
        "en": "Wa alaikum assalam. What does your business do?",
        "roman_ur": "Wa alaikum assalam. Aap ka business kya kaam karta hai?",
        "ar": "وعليكم السلام. ما نوع عملك؟",
    },
    "festival": {
        "en": "Eid Mubarak to you too. What does your business do?",
        "roman_ur": "Aap ko bhi Eid Mubarak. Aap ka business kya kaam karta hai?",
        "ar": "عيد مبارك لك أيضًا. ما نوع عملك؟",
    },
}
# R-FUP-02: after "stop" pi confirms once and then writes no more.
OPT_OUT_TEXT = {
    "en": "Understood. I won't message you again. If you ever want to talk, just write here.",
    "roman_ur": "Theek hai. Dobara paigham nahi bheja jayega. Kabhi baat karni ho to yahin likh dein.",
    "ar": "حسنًا. لن أرسل لك رسائل بعد الآن. إن أردت التحدث يومًا فاكتب هنا.",
}


def greeting_reply(kind: str, language: str | None) -> str:
    table = GREETING_TEXT[kind]
    return table.get(language or "en", table["en"])


def opt_out_reply(language: str | None) -> str:
    return OPT_OUT_TEXT.get(language or "en", OPT_OUT_TEXT["en"])


# --- who pi is (R-DISC-02, R-DISC-03, R-META-01, spec 6.1) ------------------------------------


class Identity(StrEnum):
    PERSON = "person"
    GENDER = "gender"
    SCAM = "scam"
    META = "meta"
    MODEL = "model"
    RULES = "rules"
    COMPANY = "company"
    OFFER = "offer"


IDENTITY_PATTERNS: tuple[tuple[Identity, re.Pattern[str]], ...] = (
    (
        Identity.OFFER,
        re.compile(
            r"\b(?:what (?:do|does) (?:you|workzap) (?:sell|offer|do)|what (?:is|are) (?:workzap|your)"
            r"(?:'s)? (?:product|service|offer)s?|aap kya (?:bechte|karte|dete)|kya bechte ho)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.RULES,
        re.compile(
            r"\b(?:system prompt|show me your (?:prompt|rules|instructions)|your (?:prompt|instructions)|"
            r"reveal your (?:rules|prompt))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.META,
        re.compile(
            r"\b(?:are you (?:whatsapp|meta)|is this (?:whatsapp|meta)(?: ai)?|meta ai\b|made by (?:whatsapp|meta))",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.MODEL,
        re.compile(
            r"\b(?:are you (?:chat ?gpt|gpt|claude|gemini|openai)|which (?:ai )?model|what model|"
            r"what ai are you|powered by)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.SCAM,
        re.compile(
            r"\b(?:is this (?:a )?(?:scam|fraud|fake|legit|real)|are you (?:a )?(?:scam|fraud|fake)|"
            r"can i trust you|scam hai|dhokha)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.GENDER,
        re.compile(
            r"\b(?:what(?:'s| is) your name|are you (?:a )?(?:guy|girl|man|woman|male|female)|boy or girl|"
            r"aap ka naam|tumhara naam)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Identity.COMPANY,
        re.compile(
            r"\b(?:who owns workzap|where is (?:your|the|workzap'?s) office|workzap(?:'s)? (?:office|address|owner|ceo)|"
            r"who (?:is|are) (?:the )?(?:owner|ceo|founder)s? of workzap)\b",
            re.IGNORECASE,
        ),
    ),
)
# "Is this a real person?" is a question about who pi is, not about a scam (R-DISC-02): the answer
# starts "I'm an AI", so it must win over the scam pattern.
IDENTITY_PATTERNS = (
    (
        Identity.PERSON,
        _rx(
            (
                r"is this (?:a |an )?(?:real |actual |live )?(?:person|human|man|woman|guy|girl)",
                r"is (?:someone|somebody|a (?:real )?(?:person|human)) (?:there |actually |really )?(?:typing|replying|"
                r"answering|writing|behind this|on the other (?:end|side))",
                r"(?:you|u) sound like (?:a )?(?:real )?(?:guy|person|man|girl|woman|human)",
                r"kya koi insaan (?:jawab|likh|reply|baat)\w*|koi insaan (?:hai|jawab|likh)\w*|insaan (?:jawab|likh) de raha",
            ),
            (
                r"هل (?:هذا|هذه) شخص حقيقي|هل يكتب (?:لي )?شخص",
                r"کیا کوئی انسان (?:جواب|لکھ)|کیا یہ انسان ہے",
            ),
        ),
    ),
) + IDENTITY_PATTERNS

IDENTITY_TEXT = {
    "en": {
        Identity.PERSON: "I'm an AI, not a person. I'm pi, from Workzap.",
        Identity.GENDER: "I'm pi, an AI from Workzap. I don't have a gender.",
        Identity.SCAM: "Fair question. I'm an AI from Workzap. I never ask for payment, card numbers or passwords here, and you never have to buy anything. More at workzap.ai/pi/trust.",
        Identity.META: "No. I'm made by Workzap and chat through WhatsApp's business platform. I'm not made, run or endorsed by WhatsApp or Meta.",
        Identity.MODEL: "I'm pi, Workzap's AI. I'm here to note and sort problems in your business.",
        Identity.RULES: "I can tell you how I work: I note and sort problems, I never take payment here, and you decide on any quote. The full detail is at workzap.ai/pi/how-it-works.",
        Identity.COMPANY: "I can pass that question to the Workzap team.",
        Identity.OFFER: "Workzap makes software for finding problems and solving them. I'm not here to sell anything: I note what's getting in the way of yours, and if you want, Workzap can then prepare a solution document. What's the biggest thing right now?",
    },
    "roman_ur": {
        Identity.PERSON: "Main AI hoon, insaan nahi. Main pi hoon, Workzap ki taraf se.",
        Identity.GENDER: "Main pi hoon, Workzap ka AI. Meri koi jins nahi.",
        Identity.SCAM: "Jayez sawal hai. Main Workzap ka AI hoon. Main yahan kabhi payment, card number ya password nahi maangta, aur aap par kuch kharidna zaroori nahi. Mazeed workzap.ai/pi/trust par.",
        Identity.META: "Nahi. Mujhe Workzap ne banaya hai aur yahan WhatsApp ke business platform par chat hoti hai. Mujhe WhatsApp ya Meta ne nahi banaya, na chalata hai, na endorse karta hai.",
        Identity.MODEL: "Main pi hoon, Workzap ka AI. Main aap ke business ke masail note aur sort karne ke liye hoon.",
        Identity.RULES: "Kaam ka tareeqa ye hai: masail note aur sort kiye jate hain. Yahan kabhi payment nahi li jati, aur quote par faisla aap ka hota hai. Poori tafseel workzap.ai/pi/how-it-works par hai.",
        Identity.COMPANY: "Ye sawal Workzap ki team tak pahunchaya ja sakta hai.",
        Identity.OFFER: "Workzap masail dhoondne aur hal karne ka software banata hai. Main kuch bechne nahi aaya: yahan aap ke business ki rukawat note ki jati hai. Aap chahein to Workzap phir solution document bana sakta hai. Abhi sab se bada masla kya hai?",
    },
    "ar": {
        Identity.PERSON: "أنا ذكاء اصطناعي ولست شخصًا. أنا pi من Workzap.",
        Identity.GENDER: "أنا pi، ذكاء اصطناعي من Workzap. ليس لي جنس.",
        Identity.SCAM: "سؤال وجيه. أنا ذكاء اصطناعي من Workzap. لا أطلب هنا أبدًا دفعًا أو أرقام بطاقات أو كلمات مرور، ولا يجب عليك شراء أي شيء. المزيد على workzap.ai/pi/trust.",
        Identity.META: "لا. صنعتني Workzap وأتحدث عبر منصة واتساب للأعمال. لم تصنعني واتساب أو ميتا ولا تديرني ولا تدعمني.",
        Identity.MODEL: "أنا pi، ذكاء Workzap الاصطناعي. أنا هنا لأسجّل مشكلات عملك وأرتّبها.",
        Identity.RULES: "يمكنني أن أشرح كيف أعمل: أسجّل المشكلات وأرتّبها، ولا أقبل أي دفع هنا، والقرار في أي عرض سعر لك. التفاصيل الكاملة على workzap.ai/pi/how-it-works.",
        Identity.COMPANY: "يمكنني نقل هذا السؤال إلى فريق Workzap.",
        Identity.OFFER: "تصنع Workzap برمجيات لاكتشاف المشكلات وحلّها. لست هنا لأبيع شيئًا: أسجّل ما يعيق عملك، وإن أردت يمكن لـ Workzap بعدها إعداد وثيقة حل. ما أكبر شيء الآن؟",
    },
}


def identity_asked(text: str, asks_if_ai: re.Pattern[str]) -> Identity | None:
    """Which "who are you" question this is. `asks_if_ai` is the linter's pattern, so the check that a
    reply says "AI" and the check that decides pi must say it can never disagree."""
    said = " ".join((text or "").split())
    for kind, pattern in IDENTITY_PATTERNS:
        if pattern.search(said):
            return kind
    if asks_if_ai.search(said):
        return Identity.PERSON
    return None


def identity_reply(kind: Identity, language: str | None) -> str:
    table = IDENTITY_TEXT.get(language or "en", IDENTITY_TEXT["en"])
    return table[kind]


# --- what pi will not do (R-PRIV-05, R-PRIV-06, R-ADV-04, spec 10.2 RT14-RT16, RT20, RT22, RT24) ---


class Boundary(StrEnum):
    DELETION = "deletion"
    POLITICS = "politics"
    COMPETITOR = "competitor"
    OUTCOME = "outcome"
    FRAUD = "fraud"
    THIRD_PARTY = "third_party"
    BANK_CHANGE = "bank_change"
    OFF_TOPIC = "off_topic"
    COMPLAINT = "complaint"
    ILLEGAL = "illegal"
    REFUND = "refund"
    BANK_ASK = "bank_ask"  # M2: asked for Workzap's bank details before any approval
    BANK_ASK_APPROVED = "bank_ask_approved"  # M3: the same, after the quote was approved
    OTHER_PAY = "other_pay"  # M6: card, JazzCash, Easypaisa, Apple Pay
    DISCOUNT = "discount"  # M7
    PAY_FOR_ME = "pay_for_me"  # M10: pay my supplier
    PRODUCT_REC = "product_rec"  # A5: which POS should I buy
    DECIDE_FOR_ME = "decide_for_me"  # A8
    RIVAL = "rival"  # A6: what do you think of my competitor
    WRONG_NUMBER = "wrong_number"  # 6.9
    MEMORY_ASK = "memory_ask"  # R-MEM-05: what does pi keep
    QUOTE_ONLY = "quote_only"  # R-QUOTE-09: a quote without the document


BOUNDARY_PATTERNS: tuple[tuple[Boundary, re.Pattern[str]], ...] = (
    (
        # A refund or dispute with Workzap itself (R-PAY-07), not refunds in the person's own
        # business, which are a problem to note.
        Boundary.REFUND,
        re.compile(
            r"\b(?:i (?:want|need|demand|would like) (?:a |my |the )?(?:refund|money back)"
            r"|(?:give|send) (?:me )?(?:a |my )?(?:refund|money back)"
            r"|refund (?:me|my (?:money|payment|transfer))"
            r"|(?:dispute|contest) (?:the |this |my )?(?:payment|charge|invoice|transfer)"
            r"|charge ?back|apne paise wapis|paise wapis (?:do|karo|chahiye)|refund chahiye"
            r"|pais(?:a|e|on)\s+wapa(?:s|is)\s+(?:do|dedo|de do|karo|kar do|chahiye|chahie)"
            r"|(?:rakam|raqam)\s+wapa(?:s|is)\s+(?:do|dedo|karo|kar do|chahiye))\b",
            re.IGNORECASE,
        ),
    ),
    (
        # A complaint about pi or Workzap (not about a cashier or a supplier): R-COMPL-01.
        Boundary.COMPLAINT,
        re.compile(
            r"\bi (?:want|would like) to complain\b"
            r"|\b(?:complaint|complain|shikayat)\b[^.?!\n]{0,30}\b(?:about|against|ki|par)?\s*"
            r"(?:pi|workzap|your (?:service|team|company|bot)|this (?:bot|service|chat))\b"
            r"|\b(?:not happy|unhappy|disappointed) with (?:pi|workzap|your (?:service|team|bot)|"
            r"this (?:bot|service))\b|\bworkzap ki shikayat\b|\breport (?:you|this bot)\b",
            re.IGNORECASE,
        ),
    ),
    (
        # Something illegal that pi must not help with and must not note as a problem to solve.
        Boundary.ILLEGAL,
        re.compile(
            r"\b(?:track|spy on|monitor) (?:my |our )?(?:staff|employees|workers|wife|husband)\b"
            r"[^.?!\n]{0,20}\b(?:secretly|covertly|without (?:them|their) knowing)\b"
            r"|\bread (?:their|my staff'?s?|employees') (?:whatsapp|messages|chats)\b"
            r"|\bhack\b[^.?!\n]{0,20}\b(?:account|whatsapp|phone)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.DELETION,
        re.compile(
            r"\b(?:delete (?:everything|all|my (?:data|chats?|records?|information))|"
            r"erase (?:everything|all|my (?:data|chats?|records?))|forget (?:everything|all about me)|"
            r"remove (?:all )?my (?:data|information)|mera (?:sab )?(?:data|record) (?:delete|mita)|"
            r"sab (?:kuch )?delete kar do)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.BANK_CHANGE,
        re.compile(
            r"\b(?:(?:new|changed?|different|updated?) (?:bank|account|iban)(?: details| account| number)?"
            r"[^.?!]{0,40}(?:workzap|you|your)|workzap[^.?!]{0,30}(?:changed|new) (?:their )?(?:bank|account|iban)|"
            r"send (?:me )?(?:the )?new (?:iban|account|bank)|bank (?:details|account) (?:have|has) changed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.OFF_TOPIC,
        re.compile(
            r"\b(?:(?:help|write|do) (?:me )?(?:with )?(?:my |an? |the )?(?:homework|assignment|essay|poem|"
            r"python|javascript|code|script|resume|cv)\b|tell me a (?:joke|story)|write (?:me )?(?:a |an )?"
            r"(?:poem|song|joke|story)|solve this (?:equation|math|problem set))",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.FRAUD,
        re.compile(
            r"\b(?:(?:fake|false|bogus|duplicate|double) (?:invoices?|bills?|receipts?|vouchers?)|"
            r"(?:make|create|issue|print) (?:\w+ )?(?:fake|false) (?:invoices?|bills?|receipts?)|"
            r"jali (?:bill|invoice|receipt)|tax chori|evade tax|hide (?:income|sales) from)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.THIRD_PARTY,
        re.compile(
            r"\b(?:send me (?:the )?(?:chats?|messages|conversations?) (?:of|with|from) (?:my|our|his|her)?\s*\w+|"
            r"show me (?:the )?(?:chats?|messages) (?:of|from|with) (?:my|our|his|her)?\s*\w+|"
            r"what did (?:my|our) (?:manager|cashier|staff|employee|partner|wife|husband)[^.?!]{0,20}(?:say|tell|write))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.OUTCOME,
        re.compile(
            r"\b(?:say|promise|guarantee|confirm|tell me)[^.?!]{0,30}(?:will|would)?[^.?!]{0,20}"
            r"(?:definitely|certainly|for sure|guaranteed?|100%)[^.?!]{0,30}"
            r"(?:increase|boost|double|grow|improve|raise|fix)\b|"
            r"\b(?:guarantee|promise) (?:me )?(?:more )?(?:sales|profit|results|growth)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.COMPETITOR,
        re.compile(
            r"\b(?:are you (?:any )?(?:better|cheaper|worse) than|is (?:workzap|pi) (?:better|cheaper) than|"
            r"compare (?:yourself|workzap|you) (?:to|with)|"
            r"workzap (?:vs|versus)|(?:vs|versus) workzap|why (?:you|workzap) (?:and )?not)\b"
            r"[^.?!]{0,40}",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.POLITICS,
        re.compile(
            r"\b(?:what do you think (?:about|of) (?:the )?(?:\w+ ){0,2}(?:party|government|election|"
            r"minister|prime minister|president|imran|nawaz|zardari|modi|trump|biden)|"
            r"who (?:should|will) i vote|which party (?:is|should)|your (?:political|religious) "
            r"(?:view|opinion|views|opinions)|siyasi (?:party|jamaat)|vote (?:kis|kisko))\b",
            re.IGNORECASE,
        ),
    ),
)

# More of spec 6.2 and 6.4 (M2, M3, M6, M7, M10, A5, A6, A8) and 6.9 (wrong number).
BOUNDARY_PATTERNS = BOUNDARY_PATTERNS + (
    (
        Boundary.BANK_ASK,
        re.compile(
            r"\b(?:send|give|share|tell)\s+(?:me\s+)?(?:your|the|workzap'?s)\s+(?:bank|account|iban)"
            r"(?:\s+(?:details|number|account))?\b|\bwhat(?:'s| is) your (?:bank|iban|account number)\b"
            r"|\b(?:apna|aap ka|workzap ka)\s+(?:bank|account)\s+(?:number|details|tafseel)\s+(?:bhejein|bhej do|batao|dein)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.OTHER_PAY,
        re.compile(
            r"\b(?:can i|could i|may i|how (?:do|can) i)\s+pay\s+(?:by|with|through|via|using|in)\s+"
            r"(?:card|credit card|debit card|jazz ?cash|easy ?paisa|apple pay|google pay|paypal|cash|cheque|check|crypto)\b"
            r"|\b(?:jazz ?cash|easy ?paisa|card|cash)\s+(?:se|par|pe)\s+(?:payment|pay)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.DISCOUNT,
        re.compile(
            r"\b(?:give me|can i get|can you give me|i want|i need)\s+(?:a\s+)?(?:discount|better price|lower price)\b"
            r"|\b(?:reduce|lower|cut)\s+(?:the\s+)?(?:price|quote|cost)\b|\bdiscount\s+(?:do|chahiye|milega|dein)\b"
            r"|\b(?:price|rate|quote)\s+kam\s+(?:karo|kar do|karein)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.PAY_FOR_ME,
        re.compile(
            r"\b(?:pay|send money to|transfer (?:money )?to)\s+my\s+(?:supplier|vendor|staff|employees?|landlord)\b"
            r"|\bmere\s+(?:supplier|vendor)\s+ko\s+(?:pay|paise|payment)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.PRODUCT_REC,
        re.compile(
            r"\bwhich\s+(?:pos|software|app|accounting software|erp|crm|laptop|printer|system|tool)\s+"
            r"(?:should|do you recommend|is best|to)\b|\b(?:recommend|suggest)\s+(?:me\s+)?(?:a|an|some)\s+"
            r"(?:pos|software|erp|crm|app)\b|\bkon\s*sa\s+(?:pos|software|app)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.DECIDE_FOR_ME,
        re.compile(
            r"\bwhat would you (?:do|choose)\s+(?:if you were me|in my (?:place|shoes|position))\b"
            r"|\bif you were me\b|\baap\s+meri\s+jagah\s+hote\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.RIVAL,
        re.compile(
            r"\b(?:what do you think (?:of|about)|your (?:opinion|view|thoughts) (?:on|of|about)|"
            r"is it true that)\s+(?:my|our)\s+(?:competitor|rival)s?\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.WRONG_NUMBER,
        re.compile(
            r"\byou(?:'ve| have| got)?\s+(?:the\s+)?wrong number\b|^\W*(?:sorry\W+)?wrong number\W*$"
            r"|\bgalat number\b|\bwho is this\W+i didn'?t (?:ask|message|text)\b",
            re.IGNORECASE,
        ),
    ),
)


BOUNDARY_PATTERNS = BOUNDARY_PATTERNS + (
    (
        Boundary.MEMORY_ASK,
        re.compile(
            r"\b(?:what|which)\s+(?:data|information|details|records?)\s+(?:do|does|will)\s+(?:you|pi)\s+"
            r"(?:keep|store|save|have|hold|know)\b|\bwhat do you (?:keep|store|save|remember) about me\b"
            r"|\bkya\s+(?:data|record|information)\s+(?:rakhte|rakhta|save|store)\b|\bmera\s+kya\s+(?:data|record)\b",
            re.IGNORECASE,
        ),
    ),
)


# RT51 (platform spec 12.3): "draw a map of another business's problems" is refused with the
# third-party line. "My other business" is the person's own and is not matched: the other party is
# named as another, someone else's, your other clients, or doosre / kisi aur ke.
_OTHER_PARTY = (
    r"(?<!\bmy\s)(?<!\bour\s)(?:(?:another|other|a\s+different|someone\s+else'?s?|your\s+other|their|"
    r"doosre|dusre|dosre|kisi\s+aur\s+(?:ke|ki|ka)|aur\s+kisi\s+(?:ke|ki|ka))"
    r"\s+(?:person'?s?\s+|owner'?s?\s+)?(?:business(?:es)?|compan(?:y|ies)|clients?|customers?|owners?|"
    r"shops?|dukaan|dukan)|dost\s+ke\s+business(?:es)?)"
)
_THEIR_DATA = (
    r"(?:problem\s+map|map|list|notes?|chats?|messages|conversations?|problems|masle|masail|numbers|"
    r"details|records?|files?)"
)
BOUNDARY_PATTERNS = BOUNDARY_PATTERNS + (
    (
        Boundary.THIRD_PARTY,
        re.compile(
            rf"\b(?:draw|make|build|show|send|give|share|bana|banao|dikha|dikhao|bhej|bhejo|do)\b[^.?!\n]{{0,30}}"
            rf"\b{_THEIR_DATA}\b[^.?!\n]{{0,25}}\b{_OTHER_PARTY}'?s?\b"
            rf"|\b{_OTHER_PARTY}'?s?\s+(?:ka\s+|ke\s+|ki\s+)?[^.?!\n]{{0,20}}\b{_THEIR_DATA}\b[^.?!\n]{{0,25}}"
            rf"\b(?:draw|make|build|show|send|give|share|bana|banao|dikha|dikhao|bhej|bhejo|do|dein|dena)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Boundary.QUOTE_ONLY,
        re.compile(
            r"\b(?:just|only|sirf)\s+(?:the\s+|a\s+)?(?:quote|quotation|price)\b(?!\s+and\b)"
            r"|\bquote\s+(?:without|bina|baghair)\s+(?:the\s+)?(?:document|doc)\b"
            r"|\bwithout\s+the\s+(?:solution\s+)?document\b",
            re.IGNORECASE,
        ),
    ),
)

# Fraud, forgery, bribery and covert surveillance in every trade (spec Part 7 declines, R-ADV-04):
# pi refuses and offers to note the real problem instead. These go first, so a refusal is never
# pre-empted by a looser boundary.
_DOC = (
    r"(?:invoices?|bills?|receipts?|vouchers?|records?|documents?|certificates?|reports?|signatures?|stamps?|"
    r"seals?|licen[cs]es?|permits?|attendance(?: sheets?| records?| registers?)?|marks|grades|stock (?:records?|count)|"
    r"timesheets?|payslips?|bank statements?|ledgers?|books|accounts|figures|expiry dates?|prescriptions?|"
    r"lab reports?|marksheets?|degrees?|diplomas?|transcripts?|reviews?|ratings?|testimonials?|test results?|"
    r"inspection reports?|logs?|labels?|certs?)"
)
FRAUD_PATTERNS = _rx(
    (
        r"back[- ]?dat\w*|falsif\w+|forg(?:e|ed|ing|ery)\b[^.?!\n]{0,30}" + _DOC,
        r"(?:fake|falsify|fabricate|counterfeit|photoshop|fudge|cook(?:ed)? the)\s+(?:the |a |an |our |my |their |some |all "
        r"|these |those |his |her )?(?:\w+ ){0,2}" + _DOC,
        r"(?:fake|false|bogus|paid|purchased|made[- ]up|fabricated|phoney|phony)\s+(?:google |facebook |online |"
        r"customer |5[- ]star |five[- ]star |positive |good )*(?:reviews?|ratings?|testimonials?)",
        r"buy(?:ing)? (?:\w+ ){0,2}(?:reviews?|ratings?|followers|likes)|review (?:farm|bombing)",
        r"(?:bribe[sd]?|bribing|kickbacks?)(?! (?:is|was) (?:asked|demanded))|(?:pay|paying) off (?:the |an? )?(?:inspector|"
        r"officer|official|police|clerk|auditor|examiner|guard|customs)|grease (?:the )?palm|under the table|"
        r"rishwat|rishvat|chai pani (?:de|dena)",
        r"under[- ]?(?:invoic|declar|valu)\w*|over[- ]?invoic\w*|mis[- ]?declar\w*|smuggl\w+",
        r"(?:show|declare|report|write|put|mention) (?:a )?(?:lower|less|smaller|false|wrong|reduced|cheaper) "
        r"(?:value|price|amount|weight|quantity|invoice)[^.?!\n]{0,30}(?:customs|duty|tax|fbr|\bgd\b|declaration|"
        r"bill of entry|import|clearing)",
        r"(?:wrong|false|different|fake) hs code|(?:avoid|evade|dodge|bypass) (?:the )?(?:customs|duty|duties|tariffs?)",
        r"roll(?:ing)? ?back (?:the |an? |our |his )?(?:odometer|meter|mileage|kilomet\w+|km)|odometer[^.?!\n]{0,10}"
        r"(?:roll ?back|tamper\w*|reset|correction)|(?:reduce|lower|wind back|turn back|reset|change) (?:the )?"
        r"(?:odometer|mileage|meter reading|kilomet\w+)|meter (?:roll ?back|tampering)|"
        r"(?:slow(?:ing)? (?:down )?|bypass(?:ing)? )(?:the )?(?:electricity |gas |water )?meter",
        r"(?:used|old|second[- ]?hand|refurbished|repaired|reconditioned|salvaged|expired|returned|damaged|"
        r"flood[- ]damaged|replica|copy|fake|duplicate)\b[^.?!\n]{0,30}\b(?:as|like|for)\s+(?:brand[- ]?new|new|original|"
        r"genuine|fresh|unused|authentic|oem|first[- ]?hand|imported)\b|pass(?:ing)? (?:it |them )?off as "
        r"(?:new|original|genuine)",
        r"(?:change|reset|extend|relabel|repack\w*|replace|alter|remove|reprint) (?:the )?(?:\w+ )?"
        r"(?:expiry|expiration|manufactur\w+|mfg|best before|use by|production) (?:dates?|labels?|stickers?)",
        r"(?:relabel\w*|repack\w*|re-?date\w*|reprint\w*)\b[^.?!\n]{0,40}\b(?:expir\w+|expiry|new (?:expiry )?date)|"
        r"expired (?:stock|goods|medicines?|products?|food|items?|batteries|tyres|inventory)\b[^.?!\n]{0,40}\b(?:sell|"
        r"relabel|repack|new date|fresh|resell)",
        r"(?:without|skip(?:ping)?|bypass(?:ing)?)\s+(?:the |any |a |proper |actual |physical |safety |site |fitness |"
        r"quality |gas |pressure |lift |vehicle |boiler |fire )*(?:inspection|testing|test|checking|audit|verification|"
        r"calibration|survey|examination)\b[^.?!\n]{0,30}(?:certificate|sign[- ]?off|approv\w*|pass|stamp|clearance|"
        r"issue|report|licen[cs]e|fitness|sticker|tag|permit)",
        r"(?:certificate|sign[- ]?off|approval|stamp|clearance|fitness|sticker|report|tag|permit|pass)\b[^.?!\n]{0,40}"
        r"\bwithout\b[^.?!\n]{0,15}\b(?:inspect|test|check|visit|verif|audit|measur|examin|calibrat)\w*",
        r"(?:pass|approve|certify|sign off|clear|issue)\b[^.?!\n]{0,25}without (?:inspecting|testing|checking|looking|"
        r"visiting|verifying|measuring|examining)",
        r"(?:stamp(?:ing)?|seal(?:ing)?|sign(?:ing)?|certify(?:ing)?)\b[^.?!\n]{0,30}\b(?:drawings?|plans?|designs?|"
        r"calculations?|reports?)\b[^.?!\n]{0,40}\b(?:without (?:\w+ ){0,2}(?:review|check|prepar|design|insp|verif|read|"
        r"look)\w*|(?:i|we|he|she|they)\s+(?:didn'?t|did not|never|haven'?t|have not)\s+(?:\w+\s+){0,2}(?:prepar|review|"
        r"check|design|draw|verif|inspect|see|look)\w*)",
        r"(?:rent|lend|sell|hire out)(?:ing)? (?:my |our |the )?(?:stamp|seal|licen[cs]e|signature)",
        r"(?:change|alter|edit|inflate|bump up|tamper with|fudge|manipulate|modify)\s+(?:the |a |my |our |his |her |"
        r"their |some |students?'?s? |student |exam |final |board |class |report |mark )*(?:marks|grades|gpa|cgpa|"
        r"transcripts?|marksheets?|mark sheets?|report cards?|exam results?|attendance(?: records?| sheets?| registers?)?)",
        r"(?:mark|marking) (?:students? |them |people )?present (?:who|when|though|even though|but)[^.?!\n]{0,30}"
        r"(?:absent|not (?:there|present|attend)|didn'?t)|proxy attendance|ghost (?:students?|workers?|employees?|"
        r"teachers?|beneficiar\w+|names?)",
        r"(?:bill|charge|invoice|claim|collect|overcharge)\w*\b[^.?!\n]{0,50}\b(?:not (?:yet |actually |been )?(?:delivered|"
        r"provided|performed|done|rendered|completed|used|received|installed|supplied|sent|attended)|never "
        r"(?:\w+ ){0,2}(?:delivered|provided|performed|done|rendered|completed|used|received|installed|supplied|"
        r"happened|took place)|(?:did not|didn'?t) (?:actually |even )?(?:happen|attend|come|get|receive|use|deliver|"
        r"do|perform|provide|take place)|weren'?t (?:actually |even )?(?:delivered|done|provided|performed|used))",
        r"(?:bill|charge|invoice|claim)\w*\b[^.?!\n]{0,30}\b(?:extra|more|additional|padded|inflated|phantom|ghost|"
        r"fictitious|imaginary|non[- ]?existent|fake|dummy)\s+(?:hours?|visits?|sessions?|services?|treatments?|tests?|"
        r"items?|procedures?|claims?|days?|nights?|trips?|km|kilometres?)",
        r"(?:pad|inflate|bump|add)\w*\s+(?:the |our |my |a |an )?(?:\w+ ){0,2}(?:bill|invoice|claim|hours|timesheet|"
        r"mileage|expenses?|charges?)[^.?!\n]{0,25}(?:without|they won'?t notice|nobody (?:will )?notice|(?:customer|"
        r"they) (?:won'?t|will not) (?:notice|know)|extra)|phantom billing|double[- ]?bill\w*|upcod\w+",
        r"(?:issue|give|write|sign)\w*\s+(?:a |an )?(?:fitness|health|clearance|safety|compliance|calibration|test|"
        r"medical|sick|inspection)\s+(?:certificate|report|slip|note|leave)\b[^.?!\n]{0,30}\b(?:without|even though|"
        r"although|for someone who|for (?:those|people|staff) who)",
        r"jali (?:bill|invoice|receipt|review|rating|certificate|degree|sanad|stamp|dastakhat|signature|mohar|report|"
        r"marks|hazri|attendance|drawing)|nakli (?:review|certificate|degree|stamp|mohar|report|signature|dastakhat|"
        r"invoice|bill|receipt|marksheet)|jhoot[ia] review|fake review",
        r"(?:purani|used) (?:cheez|gaari|gadi|machine|battery|maal)\b[^.?!\n]{0,25}(?:nayi|naya|new) (?:bata|ke taur|"
        r"bana ke|keh kar)\w*|(?:used|purani|copy|duplicate) (?:ko|gaari ko|gadi ko) (?:new|nayi|naya|original) bata\w*|"
        r"original bata\w*|naya bata\w*|nayi bata\w*",
        r"bina (?:inspection|test|check|checking|jaanch)\b[^.?!\n]{0,25}(?:certificate|pass|stamp|sign|fitness)|"
        r"(?:certificate|pass|stamp|sign|fitness)\b[^.?!\n]{0,25}bina (?:inspection|test|check|jaanch|dekhe)|"
        r"(?:bina dekhe|bina check|bina review)\b[^.?!\n]{0,25}(?:stamp|sign|drawing)",
        r"(?:meter|odometer)\b[^.?!\n]{0,20}(?:reading )?(?:peeche|kam|ulta|reset)\b[^.?!\n]{0,10}(?:kar|karo|kar do)|"
        r"back ?date|purani (?:tareekh|date) (?:mein|par|me|ki|daal|likh)|tareekh (?:badal|peeche|change)\w*",
        r"(?:bill|charge|invoice)[^.?!\n]{0,40}(?:nahi (?:hui|hua|ki|kiya|di|diya)|bina (?:kaam|service))|"
        r"bina (?:kaam|service|delivery) (?:ke )?(?:bill|invoice|charge)",
        r"hazri (?:jali|fake)|(?:marks|number) (?:badal|barha)\w*",
        r"inspector ko (?:rishwat|paise|paisay)|rishwat (?:dena|deni|de)",
    ),
    (
        r"جعلی|نقلی|جھوٹی (?:رپورٹ|رسید|بل|ریویو|سرٹیفکیٹ)|رشوت",
        r"(?:فاتورة|فاتوره|فواتير|شهادة|شهادات|وثيقة|وثائق|تقارير|تقرير|إيصال)\s*(?:ال)?(?:مزورة|مزيفة|وهمية|مزور|مزيف)|"
        r"تزوير|تزييف|رشوة|ارشي|تهريب|تحايل|"
        r"تقييمات (?:مزيفة|وهمية)|تقييم مزيف|تلاعب (?:في|ب)\s*(?:ال)?(?:فواتير|حسابات|أرقام|عداد)|"
        r"(?:إرجاع|ارجاع|تقليل)\s+(?:ال)?عداد|تغيير\s+(?:ال)?تاريخ|بتاريخ سابق",
    ),
)
ILLEGAL_PATTERNS = _rx(
    (
        r"(?:hidden|secret|covert|spy|concealed|pinhole|disguised)\s+(?:cctv\s+)?(?:cameras?|cams?|mics?|microphones?|"
        r"recorders?|gps|trackers?|audio|bugs?|devices?|recording)",
        r"(?:install|put|place|fit|plant|hide|set up|mount)\w*\s+(?:a |an |the |some |secret |hidden )*(?:\w+ )?"
        r"(?:cameras?|cams?|mics?|microphones?|recorders?|trackers?|bugs?)\s+(?:\w+\s+){0,4}(?:in|inside|near|at|on|"
        r"under|behind)\s+(?:the |a |our |their |his |her )?(?:\w+\s+){0,2}(?:bathrooms?|toilets?|washrooms?|"
        r"changing rooms?|trial rooms?|ladies|women'?s|girls'?|female|locker rooms?|bedrooms?|guest rooms?|"
        r"hotel rooms?|dorm\w*|hostel rooms?|restrooms?|prayer rooms?|nursing rooms?)",
        r"(?:track|tracking|monitor|monitoring|record|recording|listen(?:ing)? (?:to|in on)|spy(?:ing)? on|"
        r"follow(?:ing)?|watch(?:ing)?|surveil\w*|eavesdrop\w*)\s+(?:\w+\s+){0,2}(?:my |our |the |all |their |his |"
        r"her )?(?:drivers?|guests?|students?|pupils?|patients?|residents?|tenants?|employees|staff|workers|wife|"
        r"husband|girlfriend|boyfriend|girls|women|ladies|teachers?|nann(?:y|ies)|maids?|customers|clients?|kids|"
        r"children|daughters?|sons?)\b[^.?!\n]{0,40}\b(?:secretly|covertly|without (?:\w+ ){0,2}(?:them|their|his|her|"
        r"anyone|telling|knowing|consent|permission|knowledge|informing)|hidden|in secret|behind (?:their|his|her) "
        r"back|on the sly)",
        r"(?:put|place|plant|hide|attach)\w*\s+(?:a |an )?(?:gps )?tracker\b[^.?!\n]{0,40}\bsecretly",
        r"(?:record|tap)\w*\s+(?:\w+\s+){0,2}(?:phone )?calls\b[^.?!\n]{0,25}\bwithout\b",
        r"(?:cameras?|cctv|mics?|recorder)\b[^.?!\n]{0,30}\b(?:ladies|women'?s|girls'?|female) (?:washroom|toilet|"
        r"bathroom|changing|area|section|hostel|room|dorm)\w*",
        r"chhup(?:a|e)(?: hua| hue| ke)? (?:camera|mic|recorder|tracker)|(?:camera|mic|tracker|recorder) "
        r"(?:chhupa|chupa|lagana|laga)\w*[^.?!\n]{0,30}(?:bathroom|washroom|ladies|changing|kamre|room)|"
        r"ladies (?:washroom|bathroom|area|section|hostel) (?:mein|me|main|ke andar) camera|"
        r"chori chupe (?:track|record|nigrani)|(?:driver|drivers|staff|students?|mehmaan|guests?|wife|biwi|bachon|"
        r"ladkiyon)\s+(?:ko|ki|par|pe)\s+(?:chori chupe|chupke se|bina bataye|secretly)[^.?!\n]{0,20}(?:track|record|"
        r"nigrani|dekh|sun)\w*|bina bataye (?:track|record|nigrani)|chupke se (?:track|record|sun)",
    ),
    (
        r"چھپا (?:ہوا )?کیمرہ|خفیہ (?:کیمرہ|کیمرے|ریکارڈنگ)|(?:باتھ روم|واش روم|چینجنگ روم)\s+میں\s+کیمرہ|"
        r"چھپ کر (?:ریکارڈ|نگرانی)|بغیر بتائے|کیمرہ\s+(?:باتھ روم|واش روم|چینجنگ روم)",
        r"كاميرا\s*(?:ات)?\s*(?:مخفية|خفية|سرية|مخفيه)|كاميرات (?:مخفية|خفية|سرية)|تجسس|التجسس|تسجيل (?:سري|خفي)|"
        r"تنصت|كاميرا في (?:ال)?(?:حمام|دورة المياه|غرفة تبديل)",
    ),
)
_BANK_CHANGE_MORE = _rx(
    (
        r"(?:colleague|manager|accountant|staff|someone|person|your team|your office|workzap|he|she|they)\b[^.?!\n]{0,30}"
        r"\b(?:said|told|asked|says|wants?)\b[^.?!\n]{0,20}\b(?:to )?(?:pay|transfer|send)\b[^.?!\n]{0,20}\b(?:to|into|in)\b"
        r"[^.?!\n]{0,15}\b(?:different|another|new|other|alternate|alternative)\b[^.?!\n]{0,8}\baccount",
        r"(?:please )?(?:pay|transfer|send)\b[^.?!\n]{0,15}\b(?:to|into)\s+(?:a |this |the |our )?(?:different|another|new|"
        r"other|alternate|alternative|changed)\s+(?:bank )?account",
        r"(?:naye|naya|dusre|doosre|alag|badle hue)\s+(?:bank )?account\s+(?:mein|me|main|par)\s+(?:pay|paise|payment|"
        r"transfer|bhej|jama)",
        r"\b(?:naya|naye|new|changed|badla hua)\s+(?:bank\s+)?account(?:\s+number)?\b[^.?!\n]{0,60}"
        r"\b(?:payment|pay|paise|transfer|jama|bhej|workzap)\b",
        r"\bworkzap\s+(?:ka|ke)\s+(?:naya|naye|new)\s+(?:bank\s+)?account",
        r"\b(?:payment|pay|paise|transfer)\b[^.?!\n]{0,30}\b(?:naya|naye|new)\s+(?:bank\s+)?account\b",
        r"\buse\s+(?:this|the|our)\s+(?:new|different|other)\s+(?:bank\s+)?account\b",
    ),
    (
        r"(?:ادفع|حوّل|حول|سدد|الدفع|التحويل|تحويل|سداد|الرجاء التحويل)[^.?!\n]{0,30}حساب\s*(?:بنكي\s*)?(?:جديد|مختلف|آخر)|"
        r"حساب\s*(?:بنكي\s*)?(?:جديد|مختلف|آخر)[^.?!\n]{0,20}(?:ادفع|للدفع|للتحويل)",
        r"(?:نئے|دوسرے|مختلف|الگ)\s*(?:بینک\s*)?اکاؤنٹ\s*(?:میں|پر)?[^.?!\n]{0,20}(?:رقم|ادائیگی|پیسے|ٹرانسفر|جمع)|"
        r"(?:رقم|ادائیگی|پیسے|ٹرانسفر)[^.?!\n]{0,25}(?:نئے|دوسرے|مختلف|الگ)\s*(?:بینک\s*)?اکاؤنٹ",
    ),
)
_SCRIPT_BOUNDARIES: tuple[tuple[Boundary, re.Pattern[str]], ...] = (
    (
        Boundary.REFUND,
        _rx(
            (),
            (
                r"أريد استرداد|استرداد (?:أموالي|اموالي|المبلغ|مالي)|استرجاع (?:المبلغ|أموالي|فلوسي)|أعيدوا (?:لي )?(?:أموالي|مالي)",
                r"پیسے واپس|رقم واپس|ریفنڈ",
            ),
        ),
    ),
    (
        Boundary.DISCOUNT,
        _rx(
            (),
            (
                r"أريد خصم|أعطني خصم|هل يمكن (?:تخفيض|خصم)|تخفيض (?:ال)?(?:سعر|عرض)|خفض (?:ال)?سعر",
                r"ڈسکاؤنٹ|رعایت|قیمت کم کر|ریٹ کم",
            ),
        ),
    ),
    (
        Boundary.OTHER_PAY,
        _rx(
            (),
            (
                r"(?:الدفع|ادفع|أدفع)\s+(?:ب|عن طريق)\s*(?:ال)?(?:بطاقة|كاش|نقد\w*|بايبال|ابل باي|أبل باي)|الدفع بالبطاقة",
                r"کارڈ سے ادائیگی|جاز کیش|ایزی پیسہ|ادائیگی (?:کارڈ|نقد)",
            ),
        ),
    ),
    (
        Boundary.BANK_ASK,
        _rx(
            (),
            (
                r"(?:أرسل|ارسل|أعطني|اعطني|شاركني)\s+(?:لي )?(?:رقم|تفاصيل)\s*(?:حسابك|الحساب|حسابكم)|ما هو رقم حسابكم",
                r"(?:آپ کا|اپنا|ورک زیپ کا)\s*(?:بینک\s*)?اکاؤنٹ\s*(?:نمبر|ڈیٹیلز|تفصیل)",
            ),
        ),
    ),
    (
        Boundary.POLITICS,
        _rx(
            (
                r"who (?:will|is going to|would|should) win (?:the |this |next )?(?:\w+ )?(?:election|elections|vote|polls?)",
                r"is (?:islam|hinduism|christianity|religion|sharia)\b[^.?!\n]{0,30}\b(?:against|forbid\w*|ban\w*|allow\w*|permit\w*)",
            ),
            (
                r"من سيفوز في (?:ال)?انتخابات|رأيك في (?:ال)?(?:حكومة|حزب|انتخابات|سياسة)|لمن أصوت",
                r"الیکشن (?:میں )?کون جیت|ووٹ کسے|کس کو ووٹ|حکومت کے بارے میں|سیاسی",
            ),
        ),
    ),
    (
        Boundary.OFF_TOPIC,
        _rx(
            (
                r"(?:write|draft|make|create) (?:me )?(?:a |an )?(?:marketing|social media|instagram|facebook|linkedin|blog|"
                r"promotional|sales) (?:post|caption|ad|email|copy|article|reel script)",
                r"translate (?:this|the following|it)\b",
                r"solve (?:my|this|the) (?:homework|assignment|exam|quiz|sum|puzzle)",
            ),
        ),
    ),
)
BOUNDARY_PATTERNS = (
    (
        (Boundary.ILLEGAL, ILLEGAL_PATTERNS),
        (Boundary.FRAUD, FRAUD_PATTERNS),
        (Boundary.BANK_CHANGE, _BANK_CHANGE_MORE),
    )
    + BOUNDARY_PATTERNS
    + _SCRIPT_BOUNDARIES
)

BOUNDARY_TEXT = {
    "en": {
        Boundary.DELETION: "I've passed your request to delete your information to the Workzap team. They'll confirm here once it's done, and I won't note anything new in the meantime.",
        Boundary.POLITICS: "I stay out of politics and opinions. I'm here to note what's getting in the way of your business. What's the biggest thing right now?",
        Boundary.COMPETITOR: "I don't compare Workzap with other companies. I'm here to note what's getting in the way of your business. What's the biggest thing right now?",
        Boundary.OUTCOME: "I can't promise results. I can note the problem and Workzap can describe what it would do about it. What's the problem?",
        Boundary.FRAUD: "I can't help with false invoices, forged or backdated records, bribes or hiding income. If the real records are hard to keep, or someone is doing this to you, I can note that as a problem. Want me to?",
        Boundary.THIRD_PARTY: "I can't share anyone else's chats. I only keep what you tell me in this chat. What would you like to note about your business?",
        Boundary.BANK_CHANGE: "I can't confirm any bank details in this chat. Payment details are only on your approved quote, and I've flagged your message to the Workzap team to check.",
        Boundary.OFF_TOPIC: "That's outside what I'm for. I'm here to note what's getting in the way of your business. What's the biggest thing right now?",
        Boundary.COMPLAINT: "Thanks for telling me. I've passed this to the Workzap team.",
        Boundary.ILLEGAL: "I can't help with that. I'm here for problems in your business.",
        Boundary.REFUND: "I can't decide refunds or payment disputes. I've passed this to the Workzap team with your message, and they'll reply here.",
        Boundary.BANK_ASK: "Bank details come on an approved quote. Nothing is owed until you approve one.",
        Boundary.BANK_ASK_APPROVED: "They're on your approved quote. I can resend the quote if you need it.",
        Boundary.OTHER_PAY: "Payment is by bank transfer, with details on your approved quote. If you need another way, I'll ask the Workzap team.",
        Boundary.DISCOUNT: "I can't change the quote, but I'll pass the request to Workzap. They'll reply here.",
        Boundary.PAY_FOR_ME: "I can't make payments. I can note it if paying suppliers is a problem in your business.",
        Boundary.PRODUCT_REC: "I don't recommend products. I can note what's wrong with your current setup so Workzap can look at it.",
        Boundary.DECIDE_FOR_ME: "That's your call: I don't decide for you. I can show you what you've told me, sorted, so it's easier to see.",
        Boundary.RIVAL: "I don't comment on other businesses. What's going wrong on your side?",
        Boundary.WRONG_NUMBER: "I think you may have the wrong number. I'm pi, an AI from Workzap, here for business problems.",
        Boundary.MEMORY_ASK: "I keep the problems you've told me, the details you added, and any documents and quotes. You can ask me to delete them.",
        Boundary.QUOTE_ONLY: "The quote is for building what's in the document, so they come together. I can only ask Workzap for both.",
    },
    "roman_ur": {
        Boundary.DELETION: "Aap ka data delete karne ki darkhwast maine Workzap ki team ko bhej di hai. Wo yahan tasdeeq kar dein ge, aur tab tak kuch naya note nahi kiya jayega.",
        Boundary.POLITICS: "Siyasat aur rai is chat ke dayre se bahar hain. Main aap ke business mein rukawat note karne ke liye hoon. Abhi sab se bada masla kya hai?",
        Boundary.COMPETITOR: "Workzap ka doosri companies se muqabla yahan nahi kiya jata. Main aap ke business mein rukawat note karne ke liye hoon. Abhi sab se bada masla kya hai?",
        Boundary.OUTCOME: "Nateejon ka wada nahi kiya ja sakta. Masla note kiya ja sakta hai, aur Workzap bata sakta hai wo kya karega. Masla kya hai?",
        Boundary.FRAUD: "Jali invoice ya aamdani chupane mein madad nahi ki ja sakti. Agar asli invoices ka hisaab rakhna mushkil hai to ise masla note kiya ja sakta hai. Kya note kar loon?",
        Boundary.THIRD_PARTY: "Kisi aur ki chat share nahi ki ja sakti. Sirf wo rakha jata hai jo aap is chat mein batate hain. Business ke baare mein kya note kar loon?",
        Boundary.BANK_CHANGE: "Is chat mein bank details ki tasdeeq nahi ki ja sakti. Payment ki tafseel sirf aap ke approved quote par hoti hai. Maine aap ka paigham Workzap ki team ko check ke liye bhej diya hai.",
        Boundary.OFF_TOPIC: "Ye mere dayre se bahar hai. Main aap ke business mein rukawat note karne ke liye hoon. Abhi sab se bada masla kya hai?",
        Boundary.COMPLAINT: "Batane ka shukriya. Maine ye Workzap ki team tak pahuncha diya hai.",
        Boundary.ILLEGAL: "Is mein madad nahi ki ja sakti. Main aap ke business ke masail ke liye hoon.",
        Boundary.REFUND: "Refund ya payment ke jhagde ka faisla yahan nahi kiya ja sakta. Maine ye Workzap ki team ko aap ke paigham ke saath bhej diya hai, wo yahin jawab dein ge.",
        Boundary.BANK_ASK: "Bank ki tafseel approved quote par hoti hai. Jab tak aap approve na karein, kuch wajib nahi.",
        Boundary.BANK_ASK_APPROVED: "Wo aap ke approved quote par hain. Zaroorat ho to quote dobara bheja ja sakta hai.",
        Boundary.OTHER_PAY: "Payment bank transfer se hoti hai, tafseel aap ke approved quote par hai. Koi aur tareeqa chahiye to Workzap ki team se poochha ja sakta hai.",
        Boundary.DISCOUNT: "Quote badalna mere ikhtiyar mein nahi; ye darkhwast Workzap tak pahuncha di jayegi. Wo yahin jawab dein ge.",
        Boundary.PAY_FOR_ME: "Payments mere bas mein nahi. Agar suppliers ko payment karna aap ke business ka masla hai to ise note kiya ja sakta hai.",
        Boundary.PRODUCT_REC: "Products recommend nahi kiye jate. Aap ke mojooda setup mein kya masla hai, ye note kiya ja sakta hai taake Workzap dekh sake.",
        Boundary.DECIDE_FOR_ME: "Ye aap ka faisla hai: aap ke liye faisla nahi kiya jata. Aap ne jo bataya wo sort karke dikhaya ja sakta hai taake dekhna aasan ho.",
        Boundary.RIVAL: "Main doosre businesses par raaye nahi deta. Aap ki taraf kya masla chal raha hai?",
        Boundary.WRONG_NUMBER: "Lagta hai aap ne galat number mila diya hai. Main pi hoon, Workzap ka AI, business ke masail ke liye.",
        Boundary.MEMORY_ASK: "Aap ke batae hue masail, aap ki di hui tafseel, aur documents aur quotes rakhe jate hain. Aap inhein delete karne ko keh sakte hain.",
        Boundary.QUOTE_ONLY: "Quote us cheez ka hota hai jo document mein likhi hai, isliye dono saath aate hain. Dono hi Workzap se manga ja sakte hain.",
    },
    "ar": {
        Boundary.DELETION: "لقد أرسلت طلب حذف معلوماتك إلى فريق Workzap. سيؤكدون هنا عند الانتهاء، ولن أسجّل أي شيء جديد في هذه الأثناء.",
        Boundary.POLITICS: "أبتعد عن السياسة والآراء. أنا هنا لأسجّل ما يعيق عملك. ما أكبر شيء الآن؟",
        Boundary.COMPETITOR: "لا أقارن Workzap بشركات أخرى. أنا هنا لأسجّل ما يعيق عملك. ما أكبر شيء الآن؟",
        Boundary.OUTCOME: "لا أستطيع وعدك بنتائج. يمكنني تسجيل المشكلة ويمكن لـ Workzap أن تشرح ما ستفعله حيالها. ما المشكلة؟",
        Boundary.FRAUD: "لا أستطيع المساعدة في فواتير مزورة أو إخفاء الدخل. إن كان تتبع الفواتير الحقيقية صعبًا في عملك فيمكنني تسجيل ذلك كمشكلة. هل أفعل؟",
        Boundary.THIRD_PARTY: "لا أستطيع مشاركة محادثات أي شخص آخر. أحتفظ فقط بما تخبرني به في هذه المحادثة. ماذا تريد أن أسجّل عن عملك؟",
        Boundary.BANK_CHANGE: "لا أستطيع تأكيد أي تفاصيل بنكية في هذه المحادثة. تفاصيل الدفع موجودة فقط في عرض السعر المعتمد، وقد أرسلت رسالتك إلى فريق Workzap للتحقق.",
        Boundary.OFF_TOPIC: "هذا خارج ما أقوم به. أنا هنا لأسجّل ما يعيق عملك. ما أكبر شيء الآن؟",
        Boundary.COMPLAINT: "شكرًا لإخباري. لقد أحلت هذا إلى فريق Workzap.",
        Boundary.ILLEGAL: "لا أستطيع المساعدة في ذلك. أنا هنا لمشكلات عملك.",
        Boundary.REFUND: "لا أستطيع البت في الاسترداد أو نزاعات الدفع. لقد أحلت هذا إلى فريق Workzap مع رسالتك وسيردون هنا.",
        Boundary.BANK_ASK: "تفاصيل الحساب البنكي تأتي مع عرض السعر المعتمد. لا يترتب عليك شيء حتى توافق على عرض.",
        Boundary.BANK_ASK_APPROVED: "هي موجودة في عرض السعر المعتمد. يمكنني إعادة إرسال العرض إن احتجت.",
        Boundary.OTHER_PAY: "الدفع عن طريق التحويل البنكي وتفاصيله في عرض السعر المعتمد. إن احتجت طريقة أخرى فسأسأل فريق Workzap.",
        Boundary.DISCOUNT: "لا أستطيع تغيير عرض السعر، لكنني سأنقل الطلب إلى Workzap وسيردون هنا.",
        Boundary.PAY_FOR_ME: "لا أستطيع إجراء المدفوعات. يمكنني تسجيل ذلك إن كان دفع الموردين مشكلة في عملك.",
        Boundary.PRODUCT_REC: "لا أوصي بمنتجات. يمكنني تسجيل ما يعيق إعدادك الحالي ليطّلع عليه فريق Workzap.",
        Boundary.DECIDE_FOR_ME: "القرار قرارك ولا أقرر عنك. يمكنني أن أريك ما أخبرتني به مرتبًا ليسهل عليك رؤيته.",
        Boundary.RIVAL: "لا أعلّق على أعمال الآخرين. ما الذي يسير بشكل خاطئ من جانبك؟",
        Boundary.WRONG_NUMBER: "أظن أن الرقم خاطئ. أنا pi، ذكاء اصطناعي من Workzap، هنا لمشكلات الأعمال.",
        Boundary.MEMORY_ASK: "أحتفظ بالمشكلات التي أخبرتني بها والتفاصيل التي أضفتها وأي مستندات وعروض أسعار. يمكنك أن تطلب مني حذفها.",
        Boundary.QUOTE_ONLY: "عرض السعر خاص ببناء ما في المستند، لذلك يأتيان معًا. يمكنني طلب الاثنين من Workzap.",
    },
}


def boundary_asked(text: str) -> Boundary | None:
    said = " ".join((text or "").split())
    for kind, pattern in BOUNDARY_PATTERNS:
        if pattern.search(said):
            return kind
    return None


ASKS_WHAT_PROBLEM = {
    "en": ("What's the problem?", "What else is getting in the way?"),
    "roman_ur": ("Masla kya hai?", "Aur kya cheez rukawat bani hui hai?"),
    "ar": ("ما المشكلة؟", "ما الذي يعيق عملك أيضًا؟"),
}


def boundary_reply(kind: Boundary, language: str | None, noted: bool = False) -> str:
    """The fixed line for a limit. When problems are already noted, "What's the problem?" would
    ask again what they have told (R-MEM-02), so the question asks for what else."""
    text = BOUNDARY_TEXT.get(language or "en", BOUNDARY_TEXT["en"])[kind]
    asked, instead = ASKS_WHAT_PROBLEM.get(language or "en", ASKS_WHAT_PROBLEM["en"])
    if noted and text.endswith(asked):
        return text[: -len(asked)] + instead
    return text


# --- enquiries that are not problems: pi is Workzap's front door (R-ROUTE-01, spec 6.9) ----------


class Enquiry(StrEnum):
    DEMO = "demo_request"
    JOBS = "jobs"
    VENDOR = "vendor"
    PARTNERSHIP = "partnership"
    PRESS = "press"
    EXISTING_PROJECT = "existing_project"  # 6.9: a question about a project Workzap runs
    TECHNICAL = "technical_failure"  # 6.9: a nori bug or outage from an existing customer


ENQUIRY_PATTERNS: tuple[tuple[Enquiry, re.Pattern[str]], ...] = (
    (
        Enquiry.TECHNICAL,
        re.compile(
            r"\b(?:nori|your (?:app|system|dashboard)|the (?:app|dashboard))\b[^.?!\n]{0,40}"
            r"\b(?:is down|not working|stopped working|crashed|has a bug|buggy|won'?t (?:open|load)|"
            r"not loading|outage)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Enquiry.EXISTING_PROJECT,
        re.compile(
            r"\b(?:status|update|progress|any news)\b[^.?!\n]{0,25}\b(?:my|our|the)\b[^.?!\n]{0,20}"
            r"\bproject\b|\b(?:our|my) project with workzap\b|\bproject (?:ka|ki) (?:status|update)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Enquiry.PRESS,
        re.compile(
            r"\b(?:journalist|press (?:release|enquiry|inquiry)|media (?:enquiry|inquiry|request)|"
            r"interview (?:with|you|workzap)|write (?:an )?article about (?:you|workzap|nori))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Enquiry.DEMO,
        re.compile(
            r"\b(?:(?:book|arrange|schedule|request|want|need|get)(?: me)?(?: a| an)? (?:nori )?demo|"
            r"demo (?:of|for) nori|nori demo)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Enquiry.JOBS,
        re.compile(
            r"\b(?:job application|apply for (?:a |the )?(?:job|position|role)|are you hiring|"
            r"any (?:vacancy|vacancies|openings)|attached (?:is )?my (?:cv|resume)|my (?:cv|resume) (?:is|for)|"
            r"looking for (?:a )?job)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Enquiry.PARTNERSHIP,
        re.compile(
            r"\b(?:partner(?:ship)? with (?:you|workzap|nori)|reseller|resell (?:nori|workzap)|"
            r"become (?:a )?(?:partner|distributor)|collaborat\w+ with (?:you|workzap))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Enquiry.VENDOR,
        re.compile(
            r"\b(?:we (?:can )?(?:supply|offer|provide) (?:you|workzap)|our (?:company|agency) (?:offers|provides|supplies)|"
            r"offer(?:ing)? you our (?:services|products)|we are (?:a )?(?:supplier|vendor|agency) (?:of|for|that))\b",
            re.IGNORECASE,
        ),
    ),
)
ENQUIRY_TEXT = {
    "en": {
        Enquiry.DEMO: "I'll pass that to the Workzap team. How many shops do you have, roughly?",
        Enquiry.JOBS: "Thanks. I'll pass your interest to the Workzap team. Please don't send ID documents here.",
        Enquiry.VENDOR: "Thanks. I'll pass it to the Workzap team.",
        Enquiry.PARTNERSHIP: "Thanks. I'll pass that to the Workzap team. Which company is this, and in which country?",
        Enquiry.PRESS: "I'll pass that to the Workzap team. I can't give quotes or statements.",
        Enquiry.EXISTING_PROJECT: "I'll pass that to the Workzap team, who have your project. They'll reply here.",
        Enquiry.TECHNICAL: "I'm sorry that's happening. I've passed it to the Workzap support team now. They'll reply here.",
    },
    "roman_ur": {
        Enquiry.DEMO: "Ye Workzap ki team tak pahuncha diya jayega. Aap ki roughly kitni dukanein hain?",
        Enquiry.JOBS: "Shukriya. Aap ki dilchaspi Workzap ki team tak pahuncha di jayegi. Meherbani karke yahan ID documents na bhejein.",
        Enquiry.VENDOR: "Shukriya. Ye Workzap ki team tak pahuncha diya jayega.",
        Enquiry.PARTNERSHIP: "Shukriya. Ye Workzap ki team tak pahuncha diya jayega. Ye kaun si company hai, aur kis mulk mein?",
        Enquiry.PRESS: "Ye Workzap ki team tak pahuncha diya jayega. Koi quote ya bayan nahi diya ja sakta.",
        Enquiry.EXISTING_PROJECT: "Ye Workzap ki team ko bhej diya gaya hai, jin ke paas aap ka project hai. Wo yahin jawab dein ge.",
        Enquiry.TECHNICAL: "Afsos ke aisa ho raha hai. Ye Workzap ki support team ko bhej diya gaya hai. Wo yahin jawab dein ge.",
    },
}


def enquiry_asked(text: str) -> Enquiry | None:
    said = " ".join((text or "").split())
    for kind, pattern in ENQUIRY_PATTERNS:
        if pattern.search(said):
            return kind
    return None


def enquiry_reply(kind: Enquiry, language: str | None) -> str:
    return ENQUIRY_TEXT.get(language or "en", ENQUIRY_TEXT["en"])[kind]


# --- a language pi cannot read yet (RT19): graceful, never mocking ---------------------------------

PASHTO_LETTERS = re.compile("[\u067c\u0689\u0693\u0696\u069a\u06bc\u06cd\u06d0]")
# Sindhi writes Arabic script with letters Urdu does not use (the implosives and nasals).
SINDHI_LETTERS = re.compile(
    "[\u067b\u067f\u0680\u0683\u0684\u0687\u068a\u068c\u068d\u068f\u06a6\u06aa\u06b1\u06b3\u06bb\u0699]"
)
GURMUKHI = re.compile("[\u0a00-\u0a7f]")  # Punjabi written in Gurmukhi
# One polite line for Pashto, Punjabi (Gurmukhi) and Sindhi: the English part keeps "I can't read
# Pashto well yet" (the first language people write it in). The Roman Urdu part is gender-neutral.
UNSUPPORTED_TEXT = (
    "I can't read Pashto well yet, and the same goes for Punjabi and Sindhi, and I'd rather not "
    "guess. Please write to me in English or Urdu (Roman or script) and I'll note everything you "
    "tell me. "
    "Abhi mere liye Pashto, Punjabi aur Sindhi theek se padhna mushkil hai. Meherbani karke "
    "English ya Urdu mein likhein."
)


def unsupported_language(text: str) -> bool:
    """Pashto, Sindhi or Punjabi in Gurmukhi: letters Urdu does not use, two or more of them in
    the message. (Punjabi in Shahmukhi reads as Urdu script and is answered as Urdu.)"""
    text = text or ""
    return any(
        len(pattern.findall(text)) >= 2 for pattern in (PASHTO_LETTERS, SINDHI_LETTERS, GURMUKHI)
    )


# --- questions about nori, answered from the approved facts only (spec 0.4, 6.9, golden G15) -------


class Nori(StrEnum):
    VISION = "vision"
    PRICING = "pricing"
    ABOUT = "about"


NORI_PATTERNS: tuple[tuple[Nori, re.Pattern[str]], ...] = (
    (
        Nori.VISION,
        re.compile(r"(?=.*\bnori\b)(?=.*\b(?:cctv|camera|cameras|vision)\b)", re.IGNORECASE),
    ),
    (
        Nori.PRICING,
        re.compile(
            r"(?=.*\bnori\b)(?=.*\b(?:price|prices|pricing|cost|plans?|kitna|qeemat|kharcha)\b)",
            re.IGNORECASE,
        ),
    ),
    (
        Nori.ABOUT,
        re.compile(
            r"\b(?:tell me about nori|what(?:'s| is) nori|nori (?:kya|what)|about nori|saw nori|"
            r"heard (?:of|about) nori)\b",
            re.IGNORECASE,
        ),
    ),
)
NORI_TEXT = {
    "en": {
        Nori.VISION: "nori's Vision (CCTV) area is coming soon. It isn't available yet. nori today reads sales and stock from every shop and gives a short morning read. Is something in your shops prompting the question?",
        Nori.PRICING: "nori has three plans: Starter, Growth and Enterprise, which differ by size and support. The prices are at workzap.ai/nori/pricing.",
        Nori.ABOUT: "nori is Workzap's daily read for the shop. Each night it reads sales and stock from every shop, and each morning it gives one short read of what changed, why, and what to look at. There is more at workzap.ai/nori. Is something in your business prompting the question?",
    },
    "roman_ur": {
        Nori.VISION: "nori ka Vision (CCTV) hissa jald aa raha hai. Abhi available nahi hai. nori aaj har dukaan ki sales aur stock parh kar subah ek chhota sa read deta hai. Kya aap ki dukanon mein kuch aisa hai jis ki wajah se ye sawal aaya?",
        Nori.PRICING: "nori ke teen plans hain: Starter, Growth aur Enterprise, jo size aur support mein farq rakhte hain. Qeematein workzap.ai/nori/pricing par hain.",
        Nori.ABOUT: "nori Workzap ka dukaan ke liye roz ka read hai. Har raat ye har dukaan ki sales aur stock parhta hai. Subah ek chhota read deta hai: kya badla, kyun, aur kis par nazar rakhni hai. Mazeed workzap.ai/nori par hai. Kya aap ke business mein kuch aisa hai jis ki wajah se ye sawal aaya?",
    },
}


def nori_asked(text: str) -> Nori | None:
    said = " ".join((text or "").split())
    for kind, pattern in NORI_PATTERNS:
        if pattern.search(said):
            return kind
    return None


def nori_reply(kind: Nori, language: str | None) -> str:
    return NORI_TEXT.get(language or "en", NORI_TEXT["en"])[kind]


# --- abuse, harassment, spam, complaints, illegal asks (spec 6.7, 6.8) --------------------------


class Abuse(StrEnum):
    INSULT = "insult"
    THREAT = "threat"
    SEXUAL = "sexual_or_hate"
    SPAM = "spam"


ABUSE_PATTERNS: tuple[tuple[Abuse, re.Pattern[str]], ...] = (
    (
        Abuse.THREAT,
        re.compile(
            r"\b(?:i(?:'ll| will)|i'm going to|i am going to)\s+(?:kill|hurt|beat|burn|destroy|shoot|stab|ruin)\b"
            r"[^.?!\n]{0,40}\b(?:you|workzap|your staff|your team)\b"
            r"|\b(?:maar dunga|maar dalunga|jaan se maar|dekh lunga tumhe|tumhe nahi chhodunga|"
            r"i know where you (?:live|work))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Abuse.SEXUAL,
        re.compile(
            r"\b(?:send (?:me )?nudes?|sex chat|porn|xxx|naked pics?|sexy (?:pics?|girl)|suck my|"
            r"nigger|faggot)\b",
            re.IGNORECASE,
        ),
    ),
    (
        # An offer from a stranger, not a business that happens to deal in money or crypto.
        Abuse.SPAM,
        re.compile(
            r"\b(?:earn \$?\d+|make money (?:fast|online)|guaranteed returns|investment opportunity|"
            r"click (?:this|the) link|join my (?:whatsapp )?group|loan approved|buy followers|"
            r"seo services|you(?:'ve| have) won|lottery winner|double your (?:money|bitcoin)|"
            r"cheap (?:viagra|pills))\b",
            re.IGNORECASE,
        ),
    ),
    (
        Abuse.INSULT,
        re.compile(
            r"\b(?:you(?:'re| are)?|u|tum|tu|aap)\s+(?:are\s+|r\s+|ho\s+)?(?:a\s+|an\s+)?"
            r"(?:stupid|useless|idiot|dumb|moron|trash|garbage|worthless|ullu|gadha|bewakoof|nikamma)\b"
            r"|\b(?:this|the)\s+bot\s+is\s+(?:useless|stupid|trash|garbage|dumb)\b"
            r"|^\W*(?:just\s+)?shut up\b|\byou\s+shut up\b"  # not "the shop shut up early"
            r"|\b(?:fuck you|fuck off|stupid bot|useless bot|dumb bot|bakwas bot|chup kar|"
            r"bhenchod|madarchod|chutiya)\b",
            re.IGNORECASE,
        ),
    ),
)


ABUSE_PATTERNS = ABUSE_PATTERNS + (
    (
        Abuse.THREAT,
        _rx(
            (),
            (
                r"سأقتلك|سوف أقتلك|سأقتل|سأحرق|سأضربك|سأدمرك|أعرف أين تسكن",
                r"میں تمہیں مار|مار دوں گا|جان سے مار|قتل کر دوں|دیکھ لوں گا تمہیں",
            ),
        ),
    ),
    (
        Abuse.SEXUAL,
        _rx((), (r"صور عارية|ارسل صور عارية|سكس|ننگی تصویر|فحش (?:تصاویر|ویڈیو)",)),
    ),
    (
        Abuse.SPAM,
        _rx(
            (), (r"أرباح مضمونة|اضغط على الرابط|فزت بجائزة|لنک پر کلک|انعام جیتا|گارنٹی شدہ منافع",)
        ),
    ),
    (
        Abuse.INSULT,
        _rx(
            (),
            (
                r"أنت (?:غبي|حمار|فاشل|عديم الفائدة|سخيف)|يا غبي|يا حمار|اخرس|اسكت",
                r"تم (?:بیوقوف|گدھے|نکمے|ناکارہ)|بکواس بوٹ|چپ کرو|گھٹیا",
            ),
        ),
    ),
)

# Ways of asking pi to stop writing (R-FUP-02), beyond a bare "stop": the caller that records the
# withdrawal of consent uses this too.
OPT_OUT_PHRASE = re.compile(
    r"^\W*(?:(?:pl(?:ea)?se|pls|plz)\s+)?(?:stop|unsubscribe|opt[\s-]?out)(?:\s+(?:messaging|texting|msg(?:ing)?|"
    r"contacting|writing|sending)(?:\s+me)?(?:\s+(?:again|now|please|pls))?)?\W*$"
    r"|\b(?:pl(?:ea)?se|pls|plz)?\s*(?:do(?:n'?t| not)|dont|never)\s+(?:msg|message|text|contact|write(?: to)?|"
    r"whatsapp|call)\s+me(?:\s+again|\s+anymore|\s+any more)?\b"
    r"|\b(?:leave me alone|stop (?:messaging|texting|contacting|writing to) me|no more messages|"
    r"remove me from (?:the |your )?(?:list|chat)|band karo|band kar do|reminders? band kar(?:ein|do)|mujhe message na karo|"
    r"mujhe msg mat karo|dobara message mat karo)\b"
    r"|(?:لا ترسل لي|توقف عن (?:مراسلتي|الإرسال)|دعني وشأني)|(?:مجھے میسج نہ کریں|مجھے تنگ نہ کریں|میسج بند کریں)",
    re.IGNORECASE,
)


def opt_out_asked(text: str) -> bool:
    """Whether the person asked pi to stop writing to them."""
    return bool(OPT_OUT_PHRASE.search(" ".join((text or "").split())))


def abuse_asked(text: str) -> Abuse | None:
    said = " ".join((text or "").split())
    for kind, pattern in ABUSE_PATTERNS:
        if pattern.search(said):
            return kind
    return None


ABUSE_TEXT = {
    "en": {
        "calm": "I'm here to help with the business problems when you're ready.",
        "warn": "I'm happy to keep helping with your business. If this continues I'll have to pass this chat to the Workzap team.",
        "refuse": "I can't continue with that. I'm here for problems in your business.",
        "spam": "I'm here for problems in your business.",
        "pass": "I'm passing this chat to the Workzap team.",
    },
    "roman_ur": {
        "calm": "Main business ke masail mein madad ke liye hoon, jab aap tayyar hon.",
        "warn": "Main aap ke business mein madad karne ko tayyar hoon. Agar ye jari raha to mujhe ye chat Workzap ki team ko dena paray gi.",
        "refuse": "Main is par aage nahi chal sakta. Main aap ke business ke masail ke liye hoon.",
        "spam": "Main aap ke business ke masail ke liye hoon.",
        "pass": "Ye chat Workzap ki team ko di ja rahi hai.",
    },
}


@dataclass(frozen=True)
class AbuseStep:
    text: str
    strikes: int
    move: str | None  # "X_BLOCKED" or "X_OUT_OF_SCOPE": the state to go to
    escalate: str | None  # the staff reason, when someone must look


def abuse_step(kind: Abuse, strikes: int, language: str | None) -> AbuseStep:
    """What pi says and does for one abusive message, given the strikes so far (spec 6.7): an
    insult gets a calm line, a warning on the third strike and a hand-over on the fifth; a threat
    gets one warning and an escalation, then a hand-over; sexual content or hate gets one refusing
    line; spam gets one line and then silence."""
    table = ABUSE_TEXT.get(language or "en", ABUSE_TEXT["en"])
    if kind == Abuse.SPAM:
        return AbuseStep(table["spam"], strikes, "X_OUT_OF_SCOPE", None)
    if kind == Abuse.THREAT:
        if strikes >= 3:
            return AbuseStep(table["pass"], strikes + 1, "X_BLOCKED", "abuse_threat")
        return AbuseStep(table["warn"], 3, None, "abuse_threat")
    count = strikes + 1
    if count >= 5:
        return AbuseStep(table["pass"], count, "X_BLOCKED", "abuse")
    if kind == Abuse.SEXUAL:
        return AbuseStep(table["refuse"], count, None, "abuse" if count == 3 else None)
    if count == 3:
        return AbuseStep(table["warn"], count, None, None)
    return AbuseStep(table["calm"], count, None, None)


def stay_silent(state: str | None, text: str, brief: dict[str, Any] | None = None) -> bool:
    """Whether pi says nothing at all: a chat a person has to clear (blocked), more spam and
    abuse after pi already answered it once, or a trade Workzap does not serve (declined once)."""
    if state == "X_BLOCKED":
        return True
    if state == "X_OUT_OF_SCOPE" and (brief or {}).get("declined_trade"):
        return True
    return state == "X_OUT_OF_SCOPE" and abuse_asked(text) is not None


# --- regulated and restricted trades: only where Workzap has decided to serve them (spec 7.N) ------

REGULATED_TRADES: dict[str, re.Pattern[str]] = {
    "tobacco": re.compile(
        r"\b(?:tobacco|vape|vaping|e-?liquid|cigarettes?|hookah (?:shop|lounge))\b", re.IGNORECASE
    ),
    "alcohol": re.compile(
        r"\b(?:liquor|licensed alcohol|alcohol (?:retail|shop|store)|wine shop|spirits? (?:shop|store))\b",
        re.IGNORECASE,
    ),
    "arms": re.compile(
        r"\b(?:arms and ammunition|ammunition dealer|arms dealer|gun shop|firearms?|"
        r"licensed arms|weapons? (?:shop|dealer))\b",
        re.IGNORECASE,
    ),
    "bullion": re.compile(r"\b(?:gold bullion|bullion (?:dealer|trader|shop))\b", re.IGNORECASE),
    "money_services": re.compile(
        r"\b(?:money exchange|currency exchange|forex (?:exchange|dealer|bureau|shop)|"
        r"remittance (?:business|shop|agent)|hawala|money transfer (?:business|shop|agent))\b",
        re.IGNORECASE,
    ),
    "controlled_medicines": re.compile(
        r"\b(?:controlled medicines?|controlled drugs?|narcotics?|opioids?)\b", re.IGNORECASE
    ),
    "gambling": re.compile(
        r"\b(?:casino|betting (?:shop|business)|gambling|bookmaker|lottery (?:business|shop))\b",
        re.IGNORECASE,
    ),
    "cannabis": re.compile(r"\b(?:cannabis|marijuana|dispensary)\b", re.IGNORECASE),
    "adult": re.compile(
        r"\b(?:adult (?:services|store|shop|entertainment)|escort agency)\b", re.IGNORECASE
    ),
    "crypto": re.compile(
        r"\b(?:crypto(?:currency)? exchange|bitcoin exchange|crypto trading (?:platform|business))\b",
        re.IGNORECASE,
    ),
}

NOT_SERVED_TEXT = {
    "en": "Workzap doesn't take on work in this area, so I can't help with this one.",
    "roman_ur": "Workzap is shobe mein kaam nahi leta, is liye main is mein madad nahi kar sakta.",
}


def regulated_trade(text: str) -> str | None:
    """Which regulated trade the message says the person's business is in, if any."""
    said = " ".join((text or "").split())
    for trade, pattern in REGULATED_TRADES.items():
        if pattern.search(said):
            return trade
    return None


def not_served(text: str, served: list[str] | None) -> str | None:
    """The regulated trade pi must decline, or None. `served` is the workspace's configured list
    of served trades; when it was never set (None) leadership has not decided yet and nothing is
    declined. Once it is set, a regulated trade that is not on it is declined."""
    if served is None:
        return None
    trade = regulated_trade(text)
    return trade if trade is not None and trade not in served else None


def not_served_reply(language: str | None) -> str:
    return NOT_SERVED_TEXT.get(language or "en", NOT_SERVED_TEXT["en"])
