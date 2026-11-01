"""Whether a clause of the owner's text is the OWNER's own claim of a cause (L1, third audit): pure.

The default is NO. A cause is the owner's only when their own voice is marked, by an ALLOWLIST of
first-person epistemic markers ("I think", "I believe", "I am sure", "in my opinion", "mera khayal
hai", "mujhe lagta hai", "main manta hun", "مجھے لگتا ہے", "میرا خیال ہے", "أعتقد", "في رأيي",
"मुझे लगता है", "मेरा मानना है" ...), FOLLOWED in the same clause by the cause content, and only
when the clause has NONE of these anywhere:

* a communication, perception or reading verb or a source noun ("told", "heard", "read", "saw",
  "said", "wrote", "survey", "video", "group", "ChatGPT", "suna", "parha", "سنا", "قيل", "सुना" ...);
* attribution to anyone else or a generic source ("the staff think", "ka khayal hai", "ne kaha");
* pi's own words said back ("you asked ...");
* doubt, denial, a hedge or "it is fine" ("I don't think", "maybe", "nahi lagta", "the staff is
  fine", "ممكن", "شायद");
* sarcasm, a question or a conditional.

A bare declarative ("the rent is the problem", "rent hi masla hai") has no own-voice marker, so it
is NOT endorsed: pi asks the owner to confirm it (one question). A missed owner cause costs one
question; a wrong "owner said it" is the unsafe direction. A cause pi asked about and the owner's
very next message affirms is handled by `problem_fields` (`OwnerWords.asked`).
"""

import re

# The owner's own voice: a closed list of first-person epistemic markers.
OWN_MARKER = re.compile(
    r"\bi (?:really |truly |honestly |firmly |personally |do )?(?:think|believe|feel|know|reckon"
    r"|maintain)\b"
    r"|\bi(?:'m| am) (?:really |absolutely |quite |completely )?(?:sure|certain|convinced"
    r"|confident)\b"
    r"|\bi(?:'d| would) say\b|\bin my (?:view|opinion|experience|judge?ment|book)\b"
    r"|\bmy (?:view|opinion|belief|feeling|conviction|experience) is\b|\bto me,? "
    r"|\bmera khayal\b|\bmere khayal (?:mein|se)\b|\bmeri (?:raye|rai) (?:hai|mein)\b"
    r"|\bmere hisab se\b|\bmeri nazar mein\b"
    r"|\bmuj(?:he|hko|h ko) (?:to )?(?:lagta hai|yaqeen hai|pakka pata hai|pata hai)\b"
    r"|\bmain (?:yeh |ye )?(?:samajhta|samajhti|manta|manti|kehta|kehti|jaanta|jaanti|sochta"
    r"|sochti) (?:hun|hoon|hu)\b|\bmain (?:sure|pakka) (?:hun|hoon|hu)\b"
    r"|\bhum (?:maante|mante|samajhte|jaante) (?:hain|hein)\b|\b(?:humein|hamein) lagta hai\b"
    r"|\bmera (?:manna|yaqeen|tajurba)\b"
    r"|مجھے (?:لگتا ہے|یقین ہے|پتہ ہے|پتا ہے)|مجھ کو لگتا ہے|میرا (?:خیال|ماننا|یقین) ہے"
    r"|میرے (?:خیال میں|حساب سے)|میری رائے میں|میری نظر میں|ہمیں لگتا ہے"
    r"|میں (?:سمجھتا|سمجھتی|مانتا|مانتی|کہتا|کہتی|جانتا|جانتی) ہوں"
    r"|(?<![؀-ۿ])(?:أعتقد|اعتقد|أظن|اظن|أؤمن|اؤمن)(?![؀-ۿ])"
    r"|في رأيي|برأيي|من وجهة نظري|أرى أن|ارى ان|أشعر أن|اشعر ان|أعرف أن|اعرف ان"
    r"|أنا (?:متأكد|متاكد|واثق|مقتنع)"
    r"|मुझे (?:लगता है|यकीन है|पक्का पता है|पता है)|मेरा (?:मानना|विश्वास) है"
    r"|मेरे (?:हिसाब से|विचार में)|मेरी राय में|हमें लगता है|मैं निश्चित हूं"
    r"|मैं (?:मानता|मानती|समझता|समझती|कहता|कहती|जानता|जानती) (?:हूं|हूँ)"
)

# A communication, perception or reading verb, or a source of information, anywhere in the clause.
_SOURCE = re.compile(
    r"\b(?:told|tell|tells|telling|heard|hear|hears|hearing|read|reads|reading|saw|seen|see|sees"
    r"|watched|watching|said|says|saying|wrote|written|writes|informed|inform|pointed|points"
    r"|mentioned|mention|suggested|suggests|reported|report|reports|found|finds|showed|shows|show"
    r"|claimed|claim|learned|learnt|noticed|observed|advised|asked|ask|discussed|talked|"
    r"survey|article|video|group|post|review|reviews|news|newspaper|study|research|blog|website"
    r"|forum|thread|feedback|podcast|tv|radio|youtube|google|chatgpt|gpt|ai|whatsapp|facebook"
    r"|tiktok|instagram|rumou?rs?|gossip|expert|consultant)\b"
    r"|\b(?:suna|sunna|suni|sune|parha|padha|dekha|dekhi|kaha|kaho|bola|bataya|bata|likha|likhi"
    r"|bheja|farmaya|irshad|chhapa|chapa|mila|khabar|survey|akhbar|newspaper|chatgpt|gpt|google"
    r"|youtube|whatsapp|facebook|tiktok|instagram|ai|video|group|post|review|news)\b"
    r"|سنا|سنی|پڑھا|پڑھی|دیکھا|دیکھی|کہا|بولا|بتایا|لکھا|لکھی|بھیجا|فرمایا|ارشاد|چھپا|خبر|سروے"
    r"|آرٹیکل|ویڈیو|گروپ|پوسٹ|ریویو|اخبار|یوٹیوب|گوگل|واٹس ایپ|فیس بک|چیٹ جی پی ٹی"
    r"|سمعت|سمعنا|قرأت|قرات|قيل|رأيت|شاهدت|قال|كتب|كتبوا|أخبرني|اخبرني|أفاد|افاد|ذكر|نقل|نُقل"
    r"|وصلني|استبيان|مقال|فيديو|مجموعة|منشور|تقييم|أخبار|جريدة|صحيفة|يوتيوب|جوجل|واتساب|فيسبوك"
    r"|सुना|सुनी|पढ़ा|पढ़ी|देखा|देखी|कहा|बोला|बताया|लिखा|लिखी|भेजा|फरमाया|छापा|खबर|सर्वे"
    r"|आर्टिकल|वीडियो|ग्रुप|पोस्ट|रिव्यू|अखबार|यूट्यूब|गूगल|व्हाट्सएप|फेसबुक"
)

_FIRST_PRONOUN = frozenset("i we i'm i've we've i'd we'd i'll we'll".split())
_SAY_VERBS = frozenset(
    """say says said saying tell tells told telling think thinks thinking thought believe believes
    believed believing blame blames blamed blaming complain complains complained complaining claim
    claims claimed claiming mention mentions mentioned suggest suggests suggested insist insists
    insisted argue argues argued feel feels felt reckon reckons reckoned warn warns warned
    reported reports whined grumbled grumble grumbles show shows showed indicate indicates
    indicated prove proves proved state states stated assume assumes assumed""".split()
)
_WORD = re.compile(r"[\w']+")

# Attribution outside English (checked after the owner's own markers are taken out).
_ATTRIBUTION = re.compile(
    r"\bka khayal\b|\bki raye\b|\bki rai\b|\bke mutabiq\b|\bke mutabik\b"
    r"|\bne (?:kaha|bola|bataya)\b"
    r"|\bkeh(?:ta|te|ti)\b|\bkeh (?:raha|rahe|rahi)\b|\bbata(?:ta|te|ti)\b"
    r"|\bbata (?:raha|rahe|rahi)\b|\bbataya\b|\bshikayat\b|\bilzam\b|\bmante hain\b"
    r"|\bmanta hai\b|\bmanti hai\b|\bsamajhte hain\b|\bsamajhta hai\b|\bsamajhti hai\b"
    r"|\bsochta hai\b|\bsochti hai\b|\bsochte hain\b|\baccording to\b|\bas per\b"
    r"|\bper (?:the|my)\b|\bword is\b|\brumou?rs? has it\b|\bit(?:'s| is) said\b|\breportedly\b"
    r"|\ballegedly\b|\b(?:everybody|everyone) knows\b|\bko lagta\b|\bbol(?:ta|te|ti)\b"
    r"|\bbol (?:raha|rahe|rahi)\b|\bkehna hai\b|\bunka kehna\b"
    r"|\bin (?!my\b|our\b)\w+ (?:opinion|view)\b"
    r"|نے کہا|نے بتایا|نے بولا|کہتے ہیں|کہتا|کہتی|کہہ رہا|کہہ رہی|کہہ رہے|کا خیال|کی رائے"
    r"|کے مطابق|بتاتا|بتاتی|بتاتے|بتایا|شکایت|الزام|سمجھتے ہیں|سمجھتا ہے|سمجھتی ہے|مانتے|مانتا ہے"
    r"|سوچتا|سوچتے|کو لگتا|بولتا|بولتے|بولتی|کہنا ہے"
    r"|قالوا|قال|قالت|يقول|تقول|يقولون|يعتقد|تعتقد|يعتقدون|يظن|يظنون|يرى|يرون|أخبرني|اخبرني"
    r"|أخبرتني|يلوم|يشتكي|اشتكى|يشتكون|حسب|وفقا|بحسب|زعم|يزعم|اقترح|يقترح"
    r"|ने कहा|ने बताया|कहते हैं|कहता है|कहती है|कह रहा|कह रही|कह रहे|का मानना|का कहना"
    r"|के अनुसार|बताया|शिकायत|आरोप|मानते हैं|मानता है|सोचता है|सोचते हैं|समझते हैं"
    r"|को लगता|बोलता|बोलते|बोलती|कहना है"
)

# Doubt, denial, hedges, and "it is fine / it is elsewhere". Checked on the whole clause.
_DOUBT = re.compile(
    r"\bi (?:do not|don't|dont|doubt|can't|cannot) (?:really )?(?:think|believe|feel|say)\b"
    r"|\bi doubt\b|\bnot (?:really|sure|certain|convinced)\b|\bunsure\b|\bnothing to do with\b"
    r"|\bhas nothing to do\b|\blittle to do\b|\b(?:maybe|probably|perhaps|possibly) not\b"
    r"|\bhardly\b|\bno way\b|\bfar from\b|\bnot the case\b|\bcan't say\b|\bcannot say\b"
    r"|\bwouldn't say\b|\bdon't know\b|\bdunno\b|\bwho knows\b|\bmaybe\b|\bperhaps\b|\bpossibly\b"
    r"|\bprobably\b|\bmight\b|\bcould be\b|\bi guess\b|\bkind of\b|\bsort of\b|\bsupposedly\b"
    r"|\bseems?\b|\bapparently\b|\bhmm+\b|\bnot a factor\b|\bor something\b|\bsomething like\b"
    r"|\bnot the (?:problem|issue|reason|cause)\b|\bnot that\b|\bnot an issue\b|\bno issue\b"
    r"|\bno problem with\b|\bnothing wrong\b|\belsewhere\b|\bsomething else\b|\bforget\b"
    r"|\b(?:is|are|was|were|has been|have been) (?:fine|ok|okay|good|great|alright)\b"
    r"|\bworks fine\b|\bnot (?:the|an?) (?:main|real|actual)\b"
    r"|\bnahi lagta\b|\bnahin lagta\b|\bnhi lagta\b|\blagta nahi\b|\bmasla nahi\b|\bmasla nahin\b"
    r"|\bshayad\b|\bshayid\b|\bho sakta\b|\bho skta\b|\bpata nahi\b|\byaqeen nahi\b"
    r"|\bkhayal nahi\b|\bkoi taluq nahi\b|\blena dena nahi\b|\bkuch nahi lena\b"
    r"|\bmasle ki baat nahi\b|\btheek hai\b|\bthik hai\b|\btheek\b|\bkahin aur\b|\bkahi aur\b"
    r"|\bkoi masla nahi\b|\bya kuch\b"
    r"|مسئلہ نہیں|نہیں لگتا|لگتا نہیں|شاید|ہو سکتا ہے|پتہ نہیں|پتا نہیں|یقین نہیں|کوئی تعلق نہیں"
    r"|لینا دینا نہیں|ٹھیک ہے|کہیں اور|وجہ نہیں"
    r"|لا أعتقد|لا اعتقد|لا أظن|لا اظن|ما أعتقد|ما اعتقد|ما أظن|ما اظن|لست متأكد|لست متاكد"
    r"|ربما|قد يكون|لا علاقة|لا أدري|لا ادري|أشك|اشك|ممكن|يمكن|احتمال|على الأرجح|الظاهر"
    r"|مش متأكد|مو متأكد|مكان آخر|شيء آخر|أمر آخر|جيد|بخير|ليس هو|ليست هي|ليس هذا"
    r"|नहीं लगता|लगता नहीं|शायद|हो सकता है|पता नहीं|यकीन नहीं|कोई संबंध नहीं|समस्या नहीं"
    r"|लेना देना नहीं|ठीक है|कहीं और|वजह नहीं"
)

# pi's own words said back to it
_ECHO = re.compile(
    r"\byou(?:'re| are| were)? (?:asked|asking|mentioned|mentioning|said|saying|suggested|"
    r"suggesting|wondered|wondering|wrote|raised|brought up|claimed|claiming|telling)\b"
    r"|\byour (?:question|suggestion)\b|\baap ne (?:poocha|pucha|kaha|bataya)\b|\baapne\b"
    r"|\baap keh rahe\b|\btum ne\b|\btumne\b|آپ نے|آپ کہہ رہے|أنت قلت|انت قلت|سألت|سؤالك"
    r"|ذكرت لي|قلت لي|هل تقصد|आपने|आप कह रहे|तुमने"
)

_SARCASM = re.compile(
    r"\b(?:oh|yeah|yea|ya) (?:sure|right|yes)\b|\bas if\b|\blike that(?:'s| is)\b|\bsure sure\b"
    r"|\bright\?\s*$|\bwhatever\b|\bha(?:ha)+\b|\blol\b|/s\s*$|\bhaan haan\b|\bwah wah\b"
    r"|\bjee haan jee haan\b|\bkya baat hai\b|\bbrilliant\b|\bclearly\b|\bgenius\b|\bwow\b"
    r"|\bwhat a discovery\b|\bof course\b|\bobviously\b|\bbilkul\b"
    r"|ہاں ہاں|واہ واہ|واہ جی|ارے واہ|طبعا طبعا|أكيد أكيد|يا سلام|हां हां|वाह वाह|वाह जी"
)

_QUESTION_START = re.compile(
    r"^\s*(?:are|is|do|does|did|can|could|will|would|why|kya|کیا|هل|क्या)(?:\s|\b)"
)


def _tokens(said: str) -> list[str]:
    return _WORD.findall(said)


def attributed(said: str) -> bool:
    """Someone else, or a generic source, says or thinks it (the owner's own markers are not)."""
    scrubbed = OWN_MARKER.sub(" ", said)
    if _ATTRIBUTION.search(scrubbed):
        return True
    tokens = _tokens(scrubbed)
    for at, token in enumerate(tokens):
        if token in _SAY_VERBS and not _FIRST_PRONOUN & set(tokens[max(0, at - 3) : at]):
            return True
    return False


def doubtful(said: str) -> bool:
    return _DOUBT.search(said) is not None


def sarcastic(said: str) -> bool:
    return _SARCASM.search(said) is not None


def echoes_pi(said: str) -> bool:
    return _ECHO.search(said) is not None


def question_start(said: str) -> bool:
    return _QUESTION_START.search(said) is not None


def claim_tail(said: str, is_question: bool = False, hypothetical: bool = False) -> str | None:
    """The part of the (squashed) clause AFTER the owner's own-voice marker when the clause is the
    owner's own claim; None otherwise (the default). The cause content must be in that tail."""
    if is_question or hypothetical or question_start(said):
        return None
    if attributed(said) or doubtful(said) or sarcastic(said) or echoes_pi(said):
        return None
    if _SOURCE.search(said):
        return None
    marker = OWN_MARKER.search(said)
    if marker is None:
        return None
    tail = said[marker.end() :].strip()
    return tail if re.search(r"\w", tail) else None


def owner_claim(said: str, is_question: bool = False, hypothetical: bool = False) -> bool:
    """Whether the (squashed) clause is the owner's own marked claim."""
    return claim_tail(said, is_question, hypothetical) is not None
