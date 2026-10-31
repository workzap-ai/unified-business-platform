# ruff: noqa: E501  (word lists read better on one line each)
"""A structured, high-recall emergency detector (pure: no I/O, no model, linear time).

`safety.emergency` used to be a hand-written keyword list, and patching it phrase by phrase never
ends. This module is the second layer: it runs only when the older patterns say nothing, so it can
only ADD detections, never remove one.

How it works
------------
1. The text is normalised: NFKC, zero-width and bidi marks removed, Arabic tashkeel and tatweel
   removed, alef / yeh / kaf / heh unified, Arabic-Indic and Devanagari digits turned into ASCII,
   Devanagari nukta removed, case folded, apostrophes dropped and runs of three or more equal
   letters cut to two.
2. The text is cut into clauses (punctuation and the words aur, lekin, and, but, phir) and whole
   tokens. Each token gets a bit mask of CONCEPT TAGS (event words, person words, place words,
   modifiers) from the lexicon below. A token the lexicon does not know is tried once more with every
   repeated letter collapsed, so "aaag", "laggi" and "gyaa" still match. Short multi-word phrases
   (for example "kha li", "jee nahi lagta") are looked up from their first word.
3. A rule is an ANCHOR concept plus NEEDED concepts inside a short window of tokens (not a whole
   message substring), plus an optional AVOID concept (an idiom that is only honoured when no danger
   word is anywhere in the message). Matching is by bit masks over a sliding window, so it is linear
   in the number of tokens (the tokens are capped, first 6000 and last 2000).
4. A TRADE rule is suppressed only when a trade word (rate, quote, bechna, insurance, extinguisher,
   website ...) is in the SAME clause as the hit AND no danger, urgency or person word is anywhere in
   the message. Nothing else ever suppresses. Quoted, forwarded and reported speech ("forwarded:",
   "bhai ne bola", "she said") fires, because the matching ignores who is speaking.

The eight classes are FIRE_SMOKE, TRAPPED, POISONING, MEDICAL_RESCUE, SELF_HARM, VIOLENCE_ABUSE,
CHILD_SAFEGUARDING and KIDNAP_ROBBERY (English, Roman Urdu with its spelling variants, Urdu, Hindi,
Arabic). `DISABLED` lets a test switch one class off to prove the tests depend on it.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

CLASSES = (
    "SELF_HARM",
    "FIRE_SMOKE",
    "TRAPPED",
    "POISONING",
    "MEDICAL_RESCUE",
    "VIOLENCE_ABUSE",
    "CHILD_SAFEGUARDING",
    "KIDNAP_ROBBERY",
)

# What each class answers with (the names of safety.Emergency members).
CLASS_KIND = {
    "SELF_HARM": "SELF_HARM",
    "FIRE_SMOKE": "FIRE",
    "TRAPPED": "GENERIC",
    "POISONING": "MEDICAL",
    "MEDICAL_RESCUE": "MEDICAL",
    "VIOLENCE_ABUSE": "VIOLENCE",
    "CHILD_SAFEGUARDING": "SAFEGUARDING",
    "KIDNAP_ROBBERY": "VIOLENCE",
}

DISABLED: set[str] = set()  # tests only: a class named here is switched off

_MAX_TOKENS = 8000
_HEAD_TOKENS = 6000

# --- normalisation ---------------------------------------------------------------------------

_TRANSLATE: dict[int, str | int | None] = {}
for _src, _dst in (
    ("أإآٱ", "ا"),  # alef forms -> alef
    ("يىئېےۓی", "ی"),  # yeh forms -> farsi yeh
    ("ك", "ک"),  # arabic kaf -> keheh
    ("هہھەةۃۀ", "ه"),  # heh forms -> heh
    ("ؤ", "و"),  # waw with hamza
    ("ں", "ن"),  # noon ghunna
    ("ٹ", "ت"),  # retroflex te
    ("ڈ", "د"),  # retroflex dal
    ("ڑ", "ر"),  # retroflex re
    ("ँ", "ं"),  # candrabindu -> anusvara
):
    for _c in _src:
        _TRANSLATE[ord(_c)] = _dst
for _i in range(10):
    _TRANSLATE[0x0660 + _i] = str(_i)
    _TRANSLATE[0x06F0 + _i] = str(_i)
    _TRANSLATE[0x0966 + _i] = str(_i)
for _c in "़ـ‌‍":  # nukta, tatweel, zwnj, zwj
    _TRANSLATE[ord(_c)] = None
for _cp in range(0x064B, 0x0660):  # tashkeel
    _TRANSLATE[_cp] = None
for _cp in (0x0670, 0x0654, 0x0655):
    _TRANSLATE[_cp] = None
for _cp in range(0x06D6, 0x06EE):
    _TRANSLATE[_cp] = None
for _c in "'’‘`":
    _TRANSLATE[ord(_c)] = None

_REPEAT3 = re.compile(r"(.)\1{2,}")
_REPEAT = re.compile(r"(.)\1+")
_CLAUSE_SPLIT = re.compile(r"[.!?;,،؛؟।॥|:\n…]+")
_TOKEN_SPLIT = re.compile(r"[\s\-/\\\"()\[\]{}<>*+=~^_@#$%&“”«»]+")
_PRECLEAN = re.compile(r"\b(?:bleeding edge|chor bazar|chor bazaar|fire sale|fire wall|firewall)\b")


def normalise(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Cf")
    s = s.translate(_TRANSLATE).casefold()
    s = _REPEAT3.sub(lambda m: m.group(1) * 2, s)
    return s


def _collapse(token: str) -> str:
    return _REPEAT.sub(lambda m: m.group(1), token)


# --- the lexicon -----------------------------------------------------------------------------

_BIT: dict[str, int] = {}
_LEX: dict[str, int] = {}
_LEX_COLLAPSED: dict[str, int] = {}
_PHRASES: dict[str, list[tuple[tuple[str, ...], int]]] = {}


def _bit(name: str) -> int:
    if name not in _BIT:
        _BIT[name] = 1 << len(_BIT)
    return _BIT[name]


def _mask(expr: str) -> int:
    m = 0
    for part in expr.split("|"):
        part = part.strip()
        if part:
            m |= _bit(part)
    return m


def W(tag: str, words: str) -> None:
    """Register single-word tokens (whitespace separated) for a concept tag."""
    b = _bit(tag)
    for w in words.split():
        n = normalise(w)
        _LEX[n] = _LEX.get(n, 0) | b
        c = _collapse(n)
        _LEX_COLLAPSED[c] = _LEX_COLLAPSED.get(c, 0) | b


def PH(tag: str, phrases: str) -> None:
    """Register multi-word phrases separated by `/` for a concept tag; the tag sits on the first word."""
    b = _bit(tag)
    for phrase in phrases.split("/"):
        toks = tuple(t for t in _TOKEN_SPLIT.split(normalise(phrase)) if t)
        if len(toks) < 2:
            continue
        _PHRASES.setdefault(toks[0], []).append((toks[1:], b))


def _cross(tag: str, firsts: str, seconds: str) -> None:
    PH(tag, "/".join(f"{a} {b}" for a in firsts.split() for b in seconds.split()))


# Shared modifiers ----------------------------------------------------------------------------
W("COPULA", "hai hain he h hy hen hn hy hein ہے ہیں है हैं hu hoon is are was")
W("PROG", "raha rahi rahe rha rhi rhe rahy raha-hai رہا رہی رہے रहा रही रहे rahay")
W("NEG", "nahi nhi nai na nahin mat نہیں نا नहीं ना not no cant cannot dont never")
W(
    "NEGB",
    "nahi nhi nai na nahin ruk ruka ruki rukta band atak phool phul ghut نہیں रुक नहीं cant cannot not stopped unable",
)
W(
    "HOGAYA",
    "ho hua hui hogaya hogayi hogya hogyi hone gaya gayi gai gae gaye gya gyi hue hoi hoa हो हुआ हुई गया गई ہو ہوا ہوئی گیا گئی",
)
W("PAST_GO", "gaya gayi gai gae gaye gya gyi gayee laggaya")
W("SAB", "sab sara saara sari saari sabhi sabkuch everything all kul")
W(
    "DANGER",
    "help madad bachao bachaao bachaw bachaye bachalo bachalein emergency urgent urgently jaldi jldi fauran foran turant abhi sos rescue immediately asap انقذوني النجده بچاو بچاؤ बचाओ मदद जल्दी خطر zakhmi injured khoon dying maut",
)
W(
    "PERSON",
    "mazdoor mazdur mazdoors mazdooron worker workers labour labourer labourers driver guard chowkidar aadmi admi aurat insan insaan banda bande bandi mard woman man men women people persons person patient mareez staff abbu abu ammi amma maa baap papa mama nana nani dada dadi buzurg bujurg shohar husband biwi wife behn bahen sister brother beta beti bete patni pati",
)
W(
    "CHILD",
    "bachay bache bachay bachey bachon bachi bacchi bachcha bacha bachchay bachche bachchi baccha bacchay bacchi bacchon baby babies child children kid kids toddler infant beta beti bete betay baby bachy bachi بچے بچی بچه بچوں اطفال الاطفال الطفل طفل बच्चे बच्चा बच्ची बच्चों बेटा बेटी बेटे",
)
W("PERSON_ANY", "log logon logo")

# Trade and idiom words that, in the same clause as a hit and with no danger anywhere, mean a business talk.
W(
    "TRADE",
    "rate rates quote quotes quotation price prices pricing qeemat keemat bechna bechni bechta bechte bechti bech sell selling seller sale sales buy buying kharid kharidna supply supplier suppliers dealer vendor wholesale retail install installation lagwana lagwani lagwane training course policy insurance bima claim claims extinguisher extinguishers alarm detector detectors sprinkler equipment brigade tender uniform lighter website logo poster marketing business company agency software app pos erp design designer banana banani banane estimate proposal invoice fleet cafe hookah agarbatti dhoop novel movie film thriller cover game drama series shop-owner safety capes kapde kapre toys toy garage repair lawyer fabric clinic delivery customer customers customer-ka dukandar شراء بيع बेचना कीमत",
)

# --- FIRE_SMOKE ------------------------------------------------------------------------------
W(
    "FIRE_N",
    "aag ag agg fire flames flame blaze blazing smoke dhuan dhua dhuaan dhuwan dhuvan chingari chingariyan chingaree spark sparks sparking shola sholay shole jhulas आग धुआं धुआँ धुवां धूआं चिंगारी शोले आग آگ دھواں دھوان دخان نار النار حریق حريق الحریق الحريق شعله چنگاری",
)
W(
    "OCC",
    "lag lagi laga lagg lagna lagta lagti lagy laggi phail phaila phaili phailna phailti bhadak bhadka bhadki bhadakna uth uthi utha uthna uthta nikal nikla nikli nikalna nikalti aa aarahi aaraha aarahe aaya aayi burning burnt burns caught broke spreading rising engulfed لگی लगी لگ लग नکل निकल اندلعت اندلع تصاعد उठ उठी",
)
W(
    "PLACE_OBJ",
    "dukan dukaan shop shops godown gudaam gudam godam factory fcatory workshop mill office ghar makan building imarat bakery restaurant hotel warehouse market plaza plant store kitchen gaari gadi car truck bike pump meter oven chulha chulhe stove taar taron tar wire wires wiring cable cables transformer boiler generator cylinder showroom hall school hospital flat apartment room کان گودام دکان محل مستودع فیکٹری गोदाम दुकान فكتورى مصنع",
)
W(
    "PLACE_BIG",
    "dukan dukaan shop godown gudaam gudam godam factory workshop mill office ghar makan building imarat bakery restaurant hotel warehouse plaza plant showroom flat apartment poori pura puri maal",
)
W("BURN_V", "jal jala jali jale jalta jalti jalte jalna jhulas جل جلا जल जला जली")
W("LIGHT_ON", "bulb light lights batti diya chiragh tube led lamp deepak candle mombatti tubelight")
W("MONEYY", "paisa paise paisay rupay rupee rupees money cash budget profit mehnat kamai dil")
W("FOODY", "khana chai roti doodh milk daal salan chawal sabzi")
W(
    "BLAST_N",
    "blast dhamaka dhamake explosion boom phat phata phati burst dhamakay بلاسٹ دھماکہ دھماکا धमाका",
)
W(
    "SALE_MKT",
    "sale offer discount deal launch ad ads marketing promo promotion bazar baazar dhamaka-sale",
)


# --- TRAPPED ---------------------------------------------------------------------------------
W(
    "STRONG_TRAP",
    "phas fas phans fans phase phanse phasa phansa phasay phansay phasi phansi phasey phansey atak atka atki atke trapped stuck mahsoor محتجز محتجزون محتجزین محتجزه پھنس پھنسے پھنسا پھنسی फंस फंसे फंसा फंसी फँस फस फसे",
)
W("DAB", "dab dabe dabay dabb dabi dabbe")
W("WEAK_TRAP", "band bandh bnd bandhay bandhe locked lock tala")
W(
    "INSIDE",
    "andar ander inside kamre kamra kamray room bathroom washroom gaari gadi car vehicle lift elevator ghar house godown fridge boot dukan-ke-andar اندر بالداخل داخل अंदर अन्दर लिफ्ट لفٹ مصعد",
)
W("INSIDE_STRICT", "andar ander inside اندر بالداخل داخل अंदर अन्दर")
W("LIFT", "lift elevator لفٹ لیفٹ लिफ्ट مصعد")
W("DEBRIS", "malba malbay malbe neeche chhat deewar girne collapse collapsed mitti")
W("ANYONE", "koi someone anyone somebody کوئی कोई احد")
W("DOOR", "darwaza darwaze darwaja door gate دروازه دروازہ दरवाज़ा दरवाजा दरवाज़े")
W("OPEN_V", "khul khulta khulna khulti khulte open khol کھل कھل खुल खुलता खुलती")
W("SCHOOLY", "school college madrasa dukan office market bazar shop")
W("TRAFFIC", "traffic jam signal")
W("RAKHA", "rakha rakhta rakhte rakhi rakhe rakh")

# --- POISONING -------------------------------------------------------------------------------
W(
    "TOXIC",
    "zehar zehr jahar zahar poison poisoned poisonous phenyl phenail phenyle bleach acid tezab tezaab kerosene pesticide cleaner thinner harpic dettol سم السم زهر زہر زہر جहर ज़हर जहर",
)
W(
    "MEDS",
    "dawai dawa dawaiyan dawaen goli goliyan tablet tablets pills pill medicine medicines syrup capsule capsules دوائی دوا دواء दवाई दवा गोली گولی گولیاں",
)
W("FOREIGN", "sikka coin battery magnet button cell lego sikke")
W(
    "QTY",
    "saari saari sab poori pura puri bohat bhot zyada overdose bottle strip packet sari sara poora whole all full bohut",
)
W(
    "INGEST_P",
    "khali piya pia pili pila swallowed drank ate eaten ingested consumed took ابتلع شرب بلع تناول",
)
W("INGEST_FUT_W", "loon lun lunga lungi leta leti doon doonga dun dunga لون लूंगा लूँगा लूंगी लूं")
for _a, _b in (
    (
        "kha khaa khaya khai nigal nigla pi pee piya pia pili peeya",
        "li liya lia le lee lii liye لی لیا ली लिया लिए",
    ),
    ("کھا پی", "لی لیا"),
    ("खा पी निगल", "ली लिया"),
):
    _cross("INGEST_DONE", _a, _b)
PH("INGEST_DONE", "kha li/kha liya/pi li/pee liya/pi liya/pee li/nigal liya/kha leta hoon")
_cross(
    "INGEST_FUT",
    "kha khaa pi pee nigal",
    "loon lun lunga lungi leta leti doon doonga dun dunga leta-hoon",
)
_cross("INGEST_FUT", "खा पी", "लूंगा लूँगा लूंगी लूं")
_cross("INGEST_FUT", "کھا", "لون لوں لوں")
PH("TOXIC", "mitti ka tel/mitti tel/mitti ke tel/diesel pi")
PH(
    "KUCHKHA",
    "kuch kha loon/kuch kha lun/kuch kha lunga/kuch kha lungi/kuch kha leta/kuch kha lu/kuch kha lo",
)
W(
    "FOODCTX",
    "bhook bhookh bhuk bhukh lagi khana lunch dinner nashta nashte chai paani roti phir baad ruk wait break thori thodi der baat karta karti",
)

# --- MEDICAL_RESCUE --------------------------------------------------------------------------
W("GAS_N", "gas gaas cylinder cylindar silinder گیس سلنڈر सिलेंडर गैस غاز")
W(
    "LEAK",
    "leak leakage leek lik risna ris rasaw tasarrub burst smell boo bu badboo لیک تسرب لیک लीक लीक रिस",
)
W("ELEC_N", "bijli bijlee current karant karent electric electricity shock بجلی کرنٹ करंट बिजली")
W("CHIPAK", "chipak chipk chipka chipki")
W("ELEC_V", "pakad pakda jhatka jhatke laga lagi lag lagna lagey shock")
W(
    "BILL",
    "bill units unit tariff reading charges load shedding gayi aayi account affairs price rate status stock location order",
)
W("WIRE", "taar tar taron wire wires cable")
W(
    "DOOB",
    "doob dooba doobi doobna doobta dubi drown drowned drowning ghark غرق ڈوب ڈوبا ڈوبنا डूब डूबा",
)
W("WATER", "pani paani river nehar talab pool samundar sailaab nadi dariya canal tank tub")
W(
    "WORKY",
    "paperwork work emails email debt orders tasks stress calls requests files bills messages kaam tension qarz meetings",
)
W("GOLI_V", "lag laga lagi lagna chal chali chalna chala")
W("TABLET_CTX", "dawai bukhar dard tablet pain lun loon khaun kha khani nigal paracetamol headache")
W(
    "SNAKE_N",
    "saap saanp sanp snake bichoo bichu bicchu scorpion kutta kutte kutay dog سانپ साँप सांप ثعبان عقرب",
)
W(
    "BITE",
    "kat kata kaat kaata katna kati dasa dasna dasta daska das dank dang bit bite bitten sting stung bitta لدغ ڈسا کاٹ ڈس काट डस لدغه",
)
W("BODY_S", "haddi taang bazu baazu pair paon kamar gardan hath haath ungli بازو ہڈی ٹانگ हड्डी टांग")
W(
    "BREAK",
    "toot toota tooti toote tut tuti fracture fractured broken kat kata kati kate kuchal kuchla",
)
W("BIZ", "business sales rate price market share stock demand orders dukan kaam mehngai")
W("SAR", "sar head")
W("PHAT", "phat phata phut phati toot")
W("KHOON", "khoon khun blood bleeding bleed bleeds خون ख़ून खून")
W(
    "FLOW",
    "beh bah bahna behna nikal nikla nikalna tapak ruk ruka rukta raha rahi gir bohat bhot zyada heavy heavily profusely badly بہہ بہ",
)
W(
    "FILMY",
    "film movie scene fake poster game horror shooting makeup costume drama edge software technology tech heart hearts",
)
W("SANS", "sans saans saanse sanse سانس साँस सांस")
W("BREATHE", "breathe breathing breath breathes التنفس نفس")
W(
    "NEGE",
    "cant cannot not no stopped stop unable struggling difficulty hard hardly trouble short without لا لم cant",
)
W("DAURA", "daura dora daure dauray دورہ دوره दौरा")
W(
    "PADH",
    "pad padh pada padi padha par para parh parha parhi paray pade پڑا پڑی پڑ پڑگیا पड़ा पडा पड़ पड पड़ी पडी पड़ गया",
)
W("FIT_N", "fit fits")
W("SEIZE_N", "mirgi seizure seizures convulsion convulsions convulsing epilepsy")
W("CUSTOMS", "customs goods cargo shipment assets property tax")
W(
    "FALL_P",
    "mazdoor mazdur worker labour labourer driver guard chowkidar abbu abu ammi amma nani nana dada dadi buzurg bujurg banda aadmi admi aurat mard bachay bache bachon bachi bachcha baby child",
)
W("GIR", "gir gira gire giri girgaya")
PH("GIR", "gir gaya/gir gayi/gir pada/gir padi/gir gaye/gir paray")
W("BP", "bp")
W("BP_LEVEL", "high low shoot barh zyada bohat kam")
W("BP_SYMPT", "chakkar behosh sans saans dard ghabrahat seena seene sar")
W("CHAKKAR", "chakkar chakar")
W("AARAHE", "aa aaraha aarahe aarahi aane aati aata aate")
W("DIZZY", "dizzy giddy")
W("NUM_EMERG", "1122 115 911")
W("NUM_999", "999 112")
W("MONEYW", "rs rupay rupees aed price offer package sale only discount =")
W(
    "CALLV",
    "call karo kro bulao bulaao bulaye bulalo bula dial phone fone ring bhejo bhej send ko کرو بلاو بلاؤ बुलाओ",
)
W("POLICE_N", "police pulis thana thaane rescue پولیس")
W("SUMMON", "bulao bulaao bulaye bulalo bula call karo kro bhejo bhej send bhejna")
W("BEHOSH", "behosh behoshi unconscious fainted faint بیهوش بے ہوش बेहोश बेहोशी")
W("HOSH", "hosh ہوش होश")
W("ACC", "accident accidents aksident exident ایکسیڈنٹ एक्सीडेंट حادث حادثه تصادم")
W("ACC_HOG", "ho hua hui hogaya hogayi hogya gaya gayi zakhmi हो हुआ हुई गया गई ہو ہوا ہوئی گیا گئی")
W("HEART_ATK", "ازمه ازمة قلبیه قلبية قلبيه")
PH("HEART_ATK", "ازمه قلبیه/ہارٹ اٹیک/हार्ट अटैक/ازمة قلبية/دل کا دورہ/दिल का दौरा/ازمه قلبیه")
W("AMBU", "ambulance ambulances ambulence ambulans ایمبولینس एम्बुलेंस एंबुलेंस اسعاف")
W(
    "AMBU_NEED",
    "chahiye chahie chaye zaroorat zarurat hire bhej bhejo bhijwao bulao bulaao bula call send need needed kab aayegi aa aayegi aarahi pohanch pahunch chahyie",
)
W("OVERDOSE", "overdose overdosed")
W("ULTI", "ulti dast vomit vomiting vomited diarrhoea diarrhea qay")

# --- SELF_HARM -------------------------------------------------------------------------------
W(
    "LIFE",
    "zindagi zindgi zindagee zindage jeevan jeena jina jeene jine life living زندگی ज़िंदगी जिंदगी जीवन جینا जीना जीने الحیاه الحياة حیاتی حياتي حیاتی",
)
W(
    "TIRED",
    "tang bezaar bezar thak thaka bojh boj bhaari bhari bekar nafrat ukta tired sick hate hated done fed enough worthless meaningless pointless تنگ तंग بیزار بوجھ बोझ تعبت تعب تعبان ملل",
)
W("INSURANCE", "insurance bima policy agency")
W(
    "WANT",
    "chahiye chahta chahti chahte chahie chahyie want wanna wish rather better off چاہتا چاہتی चाहता चाहती चाहते",
)
W("JEENA", "jeena jeene jina jine jeen جینا جینے जीना जीने")
W("WORTH", "worth")
W("KHATAM", "khatam khtm khatm khtam ختم खत्म ख़त्म")
W(
    "KARV",
    "kar karna karunga karoonga kardunga dunga doonga dungi lunga lungi lun loon doon dun karenge کر دون دوں लूंगा दूंगा दूंगी कर کردون",
)
W(
    "WORKY2",
    "project kaam order invoice stock file report deadline tak kal aaj task data hisab paperwork ye wo meeting",
)
W("SELFW", "apne apni apna khud khudko jaan jan zindagi myself mujhe apnay")
W("MYSELF", "myself mysef myself")
W("HARM_V", "hang kill killing hurt harm cut cutting unalive unaliving hanging")
W("LAUGH", "laughing laughter hasna")
W("DIE", "die dead suicide suicidal")
W("DIE_FOR", "laughing laugh")
W("KMS", "kms")
W("KMDIST", "away distance range drive km mileage per run ran ride")
W("NUMERIC", "0 1 2 3 4 5 6 7 8 9")
W("MARNA", "marna marne مرنا مرنے मरना मरने")
W("MAR", "mar مر मर")
W("DILL", "dil mann man jee")
W(
    "JAUN",
    "jaunga jaungi jaun jau jaoon jaaun jaoonga jana jaana jaye jaen jata jati jayen جاون جاونگا جانا जाऊंगा जाऊँगा जाऊं जाना",
)
W(
    "IDIOMD",
    "bhook bhookh hansi garmi gharmi sardi thak neend bore sharm pyas hunger sharam bill business dukan sales rate kaam order market tension mehngai",
)
W("RATE_V", "rate")
PH(
    "SH_PHRASE",
    "end it all/ending it all/end everything/ending everything/end my life/ending my life/end myself/take my own life/take my life/take own life/no reason to live/better off dead/wish i was dead/wish i were dead/rather be dead/want to be dead/dont want to live/do not want to live/cant go on/jee nahi lagta/jee nahi lagti/jee nahi lag raha/jine ka mann nahi/jeene ka mann nahi/zindagi khatam/اريد انهاء حياتي/انهي حياتي/انهاء حياتي/سانهي كل شيء/انهي كل شيء/لا اريد ان اعيش",
)
W("SH_AR", "سانتحر انتحر انتحار انتحاري اقتل-نفسي خودکشی खुदकुशी आत्महत्या")
PH("SH_PHRASE", "اقتل نفسي/اقتل نفسی/سأقتل نفسي/سااقتل نفسی/ساقتل نفسی")
W("SH_AR", "سانتحر")
PH(
    "TAKE_PILLS",
    "take all the pills/take all my pills/take all pills/took all the pills/took all pills/ill take all the pills/swallow all the pills/swallow all my pills",
)

# --- VIOLENCE_ABUSE --------------------------------------------------------------------------
W(
    "HIT",
    "maar maara mara marta maarta maarti marti maarte marte maarne maarenge maarun maara-hai peet peeta peeti peete peetna pita-ja beat beats beating beaten punch punched slap slapped kick kicked thappad thapad thappar strangle ضرب يضرب يضربني مارتا مارتی مارتے مارا مارتي پیٹ پیٹتا मारता मारती मारते मारा पीटता पीटते मारा مارا",
)
PH("HIT", "hit me/hits me/hit her/hit him/hit my/hits her/hits my")
W(
    "FAMILYACT",
    "shohar husband pati miyan biwi wife baap abbu father maalik malik boss sasur saas devar jeth bhai uncle chacha mamu teacher ustad master watchman woh wo usne unhon unhone zoj زوجي زوجی شوہر شوهر पति बाप",
)
W(
    "VICTIM",
    "mujhe mujhko mujhse mujh muje mjhe mere meri mera ghar roz hamesha daily مجهی مجھے मुझे मुझको",
)
W(
    "IDIOM_H",
    "business kaam dukan competition market client customer deadline delivery order late sales rate price bill inflation mehngai agar warna",
)
W("QAID", "qaid kaid qeid قید क़ैद कैद")
W(
    "THIEF",
    "chor chour choor daku dakoo dacoit dacoits dakait robber robbers robbery looter lutera lutere loot thief thieves burglar burglars intruder intruders gunmen gunman goondey goonday goonde badmash badmaash gunda goondon ڈاکو چور لٹیرے सارق चोर डाकू",
)
PH("ENTER", "aa gaye/aa gaya/aa gayi/ghus aaye/ghus gaye/ghus gaya/ghus aya")
W(
    "ENTER",
    "ghus ghusa ghusay ghusaye ghusaaye aaye aagaye aaya andar ghar dukan godown pahunch pohanch chadh ghere gher pakad hamla attack firing goli lut raha",
)
W(
    "THREAT_N",
    "dhamki dhamkee dhamkiyan threat threats threatened threatening dhamkaya dhamka dhamkane tahdeed تہدید دھمکی धमकी",
)
W("KILLW", "qatal katl qatl marne maar jaan kill death murder shoot goli")
W("BACHAO", "bachao bachaao bachaw bachalo بچاو بچاؤ बचाओ")
W("SOS_AR", "انقذوني انقذني النجده النجدة انجدوني استغاثه")
W("MADAD_N", "madad")
W(
    "WEAPON",
    "bandooq bandook bandoq pistol gun guns talwar chaaku chaku knife knives chhuri churi rifle kalashnikov revolver ak47 hathyar hathiyar weapon tamancha",
)
W("PAAS", "paas")
W("WENTER", "entered entering aaya aaye le leke dikha dikhaya tan tana point pointed")
PH("WENTER", "le kar/aa gaya/aa gaye")
W("THEM", "unke uske unki unhon unhone usne woh wo log koi")

# --- CHILD_SAFEGUARDING / KIDNAP_ROBBERY -------------------------------------------------------
W(
    "SEXUAL_V",
    "chheda chhera chheri chhedna chhed choota chhoota chhua molest molested molestation harass harassed harassment rape raped zyadti ziyadti zayadti zinah zina touched touching inappropriately abused abuse",
)
W(
    "FEMALE_V",
    "beti bachi bachay bacchi beta bete behn bahen bahu biwi mujhe meri apni bachay bacche bachon baby child",
)
W("ZABARDASTI", "zabardasti zabardasti")
W("SHAADI", "shaadi nikah rishta vida")
PH("WRONGPLACE", "ghalat jagah/galat jagah/ghalat jaga")
PH("GHALATK", "ghalat kaam/galat kaam")
W("SAATH", "saath sath")
W("PARENTS", "maa baap walid walida parents ammi abbu")
W("BECH", "bech bechna bechte bik")
W(
    "AGWA",
    "agwa agwah agva ighwa kidnap kidnapped kidnapping abduct abducted abduction اغوا اغواء अपहरण",
)
W("MEDIA", "movie film novel thriller cover marketing game drama story book poster series")
W("GUM", "gum ghaib lapata missing kho")
W("UTHA", "utha uthaya uthake uthalo utha-ke اٹھا")
W("LIYA", "liya li le leja le-gaye lelo")
W("LE", "le leja lejana laye le-gaya")
W("GAYA", "gaya gaye gayi gai gya")
W("OBJ", "phone wallet bag key chabi sim card file")
W(
    "NORMALPLACE",
    "school doctor park hospital market bazar dukan masjid mosque tuition ghumane shopping",
)
W("GODE", "gode godi god neend")

# --- advice gaps (lexicon side) ---------------------------------------------------------------
W("LAW", "lawyer vakeel vakil advocate court sue sued lawsuit muqadma mukadma muqaddama litigation")
W("ASKQ", "kya should shall can could kaun kaunsi konsi batao kahan kaise sakta sakti")
W("SELFQ", "mujhe main mai i my mera meri mere apne mere-ko")
W("CHAHIYE", "chahiye chahie should shall karna kare karun kardun")
W(
    "INVEST_N",
    "share shares stock stocks bitcoin crypto gold property plot zameen forex psx etf bond bonds paisa paise money savings rupay",
)
W(
    "INVEST_ACT",
    "kharid kharidun kharidoon kharidu buy bechun sell invest lagaun lagaon lagau lagana lagani",
)
W(
    "HEALTH",
    "tabiyat tabiat tabiyet sehat bimar bimari bukhar dard pain rash fever headache cough kharish khansi zukam infection",
)
W(
    "KHAUN",
    "khaun khaon kha lun loon dawai dawa medicine tablet goli kaunsi konsi take diagnose diagnosis serious",
)
W("DIAGNOSE", "diagnose diagnosis diagnosing")
W("SERIOUS", "serious khatarnak sangeen")
W("MY", "my mera meri mere")


# --- extra spellings and scripts (added after the audit) -----------------------------------
W("SAB", "سب सब")
W("WANT", "wants wanted")
W("MYSELF", "himself herself themselves hisself")
PH(
    "SH_PHRASE",
    "/".join(
        f"{v} {p} life"
        for v in ("end ending ends take taking took".split())
        for p in ("his her their own my your".split())
    )
    + "/kill himself/kill herself/killed himself/killed herself/जीने का मन नहीं/जीने का मन नही/جینے کا من نہیں/جینے کا دل نہیں/جینے کی خواہش نہیں",
)
W("INSIDE", "कमरे कमरा घर गाड़ी बाथरूम کمرے کمرہ گھر گاڑی باتھ روم")
W("WEAK_TRAP", "बंद बन्द बंधक بند")
W("DAB", "दब दबे دب")
W("PERSON", "मजदूर लोग मरीज مزدور لوگ")
W("DEBRIS", "मलबे मलबा ملبے ملبہ")
W("TOXIC", "petrol diesel फिनायल ब्लीच तेजाब فینائل مبيض तेज़ाब")
W("MEDS", "حبوب गोलियां गोलिया दवाइयां दवाइ")
W("CHEM_ANY", "liquid chemical chemicals cleaning detergent sanitizer")
_cross("INGEST_DONE", "کھا", "لین لیں")
W("LEAK", "bhar bhari")
W("ELEC_V", "लग लगा لگ لگا")
W("FLOW", "बह बहना")
W("BREAK", "टूट टूटा टूटी टूटे ٹوٹ ٹوٹی ٹوٹا")
W("SNAKE_N", "افعى")
W("BITE", "لدغته لدغ")
W("VICTIM", "me my")
W("ME", "mujhe mujhko mujh muje mjhe مجهی मुझे")
W(
    "ENTER",
    "entered entering broke breaking inside house home shop store door घुस घुसे घुसा आए گھس گھسے گھسا",
)
PH("ENTER", "आ गए/आ गया/آ گئے/آ گیا")
W("KILLW", "मारने जान क़त्ल कत्ल قتل مارنے جان")
W("HIT", "ضربني للضرب ضربه ضربها يضربها يضربه")
PH("HIT", "hitting me/hitting her/hitting him/hitting my")
W("FEMALE_V", "daughter son girl boy children बेटी बच्ची बेटा बहन बहू بیٹی بچی بیٹا بهن")
PH("WRONGPLACE", "ghalat harkat/galat harkat")
PH("GHALATK", "गलत काम/गलत हुआ/गलत हरकत/غلط کام")
W("SAATH", "साथ ساتھ")
W("SEXUAL_V", "छेड़ा छेड़ना छेड़ती चھیڑا چھیڑا چھیڑنا")
W("ANYONE", "ajnabi ajnabee stranger unknown")
W("DAL", "dal daal dala zabardasti")
W("GUM", "गुम ग़ायब")
W("GUM_AR", "مفقود مفقوده ضائع")
W("LE", "ले لے")
W("GAYA", "गया گیا گئی گئے")
W("CHILD", "طفلي طفلتي बेटे बेटी بیٹی بیٹے بیٹا")
W("AGWA", "خطف اختطاف خطفوا")
PH("TRAP_PH", "احد ما بالداخل/احد بالداخل/شخص بالداخل/اطفال بالداخل")


# --- advice: tax, legal, medicine, money in five languages ------------------------------------
W("ASKQ", "how much क्या कौन कैसे कितना کیا کون کیسے کتنا هل ماذا kaise kitna")
W("SELFQ", "मुझे मैं मेरा मेरे میں مجھے میرا ادفع اشتري ارفع اتناول اخذ")
W("TAX_N", "tax taxes टैक्स ٹیکس ضریبه ضريبه الضریبه الضريبه")
W(
    "TAXACT",
    "chahiye dena dun doon bharun bharna bachana lagega lagta hoga file pay return deduct claim चाहिए देना भरूं دینا دینی دون ادفع yes",
)
W("LAW", "वकील केस مقدمه وکیل دعوی دعوى قضیه محام محامی")
W("INVEST_N", "शेयर سهام اسهم الاسهم الأسهم")
W("INVEST_ACT", "खरीदूं खरीदूँ خریدون خریدوں اشتری اشتري")
W("MEDS", "paracetamol antibiotic antibiotics دواء الدواء")
W("CHAHIYE", "चाहिए چاہیے چاہئے يجب ينبغي")
PH("ASKQ", "ya nahi/या नहीं/یا نہیں")
W("TAKEV", "le lun loon khaun take lena leni sakta sakti ले लूं لوں لون")
W("HEALTH", "बुखार दर्द بخار درد حمى الحمى سعال")
W("KHAUN", "कौन दवा کون دوا دواء اتناول")


W("PASTM", "thi tha the pichle pichla pichli saal last ago earlier before pehle")
W(
    "TRADE",
    "runs run vehicles billing licence license renewal permit operate operates system systems bujhane bujhana bujha extinguishing fighting payment cheque quote",
)
W("IDIOMD", "quote quotes price bhej bata dein")

# --- rules -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    cls: str
    anchor: int
    needs: tuple[tuple[int, int], ...]
    win: int
    avoid: int
    trade: bool | str
    name: str


_RULES: list[Rule] = []


def R(
    cls: str,
    anchor: str,
    needs: Iterable[str | tuple[str, int]] = (),
    win: int = 5,
    avoid: str = "",
    trade: bool | str = False,
    name: str = "",
    kind: str | None = None,
) -> None:
    ns: list[tuple[int, int]] = []
    for n in needs:
        expr, w = (n, win) if isinstance(n, str) else n
        ns.append((_mask(expr), w))
    _RULES.append(
        Rule(
            cls if kind is None else f"{cls}:{kind}",
            _mask(anchor),
            tuple(ns),
            win,
            _mask(avoid) if avoid else 0,
            trade,
            name or anchor,
        )
    )


# SELF_HARM -- first, it outranks everything -------------------------------------------------
R("SELF_HARM", "SH_PHRASE", name="sh phrase")
R("SELF_HARM", "SH_AR", name="sh arabic/hindi")
R("SELF_HARM", "LIFE", ["TIRED"], win=5, avoid="INSURANCE", name="tired of life")
R("SELF_HARM", "LIFE", ["NEG", "WANT"], win=4, avoid="INSURANCE", name="life not wanted")
R("SELF_HARM", "LIFE", ["NEG", "WORTH"], win=4, name="life not worth")
R("SELF_HARM", "JEENA", ["NEG", "WANT|COPULA"], win=3, name="jeena nahi")
R("SELF_HARM", "KHATAM", ["SAB", "KARV"], win=3, avoid="WORKY2", name="sab khatam kar")
R("SELF_HARM", "KHATAM", ["SELFW", "KARV"], win=3, avoid="WORKY2", name="khud ko khatam")
R("SELF_HARM", "TOXIC", ["INGEST_FUT"], win=3, name="zehar kha lun")
R("SELF_HARM", "MEDS", ["INGEST_FUT", "SAB|QTY"], win=4, name="goliyan kha loon sab")
R("SELF_HARM", "KUCHKHA", avoid="FOODCTX", win=8, name="kuch kha loon bare")
R("SELF_HARM", "KUCHKHA", ["KHATAM|SAB"], win=6, name="kuch kha loon sab khatam")
R("SELF_HARM", "TAKE_PILLS", name="all the pills")
R("SELF_HARM", "HARM_V", ["MYSELF"], win=3, avoid="LAUGH", name="kill myself")
R("SELF_HARM", "DIE", ["WANT"], win=3, avoid="DIE_FOR", name="want to die")
R("SELF_HARM", "KMS", win=2, avoid="NUMERIC|KMDIST", name="kms")
R("SELF_HARM", "MARNA", ["DILL"], win=3, avoid="IDIOMD", name="marne ka dil")
R("SELF_HARM", "MARNA", ["WANT|COPULA"], win=3, avoid="NEG|IDIOMD", name="marna chahta/hai")
R("SELF_HARM", "MAR", ["JAUN"], win=2, avoid="IDIOMD", name="mar jaunga")

# FIRE_SMOKE ---------------------------------------------------------------------------------
R("FIRE_SMOKE", "FIRE_N", ["OCC"], win=5, trade=True, name="fire + happening")
R("FIRE_SMOKE", "FIRE_N", ["DANGER"], win=6, name="fire + help")
R("FIRE_SMOKE", "FIRE_N", ["PLACE_OBJ"], win=5, trade="msg", name="fire + place")
R("FIRE_SMOKE", "FIRE_N", ["COPULA"], win=2, trade=True, name="fire hai")
R("FIRE_SMOKE", "FIRE_N", ["FIRE_N"], win=3, name="fire twice")
R("FIRE_SMOKE", "BURN_V", ["PROG"], win=2, avoid="LIGHT_ON", trade=True, name="jal raha hai")
R(
    "FIRE_SMOKE",
    "BURN_V",
    ["PAST_GO", "PLACE_BIG"],
    win=4,
    avoid="MONEYY|LIGHT_ON",
    trade=True,
    name="place jal gaya",
)
R(
    "FIRE_SMOKE",
    "BURN_V",
    ["PAST_GO", "SAB"],
    win=3,
    avoid="MONEYY|LIGHT_ON|FOODY",
    name="jal gaya sab",
)
R("FIRE_SMOKE", "BLAST_N", ["HOGAYA", "PLACE_BIG"], win=4, avoid="SALE_MKT", name="blast ho gaya")

# TRAPPED ------------------------------------------------------------------------------------
R("TRAPPED", "STRONG_TRAP", ["PERSON|CHILD"], win=5, avoid="TRAFFIC", name="people stuck")
R("TRAPPED", "STRONG_TRAP", ["INSIDE"], win=5, avoid="TRAFFIC", trade="msg", name="stuck inside")
R("TRAPPED", "DAB", ["PERSON|CHILD", "INSIDE|DEBRIS"], win=4, name="people buried")
R("TRAPPED", "DOOR", ["NEG", "OPEN_V"], win=4, name="door will not open")
R("TRAPPED", "ANYONE", ["INSIDE_STRICT", "COPULA|STRONG_TRAP"], win=4, name="koi andar hai")
R("TRAPPED", "WEAK_TRAP", ["CHILD", "INSIDE"], win=5, avoid="SCHOOLY", name="child shut inside")
R("TRAPPED", "TRAP_PH", name="arabic someone inside")

# POISONING ----------------------------------------------------------------------------------
R("POISONING", "TOXIC", ["INGEST_DONE|INGEST_P"], win=4, trade=True, name="poison swallowed")
R("POISONING", "MEDS", ["INGEST_DONE|INGEST_P", "CHILD|QTY"], win=6, name="medicine swallowed")
R(
    "POISONING",
    "CHILD",
    ["INGEST_DONE|INGEST_P", "TOXIC|MEDS|FOREIGN|CHEM_ANY"],
    win=6,
    name="child swallowed",
)

# MEDICAL_RESCUE -----------------------------------------------------------------------------
R("MEDICAL_RESCUE", "GAS_N", ["LEAK"], win=5, trade=True, name="gas leak")
R("MEDICAL_RESCUE", "ELEC_N", ["ELEC_V"], win=4, avoid="BILL", name="electric shock")
R("MEDICAL_RESCUE", "CHIPAK", ["ELEC_N|WIRE"], win=5, name="stuck to wire")
R("MEDICAL_RESCUE", "DOOB", ["PERSON|CHILD|WATER"], win=4, avoid="WORKY|MONEYY", name="drowning")
R("MEDICAL_RESCUE", "GOLI_V", ["GOLI_N"], win=2, avoid="TABLET_CTX", name="goli lag gayi")
R("MEDICAL_RESCUE", "SNAKE_N", ["BITE"], win=5, trade=True, name="bitten")
R("MEDICAL_RESCUE", "BODY_S", ["BREAK"], win=3, avoid="BIZ", name="broken limb")
R("MEDICAL_RESCUE", "SAR", ["PHAT", "KHOON"], win=4, name="head split blood")
R("MEDICAL_RESCUE", "KHOON", ["FLOW"], win=4, avoid="FILMY", name="bleeding")
R("MEDICAL_RESCUE", "SANS", ["NEGB"], win=3, name="cannot breathe (roman)")
R("MEDICAL_RESCUE", "BREATHE", ["NEGE"], win=3, name="cannot breathe")
R("MEDICAL_RESCUE", "DAURA", ["PADH"], win=2, name="daura pad gaya")
R("MEDICAL_RESCUE", "FIT_N", ["PADH"], win=2, name="fit pad raha")
R("MEDICAL_RESCUE", "SEIZE_N", avoid="CUSTOMS", name="seizure")
R("MEDICAL_RESCUE", "FALL_P", ["GIR"], win=3, avoid="BIZ", name="person fell")
R("MEDICAL_RESCUE", "BP", ["BP_LEVEL", "BP_SYMPT"], win=6, name="bp high")
R("MEDICAL_RESCUE", "CHAKKAR", ["AARAHE"], win=2, name="chakkar aa rahe")
R("MEDICAL_RESCUE", "DIZZY", name="dizzy")
R("MEDICAL_RESCUE", "ULTI", ["CHILD"], win=5, avoid="TRADE", name="child vomiting")
R("MEDICAL_RESCUE", "NUM_EMERG", ["CALLV"], win=3, name="emergency number")
R("MEDICAL_RESCUE", "NUM_999", ["CALLV"], win=3, avoid="MONEYW", name="999 call")
R("MEDICAL_RESCUE", "BEHOSH", name="behosh")
R("MEDICAL_RESCUE", "HOSH", ["NEGB"], win=2, name="hosh nahi")
R("MEDICAL_RESCUE", "ACC", ["ACC_HOG"], win=3, trade=True, name="accident ho gaya")
R("MEDICAL_RESCUE", "HEART_ATK", trade=True, name="heart attack script")
R("MEDICAL_RESCUE", "AMBU", ["AMBU_NEED"], win=4, trade="msg", name="ambulance needed")

# VIOLENCE_ABUSE -----------------------------------------------------------------------------
R("VIOLENCE_ABUSE", "HIT", ["FAMILYACT"], win=4, avoid="IDIOM_H", name="family hits")
R("VIOLENCE_ABUSE", "HIT", ["VICTIM"], win=3, avoid="IDIOM_H", name="hits me")
R("VIOLENCE_ABUSE", "WEAK_TRAP", ["ME", "RAKHA"], win=5, avoid="SCHOOLY", name="shut me up")
R("VIOLENCE_ABUSE", "QAID", ["VICTIM|CHILD"], win=5, name="held captive")
R(
    "VIOLENCE_ABUSE",
    "WEAK_TRAP",
    ["PERSON|CHILD", "RAKHA"],
    win=4,
    avoid="SCHOOLY",
    name="kept shut up",
)
R("VIOLENCE_ABUSE", "THIEF", ["ENTER"], win=5, avoid="SALE_MKT", trade=True, name="robbers")
R("VIOLENCE_ABUSE", "WEAPON", ["PAAS", "THEM"], win=4, trade=True, name="they have a weapon")
R("VIOLENCE_ABUSE", "WEAPON", ["WENTER"], win=4, trade=True, name="weapon at the door")
R("VIOLENCE_ABUSE", "THREAT_N", ["KILLW"], win=4, name="death threat")
R("VIOLENCE_ABUSE", "POLICE_N", ["SUMMON"], win=3, name="call police")
R("VIOLENCE_ABUSE", "BACHAO", ["BACHAO"], win=3, name="bachao bachao")
R("VIOLENCE_ABUSE", "SOS_AR", name="arabic sos")

# CHILD_SAFEGUARDING -------------------------------------------------------------------------
R("CHILD_SAFEGUARDING", "HIT", ["CHILD"], win=4, avoid="IDIOM_H", name="child hit")
R("CHILD_SAFEGUARDING", "SEXUAL_V", ["FEMALE_V"], win=5, name="sexual abuse")
R("CHILD_SAFEGUARDING", "WRONGPLACE", ["FEMALE_V"], win=5, name="touched wrongly")
R("CHILD_SAFEGUARDING", "GHALATK", ["CHILD", "SAATH", "HOGAYA"], win=4, name="ghalat kaam hua")
R("CHILD_SAFEGUARDING", "ZABARDASTI", ["SHAADI", "FEMALE_V"], win=5, name="forced marriage")
R("CHILD_SAFEGUARDING", "BECH", ["CHILD", "PARENTS"], win=4, avoid="TRADE", name="child sold")

# KIDNAP_ROBBERY -----------------------------------------------------------------------------
R(
    "KIDNAP_ROBBERY",
    "AGWA",
    ["CHILD"],
    win=5,
    avoid="MEDIA",
    kind="SAFEGUARDING",
    name="child kidnapped",
)
R("KIDNAP_ROBBERY", "AGWA", ["HOGAYA|LIYA"], win=4, avoid="MEDIA", name="kidnapped")
R(
    "KIDNAP_ROBBERY",
    "GUM",
    ["CHILD", "HOGAYA"],
    win=3,
    avoid="OBJ",
    kind="SAFEGUARDING",
    name="child missing",
)
R(
    "KIDNAP_ROBBERY",
    "LE",
    ["CHILD", "ANYONE", "GAYA"],
    win=4,
    avoid="NORMALPLACE",
    kind="SAFEGUARDING",
    name="child taken",
)
R(
    "KIDNAP_ROBBERY",
    "LE",
    ["CHILD", "DAL", "GAYA"],
    win=7,
    avoid="NORMALPLACE",
    kind="SAFEGUARDING",
    name="child bundled away",
)
R("KIDNAP_ROBBERY", "GUM_AR", ["CHILD"], win=3, kind="SAFEGUARDING", name="child missing arabic")
R(
    "KIDNAP_ROBBERY",
    "UTHA",
    ["CHILD", "LIYA|LE"],
    win=3,
    avoid="GODE|NORMALPLACE",
    kind="SAFEGUARDING",
    name="child picked up",
)

# `GOLI_N` needs a tag of its own (the word is also a tablet).
W("GOLI_N", "goli golee گولی گولی")

_ENUMERATED = tuple(_RULES)
_ADVICE_RULES: list[tuple[str, int, tuple[tuple[int, int], ...], int, int]] = []


def _advice(kind: str, anchor: str, needs: Iterable[str], win: int = 6, avoid: str = "") -> None:
    _ADVICE_RULES.append(
        (
            kind,
            _mask(anchor),
            tuple((_mask(n), win) for n in needs),
            win,
            _mask(avoid) if avoid else 0,
        )
    )


_advice("legal", "LAW", ["ASKQ", "SELFQ", "CHAHIYE"])
_advice("financial", "INVEST_N", ["ASKQ", "SELFQ", "INVEST_ACT"])
_advice("medical", "HEALTH", ["ASKQ", "KHAUN"], avoid="TRADE")
_advice("tax", "TAX_N", ["ASKQ", "TAXACT|SELFQ"], avoid="TRADE")
_advice("medical", "MEDS", ["ASKQ", "TAKEV|SELFQ"], avoid="TRADE")
_advice("medical", "DIAGNOSE", ["MY", "HEALTH"], win=5)
_advice("medical", "HEALTH", ["SERIOUS", "ASKQ"], avoid="TRADE")

_DANGER = _mask("DANGER")
_TRADE = _mask("TRADE")
_PASTM = _mask("PASTM")


# --- matching --------------------------------------------------------------------------------


@dataclass
class _Doc:
    masks: list[int]
    clause: list[int]
    clause_or: dict[int, int]
    gor: int
    positions: dict[int, list[int]]
    near_cache: dict[int, list[int]]


_FIRE_PROTECT = re.compile(r"(?:aag|ag|fire|dhuan|smoke)\s+se\s+bach\w*")
_TRADEISH = re.compile(
    r"quote|rate|price|extinguisher|system|alarm|sprinkler|insurance|bechn|chahiye"
)


def _analyse(text: str) -> _Doc | None:
    said = _PRECLEAN.sub(" ", normalise(text))
    if _FIRE_PROTECT.search(said) and _TRADEISH.search(said):
        said = _FIRE_PROTECT.sub(
            " fireprotection ", said
        )  # protect-from-fire in a trade sentence, not a cry for help
    tokens: list[str] = []
    clause: list[int] = []
    cid = 0
    for part in _CLAUSE_SPLIT.split(said):
        for tok in _TOKEN_SPLIT.split(part):
            if not tok:
                continue
            if tok in ("aur", "lekin", "and", "but", "phir", "magar", "par"):
                cid += 1
                continue
            tokens.append(tok)
            clause.append(cid)
        cid += 1
    if not tokens:
        return None
    if len(tokens) > _MAX_TOKENS:
        keep = _MAX_TOKENS - _HEAD_TOKENS
        tokens = tokens[:_HEAD_TOKENS] + tokens[-keep:]
        clause = clause[:_HEAD_TOKENS] + clause[-keep:]
    n = len(tokens)
    masks = [0] * n
    for i, tok in enumerate(tokens):
        m = _LEX.get(tok, 0)
        if len(tok) >= 3:
            c = _collapse(tok)
            if c != tok:
                m |= _LEX_COLLAPSED.get(c, 0)
        if tok.isdigit() and len(tok) <= 18:
            m |= _LEX.get(tok, 0) | _BIT["NUMERIC"]
        cands = _PHRASES.get(tok)
        if cands:
            for rest, b in cands:
                if tuple(tokens[i + 1 : i + 1 + len(rest)]) == rest:
                    m |= b
        masks[i] = m
    clause_or: dict[int, int] = {}
    gor = 0
    positions: dict[int, list[int]] = {}
    for i, m in enumerate(masks):
        if m:
            gor |= m
            clause_or[clause[i]] = clause_or.get(clause[i], 0) | m
            mm = m
            while mm:
                low = mm & -mm
                positions.setdefault(low, []).append(i)
                mm ^= low
    return _Doc(masks, clause, clause_or, gor, positions, {})


def _near(doc: _Doc, w: int) -> list[int]:
    got = doc.near_cache.get(w)
    if got is not None:
        return got
    masks = doc.masks
    n = len(masks)
    out = [0] * n
    for i in range(n):
        lo = max(0, i - w)
        hi = min(n, i + w + 1)
        acc = 0
        for j in range(lo, hi):
            if j != i:
                acc |= masks[j]
        out[i] = acc
    doc.near_cache[w] = out
    return out


def _anchor_positions(doc: _Doc, anchor: int) -> list[int]:
    out: list[int] = []
    a = anchor
    while a:
        low = a & -a
        out.extend(doc.positions.get(low, ()))
        a ^= low
    return out


def _first_hit(
    doc: _Doc,
    anchor: int,
    needs: tuple[tuple[int, int], ...],
    win: int,
    avoid: int,
    trade: bool | str,
) -> bool:
    if not anchor & doc.gor:
        return False
    for need, _w in needs:
        if not need & doc.gor:
            return False
    danger_anywhere = bool(doc.gor & _DANGER)
    for i in _anchor_positions(doc, anchor):
        ok = True
        for need, w in needs:
            if not _near(doc, w)[i] & need:
                ok = False
                break
        if not ok:
            continue
        if avoid and not danger_anywhere and _near(doc, 10)[i] & avoid:
            continue
        if trade and not danger_anywhere:
            cor = doc.clause_or.get(doc.clause[i], 0)
            if trade == "msg":
                if doc.gor & _TRADE:
                    continue
            elif cor & _TRADE or (cor & _PASTM and doc.gor & _TRADE):
                continue  # same clause, or a past-tense fire clause with a trade word elsewhere
        return True
    return False


def classify(text: str) -> str | None:
    """The class that fired, or None. A class of the form `X:KIND` carries its own answer kind."""
    doc = _analyse(text)
    if doc is None:
        return None
    for rule in _RULES:
        base = rule.cls.split(":", 1)[0]
        if base in DISABLED:
            continue
        if _first_hit(doc, rule.anchor, rule.needs, rule.win, rule.avoid, rule.trade):
            return rule.cls
    return None


def detect(text: str) -> str | None:
    """The name of the safety.Emergency member to answer with, or None."""
    cls = classify(text)
    if cls is None:
        return None
    if ":" in cls:
        return cls.split(":", 1)[1]
    return CLASS_KIND[cls]


def advice_kind(text: str) -> str | None:
    """A personal legal, financial or medical ask the older patterns missed (name of safety.Advice), or None."""
    doc = _analyse(text)
    if doc is None:
        return None
    for kind, anchor, needs, win, avoid in _ADVICE_RULES:
        if _first_hit(doc, anchor, needs, win, avoid, False):
            return kind
    return None
