# ruff: noqa: E501  (one phrase per line reads better than wrapped strings)
"""A second, fresh corpus of normal replies (ideas with quantities and units, noted lines, limits with a
next step, yes/no answers, empathy, recommendations, seasonality, identity answers, lists, pharmacy and
paperwork wording) in five languages, written separately from the first precision corpus.

False positives are counted per rule and per language. Hard rules (R-SOL-09) must have none; all the
soft rules together may flag at most 1% of the replies. Run with -s for the table."""

from collections import Counter

import pytest

from app.modules.pi import constitution_gaps as gaps

AI = {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. What is going wrong?"}
S4 = {"flow": {"state": "S4_SORTED_SUMMARY"}}
HARD = {"R-SOL-09"}

FRESH = {
    "en": {
        "ideas": [
            "Put a 2 kg trial pack of the new rice near the counter.",
            "Weigh every 25 kg sack when it arrives and write the number on the slip.",
            "Offer a 750 ml bottle at a lower price on Fridays.",
            "Pin the delivery times on the shop door.",
            "Keep a 10 minute stock count before closing.",
            "Send a short message to regulars when new stock lands.",
            "Move the fast sellers to eye level.",
            "Give each cashier a 1 page checklist for opening.",
            "Photograph the shelf at 6 pm and compare it with the morning.",
            "Set aside a 30 minute slot each week to call late suppliers.",
            "Use a 50 sheet notebook as the returns log.",
            "Agree one pickup time per day with the courier.",
            "Mark the 5 slowest items and discuss them on Sundays.",
            "Tell customers the repair takes 3 days and write the date on the receipt.",
            "Start a 20 minute handover chat between shifts.",
            "Print the price list in 2 sizes, one for the door and one for the counter.",
            "Ask the supplier for a 7 day payment window in writing.",
            "Give the 3 busiest hours an extra person.",
            "Track returns on a simple sheet with a date and a reason.",
            "Cut the weekly order into 2 smaller orders.",
        ],
        "questions": [
            "Which shop would try this first?",
            "Is it every shop, or only some?",
            "Does that sound doable this week?",
            "Which part would be hardest?",
        ],
        "latest": [
            "we lose time every evening",
            "customers keep asking for things we do not have",
            "cash is always short",
            "staff do not follow the routine",
        ],
        "notes": [
            (
                "Noted: late couriers. Is it daily, or only some days?",
                "the couriers are always late",
            ),
            (
                "Noted: short change at the till. Is it the same shop each time, or different ones?",
                "we run short of change",
            ),
            (
                "Got it, customers asking for items we lack. Is it a few items, or many?",
                "customers keep asking for things we lack",
            ),
            (
                "Noted: the price list is out of date. Is it every shop, or some?",
                "our price list is out of date",
            ),
            (
                "That makes sense, handover between shifts is thin. Is it mornings, or evenings?",
                "shift handover is thin",
            ),
            (
                "Noted: staff skipping the opening routine. Is it new, or has it always been so?",
                "staff skip the opening routine",
            ),
            (
                "Noted: returns without a reason on the slip. Is it weekly, or daily?",
                "returns come back with no reason",
            ),
            (
                "Noted: the fridge breaks in summer. Is it the main shop, or a smaller one?",
                "the fridge breaks in summer",
            ),
            (
                "Got it, quotes take days. Is it every quote, or only large ones?",
                "our quotes take days",
            ),
            (
                "Noted: parcels labelled wrongly. Is it the same people each time, or different ones?",
                "parcels get labelled wrongly",
            ),
        ],
        "specials": [
            (
                "I can't confirm payment myself. Staff confirm it and I tell you here. Which order is it?",
                "was my payment received?",
                {},
            ),
            (
                "I can't give legal advice, but I can note the dispute for the team. Which supplier is it?",
                "should I sue my supplier?",
                {},
            ),
            ("Yes, I can write that down. Which shop is it?", "Can you write this down?", {}),
            (
                "No, I don't send quotes in this chat. Which shop is it?",
                "Do you send quotes here?",
                {},
            ),
            (
                "I'm sorry, that sounds exhausting. Which part is the worst?",
                "I'm going to lose my shop",
                {},
            ),
            (
                "That sounds hard. I'm here with you. Which shop feels it most?",
                "I can't pay the rent",
                {},
            ),
            (
                "My suggestion is to start with the late couriers. Which shop?",
                "three things are wrong",
                {},
            ),
            ("Demand usually grows before Eid. Which shop gets busiest?", "sales are slow", {}),
            ("I'm an AI from Workzap, not a person. Which shop is it?", "Are you a robot?", {}),
            ("• Late couriers\n• Short cash\nIs anything missing?", "that is all for now", S4),
            (
                "Count each antibiotic pack at closing and write it on the register. Which shop?",
                "the pharmacy stock is a mess",
                {},
            ),
            ("Keep each VAT invoice in a folder by month. Which shop?", "paperwork is a mess", {}),
            (
                "Noted: the Gulberg branch runs short of change. Is it daily, or weekly?",
                "the Gulberg branch runs short of change",
                {},
            ),
            ("Workzap can look at problems like this. Which shop is it?", "Can you fix this?", {}),
        ],
    },
    "roman_ur": {
        "ideas": [
            "Naye chawal ka 2 kg ka trial pack counter ke paas rakhein.",
            "Har 25 kg ki bori aate hi tol kar parchi par likh dein.",
            "Jumme ko 750 ml ki bottle sasti kar ke dein.",
            "Delivery ka waqt dukaan ke darwaze par laga dein.",
            "Band karne se pehle 10 minute stock ginti karein.",
            "Naya maal aane par purane customers ko chhota sa message bhejein.",
            "Jaldi bikne wali cheezein nazar ke saamne rakhein.",
            "Har cashier ko khulne ki 1 safha ki checklist dein.",
            "Shaam 6 baje shelf ki tasveer lein aur subah se milayein.",
            "Har hafte 30 minute late supplier ko call karne ke liye rakhein.",
            "Returns ka hisaab 50 safhon ki copy mein likhein.",
            "Courier ke saath din mein ek pickup ka waqt tay karein.",
            "5 sab se sust items chunein aur itwar ko un par baat karein.",
            "Customer ko batayen ke marammat 3 din leti hai aur tareekh parchi par likhein.",
            "Shifton ke beech 20 minute ki hand-over baat shuru karein.",
            "Price list 2 size mein chhapwayen, ek darwaze ke liye ek counter ke liye.",
        ],
        "questions": [
            "Kaunsi dukaan pehle try karegi?",
            "Har dukaan mein ho sakta hai ya kuch mein?",
            "Ye is hafte mumkin lagta hai?",
            "Isme sab se mushkil hissa kaunsa hoga?",
        ],
        "latest": [
            "hamari shaam ko bohat der lag jati hai",
            "customers aise saman maangte hain jo hamare paas nahi hota",
            "cash hamesha kam parta hai",
            "staff routine par nahi chalta",
        ],
        "notes": [
            (
                "Note kar liya: courier hamesha der se aate hain. Roz hota hai ya kuch din?",
                "courier hamesha der se aate hain",
            ),
            (
                "Note kar liya: till par khulle paise kam hote hain. Har baar wohi dukaan hoti hai ya alag?",
                "khulle paise kam hote hain",
            ),
            (
                "Samajh gaya, jo cheez hamare paas nahi woh log maangte hain. Kuch cheezein hain ya bohat si?",
                "log wo cheez maangte hain jo nahi",
            ),
            (
                "Note kar liya: price list purani hai. Har dukaan par hai ya kuch par?",
                "price list purani hai",
            ),
            (
                "Samajh gaya, shift badalte waqt baat kam hoti hai. Subah ya shaam ko?",
                "shift badalte waqt baat kam hoti hai",
            ),
            (
                "Note kar liya: staff khulne ka routine chhor deta hai. Ye naya hai ya hamesha se?",
                "staff khulne ka routine chhor deta hai",
            ),
            (
                "Note kar liya: returns par wajah nahi likhi hoti. Hafte mein ya roz?",
                "returns par wajah nahi likhi hoti",
            ),
            (
                "Note kar liya: garmi mein fridge kharab hota hai. Bari dukaan par ya choti par?",
                "garmi mein fridge kharab hota hai",
            ),
            (
                "Samajh gaya, quote banne mein din lagte hain. Har quote ya sirf bade?",
                "quote banne mein din lagte hain",
            ),
            (
                "Note kar liya: parcel par ghalat label lagta hai. Wohi log hote hain ya alag?",
                "parcel par ghalat label lagta hai",
            ),
        ],
        "specials": [
            (
                "Payment main khud confirm nahi kar sakta. Staff confirm karega aur main yahin bata dunga. Kaunsa order hai?",
                "meri payment mil gayi?",
                {},
            ),
            (
                "Haan, main ye likh sakta hoon. Kaunsi dukaan hai?",
                "kya aap ye likh sakte hain?",
                {},
            ),
            (
                "Nahi, main is chat mein quote nahi bhejta. Kaunsi dukaan hai?",
                "kya aap yahan quote bhejte hain?",
                {},
            ),
            (
                "Mujhe afsos hai, ye bohat thaka dene wala lagta hai. Sab se mushkil hissa kaunsa hai?",
                "main dewaliya ho jaunga",
                {},
            ),
            (
                "Main aap ke saath hoon. Kaunsi dukaan sab se zyada mutasir hai?",
                "kiraya nahi de sakta",
                {},
            ),
            (
                "Meri ray hai ke pehle der se aane wale courier dekhein. Kaunsi dukaan?",
                "teen masle hain",
                {},
            ),
            (
                "Eid se pehle aam tor par demand barh jati hai. Kaunsi dukaan sab se masroof hoti hai?",
                "sales slow hain",
                {},
            ),
            (
                "Main AI hoon, Workzap ka, insaan nahi. Kaunsi dukaan hai?",
                "kya aap robot hain?",
                {},
            ),
            ("• Der se aane wale courier\n• Cash ki kami\nKuch reh gaya?", "bas itna hi", S4),
            (
                "Har roz band karte waqt antibiotic ke packet ginein aur register mein likhein. Kaunsi dukaan?",
                "dawai ka stock gadbad hai",
                {},
            ),
            (
                "VAT ki har parchi mahine ke hisaab se file mein rakhein. Kaunsi dukaan?",
                "kaghazat gadbad hain",
                {},
            ),
            (
                "Workzap is tarah ke masle dekhta hai. Kaunsi dukaan hai?",
                "kya aap ye theek kar sakte hain?",
                {},
            ),
        ],
    },
    "ur": {
        "ideas": [
            "نئے چاول کا 2 کلو کا ٹرائل پیک کاؤنٹر کے پاس رکھیں۔",
            "ہر 25 کلو کی بوری آتے ہی تول کر پرچی پر لکھ دیں۔",
            "جمعے کو 750 ملی لیٹر کی بوتل سستی کر کے دیں۔",
            "ڈیلیوری کا وقت دکان کے دروازے پر لگا دیں۔",
            "بند کرنے سے پہلے 10 منٹ اسٹاک کی گنتی کریں۔",
            "نیا مال آنے پر پرانے گاہکوں کو چھوٹا سا پیغام بھیجیں۔",
            "جلد بکنے والی چیزیں نظر کے سامنے رکھیں۔",
            "ہر کیشیئر کو کھلنے کی 1 صفحے کی چیک لسٹ دیں۔",
            "شام 6 بجے شیلف کی تصویر لیں اور صبح سے ملائیں۔",
            "ہر ہفتے 30 منٹ دیر سے آنے والے سپلائر کو فون کرنے کے لیے رکھیں۔",
            "واپسی کا حساب 50 صفحوں کی کاپی میں لکھیں۔",
            "کورئیر کے ساتھ دن میں ایک پک اپ کا وقت طے کریں۔",
            "5 سب سے سست چیزیں چنیں اور اتوار کو ان پر بات کریں۔",
            "گاہک کو بتائیں کہ مرمت میں 3 دن لگتے ہیں اور تاریخ پرچی پر لکھیں۔",
            "شفٹوں کے بیچ 20 منٹ کی ہینڈ اوور بات شروع کریں۔",
            "پرائس لسٹ 2 سائز میں چھپوائیں، ایک دروازے کے لیے ایک کاؤنٹر کے لیے۔",
        ],
        "questions": [
            "کون سی دکان پہلے آزمائے گی؟",
            "کیا یہ ہر دکان میں ممکن ہے یا کچھ میں؟",
            "کیا یہ اس ہفتے ممکن لگتا ہے؟",
            "اس میں سب سے مشکل حصہ کون سا ہوگا؟",
        ],
        "latest": [
            "شام کو ہمارا بہت وقت ضائع ہوتا ہے",
            "گاہک ایسا سامان مانگتے ہیں جو ہمارے پاس نہیں ہوتا",
            "کیش ہمیشہ کم پڑ جاتا ہے",
            "عملہ معمول پر نہیں چلتا",
        ],
        "notes": [
            (
                "نوٹ کر لیا: کورئیر ہمیشہ دیر سے آتے ہیں۔ کیا یہ روز ہوتا ہے یا کچھ دن؟",
                "کورئیر ہمیشہ دیر سے آتے ہیں",
            ),
            (
                "نوٹ کر لیا: کاؤنٹر پر کھلے پیسے کم ہوتے ہیں۔ کیا ہر بار وہی دکان ہوتی ہے یا مختلف؟",
                "کھلے پیسے کم ہوتے ہیں",
            ),
            (
                "سمجھ گیا، جو چیز ہمارے پاس نہیں وہ لوگ مانگتے ہیں۔ کیا یہ چند چیزیں ہیں یا بہت سی؟",
                "لوگ وہ چیز مانگتے ہیں جو نہیں",
            ),
            (
                "نوٹ کر لیا: پرائس لسٹ پرانی ہے۔ کیا یہ ہر دکان پر ہے یا کچھ پر؟",
                "پرائس لسٹ پرانی ہے",
            ),
            (
                "سمجھ گیا، شفٹ بدلتے وقت بات کم ہوتی ہے۔ کیا یہ صبح ہوتا ہے یا شام کو؟",
                "شفٹ بدلتے وقت بات کم ہوتی ہے",
            ),
            (
                "نوٹ کر لیا: عملہ کھلنے کا معمول چھوڑ دیتا ہے۔ کیا یہ نیا ہے یا ہمیشہ سے؟",
                "عملہ کھلنے کا معمول چھوڑ دیتا ہے",
            ),
            (
                "نوٹ کر لیا: واپسی پر وجہ نہیں لکھی ہوتی۔ کیا یہ ہفتے میں ہوتا ہے یا روز؟",
                "واپسی پر وجہ نہیں لکھی ہوتی",
            ),
            (
                "نوٹ کر لیا: گرمی میں فریج خراب ہوتا ہے۔ کیا یہ بڑی دکان پر ہے یا چھوٹی پر؟",
                "گرمی میں فریج خراب ہوتا ہے",
            ),
            (
                "سمجھ گیا، کوٹ بننے میں دن لگتے ہیں۔ کیا ہر کوٹ میں یا صرف بڑے میں؟",
                "کوٹ بننے میں دن لگتے ہیں",
            ),
            (
                "نوٹ کر لیا: پارسل پر غلط لیبل لگتا ہے۔ کیا وہی لوگ ہوتے ہیں یا مختلف؟",
                "پارسل پر غلط لیبل لگتا ہے",
            ),
        ],
        "specials": [
            (
                "میں ادائیگی خود کنفرم نہیں کر سکتا۔ عملہ کنفرم کرے گا اور میں یہیں بتا دوں گا۔ کون سا آرڈر ہے؟",
                "کیا میری ادائیگی مل گئی؟",
                {},
            ),
            ("جی ہاں، میں یہ لکھ سکتا ہوں۔ کون سی دکان ہے؟", "کیا آپ یہ لکھ سکتے ہیں؟", {}),
            (
                "جی نہیں، میں اس چیٹ میں کوٹ نہیں بھیجتا۔ کون سی دکان ہے؟",
                "کیا آپ یہاں کوٹ بھیجتے ہیں؟",
                {},
            ),
            (
                "مجھے افسوس ہے، یہ بہت تھکا دینے والا لگتا ہے۔ سب سے مشکل حصہ کون سا ہے؟",
                "میں دیوالیہ ہو جاؤں گا",
                {},
            ),
            ("میں آپ کے ساتھ ہوں۔ کون سی دکان سب سے زیادہ متاثر ہے؟", "کرایہ نہیں دے سکتا", {}),
            (
                "میرا مشورہ ہے کہ پہلے دیر سے آنے والے کورئیر دیکھیں۔ کون سی دکان؟",
                "تین مسئلے ہیں",
                {},
            ),
            (
                "عید سے پہلے عموماً مانگ بڑھ جاتی ہے۔ کون سی دکان سب سے مصروف ہوتی ہے؟",
                "فروخت کم ہے",
                {},
            ),
            (
                "میں اے آئی ہوں، Workzap کی طرف سے، انسان نہیں۔ کون سی دکان ہے؟",
                "کیا آپ روبوٹ ہیں؟",
                {},
            ),
            ("• دیر سے آنے والے کورئیر\n• کیش کی کمی\nکچھ رہ گیا؟", "بس اتنا ہی", S4),
            (
                "ہر روز بند کرتے وقت اینٹی بائیوٹک کے پیکٹ گنیں اور رجسٹر میں لکھیں۔ کون سی دکان؟",
                "دوا کا اسٹاک گڑبڑ ہے",
                {},
            ),
            (
                "وی اے ٹی کی ہر پرچی مہینے کے حساب سے فائل میں رکھیں۔ کون سی دکان؟",
                "کاغذات گڑبڑ ہیں",
                {},
            ),
            (
                "Workzap اس طرح کے مسئلے دیکھتا ہے۔ کون سی دکان ہے؟",
                "کیا آپ یہ ٹھیک کر سکتے ہیں؟",
                {},
            ),
        ],
    },
    "ar": {
        "ideas": [
            "ضع عبوة تجريبية وزن 2 كيلو من الأرز الجديد قرب الصندوق.",
            "زن كل كيس 25 كيلو عند وصوله واكتب الرقم على الإيصال.",
            "قدّم زجاجة 750 مل بسعر أقل يوم الجمعة.",
            "علّق مواعيد التوصيل على باب المحل.",
            "اجعل جرد المخزون 10 دقائق قبل الإغلاق.",
            "أرسل رسالة قصيرة للعملاء الدائمين عند وصول بضاعة جديدة.",
            "ضع الأصناف السريعة البيع على مستوى النظر.",
            "أعطِ كل كاشير قائمة تحقق من صفحة واحدة للفتح.",
            "صوّر الرف عند السادسة مساءً وقارنه بالصباح.",
            "خصص 30 دقيقة كل أسبوع للاتصال بالمورد المتأخر.",
            "سجّل المرتجعات في دفتر من 50 ورقة.",
            "اتفق مع شركة الشحن على موعد استلام واحد يومياً.",
            "اختر 5 أصناف الأبطأ وناقشها يوم الأحد.",
            "أخبر الزبون أن الإصلاح يستغرق 3 أيام واكتب التاريخ على الإيصال.",
            "ابدأ محادثة تسليم من 20 دقيقة بين الورديات.",
            "اطبع قائمة الأسعار بحجمين، واحد للباب وواحد للصندوق.",
        ],
        "questions": [
            "أي فرع سيجرب هذا أولاً؟",
            "هل هو ممكن في كل الفروع أم في بعضها؟",
            "هل يبدو هذا ممكناً هذا الأسبوع؟",
            "ما أصعب جزء في هذا؟",
        ],
        "latest": [
            "نضيع وقتاً كثيراً في المساء",
            "الزبائن يطلبون أشياء ليست عندنا",
            "النقد ناقص دائماً",
            "الموظفون لا يلتزمون بالروتين",
        ],
        "notes": [
            (
                "تم تسجيل: تأخر شركات الشحن دائماً. هل يحدث يومياً أم في بعض الأيام؟",
                "شركات الشحن تتأخر دائماً",
            ),
            (
                "تم تسجيل: نقص الفكة عند الصندوق. هل هو نفس الفرع كل مرة أم مختلف؟",
                "ينقصنا الفكة عند الصندوق",
            ),
            (
                "فهمت، الزبائن يطلبون أشياء ليست عندنا. هل هي أشياء قليلة أم كثيرة؟",
                "الزبائن يطلبون أشياء ليست عندنا",
            ),
            (
                "تم تسجيل: قائمة الأسعار قديمة. هل هي في كل الفروع أم في بعضها؟",
                "قائمة الأسعار قديمة",
            ),
            (
                "فهمت، التسليم بين الورديات ضعيف. هل يحدث صباحاً أم مساءً؟",
                "التسليم بين الورديات ضعيف",
            ),
            (
                "تم تسجيل: الموظفون يتركون روتين الفتح. هل هذا جديد أم قديم؟",
                "الموظفون يتركون روتين الفتح",
            ),
            (
                "تم تسجيل: المرتجعات بلا سبب مكتوب. هل يحدث أسبوعياً أم يومياً؟",
                "المرتجعات بلا سبب مكتوب",
            ),
            (
                "تم تسجيل: الثلاجة تتعطل في الصيف. هل هي في الفرع الكبير أم الصغير؟",
                "الثلاجة تتعطل في الصيف",
            ),
            (
                "فهمت، عروض الأسعار تستغرق أياماً. هل هي كل العروض أم الكبيرة فقط؟",
                "عروض الأسعار تستغرق أياماً",
            ),
            (
                "تم تسجيل: الطرود تُلصق عليها بطاقات خاطئة. هل هم نفس الأشخاص أم مختلفون؟",
                "الطرود تلصق عليها بطاقات خاطئة",
            ),
        ],
        "specials": [
            (
                "لا أستطيع تأكيد الدفع بنفسي. الموظفون يؤكدونه وأخبرك هنا. أي طلب هو؟",
                "هل وصلكم دفعي؟",
                {},
            ),
            ("نعم، يمكنني كتابة ذلك. أي فرع هو؟", "هل يمكنك كتابة هذا؟", {}),
            (
                "لا، لا أرسل عروض الأسعار في هذه المحادثة. أي فرع هو؟",
                "هل ترسلون عروض الأسعار هنا؟",
                {},
            ),
            ("يؤسفني ذلك، يبدو هذا مرهقاً جداً. ما أصعب جزء فيه؟", "سأفلس", {}),
            ("أنا هنا معك. أي فرع الأكثر تأثراً؟", "لا أستطيع دفع الإيجار", {}),
            ("اقتراحي أن نبدأ بشركات الشحن المتأخرة. أي فرع؟", "ثلاث مشاكل", {}),
            ("يزداد الطلب عادة قبل العيد. أي فرع يكون الأكثر انشغالاً؟", "المبيعات بطيئة", {}),
            ("أنا ذكاء اصطناعي من Workzap ولست إنساناً. أي فرع هو؟", "هل أنت روبوت؟", {}),
            ("• شحنات متأخرة\n• نقص في النقد\nهل فاتني شيء؟", "هذا كل شيء", S4),
            (
                "عدّ علب المضاد الحيوي عند الإغلاق كل يوم واكتبها في السجل. أي فرع؟",
                "مخزون الصيدلية فوضى",
                {},
            ),
            ("احفظ كل فاتورة ضريبة القيمة المضافة في ملف حسب الشهر. أي فرع؟", "الأوراق فوضى", {}),
            ("Workzap ينظر في مشاكل كهذه. أي فرع هو؟", "هل يمكنك إصلاح هذا؟", {}),
        ],
    },
    "hi": {
        "ideas": [
            "नए चावल का 2 किलो का ट्रायल पैक काउंटर के पास रखें।",
            "हर 25 किलो की बोरी आते ही तौलकर पर्ची पर लिख दें।",
            "शुक्रवार को 750 मिली की बोतल सस्ती करके दें।",
            "डिलीवरी का समय दुकान के दरवाज़े पर लगा दें।",
            "बंद करने से पहले 10 मिनट स्टॉक की गिनती करें।",
            "नया माल आने पर पुराने ग्राहकों को छोटा सा संदेश भेजें।",
            "जल्दी बिकने वाली चीज़ें नज़र के सामने रखें।",
            "हर कैशियर को खुलने की 1 पन्ने की चेकलिस्ट दें।",
            "शाम 6 बजे शेल्फ की फोटो लें और सुबह से मिलाएं।",
            "हर हफ्ते 30 मिनट देर से आने वाले सप्लायर को फोन करने के लिए रखें।",
            "वापसी का हिसाब 50 पन्नों की कॉपी में लिखें।",
            "कूरियर के साथ दिन में एक पिकअप का समय तय करें।",
            "5 सबसे धीमी चीज़ें चुनें और रविवार को उन पर बात करें।",
            "ग्राहक को बताएं कि मरम्मत में 3 दिन लगते हैं और तारीख पर्ची पर लिखें।",
            "शिफ्टों के बीच 20 मिनट की हैंडओवर बात शुरू करें।",
            "प्राइस लिस्ट 2 साइज़ में छपवाएं, एक दरवाज़े के लिए एक काउंटर के लिए।",
        ],
        "questions": [
            "कौन सी दुकान पहले आज़माएगी?",
            "क्या यह हर दुकान में संभव है या कुछ में?",
            "क्या यह इस हफ्ते संभव लगता है?",
            "इसमें सबसे मुश्किल हिस्सा कौन सा होगा?",
        ],
        "latest": [
            "शाम को हमारा बहुत समय बर्बाद होता है",
            "ग्राहक ऐसा सामान माँगते हैं जो हमारे पास नहीं होता",
            "कैश हमेशा कम पड़ जाता है",
            "स्टाफ रूटीन पर नहीं चलता",
        ],
        "notes": [
            (
                "नोट कर लिया: कूरियर हमेशा देर से आते हैं। क्या यह रोज़ होता है या कुछ दिन?",
                "कूरियर हमेशा देर से आते हैं",
            ),
            (
                "नोट कर लिया: काउंटर पर खुले पैसे कम होते हैं। क्या हर बार वही दुकान होती है या अलग?",
                "खुले पैसे कम होते हैं",
            ),
            (
                "समझ गया, जो चीज़ हमारे पास नहीं वह लोग माँगते हैं। क्या यह कुछ चीज़ें हैं या बहुत सी?",
                "लोग वह चीज़ माँगते हैं जो नहीं",
            ),
            (
                "नोट कर लिया: प्राइस लिस्ट पुरानी है। क्या यह हर दुकान पर है या कुछ पर?",
                "प्राइस लिस्ट पुरानी है",
            ),
            (
                "समझ गया, शिफ्ट बदलते समय बात कम होती है। क्या यह सुबह होता है या शाम को?",
                "शिफ्ट बदलते समय बात कम होती है",
            ),
            (
                "नोट कर लिया: स्टाफ खुलने का रूटीन छोड़ देता है। क्या यह नया है या हमेशा से?",
                "स्टाफ खुलने का रूटीन छोड़ देता है",
            ),
            (
                "नोट कर लिया: वापसी पर वजह नहीं लिखी होती। क्या यह हफ्ते में होता है या रोज़?",
                "वापसी पर वजह नहीं लिखी होती",
            ),
            (
                "नोट कर लिया: गर्मी में फ्रिज खराब होता है। क्या यह बड़ी दुकान पर है या छोटी पर?",
                "गर्मी में फ्रिज खराब होता है",
            ),
            (
                "समझ गया, कोटेशन बनने में दिन लगते हैं। क्या हर कोटेशन में या सिर्फ बड़े में?",
                "कोटेशन बनने में दिन लगते हैं",
            ),
            (
                "नोट कर लिया: पार्सल पर गलत लेबल लगता है। क्या वही लोग होते हैं या अलग?",
                "पार्सल पर गलत लेबल लगता है",
            ),
        ],
        "specials": [
            (
                "मैं भुगतान खुद पुष्टि नहीं कर सकता। स्टाफ पुष्टि करेगा और मैं यहीं बता दूँगा। कौन सा ऑर्डर है?",
                "क्या मेरा भुगतान मिल गया?",
                {},
            ),
            ("हाँ, मैं यह लिख सकता हूँ। कौन सी दुकान है?", "क्या आप यह लिख सकते हैं?", {}),
            ("नहीं, मैं इस चैट में कोटेशन नहीं भेजता। कौन सी दुकान है?", "क्या आप यहाँ कोटेशन भेजते हैं?", {}),
            (
                "मुझे अफ़सोस है, यह बहुत थका देने वाला लगता है। सबसे मुश्किल हिस्सा कौन सा है?",
                "मैं दिवालिया हो जाऊँगा",
                {},
            ),
            ("मैं आपके साथ हूँ। कौन सी दुकान सबसे ज़्यादा प्रभावित है?", "किराया नहीं दे सकता", {}),
            ("मेरा सुझाव है कि पहले देर से आने वाले कूरियर देखें। कौन सी दुकान?", "तीन समस्याएँ हैं", {}),
            ("ईद से पहले आमतौर पर मांग बढ़ जाती है। कौन सी दुकान सबसे व्यस्त होती है?", "बिक्री धीमी है", {}),
            ("मैं एक एआई हूँ, Workzap का, इंसान नहीं। कौन सी दुकान है?", "क्या आप रोबोट हैं?", {}),
            ("• देर से आने वाले कूरियर\n• कैश की कमी\nकुछ छूट गया?", "बस इतना ही", S4),
            (
                "हर दिन बंद करते समय एंटीबायोटिक के पैकेट गिनें और रजिस्टर में लिखें। कौन सी दुकान?",
                "दवा का स्टॉक गड़बड़ है",
                {},
            ),
            ("वैट की हर पर्ची महीने के हिसाब से फाइल में रखें। कौन सी दुकान?", "कागज़ात गड़बड़ हैं", {}),
            ("Workzap ऐसी समस्याएँ देखता है। कौन सी दुकान है?", "क्या आप इसे ठीक कर सकते हैं?", {}),
        ],
    },
}


def build(family):
    spec = FRESH[family]
    ideas, questions, latest = spec["ideas"], spec["questions"], spec["latest"]
    items = []
    for idea in ideas:
        for j, question in enumerate(questions):
            other = latest[(j + 1) % len(latest)]
            history = [
                AI,
                {"role": "customer", "text": other},
                {"role": "ai", "text": questions[(j + 2) % len(questions)]},
            ]
            items.append(
                (f"{idea} {question}", {"latest_customer_message": latest[j], "history": history})
            )
    notes = spec["notes"]
    for i, (reply, said) in enumerate(notes):
        before_reply, before_said = notes[(i + 3) % len(notes)]
        history = [
            AI,
            {"role": "customer", "text": before_said},
            {"role": "ai", "text": before_reply},
        ]
        items.append((reply, {"latest_customer_message": said, "history": history}))
    for reply, said, extra in spec["specials"]:
        items.append((reply, {"latest_customer_message": said, "history": [AI], **extra}))
    return items


def test_the_fresh_corpus_is_big_enough():
    assert sum(len(build(f)) for f in FRESH) >= 400


def test_fresh_normal_replies_flag_nothing_hard_and_at_most_one_percent_soft(capsys):
    per_rule: Counter[str] = Counter()
    total = soft_total = 0
    rows = []
    for family in FRESH:
        items = build(family)
        flagged = []
        for reply, context in items:
            found = gaps.check(reply, context)
            for rule, _, _ in found:
                per_rule[rule] += 1
            if found:
                flagged.append((reply, [f[0] for f in found]))
        rows.append((family, len(items), len(flagged)))
        total += len(items)
        soft_total += len(flagged)
        assert not [x for x in flagged if set(x[1]) & HARD], flagged
        assert len(flagged) <= max(1, len(items) // 100), flagged
    with capsys.disabled():
        print("\nfresh corpus false positives")
        for family, n, bad in rows:
            print(f"  {family:9} {n:4} replies, {bad} flagged")
        print(
            f"  total     {total:4} replies, {soft_total} flagged ({100 * soft_total / total:.2f}%)"
        )
        print("  per rule:", dict(per_rule) or "none")
    assert soft_total <= total // 100
    assert not (set(per_rule) & HARD)


@pytest.mark.parametrize("family", sorted(FRESH))
def test_no_reply_in_the_fresh_corpus_is_flagged(family):
    flagged = [(r, [f[0] for f in gaps.check(r, c)]) for r, c in build(family)]
    flagged = [x for x in flagged if x[1]]
    assert not flagged, flagged[:5]
