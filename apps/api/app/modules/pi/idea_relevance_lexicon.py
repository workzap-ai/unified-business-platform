# ruff: noqa: E501
"""Data for `idea_relevance`: topic concepts in English, Roman Urdu, Urdu, Arabic and Hindi.

A concept is a topic field of a small business ("delivery and couriers", "bookings and slots"): the
words an owner uses for the PROBLEM and the words used for a REMEDY of it sit in the same concept,
so "late orders", "delivery delay" and "تأخر التوصيل" all land on one concept without sharing a word.
Each concept is tagged with the taxonomy category keys (`taxonomy.CATEGORIES`) and, where useful,
sub-type keys it belongs to, so a problem record's own `category` and `subtype` also select it.

Term syntax (`terms`, separated by `|`): a phrase of 1 to 4 words matches those words in order; a
trailing `*` on a single word makes it a prefix (`deliver*` matches delivery, delivered). Terms are
written naturally and normalised by `idea_relevance.normalize_text` when the index is built, so
Arabic hamza and tashkeel, Urdu and Arabic letter forms, and digits need no care here.

Language review: the Urdu, Arabic and Hindi terms come from the taxonomy labels, the pack phrases and
the author's own knowledge. They have NOT had a native-speaker review (spec 2.5.1 asks for one).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Concept:
    key: str
    cats: tuple[str, ...]
    subs: tuple[str, ...]
    terms: str  # all languages, `|` separated
    weak: bool = False  # a tool or channel word: never links on its own with generic wording
    context: bool = False  # the kind of business (farm, school, clinic): a setting, not a problem


def _c(
    key: str, cats: str, subs: str, *langs: str, weak: bool = False, context: bool = False
) -> Concept:
    return Concept(key, tuple(cats.split()), tuple(subs.split()), "|".join(langs), weak, context)


CONCEPTS: tuple[Concept, ...] = (
    _c(
        "pay_collect",
        "cash_collections",
        "receivables_late credit_customers deposit_delays",
        "late payment*|pay late|paying late|paid late|unpaid|overdue|outstanding|dues|due date|receivable*|invoice*|collect*|collection*|arrears|owed|rent|rents|fees|tenant*|landlord*|instalment*|installment*|chase*|payment reminder*|bill*|balance due|credit sales|on credit|debtor*",
        "udhaar|udhar|wusooli|wasooli|vasooli|recovery|kiraya|kiraye|kirayedar*|fees|fee|bakaya|baqaya|adaigi|adayegi|payment|payments|invoice*|kist|qist|qarz|dues|paise wapis|paisay wapis|paise nahi",
        "ادھار|وصولی|واجبات|بقایا|کرایہ|کرایے|کرایہ دار*|فیس|فیسیں|ادائیگی*|بل|بلز|انوائس*|قسط|اقساط|قرض|دیر سے ادا*|تاخیر سے ادا*|واجب الادا*",
        "دفع|مدفوع*|مستحقات|تحصيل|فواتير|فاتورة|ايجار|إيجارات|رسوم|قسط|اقساط|مديون*|متأخرات|سداد|ديون|دين|مستاجر*|المستأجر*|مبالغ متأخرة|تأخر السداد|تأخر الدفع|الدفعات",
        "बकाया|वसूली|किराया|किरायेदार*|फीस|भुगतान|उधार|बिल|किस्त|चालान|देर से भुगतान|देर से पैसे",
    ),
    _c(
        "cash_handling",
        "cash_collections loss_security",
        "cash_mismatch cash_handling_risk petty_cash cash_leakage cod_remittance",
        "cash mismatch|cash difference|cash short*|till|cash drawer|petty cash|cash handling|cash count*|deposit*|bank in|cash leak*|cod remittance|cash on delivery payout*|daily closing|day end|reconcil*",
        "cash mismatch|cash kam|cash ghalat|galla|gallay|petty cash|cash count|daily closing|hisaab milana|hisab milana|cod ka paisa|jama karwana",
        "کیش|نقد|گلہ|گلے|پیٹی کیش|حساب ملانا|رقم جمع|ڈپازٹ|روزانہ کلوزنگ",
        "عجز الصندوق|فرق الصندوق|الصندوق|نقدي*|النقد|عهدة|مطابقة|ايداع|تسوية|اغلاق يومي|نثرية",
        "कैश|गल्ला|नकद|जमा|हिसाब मिलान|पेटी कैश",
    ),
    _c(
        "stock_shortage",
        "stock_inventory suppliers_purchasing",
        "stockout slow_replenishment raw_material_shortage supplier_late",
        "stock out*|stockout*|out of stock|run out|running out|runs out|ran out|shortage*|short of|low stock|reorder*|re-order*|restock*|replenish*|ran short|not available|sold out|minimum level",
        "maal khatam|stock khatam|maal kam|stock kam|khatam ho|khatam ho jata|khatam ho jati|reorder|dobara mangwa*|shortage|maal nahi|stock nahi|kami",
        "اسٹاک ختم|مال ختم|ختم ہو|کمی|اسٹاک کم|دوبارہ منگوا*|مال کم|دستیاب نہیں",
        "نفاد|نفد*|نقص المخزون|نقص في|نقص|مخزون منخفض|اعادة الطلب|إعادة طلب|اعادة التخزين|غير متوفر*|نفاذ|تنفد|ينفد|نفدت|اعد الطلب|أعد الطلب|حد ادنى|حدا ادنى|الحد الادنى للمخزون|سريعة البيع",
        "स्टॉक खत्म|माल खत्म|कमी|स्टॉक कम|दोबारा मंगवा*|उपलब्ध नहीं|खत्म हो",
    ),
    _c(
        "stock_excess",
        "stock_inventory sales_revenue",
        "overstock_dead_stock overstock_ageing clearance",
        "overstock*|excess stock|dead stock|slow moving|slow-moving|ageing stock|aging stock|old stock|unsold|not selling|clearance|sit(s|ting)? on shelves|pile of stock|sell off|sell the stock|offload",
        "purana maal|purana stock|dead stock|maal pada|nahi bik|bik nahi|bikta nahi|clearance|sale lagana|stock bechna|maal bechna|zyada maal|zyada stock",
        "پرانا مال|پرانا اسٹاک|ڈیڈ اسٹاک|نہیں بکتا|نہیں بک|فروخت نہیں|زیادہ مال|زیادہ اسٹاک|کلیئرنس|مال پڑا",
        "مخزون راكد|راكد*|مخزون زائد|فائض المخزون|بضاعة قديمة|لا تباع|تصفية|مخزون قديم|بطيئة الحركة|بطيء الحركة",
        "पुराना माल|पुराना स्टॉक|डेड स्टॉक|नहीं बिकता|नहीं बिक|ज्यादा माल|क्लियरेंस|ज्यादा स्टॉक",
    ),
    _c(
        "stock_count",
        "stock_inventory reporting_visibility",
        "count_mismatch no_visibility wrong_location transfers_lost serial_batch_tracking",
        "stock count*|stock take|stocktake|count the stock|inventory count*|tally|stock register|stock record*|stock levels|inventory|know (what|how much) (stock|we have)|stock list|shelf count|batch*|serial number*|lost transfer*|wrong location",
        "stock ginna|stock ginein|stock count|maal ginna|maal ginein|stock ka hisaab|stock register|stock ki list|inventory|pata nahi kitna maal|kitna maal|tally|batch",
        "اسٹاک گن*|اسٹاک کی گنتی|مال گن*|گنتی|اسٹاک رجسٹر|انوینٹری|اسٹاک کا حساب|کتنا مال|اسٹاک کی فہرست|بیچ",
        "جرد|الجرد|سجل المخزون|عد المخزون|عدّ|مطابقة المخزون|قائمة المخزون|كم لدينا|رقم تسلسلي|دفعة|المخزون",
        "स्टॉक गिन*|गिनती|स्टॉक रजिस्टर|इन्वेंटरी|कितना माल|स्टॉक की सूची|बैच",
    ),
    _c(
        "expiry_waste",
        "stock_inventory margin_cost",
        "expiry_wastage wastage_cost",
        "expiry|expir*|spoil*|wastage|waste|wasted|throw away|thrown away|perish*|best before|short dated|short-dated|rot|rotting|fifo|feed wasted",
        "expiry|expire|zaya|zaya ho|kharab ho|phenk|phenkna|wastage|waste|gal jata|sar jata|expiry date|purana maal",
        "ایکسپائری|میعاد|ضائع|خراب ہو|پھینک|ضیاع|سڑ|گل",
        "انتهاء الصلاحية|منتهي الصلاحية|صلاحية|تالف*|هدر|يتلف|يفسد|تفسد|تتلف|تتعفن|تنتهي صلاحيتها|تنتهي الصلاحية|انتهت صلاحيتها|فاسد*|ضياع|تلف|يضيع|مهدر*|نهدر",
        "एक्सपायरी|खराब हो|बर्बाद|फेंक|सड़|समाप्ति तिथि",
    ),
    _c(
        "theft_loss",
        "loss_security",
        "theft_internal theft_external fraud shrinkage_theft void_refund_abuse cctv_gaps",
        "theft|steal*|stolen|shrinkage|fraud*|pilfer*|missing items|items go missing|goes missing|cctv|camera*|void*|refund abuse|loss of goods|lost goods|dishonest|cheating|embezzl*",
        "chori|chor|churaya|churai|nuksan|ghalat bill|fraud|cctv|camera|ghaib|gum ho|gayab|dhoka|beimani",
        "چوری|چور|چرا*|نقصان|فراڈ|سی سی ٹی وی|کیمرہ|کیمرے|غائب|گم ہو|دھوکہ|بے ایمانی",
        "سرقة|سرق*|سارق*|احتيال|غش|تلاعب|كاميرا|كاميرات|مفقود*|اختلاس|ضياع البضاعة|خسارة البضاعة|نقص البضاعة",
        "चोरी|चोर|नुकसान|धोखाधड़ी|सीसीटीवी|कैमरा|गायब|बेईमानी",
    ),
    _c(
        "sales_drop",
        "sales_revenue",
        "sales_drop branch_underperforming target_missed seasonal_dip conversion_low basket_small salesforce_performance no_sales_visibility channel_conflict",
        "sales drop*|sales are down|sales down|low sales|lower sales|fewer sales|revenue|footfall|walk-ins|conversion|conversions|sales target*|slow season|slow business|quiet season|average order|basket size|upsell*|cross-sell*|salesm[ae]n|sales team|sales person|sales rep*",
        "bikri kam|bikri|sale kam|sale girna|bikri gir|orders kam|footfall|gahak kam|season|slow season|business slow|mandi|target|salesman|sales team|upsell",
        "سیل کم|بکری|بکری کم|سیل گر|آرڈر کم|گاہک کم|سیزن|مندی|ٹارگٹ|سیلز مین|سیلز ٹیم",
        "المبيعات|مبيعات|انخفاض المبيعات|ايرادات|قلة المبيعات|حركة الزبائن|موسم|ركود|هدف المبيعات|مندوب*|فريق المبيعات|متوسط الطلب",
        "बिक्री|बिक्री कम|सेल कम|ग्राहक कम|सीजन|मंदी|टारगेट|सेल्समैन",
    ),
    _c(
        "pricing",
        "sales_revenue margin_cost",
        "pricing_errors discount_abuse margin_unknown margin_shrinking price_increases_supplier",
        "price*|pricing|discount*|offer*|promo*|mark ?up|markdown|margin*|profit*|cost price|selling price|rate list|price list|price increase*|cheaper|expensive|undercut*|costs? (keep|are) (going )?up",
        "qeemat|qimat|price|rate|rates|discount|offer|munafa|profit|margin|mehnga|mehngi|sasta|rate list|price list|kharcha",
        "قیمت|قیمتیں|ریٹ|ریٹس|ڈسکاؤنٹ|رعایت|آفر|منافع|مارجن|مہنگا|مہنگی|سستا|پرائس لسٹ",
        "سعر|اسعار|خصم|خصومات|عرض|عروض|هامش|ربح|ارباح|تكلفة|تكاليف|غالي|رخيص|قائمة الاسعار",
        "कीमत|दाम|रेट|डिस्काउंट|छूट|ऑफर|मुनाफा|मार्जिन|महंगा|सस्ता|प्राइस लिस्ट",
    ),
    _c(
        "cost_control",
        "margin_cost",
        "cost_overruns utility_costs rent freight_costs hidden_costs currency_exposure",
        "expenses|expense|overheads?|electricity bill*|utility bill*|utilities|fuel cost*|fuel|running costs?|cost overrun*|hidden cost*|cut costs?|save money|savings|freight cost*|diesel|petrol|gas bill|power bill",
        "kharcha|kharche|akhrajat|bijli ka bill|bijli|bill|petrol|diesel|fuel|bachat|kharcha kam|overheads",
        "خرچہ|خرچے|اخراجات|بجلی کا بل|بجلی|پیٹرول|ڈیزل|ایندھن|بچت|خرچ کم",
        "مصاريف|مصروفات|تكاليف التشغيل|فاتورة الكهرباء|كهرباء|وقود|بنزين|ديزل|توفير|ادخار|تقليل التكاليف",
        "खर्च|खर्चे|बिजली का बिल|बिजली|पेट्रोल|डीजल|ईंधन|बचत",
    ),
    _c(
        "retention",
        "customers_retention",
        "repeat_low churn_subscription loyalty no_customer_data",
        "repeat customer*|repeat business|come back|coming back|first visit|second visit|return customer*|returning customer*|retention|retain*|loyal*|churn*|cancel(s|led|ling)? (their )?(membership|subscription)|stop coming|stopped coming|membership renewal*|renew*|lapsed|win back|first month|new members?|members? (leave|cancel|drop)|regulars?|follow ?up (with )?(customers|members)",
        "wapas|wapis|dobara aana|dobara aate|repeat gahak|repeat customer|loyal|loyalty|loyalty card|pehli visit|dusri visit|membership|renew|cancel kar|aana band|aana chor|gahak wapas|regular gahak|pehle mahine",
        "واپس|دوبارہ آ|دوبارہ آتے|ریپیٹ|وفادار|لائلٹی|لایلٹی|پہلی وزٹ|دوسری وزٹ|ممبرشپ|ممبر*|تجدید|منسوخ|آنا بند|آنا چھوڑ|پہلے مہینے|پرانے گاہک",
        "عودة العملاء|يعودون|يعود|العودة|للعودة|عودة|يرجعون|الزيارة الاولى|زيارة ثانية|عملاء متكررون|ولاء|اشتراك*|عضوية|اعضاء|تجديد|الغاء|يتوقفون|يتوقف|فقدان العملاء|الشهر الاول|زبائن دائمون",
        "वापस आ|दोबारा आ|रिपीट|वफादार|लॉयल्टी|पहली विजिट|दूसरी विजिट|मेंबरशिप|सदस्य|नवीनीकरण|रद्द|आना बंद|पहले महीने",
    ),
    _c(
        "complaints",
        "customers_retention quality_complaints",
        "complaints reviews_bad service_quality after_sales",
        "complain*|complaint*|review*|rating*|feedback|unhappy|angry|dissatisf*|bad service|poor service|negative review*|refund*|apolog*|survey*|wrong or cold|arrive cold|arrive wrong|stars?",
        "shikayat|shikayaat|complaint|review|reviews|rating|feedback|naraaz|naraz|gussa|bura review|refund|maafi|ghalat ya thande|thanda khana",
        "شکایت|شکایات|کمپلین|ریویو|ریویوز|ریٹنگ|فیڈ بیک|ناراض|غصہ|برا ریویو|ریفنڈ|معافی|غلط یا ٹھنڈے|ٹھنڈا",
        "شكوى|شكاوى|تقييم|تقييمات|مراجعة سلبية|مراجعات|ملاحظات|غاضب*|غير راض*|استرداد|اعتذار|استبيان|خدمة سيئة|باردة",
        "शिकायत|रिव्यू|रेटिंग|फीडबैक|नाराज|गुस्सा|खराब रिव्यू|रिफंड|माफी|ठंडा",
    ),
    _c(
        "leads_marketing",
        "marketing_leads sales_revenue",
        "few_leads lead_quality ad_spend_waste no_tracking social_media_inconsistent brand_awareness lead_followup_slow campaign_roi_unknown marketplace_visibility",
        "leads?|new customers|more customers|advertis*|ads|marketing|promot*|campaign*|social media|instagram|facebook|tiktok|whatsapp status|reels?|posts?|referral*|word of mouth|brand awareness|visibility|enquiries|inquiries|followers?|boost|flyers?|brochure*",
        "naye gahak|gahak|ishtehaar|ishtihar|ads|marketing|promotion|campaign|social media|instagram|facebook|status|reel|reels|post|referral|enquiry|enquiries|inquiry|pooch gooch|followers|pamphlet|flyer",
        "نئے گاہک|اشتہار|اشتہارات|مارکیٹنگ|پروموشن|مہم|سوشل میڈیا|انسٹاگرام|فیس بک|ریل|ریلز|پوسٹ|ریفرل|انکوائری|انکوائریاں|پوچھ گچھ|فالوورز|پمفلٹ|فلائر",
        "عملاء جدد|عملاء جدد|اعلان*|اعلانات|تسويق|ترويج|حملة|وسائل التواصل|انستغرام|فيسبوك|ستوري|ريلز|منشور*|احالة|استفسار*|متابعون|نشرة",
        "नए ग्राहक|विज्ञापन|मार्केटिंग|प्रमोशन|अभियान|सोशल मीडिया|इंस्टाग्राम|फेसबुक|रील|पोस्ट|रेफरल|पूछताछ|फॉलोअर|पम्फलेट",
    ),
    _c(
        "online_presence",
        "customer_experience_digital marketing_leads tech_systems",
        "website_slow_broken no_online_ordering marketplace_listing app_issues website_issues integration_marketplace",
        "website*|web site|online order*|online ordering|online shop|online store|app|apps|mobile app|listing*|google maps|google business|marketplace*|daraz|checkout|online payment*|payment link*|portal|e-?commerce|link in bio",
        "website|online order|online ordering|online shop|app|listing|google maps|marketplace|daraz|checkout|online payment|payment link|portal",
        "ویب سائٹ|آن لائن آرڈر|آن لائن|ایپ|لسٹنگ|گوگل میپ|مارکیٹ پلیس|دراز|چیک آؤٹ|ادائیگی کا لنک|پورٹل",
        "موقع الكتروني|موقع|طلب عبر الانترنت|طلبات اونلاين|متجر الكتروني|تطبيق|قائمة جوجل|خرائط جوجل|سوق الكتروني|الدفع الالكتروني|بوابة|الدفع عند الخروج|اونلاين|اون لاين",
        "वेबसाइट|ऑनलाइन ऑर्डर|ऑनलाइन|ऐप|लिस्टिंग|गूगल मैप|मार्केटप्लेस|चेकआउट|पेमेंट लिंक|पोर्टल",
    ),
    _c(
        "orders",
        "orders_fulfilment",
        "orders_lost order_errors order_tracking packing_errors multi_channel_orders pre_orders_custom",
        "order*|wrong item*|wrong order*|missing item*|packing|packed|pack |packaging|dispatch*|lost order*|order mistakes?|order errors?|pre-?orders?|custom orders?|order slip*|order sheet*|order status|order book|orders? (on|via|through) whatsapp",
        "order|orders|ghalat item|ghalat order|packing|pack|dispatch|order lost|order bhool|order ghalat|pre order|custom order|order slip|order sheet|order status|order ka status",
        "آرڈر|آرڈرز|غلط آئٹم|غلط آرڈر|پیکنگ|ڈسپیچ|آرڈر گم|آرڈر بھول|پری آرڈر|کسٹم آرڈر|آرڈر سلپ|آرڈر شیٹ|آرڈر کی حالت",
        "طلب|طلبات|الطلب|الطلبات|صنف خاطئ|طلب خاطئ|تغليف|تعبئة|ارسال|طلب مفقود|طلبات مفقودة|طلب مسبق|طلب مخصص|ورقة الطلب|حالة الطلب|اخطاء الطلبات",
        "ऑर्डर|गलत आइटम|गलत ऑर्डर|पैकिंग|डिस्पैच|ऑर्डर गुम|प्री ऑर्डर|कस्टम ऑर्डर|ऑर्डर स्लिप|ऑर्डर की स्थिति",
    ),
    _c(
        "delivery",
        "orders_fulfilment",
        "delivery_late delivery_cost rider_management returns_rto order_tracking",
        "deliver*|delivery delay*|late deliver*|late orders?|late parcels?|late loads?|arrive late|arrives late|arrived late|reach(es)? (customers )?late|courier*|rider*|driver*|parcel*|tracking|track(ing)? number*|shipment*|shipping|ship |logistics|route*|checkpoint*|trip*|dispatcher*|truck*|loads?|return(ed)? parcels?|rto|refused parcels?|where is my order|where their order is",
        "delivery|deliveries|dair se|der se pohanch|late delivery|late orders|courier|rider|riders|driver|driver*|parcel|parcels|tracking|tracking number|shipment|shipping|logistics|route|checkpoint|trip|dispatcher|truck|trucks|load|loads|rto|wapis aane wale parcel|order kahan hai|kahan hai",
        "ڈیلیوری|دیر سے پہنچ|دیر سے پہنچتی|دیر سے آ|کوریئر|کورئیر|رائیڈر|ڈرائیور*|پارسل*|ٹریکنگ|ٹریکنگ نمبر|شپمنٹ|شپنگ|لاجسٹکس|روٹ|چیک پوائنٹ*|ٹرپ|ڈسپیچر*|ٹرک*|لوڈ|واپس آنے والے پارسل|آرڈر کہاں",
        "توصيل|توصيلات|التوصيل|تأخر التوصيل|تاخر التوصيل|تصل متأخرة|تصل متاخرة|توصيل*|شركة الشحن|شركة شحن|الشحن|شحن|شحنة|شحنات|مندوب التوصيل|سائق*|سواق|طرد|طرود|التتبع|رقم التتبع|لوجستي*|مسار|نقطة تفتيش|نقاط|رحلة|رحلات|شاحنة|شاحنات|مرسل|مرتجعات الشحن|اين طلبي",
        "डिलीवरी|देर से पहुँच|देर से पहुंच|देर से|कूरियर|राइडर|ड्राइवर*|पार्सल*|ट्रैकिंग|ट्रैकिंग नंबर|शिपमेंट|शिपिंग|लॉजिस्टिक्स|रूट|चेकपॉइंट|ट्रिप|डिस्पैचर|ट्रक*|लोड|ऑर्डर कहाँ",
    ),
    _c(
        "suppliers",
        "suppliers_purchasing",
        "supplier_late supplier_quality po_tracking buying_wrong_items price_comparison import_delays minimum_orders supplier_communication credit_terms",
        "supplier*|vendor*|purchas*|purchase order*|buying|procure*|wholesaler*|import*|minimum order*|credit terms|supplier delay*|supplier late|supply chain|restock from",
        "supplier|suppliers|vendor|khareed|kharidari|purchase|purchasing|wholesaler|import|minimum order|supplier late|supplier ki dair|maal mangwana",
        "سپلائر|سپلائرز|وینڈر|خریداری|خرید|پرچیز|ہول سیلر|امپورٹ|کم از کم آرڈر|سپلائر کی دیر|مال منگوانا",
        "مورد|موردين|الموردون|المورد|مشتريات|شراء|مورّد*|تاجر جملة|استيراد|الحد الادنى للطلب|تأخر المورد|تاخر المورد|سلسلة الامداد",
        "सप्लायर|वेंडर|खरीद|खरीदारी|थोक|आयात|न्यूनतम ऑर्डर|सप्लायर की देरी",
    ),
    _c(
        "staff_attendance",
        "people_staff",
        "attendance_lateness shift_scheduling overtime",
        "attendance|late (for work|to work|arrival)|staff (arrive|arrives|come|comes|arriving|coming) late|team (arrives|comes|arrive|come) late|workers? (arrive|come|comes|arrives) late|come late to work|absent|absence|no-show staff|shift*|roster*|rota|scheduling staff|staff schedule|overtime|clock in|punch|timekeeping|leave requests?|staff late",
        "attendance|staff late aate|staff dair se aate|team dair se aati|ghair hazir|chutti|chhutti|shift|roster|overtime|staff late|punch|waqt par nahi aate",
        "حاضری|عملہ دیر|ٹیم دیر|اسٹاف دیر|کام پر دیر|غیر حاضر|چھٹی|چھٹیاں|شفٹ|شفٹس|روسٹر|اوور ٹائم|عملہ دیر|پنچ|وقت پر نہیں",
        "حضور|الحضور|غياب|غائب*|تأخر الموظف*|تاخر الموظف*|الموظفون يتأخرون|الموظفين يتأخرون|الفريق يتأخر|يتأخر عن العمل|يتاخر عن العمل|وردية|ورديات|جدول الدوام|جدول المناوبات|عمل اضافي|اجازة|اجازات|بصمة",
        "हाजिरी|स्टाफ देर|टीम काम पर देर|काम पर देर|गैर हाजिर|छुट्टी|शिफ्ट|रोस्टर|ओवरटाइम|कर्मचारी देर|पंच|समय पर नहीं",
    ),
    _c(
        "staff_skills",
        "people_staff",
        "turnover hiring_difficulty training performance_unknown accountability commission_disputes trust_honesty payroll_errors",
        "staff turnover|turnover|quit|quitting|leave the job|hire|hiring|recruit*|train*|onboard*|skills?|performance|accountab*|responsib*|salary|salaries|payroll|wages?|commission*|incentive*|bonus*|motivat*|new staff|staff (leave|quit)|employees?|workers?|apprentice*|mechanic*|cooks?|stylists?|teachers?|nurses?|cleaners?|receptionist*|waiters?|assistant*",
        "staff chhor|staff chhod|naukri chhor|hire|hiring|bharti|training|trainer|salary|tankhwah|tankhah|payroll|commission|bonus|incentive|mulazim*|mulazmeen|karigar|mistri|cook|receptionist|waiter|assistant|staff|worker|workers",
        "عملہ چھوڑ|نوکری چھوڑ|بھرتی|ٹریننگ|تربیت|تنخواہ|تنخواہیں|پے رول|کمیشن|بونس|ملازم|ملازمین|کاریگر|مستری|ریسیپشنسٹ|ویٹر|اسسٹنٹ|عملہ|ورکر|ورکرز|اساتذہ|ٹیچر*",
        "دوران الموظفين|ترك العمل|يترك العمل|توظيف|توظف|وظّف*|وظف*|تدريب|راتب|رواتب|عمولة|عمولات|حوافز|مكافأة|موظف*|موظفين|عامل|عمال|عاملين|مساعد*|فني*|طباخ*|معلم*|مدرس*|موظفة|موظف استقبال|موظفة استقبال|موظفو الاستقبال|مسؤولية",
        "स्टाफ छोड़|नौकरी छोड़|भर्ती|ट्रेनिंग|प्रशिक्षण|वेतन|तनख्वाह|पेरोल|कमीशन|बोनस|कर्मचारी|कारीगर|मिस्त्री|रिसेप्शनिस्ट|वेटर|असिस्टेंट|स्टाफ|वर्कर|शिक्षक",
    ),
    _c(
        "process_manual",
        "operations_process",
        "manual_work duplicate_entry bottleneck approvals_slow no_sop quality_inconsistent capacity checklists_not_done handoffs",
        "manual*|by hand|paperwork|duplicate entr*|enter(ing)? (the )?(data|twice)|bottleneck*|approval*|sop|procedure*|process|checklist*|handoff*|hand over|handover|capacity|backlog|workflow|overload*|too busy|rush|peak hour*|peak time*|kitchen|oven|prep|queue*|waiting time|wait time|wait too long|long wait",
        "manual|haath se|kaghaz|dobara entry|bottleneck|approval|sop|checklist|handover|capacity|backlog|workflow|rush|peak|kitchen|oven|tayyari|queue|line|intezar|intezaar|bohat intezar",
        "دستی|ہاتھ سے|کاغذ|دوبارہ اندراج|رکاوٹ|منظوری|چیک لسٹ|ہینڈ اوور|صلاحیت|رش|پیک|کچن|اوون|تیاری|قطار|لائن|انتظار|بہت انتظار",
        "يدوي|يدويا|ورقي|ادخال مكرر|اختناق|موافقات|موافقة|قائمة تحقق|تسليم|سعة|ازدحام|ذروة|وقت الذروة|مطبخ|فرن|تحضير|طابور|انتظار|وقت الانتظار",
        "हाथ से|कागज|दोबारा एंट्री|रुकावट|मंजूरी|चेकलिस्ट|हैंडओवर|क्षमता|भीड़|पीक|किचन|ओवन|तैयारी|कतार|लाइन|इंतजार",
    ),
    _c(
        "reporting",
        "reporting_visibility",
        "reports_late reports_wrong data_scattered no_dashboard owner_blind branch_comparison kpi_undefined manual_reports",
        "report*|dashboard*|visibility|kpi*|figures|numbers|data is scattered|scattered data|owner blind|don't know (how|what)|summary|monthly summary|spreadsheet*|excel|sheet*|compare branches|branch comparison|track(ing)? progress",
        "report|reports|dashboard|visibility|kpi|figures|numbers|hisaab|hisab|pata nahi chalta|summary|excel|sheet|branches ka muqabla|record",
        "رپورٹ|رپورٹس|ڈیش بورڈ|اعداد و شمار|حساب|خلاصہ|ایکسل|شیٹ|برانچ کا موازنہ|ریکارڈ|پتا نہیں چلتا",
        "تقرير|تقارير|لوحة المعلومات|لوحة بيانات|رؤية|مؤشرات|ارقام|ملخص|اكسل|جدول|مقارنة الفروع|سجل|سجلات",
        "रिपोर्ट|डैशबोर्ड|आंकड़े|हिसाब|सारांश|एक्सेल|शीट|ब्रांच की तुलना|रिकॉर्ड",
    ),
    _c(
        "software_tools",
        "tech_systems operations_process",
        "pos_issues software_not_connected outdated_system no_system system_downtime vendor_lock whatsapp_overload excel_dependency data_loss user_adoption",
        "software|system*|pos|crm|erp|tool*|technology|digital|automat*|integrat*|sync*|data loss|lost data|crash*|downtime|outdated|backup",
        "software|system|pos|crm|erp|tool|technology|digital|automation|automatic|sync|data gum|crash|downtime|purana system|backup",
        "سافٹ ویئر|سسٹم|پی او ایس|ٹیکنالوجی|ڈیجیٹل|آٹومیشن|خودکار|ڈیٹا ضائع|کریش|پرانا سسٹم|بیک اپ",
        "برنامج|برمجيات|نظام|نقطة بيع|تقنية|تكنولوجيا|رقمي|اتمتة|اتوماتيكي|مزامنة|فقدان البيانات|عطل|نظام قديم|نسخ احتياطي",
        "सॉफ्टवेयर|सिस्टम|पीओएस|तकनीक|डिजिटल|ऑटोमेशन|अपने आप|डेटा खो|क्रैश|पुराना सिस्टम|बैकअप",
        weak=True,
    ),
    _c(
        "whatsapp_messages",
        "communication_coordination customers_retention",
        "info_lost_in_whatsapp customer_communication slow_response lead_followup_slow chat_overload tasks_dropped",
        "whatsapp|messages?|chat|chats|reply|replies|respond*|response time|unanswered|no reply|never get a reply|enquir*|inquir*|calls?|phone calls?|calling|follow ?up|lost between|shared list|shared inbox|group chat|text message*|sms|notify|notification*|update(s)? (to )?customers?|keep customers informed|status updates?",
        "whatsapp|message|messages|chat|jawab|reply|jawab nahi|jawab nahi jata|enquiry|enquiries|inquiry|call|phone|phone karte|follow up|followup|sms|update|updates|status|khabar|bata do|bata dein",
        "واٹس ایپ|میسج|میسجز|پیغام|چیٹ|جواب|جواب نہیں|انکوائری|انکوائریاں|کال|فون|فالو اپ|ایس ایم ایس|اپ ڈیٹ|اپڈیٹ|خبر|بتا دیں|بتائیں",
        "واتساب|رسالة|رسائل|دردشة|محادثة|رد|الرد|ردود|بدون رد|استفسار*|اتصال|مكالمة|مكالمات|هاتف|متابعة|رسالة نصية|تحديث|تحديثات|اشعار|اخبار",
        "व्हाट्सएप|मैसेज|संदेश|चैट|जवाब|जवाब नहीं|पूछताछ|कॉल|फोन|फॉलो अप|एसएमएस|अपडेट|सूचना|बता दें",
    ),
    _c(
        "bookings",
        "customer_experience_digital operations_process",
        "booking_appointments",
        "book*|appointment*|reservation*|overlap*|double[- ]?book*|slot*|calendar|diary|schedul*|no-?show*|cancellation*|cancel(s|led)? (booking|appointment)|walk-?ins?|time slots?|available times?|courts?|turf|pitch|tables? (booking|reservation)|reschedul*",
        "booking|bookings|double booking|appointment|appointments|reservation|slot|slots|calendar|diary|schedule|no show|cancel|cancellation|court|turf|reschedule|ek hi slot|wahi slot|time slot",
        "بکنگ|بکنگز|ڈبل بکنگ|اپائنٹمنٹ|ریزرویشن|سلاٹ|سلاٹس|کیلنڈر|ڈائری|شیڈول|نو شو|منسوخ|کورٹ|کورٹس|ٹرف|ایک ہی سلاٹ|ٹائم سلاٹ",
        "حجز|حجوزات|حجز مزدوج|حجوزات مزدوجة|موعد|مواعيد|موعد الملعب|تعارض|تداخل|تتداخل|جدولة|تقويم|دفتر المواعيد|لا يحضر|الغاء الحجز|ملعب|ملاعب|جلسة|حجوزات متداخلة|فترة زمنية",
        "बुकिंग|डबल बुकिंग|अपॉइंटमेंट|आरक्षण|स्लॉट|कैलेंडर|डायरी|शेड्यूल|नो शो|रद्द|कोर्ट|एक ही स्लॉट|टाइम स्लॉट",
    ),
    _c(
        "capacity_idle",
        "operations_process sales_revenue",
        "capacity seasonal_dip",
        "empty slots?|idle|idle time|unused|underused|under-?utili[sz]ed|quiet (hours|times)|off-?peak|fill (the )?(empty|slots)|spare capacity|empty seats?|empty tables?|empty rooms?|vacant|vacancy|vacancies",
        "khali|khali slots|idle|unused|off peak|khali waqt|khali tables|khali kamre",
        "خالی|خالی سلاٹ|بیکار|استعمال نہیں|آف پیک|خالی وقت|خالی ٹیبلز|خالی کمرے",
        "فارغ|شاغر|غير مستغل|ساعات الهدوء|فترات الهدوء|مقاعد فارغة|طاولات فارغة|غرف فارغة|اوقات فارغة",
        "खाली|खाली स्लॉट|बेकार|उपयोग नहीं|ऑफ पीक|खाली समय|खाली कमरे",
    ),
    _c(
        "equipment",
        "operations_process quality_complaints",
        "maintenance_downtime product_defects rework",
        "equipment|machine*|breakdown*|broke down|repair*|spare parts?|parts?|maintenance|servicing|fault*|defect*|rework|cooling|ac |generator|fridge|refrigerat*|heat|temperature|vehicle*|tyres?|engine",
        "machine|machines|breakdown|kharab|repair|spare parts|parts|part|maintenance|service|fault|defect|rework|cooling|generator|fridge|garmi|temperature|gaari|gari|engine",
        "مشین|مشینیں|خرابی|خراب|مرمت|اسپیئر پارٹس|پارٹس|پارٹ|مینٹیننس|سروس|نقص|ری ورک|کولنگ|جنریٹر|فریج|گرمی|درجہ حرارت|گاڑی|انجن",
        "معدات|ماكينة|ماكينات|اعطال|عطل|تعطل|اصلاح|تصليح|قطع غيار|صيانة|خلل|عيوب|عيب|اعادة عمل|تبريد|مولد|ثلاجة|حرارة|حر|درجة الحرارة|مركبة|سيارة|محرك",
        "मशीन|खराबी|खराब|मरम्मत|स्पेयर पार्ट्स|पार्ट|मेंटेनेंस|सर्विस|दोष|रीवर्क|कूलिंग|जनरेटर|फ्रिज|गर्मी|तापमान|गाड़ी|इंजन",
    ),
    _c(
        "job_tracking",
        "operations_process communication_coordination",
        "handoffs tasks_dropped",
        "job slip*|job card*|work order*|job status|status of (the )?(job|repair|work)|ready when|when (will|is) (it|my car|the car) ready|ready for pickup|pick-?up|collection date|promised date|turnaround|progress",
        "job slip|job card|work order|job status|kab tayyar|tayyar hogi|tayyar hogi|pickup|date|marhala|progress|kaam ka status",
        "جاب سلپ|جاب کارڈ|ورک آرڈر|کب تیار|تیار ہوگی|پک اپ|مرحلہ|کام کی حالت|پیش رفت",
        "بطاقة العمل|امر العمل|حالة العمل|متى تجهز|جاهزة|استلام|موعد التسليم|مرحلة|تقدم",
        "जॉब स्लिप|जॉब कार्ड|वर्क ऑर्डर|कब तैयार|तैयार होगी|पिकअप|चरण|प्रगति",
    ),
    _c(
        "compliance",
        "compliance_admin",
        "tax_filing_effort licences_renewals audits documentation contracts_tracking regulatory_reporting record_keeping",
        "tax*|vat|fbr|licen[cs]e*|permit*|audit*|compliance|regulat*|documents?|documentation|paperwork|contract*|filing|filings|returns? deadline|record keeping|records",
        "tax|fbr|licence|license|permit|audit|compliance|document|documents|contract|filing|deadline|record keeping|kaghazat|kaghazi",
        "ٹیکس|ایف بی آر|لائسنس|پرمٹ|آڈٹ|دستاویزات|دستاویز|معاہدہ|فائلنگ|ڈیڈ لائن|کاغذات|کاغذی",
        "ضريبة|ضرائب|ضريبة القيمة المضافة|رخصة|رخص|تصريح|تدقيق|امتثال|مستندات|وثائق|عقد|عقود|تقديم الاقرار|موعد نهائي|سجلات",
        "टैक्स|एफबीआर|लाइसेंस|परमिट|ऑडिट|दस्तावेज|अनुबंध|फाइलिंग|डेडलाइन|कागजात",
    ),
    _c(
        "team_coordination",
        "communication_coordination people_staff",
        "branches_not_aligned owner_bottleneck meetings_wasteful field_team_visibility communication_internal",
        "team|branches|branch|coordinat*|alignment|aligned|owner bottleneck|everything depends on me|meetings?|instructions?|handover|shared (list|sheet|board)|task list|assign*|delegat*|who is doing|responsible for",
        "team|branches|branch|coordination|meeting|meetings|instructions|handover|shared list|task list|assign|delegate|zimmedar|zimmedari|sab kuch mujh par",
        "ٹیم|برانچز|برانچ|کوآرڈینیشن|میٹنگ|میٹنگز|ہدایات|مشترکہ فہرست|ٹاسک لسٹ|ذمہ دار|ذمہ داری|سب کچھ مجھ پر",
        "فريق|فروع|فرع|تنسيق|اجتماع|اجتماعات|تعليمات|قائمة مشتركة|قائمة المهام|مسؤول|مسؤولية|كل شيء علي",
        "टीम|ब्रांच|समन्वय|मीटिंग|निर्देश|साझा सूची|टास्क लिस्ट|जिम्मेदार|जिम्मेदारी|सब कुछ मुझ पर",
    ),
    _c(
        "growth_planning",
        "planning_growth",
        "expansion_pains forecasting budgeting_process new_branch_setup franchise_control seasonal_planning succession_family",
        "expan*|new branch*|open(ing)? (a )?(new )?(branch|shop|outlet)|forecast*|budget*|plan(ning)? (ahead|the season)|seasonal|season|succession|family business|franchise*|grow(th)?|scale|scaling",
        "expansion|naya branch|nayi branch|forecast|budget|planning|season|seasonal|family business|franchise|barhna|growth",
        "توسیع|نئی برانچ|فورکاسٹ|بجٹ|منصوبہ بندی|سیزن|فیملی بزنس|فرنچائز|ترقی",
        "توسع|فرع جديد|توقع|توقعات|ميزانية|تخطيط|موسم|موسمي|عمل عائلي|امتياز تجاري|نمو",
        "विस्तार|नई ब्रांच|पूर्वानुमान|बजट|योजना|सीजन|पारिवारिक व्यवसाय|फ्रेंचाइजी|वृद्धि",
    ),
    _c(
        "students_school",
        "customers_retention cash_collections",
        "",
        "students?|pupils?|parents?|school|class(es|room)?|teachers?|exam*|homework|admission*|curriculum|tuition|academy|coaching",
        "student|students|talib ilm|parents|walidain|school|class|teacher|exam|admission|tuition|academy",
        "طلبہ|طالب علم|والدین|اسکول|کلاس|استاد|امتحان|داخلہ|ٹیوشن|اکیڈمی",
        "طلاب|طالب|اولياء الامور|مدرسة|صف|فصل|معلم|امتحان|قبول|دروس خصوصية|اكاديمية",
        "छात्र|विद्यार्थी|अभिभावक|स्कूल|कक्षा|शिक्षक|परीक्षा|दाखिला|ट्यूशन|अकादमी",
        context=True,
    ),
    _c(
        "health_clinic",
        "customers_retention operations_process",
        "",
        "patient*|doctor*|clinic|prescription*|medicine*|pharmac*|nurse*|treatment|diagnos*|dental|lab test*|medical",
        "mareez|mareezon|patient|patients|doctor|clinic|prescription|prescriptions|medicine|medicines|dawai|dawaiyan|pharmacy|nurse|ilaaj|ilaj",
        "مریض|مریضوں|ڈاکٹر|کلینک|نسخہ|نسخے|پریسکرپشن|دوا|دوائی|ادویات|فارمیسی|نرس|علاج",
        "مريض|مرضى|طبيب|دكتور|عيادة|وصفة|وصفات|دواء|ادوية|صيدلية|ممرضة|علاج",
        "मरीज|डॉक्टर|क्लिनिक|पर्ची|दवा|दवाइयां|फार्मेसी|नर्स|इलाज",
        context=True,
    ),
    _c(
        "food_service",
        "operations_process quality_complaints margin_cost",
        "",
        "restaurant*|menu|dish(es)?|chef*|kitchen|cook*|food|meal*|lunch|dinner|breakfast|table*|waiter*|covers|food cost|dine|banquet|catering|caterer*",
        "restaurant|menu|dish|dishes|chef|kitchen|cook|cooks|khana|lunch|dinner|table|waiter|food cost|banquet|catering|caterer|degh",
        "ریسٹورنٹ|مینو|ڈش|ڈشز|شیف|کچن|باورچی|کھانا|لنچ|ڈنر|ٹیبل|ویٹر|فوڈ کاسٹ|بینکوئٹ|کیٹرنگ|کیٹرر|دیگ",
        "مطعم|قائمة الطعام|طبق|اطباق|طاه|مطبخ|طباخ|طعام|غداء|عشاء|طاولة|نادل|تكلفة الطعام|قاعة|تموين|متعهد",
        "रेस्टोरेंट|मेन्यू|डिश|शेफ|किचन|रसोइया|खाना|लंच|डिनर|टेबल|वेटर|फूड कॉस्ट|बैंक्वेट|कैटरिंग",
        context=True,
    ),
    _c(
        "livestock_farm",
        "stock_inventory loss_security margin_cost",
        "",
        "birds?|poultry|chicks?|flock*|shed*|feed|fodder|eggs?|mortality|vaccin*|livestock|cattle|cows?|buffalo*|milk|farm|hens?|broilers?|layers?|died|dying|die every",
        "parinde|parinda|murghi|murghiyan|chuzay|chooze|shed|chara|anda|anday|mortality|vaccine|vaccination|janwar|gaye|bhains|doodh|farm|mar jate|mar rahe|mar gaye",
        "پرندے|پرندہ|مرغی|مرغیاں|چوزے|شیڈ|چارہ|چارے|انڈے|انڈا|ویکسین|جانور|گائے|بھینس|دودھ|فارم|مر جاتے|مر رہے|مر گئے",
        "طيور|طائر|طيور الدواجن|دواجن|دجاج|فراخ|كتاكيت|عنبر|علف|بيض|نفوق|لقاح|تطعيم|ماشية|ابقار|بقر|جاموس|حليب|مزرعة|تموت|يموت|ماتت",
        "पक्षी|मुर्गी|मुर्गियां|चूजे|शेड|चारा|अंडे|मृत्यु|टीका|पशु|गाय|भैंस|दूध|फार्म|मर जाते|मर रहे",
        context=True,
    ),
    _c(
        "fitness_beauty",
        "customers_retention",
        "",
        "gym|fitness|trainer*|workout*|classes|class schedule|members?|membership*|salon|stylist*|hair|beauty|facial|spa|massage|treatments?",
        "gym|fitness|trainer|workout|class|classes|member|members|membership|salon|stylist|hair|beauty|facial|spa|massage",
        "جم|فٹنس|ٹرینر|ورزش|کلاس|کلاسز|ممبر|ممبرز|ممبرشپ|سیلون|اسٹائلسٹ|بال|بیوٹی|فیشل|سپا|مساج",
        "نادي رياضي|لياقة|مدرب|تمرين|حصة|حصص|عضو|اعضاء|عضوية|صالون|مصفف|شعر|تجميل|سبا|مساج",
        "जिम|फिटनेस|ट्रेनर|वर्कआउट|क्लास|सदस्य|मेंबरशिप|सैलून|स्टाइलिस्ट|बाल|ब्यूटी|फेशियल|स्पा|मसाज",
        context=True,
    ),
    _c(
        "property_rentals",
        "cash_collections operations_process",
        "",
        "flats?|apartments?|tenants?|landlords?|property|properties|lease*|repair requests?|maintenance requests?|broken (tap|light)s?|plumb*|electrician*|building",
        "flat|flats|tenant|tenants|kirayedar|makan|makaan|property|lease|repair request|nalka|tap|plumber|electrician|building",
        "فلیٹ|فلیٹس|کرایہ دار|مکان|پراپرٹی|لیز|مرمت کی درخواست|نلکا|ٹونٹی|پلمبر|الیکٹریشن|عمارت",
        "شقة|شقق|مستأجر|مستأجرون|مالك|عقار|عقارات|عقد ايجار|طلب صيانة|حنفية|سباك|كهربائي|مبنى",
        "फ्लैट|किरायेदार|मकान|प्रॉपर्टी|लीज|मरम्मत अनुरोध|नल|प्लंबर|इलेक्ट्रीशियन|इमारत",
        context=True,
    ),
    _c(
        "returns_refunds",
        "stock_inventory orders_fulfilment",
        "returns_handling returns_rto",
        "return*|refund*|exchange*|replacement*|rto|refused|rejected parcels?|damaged in transit|come back|came back|paid twice",
        "return|returns|refund|exchange|replacement|rto|wapas kar|wapas karna|wapas kiya|wapis kar|damage|damaged|do baar",
        "ریٹرن|واپس کرنا|واپس کریں|واپس کیا|ریفنڈ|تبادلہ|ایکسچینج|متبادل|نقصان زدہ|دو بار",
        "ارجاع|مرتجع*|مرتجعات|استرداد|استبدال|تبديل|رفض|تالفة|مرتين",
        "रिटर्न|वापस करना|वापस करें|वापस किया|रिफंड|एक्सचेंज|बदलना|क्षतिग्रस्त|दो बार",
    ),
    _c(
        "receipts_records",
        "compliance_admin cash_collections",
        "record_keeping documentation",
        "receipt*|receipt book|ledger|khata|khaata|register|log ?book|notebook|diary|written record|paper record|bookkeeping|accounts book|numbered",
        "receipt|receipts|ledger|khata|khaata|register|logbook|copy|rasid|raseed|hisaab kitaab|hisab kitab|bahi",
        "رسید|رسیدیں|لیجر|کھاتہ|کھاتے|رجسٹر|لاگ بک|کاپی|بہی|حساب کتاب",
        "ايصال|ايصالات|دفتر|سجل|كشف حساب|مسك الدفاتر|دفتر الحسابات|نسخة|حسابات",
        "रसीद|लेजर|खाता|रजिस्टर|लॉग बुक|कॉपी|बही|हिसाब किताब",
    ),
)


# A second pass, written from the words the pack problem phrases use for these topics (the packs are
# read-only data: `tests/unit/test_pi_idea_relevance_matrix.py` pins how many phrases get a concept
# that agrees with their labelled category). Merged into the concepts above.
EXTRA_TERMS: dict[str, str] = {
    "pay_collect": "cash|advance*|claim*|pays later|pay later|paid later|later payment|cheque*|repay*|never repay|money owed|payout*|cash flow|advances to|client pays|customers pay|pay on time|paid on time|late fee*|نقد|سداد|دفعة|شيك*|سلف*|قسط|paise|paisa|paisay|پیسے|پیسہ|पैसे",
    "cash_handling": "cash register|physical cash|cash in hand|cash box|handwritten cash|daily cash|cash book|card machine|pos cash|short in cash|cash ends up",
    "stock_count": "stock|stocks|godown|warehouse*|raw materials?|count never matches|doesnt match|does not match|on paper|physical count|spares|parts list|stock says|system says|book stock|stock sheet|اسٹاک|گودام|مستودع|مخزن|المخازن|गोदाम|स्टॉक",
    "stock_shortage": "ran out of|out of|finish early|finishes early|not in stock|no stock|stock finish*|short supply|backorder*|waiting for stock|parts shortage|missing parts",
    "pricing": "cost*|costs|actual cost|cost per|real cost|earn*|charges|charging|undercharg*|overcharg*|contract price|quote*|quotation*|tender*|estimate*|لاگت|تكلفة|أسعار|السعر|لاگت",
    "cost_control": "electricity|water|power|rising|loss|losses|charges|utilities|generator fuel|spend*|spending|overspend*|budget overrun|too much (money|spent)|money goes|where the money goes|الماء|الكهرباء|پانی|بجلی",
    "theft_loss": "go(es)? missing|disappear*|private (work|jobs|sales|deals)|side jobs?|sell(s|ing)? on the side|personal use|pocket*|extra (sold|bills?)|sold privately|keep the money|skim*",
    "staff_skills": "technician*|instructor*|operator*|crew|helpers?|engineers?|skilled|hard to find (staff|people|workers)|find (staff|people|workers|good)|argue*|disput*|poach*|karigar|مهندس|فني|مدرب|بندہ|بندے",
    "retention": "repeat*|forget us|forgot us|never hear|hear from us|past buyers|past customers|past clients|old customers|lapsed|warranty|subscription*|no reminders?|next (oil change|service|visit|appointment)|dropout*|drop out|dropping out|enrol*|re-?enrol*|leave us|left us",
    "whatsapp_messages": "dms?|direct messages?|asking|unanswered|questions?|hundreds of messages|messages pile|pile of messages|approval requests?|replies?|reply late|no one replies|nobody replies|nobody answers|calls? back|phone rings|miss(ed)? calls?|voice notes?|inbox|مسج|رسائل|ضائعة",
    "compliance": "renewal*|registration*|insurance|inspection*|claim*|filing|certificate*|certification|authority|authorities|expire*|expiry|handwritten|submission*|deadline*|permits?|تجديد|تسجيل|شهادة|تأمين|فحص|بیمہ|رجسٹریشن",
    "process_manual": "paper*|handwritten|written down|in (my|his|her|the manager's|one person's) head|production plan|back and forth|takes days|takes hours|nobody knows|no one knows|breaks? down|every night|night shift|at night|re-?type|re-?enter|copy paste|copying|retyping|handled by hand|by hand",
    "delivery": "transport*|transit|installation*|on time|promised date|ready date|delay*|delayed|goods arrive|dispatch delay|late arrival|cargo|freight|container*|clearance delay|نقل|شحنة|حاوية|تأخير|ميناء",
    "orders": "wrong size|wrong colou?r|wrong design|wrong quantity|mix-?ups?|mixed up|double ordered|duplicate orders?|order forms?|order taking|take orders|taking orders|phone orders?|whatsapp orders?|made to order|made-to-order|special orders?",
    "suppliers": "distributor*|abroad|contractors?|late delivery from|arrive late|supplier delays?|mills?|factory|factories|موزع|مصنع|مقاول|ٹھیکیدار",
    "sales_drop": "weekday*|weekend*|summer|winter|ramadan|sales|slow (day|days|month|months|weekday|weekdays)|quiet (day|days)|dead days?|few customers|fewer customers|no customers|nobody comes|customers dont come|footfall|رمضان|صيف|شتاء|گرمی|سردی|رمضان",
    "reporting": "compare|utili[sz]ation|reconcile|across (branches|locations|sites|outlets)|per (branch|cohort|site|machine|vehicle|trip|shift|class)|profit per|cannot see|cant see|see in one place|one place|figure out|work out|find out how much|how much (we|i) (made|earn)|كشف|حسابات|مقارنة",
    "equipment": "machines?|printer|loom|oven|boiler|tractor|pump|compressor|mixer|crusher|scanner|truck|fleet|tyre|tire|breakdowns?|stops working|stopped working|goes down|went down|ماكینة",
    "complaints": "quality|inconsistent|consistency|reject*|rejects|rejection|batch*|shade*|finish*|claims?|defect*|refuse*|refused|reputation|جودة|معاير|معیار|نقص",
    "growth_planning": "second (shop|branch|location|outlet|site|clinic|school|restaurant)|open a|ramadan|summer|new location|capacity planning|next (year|season|month)|how many (to|will)|hire for|forecast|seasonal staff|خطة|موسم",
    "leads_marketing": "brand*|influencers?|follow(ing)? up|new (clients|buyers|patients|students|members|guests)|bring (in )?(clients|buyers|customers|patients|students|members)|no one knows us|nobody knows us|find us|found us|walk-?ins?|عملاء|مرضى جدد|طلاب جدد",
    "software_tools": "whatsapp|excel|computer*|spreadsheets?|google sheets?|tracker|tracking sheet|apps? (dont|do not|never)|different (apps|systems|tools|sheets)|doesnt talk|does not talk|re-?key|اكسل|کمپیوٹر|حاسوب",
    "bookings": "booked|booking|show-?ups?|show up|showtime*|slot|slots|date clash*|clash*|same (date|time|slot|day)|two (events|bookings|teams|groups|clients)|overbook*|تضارب|متضارب",
    "team_coordination": "approve*|sign off|sign-?off|approval|waits? for me|wait for me|without me|everything (goes|runs) through|through me|technicians? (dont|do not)|who (is|was) doing|know who|assigned|القرار|موافقة",
}

CONCEPTS = tuple(
    Concept(c.key, c.cats, c.subs, c.terms + "|" + EXTRA_TERMS[c.key], c.weak, c.context)
    if EXTRA_TERMS.get(c.key)
    else c
    for c in CONCEPTS
)


# Concepts of one family are neighbours: a problem about one is answered by an idea about another
# (a roster for lateness, a register for a stock-out). A neighbour match is worth less than the same
# concept (2 points, not 3).
FAMILIES: dict[str, str] = {
    "staff_skills": "people", "staff_attendance": "people",
    "pay_collect": "money_in", "cash_handling": "money_in", "receipts_records": "money_in",
    "stock_shortage": "stock", "stock_excess": "stock", "stock_count": "stock", "expiry_waste": "stock",
    "orders": "fulfilment", "delivery": "fulfilment", "returns_refunds": "fulfilment",
    "retention": "care", "complaints": "care",
    "bookings": "slots", "capacity_idle": "slots",
    "pricing": "margin", "cost_control": "margin",
    "process_manual": "ops", "job_tracking": "ops",
}  # fmt: skip

# Topics that are NOT a problem of the business but a plausible-sounding aside (decor, logos, merch,
# gifts, contests). An idea whose only topics are these is UNLINKED, not UNKNOWN: pi recognised what
# it is about and it is not the owner's problem. They never link to a problem.
OFF_TOPIC: tuple[Concept, ...] = (
    _c(
        "decor_brand",
        "",
        "",
        "paint*|repaint*|decorat*|interior*|furniture|wallpaper|logo*|signboard*|sign board*|signage|banner*|business card*|visiting card*|branding|uniform*|renovat*|plants?|perfume|incense|music|playlist|aroma|lighting|curtains?|carpet*|wall(s)?|mural|gift wrap*|gift card*|souvenir*|mug*|t-?shirts?|shirts?|merch*|coloured lights|colored lights|decorative lights|fairy lights|neon",
        "paint|rang wali|rangon mein|decor|decoration|interior|furniture|logo|signboard|banner|visiting card|branding|uniform|colour|color|renovation|perfume|music|lighting|parde|carpet|deewar|deewaron|gift wrapping|gift wrap|souvenir|mug|shirt|shirts|merch|rangeen batti|rangeen lights|corner",
        "پینٹ|سجاوٹ|ڈیکور|فرنیچر|لوگو|سائن بورڈ|بینر|وزٹنگ کارڈ|برانڈنگ|یونیفارم|مرمت و تزئین|پرفیوم|موسیقی|لائٹنگ|پردے|قالین|دیوار|دیواروں|گفٹ ریپنگ|تحفہ|تحائف|مگ|شرٹ|شرٹس|رنگین بتیاں|رنگین لائٹس|رنگین بتی|کارنر",
        "طلاء|اصبغ*|دهان|ديكور|زخرفة|اثاث|شعار|لافتة|لوحة|لافتات|بطاقة عمل|بطاقات زيارة|هوية بصرية|زي موحد|لون|تجديد|عطر|موسيقى|اضاءة|ستائر|سجاد|جدار|جدران|تغليف الهدايا|هدية|هدايا|قمصان|قميص|اضواء ملونة|اضاءة ملونة|انوار ملونة",
        "पेंट|सजावट|डेकोर|फर्नीचर|लोगो|साइनबोर्ड|बैनर|विजिटिंग कार्ड|ब्रांडिंग|यूनिफॉर्म|इत्र|संगीत|लाइटिंग|पर्दे|कालीन|दीवार|दीवारों|गिफ्ट रैपिंग|उपहार|शर्ट|रंगीन बत्तियां|रंगीन लाइट",
    ),
    _c(
        "events_contests",
        "",
        "",
        "lucky draw*|prize*|contest*|competition*|raffle*|sports day|annual day|celebrity|charity|donat*|award*|trophy|trophies|snack*|drinks?|protein bars?|cold drinks?|water cooler|tips leaflet|leaflet*|newsletter|mascot",
        "lucky draw|inam|inaam|muqabla|sports day|annual day|celebrity|charity|donate|award|trophy|snacks|drinks|thande drinks|protein bar|leaflet|parcha|newsletter|mascot|mashware",
        "لکی ڈرا|انعام|انعامات|مقابلہ|اسپورٹس ڈے|سالانہ|مشہور شخصیت|خیرات|عطیہ|ایوارڈ|ٹرافی|اسنیکس|مشروبات|ٹھنڈے مشروبات|پروٹین بار|پرچہ|نیوز لیٹر|مشورے",
        "سحب|جائزة|جوائز|مسابقة|يوم رياضي|يوم سنوي|مشهور|خيرية|تبرع|كأس|وجبات خفيفة|مشروبات|مشروبات باردة|مشروبات|قطع بروتين|الواح بروتين|ألواح بروتين|نشرة|تميمة|نصائح صحية",
        "लकी ड्रा|इनाम|प्रतियोगिता|स्पोर्ट्स डे|वार्षिक|सेलिब्रिटी|दान|पुरस्कार|ट्रॉफी|स्नैक्स|ठंडे पेय|प्रोटीन बार|पर्चा|न्यूज़लेटर|सलाह",
    ),
)

# Boilerplate that fits any business. A phrase here, with no specific link, makes an idea GENERIC.
GENERIC_PHRASES = (
    "improve your business|improve the business|improve your (shop|club|farm|gym|clinic|restaurant|school|work)|grow your business|grow the business|develop your business|"
    "better software|use technology|use new technology|go digital|digitali[sz]e|be more efficient|work harder|work smarter|increase (your )?sales|"
    "boost (your )?(business|sales)|do better marketing|better marketing|marketing better|better management|manage better|manage your business better|"
    "improve (your )?service|improve quality|keep customers happy|focus on customers|think about customers|stay positive|plan better|organi[sz]e better|be consistent|"
    "make more money|business better|business grow|grow (the )?business|more efficient|best practices?|take it to the next level|"
    "improve the marketing|market better|grow with marketing|grow your work|grow with social media|new technology|improve with technology|"
    "business behtar|behtar software|software istemal|business barhe|business barhayein|marketing behtar|marketing se business|behtar karein|behtar karo|"
    "technology istemal|digital karein|kaam behtar|business ko behtar|mehnat karein|behtar management|sales barhayein|"
    "کاروبار بہتر|بہتر سافٹ ویئر|سافٹ ویئر استعمال|ٹیکنالوجی استعمال|مارکیٹنگ بہتر|کاروبار بڑھ|کاروبار بڑھائیں|کام بہتر|بہتر کریں|محنت کریں|بہتر مینجمنٹ|سیلز بڑھائیں|مارکیٹنگ سے کاروبار|کلب بہتر|فارم بہتر|"
    "تحسين التسويق|حسن التسويق|حسنوا التسويق|حسّن التسويق|حسّنوا التسويق|نمّوا عملكم|نموا عملكم|نمّ عملك|تنمية عملك|تنمية عملكم|بالتسويق عبر وسائل التواصل|تكنولوجيا جديدة|بتكنولوجيا جديدة|"
    "تحسين العمل|تحسين عملكم|تحسين النادي|تحسين المزرعة|تحسين الاعمال|تحسين التجارة|برنامجا افضل|برنامج افضل|برنامج أفضل|استخدم التكنولوجيا|استخدموا التكنولوجيا|تسويق افضل|تسويق أفضل|تنمية العمل|زيادة المبيعات|ادارة افضل|اعمل بجد|اعملوا بجد|"
    "व्यवसाय बेहतर|बेहतर सॉफ्टवेयर|सॉफ्टवेयर का उपयोग|तकनीक का उपयोग|मार्केटिंग बेहतर|व्यवसाय बढ़ा|काम बेहतर|बेहतर करें|मेहनत करें|बेहतर प्रबंधन|बिक्री बढ़ाएं|नई तकनीक"
)

# Words that mean nothing about WHICH problem an idea answers. They never count as a shared word.
STOPWORDS = (
    # English
    "the a an and or but if so to of in on at for from by with without as is are was were be been being it its this that these those your you our we they them their he she his her my me i "
    "do does did done doing have has had having will would can could should may might must shall not no yes than then there here when while where which who whom what why how all any each every some "
    "more most much many few less least very just also only even still again ever never always often once twice per into onto over under up down out off about after before between during one two three four five "
    "get got make made let use used using keep kept give take send put set see look ask tell say said want need try tried so too own same other another such both either neither "
    "before after first last second third next pehle baad pehli pehla dusra dusri پہلے پہلی پہلا بعد قبل الاولى اول पहले पहली बाद "
    "dont cant doesnt didnt wont isnt arent wasnt weve ive youre theyre thats cannot know knows nobody nothing everything something anything anyone someone whole half lots full hard different actual real huge because "
    # Roman Urdu
    "hai hain ho hoga hogi honge tha thi the ka ki ke ko se mein me par pe aur ya bhi hi to toh nahi nahin na koi kuch sab har ek do teen yeh ye woh wo is us in un jab tab taake kyunke ke liye "
    "karein karo kar karna karen kijiye dein do den dena lein lo len lena rakhein rakho rakhna likhein likho banayen banao jaye jaye ja jana aaye aa aana hua hui hue raha rahi rahe sakta sakte sakti chahiye "
    "mujhe humein hamare hamara hamari mera meri mere apna apni apne unka unki unke uska uski uske ab phir bohat bahut zyada kam sirf lekin magar agar kyun kya kaise kahan kab "
    # Urdu
    "ہے ہیں ہو ہوگا ہوگی تھا تھی تھے کا کی کے کو سے میں پر اور یا بھی ہی تو نہیں نہ کوئی کچھ سب ہر ایک دو تین یہ وہ اس ان جب تب تاکہ کیونکہ لیے کریں کرو کر کرنا دیں دیں لیں رکھیں لکھیں بنائیں جائے آئے ہوا ہوئی ہوئے رہا رہی رہے سکتا سکتے چاہیے مجھے ہمیں ہمارے ہمارا ہماری میرا میری میرے اپنا اپنی اپنے ان کا اس کا اب پھر بہت زیادہ کم صرف لیکن مگر اگر کیوں کیا کیسے کہاں کب "
    # Arabic
    "في من الى إلى على عن مع او أو ثم لكن هذا هذه ذلك تلك هو هي هم هن نحن انا أنا انت أنت كل بعض اي أي لا نعم قد لقد كان كانت يكون تكون ان أن إن حتى لكي لتظهر حتى لا ما ماذا كيف اين أين متى لماذا الذي التي الذين عند بعد قبل بين خلال هناك هنا جدا جداً فقط ايضا أيضا مرة واحد واحدة اثنان ثلاثة كثيرا كثيراً قليل لدينا لدي لنا لي له لها لهم عندنا عندي كم "
    # Hindi
    "है हैं हो होगा होगी था थी थे का की के को से में पर और या भी ही तो नहीं ना कोई कुछ सब हर एक दो तीन यह वह इस उस ये वो जब तब ताकि क्योंकि लिए करें करो कर करना दें लें रखें लिखें बनाएं जाए आए हुआ हुई हुए रहा रही रहे सकता सकते चाहिए मुझे हमें हमारे हमारा हमारी मेरा मेरी मेरे अपना अपनी अपने अब फिर बहुत ज्यादा कम सिर्फ लेकिन मगर अगर क्यों क्या कैसे कहाँ कब"
)

# Everyday words that appear in ideas for every kind of problem: a shared one is no evidence.
WEAK_TOKENS = (
    "customer customers client clients buyer buyers business shop store owner people person team staff day days week weeks month months year years time times "
    "every each daily weekly monthly list lists sheet sheets note notes message messages page pages simple small short new old good better best first last next one "
    "idea ideas thing things way ways problem problems issue issues work works working help helps free "
    "gahak gahakon customer log banda bande roz rozana hafta hafte mahina mahine saal waqt list kaam masla masle behtar naya naye purana chhota "
    "گاہک گاہکوں لوگ بندہ روز روزانہ ہفتہ ہفتے مہینہ مہینے سال وقت فہرست کام مسئلہ مسئلے بہتر نیا نئے پرانا چھوٹا کاروبار "
    "زبون زبائن عملاء عميل ناس شخص يوم ايام اسبوع اسابيع شهر شهور سنة وقت قائمة ورقة رسالة عمل مشكلة مشاكل افضل جديد قديم صغير الاعمال "
    "ग्राहक लोग आदमी रोज रोजाना हफ्ता हफ्ते महीना महीने साल समय सूची काम समस्या बेहतर नया नए पुराना छोटा व्यवसाय"
)

# Remedies a tried entry can repeat. Narrow on purpose: a remedy shared by many ideas ("a list") is
# not a repeat. concept -> terms (same syntax as above).
REMEDIES: dict[str, str] = {
    "discount": "discount*|price cut*|cheaper|sale offer|offer a sale|ڈسکاؤنٹ|رعایت|خصم|تخفيض|ڈسکاونٹ|छूट|डिस्काउंट|discount dena|discount do|mark ?down",
    "hire": "hire|hiring|recruit*|extra staff|more staff|new staff|بھرتی|توظيف|وظّف*|भर्ती|bharti|naya banda|ایک اور آدمی|مزید عملہ",
    "ads": "ads|advertis*|boost|sponsored|campaign*|اشتہار|اشتہارات|اعلان*|विज्ञापन|ishtehaar|ishtihar|paid promotion",
    "software": "new software|software|app|crm|pos system|erp|system|سافٹ ویئر|برنامج|نظام|सॉफ्टवेयर|ایپ|تطبيق|ऐप",
    "training": "training|train the|course|workshop|ٹریننگ|تربیت|تدريب|ट्रेनिंग|प्रशिक्षण",
    "reminder": "reminder*|remind*|ریمائنڈر|یاد دہانی|تذكير|تذكير*|रिमाइंडर|याद दिला*|yaad dehani|yaad dilana",
    "loyalty": "loyalty|loyalty card|points|reward*|ویلیو کارڈ|وفادار*|ولاء|لائلٹی|इनाम कार्ड|rewards program",
    "register": "register|ledger|notebook|diary|khata|رجسٹر|کھاتہ|دفتر|سجل|رجسٹر|रजिस्टर|खाता|डायरी|ڈائری|دفتر",
    "supplier_change": "new supplier|change (the )?supplier|another supplier|switch (the )?(courier|supplier)|نیا سپلائر|مورد جديد|نیا کوریئر|شركة شحن اخرى|नया सप्लायर|nayi courier|naya supplier",
    "raise_price": "raise (the )?prices?|increase (the )?prices?|price increase|قیمت بڑھا|رفع الاسعار|कीमत बढ़ा|qeemat barha|price barha",
}
