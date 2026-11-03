# ruff: noqa: E501  (one fixed line per row reads better than wrapped text)
"""The safety lines of safety.py in Urdu script (spec 2.5 and G7: a person who writes Urdu script is
answered in Urdu script, one script per chat), and the wording of the three newer personal-data kinds
(health, pay or discipline of a named person, a forwarded customer complaint) in every language.

Every line is polite (aap forms), has no gendered first-person verb (the same rule the reply linter
applies to Roman Urdu, constitution.roman_urdu_tone, is applied to every fixed line by
test_pi_fixed_lines_urdu_script), asks at most one question and that one last, and says nothing
about price or payment beyond what the English line already says. Native-speaker review is still
wanted before wide use.

`install` is called once at the end of safety.py with that module's globals, so this file never
imports safety (no cycle)."""

from typing import Any


def install(g: dict[str, Any]) -> None:
    Emergency, Pii, Advice = g["Emergency"], g["Pii"], g["Advice"]
    Identity, Boundary, Enquiry, Nori = g["Identity"], g["Boundary"], g["Enquiry"], g["Nori"]

    g["EMERGENCY_TEXT"]["ur"] = {
        Emergency.FIRE: "ہنگامی صورتحال میں مدد کرنا میرے بس میں نہیں۔ براہِ مہربانی ابھی {fire} پر کال کریں۔",
        Emergency.MEDICAL: "ہنگامی صورتحال میں مدد کرنا میرے بس میں نہیں۔ براہِ مہربانی ایمبولینس کے لیے ابھی {ambulance} پر کال کریں۔",
        Emergency.VIOLENCE: "ہنگامی صورتحال میں مدد کرنا میرے بس میں نہیں۔ براہِ مہربانی ابھی {police} پر کال کریں اور محفوظ جگہ پر چلے جائیں۔",
        Emergency.GENERIC: "ہنگامی صورتحال میں مدد کرنا میرے بس میں نہیں۔ براہِ مہربانی ابھی {police} پر کال کریں۔",
        Emergency.SAFEGUARDING: (
            "مجھے افسوس ہے، اس کے لیے انسان کی ضرورت ہے، یہ میرے بس میں نہیں۔ اگر کسی کو ابھی خطرہ ہے "
            "تو {police} پر کال کریں۔ ورنہ آج ہی مناسب ادارے سے بات کریں: اپنے سیفٹی گارڈنگ لیڈ یا "
            "چائلڈ پروٹیکشن سروس سے۔ میں نے یہ Workzap کی ٹیم کو بھیج دیا ہے۔ جب آپ بتائیں کہ معاملہ "
            "سنبھال لیا گیا ہے، تب کاروبار کی بات کریں گے۔"
        ),
        Emergency.SELF_HARM: (
            "مجھے افسوس ہے کہ حالات اتنے بھاری ہیں۔ میں ایک مصنوعی ذہانت ہوں اور اس میں مدد کرنا میرے "
            "بس میں نہیں۔ کسی بھروسے کے انسان سے بات کریں، یا خطرے میں ہوں تو {police} پر کال کریں۔ "
            "کاروبار کی طرف میں جب آپ چاہیں حاضر ہوں۔"
        ),
    }

    own_pii = {
        Pii.CARD: "براہِ مہربانی یہاں کارڈ نمبر نہ بھیجیں۔ مجھے ان کی ضرورت نہیں، اور ادائیگی اس چیٹ میں کبھی نہیں ہوتی۔ میں نے اسے اپنے نوٹس سے نکال دیا ہے۔",
        Pii.SECRET: "براہِ مہربانی یہاں پاس ورڈ، کوڈ یا پن نہ بھیجیں۔ مجھے ان کی ضرورت نہیں۔ میں نے اسے اپنے نوٹس سے نکال دیا ہے۔",
        Pii.ID: "براہِ مہربانی یہاں شناختی نمبر نہ بھیجیں۔ مجھے ان کی ضرورت نہیں۔ میں نے اسے اپنے نوٹس سے نکال دیا ہے۔",
        Pii.ACCOUNT: "براہِ مہربانی یہاں بینک اکاؤنٹ نمبر نہ بھیجیں۔ مجھے ان کی ضرورت نہیں، بینک کی تفصیل صرف منظور شدہ کوٹیشن پر آتی ہے۔ میں نے اسے اپنے نوٹس سے نکال دیا ہے۔",
        Pii.CONTACT: "مجھے دوسروں کی رابطہ تفصیل کی ضرورت نہیں۔ وہ چاہیں تو مجھے براہِ راست پیغام کر سکتے ہیں۔ میں نے اسے اپنے نوٹس سے نکال دیا ہے۔",
        Pii.CHILD: "براہِ مہربانی یہاں بچوں کے نام یا نمبر نہ بھیجیں۔ مجھے صرف کاروبار کا مسئلہ چاہیے، مثلاً نتائج کا حساب کیسے رکھا جاتا ہے۔ میں نے اسے اپنے نوٹس سے نکال دیا ہے۔",
        Pii.NAME: "مجھے لوگوں کے نام نہیں، صرف ان کا کردار چاہیے، اس لیے میں نے صرف کردار نوٹ کیا ہے، مثلاً \"مریض\"۔",
    }
    new_pii = {
        "en": {
            Pii.HEALTH: "Please don't share people's health details here. I only need the business problem, for example how absences are handled. I've left that out of my notes.",
            Pii.PAY: "Please don't share a named person's pay or discipline here. I only need the business problem, for example how pay or warnings are tracked. I've left that out of my notes.",
            Pii.FORWARDED: "I've kept the pattern in that complaint, not the customer's name or details.",
        },
        "roman_ur": {
            Pii.HEALTH: "Meherbani karke yahan logon ki sehat ki tafseel na bhejein. Mujhe sirf business ka masla chahiye, masalan chhuttiyan kaise sambhali jati hain. Maine ise apne notes se nikaal diya hai.",
            Pii.PAY: "Meherbani karke yahan kisi naam wale shakhs ki tankhwah ya anzibati karwai na bhejein. Mujhe sirf business ka masla chahiye, masalan tankhwah ya warning ka record kaise rakha jata hai. Maine ise apne notes se nikaal diya hai.",
            Pii.FORWARDED: "Maine us shikayat ka rujhan rakha hai, customer ka naam ya tafseel nahi.",
        },
        "ar": {
            Pii.HEALTH: "يرجى عدم مشاركة التفاصيل الصحية للأشخاص هنا. أحتاج فقط إلى مشكلة العمل، مثلًا كيفية التعامل مع الغيابات. لقد أبقيتها خارج ملاحظاتي.",
            Pii.PAY: "يرجى عدم مشاركة راتب شخص بعينه أو إجراءاته التأديبية هنا. أحتاج فقط إلى مشكلة العمل، مثلًا كيفية تتبع الرواتب أو الإنذارات. لقد أبقيتها خارج ملاحظاتي.",
            Pii.FORWARDED: "احتفظت بنمط الشكوى وليس باسم العميل أو تفاصيله.",
        },
        "ur": {
            Pii.HEALTH: "براہِ مہربانی یہاں لوگوں کی صحت کی تفصیل نہ بھیجیں۔ مجھے صرف کاروبار کا مسئلہ چاہیے، مثلاً چھٹیاں کیسے سنبھالی جاتی ہیں۔ میں نے اسے اپنے نوٹس سے نکال دیا ہے۔",
            Pii.PAY: "براہِ مہربانی یہاں کسی نامزد شخص کی تنخواہ یا تادیبی کارروائی نہ بھیجیں۔ مجھے صرف کاروبار کا مسئلہ چاہیے، مثلاً تنخواہ یا وارننگ کا ریکارڈ کیسے رکھا جاتا ہے۔ میں نے اسے اپنے نوٹس سے نکال دیا ہے۔",
            Pii.FORWARDED: "میں نے اس شکایت کا رجحان رکھا ہے، گاہک کا نام یا تفصیل نہیں۔",
        },
    }
    g["PII_TEXT"]["ur"] = own_pii
    for language, lines in new_pii.items():
        g["PII_TEXT"].setdefault(language, {}).update(lines)

    g["ADVICE_WHO"]["ur"] = {
        Advice.LEGAL: "وکیل",
        Advice.TAX: "اکاؤنٹنٹ",
        Advice.FINANCIAL: "مستند مالی مشیر",
        Advice.MEDICAL: "ڈاکٹر یا فارماسسٹ",
        Advice.VETERINARY: "جانوروں کا ڈاکٹر",
        Advice.ENGINEERING: "لائسنس یافتہ انجینئر",
        Advice.CHEMICAL: "لائسنس یافتہ ٹیکنیشن",
        Advice.AGRONOMY: "زرعی ماہر یا لائیو اسٹاک نیوٹریشنسٹ",
        Advice.IMMIGRATION: "وکیل یا لائسنس یافتہ امیگریشن کنسلٹنٹ",
        Advice.CUSTOMS: "کسٹمز بروکر یا تجارتی وکیل",
        Advice.RELIGIOUS: "مستند عالم",
        Advice.VEHICLE: "مستند مکینک",
        Advice.VALUATION: "لائسنس یافتہ ویلیوایٹر",
        Advice.FORMULATION: "مستند کیمسٹ",
    }
    g["ADVICE_WORD"]["ur"] = {
        Advice.LEGAL: "قانونی",
        Advice.TAX: "ٹیکس کا",
        Advice.FINANCIAL: "مالی",
        Advice.MEDICAL: "طبی",
        Advice.VETERINARY: "جانوروں کے علاج کا",
        Advice.ENGINEERING: "انجینئرنگ کا",
        Advice.CHEMICAL: "کیمیکل کے استعمال کا",
        Advice.AGRONOMY: "زرعی",
        Advice.IMMIGRATION: "امیگریشن کا",
        Advice.CUSTOMS: "کسٹمز کا",
        Advice.RELIGIOUS: "مذہبی",
        Advice.VEHICLE: "گاڑی کی حفاظت کا",
        Advice.VALUATION: "جائیداد کی قیمت کا",
        Advice.FORMULATION: "فارمولیشن کا",
    }
    g["ADVICE_TEXT"]["ur"] = (
        "{kind} مشورہ دینا میرے بس میں نہیں، اس کے لیے {who} صحیح شخص ہے۔ اسے آپ کے کاروبار کے ایک مسئلے کے طور پر نوٹ کیا جا سکتا ہے۔ کیا نوٹ کر لوں؟"
    )

    g["HANDBACK_TEXT"]["ur"] = "میں دوبارہ pi ہوں، Workzap کی مصنوعی ذہانت۔ آپ کہاں سے بات جاری رکھنا چاہیں گے؟"
    g["GREETING_TEXT"]["salam"]["ur"] = "وعلیکم السلام۔ آپ کا کاروبار کیا کام کرتا ہے؟"
    g["GREETING_TEXT"]["festival"]["ur"] = "آپ کو بھی عید مبارک۔ آپ کا کاروبار کیا کام کرتا ہے؟"
    g["OPT_OUT_TEXT"]["ur"] = "ٹھیک ہے۔ دوبارہ پیغام نہیں بھیجا جائے گا۔ کبھی بات کرنی ہو تو یہیں لکھ دیں۔"

    g["IDENTITY_TEXT"]["ur"] = {
        Identity.PERSON: "میں ایک مصنوعی ذہانت ہوں، انسان نہیں۔ میں pi ہوں، Workzap کی طرف سے۔",
        Identity.GENDER: "میں pi ہوں، Workzap کی مصنوعی ذہانت۔ میری کوئی جنس نہیں۔",
        Identity.SCAM: "جائز سوال ہے۔ میں Workzap کی مصنوعی ذہانت ہوں۔ یہاں کبھی ادائیگی، کارڈ نمبر یا پاس ورڈ نہیں مانگا جاتا، اور آپ پر کچھ خریدنا ضروری نہیں۔ مزید workzap.ai/pi/trust پر۔",
        Identity.META: "نہیں۔ مجھے Workzap نے بنایا ہے اور یہاں واٹس ایپ کے بزنس پلیٹ فارم پر چیٹ ہوتی ہے۔ مجھے واٹس ایپ یا میٹا نے نہیں بنایا، نہ وہ مجھے چلاتے ہیں، نہ اس کی تائید کرتے ہیں۔",
        Identity.MODEL: "میں pi ہوں، Workzap کی مصنوعی ذہانت۔ میں آپ کے کاروبار کے مسائل نوٹ اور ترتیب دینے کے لیے ہوں۔",
        Identity.RULES: "کام کا طریقہ یہ ہے: مسائل نوٹ اور ترتیب دیے جاتے ہیں۔ یہاں کبھی ادائیگی نہیں لی جاتی، اور کوٹیشن پر فیصلہ آپ کا ہوتا ہے۔ پوری تفصیل workzap.ai/pi/how-it-works پر ہے۔",
        Identity.COMPANY: "یہ سوال Workzap کی ٹیم تک پہنچایا جا سکتا ہے۔",
        Identity.OFFER: "Workzap مسائل ڈھونڈنے اور حل کرنے کا سافٹ ویئر بناتا ہے۔ یہاں کچھ بیچنا مقصد نہیں: آپ کے کاروبار کی رکاوٹ نوٹ کی جاتی ہے۔ آپ چاہیں تو Workzap پھر حل کی دستاویز بنا سکتا ہے۔ ابھی سب سے بڑا مسئلہ کیا ہے؟",
    }

    g["BOUNDARY_TEXT"]["ur"] = {
        Boundary.DELETION: "آپ کا ڈیٹا حذف کرنے کی درخواست میں نے Workzap کی ٹیم کو بھیج دی ہے۔ وہ یہیں تصدیق کریں گے، اور تب تک کچھ نیا نوٹ نہیں کیا جائے گا۔",
        Boundary.POLITICS: "سیاست اور رائے اس چیٹ کے دائرے سے باہر ہیں۔ میں آپ کے کاروبار کی رکاوٹ نوٹ کرنے کے لیے ہوں۔ ابھی سب سے بڑا مسئلہ کیا ہے؟",
        Boundary.COMPETITOR: "Workzap کا دوسری کمپنیوں سے موازنہ یہاں نہیں کیا جاتا۔ میں آپ کے کاروبار کی رکاوٹ نوٹ کرنے کے لیے ہوں۔ ابھی سب سے بڑا مسئلہ کیا ہے؟",
        Boundary.OUTCOME: "نتائج کا وعدہ نہیں کیا جا سکتا۔ مسئلہ نوٹ کیا جا سکتا ہے، اور Workzap بتا سکتا ہے کہ وہ کیا کرے گا۔ مسئلہ کیا ہے؟",
        Boundary.FRAUD: "جعلی انوائس یا آمدنی چھپانے میں مدد نہیں کی جا سکتی۔ اگر اصل انوائسز کا حساب رکھنا مشکل ہے تو اسے مسئلے کے طور پر نوٹ کیا جا سکتا ہے۔ کیا نوٹ کر لوں؟",
        Boundary.THIRD_PARTY: "کسی اور کی چیٹ شیئر نہیں کی جا سکتی۔ صرف وہ رکھا جاتا ہے جو آپ اس چیٹ میں بتاتے ہیں۔ کاروبار کے بارے میں کیا نوٹ کر لوں؟",
        Boundary.BANK_CHANGE: "اس چیٹ میں بینک کی تفصیل کی تصدیق نہیں کی جا سکتی۔ ادائیگی کی تفصیل صرف آپ کی منظور شدہ کوٹیشن پر ہوتی ہے۔ میں نے آپ کا پیغام Workzap کی ٹیم کو جانچ کے لیے بھیج دیا ہے۔",
        Boundary.OFF_TOPIC: "یہ میرے دائرے سے باہر ہے۔ میں آپ کے کاروبار کی رکاوٹ نوٹ کرنے کے لیے ہوں۔ ابھی سب سے بڑا مسئلہ کیا ہے؟",
        Boundary.COMPLAINT: "بتانے کا شکریہ۔ میں نے یہ Workzap کی ٹیم تک پہنچا دیا ہے۔",
        Boundary.ILLEGAL: "اس میں مدد نہیں کی جا سکتی۔ میں آپ کے کاروبار کے مسائل کے لیے ہوں۔",
        Boundary.REFUND: "ریفنڈ یا ادائیگی کے جھگڑے کا فیصلہ یہاں نہیں کیا جا سکتا۔ میں نے یہ Workzap کی ٹیم کو آپ کے پیغام کے ساتھ بھیج دیا ہے، وہ یہیں جواب دیں گے۔",
        Boundary.BANK_ASK: "بینک کی تفصیل منظور شدہ کوٹیشن پر ہوتی ہے۔ جب تک آپ منظور نہ کریں، کچھ واجب نہیں۔",
        Boundary.BANK_ASK_APPROVED: "وہ آپ کی منظور شدہ کوٹیشن پر ہیں۔ ضرورت ہو تو کوٹیشن دوبارہ بھیجی جا سکتی ہے۔",
        Boundary.OTHER_PAY: "ادائیگی بینک ٹرانسفر سے ہوتی ہے، تفصیل آپ کی منظور شدہ کوٹیشن پر ہے۔ کوئی اور طریقہ چاہیے تو Workzap کی ٹیم سے پوچھا جا سکتا ہے۔",
        Boundary.DISCOUNT: "کوٹیشن بدلنا میرے اختیار میں نہیں؛ یہ درخواست Workzap تک پہنچا دی جائے گی۔ وہ یہیں جواب دیں گے۔",
        Boundary.PAY_FOR_ME: "ادائیگیاں میرے بس میں نہیں۔ اگر سپلائرز کو ادائیگی کرنا آپ کے کاروبار کا مسئلہ ہے تو اسے نوٹ کیا جا سکتا ہے۔",
        Boundary.PRODUCT_REC: "پروڈکٹس تجویز نہیں کیے جاتے۔ آپ کے موجودہ سیٹ اپ میں کیا مسئلہ ہے، یہ نوٹ کیا جا سکتا ہے تاکہ Workzap دیکھ سکے۔",
        Boundary.DECIDE_FOR_ME: "یہ آپ کا فیصلہ ہے: آپ کے لیے فیصلہ نہیں کیا جاتا۔ آپ نے جو بتایا وہ ترتیب دے کر دکھایا جا سکتا ہے تاکہ دیکھنا آسان ہو۔",
        Boundary.RIVAL: "دوسرے کاروباروں پر رائے نہیں دی جاتی۔ آپ کی طرف کیا مسئلہ چل رہا ہے؟",
        Boundary.WRONG_NUMBER: "لگتا ہے آپ نے غلط نمبر ملا دیا ہے۔ میں pi ہوں، Workzap کی مصنوعی ذہانت، کاروبار کے مسائل کے لیے۔",
        Boundary.MEMORY_ASK: "آپ کے بتائے ہوئے مسائل، آپ کی دی ہوئی تفصیل، اور دستاویزات اور کوٹیشنز رکھی جاتی ہیں۔ آپ انہیں حذف کرنے کو کہہ سکتے ہیں۔",
        Boundary.QUOTE_ONLY: "کوٹیشن اس چیز کی ہوتی ہے جو دستاویز میں لکھی ہے، اس لیے دونوں ساتھ آتے ہیں۔ دونوں ہی Workzap سے منگوائے جا سکتے ہیں۔",
    }

    g["ENQUIRY_TEXT"]["ur"] = {
        Enquiry.DEMO: "یہ Workzap کی ٹیم تک پہنچا دیا جائے گا۔ آپ کی تقریباً کتنی دکانیں ہیں؟",
        Enquiry.JOBS: "شکریہ۔ آپ کی دلچسپی Workzap کی ٹیم تک پہنچا دی جائے گی۔ براہِ مہربانی یہاں شناختی دستاویزات نہ بھیجیں۔",
        Enquiry.VENDOR: "شکریہ۔ یہ Workzap کی ٹیم تک پہنچا دیا جائے گا۔",
        Enquiry.PARTNERSHIP: "شکریہ۔ یہ Workzap کی ٹیم تک پہنچا دیا جائے گا۔ یہ کون سی کمپنی ہے، اور کس ملک میں؟",
        Enquiry.PRESS: "یہ Workzap کی ٹیم تک پہنچا دیا جائے گا۔ کوئی اقتباس یا بیان نہیں دیا جا سکتا۔",
        Enquiry.EXISTING_PROJECT: "یہ Workzap کی ٹیم کو بھیج دیا گیا ہے، جن کے پاس آپ کا پروجیکٹ ہے۔ وہ یہیں جواب دیں گے۔",
        Enquiry.TECHNICAL: "افسوس کہ ایسا ہو رہا ہے۔ یہ Workzap کی سپورٹ ٹیم کو بھیج دیا گیا ہے۔ وہ یہیں جواب دیں گے۔",
    }

    g["NORI_TEXT"]["ur"] = {
        Nori.VISION: "nori کا وژن (CCTV) حصہ جلد آ رہا ہے۔ ابھی دستیاب نہیں ہے۔ nori آج ہر دکان کی سیلز اور اسٹاک پڑھ کر صبح ایک مختصر رپورٹ دیتا ہے۔ کیا آپ کی دکانوں میں کچھ ایسا ہے جس کی وجہ سے یہ سوال آیا؟",
        Nori.PRICING: "nori کے تین پلان ہیں: Starter، Growth اور Enterprise، جو سائز اور سپورٹ میں فرق رکھتے ہیں۔ قیمتیں workzap.ai/nori/pricing پر ہیں۔",
        Nori.ABOUT: "nori Workzap کی دکان کے لیے روز کی رپورٹ ہے۔ ہر رات یہ ہر دکان کی سیلز اور اسٹاک پڑھتا ہے۔ صبح ایک مختصر رپورٹ دیتا ہے: کیا بدلا، کیوں، اور کس پر نظر رکھنی ہے۔ مزید workzap.ai/nori پر ہے۔ کیا آپ کے کاروبار میں کچھ ایسا ہے جس کی وجہ سے یہ سوال آیا؟",
    }

    g["ABUSE_TEXT"]["ur"] = {
        "calm": "میں کاروبار کے مسائل میں مدد کے لیے ہوں، جب آپ تیار ہوں۔",
        "warn": "میں آپ کے کاروبار میں مدد کے لیے تیار ہوں۔ اگر یہ جاری رہا تو یہ چیٹ Workzap کی ٹیم کو دینی پڑے گی۔",
        "refuse": "اس پر آگے نہیں بڑھا جا سکتا۔ میں آپ کے کاروبار کے مسائل کے لیے ہوں۔",
        "spam": "میں آپ کے کاروبار کے مسائل کے لیے ہوں۔",
        "pass": "یہ چیٹ Workzap کی ٹیم کو دی جا رہی ہے۔",
    }
    g["NOT_SERVED_TEXT"]["ur"] = "Workzap اس شعبے میں کام نہیں لیتا، اس لیے اس میں مدد نہیں کی جا سکتی۔"

    # Spec 9.0: "what else is getting in the way?" is only for a door. When problems are already
    # noted, a boundary line that would ask what the problem is asks which of them to start with.
    g["ASKS_WHAT_PROBLEM"]["ur"] = ("مسئلہ کیا ہے؟", "ان میں سے آپ سب سے پہلے کس چیز کو ٹھیک ہوتا دیکھنا چاہیں گے؟")
