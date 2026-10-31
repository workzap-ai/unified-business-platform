"""Whether a clause of the owner's text is the OWNER's own claim (L1 re-audit): pure, no database.

A cause is the owner's only when they said it themselves, plainly. The default is NO: a clause
endorses only when none of these broad markers is in it, in English, Roman Urdu, Urdu, Arabic and
Hindi:

* attribution to anyone else or to a generic source ("the staff think", "customers say", "he told
  me", "ka khayal hai", "ne kaha", "کہتے ہیں", "قالوا", "कहते हैं"); the owner's own "I think",
  "mera khayal hai", "مجھے لگتا", "أعتقد", "मुझे लगता है" are the owner's claim and are not
  attribution;
* pi's own words said back ("you asked whether ...", "aap ne poocha");
* doubt, denial and hedges ("I don't think", "not sure", "nothing to do with it", "maybe",
  "nahi lagta", "masla nahi", "نہیں لگتا", "لا أظن", "नहीं लगता");
* sarcasm ("oh sure", "yeah right", "as if", "like that's the real reason");
* a question or a conditional.

A missed owner cause costs one more question; a wrong "owner said it" is the unsafe direction, so
every list is meant to be broad. A bare declarative clause with none of the markers endorses.
"""

import re

# The owner's own claim phrases (never read as attribution).
FIRST_CLAIM = re.compile(
    r"\bi (?:really |do )?(?:think|believe|feel|reckon)\b|\bin my (?:view|opinion)\b"
    r"|\bi(?:'d| would) say\b|\bi(?:'m| am) (?:convinced|certain|sure)\b|\bi say\b"
    r"|\bmera khayal\b|\bmeri raye\b|\bmeri rai\b|\bmujhe lagta\b|\bmain (?:yeh )?"
    r"(?:samajhta|samajhti|manta|manti|sochta|sochti)\b|\bhumein lagta\b|\bhamein lagta\b"
    r"|\bmera manna\b|\bmera yaqeen\b|\bmujh ?ko lagta\b|\b(?:hum|ham) ?ko lagta\b"
    r"|مجھ کو لگتا|मुझ ?को लगता|हमको लगता"
    r"|میرا خیال|میرے خیال|میری رائے|مجھے لگتا|میں سمجھتا|میں سمجھتی|ہمیں لگتا|میں مانتا|میں مانتی"
    r"|أعتقد|اعتقد|أظن|اظن|في رأيي|برأيي|أرى|ارى|أشعر|اشعر|أؤمن|اؤمن"
    r"|मेरा मानना|मेरे विचार|मुझे लगता|मैं मानता|मैं मानती|मैं समझता|मैं समझती|हमें लगता"
)

_FIRST_PRONOUN = frozenset("i we i'm i've we've i'd we'd i'll we'll".split())
_SAY_VERBS = frozenset(
    """say says said saying tell tells told telling think thinks thinking thought believe believes
    believed believing blame blames blamed blaming complain complains complained complaining claim
    claims claimed claiming mention mentions mentioned suggest suggests suggested insist insists
    insisted argue argues argued feel feels felt reckon reckons reckoned warn warns warned
    reported reports whined grumbled grumble grumbles show shows showed indicate indicates
    indicated prove proves proved state states stated""".split()
)
_WORD = re.compile(r"[\w']+")

# Attribution outside English (checked after the owner's own claim phrases are taken out).
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

# Doubt, denial and hedges. Checked on the whole clause.
_DOUBT = re.compile(
    r"\bi (?:do not|don't|dont|doubt|can't|cannot) (?:really )?(?:think|believe|feel|say)\b"
    r"|\bi doubt\b|\bnot (?:really|sure|certain|convinced)\b|\bunsure\b|\bnothing to do with\b"
    r"|\bhas nothing to do\b|\b(?:maybe|probably|perhaps|possibly) not\b|\bhardly\b|\bno way\b"
    r"|\bfar from\b|\bnot the case\b|\bcan't say\b|\bcannot say\b|\bwouldn't say\b|\bdon't know\b"
    r"|\bdunno\b|\bwho knows\b|\bmaybe\b|\bperhaps\b|\bpossibly\b|\bprobably\b|\bmight\b"
    r"|\bcould be\b|\bi guess\b|\bkind of\b|\bsort of\b|\bsupposedly\b|\bseems?\b|\bapparently\b"
    r"|\bhmm+\b|\bnot a factor\b|\bnot the (?:problem|issue|reason|cause)\b"
    r"|\bnahi lagta\b|\bnahin lagta\b|\bnhi lagta\b|\bmasla nahi\b|\bmasla nahin\b|\bshayad\b"
    r"|\bho sakta hai\b|\bpata nahi\b|\byaqeen nahi\b|\bkhayal nahi\b|\bkoi taluq nahi\b"
    r"|\blena dena nahi\b|\bkuch nahi lena\b|\bmasle ki baat nahi\b"
    r"|مسئلہ نہیں|نہیں لگتا|شاید|ہو سکتا ہے|پتہ نہیں|پتا نہیں|یقین نہیں|کوئی تعلق نہیں"
    r"|لینا دینا نہیں"
    r"|لا أعتقد|لا اعتقد|لا أظن|لا اظن|لست متأكد|لست متاكد|ربما|قد يكون|لا علاقة|لا أدري"
    r"|لا ادري|أشك|اشك"
    r"|नहीं लगता|शायद|हो सकता है|पता नहीं|यकीन नहीं|कोई संबंध नहीं|समस्या नहीं"
    r"|लेना देना नहीं"
)

# pi's own words said back to it
_ECHO = re.compile(
    r"\byou(?:'re| are| were)? (?:asked|asking|mentioned|mentioning|said|saying|suggested|"
    r"suggesting|wondered|wondering|wrote|raised|brought up|claimed|claiming|telling)\b"
    r"|\byour (?:question|suggestion)\b|\baap ne (?:poocha|pucha|kaha|bataya)\b|\baapne\b"
    r"|\baap keh rahe\b|آپ نے|آپ کہہ رہے|سألت|سؤالك|ذكرت لي|قلت لي|هل تقصد|आपने|आप कह रहे"
)

_SARCASM = re.compile(
    r"\b(?:oh|yeah|yea|ya) (?:sure|right|yes)\b|\bas if\b|\blike that(?:'s| is)\b|\bsure sure\b"
    r"|\bright\?\s*$|\bwhatever\b|\bha(?:ha)+\b|\blol\b|/s\s*$|\bhaan haan\b|\bwah wah\b"
    r"|\bjee haan jee haan\b|\bkya baat hai\b|\bbrilliant\b|\bclearly\b|\bgenius\b"
    r"|ہاں ہاں|واہ واہ|طبعا طبعا|أكيد أكيد|हां हां|वाह वाह"
)

_QUESTION_START = re.compile(
    r"^\s*(?:are|is|do|does|did|can|could|will|would|why|kya|کیا|هل|क्या)(?:\s|\b)"
)


def _tokens(said: str) -> list[str]:
    return _WORD.findall(said)


def attributed(said: str) -> bool:
    """Someone else, or a generic source, says or thinks it (the owner's own "I think" is not)."""
    scrubbed = FIRST_CLAIM.sub(" ", said)
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


def owner_claim(said: str, is_question: bool = False, hypothetical: bool = False) -> bool:
    """Whether the (squashed) clause can be the owner's own plain claim."""
    if is_question or hypothetical or question_start(said):
        return False
    return not (attributed(said) or doubtful(said) or sarcastic(said) or echoes_pi(said))
