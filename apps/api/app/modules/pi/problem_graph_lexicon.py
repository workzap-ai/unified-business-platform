# ruff: noqa: E501  (word lists and four-language tables read better one entry per line)
"""PS-7: fixed words and wording for the problem graph. Data only: no logic that decides anything.

Everything is in English, Roman Urdu, Urdu script and Arabic (Hindi optional and not covered: it
falls back to English). The same business logic applies in every language: a connective in one
language means the same direction as its twin in another.

Markers are written the way people write them and folded once at import (`problem_graph.fold`
does the same to the owner's text: lower case, Arabic and Urdu letter variants merged, diacritics
dropped, Eastern digits turned into ASCII). Written by one author, not reviewed by a native speaker
of Urdu or Arabic: the tests check the form and the behaviour, not the quality of the language
(the taxonomy labels carry the same warning, spec 2.5.1).

A hypothesis here is a possible cause to CHECK. It is never a finding: every one is `pi_inferred`
until the owner says it or evidence is stored (platform spec v1.6, 3.5 and 4.3).
"""

LANGUAGES = ("en", "roman_ur", "ur", "ar")
ALIASES = {
    "en": "en", "english": "en", "roman_ur": "roman_ur", "roman-ur": "roman_ur",
    "romanurdu": "roman_ur", "roman_urdu": "roman_ur", "ur_roman": "roman_ur", "ur-latn": "roman_ur",
    "ur": "ur", "urdu": "ur", "ar": "ar", "arabic": "ar",
}  # fmt: skip

# ---------------------------------------------------------------------------------------------
# Connectives. FOLLOWS: "effect <conn> cause". PRECEDES: "cause <conn> effect".
# ---------------------------------------------------------------------------------------------
FOLLOWS = (
    "because of", "because", "due to", "owing to", "caused by", "on account of", "the reason is that",
    "the reason is", "reason being",
    "kyun ke", "kyunke", "kyunki", "kiyunke", "kiyunki", "kion ke", "kyon ke", "kyonke", "is liye ke",
    "isliye ke", "is lie ke", "wajah yeh hai ke", "wajah ye hai ke", "wajah yeh hai", "wajah ye hai",
    "sabab yeh hai ke",
    "کیونکہ", "کیوں کہ", "چونکہ", "وجہ یہ ہے کہ", "وجہ یہ ہے", "اس لیے کہ", "اس لئے کہ",
    "لأن", "لان", "بسبب", "نتيجة ل", "السبب هو", "السبب ان", "ذلك ان", "اذ ان",
)  # fmt: skip
PRECEDES = (
    "that is why", "thats why", "that's why", "which is why", "as a result", "as a consequence",
    "which leads to", "which led to", "leads to", "led to", "leading to", "results in", "resulting in",
    "which causes", "which means", "and therefore", "therefore", "hence", "consequently",
    "is liye", "isliye", "isi liye", "isiliye", "is lie", "isi lie", "is wajah se", "isi wajah se",
    "jis ki wajah se", "jis ke karan", "jis se", "ki wajah se", "ke karan", "ke sabab", "ke baais",
    "wajah se", "is karan",
    "اس لیے", "اس لئے", "اسی لیے", "اسی لئے", "اس وجہ سے", "اسی وجہ سے", "جس کی وجہ سے", "جس سے",
    "کی وجہ سے", "کے باعث", "کے سبب", "نتیجتا",
    "لذلك", "لهذا", "ولذلك", "ولهذا", "مما يؤدي الى", "مما ادى الى", "يؤدي الى", "ادى الى", "ادي الى",
    "نتيجة لذلك", "مما يسبب", "وبالتالي", "بالتالي", "مما يعني",
)  # fmt: skip
# "so" is only a connective after a comma or at the start of a sentence (see problem_graph).
SO_WORD = "so"
# Roman Urdu and Urdu "X is liye Y ke Z" (the clause after "ke" is the cause).
KE_WORDS = ("ke", "kay", "ki", "کہ", "که")

HEDGES = (
    "i think", "i believe", "i guess", "i feel", "maybe", "perhaps", "probably", "not sure", "might be",
    "could be", "seems", "i suspect",
    "mera khayal", "mera khial", "mujhe lagta", "mujhe lagta hai", "shayad", "ho sakta hai", "lagta hai",
    "mera andaza", "andaza",
    "میرا خیال", "مجھے لگتا", "شاید", "ہو سکتا ہے", "لگتا ہے", "میرا اندازہ",
    "اعتقد", "اظن", "ربما", "يبدو", "لعل", "اشعر ان", "احتمال",
)  # fmt: skip
PARTIAL = (
    "also because", "partly", "part of the reason", "one reason", "another reason", "one of the reasons",
    "in part", "partially", "among other things",
    "ek wajah", "ek aur wajah", "ek karan", "ek sabab", "kuch had tak", "ek wajah yeh bhi", "wajah yeh bhi",
    "ایک وجہ", "ایک اور وجہ", "ایک سبب", "کچھ حد تک", "جزوی",
    "احد الاسباب", "سبب اخر", "جزئيا", "جزئيا", "جزء من السبب", "الى حد ما",
)  # fmt: skip
NEGATIONS = (
    "not", "no", "never", "isnt", "isn't", "wasnt", "wasn't", "dont", "don't", "doesnt", "doesn't",
    "nahi", "nahin", "nai", "nhi", "na", "mat",
    "نہیں", "نہی", "نا", "مت",
    "ليس", "لا", "ليست", "لم", "ما", "مش",
)  # fmt: skip
CONDITIONALS = (
    "if", "unless", "whether", "suppose", "agar", "jab tak", "chahe", "اگر", "جب تک", "چاہے",
    "لو", "اذا", "إذا", "لو ان", "سواء",
)  # fmt: skip
QUESTION_WORDS = (
    "why", "how come", "is it because", "kya", "kyun", "kyon", "kyu", "kaise", "کیا", "کیوں", "کیسے",
    "هل", "لماذا", "لما", "كيف", "ليه",
)  # fmt: skip
NOT_HELPED = (
    "did not help", "didnt help", "didn't help", "no change", "no effect", "got worse", "made it worse",
    "failed", "not worked", "did not work", "didnt work", "didn't work",
    "kaam nahi kiya", "faida nahi", "farq nahi", "aur barh", "aur bigar", "kaam nahi aaya", "nakam",
    "کام نہیں کیا", "فائدہ نہیں", "فرق نہیں", "اور بڑھ", "اور بگڑ", "ناکام",
    "لم ينجح", "لم يفد", "لا فرق", "ساء اكثر", "ازداد", "فشل",
)  # fmt: skip

# What marks a statement as a business consequence (money, customers, sales lost) and as a symptom
# (an outward sign).
CONSEQUENCE = (
    "losing customers", "lose customers", "lost customers", "customers leave", "customers leaving",
    "lost sales", "losing sales", "lose sales", "losing money", "lose money", "lost money", "loss of",
    "money lost", "we lose", "losing business", "going out of business", "revenue drop", "profit drop",
    "gahak kho", "gahak chhor", "gahak ja rahe", "gahak jaa rahe", "bikri kam", "bikri gir", "nuqsan",
    "nuksan", "paisa doob", "paisa zaya", "munafa kam", "paisa kam", "customers kho",
    "گاہک کھو", "گاہک چھوڑ", "گاہک جا رہے", "بکری کم", "نقصان", "پیسہ ڈوب", "پیسے ڈوب", "منافع کم",
    "خسارة", "خسائر", "نخسر", "نفقد العملاء", "فقدان العملاء", "خسارة المبيعات", "تراجع المبيعات",
    "ضياع المال", "تراجع الارباح", "العملاء يغادرون", "نفقد زبائن",
)  # fmt: skip
SYMPTOM = (
    "late", "delay", "delayed", "delays", "mismatch", "complain", "complaint", "complaints", "cancel",
    "cancelled", "canceled", "cancellation", "returned", "returns", "return", "missing", "shortage",
    "run out", "runs out", "ran out", "out of stock", "broken", "wrong", "not arriving", "not delivered",
    "bounce", "bounced", "no show", "no-show", "refuse", "refused",
    "der", "deri", "late", "shikayat", "shikayatein", "wapas", "gum", "kam", "khatam", "toot", "ghalat",
    "cancel", "nahi aate", "nahi milta", "nahi pohanchta", "nahi pahunchta",
    "دیر", "تاخیر", "شکایت", "شکایات", "واپس", "گم", "کم", "ختم", "ٹوٹ", "غلط", "منسوخ", "نہیں آتے",
    "تاخير", "متاخر", "تاخر", "شكوى", "شكاوى", "مرتجع", "مرتجعات", "ملغي", "الغاء", "نقص", "ناقص",
    "مفقود", "خطا", "خاطئ", "يرفض", "رفض",
)  # fmt: skip

# ---------------------------------------------------------------------------------------------
# Stop words (not content) in the four languages.
# ---------------------------------------------------------------------------------------------
STOP = frozenset(
    """a an the and or but of to in on at for from by with is are was were be been it its this that
    these those i we you they he she my our your their me us them as so if not no do does did have has
    had will would can could should may might also very too just about into than then there here when
    what which who whom how why all some any each more most other such only own same up out over
    one two keep kept lot lots many much get got going go goes
    hai hain tha thi the ho hota hoti hote ka ki ke ko se me mein par per pe aur ya bhi hi to toh
    yeh ye wo woh is us in un hum hamara hamari hamare mera meri mere aap apna apni apne kar karta
    karti karte kiya kiye gaya gayi gaye raha rahi rahe rahi wala wali wale sab bohat bahut kuch koi
    nahi nahin na jo jab tab agar lekin magar phir abhi yahan wahan kaun kya kyun kaise kitna kitne
    sirf zyada tar liye lie se tak saath ke liye
    و في من على الى عن ان هذا هذه ذلك التي الذي كان كانت يكون هو هي هم نحن انا انت ما لا لم لن قد
    كل بعض مع او ثم لكن حتى اذا اذ كما بين عند لدي لدينا
    اور یا کی کا کے کو سے میں پر تک ہے ہیں تھا تھی تھے ہو ہوتا ہوتی ہوتے یہ وہ اس ان ہم ہمارا ہماری
    ہمارے میرا میری میرے آپ کر کرتا کرتی کرتے کیا گیا گئی گئے رہا رہی رہے والا والی والے سب بہت کچھ کوئی
    نہیں نا جو جب تب اگر لیکن مگر پھر ابھی یہاں وہاں کون کیوں کیسے کتنا کتنے صرف زیادہ لیے لئے ساتھ بھی ہی تو
    """.split()
)

GENERIC = frozenset(  # words that name "a problem" and carry no topic
    """problem problems issue issues thing things work masla masle mushkil mushkilat kaam مسئلہ مسائل مشکل
    کام مشكلة مشكلات مشكله مشاكل شيء امر""".split()
)

# ---------------------------------------------------------------------------------------------
# Shared resources and processes: the same one named in two problems links them (weakly).
# key -> markers. A marker is a whole word or phrase.
# ---------------------------------------------------------------------------------------------
RESOURCES: dict[str, tuple[str, ...]] = {
    "courier": ("courier", "couriers", "rider", "riders", "delivery boy", "delivery partner", "dispatch", "trax", "leopards", "tcs", "کوریئر", "رائیڈر", "ڈسپیچ", "شحن", "مندوب التوصيل", "شركة الشحن", "سائق التوصيل", "كوريير"),
    "staff": ("staff", "employee", "employees", "assistant", "worker", "workers", "manager", "salesman", "cashier", "عملہ", "ملازم", "ملازمین", "اسسٹنٹ", "مینیجر", "کیشیئر", "الموظفين", "موظف", "الموظف", "عامل", "العمال", "مساعد", "المدير", "امين الصندوق"),
    "system": ("pos", "software", "system", "app", "excel", "spreadsheet", "sheet", "erp", "tally", "quickbooks", "سافٹ ویئر", "سسٹم", "ایپ", "ایکسل", "برنامج", "نظام", "تطبيق", "اكسل", "جدول"),
    "stock": ("stock", "inventory", "godown stock", "maal", "اسٹاک", "مال", "المخزون", "مخزون", "البضاعة", "بضاعة", "بضائع"),
    "supplier": ("supplier", "suppliers", "vendor", "vendors", "wholesaler", "سپلائر", "سپلائرز", "ہول سیلر", "المورد", "الموردين", "مورد", "موردين"),
    "payment": ("cod", "cash on delivery", "payment", "payments", "advance", "easypaisa", "jazzcash", "ادائیگی", "پیمنٹ", "ایڈوانس", "الدفع", "دفعة", "الدفعات", "دفعات", "السداد"),
    "records": ("register", "ledger", "notebook", "khata", "record", "records", "paper", "رجسٹر", "کھاتہ", "کھاتے", "ریکارڈ", "سجل", "دفتر", "السجل", "السجلات", "دفتر الحسابات"),
    "whatsapp": ("whatsapp", "whats app", "واٹس ایپ", "واٹسایپ", "واتساب", "الواتساب", "واتس اب"),
    "warehouse": ("depot", "warehouse", "godown", "storeroom", "گودام", "ڈپو", "المستودع", "مستودع", "المخزن", "مخزن"),
    "website": ("website", "web site", "online store", "online shop", "webshop", "ویب سائٹ", "آن لائن", "الموقع", "موقع", "المتجر الالكتروني", "متجر الكتروني"),
    "customers_list": ("customer list", "customer data", "contacts", "contact list", "phone numbers", "address", "addresses", "گاہکوں کی فہرست", "رابطے", "پتہ", "پتے", "قائمة العملاء", "بيانات العملاء", "العناوين", "العنوان"),
    "owner": ("owner", "me myself", "i myself", "main khud", "mujhe khud", "مجھے خود", "میں خود", "انا بنفسي", "بنفسي"),
}  # fmt: skip

# ---------------------------------------------------------------------------------------------
# Category families (weak link). A category belongs to at most one family.
# ---------------------------------------------------------------------------------------------
FAMILIES: dict[str, tuple[str, ...]] = {
    "supply_chain": ("stock_inventory", "orders_fulfilment", "suppliers_purchasing"),
    "money": ("cash_collections", "margin_cost", "sales_revenue", "loss_security"),
    "customer": ("customers_retention", "marketing_leads", "quality_complaints", "customer_experience_digital"),
    "people_process": ("people_staff", "operations_process", "communication_coordination", "compliance_admin"),
    "systems_data": ("tech_systems", "reporting_visibility", "planning_growth"),
}  # fmt: skip
FAMILY_OF = {cat: fam for fam, cats in FAMILIES.items() for cat in cats}

# Layer hints by taxonomy.
CONSEQUENCE_SUBTYPES = frozenset(
    """sales_drop margin_shrinking cash_flow_tight repeat_low churn_subscription reviews_bad target_missed
    branch_underperforming seasonal_dip conversion_low basket_small cost_overruns hidden_costs
    wastage_cost""".split()
)
OPERATIONAL_SUBTYPES = frozenset(
    """manual_work duplicate_entry bottleneck approvals_slow no_sop checklists_not_done handoffs
    no_visibility no_tracking no_system outdated_system software_not_connected excel_dependency
    data_scattered no_dashboard kpi_undefined manual_reports accountability communication_internal
    info_lost_in_whatsapp tasks_dropped owner_bottleneck branches_not_aligned no_customer_data
    po_tracking order_tracking record_keeping documentation shift_scheduling""".split()
)
OPERATIONAL_CATEGORIES = frozenset(
    """operations_process tech_systems people_staff communication_coordination reporting_visibility
    compliance_admin""".split()
)

# ---------------------------------------------------------------------------------------------
# Category guess from words (only used when a record carries no category; labelled a guess).
# ---------------------------------------------------------------------------------------------
CATEGORY_WORDS: dict[str, tuple[str, ...]] = {
    "orders_fulfilment": ("order", "orders", "delivery", "deliver", "parcel", "courier", "rider", "cancel", "return", "dispatch", "آرڈر", "ڈیلیوری", "پارسل", "کوریئر", "طلب", "طلبات", "توصيل", "شحن"),
    "stock_inventory": ("stock", "inventory", "stockout", "maal", "اسٹاک", "مال", "مخزون", "المخزون", "نفد"),
    "cash_collections": ("rent", "payment", "payments", "collect", "cash", "receivable", "pay late", "paying late", "invoice", "udhaar", "wusooli", "کرایہ", "ادائیگی", "وصولی", "ادھار", "ايجار", "إيجار", "دفع", "تحصيل", "فواتير"),
    "customers_retention": ("customer", "customers", "complain", "complaint", "tenant", "tenants", "repeat", "review", "gahak", "شکایت", "گاہک", "عميل", "عملاء", "شكوى", "شكاوى", "مستأجر", "مستاجر"),
    "marketing_leads": ("leads", "lead", "ads", "advert", "marketing", "followers", "enquiry", "inquiry", "ishtehaar", "اشتہار", "مارکیٹنگ", "اعلان", "اعلانات", "تسويق", "استفسار"),
    "suppliers_purchasing": ("supplier", "vendor", "purchase", "buying", "سپلائر", "خریداری", "مورد", "موردين", "مشتريات"),
    "people_staff": ("staff", "employee", "attendance", "salary", "hire", "hiring", "training", "عملہ", "ملازم", "تنخواہ", "موظف", "موظفين", "رواتب", "حضور"),
    "operations_process": ("process", "manual", "register", "paperwork", "track", "tracking", "assign", "lose track", "who reported", "عمل", "دستی", "رجسٹر", "تتبع", "يدوي", "سجل"),
    "reporting_visibility": ("report", "reports", "dashboard", "visibility", "numbers", "رپورٹ", "رپورٹس", "تقرير", "تقارير", "لوحة"),
    "tech_systems": ("software", "system", "pos", "app", "excel", "سافٹ ویئر", "سسٹم", "برنامج", "نظام", "تطبيق"),
    "margin_cost": ("margin", "profit", "costs", "cost", "expenses", "munafa", "منافع", "اخراجات", "ربح", "تكاليف", "مصاريف"),
    "sales_revenue": ("sales", "revenue", "bikri", "سیل", "بکری", "مبيعات", "المبيعات", "ايرادات"),
    "quality_complaints": ("quality", "defect", "defective", "damaged", "معیار", "خراب", "جودة", "عيب", "تالف"),
    "compliance_admin": ("tax", "licence", "license", "compliance", "audit", "ٹیکس", "لائسنس", "ضريبة", "ترخيص"),
    "communication_coordination": ("whatsapp", "coordination", "miscommunication", "واٹس ایپ", "رابطہ", "واتساب", "تنسيق"),
}  # fmt: skip

# ---------------------------------------------------------------------------------------------
# The cause catalogue (source: taxonomy). key -> (label x4, check x4, triggers).
# label: a noun phrase describing a POSSIBLE cause. check: what to look at to find out.
# triggers: words that, if the owner or the problem record already says them, count as support.
# ---------------------------------------------------------------------------------------------
_Q = tuple[str, str, str, str]  # (en, roman_ur, ur, ar)


def _h(label: _Q, check: _Q, triggers: str) -> dict[str, object]:
    return {
        "label": label,
        "check": check,
        "triggers": tuple(t.strip() for t in triggers.split("|")),
    }


CAUSES: dict[str, dict[str, object]] = {
    "stock_unavailable": _h(
        ("stock not available when the order arrives", "order aane par maal maujood nahi hota", "آرڈر آنے پر مال موجود نہیں ہوتا", "عدم توفر المخزون عند وصول الطلب"),
        ("Are orders accepted for items that are already out of stock?", "Kya aise items ke order le liye jate hain jo pehle se khatam hon?", "کیا ایسی اشیا کے آرڈر لیے جاتے ہیں جو پہلے سے ختم ہوں؟", "هل تُقبل طلبات على أصناف نفدت بالفعل؟"),
        "out of stock|stockout|stock out|no stock|maal khatam|maal nahi|stock khatam|اسٹاک ختم|مال ختم|مال نہیں|نفد|نفاد|غير متوفر",
    ),
    "order_processing_delay": _h(
        ("orders processed late after they come in", "order aane ke baad process hone mein der", "آرڈر آنے کے بعد پراسیس ہونے میں دیر", "تأخر معالجة الطلب بعد وصوله"),
        ("How long does an order wait between arriving and being confirmed or packed?", "Order aane se confirm ya pack hone tak kitna waqt lagta hai?", "آرڈر آنے سے کنفرم یا پیک ہونے تک کتنا وقت لگتا ہے؟", "كم يستغرق الطلب بين وصوله وتأكيده أو تغليفه؟"),
        "processing|confirm late|packing late|order late process|pack hone|process mein der|تاخير المعالجة|پراسیس|تأخر التغليف",
    ),
    "delivery_failure": _h(
        ("delivery attempts that fail at the door", "delivery ke waqt darwaze par nakami", "ڈیلیوری کے وقت دروازے پر ناکامی", "فشل محاولات التوصيل عند الباب"),
        ("What happens on a failed delivery attempt, and how often does it happen?", "Delivery nakam ho to kya hota hai, aur kitni baar hota hai?", "ڈیلیوری ناکام ہو تو کیا ہوتا ہے، اور کتنی بار ہوتا ہے؟", "ماذا يحدث عند فشل محاولة التوصيل وكم مرة يحدث ذلك؟"),
        "failed delivery|not at home|door|darwaze|nahi lete|refuse|refused|دروازے|نہیں لیتے|فشل التوصيل|يرفض|رفض الاستلام",
    ),
    "customer_unconfirmed": _h(
        ("orders that the customer never confirmed", "aise order jo gahak ne confirm hi nahi kiye", "ایسے آرڈر جو گاہک نے کنفرم ہی نہیں کیے", "طلبات لم يؤكدها العميل"),
        ("Is every order confirmed with the customer before it is sent?", "Kya har order bhejne se pehle gahak se confirm hota hai?", "کیا ہر آرڈر بھیجنے سے پہلے گاہک سے کنفرم ہوتا ہے؟", "هل يُؤكَّد كل طلب مع العميل قبل إرساله؟"),
        "confirm|confirmation|not confirmed|fake order|کنفرم|تصدیق|تاكيد|تأكيد|غير مؤكد",
    ),
    "wrong_contact_data": _h(
        ("wrong or incomplete phone number or address", "ghalat ya adhoora phone number ya pata", "غلط یا ادھورا فون نمبر یا پتہ", "رقم هاتف أو عنوان خاطئ أو ناقص"),
        ("Are phone numbers and addresses checked when the order is taken?", "Order lete waqt phone number aur pata check hota hai?", "کیا آرڈر لیتے وقت فون نمبر اور پتہ چیک ہوتا ہے؟", "هل يُتحقق من رقم الهاتف والعنوان عند أخذ الطلب؟"),
        "wrong address|wrong number|address|phone number|pata ghalat|ghalat pata|غلط پتہ|غلط نمبر|عنوان خاطئ|رقم خاطئ|العنوان",
    ),
    "cod_payment_issue": _h(
        ("cash-on-delivery or payment problems at hand-over", "cash on delivery ya payment ka masla hand-over par", "کیش آن ڈیلیوری یا ادائیگی کا مسئلہ", "مشكلات الدفع عند الاستلام"),
        ("How many of the affected orders were cash on delivery, and how many were prepaid?", "Mutasir orders mein se kitne cash on delivery the aur kitne pehle se ada shuda?", "متاثرہ آرڈرز میں سے کتنے کیش آن ڈیلیوری تھے اور کتنے پہلے سے ادا شدہ؟", "كم من الطلبات المتأثرة كانت دفعاً عند الاستلام وكم منها مدفوع مسبقاً؟"),
        "cod|cash on delivery|payment|paisa nahi|ادائیگی|کیش آن|الدفع عند الاستلام|دفع",
    ),
    "inventory_sync": _h(
        ("stock counts that do not match across channels", "alag alag jagah stock ki ginti ka mel na khana", "مختلف جگہوں پر اسٹاک کی گنتی کا میل نہ کھانا", "عدم تطابق أرقام المخزون بين القنوات"),
        ("Is the same stock sold in more than one place, and how is the count kept in step?", "Kya wahi stock ek se zyada jagah bikta hai, aur ginti kaise barabar rakhi jati hai?", "کیا وہی اسٹاک ایک سے زیادہ جگہ بکتا ہے، اور گنتی کیسے برابر رکھی جاتی ہے؟", "هل يُباع المخزون نفسه في أكثر من مكان وكيف يُحفظ العدد متطابقاً؟"),
        "sync|not matching|multiple channels|two places|online and shop|ginti|mel nahi|عدم تطابق|مزامنة|گنتی|قنوات",
    ),
    "communication_gap": _h(
        ("customers or staff not told what is happening", "gahak ya staff ko bataya nahi jata ke kya ho raha hai", "گاہک یا عملے کو بتایا نہیں جاتا کہ کیا ہو رہا ہے", "عدم إبلاغ العملاء أو الموظفين بما يحدث"),
        ("Who tells the customer when something changes, and how?", "Jab kuch badalta hai to gahak ko kaun aur kaise batata hai?", "جب کچھ بدلتا ہے تو گاہک کو کون اور کیسے بتاتا ہے؟", "من يخبر العميل عند حدوث تغيير وكيف؟"),
        "not told|no update|no message|didn't know|bataya nahi|khabar nahi|اطلاع نہیں|بتایا نہیں|لم يتم إبلاغ|بدون اشعار|لا تحديث",
    ),
    "courier_unreliable": _h(
        ("the courier or rider being slow or unreliable", "courier ya rider ka sust ya na-qabil-e-aitmaad hona", "کوریئر یا رائیڈر کا سست یا ناقابل اعتماد ہونا", "بطء أو عدم موثوقية شركة الشحن أو المندوب"),
        ("Which deliveries are late, and are they mostly with one courier or one area?", "Kaun si deliveries late hain, aur kya zyada tar ek courier ya ek ilaqe ki hain?", "کون سی ڈیلیوریاں لیٹ ہیں، اور کیا زیادہ تر ایک کوریئر یا ایک علاقے کی ہیں؟", "أي الشحنات تتأخر وهل أغلبها مع شركة شحن واحدة أو منطقة واحدة؟"),
        "courier|rider|delivery boy|late deliver|کوریئر|رائیڈر|شركة الشحن|المندوب|شحن",
    ),
    "dispatch_delay": _h(
        ("orders leaving the shop or depot late", "order dukaan ya depot se der se nikalna", "آرڈر کا دکان یا ڈپو سے دیر سے نکلنا", "تأخر خروج الطلبات من المحل أو المستودع"),
        ("At what time of day do orders leave, and how many wait until the next day?", "Order din ke kis waqt nikalte hain, aur kitne agle din tak ruk jate hain?", "آرڈر دن کے کس وقت نکلتے ہیں، اور کتنے اگلے دن تک رک جاتے ہیں؟", "في أي وقت من اليوم تخرج الطلبات وكم منها ينتظر لليوم التالي؟"),
        "dispatch|depot|ek depot|ships from|warehouse|ڈپو|ڈسپیچ|مستودع",
    ),
    "product_mismatch": _h(
        ("the item differing from how it was shown or described", "item ka dikhaye ya bataye gaye se mukhtalif hona", "آئٹم کا دکھائے یا بتائے گئے سے مختلف ہونا", "اختلاف المنتج عن الوصف أو الصور"),
        ("What reasons do returning customers give, in their own words?", "Wapas karne wale gahak apni zabaan mein kya wajah batate hain?", "واپس کرنے والے گاہک اپنی زبان میں کیا وجہ بتاتے ہیں؟", "ما الأسباب التي يذكرها العملاء المرجِعون بكلماتهم؟"),
        "not as shown|different from|size|colour|color|photo|jaisa dikhaya|مختلف|سائز|رنگ|تصویر|مختلف عن|الصورة",
    ),
    "manual_entry": _h(
        ("information typed or copied by hand more than once", "maloomat ka haath se baar baar likha ya copy kiya jana", "معلومات کا ہاتھ سے بار بار لکھا یا کاپی کیا جانا", "إدخال المعلومات يدوياً أكثر من مرة"),
        ("Where is the same information written down more than once?", "Wahi maloomat kin kin jagah dobara likhi jati hai?", "وہی معلومات کن کن جگہ دوبارہ لکھی جاتی ہے؟", "أين تُكتب المعلومات نفسها أكثر من مرة؟"),
        "manual|by hand|typing|copy|duplicate|haath se|دستی|ہاتھ سے|نقل|يدوي|يدويا",
    ),
    "no_checklist": _h(
        ("no fixed steps or checklist to follow", "amal karne ke liye tay shuda tareeqa ya checklist ka na hona", "پیروی کے لیے طے شدہ طریقہ یا چیک لسٹ کا نہ ہونا", "عدم وجود خطوات ثابتة أو قائمة تحقق"),
        ("Is there a written or agreed set of steps, and is it followed every time?", "Kya likhe ya tay shuda qadam hain, aur kya har baar un par amal hota hai?", "کیا لکھے یا طے شدہ قدم ہیں، اور کیا ہر بار ان پر عمل ہوتا ہے؟", "هل توجد خطوات مكتوبة أو متفق عليها وهل تُتبع في كل مرة؟"),
        "checklist|no sop|no steps|forget|forgot|bhool|چیک لسٹ|بھول|قائمة تحقق|نسيان",
    ),
    "handoff_gap": _h(
        ("information lost when work passes from one person to another", "kaam ek se doosre ko dete waqt maloomat ka kho jana", "کام ایک سے دوسرے کو دیتے وقت معلومات کا کھو جانا", "ضياع المعلومات عند انتقال العمل بين شخصين"),
        ("When work is passed on, what exactly is handed over and how?", "Kaam aage dete waqt kya aur kaise diya jata hai?", "کام آگے دیتے وقت کیا اور کیسے دیا جاتا ہے؟", "عند تسليم العمل ماذا يُسلَّم وكيف؟"),
        "who reported|lose track|lost track|handover|hand over|pass on|kisne bataya|ٹریک|کس نے بتایا|فقدان التتبع|تسليم",
    ),
    "supplier_delay": _h(
        ("the supplier delivering late or short", "supplier ka der se ya kam maal bhejna", "سپلائر کا دیر سے یا کم مال بھیجنا", "تأخر المورد أو توريده كمية ناقصة"),
        ("How many supplier orders arrived late or short in the last few months?", "Pichle kuch mahinon mein supplier ke kitne order der se ya kam aaye?", "پچھلے کچھ مہینوں میں سپلائر کے کتنے آرڈر دیر سے یا کم آئے؟", "كم طلباً من المورد وصل متأخراً أو ناقصاً في الأشهر الأخيرة؟"),
        "supplier late|supplier|vendor|supplier ne|سپلائر|المورد",
    ),
    "no_reorder_rule": _h(
        ("no set level at which stock is re-ordered", "stock dobara mangwane ki koi tay shuda hadd ka na hona", "اسٹاک دوبارہ منگوانے کی کوئی طے شدہ حد نہ ہونا", "عدم وجود حد محددة لإعادة الطلب"),
        ("How is it decided that it is time to order an item again?", "Kaise tay hota hai ke ab item dobara mangwane ka waqt aa gaya?", "کیسے طے ہوتا ہے کہ اب آئٹم دوبارہ منگوانے کا وقت آ گیا؟", "كيف يُقرَّر أن وقت إعادة طلب الصنف قد حان؟"),
        "reorder|re-order|run out|ran out|runs out|khatam ho jata|ختم ہو جاتا|ينفد",
    ),
    "demand_not_tracked": _h(
        ("not knowing which items sell and how fast", "ye na jaanna ke kaun si cheez kitni tezi se bikti hai", "یہ نہ جاننا کہ کون سی چیز کتنی تیزی سے بکتی ہے", "عدم معرفة الأصناف الأكثر مبيعاً وسرعة بيعها"),
        ("Is there any record of how many of each item sell in a month?", "Kya is ka koi record hai ke har item mahine mein kitna bikta hai?", "کیا اس کا کوئی ریکارڈ ہے کہ ہر آئٹم مہینے میں کتنا بکتا ہے؟", "هل يوجد سجل لكمية مبيعات كل صنف شهرياً؟"),
        "dead stock|overstock|unsold|slow moving|pada hai|بکتا نہیں|راکد|مخزون راكد",
    ),
    "manual_counting": _h(
        ("stock counted by hand with no regular check", "stock ki haath se ginti aur baqaida check ka na hona", "اسٹاک کی ہاتھ سے گنتی اور باقاعدہ چیک کا نہ ہونا", "جرد يدوي دون مراجعة منتظمة"),
        ("How often is stock counted, and who does it?", "Stock ki ginti kitni baar hoti hai, aur kaun karta hai?", "اسٹاک کی گنتی کتنی بار ہوتی ہے، اور کون کرتا ہے؟", "كم مرة يُجرد المخزون ومن يقوم بذلك؟"),
        "count|counting|recount|ginti|گنتی|جرد",
    ),
    "no_receiving_check": _h(
        ("goods not checked when they arrive or leave", "maal aate ya jate waqt check na hona", "مال آتے یا جاتے وقت چیک نہ ہونا", "عدم فحص البضاعة عند الاستلام أو الخروج"),
        ("Is anything checked against a list when goods come in or go out?", "Kya maal aate ya jate waqt kisi list se milaya jata hai?", "کیا مال آتے یا جاتے وقت کسی فہرست سے ملایا جاتا ہے؟", "هل تُطابق البضاعة مع قائمة عند دخولها أو خروجها؟"),
        "theft|shrinkage|missing stock|goods missing|chori|چوری|سرقة|نقص المخزون",
    ),
    "no_stock_record": _h(
        ("no reliable record of what is in stock", "kya maal maujood hai iska bharosemand record na hona", "کیا مال موجود ہے اس کا بھروسے مند ریکارڈ نہ ہونا", "عدم وجود سجل موثوق لما في المخزون"),
        ("Where is the stock written down today, and how current is it?", "Aaj stock kahan likha hota hai, aur kitna taaza hota hai?", "آج اسٹاک کہاں لکھا ہوتا ہے، اور کتنا تازہ ہوتا ہے؟", "أين يُسجَّل المخزون اليوم ومدى حداثته؟"),
        "no record|not recorded|dont know how much|pata nahi kitna|ریکارڈ نہیں|پتہ نہیں کتنا|لا يوجد سجل",
    ),
    "no_reminder_process": _h(
        ("no regular reminder to people who owe money", "jin par paisa baqaya hai unhein baqaida yaad dehani ka na hona", "جن پر پیسہ باقی ہے انہیں باقاعدہ یاد دہانی کا نہ ہونا", "عدم وجود تذكير منتظم لمن عليهم مبالغ"),
        ("How are late payers reminded today, and by whom?", "Der se ada karne walon ko aaj kaise aur kaun yaad dilata hai?", "دیر سے ادا کرنے والوں کو آج کیسے اور کون یاد دلاتا ہے؟", "كيف يُذكَّر المتأخرون في السداد اليوم ومن يقوم بذلك؟"),
        "chase|chasing|remind|call one by one|ek ek|yaad dehani|ایک ایک|یاد دہانی|تذكير|متابعة",
    ),
    "unclear_terms": _h(
        ("payment dates or terms not clear to the customer", "ada'egi ki tareekhein ya shara'it gahak ko wazeh na hona", "ادائیگی کی تاریخیں یا شرائط گاہک کو واضح نہ ہونا", "عدم وضوح مواعيد أو شروط الدفع للعميل"),
        ("Are the due date and the terms agreed in writing with each customer?", "Kya har gahak ke saath tareekh aur shara'it likh kar tay hoti hain?", "کیا ہر گاہک کے ساتھ تاریخ اور شرائط لکھ کر طے ہوتی ہیں؟", "هل يُتفق على الموعد والشروط كتابياً مع كل عميل؟"),
        "terms|due date|agreement|credit terms|shara'it|شرائط|تاریخ|اتفاق|شروط|موعد",
    ),
    "no_daily_reconciliation": _h(
        ("no daily matching of cash against records", "rozana cash ko record se na milana", "روزانہ کیش کو ریکارڈ سے نہ ملانا", "عدم مطابقة النقد مع السجلات يومياً"),
        ("Is cash matched against sales every day, and by whom?", "Kya rozana cash ko bikri se milaya jata hai, aur kaun milata hai?", "کیا روزانہ کیش کو بکری سے ملایا جاتا ہے، اور کون ملاتا ہے؟", "هل يُطابق النقد مع المبيعات يومياً ومن يقوم بذلك؟"),
        "cash mismatch|cash short|shortfall|daily closing|hisaab nahi milta|حساب نہیں ملتا|کیش کم|عجز الصندوق|اغلاق يومي",
    ),
    "no_follow_up": _h(
        ("no follow-up after the first contact", "pehle rabte ke baad dobara rabta na karna", "پہلے رابطے کے بعد دوبارہ رابطہ نہ کرنا", "عدم المتابعة بعد التواصل الأول"),
        ("What happens after a customer first gets in touch, and who follows up?", "Gahak ke pehle rabte ke baad kya hota hai, aur kaun follow-up karta hai?", "گاہک کے پہلے رابطے کے بعد کیا ہوتا ہے، اور کون فالو اپ کرتا ہے؟", "ماذا يحدث بعد أول تواصل من العميل ومن يتابع؟"),
        "follow up|follow-up|no reply|never called|dobara rabta|فالو اپ|جواب نہیں|متابعة|لا رد",
    ),
    "slow_response_process": _h(
        ("messages or calls answered late", "paighamat ya calls ka der se jawab", "پیغامات یا کالز کا دیر سے جواب", "تأخر الرد على الرسائل أو المكالمات"),
        ("How long does a customer wait for a first reply, and who answers?", "Gahak ko pehle jawab ke liye kitna intezar karna parta hai, aur kaun jawab deta hai?", "گاہک کو پہلے جواب کے لیے کتنا انتظار کرنا پڑتا ہے، اور کون جواب دیتا ہے؟", "كم ينتظر العميل أول رد ومن يرد؟"),
        "slow reply|reply late|late reply|response|jawab der|جواب دیر|دیر سے جواب|بطء الرد|تأخر الرد",
    ),
    "staff_training": _h(
        ("staff not trained for this task", "is kaam ke liye staff ki tarbiyat na hona", "اس کام کے لیے عملے کی تربیت نہ ہونا", "عدم تدريب الموظفين على هذه المهمة"),
        ("Who has been shown how to do this task, and by whom?", "Is kaam ka tareeqa kis ko kis ne sikhaya hai?", "اس کام کا طریقہ کس کو کس نے سکھایا ہے؟", "من تم تدريبه على هذه المهمة ومن دربه؟"),
        "training|untrained|dont know how|new staff|tarbiyat|sikhaya|تربیت|سکھایا|تدريب",
    ),
    "unclear_roles": _h(
        ("nobody clearly responsible for this task", "is kaam ki zimmedari kisi ek ki wazeh na hona", "اس کام کی ذمہ داری کسی ایک کی واضح نہ ہونا", "عدم وضوح المسؤول عن هذه المهمة"),
        ("Who is responsible for this task, and do they know it?", "Is kaam ka zimmedar kaun hai, aur kya use pata hai?", "اس کام کا ذمہ دار کون ہے، اور کیا اسے پتہ ہے؟", "من المسؤول عن هذه المهمة وهل يعلم بذلك؟"),
        "responsible|nobody|no one|zimmedar|koi nahi|ذمہ دار|کوئی نہیں|مسؤول|لا احد",
    ),
    "no_attendance_record": _h(
        ("no reliable record of who came and when", "kaun kab aaya iska bharosemand record na hona", "کون کب آیا اس کا بھروسے مند ریکارڈ نہ ہونا", "عدم وجود سجل موثوق للحضور"),
        ("How is attendance recorded today?", "Aaj hazri kaise likhi jati hai?", "آج حاضری کیسے لکھی جاتی ہے؟", "كيف يُسجَّل الحضور اليوم؟"),
        "attendance|late coming|hazri|حاضری|دیر سے آنا|الحضور|التأخر عن العمل",
    ),
    "no_tracking": _h(
        ("not measuring where results come from", "ye na napna ke nateeje kahan se aate hain", "یہ نہ ناپنا کہ نتیجے کہاں سے آتے ہیں", "عدم قياس مصدر النتائج"),
        ("Is there any record of where each customer or sale came from?", "Kya is ka koi record hai ke har gahak ya bikri kahan se aayi?", "کیا اس کا کوئی ریکارڈ ہے کہ ہر گاہک یا بکری کہاں سے آئی؟", "هل يوجد سجل لمصدر كل عميل أو عملية بيع؟"),
        "no tracking|dont track|cannot track|not tracked|track nahi|ٹریک نہیں|لا نتتبع|بدون تتبع",
    ),
    "separate_tools": _h(
        ("information kept in separate tools that do not talk to each other", "maloomat alag alag tools mein jo aapas mein juray nahi", "معلومات الگ الگ ٹولز میں جو آپس میں جڑے نہیں", "معلومات في أدوات منفصلة غير مترابطة"),
        ("Which tools hold the information today, and is anything copied between them?", "Aaj maloomat kin tools mein hain, aur kya kuch ek se doosre mein copy hota hai?", "آج معلومات کن ٹولز میں ہیں، اور کیا کچھ ایک سے دوسرے میں کاپی ہوتا ہے؟", "أي الأدوات تحمل المعلومات اليوم وهل يُنسخ شيء بينها؟"),
        "separate|not connected|different systems|alag alag|الگ الگ|جڑے نہیں|منفصل|غير مترابط",
    ),
    "manual_reports": _h(
        ("reports put together by hand", "reports ka haath se banaya jana", "رپورٹس کا ہاتھ سے بنایا جانا", "إعداد التقارير يدوياً"),
        ("Who prepares the report, from what, and how long does it take?", "Report kaun banata hai, kis se, aur kitna waqt lagta hai?", "رپورٹ کون بناتا ہے، کس سے، اور کتنا وقت لگتا ہے؟", "من يعد التقرير ومن أي مصدر وكم يستغرق؟"),
        "report|reports|manual report|رپورٹ|تقرير|تقارير",
    ),
    "price_competition": _h(
        ("competitors offering lower prices", "muqabil ka kam qeemat par bechna", "مقابل کا کم قیمت پر بیچنا", "منافسون يقدمون أسعاراً أقل"),
        ("Which competitors are you losing customers to, and on what?", "Aap kin muqabil ke haath gahak kho rahe hain, aur kis wajah se?", "آپ کن مقابل کے ہاتھ گاہک کھو رہے ہیں، اور کس وجہ سے؟", "لأي منافسين تخسر عملاء وبسبب ماذا؟"),
        "competitor|competitors|cheaper|lower price|muqabil|sasta|مقابل|سستا|منافس|ارخص",
    ),
    "service_quality_gap": _h(
        ("customers not happy with the service they get", "gahak ko milne wali service se na-khushi", "گاہک کو ملنے والی سروس سے ناخوشی", "عدم رضا العملاء عن الخدمة"),
        ("What do unhappy customers say, in their own words?", "Na-khush gahak apni zabaan mein kya kehte hain?", "ناخوش گاہک اپنی زبان میں کیا کہتے ہیں؟", "ماذا يقول العملاء غير الراضين بكلماتهم؟"),
        "complaint|complaints|unhappy|bad service|shikayat|شکایت|ناخوش|خراب سروس|شكوى|سوء الخدمة",
    ),
    "seasonality": _h(
        ("a seasonal slow period", "mausami sust daur", "موسمی سست دور", "فترة ركود موسمية"),
        ("Did the same months slow down last year as well?", "Kya pichle saal bhi yehi mahine sust the?", "کیا پچھلے سال بھی یہی مہینے سست تھے؟", "هل تباطأت الأشهر نفسها العام الماضي؟"),
        "season|seasonal|ramzan|eid|winter|summer|mausam|موسم|رمضان|عید|موسمي|شتاء|صيف",
    ),
    "owner_bottleneck": _h(
        ("everything depending on the owner's own time", "har cheez ka maalik ke apne waqt par munhasir hona", "ہر چیز کا مالک کے اپنے وقت پر منحصر ہونا", "اعتماد كل شيء على وقت المالك"),
        ("Which decisions or tasks wait for you personally, and how many a week?", "Kaun se faislay ya kaam sirf aap ke intezar mein rukte hain, aur hafte mein kitne?", "کون سے فیصلے یا کام صرف آپ کے انتظار میں رکتے ہیں، اور ہفتے میں کتنے؟", "ما القرارات أو المهام التي تنتظرك شخصياً وكم عددها أسبوعياً؟"),
        "i have to|only me|everything waits|main khud|sab mujh|صرف میں|مجھے خود|انا وحدي|بنفسي",
    ),
    "no_process_owner": _h(
        ("no agreed way of doing this, so it differs each time", "is kaam ka koi tay shuda tareeqa na hona, har baar mukhtalif", "اس کام کا کوئی طے شدہ طریقہ نہ ہونا، ہر بار مختلف", "عدم وجود طريقة متفق عليها فيختلف الأمر كل مرة"),
        ("Is there one agreed way of doing this, and who decides it?", "Kya is kaam ka ek tay shuda tareeqa hai, aur kaun tay karta hai?", "کیا اس کام کا ایک طے شدہ طریقہ ہے، اور کون طے کرتا ہے؟", "هل توجد طريقة واحدة متفق عليها ومن يقررها؟"),
        "no process|no system|no standard|differs|tareeqa nahi|کوئی طریقہ نہیں|بدون نظام|لا نظام",
    ),
}  # fmt: skip

# subtype -> cause keys (most specific), then category, then FALLBACK.
SUBTYPE_CAUSES: dict[str, tuple[str, ...]] = {
    "orders_lost": ("stock_unavailable", "order_processing_delay", "delivery_failure", "customer_unconfirmed", "wrong_contact_data", "cod_payment_issue", "inventory_sync", "communication_gap"),
    "delivery_late": ("courier_unreliable", "dispatch_delay", "order_processing_delay", "wrong_contact_data", "communication_gap"),
    "returns_rto": ("delivery_failure", "wrong_contact_data", "customer_unconfirmed", "cod_payment_issue", "product_mismatch", "courier_unreliable"),
    "order_errors": ("manual_entry", "no_checklist", "handoff_gap", "product_mismatch"),
    "packing_errors": ("manual_entry", "no_checklist", "handoff_gap", "product_mismatch"),
    "stockout": ("supplier_delay", "no_reorder_rule", "demand_not_tracked", "inventory_sync", "no_stock_record"),
    "count_mismatch": ("manual_counting", "no_receiving_check", "no_stock_record", "handoff_gap"),
    "shrinkage_theft": ("manual_counting", "no_receiving_check", "no_stock_record", "handoff_gap"),
    "overstock_dead_stock": ("demand_not_tracked", "no_stock_record", "price_competition"),
    "overstock_ageing": ("demand_not_tracked", "no_stock_record", "price_competition"),
    "receivables_late": ("no_reminder_process", "unclear_terms", "no_follow_up", "no_process_owner"),
    "credit_customers": ("no_reminder_process", "unclear_terms", "no_follow_up", "no_process_owner"),
    "cash_mismatch": ("no_daily_reconciliation", "manual_entry", "unclear_roles"),
    "sales_drop": ("price_competition", "seasonality", "service_quality_gap", "no_follow_up", "stock_unavailable"),
    "slow_response": ("slow_response_process", "unclear_roles", "staff_training", "communication_gap"),
    "complaints": ("slow_response_process", "unclear_roles", "staff_training", "communication_gap"),
    "repeat_low": ("no_follow_up", "service_quality_gap", "no_tracking"),
    "few_leads": ("no_tracking", "no_follow_up"),
    "lead_followup_slow": ("no_follow_up", "slow_response_process", "unclear_roles"),
    "supplier_late": ("supplier_delay", "no_reorder_rule", "no_tracking"),
    "attendance_lateness": ("no_attendance_record", "unclear_roles"),
}  # fmt: skip
CATEGORY_CAUSES: dict[str, tuple[str, ...]] = {
    "stock_inventory": ("no_stock_record", "manual_counting", "supplier_delay", "inventory_sync"),
    "sales_revenue": ("price_competition", "seasonality", "service_quality_gap", "no_follow_up"),
    "cash_collections": ("no_reminder_process", "no_daily_reconciliation", "unclear_terms"),
    "margin_cost": ("no_tracking", "supplier_delay", "manual_entry"),
    "customers_retention": ("slow_response_process", "no_follow_up", "service_quality_gap"),
    "marketing_leads": ("no_tracking", "no_follow_up"),
    "orders_fulfilment": ("stock_unavailable", "order_processing_delay", "delivery_failure", "communication_gap"),
    "suppliers_purchasing": ("supplier_delay", "no_reorder_rule", "no_tracking"),
    "people_staff": ("unclear_roles", "staff_training", "no_attendance_record"),
    "operations_process": ("manual_entry", "no_checklist", "handoff_gap", "no_process_owner"),
    "reporting_visibility": ("manual_reports", "separate_tools", "no_tracking"),
    "tech_systems": ("separate_tools", "manual_entry", "staff_training"),
    "quality_complaints": ("no_checklist", "staff_training", "service_quality_gap"),
    "compliance_admin": ("no_process_owner", "manual_entry", "no_tracking"),
    "communication_coordination": ("communication_gap", "owner_bottleneck", "handoff_gap"),
    "loss_security": ("no_receiving_check", "no_daily_reconciliation", "unclear_roles"),
    "planning_growth": ("demand_not_tracked", "owner_bottleneck", "no_tracking"),
    "customer_experience_digital": ("separate_tools", "slow_response_process", "no_follow_up"),
}  # fmt: skip
FALLBACK_CAUSES = ("communication_gap", "no_process_owner", "no_tracking")

GUESS_PREFIX = {
    "en": "A possibility to check, not a finding: ",
    "roman_ur": "Ek imkaan jo check karni hai, nateeja nahi: ",
    "ur": "ایک امکان جسے جانچنا ہے، نتیجہ نہیں: ",
    "ar": "احتمال يجب التحقق منه وليس نتيجة: ",
}
NOT_CONFIRMED = {
    "en": "not confirmed",
    "roman_ur": "tasdeeq nahi hui",
    "ur": "تصدیق نہیں ہوئی",
    "ar": "غير مؤكد",
}
PACK_PREFIX = {
    "en": "Seen in similar businesses (pack pattern, English only): ",
    "roman_ur": "Milte julte karobar mein yeh bhi dekha gaya (pack, sirf English): ",
    "ur": "ملتے جلتے کاروبار میں یہ بھی دیکھا گیا (پیک، صرف انگریزی): ",
    "ar": "شوهد في أعمال مشابهة (نمط من الحزمة، بالإنجليزية فقط): ",
}
PACK_CHECK = {
    "en": "Does this also happen in your business?",
    "roman_ur": "Kya aap ke karobar mein bhi aisa hota hai?",
    "ur": "کیا آپ کے کاروبار میں بھی ایسا ہوتا ہے؟",
    "ar": "هل يحدث هذا في عملك أيضاً؟",
}
