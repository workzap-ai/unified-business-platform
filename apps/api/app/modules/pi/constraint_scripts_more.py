"""L2-1: the reading tables for LIMITS and for the words around them (Urdu, Arabic, Hindi).

Pure data, read by `constraint_scripts.build`. Written by structure, not by example sentence:
  * can / cannot: سکتے, نستطيع, सकते next to a negation word read as "cannot";
  * negation: نہیں نہ مت, لا ليس لن, नहीं न मत; "only": صرف فقط केवल सिर्फ; "must": چاہیے يجب चाहिए;
  * resources ("we have no X"): پاس لدينا पास / money, budget, people, places, channels, time units;
  * phrases that change meaning as a pair (at least, at most, because, per month) are replaced
    whole, before single words are read.
A word that is not here is UNREAD, and an unread word keeps an option or a limit from ever being
`ok` (see `constraint_scripts`).
"""

URDU = """
سکتے=can سکتی=can سکتا=can سکیں=can سکوں=can صرف=only چاہیے=must چاہئے=must
چلنا=run چلے=run چلانا=run چلتا=run
واٹس=whatsapp فون=phone کمپیوٹر=computer پرنٹ=print چھپا=printed چھپی=printed چھپے=printed
کاغذ=paper اسکرین=screen انسٹاگرام=instagram پیغام=message پیغامات=messages
پیسے=money پیسہ=money رقم=money بجٹ=budget وعدہ=promise دن=days دنوں=days
معاہدے=contract معاہدہ=contract کورئیر=courier کوریئر=courier بکنگ=booking بکنگز=bookings
ریسپشنسٹ=receptionist مکینک=mechanic مزدور=worker باورچی=cook ڈسپیچر=dispatcher
اسٹائلسٹ=stylist گاہک=customer گاہکوں=customers خریدار=buyer کیٹرر=caterer پارٹنر=partner
شفٹ=shift رات=night لگا=add فیس=fee منٹ=minute گھنٹے=hours گھنٹہ=hours ہفتے=weeks ہفتہ=weeks
مہینے=months مہینہ=per_month ماہانہ=monthly سالانہ=yearly کل=tomorrow آج=today اندر=within تک=tak
مفت=free ادھار=loan اٹھا=afford ممکن=possible
اپڈیٹ=update ایڈجسٹ=adjust ریٹ=rate ریٹس=rates مینو=menu وقت=time ٹائمنگ=timing اشتہار=ad
اسسٹنٹ=assistant فہرست=list رجسٹر=register شیٹ=sheet ریکارڈ=record فائل=file کیلنڈر=calendar
ریمائنڈر=reminder کسی=anyone
اضافی=extra عملے=staff سوئچ=switch شروع=start بنائیں=make بنانا=make بھیجیں=send
"""
ARABIC = """
نستطيع=can تستطيع=can استطيع=can يستطيع=can نقدر=can يمكن=can فقط=only يجب=must
يعمل=run واتساب=whatsapp هاتف=phone هواتف=phone هواتفنا=phone حاسوب=computer كمبيوتر=computer
طباعة=print ورق=paper شاشة=screen انستغرام=instagram رسالة=message رسائل=messages
مال=money ميزانية=budget ميزانيتنا=budget وعد=promise ايام=days يوم=days عقد=contract بسبب=because
شركة=company شحن=shipping زبائن=customers حجز=booking حجوزات=bookings واحدة=1 واحد=1
موظفة=employee مصففين=stylists عاملين=workers طباخين=cooks ارسال=dispatch لدينا=have عندنا=have
يوجد=have توقف=stop قبول=accept وردية=shift ليلية=night مطبخ=kitchen تدريب=training تمديد=extend
ساعات=hours ساعة=hour اسبوع=weeks شهر=months غدا=tomorrow اليوم=today خلال=within تحمل=afford
شهريا=monthly سنويا=yearly مجانا=free طباخ=cook موظف=employee مصفف=stylist عامل=worker
تحديث=update تعديل=adjust سعر=price المنيو=menu قائمه=menu وقت=time اعلان=ad حمله=campaign
مساعد=assistant سجل=register ملف=file تقويم=calendar تذكير=reminder احد=anyone
اضافي=extra اضافيين=extra تبديل=change انتقل=switch ابدا=start ابدأ=start ارسل=send
"""
HINDI = """
सकते=can सकती=can सकता=can सकें=can केवल=only सिर्फ=only चाहिए=must चलना=run चले=run
व्हाट्सऐप=whatsapp वॉट्सऐप=whatsapp व्हाट्सएप=whatsapp फोन=phone फ़ोन=phone कंप्यूटर=computer
वेबसाइट=website प्रिंट=print कागज=paper कागज़=paper स्क्रीन=screen संदेश=message
पैसे=money पैसा=money वादा=promise दिन=days दिनों=days हफ्ते=weeks हफ़्ते=weeks सप्ताह=weeks
महीने=months महीना=per_month मासिक=monthly वार्षिक=yearly आज=today कल=tomorrow अंदर=within
तक=tak अनुबंध=contract कॉन्ट्रैक्ट=contract बुकिंग=booking कूरियर=courier उठा=afford मुफ्त=free
अपडेट=update एडजस्ट=adjust रेट=rate मेन्यू=menu समय=time विज्ञापन=ad
असिस्टेंट=assistant सूची=list रजिस्टर=register शीट=sheet रिकॉर्ड=record फ़ाइल=file
कैलेंडर=calendar रिमाइंडर=reminder किसी=anyone
अतिरिक्त=extra स्विच=switch शुरू=start बनाएं=make भेजें=send
रिसेप्शनिस्ट=receptionist मैकेनिक=mechanic मजदूर=worker रसोइया=cook स्टाइलिस्ट=stylist
"""
PLACES = """
کراچی=karachi لاہور=lahore راولپنڈی=rawalpindi ملتان=multan پشاور=peshawar کوئٹہ=quetta دبئی=dubai
ریاض=riyadh جدہ=jeddah دوحہ=doha
كراتشي=karachi لاهور=lahore ملتان=multan بيشاور=peshawar دبي=dubai الرياض=riyadh جدة=jeddah
الدوحة=doha
कराची=karachi लाहौर=lahore मुल्तान=multan पेशावर=peshawar क्वेटा=quetta दुबई=dubai रियाद=riyadh
बाहर=outside باہر=outside خارج=outside आगे=beyond آگے=beyond
"""
# replaced whole, before single words: (source, English)
PHRASES = (
    ("واٹس ایپ", "whatsapp"),
    ("ویب سائٹ", "website"),
    ("اسلام آباد", "islamabad"),
    ("فیصل آباد", "faisalabad"),
    ("کم از کم", "at least"),
    ("زیادہ سے زیادہ", "at most"),
    ("سے زیادہ خرچ نہیں کر سکتے", "at most"),
    ("سے زیادہ نہیں", "at most"),
    ("سے زیادہ نہ", "at most"),
    ("سے کم", "under"),
    ("سے اوپر", "above"),
    ("سے زیادہ", "above"),
    ("کی وجہ سے", "because"),
    ("کے لیے", "for"),
    ("کے لئے", "for"),
    ("کے ساتھ", "with"),
    ("سے آگے", "beyond"),
    ("کے علاوہ", "other than"),
    ("کے باہر", "outside"),
    ("ہر مہینے", "per month"),
    ("ہر ہفتے", "per week"),
    ("روپے مہینہ", "روپے per month"),
    ("على الاقل", "at least"),
    ("كحد اقصى", "at most"),
    ("بحد اقصى", "at most"),
    ("لا يزيد عن", "at most"),
    ("لا تزيد عن", "at most"),
    ("لا يتجاوز", "at most"),
    ("لا نستطيع انفاق اكثر من", "no more than"),
    ("لا استطيع انفاق اكثر من", "no more than"),
    ("اقل من", "under"),
    ("اكثر من", "above"),
    ("في الشهر", "per month"),
    ("في الاسبوع", "per week"),
    ("في السنه", "per year"),
    ("دون اي", "without any"),
    ("دون", "without"),
    ("لا يوجد", "not have"),
    ("ليس لدينا", "not have"),
    ("لا احد", "nobody"),
    ("कम से कम", "at least"),
    ("ज़्यादा से ज़्यादा", "at most"),
    ("ज्यादा से ज्यादा", "at most"),
    ("अधिक से अधिक", "at most"),
    ("से ज़्यादा नहीं", "at most"),
    ("से ज्यादा नहीं", "at most"),
    ("से अधिक नहीं", "at most"),
    ("से कम", "under"),
    ("से ऊपर", "above"),
    ("से आगे", "beyond"),
    ("के अलावा", "other than"),
    ("की वजह से", "because"),
    ("के कारण", "because"),
    ("के लिए", "for"),
    ("हर महीने", "per month"),
    ("ہمارے پاس", "have"),
    ("میرے پاس", "have"),
    ("हमारे पास", "have"),
)
