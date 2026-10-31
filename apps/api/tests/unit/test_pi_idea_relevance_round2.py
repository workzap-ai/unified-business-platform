# ruff: noqa: E501
"""PS-3 round 2: fresh ideas written BEFORE tuning. Ten problem profiles x five languages, each with
two valid REWORDED ideas (causal or remedy wording, not the owner's words) and two unrelated
novelty ideas (names, logos, colours, games, drinks). Every profile is also tried in a WIDE form
whose problem text carries business-setting words (shop, office, front desk, staff): a setting word
alone must never link an idea. Plus the exact ideas the integrated 32-journey run got wrong."""

import pytest

from app.modules.pi.idea_relevance import IdeaKind, evaluate_idea

LANGS = ("en", "roman_ur", "ur", "ar", "hi")
WIDE_TAIL = {
    "en": "I run this myself in my shop with a small staff, one office and a front desk.",
    "roman_ur": "Main yeh apni dukaan mein chhote staff, ek office aur front desk ke saath khud chalata hoon.",
    "ur": "میں یہ اپنی دکان میں چھوٹے عملے، ایک دفتر اور فرنٹ ڈیسک کے ساتھ خود چلاتا ہوں۔",
    "ar": "أديره بنفسي في متجري مع موظفين قليلين ومكتب واحد ومكتب استقبال.",
    "hi": "मैं इसे अपनी दुकान में छोटे स्टाफ, एक ऑफिस और फ्रंट डेस्क के साथ खुद चलाता हूं।",
}

# profile -> category, lang -> (problem, valid1, valid2, unrelated1, unrelated2)
P2: dict[str, dict] = {
    "heat_shed": {
        "category": "loss_security",
        "en": (
            "Birds die in the shed every summer afternoon because it gets too hot.",
            "Open the side curtains in the afternoon so air moves through the shed.",
            "Hang wet sacks at the shed windows so the hot air cools down.",
            "Design a new logo for the farm gate.",
            "Start a mobile game for the farm staff.",
        ),
        "roman_ur": (
            "Garmiyon mein shed bohat garam ho jata hai aur parinde mar jate hain.",
            "Dopahar mein shed ke parde khol dein taake hawa guzre.",
            "Shed ki khidkiyon par geelay bore latkayen taake garmi kam ho.",
            "Farm ke gate ke liye naya logo banayein.",
            "Staff ke liye mobile game banayein.",
        ),
        "ur": (
            "گرمیوں میں شیڈ بہت گرم ہو جاتا ہے اور پرندے مر جاتے ہیں۔",
            "دوپہر میں شیڈ کے پردے کھول دیں تاکہ ہوا گزرے۔",
            "شیڈ کی کھڑکیوں پر گیلی بوریاں لٹکائیں تاکہ گرمی کم ہو۔",
            "فارم کے گیٹ کے لیے نیا لوگو بنائیں۔",
            "عملے کے لیے موبائل گیم بنائیں۔",
        ),
        "ar": (
            "تموت الطيور في العنبر في الصيف لأن الحرارة مرتفعة جدا.",
            "افتحوا الستائر الجانبية بعد الظهر ليمر الهواء في العنبر.",
            "علقوا أكياسا مبللة على نوافذ العنبر لتخفيف الحر.",
            "صمموا شعارا جديدا لبوابة المزرعة.",
            "اصنعوا لعبة على الجوال للموظفين.",
        ),
        "hi": (
            "गर्मियों में शेड बहुत गर्म हो जाता है और पक्षी मर जाते हैं।",
            "दोपहर में शेड के पर्दे खोल दें ताकि हवा गुजरे।",
            "शेड की खिड़कियों पर गीली बोरियां लटकाएं ताकि गर्मी कम हो।",
            "फार्म के गेट के लिए नया लोगो बनाएं।",
            "स्टाफ के लिए मोबाइल गेम बनाएं।",
        ),
    },
    "clinic_wait": {
        "category": "customer_experience_digital",
        "en": (
            "Patients wait over an hour at the front desk because walk-ins and appointments get mixed.",
            "Use a desktop computer at the front desk to check patients in by appointment time.",
            "Keep a numbered list of today's bookings on the receptionist's phone.",
            "Sell protein shakes at the front desk.",
            "Rename the clinic with a new name.",
        ),
        "roman_ur": (
            "Reception par mareez ek ghante se zyada intezar karte hain kyunke walk-in aur appointments mix ho jate hain.",
            "Front desk par desktop computer se mareezon ko appointment ke waqt ke mutabiq check in karein.",
            "Aaj ki bookings ki number wali list receptionist ke phone par rakhein.",
            "Front desk par protein shakes bechein.",
            "Clinic ka naya naam rakhein.",
        ),
        "ur": (
            "ریسپشن پر مریض ایک گھنٹے سے زیادہ انتظار کرتے ہیں کیونکہ واک اِن اور اپائنٹمنٹ مل جاتے ہیں۔",
            "فرنٹ ڈیسک پر ڈیسک ٹاپ کمپیوٹر سے مریضوں کو اپائنٹمنٹ کے وقت کے مطابق چیک اِن کریں۔",
            "آج کی بکنگز کی نمبر والی فہرست ریسپشنسٹ کے فون پر رکھیں۔",
            "فرنٹ ڈیسک پر پروٹین شیکس بیچیں۔",
            "کلینک کا نیا نام رکھیں۔",
        ),
        "ar": (
            "ينتظر المرضى أكثر من ساعة عند الاستقبال لأن المواعيد والحالات الطارئة تختلط.",
            "استخدموا حاسوبا مكتبيا عند الاستقبال لتسجيل وصول المرضى حسب موعدهم.",
            "ضعوا قائمة مرقمة لحجوزات اليوم على هاتف الاستقبال.",
            "بيعوا مشروبات البروتين عند مكتب الاستقبال.",
            "اختاروا اسما جديدا للعيادة.",
        ),
        "hi": (
            "रिसेप्शन पर मरीज एक घंटे से ज्यादा इंतजार करते हैं क्योंकि वॉक-इन और अपॉइंटमेंट मिल जाते हैं।",
            "फ्रंट डेस्क पर डेस्कटॉप कंप्यूटर से मरीजों को अपॉइंटमेंट के समय के अनुसार चेक इन करें।",
            "आज की बुकिंग की नंबर वाली सूची रिसेप्शनिस्ट के फोन पर रखें।",
            "फ्रंट डेस्क पर प्रोटीन शेक बेचें।",
            "क्लिनिक का नया नाम रखें।",
        ),
    },
    "milk_van": {
        "category": "loss_security",
        "en": (
            "About 40 litres of milk spoil every day because the van reaches customers late.",
            "Send the milk out with the first van in the morning so it arrives sooner.",
            "Make a van timetable and remind the driver every day.",
            "Open a Facebook page for the dairy.",
            "Paint the dairy shop in new colours.",
        ),
        "roman_ur": (
            "Roz 40 litre doodh kharab hota hai kyunke gaadi customers tak late pohanchti hai.",
            "Doodh ko subah ki pehli gaadi mein nikaal dein taake jaldi pohanche.",
            "Gaadi ka time table banayein aur driver ko roz yaad dilayein.",
            "Dairy ka Facebook page banayein.",
            "Dairy ki dukaan ko naye rang mein paint karwayein.",
        ),
        "ur": (
            "روزانہ چالیس لیٹر دودھ خراب ہوتا ہے کیونکہ گاڑی گاہکوں تک دیر سے پہنچتی ہے۔",
            "دودھ کو صبح کی پہلی گاڑی میں نکالیں تاکہ جلدی پہنچے۔",
            "گاڑی کا ٹائم ٹیبل بنائیں اور ڈرائیور کو روز یاد دلائیں۔",
            "ڈیری کا فیس بک پیج بنائیں۔",
            "ڈیری کی دکان کو نئے رنگ میں پینٹ کروائیں۔",
        ),
        "ar": (
            "يفسد حوالي أربعين لترا من الحليب كل يوم لأن السيارة تصل إلى الزبائن متأخرة.",
            "أخرجوا الحليب مع أول سيارة في الصباح ليصل أسرع.",
            "ضعوا جدول مواعيد للسيارة وذكروا السائق كل يوم.",
            "أنشئوا صفحة فيسبوك للمزرعة.",
            "اصبغوا محل الألبان بألوان جديدة.",
        ),
        "hi": (
            "रोज चालीस लीटर दूध खराब होता है क्योंकि गाड़ी ग्राहकों तक देर से पहुंचती है।",
            "दूध को सुबह की पहली गाड़ी में निकालें ताकि जल्दी पहुंचे।",
            "गाड़ी का टाइम टेबल बनाएं और ड्राइवर को रोज याद दिलाएं।",
            "डेयरी का फेसबुक पेज बनाएं।",
            "डेयरी की दुकान को नए रंग में पेंट करवाएं।",
        ),
    },
    "irrigation": {
        "category": "margin_cost",
        "en": (
            "The tube well runs at the wrong times so wheat gets water late and the electricity bill is very high.",
            "Write a weekly watering schedule and fix the tube well running times.",
            "Water at night when the power rate is lower and note the hours in a diary.",
            "Make a mobile game for the farm.",
            "Hire a celebrity to visit the field.",
        ),
        "roman_ur": (
            "Tube well galat waqt chalta hai is liye gandum ko pani late milta hai aur bijli ka bill bohat zyada hai.",
            "Pani dene ka haftay ka jadwal likhein aur tube well ka time tay karein.",
            "Raat ko pani dein jab bijli sasti ho aur ghantay diary mein likhein.",
            "Farm ke liye mobile game banayein.",
            "Khet mein kisi mashhoor admi ko bulayein.",
        ),
        "ur": (
            "ٹیوب ویل غلط وقت پر چلتا ہے اس لیے گندم کو پانی دیر سے ملتا ہے اور بجلی کا بل بہت زیادہ ہے۔",
            "پانی دینے کا ہفتہ وار جدول لکھیں اور ٹیوب ویل کا وقت طے کریں۔",
            "رات کو پانی دیں جب بجلی سستی ہو اور گھنٹے ڈائری میں لکھیں۔",
            "فارم کے لیے موبائل گیم بنائیں۔",
            "کھیت میں کسی مشہور شخصیت کو بلائیں۔",
        ),
        "ar": (
            "تعمل المضخة في أوقات خاطئة فيصل الماء إلى القمح متأخرا وفاتورة الكهرباء مرتفعة جدا.",
            "اكتبوا جدولا أسبوعيا للري وحددوا أوقات تشغيل المضخة.",
            "اسقوا ليلا عندما تكون تعرفة الكهرباء أقل ودونوا الساعات في دفتر.",
            "اصنعوا لعبة على الجوال للمزرعة.",
            "ادعوا شخصية مشهورة لزيارة الحقل.",
        ),
        "hi": (
            "ट्यूबवेल गलत समय पर चलता है इसलिए गेहूं को पानी देर से मिलता है और बिजली का बिल बहुत ज्यादा है।",
            "पानी देने का साप्ताहिक कार्यक्रम लिखें और ट्यूबवेल का समय तय करें।",
            "रात को पानी दें जब बिजली सस्ती हो और घंटे डायरी में लिखें।",
            "फार्म के लिए मोबाइल गेम बनाएं।",
            "खेत में किसी मशहूर हस्ती को बुलाएं।",
        ),
    },
    "gym_fees": {
        "category": "cash_collections",
        "en": (
            "About 25 gym members stop paying their monthly fees and the desk does not notice.",
            "Keep a weekly list of unpaid members that the desk checks every Monday.",
            "Message each member two days before the fee date.",
            "Add a juice bar next to the gym floor.",
            "Print team t-shirts for the staff.",
        ),
        "roman_ur": (
            "Takreeban 25 gym members mahana fees dena band kar dete hain aur desk ko pata nahi chalta.",
            "Na dene walon ki haftay wali list rakhein jo desk har Monday dekhe.",
            "Har member ko fees ki tareekh se do din pehle message bhejein.",
            "Gym floor ke saath juice bar shuru karein.",
            "Staff ke liye team t-shirts chhapwayein.",
        ),
        "ur": (
            "تقریباً پچیس جم ممبرز ماہانہ فیس دینا بند کر دیتے ہیں اور ڈیسک کو پتا نہیں چلتا۔",
            "فیس نہ دینے والوں کی ہفتہ وار فہرست رکھیں جو ڈیسک ہر پیر دیکھے۔",
            "ہر ممبر کو فیس کی تاریخ سے دو دن پہلے پیغام بھیجیں۔",
            "جم فلور کے ساتھ جوس بار شروع کریں۔",
            "عملے کے لیے ٹیم ٹی شرٹس چھپوائیں۔",
        ),
        "ar": (
            "نحو خمسة وعشرين عضوا في النادي يتوقفون عن دفع الرسوم الشهرية ولا ينتبه المكتب.",
            "احتفظوا بقائمة أسبوعية بالأعضاء غير المسددين يراجعها المكتب كل اثنين.",
            "أرسلوا لكل عضو رسالة قبل موعد الرسوم بيومين.",
            "افتحوا ركن عصير بجانب صالة النادي.",
            "اطبعوا قمصان فريق للموظفين.",
        ),
        "hi": (
            "करीब पच्चीस जिम सदस्य मासिक फीस देना बंद कर देते हैं और डेस्क को पता नहीं चलता।",
            "फीस न देने वालों की साप्ताहिक सूची रखें जिसे डेस्क हर सोमवार देखे।",
            "हर सदस्य को फीस की तारीख से दो दिन पहले संदेश भेजें।",
            "जिम फ्लोर के पास जूस बार शुरू करें।",
            "स्टाफ के लिए टीम टी शर्ट छपवाएं।",
        ),
    },
    "wrong_address": {
        "category": "orders_fulfilment",
        "en": (
            "About 20 orders a week come back from our online shop because of a wrong delivery address.",
            "Confirm the address with the customer on WhatsApp before shipping.",
            "Ask the customer to share their map location when ordering.",
            "Design a new logo for the shop.",
            "Add a gift wrapping option at checkout.",
        ),
        "roman_ur": (
            "Hamari online dukaan se haftay mein 20 orders ghalat address ki wajah se wapas aate hain.",
            "Shipping se pehle WhatsApp par customer se address confirm karein.",
            "Order dete waqt customer se map location share karwayein.",
            "Dukaan ke liye naya logo design karein.",
            "Checkout par gift wrapping ka option shamil karein.",
        ),
        "ur": (
            "ہماری آن لائن دکان سے ہفتے میں بیس آرڈر غلط ایڈریس کی وجہ سے واپس آتے ہیں۔",
            "شپنگ سے پہلے واٹس ایپ پر گاہک سے ایڈریس کنفرم کریں۔",
            "آرڈر دیتے وقت گاہک سے میپ لوکیشن شیئر کروائیں۔",
            "دکان کے لیے نیا لوگو ڈیزائن کریں۔",
            "چیک آؤٹ پر گفٹ ریپنگ کا آپشن شامل کریں۔",
        ),
        "ar": (
            "يرجع حوالي عشرين طلبا في الأسبوع من متجرنا الإلكتروني بسبب خطأ في عنوان التوصيل.",
            "أكدوا العنوان مع العميل على واتساب قبل الشحن.",
            "اطلبوا من العميل مشاركة موقعه على الخريطة عند الطلب.",
            "صمموا شعارا جديدا للمتجر.",
            "أضيفوا خيار تغليف الهدايا عند الدفع.",
        ),
        "hi": (
            "हमारी ऑनलाइन दुकान से हफ्ते में बीस ऑर्डर गलत पते की वजह से वापस आते हैं।",
            "शिपिंग से पहले व्हाट्सएप पर ग्राहक से पता कन्फर्म करें।",
            "ऑर्डर देते समय ग्राहक से मैप लोकेशन शेयर करवाएं।",
            "दुकान के लिए नया लोगो डिजाइन करें।",
            "चेकआउट पर गिफ्ट रैपिंग का विकल्प जोड़ें।",
        ),
    },
    "status_calls": {
        "category": "communication_coordination",
        "en": (
            "Customers phone the workshop 12 times a day to ask if their car is ready.",
            "Send a WhatsApp message to the customer when the car is ready.",
            "Give each customer a job slip with the stage of the repair.",
            "Put up a new signboard in front of the workshop.",
            "Sell tea and biscuits at the gate.",
        ),
        "roman_ur": (
            "Customers workshop ko roz 12 martaba phone karke poochte hain ke gaari tayyar hai ya nahi.",
            "Gaari tayyar hote hi customer ko WhatsApp message bhejein.",
            "Har customer ko repair ke marhale wali job slip dein.",
            "Workshop ke samne naya signboard lagayein.",
            "Gate par chai aur biscuit bechein.",
        ),
        "ur": (
            "گاہک ورکشاپ کو روزانہ بارہ بار فون کر کے پوچھتے ہیں کہ گاڑی تیار ہے یا نہیں۔",
            "گاڑی تیار ہوتے ہی گاہک کو واٹس ایپ پیغام بھیجیں۔",
            "ہر گاہک کو مرمت کے مرحلے والی جاب سلپ دیں۔",
            "ورکشاپ کے سامنے نیا سائن بورڈ لگائیں۔",
            "گیٹ پر چائے اور بسکٹ بیچیں۔",
        ),
        "ar": (
            "يتصل العملاء بالورشة اثنتي عشرة مرة يوميا ليسألوا هل السيارة جاهزة.",
            "أرسلوا رسالة واتساب للعميل عندما تصبح السيارة جاهزة.",
            "أعطوا كل عميل بطاقة عمل فيها مرحلة الإصلاح.",
            "ضعوا لافتة جديدة أمام الورشة.",
            "بيعوا الشاي والبسكويت عند البوابة.",
        ),
        "hi": (
            "ग्राहक वर्कशॉप को रोज बारह बार फोन करके पूछते हैं कि गाड़ी तैयार है या नहीं।",
            "गाड़ी तैयार होते ही ग्राहक को व्हाट्सएप संदेश भेजें।",
            "हर ग्राहक को मरम्मत के चरण वाली जॉब स्लिप दें।",
            "वर्कशॉप के सामने नया साइनबोर्ड लगाएं।",
            "गेट पर चाय और बिस्कुट बेचें।",
        ),
    },
    "pharmacy_expiry": {
        "category": "stock_inventory",
        "en": (
            "About 12 boxes of medicine a month expire unsold on the shelf.",
            "Write each box's expiry month in one list and check it once a week.",
            "Put the boxes close to expiry on the front shelf so they sell first.",
            "Give the pharmacy a new name.",
            "Add a perfume corner near the door.",
        ),
        "roman_ur": (
            "Har mahine taqreeban 12 dawai ke dabbe expire ho kar bikay bina shelf par rehte hain.",
            "Har dabbe ke expiry ka mahina ek list mein likhein aur haftay mein ek baar dekhein.",
            "Expiry ke qareeb dabbe samne wali shelf par rakhein taake pehle bikein.",
            "Pharmacy ka naya naam rakhein.",
            "Darwaze ke paas perfume corner banayein.",
        ),
        "ur": (
            "ہر مہینے تقریباً بارہ دوائی کے ڈبے میعاد ختم ہو کر بکے بغیر شیلف پر رہتے ہیں۔",
            "ہر ڈبے کی میعاد کا مہینہ ایک فہرست میں لکھیں اور ہفتے میں ایک بار دیکھیں۔",
            "میعاد کے قریب ڈبے سامنے والی شیلف پر رکھیں تاکہ پہلے بکیں۔",
            "فارمیسی کا نیا نام رکھیں۔",
            "دروازے کے پاس پرفیوم کارنر بنائیں۔",
        ),
        "ar": (
            "تنتهي صلاحية حوالي اثني عشر علبة دواء كل شهر دون أن تباع على الرف.",
            "اكتبوا شهر انتهاء صلاحية كل علبة في قائمة واحدة وراجعوها مرة كل أسبوع.",
            "ضعوا العلب القريبة من انتهاء الصلاحية على الرف الأمامي لتباع أولا.",
            "اختاروا اسما جديدا للصيدلية.",
            "افتحوا ركن عطور بجانب الباب.",
        ),
        "hi": (
            "हर महीने करीब बारह दवा के डिब्बे बिना बिके शेल्फ पर एक्सपायर हो जाते हैं।",
            "हर डिब्बे की एक्सपायरी का महीना एक सूची में लिखें और हफ्ते में एक बार देखें।",
            "एक्सपायरी के करीब डिब्बे आगे वाली शेल्फ पर रखें ताकि पहले बिकें।",
            "फार्मेसी का नया नाम रखें।",
            "दरवाजे के पास परफ्यूम कॉर्नर बनाएं।",
        ),
    },
    "truck_diesel": {
        "category": "operations_process",
        "en": (
            "Our trucks deliver late and the diesel use never adds up.",
            "Ask each driver to write a short trip record and hand it in every evening.",
            "Photograph each diesel receipt and send it on WhatsApp.",
            "Change the colour of the office walls.",
            "Paint the trucks in the company colours.",
        ),
        "roman_ur": (
            "Hamare trucks late pohanchte hain aur diesel ka hisaab bhi nahi milta.",
            "Har driver se kahein ke har trip ka chhota record likhe aur roz shaam jama kare.",
            "Diesel ki raseed ki tasveer WhatsApp par bhejein.",
            "Office ka rang badal dein.",
            "Trucks ko company ke rangon mein paint karwayein.",
        ),
        "ur": (
            "ہمارے ٹرک دیر سے پہنچتے ہیں اور ڈیزل کا حساب بھی نہیں ملتا۔",
            "ہر ڈرائیور سے کہیں کہ ہر ٹرپ کا چھوٹا ریکارڈ لکھے اور روز شام جمع کرائے۔",
            "ڈیزل کی رسید کی تصویر واٹس ایپ پر بھیجیں۔",
            "دفتر کی دیواروں کا رنگ بدل دیں۔",
            "ٹرکوں کو کمپنی کے رنگوں میں پینٹ کروائیں۔",
        ),
        "ar": (
            "تصل شاحناتنا متأخرة وحساب الديزل لا يطابق أبدا.",
            "اطلبوا من كل سائق كتابة سجل قصير لكل رحلة وتسليمه كل مساء.",
            "صوروا إيصال الديزل وأرسلوه على واتساب.",
            "غيروا لون جدران المكتب.",
            "اصبغوا الشاحنات بألوان الشركة.",
        ),
        "hi": (
            "हमारे ट्रक देर से पहुंचते हैं और डीजल का हिसाब भी नहीं मिलता।",
            "हर ड्राइवर से कहें कि हर ट्रिप का छोटा रिकॉर्ड लिखे और रोज शाम जमा करे।",
            "डीजल की रसीद की तस्वीर व्हाट्सएप पर भेजें।",
            "ऑफिस की दीवारों का रंग बदल दें।",
            "ट्रकों को कंपनी के रंगों में पेंट करवाएं।",
        ),
    },
    "salon_noshow": {
        "category": "customers_retention",
        "en": (
            "Customers book salon appointments and then do not show up, so chairs sit empty.",
            "Send a reminder message the evening before each appointment.",
            "Ask for a small booking confirmation reply from the customer.",
            "Buy new mirrors with gold frames.",
            "Play loud music in the waiting area.",
        ),
        "roman_ur": (
            "Customers salon mein appointment book karke aate nahi, is liye kursiyan khali rehti hain.",
            "Har appointment se ek shaam pehle reminder message bhejein.",
            "Customer se booking confirm karne ka chhota jawab mangein.",
            "Sunehri frame wale naye aaine kharidein.",
            "Intezar wali jagah par tez music chalayein.",
        ),
        "ur": (
            "گاہک سیلون میں اپائنٹمنٹ بک کر کے آتے نہیں اس لیے کرسیاں خالی رہتی ہیں۔",
            "ہر اپائنٹمنٹ سے ایک شام پہلے یاد دہانی کا پیغام بھیجیں۔",
            "گاہک سے بکنگ کنفرم کرنے کا چھوٹا جواب مانگیں۔",
            "سنہری فریم والے نئے آئینے خریدیں۔",
            "انتظار کی جگہ پر تیز موسیقی چلائیں۔",
        ),
        "ar": (
            "يحجز الزبائن مواعيد في الصالون ثم لا يحضرون فتبقى الكراسي فارغة.",
            "أرسلوا رسالة تذكير مساء اليوم السابق لكل موعد.",
            "اطلبوا من الزبون رداً قصيراً لتأكيد الحجز.",
            "اشتروا مرايا جديدة بإطارات ذهبية.",
            "شغلوا موسيقى عالية في منطقة الانتظار.",
        ),
        "hi": (
            "ग्राहक सैलून में अपॉइंटमेंट बुक करके आते नहीं इसलिए कुर्सियां खाली रहती हैं।",
            "हर अपॉइंटमेंट से एक शाम पहले रिमाइंडर संदेश भेजें।",
            "ग्राहक से बुकिंग कन्फर्म करने का छोटा जवाब मांगें।",
            "सुनहरे फ्रेम वाले नए आइने खरीदें।",
            "इंतजार की जगह पर तेज संगीत चलाएं।",
        ),
    },
}


def _problem(key: str, lang: str, wide: bool) -> list[dict]:
    text = P2[key][lang][0]
    words = [text, WIDE_TAIL[lang]] if wide else [text]
    return [{"id": "p1", "title": text, "user_words": words, "category": P2[key]["category"]}]


VALID = [(k, lang, i, w) for k in P2 for lang in LANGS for i in (1, 2) for w in (False, True)]
UNREL = [(k, lang, i, w) for k in P2 for lang in LANGS for i in (3, 4) for w in (False, True)]


def test_a_hundred_fresh_ideas_per_direction() -> None:
    assert len({(k, lang, i) for k, lang, i, _ in VALID}) == 100
    assert len({(k, lang, i) for k, lang, i, _ in UNREL}) == 100


@pytest.mark.parametrize(
    ("key", "lang", "i", "wide"),
    VALID,
    ids=[f"{v[0]}-{v[1]}-v{v[2]}-{'wide' if v[3] else 'narrow'}" for v in VALID],
)
def test_valid_reworded_idea_is_linked(key: str, lang: str, i: int, wide: bool) -> None:
    v = evaluate_idea(P2[key][lang][i], _problem(key, lang, wide), None, None, lang)
    assert v.kind is IdeaKind.LINKED, (v.kind, v.reason, v.evidence_words, v.concepts)


@pytest.mark.parametrize(
    ("key", "lang", "i", "wide"),
    UNREL,
    ids=[f"{v[0]}-{v[1]}-u{v[2]}-{'wide' if v[3] else 'narrow'}" for v in UNREL],
)
def test_unrelated_novelty_idea_is_never_linked(key: str, lang: str, i: int, wide: bool) -> None:
    v = evaluate_idea(P2[key][lang][i], _problem(key, lang, wide), None, None, lang)
    assert v.kind in (IdeaKind.UNLINKED, IdeaKind.GENERIC), (
        v.kind,
        v.reason,
        v.evidence_words,
        v.concepts,
    )


def test_unrelated_novelty_is_unlinked_not_merely_unknown() -> None:
    n = sum(
        evaluate_idea(P2[k][lang][i], _problem(k, lang, w), None, None, lang).kind
        is IdeaKind.UNLINKED
        for k, lang, i, w in UNREL
    )
    assert n >= 190, n  # of 200


# ----- the exact ideas the integrated 32-journey run got wrong -------------------------------------------


def _wide(title: str, owner: str, cat: str) -> list[dict]:
    return [{"id": "p1", "title": title, "user_words": [owner], "category": cat}]


JOURNEY_WRONG = [
    # (idea, problem title, all owner text, category, expected kind)
    (
        "Sell protein shakes at the front desk",
        "Members stop paying fees",
        "About 25 of them stop paying. A weekly list of unpaid members that the desk checks every Monday.",
        "cash_collections",
        IdeaKind.UNLINKED,
    ),
    (
        "Office ka rang badal dein",
        "Trucks deliver late",
        "Driver late pohanchte hain. Diesel ka hisaab bhi nahi milta. 15 gaadiyan hain aur office mein manager hai.",
        "operations_process",
        IdeaKind.UNLINKED,
    ),
    (
        "Mobile game banayein",
        "Irrigation timing and power bill",
        "Meri 10 acre ki gandum mein pani ka waqt par intezam nahi hota, tube well ka bijli ka bill bohat zyada aata hai.",
        "margin_cost",
        IdeaKind.UNLINKED,
    ),
    (
        "دکان کا نیا نام رکھیں",
        "Medicines expire unsold",
        "ہماری فارمیسی میں دوائیں میعاد ختم ہونے سے پہلے نہیں بکتیں۔ میں اسٹاک خود دیکھتا ہوں، میعاد کی کوئی فہرست نہیں ہے۔",
        "stock_inventory",
        IdeaKind.UNLINKED,
    ),
    (
        "بلڈنگ کی چھت پر نیا رنگ کروائیں",
        "Rent arrives late",
        "ہر مہینے آٹھ کرایہ دار کرایہ دیر سے دیتے ہیں اور میں فون پر پیچھے پڑتا ہوں۔ بلڈنگ کی دوسری منزل۔",
        "cash_collections",
        IdeaKind.UNLINKED,
    ),
    (
        "صمموا شعاراً جديداً للمتجر",
        "Orders come back wrong address",
        "في متجرنا الإلكتروني يرجع حوالي 20 طلباً في الأسبوع بسبب خطأ في العنوان. لا نستطيع تغيير شركة الشحن.",
        "orders_fulfilment",
        IdeaKind.UNLINKED,
    ),
    (
        "Open the side curtains in the afternoon so air moves through the shed",
        "Birds die in summer",
        "I lose around 200 birds every month. The shed gets very hot and we cannot add new fans. We poured water on the roof but it did not help.",
        "loss_security",
        IdeaKind.LINKED,
    ),
    (
        "Use a desktop computer system for check in at the front desk",
        "Patients wait too long",
        "Patients wait over an hour. Walk-ins and appointments mix at the front desk. We tried a token system.",
        "customer_experience_digital",
        IdeaKind.LINKED,
    ),
    (
        "Doodh ko subah ki pehli gaadi mein alag nikaal dein taake kam der mein pohanche",
        "Milk spoils before delivery",
        "Meri dairy mein roz 40 litre doodh kharab ho jata hai, subah se shaam tak gaadi late pohanchti hai. Thanda karne ki machine nahi hai.",
        "loss_security",
        IdeaKind.LINKED,
    ),
    (
        "دوپہر میں شیڈ کے پردے کھول دیں تاکہ ہوا گزرے",
        "Birds die in summer",
        "میرے پولٹری فارم میں گرمیوں میں ہر ہفتے مرغیاں مر جاتی ہیں۔ شیڈ بہت گرم ہو جاتا ہے اور ہم نئے پنکھے نہیں لگا سکتے۔ چھت پر پانی ڈالا۔",
        "loss_security",
        IdeaKind.LINKED,
    ),
    (
        "إخراج الحليب مع أول سيارة في الصباح ليصل أسرع",
        "Milk spoils before delivery",
        "في مزرعة الألبان يفسد حوالي 30 لتراً من الحليب كل يوم قبل التسليم. أعتقد أن السبب تأخر السيارة. ليس عندنا مبرد.",
        "loss_security",
        IdeaKind.LINKED,
    ),
    (
        "كتابة جدول أسبوعي للريّ وتحديد أوقات تشغيل المضخة",
        "Irrigation timing and power bill",
        "في مزرعة القمح مساحتها 10 فدان لا نسقي في الوقت المناسب وفاتورة الكهرباء مرتفعة جداً.",
        "margin_cost",
        IdeaKind.LINKED,
    ),
]


@pytest.mark.parametrize(
    ("idea", "title", "owner", "cat", "kind"),
    JOURNEY_WRONG,
    ids=[f"j{i}" for i in range(len(JOURNEY_WRONG))],
)
def test_integrated_journey_errors(
    idea: str, title: str, owner: str, cat: str, kind: IdeaKind
) -> None:
    v = evaluate_idea(idea, _wide(title, owner, cat))
    assert v.kind is kind, (v.kind, v.reason, v.evidence_words, v.concepts)


# ----- signage and branding: a concrete new object that answers no stated problem is UNLINKED ----------

SIGNAGE = {
    "en": [
        "Put a new board outside the school gate.",
        "Hang a colourful banner above the entrance.",
        "Put up a new nameplate at the front.",
    ],
    "roman_ur": [
        "School ke bahar naya board lagayein",
        "Darwaze ke upar rangeen banner lagwayein.",
        "Naya signboard aur nameplate banwayen.",
    ],
    "ur": [
        "اسکول کے باہر نیا بورڈ لگائیں۔",
        "دروازے کے اوپر رنگین بینر لگوائیں۔",
        "نیا سائن بورڈ اور نیم پلیٹ بنوائیں۔",
    ],
    "ar": [
        "ضعوا لافتة جديدة خارج المدرسة.",
        "علقوا بانرا ملونا فوق المدخل.",
        "اصنعوا لوحة اسم جديدة.",
    ],
    "hi": [
        "स्कूल के बाहर नया बोर्ड लगाएं।",
        "दरवाजे के ऊपर रंगीन बैनर लगवाएं।",
        "नया साइनबोर्ड और नेमप्लेट बनवाएं।",
    ],
}
SIGN_CASES = [
    (k, lang, n, w)
    for k in ("clinic_wait", "heat_shed", "gym_fees")
    for lang in LANGS
    for n in range(3)
    for w in (False, True)
]


@pytest.mark.parametrize(
    ("key", "lang", "n", "wide"),
    SIGN_CASES,
    ids=[f"{c[0]}-{c[1]}-s{c[2]}-{'wide' if c[3] else 'narrow'}" for c in SIGN_CASES],
)
def test_signage_is_unlinked_not_unknown(key: str, lang: str, n: int, wide: bool) -> None:
    v = evaluate_idea(SIGNAGE[lang][n], _problem(key, lang, wide), None, None, lang)
    assert v.kind is IdeaKind.UNLINKED, (v.kind, v.reason, v.concepts)


def test_the_exact_idea_from_the_school_journey() -> None:
    probs = [
        {
            "id": "p1",
            "title": "School fee arrives late",
            "user_words": ["Bohat se parents fees der se dete hain"],
            "category": "cash_collections",
        }
    ]
    v = evaluate_idea("School ke bahar naya board lagayein", probs, None, None, "roman_ur")
    assert v.kind is IdeaKind.UNLINKED


def test_a_task_board_for_the_problem_is_still_linked() -> None:
    probs = [
        {
            "id": "p1",
            "title": "Customers phone for the repair status",
            "user_words": ["customers keep calling to ask if the car is ready"],
            "category": "communication_coordination",
        }
    ]
    v = evaluate_idea(
        "Keep a job slip on every car and message the customer when it is ready.", probs
    )
    assert v.kind is IdeaKind.LINKED
