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
        if len(toks) == 1:
            _LEX[toks[0]] = _LEX.get(toks[0], 0) | b
            _LEX_COLLAPSED[_collapse(toks[0])] = _LEX_COLLAPSED.get(_collapse(toks[0]), 0) | b
            continue
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
    "help madad bachao bachaao bachaw bachaye bachalo bachalein emergency urgent urgently jaldi jldi fauran foran turant abhi sos rescue immediately asap انقذوني النجده بچاو بچاؤ बचाओ मदद जल्दी خطر zakhmi injured dying maut",
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


W("PASTM", "thi tha pichle pichla pichli saal last ago earlier before pehle")
W(
    "TRADE",
    "runs run vehicles billing licence license renewal permit operate operates system systems bujhane bujhana bujha extinguishing fighting payment cheque quote",
)
W("IDIOMD", "quote quotes price bhej bata dein")


# --- second recall wave (burning things, falls, choking, swallowing, threats, doubt, advice) ---
W("BURN_V", "burning burn burns burnt يحترق تحترق احترق يشتعل تشتعل اشتعل يحرق")
W(
    "PLACE_OBJ",
    "roof stockroom بیت بيت منزل مطبخ غرفه محل متجر مصنع مخزن مستودع شقه سياره مبنی مبنى छत",
)
W("STRONG_TRAP", "محاصرون محاصرین محاصر عالقون عالقین")
W("PERSON", "نحن ناس احنا")
W("TRADE", "نبيع نبیع طفايات طفایات طفايه اجهزه انذار")
W(
    "HEIGHT",
    "height roof scaffolding ladder balcony chhat unchai unchaai seerhi seerhiyon upar اونچائی ऊंचाई छत مرتفع سقف سلم",
)
W("FELL", "fell fall fallen falls gir gira gire giri سقط گر गिर गिरा गिरी")
W("CHOKE_V", "choking choked choke chokes يختنق اختناق दमघुट")
W("SWALLOW", "swallowed swallow swallowing nigal nigla nigli ابتلع بلع نگل")
W("FOREIGN", "بطاریه بطارية batteries")
W("TECH", "cursor mouse page screen website app scroll order shipment stock sales cart")
PH(
    "NOMOVE",
    "not moving/isnt moving/is not moving/does not move/doesnt move/not responding/unresponsive/no pulse/wont wake up/not waking up/hilta nahi/hil nahi raha/hil nahi rahi/nahi hil raha/ہلتا نہیں/ہل نہیں رہا/हिल नहीं रहा/नहीं हिल रहा/हिलता नहीं/لا يتحرك/لا تتحرك/لا يستجيب/لا نبض",
)
W("STROKE_N", "stroke falij falaj faalij فالج लकवा paralysis paralyzed")
W(
    "STROKE_V",
    "ho hua attack have having had think thinks looks lagta aaya aaye gaya hone may signs",
)
W("AMBU_NEED", "بھیجیں بھیجو भेजें भेजो ارسلوا ارسل bhejen bhejain bhejiye")
W("THREAT_P", "kill murder shoot stab strangle قتل")
PH(
    "THREAT_P",
    "kill me/kill you/kill us/murder me/shoot me/stab me/beat me up/hurt me/kill my/will kill/maar dunga/maar dalunga/maar dalenge/maar dungi/jaan se maar",
)
W("YOU2", "tujhe tumhe tumhein tujhko usay usko")
W("HIT", "مار मार")
W("HITME", "يضربني ضربني يضربنی ضربنی")
W("THREAT_AR", "يهددني يهدد هددني تهديد بالقتل القتل يهدد")
W("LE_DE", "le de لے دے")
W("FUTV", "loonga lunga loon doonga dunga dungi lungi lun dun looga")
W("UNSURE", "sure unsure maybe might perhaps shayad lagta ")
PH(
    "UNSURE",
    "not sure/dont know/do not know/i think/may have/pata nahi/ya nahi/ya nhi/mujhe lagta/not certain/could be",
)
W("QTY", "many too much extra")
W("DOOB_E", "drown drowned drowning")
W("HEALTH", "صداع الصداع")
W("KHAUN", "اخذ")
W("LAW", "کیس")
W("CHAHIYE", "کروں کرون کردوں करूं करूँ करूं")
W("TAXACT", "parega padega parhega paray padhega bharna bharun")


# --- third wave: child safeguarding, kidnap, robbery -------------------------------------------
W(
    "SEXUAL_V",
    "chhedta chhedti chhedte chhedtay chhuta chhuti chhute chhoo छूता छूती छूते छेड़ता छेड़ती چھیڑتا چھیڑتی چھوتا چھوتی تحرش اعتداء",
)
W("HIT", "पीटा पीटती पीटते पीटना पीटा")
W("AGWA", "अगवा")
W("GUM", "گم")
W("CHILD", "ابني ابنتي بنتي ابنی")
W("FEMALE_V", "bhanji bhatiji niece ladki girl")
W("KISI", "kisi کسی किसी")
W("TAKEN", "took taken takes grabbed snatched")
W("CARAWAY", "car van vehicle gaari away truck")


# --- fourth wave: live fire cues, hedged fire, abuse, confinement, ransom, gunpoint, robbery ---
W("LIVE", "ringing rang baj beeping siren flames dikh dikhai dikhi smell smelling")
PH(
    "LIVE",
    "can see/full of/right now/dikh raha/dikh rahi/bhar gaya/bhar gayi/aa rahi hai/aa raha hai/الآن/بالداخل",
)
W("BURN_AR", "يحترق تحترق احترق احترقت يشتعل تشتعل اشتعل اشتعلت")
W("PLACE_OBJ", "شاحنه شاحنة حافله حافلة باص bus highway sadak")
W(
    "RELATIVE",
    "bhai bhaiya brother sister behn bahen shohar husband biwi wife abbu ammi papa mama dost friend cashier son daughter اخي اختي ابني بنتي",
)
W(
    "CHILD",
    "son daughter niece nephew bhanji bhatija bhatiji bhanja ladki girl little طفله طفلة الصغير الصغيره صغير صغيره ابنه بنت ولد اخي اختی लड़की लडकी بیٹی لڑکی",
)
for _n in range(1, 18):
    PH(
        "CHILD",
        f"{_n} year old/{_n} years old/{_n} saal ki/{_n} saal ka/{_n} saal ke/{_n} sal ki/{_n} sal ka",
    )
W(
    "ADULT",
    "teacher tutor driver uncle chacha mamu tayya ustad master neighbour padosi cousin relative stepfather stepmother maalik boss watchman guard doctor ڈرائیور استاد चाचा ड्राइवर عمها خاله",
)
W("BEATV", "beat beats beating beaten hits hit")
W(
    "SEXUAL_V",
    "touches touched touching sexually assault assaulted balatkar बलात्कार بلاتکار اغتصاب جنسي جنسی badtameezi badtamizi بدتمیزی dirty obscene gandi gandy گندی",
)
PH(
    "SEXUAL_V",
    "bad way/wrong way/ghalat tareeke se/ghalat tareeqe se/غلط طریقے سے/गलत तरीके से/dirty pictures/dirty photos/gandi tasveer/gandi tasveerein/obscene pictures/forced my/forced her/sexual assault/الاعتداء الجنسي",
)
PH(
    "TANGK",
    "tang karta/tang karti/tang kar raha/tang kar rahi/تنگ کرتا/تنگ کرتی/तंग करता/तंग करती/harass karta/harass karti",
)
PH("HABS", "حبس الطفل/حبسوا/حبست")
W("HABS", "حبس")
W("LOCKED", "locked lock band bandh bandhe habs حبس بند")
W("FOODLESS", "bhookha bhooka bhukha بھوکا भूखा جوع")
PH("FOODLESS", "without food/khana nahi/khana nahin/no food/کھانا نہیں/खाना नहीं/بدون طعام")
W("RANSOM", "ransom fidya fidyah firauti फिरौती فدیہ فدية bhatta بھتہ extortion")
W("HOSTAGE", "hostage hostages yarghamal yerghamal yarghamaal یرغمال यरगमाल बंधक رهينه رهينة رهائن")
PH(
    "GUNPOINT",
    "gunpoint/knifepoint/bandooq ki nok/bandook ki nok/بندوق کی نوک/बंदूक की नोक/pistol dikha/pistol dikhakar/pistol dikha kar/पिस्तौल दिखाकर/holding a gun/pointed a gun/pointing a gun/gun to my head/hathyar dikha/تحت تهديد السلاح/هددوني بالسلاح/تحت تهديد",
)
W("ROB_STRONG", "mugged mugging robbing robbed snatched snatching looting looted lutera")
W("ROB_WEAK", "loot lut lutna cheen cheena cheen-liya chheen छीन लूट لوٹ لٹ سرقوا يسرقون نهب")
W("BAGMOB", "bag mobile phone purse wallet cash chain handbag dukan shop ghar house")
W("MONEYASK", "want demand demanding maang maange mang مانگ مانگا طلبوا طلب मांग")
W("MONEYN", "money paise paisa rupay پیسے پیسه पैसे ransom")
W("THIEF", "daaka daka dakaiti dacoity")
W("ENTER", "pad")
W("LIYA", "लिया ली")


# === event grammar (wave 4): broad per-class event lexicons with inflections ======================
_SUF = ("", "a", "i", "e", "aa", "ta", "ti", "te", "na", "ne", "ni", "ya", "yi", "ye")


def INFL(tag: str, stems: str, suffixes: tuple[str, ...] = _SUF) -> None:
    """Register every stem with each suffix (Roman Urdu verb inflections)."""
    W(tag, " ".join(st + sf for st in stems.split() for sf in suffixes))


# who: pronouns, groups, weapons and cues shared by several classes
W(
    "PRON",
    "he she they him her them us me my our woh wo usne unhon unhone unko usay usko unhein humein hamein hum ہمیں مجھے उन्हें हमें उसने वो وہ انہوں هم هو هي هما",
)
W(
    "GROUP",
    "crowd mob gang men man aadmi log logon bheed hajoom group armed masked mussalah naqabposh naqab bandits gunmen robbers daku daakuon dakuon dacoits ہجوم भीड़ الغوغاء حشد رجال مسلحین مسلحون مسلح لوگ लोग आदमी हथियारबंद नकाबपोश نقاب",
)
W(
    "ARMED",
    "armed mussalah masked naqabposh gunmen bandits daku daakuon dakuon dacoits robbers مسلح مسلحین مسلحون نقاب हथियारबंद नकाबपोश بندوق بندوقوں बंदूकधारी बंदूक",
)
W(
    "HIGHPLACE",
    "roof rooftop bridge building terrace balcony chhat pul imarat sath mazil سطح جسر छत पुल مبنى عمارة بالکونی",
)
W("HEIGHT", "manhole well kuan kuein pit gutter ditch")
W(
    "BODY_ALL",
    "hand arm leg foot head wrist finger fingers chest neck face eye stomach hath haath bazu baazu pair paon ungli ungliyan sar kalai gardan chehra aankh pet seena seene kamar ہاتھ بازو ٹانگ پاؤں سر سینه سینے گردن चेहरा हाथ पैर सिर सीना छाती यد رجل راس صدر عنق وجه بطن معصم",
)
W(
    "INJ",
    "injured injury wound wounded crushed crush crushing mangled bleeding chot chhot zakhmi zakhm jakhmi kuchal kuchla kuchli kuchal-gaya ghayal ghaayal زخمی زخم چوٹ घायल चोट जख्मी جريح جرح اصابة اصيب سحق",
)
W("MACHINE", "machine press cutter grinder saw mashin mashinery machinery مشین ماکینة ماكينة मशीन")
W("CAUGHTIN", "aa phans phansa phans-gaya caught crushed stuck dab kat kuchal علقت علق دهس")
PH("CAUGHTIN", "aa gaya/aa gayi/aa gaye/اگیا/آ گیا/आ गया/आ गई")
W("CHEST", "chest seena seene sina chhati chhaati سینے سینه छाती सीने صدر")
W(
    "CHEST_V",
    "clutched clutch clutching pakad pakda pakadte dard pain tightness pressure heavy bhaari bhari جكڑ درد ألم ضيق دبانا",
)
PH(
    "DOWN",
    "dropped to the floor/fell to the floor/lying on the floor/lying on the road/lying unconscious/collapsed on/gir pade/gir pada/gir padi/gir paray/pada hai/padi hai/pade hain/پڑے ہیں/پڑا ہے/پڑی ہے/पड़ा है/पड़ी है/पड़े हैं/على الارض/ملقى على/ملقاة على",
)
W("DOWN", "collapsed collapse")
PH(
    "SPEECHLOSS",
    "cannot speak/can not speak/cant speak/unable to speak/slurred speech/face drooping/face is drooping/drooping on one side/bol nahi pa/bol nahi sakta/bol nahi sakti/bol nahi raha/bol nahi rahi/munh tedha/zubaan ladkhada/zuban ladkhada/بول نہیں/منہ ٹیڑھا/زبان لڑکھڑا/बोल नहीं/मुंह टेढ़ा/لا يتكلم/لا يستطيع الكلام/لا تستطيع الكلام",
)
W(
    "CONVULSE",
    "convulsion convulsions convulsing seizures seizing jhatke jhatka jhatkay تشنج تشنجات جھٹکے جھٹکا झटके झटका",
)
PH(
    "VEHICLE_HIT",
    "hit by a car/hit by a truck/hit by a bus/hit by a bike/hit by a vehicle/hit by a motorcycle/run over/ran over/knocked down by/takkar maar/takkar mari/takkar maari/takkar lag/kuchal diya/ٹکر مار/ٹکر ہو/टक्कर मार/टक्कर लग/صدمت سيارة/دهسته سيارة/دهستها سيارة",
)
PH(
    "INLABOUR",
    "in labour/in labor/labour pain/labor pain/dard-e-zah/dard e zah/dard zeh/dard-e-zeh/زچگی/ڈلیوری کا وقت/प्रसव पीड़ा/प्रसव/مخاض",
)
W("TOUCHV", "touched touch chhoo choo chhu chhua chhoo-liya chhu liya choti छू छुआ چھوا چھو")
PH(
    "LIVEWIRE",
    "live wire/naked wire/open wire/khula taar/nanga taar/ننگا تار/کھلا تار/नंगा तार/खुला तार",
)
W("KHOON2", "ब्लीडिंग bleeding blood-loss")
W(
    "KEEDE",
    "pesticide insecticide insecticides antifreeze surf detergent dettol antiseptic disinfectant naphthalene harpic thinner kerosene mitti-tel acid tezab tezaab rat-poison موتی مبيد مبيض ديتول कीटनाशक डिटॉल फिनायल تیزاب तेजाब كحول",
)
PH(
    "TOXIC",
    "keede maar dawai/keede mar dawai/keeray maar dawai/kida mar dawai/rat poison/chuhe maar dawai/chuhay maar dawai/cleaning liquid/washing powder/cleaning fluid/floor cleaner/toilet cleaner/nail polish remover/کیڑے مار دوا/कीड़े मारने की दवा/مبيد حشري/مبيد حشرات",
)
W(
    "INGEST_ANY",
    "kha khaa khaya khai khali pi pee piya pia pili pila pee-li pi-li nigal nigla nigli drank drink ate eat eaten swallow swallowed swallowing inhaled inhale chata chakha chakhi چکھا پی پیا کھا کھایا पी पिया खा खाया شرب ابتلع بلع استنشق",
)
PH(
    "INGEST_ANY",
    "muh mein daal/muh me daal/munh mein daal/منہ میں ڈال/मुंह में डाल/in his mouth/in her mouth/put in his mouth/put in her mouth",
)
W(
    "FUMES",
    "fumes fume fumes gas dhuan dhuaan dhua smoke carbon monoxide co thinner paint-thinner vapour vapor دھواں دخان धुआं गैस غاز بخار",
)
W(
    "HEATER",
    "geyser angheethi angethi anghiti angiti heater stove coal koyla charcoal brazier stove-gas gas-heater مدفأة انگیٹھی अंगीठी गीजर گیزر",
)
W("CLOSEDROOM", "closed locked sealed band bandh bund sealed-room ventilation بند مغلق बंद")
W(
    "CLOSEDPLACE",
    "room kamre kamra kamray bathroom washroom garage car kitchen godown کمرے کمرہ غرفة कमरे कमरा गैरेज",
)
W(
    "FAINTED",
    "behosh behoshi unconscious fainted faint dizzy chakkar chakkar-kha fainting sunn sans-nahi بے ہوش فاقد الوعي बेहोश चक्कर",
)
W("VOMIT", "ulti ulti-kar vomit vomiting vomited vomits qay ulti-ho قے الٹی उल्टी उलटी تقيأ")
W(
    "FAMILYALL",
    "family ghar-walay ghar ghar-ke sab pura poora sabhi everyone whole all family-members سب سارا پورا परिवार सब पूरा الاسرة الجميع",
)
# violence
PH(
    "HITV",
    "hit me/hit him/hit her/hit them/hit us/hit my/hits me/hits her/hits him/hitting me/is attacking/are attacking/attacking our/attacking the/attacked our/attacked the/attacked me/attacked her/attacked him/kick him/kicking him/kicked him",
)
W(
    "VIOL_STRONG",
    "stab stabs stabbed stabbing strangle strangled strangling throttle throttled throttling lathicharge pathrao پتھراؤ पथराव يطعن طعن يخنق خنق",
)
W(
    "VIOL_OBJ",
    "lathi lathiyan lathiyon laathi laathiyan laathiyon danda dande danday dandon patthar pathar stones stoning laat laatein laatan kicked kicking لاٹھی لاٹھیاں ڈنڈے ڈنڈا پتھر لات लाठी लाठियां डंडे डंडा पत्थर लात هراوات الهراوات بالهراوات عصي بالعصي الحجارة حجارة سكاكين",
)
PH(
    "VIOL_STRONG",
    "gala daba/gala dabaa/gala dabate/gale ko daba/gala ghont/gala ghot/gala dabaya/گلا دبا/गला दब/by the hair/baalon se pakad/baal pakad/balon se/dragged her/dragged him/dragged me/dragged by/ghaseet/firing ho rahi/firing ho raha/firing hui/goli chal/goliyan chal/gunshots/shots fired/fired at/firing at/someone is firing/someone is shooting/shooting near/phenkne ki dhamki/throw acid/throwing acid/threw acid/tezaab phenk/tezab phenk/acid phenk/تیزاب پھینک/तेजाब फेंक/اطلاق نار/إطلاق نار/pistol taan/pistol tan/bandooq taan/pointing a pistol/pointing a gun/pointed a pistol/pointing a knife/pointed a knife/held a blade/held a knife/held a gun/put a knife/put a blade/knife to my/knife to her/knife to his/knife to the/blade to the/blade to my/blade to her/blade to his/chaaku dikha/churi dikha/garam istri se/hot iron",
)
INFL("JALATA", "jala jalaa", ("ta", "te", "ti", "ya", "yi", "ye"))
W("JALATA", "burns burned-me burnt-me جلاتا جلاتی जलाता जलाती जलाते جلا जला")
PH(
    "JALATA",
    "jala diya/jala dete/jala rahe/jala raha/jala rahi/burns me/burn me/burning me/burnt me/cigarette se jala/cigarette se jalate/cigarettes/sigret se jala/جلا دیا/जला दिया",
)
W("LOCKUP", "locked lock band bandh bandhe bandha qaid kaid قید बंद بند حبس حبسني")
W(
    "HITV",
    "maar maara maari maare marta maarta maarti maarte maarne peet peeta peeti peete peetna beats beating beaten punch punched slap slapped slapping thappad thapad assault assaulted assaulting thrash thrashed thrashing ضرب يضرب يضربني ضربني ضربها يضربها مارتا مارتی مارا مار مارتے پیٹ پیٹتا मारता मारती मारा मार मारते पीट पीटता पीटा पीटते हमला هجوم يهاجم هاجم",
)
W("DOORV", "darwaza darwaze darwaja door gate دروازه دروازے दरवाजा दरवाज़ा باب")
W(
    "BREAKV",
    "tod torh tora toda tod-raha torna todna break breaking breaks broke broken smash smashing smashed kick kicking توڑ تور توڑ رہا तोड़ तोड رہا یکسر یكسر يكسر",
)
W("NIGHTW", "raat night midnight raatko raat-ko رات रात ليل منتصف")
W("KOI2", "koi someone somebody کوئی कोई احدهم")
W("SHATTER", "shisha shishay shishe glass windows windshield شیشے شیشہ कांच शीशे زجاج")
# self-harm
PH(
    "VIOL_OBJ",
    "with a belt/belt se/بیلٹ سے/बेल्ट से/بالحزام/with a stick/with sticks/with rods/with stones/with a rod/with an iron rod/laathi se/lathi se/danda se/danday se/ڈنڈے سے/لاٹھی سے/लाठी से/डंडे से",
)
W("ROPE", "rope rassi rasi noose phansi fanda fansi hang hanging hanged حبل رسی रस्सी فندہ")
W("HANGW", "hang hanging noose phansi fanda fansi لٹک لٹکنا फांसी फंदा")
W(
    "JUMPV",
    "jump jumping kood kud kood-jaunga koodna chhalang chhalaang jumped leap leaping قفز چھلانگ کود कूद कूदना छलांग",
)
W("BUNGEE", "bungee ski rope-jump parachute skydiving long-jump high-jump jump-start")
W(
    "HOARD",
    "jama saved save collected collect stockpile stored sambhal sambhaal rakh-li jama-kar جمع कर جمع करली",
)
W("TONIGHT", "tonight aaj-raat raat tonite کل आज रात الليلة الليله اليوم")
PH("TONIGHT", "aaj raat/آج رات/आज रात/is raat/اس رات/इस रात")
PH(
    "SH_PHRASE",
    "goodbye letter/goodbye note/suicide note/last message/my last message/my final message/this is my last/final goodbye/alvida ka khat/alvida ka letter/alvida letter/alvida khat/sab ko alvida/sab ko khuda hafiz/alvida duniya/aakhri khat/aakhri message/aakhri paigham/aakhri baat/aakhri alfaz/aakhri salam/آخری پیغام/آخری خط/آخری بات/الوداعی خط/الوداعی پیغام/آخری سلام/आखिरी संदेश/आखिरी खत/आखिरी बात/अलविदा का खत/सबको अलविदा/رسالة الوداع/رسالتي الاخيرة/رسالتي الأخيرة/رسالة وداع/وداعا للجميع/hamesha ke liye so/hamesha ke liye sona/hamesha ke liye chala/never wake up/not wake up again/not wake up ever/ولا استيقظ/ولا أستيقظ/कभी नहीं उठना/कभी न उठना/kabhi na uthna/kabhi na uthun/kabhi nahi uthna/better off without me/better off if i was gone/better off if i were gone/better if i was gone/better without me/mere bina behtar/mere bina sab/mere bina sab theek/mere bina sab behtar/میرے بغیر سب/میرے بغیر بہتر/मेरे बिना सब/मेरे बिना बेहतर/الجميع افضل حالا بدوني/الجميع أفضل حالا بدوني/افضل بدوني/أفضل بدوني/pain to stop forever/pain to stop for good/want the pain to stop/dard bardasht nahi/bardasht nahi hota/bardasht nahi hoga/برداشت نہیں ہوتا/बर्दाश्त नहीं होता/bas sab khatam/bas ab sab khatam/ab sab khatam/jee nahi sakti/jee nahi sakta/jee nahin sakta/nahi jee sakta/nahi jee sakti/nahin jee sakta/nahin jee sakti/aur nahi jiya/nahi jiya jata/nahin jiya jata/nahi jiya jaata/نہیں جی سکتا/نہیں جی سکتی/नहीं जी सकता/नहीं जी सकती/لم أعد أستطيع العيش/لا استطيع العيش/لا أستطيع العيش/قررت أن أنهي/قررت ان انهي/i have decided to kill/i have decided to end/decided to die/faisla kar liya hai mar/marne ka faisla/मरने का फैसला/مرنے کا فیصلہ/maine faisla kar liya/ab mujhse aur nahi/ab mujhse nahi/mujhse aur nahi jiya/i cant do this anymore/i cant go on/i can not go on/cant take it anymore/can not take it anymore/cannot take it anymore/cant take this anymore/i am done with everything/i am done with life/done with everything/sab se thak gaya/saari zindagi se thak/jump off the/jump from the/jump off a/jump from a/jump from roof/jump off roof",
)
W("SH_ROOF", "roof edge terrace bridge chhat pul sath سطح छत")
# kidnap / robbery
W(
    "CASHTAKE",
    "paise paisa cash money phones phone mobile mobiles till gallay galla gallay naqdi naqd nakdi rupay rupees purse wallet bag zevar jewellery jewelry gold پیسے نقدی موبائل موبائلز گلے पैसे नकदी मोबाइल गल्ले पैसा المال هواتف هاتف الصندوق النقود",
)
W("STRANGER", "stranger ajnabi ajnabee unknown man unknown-man اجنبی अजनबी غريب شخص-غريب")
W(
    "LURE",
    "lured lure luring bithaya bithakar bitha phusla phuslaya phuslakar bahla bahlaya بٹھا बिठा बिठाकर",
)
W("CARV", "car gaari gadi van vehicle rickshaw motorcycle bike truck گاڑی سیارة सيارة गाड़ी")
PH(
    "PAYORELSE",
    "pay by tomorrow/pay or else/or else we/otherwise we will/otherwise we'll/paise do warna/paisay do warna/paise nahi diye to/paise nahi diye toh/kal tak paise/kal tak ka waqt/پیسے دو ورنہ/کل تک پیسے/ورنہ/पैसे दो वरना/कल तक पैसे/वरना/اذا لم تدفعوا/او سوف/غدا المال",
)
PH(
    "KEPT",
    "rakh liya/rakh liye/rakh liya hai/رکھ لیا/रख लिया/انہوں نے رکھ لیا/احتجزوا/احتجزو/احتجزه/احتجزها/they have my/they have our/they took my/they took our/they are holding my/they are holding our/holding my/holding our/they are keeping my",
)
PH(
    "DEMANDMONEY",
    "want money/asking for money/demanding money/demand money/asking for ransom/paise maang/paisay maang/paise maange/paisay maange/maang rahe hain/maang rahe/mang rahe/مانگ رہے/مانگ رہا/मांग रहे/मांग रहा/يطلبون المال/يطلبون فدية/طلبوا مال/يطلبون",
)
W("STORM", "stormed storm storming raided raid raiding ransacked ransack stormed-in")
W("HOLDUP", "holdup hold-up held-up robbed robbing mugged mugging looted looting loot looted-the")
PH(
    "HOLDUP",
    "held up/hold up/emptied the till/emptied the cash/took the cash/took all the cash/took the money/took all the money/took my phone/took the phone/took our phones/took all the passengers/cheen liye/cheen li/cheen kar/cheen liya/loot liya/loot li/loot kar/le gaye paise/paise le gaye/paise le gaye/نقدی لے گئے/پیسے لے گئے/چھین لیے/چھین لی/چھین لیا/लूट लिया/छीन लिए/छीन ली/छीन लिया/पैसे ले गए/सرقوا/سرقوا المال/سرقوا الصندوق",
)
W("THIEF", "daakuon dakuon looteron lutere lootere")
W("DOORCRASH", "toor torh tod tor توڑ तोड़")
W(
    "TIEV",
    "tie tying tied tie-up baandh baandhna baandhte baandh-rahe baandhkar bandh-kar bandhte bandhna باندھ باندھ رہے बांध बाँध बांधकर قيدوا قيد ربطوا ربط",
)
W("US", "us hamein humein hum hamen ہمیں ہم हमें हम لنا نحن")
W(
    "RELEASE",
    "release rihai rihaayi chhodne chhorne choorne chhudane chhudwane chhudaane chhodna رہائی छुड़ाने छोड़ने छुड़ाना الإفراج افراج",
)
# event mask and hedged rule

W("GUARD", "guard chowkidar watchman cashier manager staff driver security")
W(
    "SERVANT",
    "servant naukrani nokrani naukar maid kaam-karwa kaam-karwate kaam-karwana domestic ghar-ka-kaam نوکرانی नौकरानी خادمة",
)
PH(
    "SERVANT",
    "made to work/forced to work/being forced to work/kaam karwate/kaam karwa/kaam par lagaya/child labour/child labor/brick kiln/bhatta mazdoor/بھٹے پر/ईंट भट्ठे/تعمل خادمة",
)
PH(
    "FORCEDM",
    "forced marriage/zabardasti shaadi/zabardasti ki shaadi/zabardasti nikah/majboor kar ke shaadi/married off/marrying off/against her will/against his will/early marriage/child marriage/underage marriage/زبردستی کی شادی/زبردستی شادی/जबरदस्ती शादी/जबरन शादी/بالإكراه/تزويج/كره",
)
W(
    "KISSV",
    "kiss kisses kissing kissed choom choomta choomte choomti chooma چومتا چومنا चूमता चूमना يقبل قبل",
)
W("NAKED", "naked nude nanga nangi ننگی ننگا नग्न नंगा obscene فاضحة صور-فاضحة")
PH(
    "NAKED",
    "naked pictures/nude pictures/naked photos/nude photos/naked videos/ganday video/gande video/gandi video/گندی ویڈیو/गंदी वीडियो/صورا فاضحة/صور فاضحة",
)
W("HITV", "talwon talwe تلووں तलवों")
PH(
    "CHILD",
    "madrasa ka ustaad/madrasay ka ustaad/madrasa teacher/madrasay ka teacher/مدرسے کا استاد/मदरसे का उस्ताद/معلم المدرسة",
)
for _w in "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen aath nau das gyarah barah terah chaudah pandrah solah satrah ایک دو تین چار پانچ چھ سات آٹھ نو دس گیارہ بارہ تیرہ چودہ پندرہ سولہ سترہ एक दो तीन चार पांच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह".split():
    PH(
        "CHILD",
        f"{_w} year old/{_w} years old/{_w} saal ki/{_w} saal ka/{_w} saal ke/{_w} sal ki/{_w} sal ka/{_w} سال کی/{_w} سال کا/{_w} سال کے/{_w} साल की/{_w} साल का/{_w} साल के/boy of {_w}/girl of {_w}/a boy of {_w}/a girl of {_w}/{_w} year-old",
    )
W(
    "CHILD",
    "minor nabalig underage younger-sister younger-brother little-sister little-brother نابالغ नाबालिग قاصر",
)
W(
    "RELATIVE",
    "cousin father mother walid walida driver staff employee boss colleague neighbour neighbor padosi pita माता पिता वालिद ابن-عمي ابن-عم اخ اخت اب ام زوج زوجة زوجتي والدي والدتي ابني اخي اختي",
)
W(
    "MONEYN",
    "lakh lakhs crore karod hazar thousand million لاکھ لاکھوں کروڑ ہزار लाख करोड़ हजार ألف مليون",
)
W(
    "FEMALE_V",
    "sister behan behen bahen girl woman wife daughter niece ladki aurat بہن لڑکی عورت बहन लड़की औरत",
)


# === wave 4b: fixes found by the first fresh set ===
W("BIZ", "margins margin revenue profit economy cost costs")
W("WORKY", "tickets ticket backlog queue outage incidents incident")
W("TRADE", "dressing listing products product catalog catalogue")
PH("DOWN", "گر پڑے/گر پڑا/گر پڑی/गिर पड़े/गिर पड़ा/गिर पड़ी/गिर गए/گر گئے/گر گیا/گر گئی")
W(
    "RELATIVE",
    "पिताजी पापा मां माँ दादी दादा नानी नाना भाई بابا ابو امی ماں دادی دادا نانی نانا بھائی بہن بیٹا",
)
W(
    "CHILD",
    "طفلا طفلين اطفال ولدا daughters sons sisters nieces girls bachiyon bachiyan bachiyaan bachchiyon larkiyon ladkiyon betiyon betiyan bachyon",
)
W("COUGH", "cough coughing coughs khansi khansna khansta khansti کھانسی कھानسी खांसी سعال يسعل")
PH(
    "COUGH",
    "cannot stop coughing/can not stop coughing/cant stop coughing/can't stop coughing/khansi ruk nahi/کھانسی نہیں رک/खांसी नहीं रुक",
)
PH(
    "TOXIC",
    "mixed bleach/mixing bleach/mixed chemicals/mixing chemicals/bleach and acid/bleach with acid/bleach and ammonia",
)
W(
    "THROWV",
    "phenk phenka phenke phenkna phenkne phenki پھینک پھینکنے پھینکا پھینکنا फेंक फेंकने फेंका फेंकना throw threw throwing thrown سكب اسكب يسكب يرمي",
)
W("ACID", "acid tezab tezaab تیزاب तेजाब تیزاب حمض الحمض")
W("VIOL_STRONG", "golibari goliyan-chal فائرنگ गोलीबारी gunshots gunshot ghaseet")
W("JUMPV", "اقفز يقفز")
W("HIGHPLACE", "چھت पل پل")
PH(
    "SH_PHRASE",
    "کبھی نہ اٹھنا/کبھی نہیں اٹھنا/کبھی نہ جاگنا/سو جانا چاہتا/سو جانا چاہتی/और कभी नहीं उठना",
)
W(
    "SNEAK",
    "sneak sneaks sneaked sneaking chupke chupkay chupchap enters entered یدخل يدخل يدخلون يتسلل گھستا",
)
W("NIGHTW", "ليلا ليلة")
W("FEMALE_V", "اختي بنت ابنه")
W("CARV", "سيارته سيارتهم سيارتي سيارتها")
W("KEPT", "احتجزوا احتجزه احتجزها")
W("PAYORELSE", "ورنہ वरना warna ورنه")
W("THIEF", "डाकुओं चोरों लुटेरों ڈاکوؤں چوروں لٹیروں اللصوص")
W("FIRE_N", "चिंगारियां چنگاریاں چنگاریان شرار شرارا شرارة")


# === wave 4c: wider harm bags, found with the second fresh set ===
# medical symptom and injury bag
W(
    "HARM_MED",
    "foaming froth peeling swelling swollen sooj sooj-gaye swell hives allergic anaphylaxis asthma dama inhaler diabetic diabetes sweating limp pale paleness peela zard zard-pad sunn sunn-ho nosebleed fracture fractured bent crooked mud mudi mudna phisal phisla phisli slipped slipping bite bit bitten bites kaat kaata kaati chewed screaming chilla chillana chilla-raha ukhad ukhadna sooja سوج سوجن کاٹ لیا ٹھنڈا ٹھنڈے मुड़ मुड़ी सूज फिसल फिसलकर काट لدغ عض زرقاوان زرقاء ينزف نزيف مكسورة مكسور ورم تورم فاقد تدفق",
)
PH(
    "HARM_MED",
    "body is cold/body cold/jism thanda/jism thandaa/sharir thanda/جسم ٹھنڈا/شرابیر ٹھنڈا/शरीर ठंडा/not crying/not waking up/wont wake up/will not wake up/not waking/uth nahi raha/uth nahi rahi/uth nahi rahe/اٹھ نہیں رہا/اٹھ نہیں رہے/उठ नहीं रहे/उठ नहीं रहा/لا يستيقظ/لا يستيقظون/lips and throat/honth aur gala/talking nonsense/ajeeb baatein/saans ukhad/sans ukhad/not stopped for/ruk nahi raha/ruk hi nahi raha/رک نہیں رہا/نہیں رک رہا/ولا يتوقف/skin is peeling/jild utar/جلد اتر/hit on the head/hit the mason/sar par lagi/sar pe lagi/head injury/چہرے پر کاٹ/चेहरे पर काट/في وجهه/عض الولد",
)
W("NOMOVE", "")
PH(
    "NOMOVE",
    "not waking up/wont wake up/will not wake up/uth nahi raha/uth nahi rahi/uth nahi rahe/اٹھ نہیں رہا/اٹھ نہیں رہے/उठ नहीं रहे/उठ नहीं रहा/لا يستيقظ/لا يستيقظون/not waking",
)
# poisoning bag
W(
    "HARM_POIS",
    "foaming froth unlabeled unlabelled unknown-liquid pellets pellet killer chewed chaba chabaa chabali chaba-li biryani feast وليمة تسمم تسممت سم الفئران عصير",
)
PH(
    "HARM_POIS",
    "from an unlabeled bottle/from an unlabelled bottle/from a bottle/mouse killer/rat killer/rat pellets/chuhe maar/chuhay maar/چوہے مار/چوہے مار گولیاں/सسم/सुम فئران/whole strip/poori strip/puri strip/sari goliyan/saari goliyan/ate the biryani/ate the food/khana kha kar/کھانا کھا کر/खाना खाकर/خوراک/after the wedding/شادی کا کھانا/शादी का खाना",
)
W("DAST", "dast loose-motions diarrhoea diarrhea دست दस्त اسهال")
W("VOMIT", "dast دست दस्त اسهال قيء")
W("NOMEDS", "")
PH(
    "MEDS",
    "neend ki goli/neend ki goliyan/neend ki shishi/neend ki dawai/neend ki dawa/نیند کی گولی/نیند کی گولیاں/نیند کی شیشی/नींद की गोली/नींद की गोलियां/नींद की शीशी/sleeping pills/sleeping pill/sleeping tablets/sleeping tablet/حبوب النوم/حبوب منومة",
)
W("QTY", "shishi bottle strip شیشی शीशी زجاجة زجاجه كاملة كامله whole full puri poori پوری पूरी")
W("INGEST_P", "taken تناولت تناول have-taken")
# violence bag
W("PETROL", "petrol diesel kerosene benzin بنزين بنزین پٹرول पेट्रोल मिट्टी")
W(
    "POUR",
    "poured pour pouring chhirak chhirka chhidak chhirkna chhirakna sprinkle sprinkled drenched سكب چھڑک چھڑکا छिड़क छिड़का सिंचित",
)
W("LIGHTERW", "lighter match matchstick matches ماچس लाइटर माचिस")
W("BOMBW", "bomb grenade bam blast-hua dhamake gola-barood قنبلة قنبله گرینیڈ ग्रेनेड बम بم")
W("THROAT", "throat gala gale gardan گلا گردن गला गर्दन رقبة عنق حلق")
W("HANDS", "hands hand hath haath ہاتھ हाथ يد يدي")
W(
    "PRESS",
    "press pressed pressing squeeze squeezed squeezing grab grabbed daba daaba dabaya dabate دبا दबा ghont",
)
PH(
    "THROAT",
    "around her throat/around his throat/around my throat/on her throat/on his throat/around the neck/by the throat/gardan par hath/gale par hath/گردن پر ہاتھ/गर्दन पर हाथ",
)
W(
    "DRAGV",
    "drag dragged dragging dragg ghaseet ghaseeta khench kheench khencha khenchna khinch jabran dhakel dhakelna کھینچ کھینچا ڈھکیل खींच खींचा घसीट घसीटा يجر سحب جر",
)
W(
    "VIOL_OBJ",
    "hockey bat bats cricket-bat rods rod eent eentein eenten bricks brick اینٹ اینٹیں ایٹ ईंट ईंटें الهوكي",
)
W("HITV", "hitting hits punching smashing hitted beaten-up ہٹنگ")
W("PERSON", "boys boy girls ladke ladka larka larke لڑکے लड़के اولاد الاولاد شباب شاب")
W("BRICKTHROW", "barsa barsana barsa-rahi barsate برسا बरसा raining-bricks")
# self-harm bag
W("VEIN", "nas nass nas-kaat vein veins artery شریان شرياني رگ نس नस رگیں wrist kalai كلائة معصم")
W(
    "CUTV",
    "kaat kaatna katna kaat-lunga kaat-lungi cut cutting slit slash slice slit-my اقطع قطع قطعت کاٹ काट",
)
W("WILLW", "will wasiyat wasiyatnama wasiyyat وصیت وصيتي وصيه वसीयत वसीयतनामा")
W(
    "WRITEV",
    "write wrote written writing likh likha likhi likhdi likh-di كتبت اكتب كتب لکھ لکھی لکھ دی लिख लिखी",
)
PH(
    "DEPART",
    "wont be here tomorrow/won't be here tomorrow/will not be here tomorrow/not be here tomorrow/wont be around/won't be around/not be around/kal main nahi/kal main nahi hounga/kal main nahi rahunga/کل میں نہیں/कल मैं नहीं/لن اكون هنا/لن أكون هنا/لن اكون موجودا/main nahi rahunga/main nahi rahungi/main nahi hounga/میں نہیں رہوں گا/میں نہیں ہوں گا/मैं नहीं रहूंगा/मैं नहीं रहूँगा",
)
PH(
    "SH_PHRASE",
    "disappear forever/disappeared forever/vanish forever/gayab ho jaun/gayab ho jaoon/hamesha ke liye gayab/ہمیشہ کے لیے غائب/हमेशा के लिए गायब/nobody would notice if i/no one would notice if i/koi farq nahi padega agar main/kisi ko farq nahi padega/کسی کو فرق نہیں پڑے گا/किसी को फर्क नहीं पड़ेगा/in front of a train/under a train/in front of a truck/into oncoming traffic/off the highway on purpose/drive off a cliff/train ke neeche/ٹرین کے نیچے/ट्रेन के नीचे/canal mein kood/nehar mein kood/نہر میں کود/नहर में कूद/on purpose off the/car off the/driving the car off",
)
# abuse of children bag
W("STRIPV", "strip stripped stripping utarwa utarwakar utarwate uttar utarna utaar يجرد جرد اتروا")
PH(
    "STRIPV",
    "kapde utar/kapde utarwa/کپڑے اتر/کپڑے اتروا/कपड़े उतर/कपड़े उतरवा/ملابسهم/take off their clothes/take off her clothes/remove their clothes/remove her clothes",
)
W("CHILD", "boys boy larkon larko ladko لڑکوں लड़कों الاولاد اولاد")
PH(
    "SEXUAL_V",
    "comes to her bed/comes to my bed/comes to his bed/comes into her bed/bistar par aata/bistar par aate/bistar pe aata/بستر پر آتا/بستر پر آتے/बिस्तर पर आता/बिस्तर पर आते/ليأتي إلى سريرها/يأتي إلى سريرها/يأتي الى سريرها/touches them/touched them/touching them/chhoota hai/chhoote hain/چھوتا ہے/چھوتے ہیں/छूता है/छूते हैं/يلمسهم/يلمسهن/يلمسها",
)
W("CHAIN", "chained chain zanjeer zanjir جنجیر زنجیر जंजीर مقيد سلسلة")
PH(
    "ABUSEMARK",
    "burn marks/jale hue nishan/jalne ke nishan/bruises/neel ke nishan/نیل کے نشان/جلنے کے نشان/جلنے کے نشانات/जलने के निशान/चोट के निशान/اثار حروق/اثار ضرب/كدمات",
)
for _w in "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen".split():
    PH("CHILD", f"aged {_w}/age {_w}/{_w} saal/{_w} سال/{_w} साल/{_w} sal")
W("MEDIA", "props prop note")
# robbery bag
W("BAGMOB", "chain gold-chain sone-ki-chain چین चेन necklace jewellery zevar gale-se سلسلة")
W("CASHTAKE", "chain necklace cargo truck load maal سلسلة")
PH(
    "ESCAPEV",
    "bhaag gaye/bhag gaye/bhaag gayi/بھاگ گئے/بھاگ گیا/भाग गए/भाग गया/ran away with/fled with/ran off with/drove off with/هربوا/هرب",
)
W("ROB_STRONG", "خطفا خطفوا")
W("SHUTTER", "shutter shutters shuter شٹر शटर")
W("DOORV", "shutter shutters شٹر शटर")
W("FORCEDV", "forced forcing jabran forcefully tora toda")
W("GUARD", "guards cashiers managers drivers watchmen chowkidars")
PH(
    "KEPT",
    "is with us/hamare paas hai/hamare paas/ہمارے پاس ہے/ہمارے پاس/हमारे पास है/हमारे पास/عندنا/we have your son/we have your daughter/we have your husband/we have your brother/we have your father/aap ka beta hamare/آپ کا بیٹا ہمارے/आपका बेटा हमारे/ابنك عندنا",
)
W("STORM", "اقتحم اقتحموا يقتحم يقتحمون")
W("ENTER", "اقتحم اقتحموا يقتحم يقتحمون")
# fire bag
PH(
    "FIRE_N",
    "burning smell/smell of burning/smells of burning/smells like burning/burning plastic/burning rubber/burning wires/burning wire/jalne ki boo/jalne ki badboo/jalne ki bu/plastic jalne/تار جلنے/جلنے کی بو/جلنے کی بدبو/जलने की बदबू/जलने की बू/प्लास्टिक जलने/رائحة احتراق/رائحة بلاستيك محترق/رائحه حريق",
)
W("FIRE_N", "محترق محترقة")
PH(
    "FIRE_N",
    "glowing orange/orange glow/orange light/narangi roshni/narangi raushni/نارنجی روشنی/नारंगी रोशनी/lal roshni/لال روشنی/लाल रोशनी",
)

W(
    "TECH",
    "customer customers client clients supplier vendor whatsapp message messages email emails phone reply chat dm inbox",
)


# === wave 4d: concept bags found with the third (held-out) fresh set ===
W("TRADE", "ad ads toothpaste menu card review merchandise sandwich diffuser")
W(
    "SHAKE",
    "kaanp kaanpna kaanpta kaanpti kaanp-raha shaking trembling shiver shivering کانپ ارتعاش يرتجف कांप कांपना",
)
W(
    "BOIL",
    "boiling ubalte ubalta khaulte khaulta khaulte-paani کھولتے उबलते खौलते المغلي المغلى المغلية",
)
PH(
    "BOIL",
    "hot oil/garam tel/garam paani/gram pani/گرم تیل/गरम तेल/hot water/scalding/scalded/zeitoon",
)
W("LIPS", "lips honth ہونٹ होंठ شفاه شفتاه شفتان")
W(
    "COLORBLUE",
    "blue purple violet neela neele neeli nila jaamni jamni neelay نیلے نیلا जامنी جامنی नीले बैंगनी ارجوانيتان ارجوانية زرقاوان زرقاء ازرق",
)
PH(
    "INLABOUR",
    "water broke/waters broke/water has broken/paani toot gaya/baby is coming/baby is coming right now/bachcha ho raha/bachcha hone wala/پانی ٹوٹ/पानी टूट/قارب الولادة/ولادة الان",
)
PH(
    "DAMPHOOL",
    "dam phool/dum phool/sans phool/saans phool/sans phulna/saans phulna/دم پھول/سانس پھول/सांस फूल/दम फूल/gasping for/gasping and",
)
W("DAMPHOOL", "gasping gasp gasps يلهث لهاث")
W(
    "BODY_ALL",
    "hip kulha kooli kandha shoulder jaw rib ribs pasli pasliyan knee ghutna ankle thigh ران ورك الورك ركبة",
)
W("GOLI_V", "لگ لگی لگا لگ گئی چل چلی लग लगी लगा चल चली")
W("GOLI_N", "गोली गोलियां")
PH(
    "GUNSHOT",
    "طلق ناري/برصاصة/اصيب برصاص/اصيب بطلق/رصاصة في/shot in the/got shot/was shot/been shot/golibari mein/firing mein",
)
W("INGEST_ANY", "chaata chata chaat licked lick لحس چاٹ چاٹ چاٹنا चाट चाटा")
W("KEEDE", "حمض الحمض")
W("EDIBLE_RISK", "berries berry mushroom mushrooms jungli-phal wild-fruit توت توتا کھمبی खुमी मशरूम")
PH(
    "EDIBLE_RISK",
    "jungli phal/wild fruit/wild fruits/wild berries/wild mushrooms/bagh ke phal/باغ کے پھل/جنگلی پھل/जंगली फल",
)
W("SICK", "sick ill beemar bimar vomiting vomit mareez مرضى مريض بیمار बीमार")
W("WEAPON", "axe kulhari kulhaari kulhadi کلہاڑی कुल्हाड़ी फأس فأس مسدس سلاح سكين سكاكين")
PH(
    "THREAT_P",
    "finish me/finish you/finish him/finish her/finish us/khatam kar dunga/khatam kar doonga/khatam kar dungi/ختم کر دوں گا/خत्म कर दूंगा/खत्म कर दूंगा/سينهيني/سأنهيه/سانهيه",
)
PH(
    "SMOTHER",
    "pillow over/pillow on her face/pillow on his face/takiya rakh/takiye se/تکیہ منہ پر/تکیہ رکھ/وسادة على وجه/تکیے سے/तकिया मुंह पर/तकिया रख/smother/smothered/smothering/suffocate/suffocated/suffocating/dam ghont/دم گھونٹ/دم घोंट",
)
PH(
    "VIOL_STRONG",
    "spraying bullets/raining bullets/opened fire/open fire/opening fire/goliyan barsa/goliyan barsa rahi/goliyan barsa raha/گولیاں برسا/गोलियां बरسा/गोलियां बरसा/تمطر المحل بالرصاص/بالرصاص/rounds of fire/gunfire",
)
W("HITV", "slaps slapping thappad थप्पड़ تھپڑ يصفعه يصفع يصفعها")
PH(
    "VOYEUR",
    "recording my/recording her/recording him/filming her/filming my/filming him/hidden camera/secret camera/camera in the bathroom/chhupa camera/chhupa hua camera/خفیہ کیمرہ/छिपा कैमरा/record karta hai/record karte hain/ریکارڈ کرتا ہے/रिकॉर्ड करता है/يصور/يصورها",
)
W("BATHROOMW", "bathroom washroom hammam toilet changing-room حمام باتھ روم बाथरूम")
PH(
    "LAP",
    "sit on his lap/sit on my lap/sit on her lap/made her sit/made him sit/goad mein bitha/god mein bitha/goad mein bithaya/گود میں بٹھا/गोद में बिठा/في حضنه/في حضني",
)
PH(
    "SOLDP",
    "being sold/is being sold/was sold/sold to/selling my/sell my/selling her/selling his/selling the girl/bech rahe/bech diya/bech di/بیچ دیا/بیچ رہے/बेच दिया/बेच रहे/hawale kar rahe/hawale kar diya/حوالے کر رہے/हवाले कर रहे/يبيعون/باعوا",
)
W("CARV", "taxi cab driver rickshaw-wala")
W("CASHTAKE", "safe tijori tijoree vault تجوری तिजोरी خزنة الصندوق")
W(
    "RELATIVE",
    "पति पत्नी बीवी भाई बहन बेटा बेटी पिता माता चाचा मामा شوہر بیوی بھائی بہن بیٹا بیٹی والد والدہ چچا ماموں",
)
W("ROB_STRONG", "يسرق سرق")
W("RAIL", "railway railtrack track rail ریلوے ٹریک रेलवे ट्रैक سكة القطار سكه القطار القطار train")
W(
    "WAITINGON",
    "khada khadi khada-hoon baith baitha standing waiting sitting intezaar intezar انتظار انتظر खड़ा खड़ी इंतजार वेट واقف واقفة",
)
PH(
    "SH_PHRASE",
    "tonight is the night/aaj raat hi woh raat/aaj hi woh raat hai/آج رات وہی رات/आज रात वही रात/الليلة هي الليلة/not exist/dont want to exist/do not want to exist/close my eyes and not/aankhein band kar ke ab kabhi nahi/never exist again/wish i didnt exist/wish i was never born/wish i had never been born/kaash main paida na hota/کاش میں پیدا نہ ہوتا/काश मैं पैदा न होता/اريد ان اغمض عيني/bought the pills/pills and a bottle/goliyan aur botal/sat down to do it/i bought a rope/bought a rope/rassi khareed/رسی خرید/रस्सी खरीद",
)


# === wave 4e: structural concepts from the fourth fresh set (plans, grooming, grabbing, climbing in, burn threats) ===
W("PLANW", "plan planning planned planning-to منصوبہ منصوبے योजना خططت خطة")
W(
    "ENDW",
    "end ending finish suicide die dying khatam marne marna مرنے ختم खत्म मरने حياتي انهاء انهي",
)
PH(
    "SH_PHRASE",
    "take his own life/take her own life/take their own life/took his own life/took her own life/took their own life/going to take his own life/end it this/end it tonight/end it on/end it by/end it after/wont need her anymore/wont need him anymore/wont need it anymore/will not need it/zaroorat nahi hogi/ضرورت نہیں ہوگی/ज़रूरत नहीं होगी/gave away my/given away my/gave my cat away/gave my dog away/de di kyunki ab/di kyunki ab mujhe/لے لے گا/le lega/le legi/jaan le lega/جان لے لے گا/जान ले लेगा",
)
W("FUTV", "lega legi lenge dega degi denge لے گا لے گی देगा देगी लेगा लेगी")
W("ALONEW", "alone akele akela akeli تنہا اکیلے اکیلا अकेले अकेला")
PH(
    "ALONEW",
    "his room/apne kamre/apne room/اپنے کمرے/अपने कमरे/come to his room/come to my room/behind the counter/counter ke peeche/after class/class ke baad/بعد الکلاس/class के बाद/bulata hai/bulaata hai/bulati hai/بلاتا ہے/बुलाता है/asks the girls/asks the boys/asks her to come/asks him to come",
)
W("GRABV", "grabbed grab snatched snatch pakad pakda pakadliya dhar-liya دبوچ پکڑ पकड़ पकड़ा खींचा")
PH(
    "GRABV",
    "pakad liya/pakad li/pakad kar le gaye/pakad ke le gaye/پکڑ لیا/پکڑ کر لے گئے/पकड़ लिया/पकड़ कर ले गए/grabbed her/grabbed him/grabbed my/grabbed our/they grabbed/unhon ne pakad",
)
W(
    "CLIMB",
    "climbing climb climbed phaand phaandna phaand-kar phand deewar diwar compound boundary wall چڑھ پھاند دیوار دیوار पھاند फांद फांदकर दीवार चढ़ चढ़",
)
PH(
    "CLIMB",
    "climbing the wall/climbing over/over the wall/deewar phaand/diwar phaand/دیوار پھاند/दीवार फांद/boundary wall/compound wall",
)
PH(
    "HARM_MED",
    "peele pad/peela pad/peele par/پیلے پڑ/पीले पड़/شحب/utha nahi pa/utha nahi sakta/اٹھا نہیں پا/उठा नहीं पा/لا يستطيع رفع/cannot lift/can not lift/unable to lift/cant lift/can't lift",
)
PH(
    "TOXIC",
    "ghaas maar dawai/ghas maar dawai/weed killer/weedkiller/घास मारने की दवा/घास मार दवा/گھاس مار دوا/مبيد الاعشاب/مبيد الأعشاب",
)
PH(
    "THREAT_P",
    "will burn/going to burn/burn my house/burn our house/burn the house/burn your house/jala dega/jala denge/jala dunga/jala dungi/جلا دے گا/جلا دیں گے/जला देगा/जला देंगे/سيحرق/سنحرق",
)
W("SALE_MKT", "clearance")
PH(
    "FIRE_N",
    "wall is lit up/whole wall is lit up/deewar bhadak/diwar bhadak/دیوار بھڑک/दीवार भड़क/bhadak rahi hai/bhadak raha hai/bhadak gayi/bhadak gaya/بھڑک رہی/بھڑک اٹھی/भड़क रही/भड़क उठी/lit up/caught fire",
)
W(
    "RELATIVE",
    "chacha mamu tayya phuphi khala chachi mami चाचा मामा ताऊ बुआ खाला چچا ماموں تایا پھوپھی خالہ عمي خالي",
)

W("BIZ", "quarter year month target targets")
W("WORKY", "quarter strong target targets")

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
R("SELF_HARM", "SH_PHRASE", avoid="SALE_MKT", name="sh phrase")
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
R("CHILD_SAFEGUARDING", "HIT", ["CHILD"], win=8, avoid="IDIOM_H", name="child hit")
R("CHILD_SAFEGUARDING", "SEXUAL_V", ["FEMALE_V"], win=8, name="sexual abuse")
R("CHILD_SAFEGUARDING", "WRONGPLACE", ["FEMALE_V"], win=10, name="touched wrongly")
R("CHILD_SAFEGUARDING", "GHALATK", ["CHILD", "SAATH", "HOGAYA"], win=4, name="ghalat kaam hua")
R("CHILD_SAFEGUARDING", "ZABARDASTI", ["SHAADI", "FEMALE_V"], win=5, name="forced marriage")
R("CHILD_SAFEGUARDING", "BECH", ["CHILD", "PARENTS"], win=8, avoid="TRADE", name="child sold")

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
    win=6,
    avoid="OBJ",
    kind="SAFEGUARDING",
    name="child missing",
    trade="msg",
)
R(
    "KIDNAP_ROBBERY",
    "LE",
    ["CHILD", "ANYONE", "GAYA"],
    win=10,
    avoid="NORMALPLACE",
    kind="SAFEGUARDING",
    name="child taken",
    trade="msg",
)
R(
    "KIDNAP_ROBBERY",
    "LE",
    ["CHILD", "DAL", "GAYA"],
    win=10,
    avoid="NORMALPLACE",
    kind="SAFEGUARDING",
    name="child bundled away",
)
R("KIDNAP_ROBBERY", "GUM_AR", ["CHILD"], win=3, kind="SAFEGUARDING", name="child missing arabic")
R(
    "KIDNAP_ROBBERY",
    "UTHA",
    ["CHILD", "LIYA|LE"],
    win=10,
    avoid="GODE|NORMALPLACE",
    kind="SAFEGUARDING",
    name="child picked up",
)

# `GOLI_N` needs a tag of its own (the word is also a tablet).
W("GOLI_N", "goli golee گولی گولی")


# second recall wave ---------------------------------------------------------------------------
R(
    "FIRE_SMOKE",
    "BURN_V",
    ["PLACE_OBJ|PLACE_BIG|PERSON"],
    win=4,
    avoid="LIGHT_ON|MONEYY|FOODY",
    trade="msg",
    name="something is burning",
)
R("MEDICAL_RESCUE", "FELL", ["HEIGHT"], win=5, avoid="BIZ", trade="msg", name="fell from a height")
R("MEDICAL_RESCUE", "NOMOVE", avoid="TECH", name="not moving")
R("MEDICAL_RESCUE", "CHOKE_V", trade="msg", name="choking")
R("MEDICAL_RESCUE", "STROKE_N", ["STROKE_V"], win=4, avoid="FILMY", name="stroke")
R("MEDICAL_RESCUE", "DOOB_E", avoid="WORKY", name="drowning (english)")
R("MEDICAL_RESCUE", "DOOB", ["PROG"], win=2, avoid="WORKY|MONEYY|BIZ", name="doob raha")
R("MEDICAL_RESCUE", "BREATHE", ["UNSURE"], win=6, name="doubt about breathing")
R("MEDICAL_RESCUE", "SANS", ["UNSURE"], win=6, name="doubt about saans")
R("POISONING", "SWALLOW", ["MEDS|FOREIGN|TOXIC"], win=4, trade="msg", name="swallowed something")
R(
    "VIOLENCE_ABUSE",
    "THREAT_P",
    ["ME|YOU2|VICTIM|US|PRON"],
    win=6,
    avoid="IDIOM_H",
    name="threat to kill me",
)
R("VIOLENCE_ABUSE", "HITME", name="beats me (arabic)")
R("VIOLENCE_ABUSE", "THREAT_AR", name="threatens me (arabic)")
R("VIOLENCE_ABUSE", "HIT", ["DANGER"], win=4, name="beating and help")
R("SELF_HARM", "SELFW", ["LE_DE", "FUTV"], win=4, avoid="WORKY2|IDIOMD", name="jaan le loonga")

R(
    "KIDNAP_ROBBERY",
    "UTHA",
    ["CHILD", "LIYA|LE", "KISI|ANYONE"],
    win=10,
    kind="SAFEGUARDING",
    trade="msg",
    name="someone picked the child up",
)
R(
    "KIDNAP_ROBBERY",
    "TAKEN",
    ["CHILD", "CARAWAY"],
    win=6,
    avoid="NORMALPLACE",
    kind="SAFEGUARDING",
    name="child taken in a car",
)

# fourth wave rules ------------------------------------------------------------------------------
R("FIRE_SMOKE", "FIRE_N", ["UNSURE"], win=6, trade="msg", name="hedged fire")
R("FIRE_SMOKE", "FIRE_N", ["LIVE"], win=8, name="fire with live cues")
R(
    "FIRE_SMOKE",
    "BURN_V",
    ["PAST_GO|PROG", "DANGER|INSIDE|PERSON"],
    win=6,
    avoid="LIGHT_ON|MONEYY|FOODY",
    name="burnt with people or urgency",
)
R("FIRE_SMOKE", "BURN_AR", trade="msg", name="arabic burning")
R("CHILD_SAFEGUARDING", "SEXUAL_V", ["CHILD"], win=10, name="abuse of a child (wide)")
R("CHILD_SAFEGUARDING", "TANGK", ["CHILD", "ADULT"], win=10, name="adult harasses a child")
R(
    "CHILD_SAFEGUARDING",
    "LOCKED",
    ["CHILD", "FOODLESS"],
    win=10,
    name="child locked up without food",
)
R("CHILD_SAFEGUARDING", "HABS", ["CHILD"], win=6, name="child confined (arabic)")
R("CHILD_SAFEGUARDING", "BEATV", ["CHILD"], win=10, avoid="IDIOM_H", name="child beaten (wide)")
R("KIDNAP_ROBBERY", "RANSOM", avoid="MEDIA|TECH", trade="msg", name="ransom or extortion")
R("KIDNAP_ROBBERY", "HOSTAGE", avoid="MEDIA", name="hostage")
R("KIDNAP_ROBBERY", "GUNPOINT", name="gunpoint")
R("KIDNAP_ROBBERY", "AGWA", avoid="MEDIA", trade="msg", name="kidnap word alone")
R("KIDNAP_ROBBERY", "ROB_STRONG", avoid="SALE_MKT|TECH", trade="msg", name="mugged or robbing")
R(
    "KIDNAP_ROBBERY",
    "ROB_WEAK",
    ["PROG|BAGMOB|ME|VICTIM|COPULA|DANGER"],
    win=6,
    avoid="SALE_MKT",
    trade="msg",
    name="looting or snatching",
)
R(
    "KIDNAP_ROBBERY",
    "TAKEN|UTHA|LE",
    ["CHILD|RELATIVE", "MONEYASK|MONEYN"],
    win=10,
    kind="SAFEGUARDING",
    name="taken and money asked",
)
R(
    "KIDNAP_ROBBERY",
    "MONEYASK",
    ["MONEYN", "CHILD|RELATIVE"],
    win=8,
    kind="SAFEGUARDING",
    name="money asked for a person",
)
R("KIDNAP_ROBBERY", "UTHA", ["RELATIVE", "LIYA|LE"], win=6, trade="msg", name="relative picked up")
R(
    "KIDNAP_ROBBERY",
    "TAKEN",
    ["CHILD|RELATIVE", "UNSURE"],
    win=8,
    kind="SAFEGUARDING",
    name="maybe someone took",
)

# === event grammar rules (wave 4) ====================================================================
# MEDICAL: injuries, collapse, convulsion, labour, vehicle hits, chest pain, machines, live wires
R("MEDICAL_RESCUE", "KHOON", avoid="FILMY|TECH", trade="msg", name="blood")
R("MEDICAL_RESCUE", "KHOON2", trade="msg", name="blood (bleeding)")
R("MEDICAL_RESCUE", "INJ", avoid="FILMY|TECH", trade="msg", name="injury")
R(
    "MEDICAL_RESCUE",
    "BODY_ALL",
    ["INJ|CAUGHTIN|BREAK|BITE"],
    win=4,
    avoid="BIZ|FILMY",
    trade="msg",
    name="body part hurt",
)
R(
    "MEDICAL_RESCUE",
    "MACHINE",
    ["BODY_ALL", "CAUGHTIN"],
    win=7,
    trade="msg",
    name="machine caught a limb",
)
R(
    "MEDICAL_RESCUE",
    "CHEST",
    ["CHEST_V"],
    win=5,
    trade="msg",
    avoid="FILMY",
    name="chest pain or clutching",
)
R(
    "MEDICAL_RESCUE",
    "DOWN",
    ["PERSON|CHILD|RELATIVE|PRON"],
    win=8,
    avoid="BIZ|TECH",
    trade="msg",
    name="person down",
)
R("MEDICAL_RESCUE", "SPEECHLOSS", trade="msg", name="cannot speak or face drooping")
R("MEDICAL_RESCUE", "CONVULSE", avoid="TECH", trade="msg", name="convulsions")
R(
    "MEDICAL_RESCUE",
    "VEHICLE_HIT",
    ["PERSON|CHILD|RELATIVE|PRON|FELL"],
    win=8,
    trade="msg",
    name="hit by a vehicle",
)
R(
    "MEDICAL_RESCUE",
    "VEHICLE_HIT",
    ["CHILD|RELATIVE"],
    win=10,
    trade="msg",
    name="relative hit by a vehicle",
)
R("MEDICAL_RESCUE", "INLABOUR", ["KHOON|KHOON2|INJ|DANGER"], win=8, name="labour with bleeding")
R("MEDICAL_RESCUE", "TOUCHV", ["WIRE|ELEC_N|LIVEWIRE"], win=5, name="touched a live wire")
R(
    "MEDICAL_RESCUE",
    "LIVEWIRE",
    ["PERSON|CHILD|RELATIVE|PRON|FELL"],
    win=8,
    name="live wire and a person",
)
R(
    "MEDICAL_RESCUE",
    "FELL",
    ["HEIGHT|PERSON|CHILD|RELATIVE"],
    win=6,
    avoid="BIZ|TECH|WORKY|MONEYY",
    trade="msg",
    name="person fell",
)
# POISONING and gas
R(
    "POISONING",
    "KEEDE|TOXIC",
    ["INGEST_ANY|INGEST_DONE|INGEST_P"],
    win=6,
    trade="msg",
    name="ingested a toxic product",
)
R(
    "POISONING",
    "VOMIT",
    ["PROG|CHILD|PERSON|FAMILYALL|PRON"],
    win=6,
    trade="msg",
    avoid="TECH",
    name="vomiting",
)
R(
    "POISONING",
    "HEATER",
    ["FUMES|FAINTED|NOMOVE|DOWN|LEAK"],
    win=8,
    trade="msg",
    name="heater or geyser fumes",
)
R(
    "POISONING",
    "CLOSEDROOM",
    ["CLOSEDPLACE", "FUMES|GAS_N"],
    win=6,
    trade="msg",
    name="gas in a closed room",
)
R(
    "POISONING",
    "GAS_N",
    ["FAINTED|CLOSEDROOM|DOWN"],
    win=8,
    trade="msg",
    name="gas and a person down",
)
R(
    "POISONING",
    "FUMES",
    ["FAINTED|CHILD|PERSON|RELATIVE|DOWN"],
    win=8,
    trade="msg",
    avoid="WORKY|FILMY",
    name="fumes and a person",
)
R("POISONING", "FAINTED", ["FUMES|GAS_N|HEATER"], win=8, trade="msg", name="fainted from fumes")
# VIOLENCE
R(
    "VIOLENCE_ABUSE",
    "VIOL_STRONG",
    avoid="MEDIA|FILMY|TECH|SALE_MKT",
    trade="msg",
    name="strong violence word",
)
R(
    "VIOLENCE_ABUSE",
    "HITV",
    ["ME|VICTIM|US|CHILD|RELATIVE|PRON|GROUP|PERSON"],
    win=6,
    avoid="IDIOM_H|SALE_MKT|TECH",
    trade="msg",
    name="hits a person (wide)",
)
R(
    "VIOLENCE_ABUSE",
    "JALATA",
    ["ME|VICTIM|US|PRON|PERSON|CHILD|RELATIVE|FAMILYACT"],
    win=6,
    avoid="LIGHT_ON|FOODY|MONEYY",
    trade="msg",
    name="burns a person",
)
R(
    "VIOLENCE_ABUSE",
    "LOCKUP",
    ["ME|US", "CLOSEDPLACE|INSIDE|RAKHA"],
    win=6,
    avoid="SCHOOLY|TRADE",
    name="locked me in",
)
R(
    "VIOLENCE_ABUSE",
    "VIOL_OBJ",
    ["HITV|GROUP|PRON|ME|BREAKV|ENTER|US|PERSON|CHILD|RELATIVE|HIT"],
    win=6,
    avoid="TRADE|SALE_MKT|MEDIA|TECH",
    trade="msg",
    name="weapon object used on someone",
)
R(
    "VIOLENCE_ABUSE",
    "DOORV",
    ["BREAKV", "NIGHTW|KOI2|PRON|DANGER"],
    win=6,
    avoid="TRADE",
    trade="msg",
    name="someone breaking a door",
)
R("VIOLENCE_ABUSE", "SHATTER", ["BREAKV", "GROUP"], win=8, trade="msg", name="mob smashing")
R(
    "VIOLENCE_ABUSE",
    "GROUP",
    ["BREAKV|VIOL_STRONG|HITV", "PLACE_OBJ|PLACE_BIG|SHATTER|PERSON"],
    win=8,
    avoid="TRADE|SALE_MKT|MEDIA",
    trade="msg",
    name="a group attacks a place or person",
)
R(
    "VIOLENCE_ABUSE",
    "ENTER",
    ["GROUP|THIEF|ARMED"],
    win=6,
    avoid="TRADE",
    trade="msg",
    name="a group forces its way in",
)
R(
    "VIOLENCE_ABUSE",
    "STORM",
    ["GROUP|ARMED|THIEF|PLACE_OBJ"],
    win=6,
    avoid="TRADE",
    trade="msg",
    name="stormed",
)
R(
    "VIOLENCE_ABUSE",
    "WEAPON",
    ["PRON|ME|US|GROUP", "HOLDUP|CASHTAKE|ENTER|WENTER|ME"],
    win=8,
    avoid="TRADE",
    trade="msg",
    name="weapon used on someone",
)
R("VIOLENCE_ABUSE", "DEMANDMONEY", ["WEAPON|ARMED|GROUP"], win=8, name="armed men demand money")
# SELF-HARM
R(
    "SELF_HARM",
    "JUMPV",
    ["HIGHPLACE|SH_ROOF"],
    win=6,
    avoid="BUNGEE|TRADE|MEDIA",
    name="jump from a height",
)
R("SELF_HARM", "ROPE", ["HANGW", "SELFW|ME|WANT"], win=6, name="rope to hang")
R("SELF_HARM", "HOARD", ["MEDS", "TONIGHT|SAB|QTY"], win=8, name="pills saved for tonight")
R("SELF_HARM", "MEDS", ["HOARD", "TONIGHT"], win=8, name="pills saved (alt)")
# CHILD
R(
    "CHILD_SAFEGUARDING",
    "CHILD",
    ["HITV|JALATA|FOODLESS|LOCKUP|SEXUAL_V|TOUCHV|VIOL_STRONG"],
    win=10,
    avoid="IDIOM_H|TRADE|MEDIA",
    name="child harmed (wide)",
)
R(
    "CHILD_SAFEGUARDING",
    "CHILD",
    ["ADULT|FAMILYACT|PRON|RELATIVE", "NIGHTW", "INSIDE|CLOSEDPLACE"],
    win=10,
    name="adult enters a child's room at night",
)
R("CHILD_SAFEGUARDING", "CHILD", ["SERVANT"], win=8, name="child kept as a servant")
R("CHILD_SAFEGUARDING", "CHILD", ["FORCEDM"], win=8, name="child forced into marriage")
R("CHILD_SAFEGUARDING", "FORCEDM", ["CHILD|FEMALE_V"], win=8, name="forced marriage of a girl")
R(
    "CHILD_SAFEGUARDING",
    "CHILD",
    ["KISSV|NAKED"],
    win=8,
    name="kissing or showing naked pictures to a child",
)
R("CHILD_SAFEGUARDING", "KISSV", ["CHILD|FEMALE_V"], win=8, name="kissing a child")
R("CHILD_SAFEGUARDING", "NAKED", ["CHILD|FEMALE_V"], win=8, name="naked pictures near a child")
# KIDNAP / ROBBERY
R(
    "KIDNAP_ROBBERY",
    "STRANGER",
    ["CHILD", "CARV|LURE"],
    win=10,
    kind="SAFEGUARDING",
    name="stranger takes a child in a car",
)
R("KIDNAP_ROBBERY", "PAYORELSE", ["RELATIVE|CHILD|KEPT"], win=10, name="pay or else for a person")
R(
    "KIDNAP_ROBBERY",
    "KEPT",
    ["RELATIVE|CHILD", "PAYORELSE|DEMANDMONEY|MONEYN|MONEYASK"],
    win=10,
    name="they have my relative and want money",
)
R("KIDNAP_ROBBERY", "KEPT", ["RELATIVE|CHILD"], win=4, name="they are holding my relative")
R(
    "KIDNAP_ROBBERY",
    "ARMED",
    ["CASHTAKE|HOLDUP"],
    win=10,
    avoid="SALE_MKT|TRADE",
    name="armed men take money",
)
R(
    "KIDNAP_ROBBERY",
    "GROUP",
    ["HOLDUP", "CASHTAKE|PLACE_OBJ|ME|VICTIM"],
    win=10,
    avoid="SALE_MKT",
    trade="msg",
    name="a group robs",
)
R(
    "KIDNAP_ROBBERY",
    "THIEF",
    ["CASHTAKE|HOLDUP|TIEV|CARV"],
    win=10,
    avoid="SALE_MKT|TRADE",
    trade="msg",
    name="robbers take money",
)
R(
    "KIDNAP_ROBBERY",
    "TIEV",
    ["US|ME|GUARD|RELATIVE|PERSON|THIEF|GROUP|ARMED"],
    win=8,
    avoid="TRADE|SALE_MKT",
    trade="msg",
    name="people being tied up",
)
R("KIDNAP_ROBBERY", "RELEASE", ["MONEYASK|MONEYN|DEMANDMONEY"], win=8, name="release for money")
R(
    "KIDNAP_ROBBERY",
    "DEMANDMONEY",
    ["RELATIVE|CHILD"],
    win=10,
    kind="SAFEGUARDING",
    name="money demanded for a relative",
)
R(
    "KIDNAP_ROBBERY",
    "HOLDUP",
    ["ME|US|VICTIM|PERSON|GROUP|ARMED|WEAPON|PLACE_OBJ"],
    win=8,
    avoid="SALE_MKT|MEDIA|TRADE|TECH",
    trade="msg",
    name="hold-up",
)
# hedged: a doubtful report of any strong event is never silent
R(
    "MEDICAL_RESCUE",
    "UNSURE",
    ["EVENT"],
    win=8,
    avoid="TECH|MEDIA|GUARD",
    trade="msg",
    name="hedged report of an emergency",
)

# wave 4b rules
R("FIRE_SMOKE", "FIRE_N", ["PROG"], win=4, trade="msg", name="smoke or fire and a progressive verb")
R("VIOLENCE_ABUSE", "ACID", ["THROWV"], win=5, avoid="TRADE", name="throwing acid")
R("POISONING", "KEEDE|TOXIC", ["COUGH"], win=6, trade="msg", name="chemical fumes and coughing")
R("CHILD_SAFEGUARDING", "FORCEDM", avoid="MEDIA", trade="msg", name="forced or early marriage")
R("CHILD_SAFEGUARDING", "CHILD", ["SNEAK", "NIGHTW"], win=10, name="adult sneaks in at night")

# wave 4c rules
R(
    "MEDICAL_RESCUE",
    "HARM_MED",
    ["PERSON|CHILD|RELATIVE|PRON|BODY_ALL|ME|PERSON"],
    win=8,
    avoid="BIZ|TECH|FILMY|MEDIA",
    trade="msg",
    name="harm word and a person",
)
R(
    "POISONING",
    "HARM_POIS",
    ["PERSON|CHILD|RELATIVE|PRON|ME|VOMIT|INGEST_ANY|INGEST_DONE|FAMILYALL|GROUP"],
    win=8,
    avoid="TECH|FILMY|MEDIA",
    trade="msg",
    name="poison bag and a person or ingestion",
)
R(
    "POISONING",
    "VOMIT",
    ["HARM_POIS|FOODW|FAMILYALL"],
    win=10,
    trade="msg",
    name="vomiting after food",
)
R(
    "POISONING",
    "HEATER",
    ["NOMOVE|HARM_MED|CLOSEDROOM"],
    win=10,
    trade="msg",
    name="heater and a person down",
)
R(
    "POISONING",
    "MEDS",
    ["INGEST_ANY|INGEST_P|INGEST_DONE", "QTY"],
    win=8,
    trade="msg",
    name="medicine in quantity swallowed",
)
R(
    "VIOLENCE_ABUSE",
    "PETROL",
    ["POUR|LIGHTERW"],
    win=8,
    avoid="TRADE",
    trade="msg",
    name="petrol poured",
)
R(
    "VIOLENCE_ABUSE",
    "BOMBW",
    avoid="MEDIA|SALE_MKT|TRADE|FILMY|TECH",
    trade="msg",
    name="bomb or grenade",
)
R("VIOLENCE_ABUSE", "THROAT", ["HANDS|PRESS"], win=6, trade="msg", name="hands on a throat")
R(
    "VIOLENCE_ABUSE",
    "DRAGV",
    ["PERSON|CHILD|RELATIVE|FEMALE_V|ME|PRON"],
    win=8,
    avoid="TRADE|TECH|MEDIA",
    trade="msg",
    name="dragging a person",
)
R(
    "VIOLENCE_ABUSE",
    "VIOL_OBJ",
    ["BRICKTHROW|PERSON|GROUP"],
    win=6,
    avoid="TRADE|SALE_MKT|MEDIA|TECH",
    trade="msg",
    name="objects thrown or used on people",
)
R(
    "VIOLENCE_ABUSE",
    "HITV",
    ["VIOL_OBJ|PERSON|GROUP"],
    win=6,
    avoid="IDIOM_H|SALE_MKT|TECH|TRADE",
    trade="msg",
    name="hitting people (wide)",
)
R(
    "SELF_HARM",
    "VEIN",
    ["CUTV"],
    win=4,
    avoid="TRADE|MEDIA",
    trade="msg",
    name="cutting a vein or wrist",
)
R("SELF_HARM", "WILLW", ["WRITEV", "DEPART"], win=8, name="wrote a will and will not be here")
R(
    "SELF_HARM",
    "MEDS",
    ["INGEST_P|INGEST_ANY|INGEST_DONE", "QTY", "SELFW|ME|WANT|TONIGHT"],
    win=8,
    name="whole bottle of sleeping pills taken (self)",
)
R(
    "CHILD_SAFEGUARDING",
    "STRIPV",
    ["CHILD|PERSON"],
    win=8,
    avoid="TRADE|MEDIA",
    name="children made to strip",
)
R("CHILD_SAFEGUARDING", "CHAIN", ["CHILD"], win=8, avoid="TRADE", name="child chained")
R(
    "CHILD_SAFEGUARDING",
    "ABUSEMARK",
    ["CHILD"],
    win=10,
    avoid="TRADE",
    name="marks of abuse on a child",
)
R(
    "CHILD_SAFEGUARDING",
    "SEXUAL_V",
    ["CHILD|PERSON"],
    win=10,
    avoid="TRADE|MEDIA",
    name="touching or bed (wide)",
)
R(
    "KIDNAP_ROBBERY",
    "ESCAPEV",
    ["BAGMOB|CASHTAKE|GROUP|ARMED"],
    win=10,
    avoid="SALE_MKT",
    trade="msg",
    name="ran away with goods",
)
R(
    "KIDNAP_ROBBERY",
    "DOORV",
    ["BREAKV|FORCEDV", "INSIDE|NIGHTW|KOI2|PRON|DANGER"],
    win=8,
    avoid="TRADE",
    trade="msg",
    name="forced entry",
)
R("KIDNAP_ROBBERY", "KEPT", ["RELATIVE|CHILD"], win=6, name="they have my relative (wide)")
R(
    "KIDNAP_ROBBERY",
    "ROB_STRONG",
    ["BAGMOB|PERSON|ME|PRON|GROUP"],
    win=8,
    avoid="SALE_MKT|TECH",
    trade="msg",
    name="snatched from a person",
)

# wave 4d rules
R(
    "MEDICAL_RESCUE",
    "TOUCHV",
    ["MACHINE|PLACE_OBJ|ELEC_N|WIRE", "SHAKE|CHIPAK|NOMOVE"],
    win=8,
    trade="msg",
    name="touched a machine and shaking or stuck",
)
R("MEDICAL_RESCUE", "CHIPAK", ["SHAKE"], win=6, name="stuck and shaking")
R(
    "MEDICAL_RESCUE",
    "BOIL",
    ["BODY_ALL|CHILD|PERSON"],
    win=8,
    avoid="TRADE|FILMY",
    trade="msg",
    name="boiling liquid on a person",
)
R("MEDICAL_RESCUE", "LIPS", ["COLORBLUE"], win=5, name="blue or purple lips")
R("MEDICAL_RESCUE", "DAMPHOOL", trade="msg", name="gasping")
R("MEDICAL_RESCUE", "GUNSHOT", trade="msg", name="shot")
R(
    "POISONING",
    "EDIBLE_RISK",
    ["INGEST_ANY", "SICK"],
    win=10,
    trade="msg",
    name="wild food and sickness",
)
R(
    "VIOLENCE_ABUSE",
    "WEAPON",
    ["THREAT_P"],
    win=10,
    avoid="TRADE",
    trade="msg",
    name="weapon and a threat",
)
R("VIOLENCE_ABUSE", "SMOTHER", avoid="TRADE|MEDIA|FILMY", trade="msg", name="smothering")
R(
    "CHILD_SAFEGUARDING",
    "VOYEUR",
    ["CHILD|FEMALE_V|BATHROOMW"],
    win=8,
    avoid="TRADE|MEDIA",
    name="recording a child or girl",
)
R("CHILD_SAFEGUARDING", "LAP", ["CHILD"], win=10, name="child made to sit on a lap")
R(
    "CHILD_SAFEGUARDING",
    "SOLDP",
    ["CHILD|FEMALE_V|RELATIVE"],
    win=8,
    avoid="TRADE",
    trade="msg",
    name="girl or relative being sold",
)
R(
    "KIDNAP_ROBBERY",
    "LOCKUP",
    ["CARV", "FEMALE_V|RELATIVE|CHILD|ME"],
    win=8,
    avoid="TRADE",
    name="locked in a car or taxi",
)
R(
    "SELF_HARM",
    "RAIL",
    ["WAITINGON"],
    win=8,
    avoid="TRADE|MEDIA",
    name="waiting on the railway track",
)

# wave 4e rules
R(
    "SELF_HARM",
    "PLANW",
    ["ENDW"],
    win=8,
    avoid="TRADE|WORKY|SALE_MKT|MEDIA",
    name="a plan to end it",
)
R(
    "CHILD_SAFEGUARDING",
    "CHILD",
    ["ALONEW", "ADULT|GUARD|FAMILYACT|PERSON|PRON"],
    win=12,
    avoid="TRADE|MEDIA",
    name="adult and a child alone (grooming)",
)
R(
    "CHILD_SAFEGUARDING",
    "CHILD",
    ["HITV|VIOL_OBJ|JALATA", "FOODLESS|LOCKUP|CHAIN|SERVANT|ABUSEMARK|VIOL_OBJ"],
    win=14,
    avoid="TRADE|MEDIA|IDIOM_H",
    name="child hit with neglect or restraint",
)
R(
    "CHILD_SAFEGUARDING",
    "CHILD",
    ["HITV|JALATA"],
    win=14,
    avoid="TRADE|MEDIA|IDIOM_H",
    name="child hit (long range)",
)
R(
    "KIDNAP_ROBBERY",
    "GRABV",
    ["CHILD|FEMALE_V|RELATIVE"],
    win=8,
    avoid="TRADE|SALE_MKT",
    trade="msg",
    name="grabbed a child or relative",
)
R(
    "KIDNAP_ROBBERY",
    "THIEF",
    ["CLIMB"],
    win=10,
    avoid="TRADE",
    trade="msg",
    name="thieves climbing in",
)
R(
    "KIDNAP_ROBBERY",
    "PAYORELSE",
    ["CASHTAKE|MONEYN|MONEYASK", "RELATIVE|CHILD"],
    win=12,
    name="money or else, for a relative (long range)",
)

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

_EVENT_TAGS = "GRABV|CLIMB|SMOTHER|GUNSHOT|DAMPHOOL|VOYEUR|LAP|SOLDP|EDIBLE_RISK|HARM_MED|HARM_POIS|PETROL|BOMBW|THROAT|DRAGV|VEIN|WILLW|STRIPV|ABUSEMARK|ESCAPEV|FIRE_N|BURN_V|BURN_AR|STRONG_TRAP|TOXIC|KEEDE|KHOON|KHOON2|BEHOSH|NOMOVE|DOOB_E|THREAT_P|VIOL_STRONG|SEXUAL_V|AGWA|HOSTAGE|RANSOM|GUNPOINT|SH_PHRASE|CHOKE_V|SWALLOW|CONVULSE|SPEECHLOSS|VEHICLE_HIT|JALATA|TIEV|KEPT"
for _t in _EVENT_TAGS.split("|"):
    _bit(_t)
_EVENT_MASK = _mask(_EVENT_TAGS)
_EV_BIT = _bit("EVENT")

_DANGER = _mask("DANGER")
_TRADE = _mask("TRADE")
_LIVE = _mask("LIVE")
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
        if (
            len(tok) > 3
            and "\u0621" <= tok[0] <= "\u064a"
            and tok[0] in "\u0648\u0641\u0633\u0628\u0644"
        ):
            m |= _LEX.get(tok[1:], 0)
        if len(tok) > 4 and tok.startswith("\u0627\u0644"):
            m |= _LEX.get(tok[2:], 0)
        if len(tok) > 4 and tok.startswith("\u0644\u0644"):  # la + al, as in "for the headache"
            m |= _LEX.get("\u0627\u0644" + tok[2:], 0) | _LEX.get(tok[2:], 0)
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
        if m & _EVENT_MASK:
            m |= _EV_BIT
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
    danger_anywhere = bool(doc.gor & (_DANGER | _LIVE))
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


W(
    "MEDIA_STRICT",
    "merchandise merch tshirt mug novel script poster banner campaign awareness movie film drama thriller book story helpline trailer screenplay documentary",
)
_MEDIA_STRICT = _mask("MEDIA_STRICT")
_VICTIMISH = _mask("DANGER|LIVE|PERSON|CHILD|RELATIVE|ME|VICTIM|INSIDE|PRON|US")


def media_only(text: str, trade: bool = True) -> bool:
    """True for a creative, campaign or trade statement (novel, poster, quote, rate ...) that names no person and has no live cue."""
    doc = _analyse(text)
    if doc is None:
        return False
    words = _MEDIA_STRICT | _mask("SALE_MKT") | (_TRADE if trade else 0)
    cues = _VICTIMISH | (
        _mask("AMBU|SUMMON|SANS|BREATHE|CALLV|NEGE|NEGB|HOSH|BEHOSH|KHOON|NOMOVE") if trade else 0
    )
    return bool(doc.gor & words) and not doc.gor & cues
