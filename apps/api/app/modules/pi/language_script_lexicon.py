# ruff: noqa: E501
"""Word lists for language_script.py. Data only: no logic, no imports.

Everything here is a plain whitespace-separated string so a native speaker can review and extend it
without reading code. Latin-script words are written in ordinary spelling; language_script.py folds
them (aa to a, ee to i, oo to u, repeated letters squeezed) so one entry covers its spelling variants.
Written by one author from general knowledge: NOT a native-speaker review (spec 2.5.1 still applies).

Words that mean something in two languages (to, me, main, do, is, no, ho, hi, se, ya, de, la, en)
are left out of the strong lists on purpose: a marker has to be rare in the rival language.
"""

# --------------------------------------------------------------------------------------------
# Roman Urdu / Roman Hindi (Latin letters). STRONG = rare in English, common in either of them.
# --------------------------------------------------------------------------------------------
ROMAN_INDIC_STRONG = """
aap ap aapka aapki aapke apka apki apke aapko apko aapse hum ham hamara hamari hamare hmara hmari hmare humara humari humare humein hamein hume
mera meri mere mujhe mjhe muje mujhy meray merey mujhko mujhse mujh tum tumhara tumhari tumhare tumhein tera teri tere tujhe wo woh yeh ye yahan yaha wahan waha kahan kidhar udhar idhar
hai hain hy hn hoon hun hota hoti hote hoga hogi honge hua hui hue hogaya hogya hogayi tha thi thay thy thin
kya kia kiya kyun kyu kyon kiyun kyunke kyunki kiunke kaise kese kaisay kaisa kaisi kab kitna kitni kitne kitnay kon kaun konsa kaunsa kaunsi
nahi nahin nhi nai nahee mat bilkul
chahiye chahye chaiye chahiyay chahta chahti chahte chahun chahein chahiyen
karna karne karta karti karte karo karen karein karun karoon kiye kardo krdo karwana krna kr
ka ki ke ko mein bhi aur lekin magar phir abhi jab sab kuch koi sirf bas zyada bohat bohot bohut boht bht bahut bahot
raha rahi rahe rha rhi rhe gaya gayi gaye gya gyi
bata batao batana batayein bataye btao btana bataen batain bataiye
sakta sakti sakte sakhta skta skte sakein sakun sakoon
milta milti milte milna mila mili mile milega milegi
dena dene dete deta deti dedo lena lene lete leta lelo
dekh dekho dekhna dekhte dekhta dekhein dikhao dikhana
jana jata jati jate jaye jaen jayein jaega jayegi jao
aana aata aati aate aaya aayi aaye ayega aaega aao
rakhna rakhta rakhte rakha rakhi
bolna bolta bolte bola kaha kehna kehta kehte kehti bolo
samajh samjha samjhi samajhna samajhta samajhti pata maloom malum
sochna sochta sochte likhna likhta likhte likha likhi likhein
chalta chalti chalte chalna chala chali chalo
shuru khatam poora puri pura pore
acha accha achha achi theek thik thek
dukan dukaan dukaanain dukaandar karobar karobaar dhanda dhandha dhande kaam kaaj masla masle masail mushkil
paisa paise paisay rupay rupaye hisaab hisab hisaabkitaab kitab
maal naraz nuksan nuksaan munafa munafah ghalti galti ghalat galat
log logon bachon bacha bachay bachche walid walida
aaj kal parson subah shaam raat hafta hafte mahina mahine mahinay saal
liye lie wala wali wale walon
bhai behan yaar janab sahab sahib bhaijan
is isko iska iski iske usne usko uska uski unka unki unhe
bar baar zaroori zaroorat zarurat
phirse dobara jaldi der ghanta ghante minute
sath saath tak waqt
lag lagta lagti lagte laga lagi lagna
ho jata hojata hojaye hojaega
pehle pehla pichle pichla agle agla
kuchh kuchhh thora thoda thori zara
wapas aisa aisi aise waisa waisi waise jaisa jaisi jaise
nahin chhota chhoti chhote bara bari bare
""".split()

# Weak Roman Indic markers: also words of another language (se is French/Spanish, ya Spanish, par golf, tab...).
ROMAN_INDIC_WEAK = "se ya par pe ab tab kam soch chal mai na ji".split()

# Urdu-leaning Latin spellings (rare in Hindi) and Hindi-leaning ones (rare in Urdu).
ROMAN_URDU_ONLY = """
shukriya shukria shukriyah meherbani mehrbani meharbani waqt masla masle masail karobar karobaar mareez
janab inshallah mashallah jazakallah assalam walaikum alaikum salam khayal tankhwah tankhwa tankhah
qeemat fauran filhal zaya azeez farmaye farmayen insaan kaghaz hukumat tareeqa tariqa wajah
""".split()
ROMAN_HINDI_ONLY = """
namaste namaskar dhanyavaad dhanyawad dhanyavad kripya kripaya samasya samay vyapar vyapaar vyavsay vyavsaay
grahak vishay avashyak avashyakta labh karmchari vetan bhugtan dukandaar kitabein kintu parantu isliye
shayad pratishat bhai-saab
""".split()

# --------------------------------------------------------------------------------------------
# English: function words (strong), business and everyday vocabulary (light: Roman Urdu keeps
# business terms in English, spec 2.5 "Business terms often stay English").
# --------------------------------------------------------------------------------------------
ENGLISH_FUNCTION = """
the and you your yours we our ours they their he she his her with for that this these those have has had are was were been will would could
should can what when where why how which who not but from about into there here some any more much many also just only very really because
every always never still again after before over under than then them being doing does did don't doesn't isn't aren't can't won't i'm it's i've
i'll we're that's what's need want like know tell help make give send show thanks hello good morning same other another each most too even own
such both few it my of at by be an if up am as
""".split()
ENGLISH_WEAK = "is i a".split()
ENGLISH_VOCAB = """
shop store stock sale sales delivery customer customers staff order orders invoice invoices payment salary branch branches manager team system
problem problems issue issues time month week day year work business money price prices cost quote quotation report record register diary phone
computer office school clinic doctor doctors client clients supplier suppliers warehouse inventory product products material budget expense
tenants tenant rent employee employees worker workers driver drivers rider riders parcel parcels booking bookings appointment queue waiting
reception receptionist complaint feedback review follow reminder message call whatsapp email website app software machine repair quality
damage waste delay mistake late early slow fast cheap expensive solution idea plan meeting contract license fee fees student students parents
teacher class exam farm farmer crop mango fruit season demand supply profit loss margin discount credit cash bank account tax loan target
deadline schedule shift attendance leave overtime partner accountant mechanic patient nurse pharmacy bakery factory truck trucks courier
return returns refund cancel exchange enquiry enquiries customer's problem's currently monthly weekly daily
now makes sense think thing things people way new old first last next long little big small high low right left back going come comes take
takes look find found use using used keep let say said says see seen ask asked try tried put run runs start started stop end open close pay paid
buy sell sold hold lose lost miss missed sent change changed happen happens happened mean means meant feel felt become seem seems called
getting taking making having losing selling buying paying working waiting asking
""".split()

# The same fillers in other scripts (a one-word "no", "yes", "ok", "thanks" is no sign of a language).
AMBIGUOUS_NATIVE = """
نہیں ہاں جی ٹھیک شکریہ اچھا بس بالکل لا نعم شكرا شکریہ حسنا تمام طيب طیب اوکے ممنون بله خیر باشه نه
नहीं नही हाँ हां जी ठीक धन्यवाद अच्छा बस बिल्कुल
""".split()

# Short answers and fillers that never decide a language on their own (spec RLANG09).
AMBIGUOUS_ANSWERS = """
ok okay yes no yeah yep nope haan han ha hmm hm hmmm mm nahi nahin nhi nai ji jee theek thik hai acha accha achha shukriya shukria thanks
thank please plz pls bas bilkul sure fine k kk done good great thx oh ah aha wow lol haha hehe sorry salam hi hey bye
""".split()

# --------------------------------------------------------------------------------------------
# Other Latin-script languages (own small words; each must be rare in English and Roman Urdu).
# --------------------------------------------------------------------------------------------
LATIN_LANGS: dict[str, str] = {
    "fr": """
aide avec besoin bonjour boutique c'est client clients commande commandes comment d'accord dans des du elle entreprise est et il j'ai je les leur
magasin mais merci mes mon ne non nous oui pas pour problème probleme que qui s'il ses souvent suis sur svp toujours très tres tu un une vous
nos notre votre ce cette sont ont avons sans personne combien coûte coute faut retard retards mois chaque cahier devis pouvez voulez voudrais
j'ai n'ai l'équipe équipe réservations reservations livraisons livreurs mécontents salaires employés budget système tard
ils elles ai as avons avez ont fais fait faire ça cela ceci tout tous rien quelque quand où pourquoi parce sur sous entre jusqu depuis sans
compris voulons veux peux pouvez pouvons sommes êtes etes déjà deja aussi encore maintenant
prix avant savoir décider decider voudrais aimerais bien plus moins quel quelle quels pouvoir faire
""",
    "es": """
ayuda cada clientes como cómo con de el en favor frecuencia gracias hola la las los mes mi mis muy necesito negocio para pedidos pero por
problema que quiero qué sí tengo tienda un una vale nuestros nuestras dónde donde está estamos hay nadie nunca siempre cuánto cuanto
cuesta tarda perdemos varias facturas cada mes repartidores llegan tarde enfadados presupuesto sistema nuevo este año reservas libreta
entendido primero pensarlo luego respondo sueldos empleados entregas tenemos dos tiendas control ventas
ya lo he se su sus nos nosotros ellos esta este esto es son están estan ser tiene tienen puede pueden quieren queremos hacer decir van voy vamos
muchas también tambien todo todos nada algo cuando porque sobre entre hasta desde sin construir decirme ayudar ayudarme puedo podemos
precio antes saber decidir quisiera querría
""",
    "de": """
aber bestellungen bestellung bin bitte danke das der die ein eine einen geschäft gut habe hallo hilfe ich ist ja kunden laden mein meine nein
nicht oft problem sehr sie sind und verwechselt wie wir unsere unser fragen ständig wo ihre stimmt nie mit register überein möchte wissen
praxis tun können viel kostet lange dauert einrichtung verlieren jeden monat mehrere rechnungen niemand merkt bestand klein
wir haben hat sind war waren wird werden kann können will wollen muss müssen auch noch schon nur dann wenn weil dass zu von bei nach aus
über unter zwischen ohne gegen für heute morgen gestern jetzt immer nie alle alles nichts etwas verstanden
preis bevor entscheide möchte wissen
""",
    "id": """
yang dan aku saya kamu anda tidak gak ga tolong pakai bahasa indonesia apa ini itu bisa mau kenapa dengan untuk sama kalau buat bukan sudah
belum juga dong sih punya usaha jualan lagi ada masalah sering keliru siapa nomor mohon terima kasih halo selamat pagi bagaimana tapi
karena atau jadi lebih sangat banget aja deh pelanggan kami terus bertanya mana pesanan mereka toko kecil stok pernah catatan berapa
biayanya lama waktu dibutuhkan kehilangan beberapa faktur setiap bulan sadar
""",
    "tr": """
ama ben benim bir bu cok çok degil değil evet hayir hayır icin isletme için işletme lutfen lütfen mağaza merhaba müşteri nasil nasıl
olur sen senin sipariş siparişler sorun sık tamam teşekkürler var ve yardım yok müşterilerimiz siparişlerinin nerede sürekli soruyor küçük
dükkanım stok hiçbir zaman kayıtla uyuşmuyor neler yapabileceğinizi öğrenmek istiyorum maliyeti kadar kurulumu sürer her ay birkaç faturayı
kaybediyoruz kimse fark etmiyor kliniğim
""",
    "tl": """
ang ng mga sa ako ikaw siya kami tayo sila hindi po opo salamat kasi pero para yung naman lang ba wala ito ano paano kailangan benta
tindahan gusto nila namin natin ay may kung nasaan laging nagtatanong namin order nila tugma talaan magkano gastos gaano katagal
tulong masubaybayan alam nawawala kada buwan naintindihan na ko mo niya
""",
}

# Latin letters that point to one language (letter -> language, weight).
LATIN_LETTER_HINTS: dict[str, tuple[str, float]] = {
    "ñ": ("es", 2.0), "¿": ("es", 2.0), "¡": ("es", 2.0),
    "ß": ("de", 2.0), "ä": ("de", 1.0),
    "ğ": ("tr", 2.0), "ş": ("tr", 2.0), "ı": ("tr", 2.0), "İ": ("tr", 2.0),
    "è": ("fr", 1.5), "ê": ("fr", 1.5), "ç": ("fr", 0.7), "ù": ("fr", 1.5), "û": ("fr", 1.5), "ô": ("fr", 1.5), "î": ("fr", 1.5), "œ": ("fr", 2.0),
    "á": ("es", 0.7), "í": ("es", 0.7), "ó": ("es", 0.7), "ú": ("es", 0.5),
    "ö": ("de", 0.5), "ü": ("de", 0.5),
}  # fmt: skip

# --------------------------------------------------------------------------------------------
# Arabic-script words, written as spoken (language_script.py folds ي to ی, ك to ک, hamza forms).
# --------------------------------------------------------------------------------------------
ARABIC_SCRIPT_WORDS: dict[str, str] = {
    "ur": """
ہے ہیں ہوں تھا تھی تھے کی کا کے کو سے میں پر نہیں اور یہ وہ کیا آپ ہم ہمارا ہماری ہمارے میرا میری میرے مجھے ہمیں کریں کرنا کرتے کرتا کرتی
چاہیے چاہئے چاہتا چاہتے بہت لیکن مگر پھر ابھی جب سب کچھ کوئی صرف زیادہ کم بھی ہوتا ہوتی ہوتے ہوگا ہوگی گیا گئی گئے رہا رہی رہے سکتے سکتا
سکتی لیے لئے والا والی والے ہوئی ہوئے کہاں کیسے کب کتنا کتنی کتنے کون کس اس ان جو شکریہ مسئلہ کاروبار دکان گاہک پیسے پیسہ وقت جلدی ٹھیک اچھا
چاہیں بتائیں دیں دیتے لگ لگتا لگتی ملتا ملتی ملتے جاتا جاتی جاتے آتا آتی آتے رکھا رکھتے پڑتا پڑتی پڑتے کہا کہتے کہنا لکھنا سمجھ معلوم پتہ
پتا ورنہ کیونکہ تاکہ جبکہ مجھ ملتی ہر مہینے مہینے لوگ لوگوں بچے بچوں سال دن رات شام صبح پہلے پچھلے مطلب میرا غلط معاف نقصان منافع
""",
    "ar": """
في على إلى الى عن هذا هذه ذلك التي الذي لم لن هل كان كانت لدي لدينا عندنا عندي نحن أنا ليس يجب يمكن أريد اريد نريد نستطيع كيف لماذا أين
اين ماذا هناك بعد قبل أيضا ايضا فقط لكن ثم حتى عند كم مع كل ولا لا قصدت قصدي أقصد اقصد شكرا مرحبا العملاء الزبائن الموظفين الموظفة
المخزون الفواتير الطلبات التسليم متأخر متأخرة دائما باستمرار الشهر الأسبوع نستطيع تستطيع يستطيع أحتاج احتاج لدينا لديك
""",
    "fa": """
ممنون حالا فهمیدم متشکرم باشه خیر چطور کنم کنید کنیم کردم گفتم میخواهم میخواهیم خواهم دیگر همه یک روز بسیار هنوز همین همان اینجا آنجا چون زیرا
بعد قبل حدود تقریبا تقریباً فقط
است که این را با برای از در نیست هستم هستیم هستند دارم داریم دارند داشتیم می نمی شما خیلی چقدر چه چرا کجا ولی اما باید بود بودن شد شده
نیز آن آیا لطفا مدام همیشه هیچ مشتریان فاکتور هزینه موجودی زمان خوب پیش ماه هفته کارمندان کارکنان فروشگاه انبار شعبه سفارش سفارش‌شان
منظورم فراموش متوجه نمی‌شود نمی‌دانم
""",
    "ps": """
زه ته دی دا چې او په کې ما مو یې څه چیرته څومره ډیر لږ دي لرم شته نشته وي کوم هغه دغه نو خو ټول مشتریان دوکان کارکوونکي
""",
    "sd": """
آهي آھي ۽ جو جي جا ۾ مون اسان توهان ناهي ٿيندو لڳندو وٽ هن هي ڪيترو ڪيترا ڪري ڪم دڪان گراهڪ ڀيرا پڇندا سندن ڪٿي ننڍي هڪ
""",
    "pa": """
اے نیں کیہ کیہڑا تسی ساڈا ساڈی ساڈے سانوں مینوں ایہہ ایہ اوہ اوہناں وچ کول کتھے کنا کنی ویلا لگے ہووے ہوندا کردے کردا کردی دا دی دے
پچھدے گھٹ جئی اک چلاندا واں تے وار نوں کم
""",
}

# Persian-only function words that need no letters to be told from Urdu: single tokens "می" / "نمی".
PERSIAN_PREFIX_TOKENS = ("می", "نمی")

# --------------------------------------------------------------------------------------------
# Words that are never mapped by the business-term normaliser (negations, quantities, answers).
# --------------------------------------------------------------------------------------------
NEVER_MAP = """
no not never none nothing nobody neither nor without cannot can't don't doesn't isn't aren't won't wasn't weren't hadn't haven't
nahi nahin nhi nai na mat bina bagair kabhi kuch koi sab sirf bas zyada kam aadha poora puri
نہیں نہ نہی نا مت بغیر کبھی کوئی کچھ سب صرف زیادہ کم آدھا پورا پوری
لا لم لن ليس ما بدون غير أبدا قط كل بعض كثير قليل نصف
नहीं नही न मत बिना कभी कोई कुछ सब सिर्फ ज्यादा कम आधा पूरा
all some few many most more less half double triple twice once zero one two three four five six seven eight nine ten hundred thousand
lakh lac crore karor hazar hazaar million billion dozen
ek do teen char paanch chhe saat aath nau das sau
""".split()

# --------------------------------------------------------------------------------------------
# Business terms: concept: spelling variants and translations (single tokens, any script).
# --------------------------------------------------------------------------------------------
BUSINESS_TERMS = """
order: order orders ordar ordars ordr aarder aardar odar آرڈر آرڈرز اوردر طلب طلبات طلبية طلبیہ ऑर्डर ऑर्डर्स आर्डर ऑडर
delivery: delivery deliveries delivary delivary dilevery dilivery deliveri deliverey ڈیلیوری ڈلیوری تسليم تسلیم توصيل توصیل تسليمات डिलीवरी डिलिवरी
dispatch: dispatch dispatched dispatching despatch dispach ڈسپیچ ارسال إرسال شحن डिस्पैच
shipment: shipment shipments shipmnt consignment شپمنٹ کھیپ شحنة شحنات शिपमेंट खेप
parcel: parcel parcels parsal parcal پارسل پارسلز طرد طرود पार्सल
courier: courier couriers kuriar korier کورئیر کوریئر مندوب كورير कूरियर
rider: rider riders raider رائیڈر سوار مندوب-توصيل राइडर
return: return returns returned vapsi wapsi واپسی ریٹرن مرتجع مرتجعات إرجاع वापसी रिटर्न
refund: refund refunds refand ریفنڈ رقم-واپسی استرداد استرجاع रिफंड
exchange: exchange exchanges ekschange تبادلہ تبدیلی استبدال तबादला
cancel: cancel cancelled canceled cancellation cancal cansel کینسل منسوخ منسوخی إلغاء الغاء कैंसल रद्द
invoice: invoice invoices invois inwoice inovice ainvoice انوائس انوائسز فاتورة فواتير فاکتور فاکتورها बिल-बुक इनवॉइस इनवाइस
bill: bill bills bil bilz بل بلز بلوں فاتورة-كهرباء बिल
receipt: receipt receipts reciept rasid raseed raseed رسید رسیدیں ایصال إيصال إيصالات रसीद रिसीट
quote: quote quotes quotation quotations qoutation kotation quatation کوٹیشن کوٹ عرض-سعر پیش‌فاکتور कोटेशन
estimate: estimate estimates estimation اندازہ تخمینہ تقدير تقدیر अनुमान अंदाज़ा
payment: payment payments paymnt paiment peyment adaigi adayegi ادائیگی ادائیگیاں پیمنٹ دفع دفعة مدفوعات سداد پرداخت भुगतान पेमेंट
advance: advance advanc edvance ایڈوانس پیشگی دفعة-مقدمة مقدم پیش‌پرداخت एडवांस अग्रिम
credit: credit udhaar udhar udhaar udhaar ادھار اُدھار قرض-بيع آجل نسیه उधार उधारी क्रेडिट
discount: discount discounts discont diskount ڈسکاؤنٹ رعایت چھوٹ خصم تخفيض تخفیض تخفیف डिस्काउंट छूट
price: price prices prise qeemat keemat kimat qimat قیمت قیمتیں ریٹ ریٹس سعر أسعار اسعار قیمت‌ها कीमत दाम भाव प्राइस
cost: cost costs kharcha kharch kharcha kharche lagat khrcha خرچہ خرچ لاگت تکلفة تكلفة هزينه هزینه खर्च खर्चा लागत
profit: profit profits munafa munafah nafa nafah faida fayda منافع نفع فائدہ ربح أرباح ارباح मुनाफा फायदा लाभ
loss: loss losses nuksan nuksaan nuqsan nuqsaan نقصان خسارہ خسارة خسائر ضرر زیان नुकसान घाटा हानि
margin: margin margins maargin مارجن ہامش هامش حاشیه मार्जिन
sale: sale sales saale سیل سیلز فروخت بیع مبيعات مبیعات فروش बिक्री सेल
purchase: purchase purchases purchasing kharid kharidari kharidna خریداری خرید شراء مشتريات خرید-کالا खरीद खरीदारी
supplier: supplier suppliers suplier supplyer سپلائر سپلائرز مورد موردين مورّد تامین‌کننده सप्लायर आपूर्तिकर्ता
vendor: vendor vendors vender venders وینڈر فروشندہ بائع باعة فروشنده विक्रेता वेंडर
customer: customer customers custmer costumer customar gahak gahaq grahak grahaq kastmar کسٹمر کسٹمرز گاہک گاہکوں عميل عملاء العملاء الزبون زبون زبائن مشتری مشتریان ग्राहक कस्टमर
client: client clients cliant kilaint کلائنٹ کلائنٹس موکل عميل-خدمة کلائنت क्लाइंट मुवक्किल
buyer: buyer buyers khareedar kharidar خریدار خریداروں खरीदार
seller: seller sellers baichne-wala bechnewala بیچنے-والا بائع-سلعة विक्रेता-व्यक्ति
shop: shop shops dukan dukaan dukaanain dukaanein dukkan dokan دکان دکانیں دکانوں دوکان محل متجر دكان دوکان‌ها فروشگاه दुकान दुकानें शॉप
store: store stores stor istore اسٹور سٹور مخزن-تجاري متجر-كبير فروشگاه-بزرگ स्टोर
branch: branch branches brnch branchen برانچ برانچیں شاخ فرع فروع شعبه شعب शाखा ब्रांच
warehouse: warehouse warehouses godown godaam gudam گودام گوداموں مستودع مخزن انبار گودام‌ها वेयरहाउस गोदाम
stock: stock stocks stok stak stoc اسٹاک سٹاک اسٹاکس مخزون موجودی स्टॉक
inventory: inventory inventories inventri inventary انوینٹری جرد جرد-المخزون موجودی-کالا इन्वेंटरी
item: item items aitem itm آئٹم آئٹمز عنصر بند صنف قلم आइटम
product: product products prodct maal mal prodakt پروڈکٹ پروڈکٹس مال منتج منتجات محصول محصولات उत्पाद प्रोडक्ट माल
material: material materials maal-material matiryal میٹیریل مواد مادہ مواد-خام مصالح सामग्री मटेरियल
packaging: packaging packing pakaging paking پیکنگ پیکیجنگ تغليف تعبئة بسته‌بندی पैकिंग पैकेजिंग
barcode: barcode barcodes bar-code بار-کوڈ باركود بارکد बारकोड
catalogue: catalogue catalog catalogs catelog کیٹلاگ فہرست-مصنوعات كتالوج کاتالوگ कैटलॉग
brand: brand brands brnd برانڈ برانڈز علامة-تجارية ماركة برند ब्रांड
market: market markets mandi bazaar bazar bazaar مارکیٹ منڈی بازار سوق أسواق اسواق بازار-ها मार्केट मंडी बाज़ार
season: season seasons seasn mausam موسم سیزن موسم-بیع सीज़न मौसम
demand: demand demands dimand mang مانگ ڈیمانڈ طلب-السوق الطلب-على تقاضا मांग डिमांड
supply: supply suplai فراہمی سپلائی إمداد توريد عرضه आपूर्ति सप्लाई
rent: rent rents kiraya kiraaya kirayah kiray کرایہ کرائے ایجار إيجار اجاره किराया
tenant: tenant tenants kirayadar kiraydar کرایہ-دار کرایہ-دار مستأجر مستاجر مستأجرين مستاجرین مستأجرا مستأجرون مستاجران किरायेदार टेनेंट
landlord: landlord landlords malik-makan مالک-مکان مالک-جائیداد مؤجر مالك-العقار موجر मकान-मालिक
salary: salary salaries salry tankhwah tankhwa tankhah tankha tankhuah تنخواہ تنخواہیں سیلری راتب رواتب الراتب حقوق-ماهانه तनख्वाह तनख़्वाह सैलरी वेतन
wage: wage wages dihadi dehadi ujrat ajrat اجرت دہاڑی ویجز أجر أجور اجور دستمزد मजदूरी दिहाड़ी
bonus: bonus bonuses bonas بونس انعام مکافأة مكافأة پاداش बोनस
commission: commission commissions comission kamishan کمیشن عمولة عمولات کمیسیون कमीशन
tax: tax taxes taks ٹیکس ٹیکسز ضريبة ضرائب مالیات कर टैक्स
loan: loan loans lon qarz qarza karza قرض قرضہ لون قروض وام लोन कर्ज
bank: bank banks bnk بینک بنک بنوک مصرف بانک बैंक
cash: cash cesh kaish نقد کیش نقدي نقدا نقد-پول कैश नकद
account: account accounts acount akaunt اکاؤنٹ اکاؤنٹس حساب حسابات حساب-بانکی अकाउंट खाता
ledger: ledger ledgers lejar لیجر کھاتہ کھاتے دفتر-الأستاذ سجل-الحسابات बही खाता-बही
accounts: accounting accountancy hisaab-kitaab hisabkitab hisaabkitaab حساب-کتاب حسابات-عامة محاسبة حسابداری हिसाब-किताब लेखा
register: register registers regestir registar رجسٹر رجسٹرز سجل سجلات دفتر-سجل रजिस्टर
diary: diary diaries dayri ڈائری ڈائریاں مفكرة دفتر-یادداشت डायरी
record: record records recrd rikard ریکارڈ ریکارڈز سجل-بيانات سجلات-بيانات रिकॉर्ड
report: report reports riport ripot رپورٹ رپورٹس تقرير تقارير گزارش गुزارش रिपोर्ट
budget: budget budgets bajet bajat بجٹ بجٹس ميزانية ميزانيات بودجه बजट
expense: expense expenses expence akhrajat akhrajaat اخراجات خرچے مصروفات مصاريف هزینه‌ها खर्चे व्यय
income: income incomes amdani amdan aamdani آمدنی آمدن دخل إيرادات ايرادات درآمد आमदनी आय
revenue: revenue revenues rivenue ریونیو محصول-آمدنی إيرادات-المبيعات राजस्व
target: target targets taregt ٹارگٹ ٹارگٹس ہدف هدف أهداف اهداف टारगेट लक्ष्य
deadline: deadline deadlines dedline ڈیڈ-لائن ڈیڈلائن آخری-تاریخ موعد-نهائي موعد-نهایی डेडलाइन
schedule: schedule schedules shedule skedyul شیڈول شیڈولز جدول جداول शेड्यूल
shift: shift shifts shiftain شفٹ شفٹیں شفٹس وردية ورديات شیفت पाली शिफ्ट
attendance: attendance attendence hazri hazari حاضری حضور حضور-غياب حضور-وغیاب उपस्थिति हाज़िरी
leave: leave leaves chutti chhutti chuttiyan chhuttiyan چھٹی چھٹیاں اجازة إجازة إجازات مرخصی छुट्टी लीव
overtime: overtime over-time overtym اوور-ٹائم اوورٹائم عمل-إضافي ساعات-إضافية اضافه-کار ओवरटाइम
staff: staff stuff stafff staf sttaf اسٹاف سٹاف عملہ عملے موظفين موظفون الموظفين طاقم کارکنان स्टाफ
employee: employee employees emplyee empoyee mulazim mulazmeen ملازم ملازمین ملازمہ موظف الموظف کارمند कर्मचारी एम्प्लॉयी
worker: worker workers workr kaarigar karigar mazdoor mazdur کاریگر مزدور ورکر ورکرز عامل عمال عاملین کارگر कारीगर मजदूर वर्कर
manager: manager managers manegar maneger mangr مینیجر منیجر مینیجرز مدير مديرة مدراء مدیر मैनेजर प्रबंधक
owner: owner owners onar malik maalik مالک مالکان صاحب-کاروبار صاحب مالك اصحاب مالکین मालिक ओनर
partner: partner partners parnter sajhedar shareek پارٹنر شریک شراکت-دار شريك شركاء همکار पार्टनर साझेदार
accountant: accountant accountants akountent muhasib muhasab اکاؤنٹنٹ محاسب محاسبین محاسب-قانونی حسابدار अकाउंटेंट मुनीम
driver: driver drivers draiver draivar ڈرائیور ڈرائیورز سائق سائقين سائقون راننده راننده‌ها ड्राइवर चालक
mechanic: mechanic mechanics mekanik mistri mistry مکینک مکینکس میکینک میکانیکی مستری ميكانيكي ميكانيكيين مکانیک मैकेनिक मिस्त्री
doctor: doctor doctors dr daktar dactar ڈاکٹر ڈاکٹرز طبیب طبيب أطباء اطباء دكتور دكاترة دکتر डॉक्टर चिकित्सक
patient: patient patients mareez mariz mareez مریض مریضوں مريض مرضى مرضی بیمار मरीज़ मरीज रोगी
nurse: nurse nurses nars نرس نرسز ممرضة ممرضات پرستار नर्स
receptionist: receptionist receptionists reception-staff ریسپشنسٹ استقبالیہ-والی موظفة-الاستقبال مسؤولة-الاستقبال مسئول-پذیرش रिसेप्शनिस्ट
reception: reception recepshan استقبالیہ ریسپشن استقبال الاستقبال پذیرش रिसेप्शन
teacher: teacher teachers tichar ustad ustaad استاد اساتذہ ٹیچر ٹیچرز معلم معلمين معلمة المعلمين معلّم معلم‌ها शिक्षक अध्यापक टीचर
student: student students stdnt talib-e-ilm talibilm طالب-علم طلباء طلبہ سٹوڈنٹ طالب طلاب الطلاب دانش‌آموز दानش‌آموز विद्यार्थी छात्र स्टूडेंट
parent: parent parents walid walideen walidain والد والدین والدہ اولیاء-الأمور أولياء-الأمور اولیاء والدین-ها माता-पिता अभिभावक पैरेंट
farmer: farmer farmers kisaan kisan zamindar کسان کسانوں زمیندار کاشتکار مزارع فلاح فلاحين مزارعين کشاورز किसान
crop: crop crops fasal faslain فصل فصلیں فصلوں محصول-زراعي محاصيل محصولات-کشاورزی फसल
harvest: harvest harvesting katai kataai کٹائی ہارویسٹ حصاد جني برداشت कटाई फसल-कटाई
booking: booking bookings bokking buking بکنگ بکنگز حجز حجوزات الحجوزات رزرو رزروها बुकिंग
appointment: appointment appointments apointment apoiment اپوائنٹمنٹ اپائنٹمنٹ ملاقات موعد مواعيد المواعيد قرار-ملاقات अपॉइंटमेंट मुलाकात
reservation: reservation reservations riservation ریزرویشن ریزرویشنز حجز-مسبق रिज़र्वेशन
slot: slot slots slott سلاٹ سلاٹس خانة فترة وقت-محدد ساعت-ها स्लॉट
queue: queue queues katar قطار لائن قطارین طابور طوابير صف صف-انتظار कतार क्यू लाइन
waiting: waiting intezar intizar انتظار انتظاری انتظار-طويل انتظار-ساعت इंतज़ार इंतजार
enquiry: enquiry enquiries inquiry inquiries inquary enqiry انکوائری انکوائریاں پوچھ-گچھ استفسار استفسارات استعلام پرسش पूछताछ इंक्वायरी
complaint: complaint complaints complaint shikayat shikayaat shikayatein شکایت شکایات شکایتیں شکوى شكاوى شکایت-ها शिकायत
feedback: feedback fedback feedbak فیڈ-بیک فیڈبیک رائے تاثرات ملاحظات ملاحظة بازخورد फीडबैक प्रतिक्रिया
review: review reviews riview ریویو ریویوز جائزہ مراجعة مراجعات تقييم समीक्षा रिव्यू
followup: followup follow-up followups follow-ups folowup فالو-اپ فالواپ متابعة متابعه پیگیری फॉलो-अप फॉलोअप
reminder: reminder reminders remindr ریمائنڈر یاد-دہانی تذکير تذکیر تنبيه یادآوری रिमाइंडर
message: message messages mesage msg msgs paigham paighaam پیغام پیغامات میسج میسجز رسالة رسائل پیام پیام‌ها संदेश मैसेज
call: call calls kall کال کالز مکالمة مکالمات اتصال تماس कॉल
phone: phone phones fone mobile mobiles mobail فون فونز موبائل ہاتف هاتف هواتف جوال تلفن गوشی फोन मोबाइल
whatsapp: whatsapp whatsap watsapp whtsapp واٹس-ایپ واٹساپ واتساب واتس-اب واتساپ व्हाट्सएप व्हाट्सऐप
email: email emails e-mail imail ای-میل ایمیل ایمیلز بريد-إلكتروني ايميل ایمیل-ها ईमेल
website: website websites web-site vebsite ویب-سائٹ ویبسائٹ موقع موقع-إلكتروني وب‌سایت वेबसाइट
app: app apps aap-app ایپ ایپس تطبيق تطبيقات اپلیکیشن ऐप एप
software: software softwares softwear سافٹ-ویئر سافٹ‌ویئر برنامج برامج نرم‌افزار सॉफ्टवेयर
system: system systems sistam sistem سسٹم سسٹمز نظام أنظمة انظمة سامانه सिस्टम प्रणाली
computer: computer computers kampyutar compyuter کمپیوٹر کمپیوٹرز حاسوب حاسوب-شخصي كمبيوتر رایانه कंप्यूटर कम्प्यूटर
printer: printer printers printar پرنٹر پرنٹرز طابعة طابعات پرینتر प्रिंटर
internet: internet intarnet انٹرنیٹ نیٹ إنترنت انترنت اینترنت इंटरनेट
machine: machine machines mashin mashine مشین مشینیں آلة آلات ماكينة ماكينات ماشین मशीन
equipment: equipment equipments ikwipment سامان آلات-ومعدات معدات تجهيزات تجهیزات उपकरण
repair: repair repairs repairing marammat marmat مرمت ریپیئر ریپئر إصلاح اصلاح تصليح تعمیر मरम्मत रिपेयर
maintenance: maintenance maintainance mentenance maintanence مینٹیننس دیکھ-بھال صيانة صیانه रखरखाव मेंटेनेंस
quality: quality qualty kwaliti کوالٹی معیار جودة کیفیت गुणवत्ता क्वालिटी
defect: defect defects difect نقص خرابی عیب عيب عيوب نقائص نقص-ها खराबी दोष
damage: damage damaged damages dameg ڈیمیج نقصان-شدہ ضرر-مادی تلف أضرار اضرار آسیب क्षति डैमेज
wastage: wastage wastege zaya zaya-shuda ضیاع ضائع فضلہ هدر هدرر اتلاف پرت बर्बादी अपव्यय
spoilage: spoilage kharab-hona sarna sarhna sad-jana سڑنا خراب-ہونا تلف-البضاعة تلف-السلع فاسد سڑ-جانا خراب-شدن सड़ना खराब
theft: theft chori choori tharak چوری سرقة سرقه دزدی चोरी
delay: delay delays delayed dealy late-hona der deri دیر تاخیر تأخير تاخیر تأخرات تأخر دیرکرد देरी विलंब
mistake: mistake mistakes mistek ghalti galti ghalatiyan غلطی غلطیاں خطأ أخطاء اخطاء اشتباه गलती भूल
error: error errors eror trutti خرابی-غلطی خطأ-تقني ایرر एरर त्रुटि
time: time timing waqt waqat samay وقت ٹائم ٹائمنگ زمن وقت-العمل زمان समय टाइम
day: day days din roz dinon دن دنوں روز یوم أيام ايام روزها दिन
week: week weeks hafta hafte haftay ہفتہ ہفتے ہفتوں أسبوع اسبوع أسابيع اسابيع هفته सप्ताह हफ्ता हफ्ते
month: month months mahina mahine mahinay maheena مہینہ مہینے مہینوں شهر أشهر اشهر ماه ماه‌ها महीना महीने
year: year years saal sal سال سالوں سنة سنوات عام اعوام سال‌ها साल वर्ष
today: today aaj aj آج اليوم امروز आज
tomorrow: tomorrow kal-aane-wala کل غدا غداً فردا कल
yesterday: yesterday kal-guzra گزشتہ-کل امس البارحة دیروز बीता-कल
morning: morning subah subha sabah صبح صباح صباحا الصباح صبحگاه सुबह
evening: evening shaam شام مساء المساء مساءً عصر शाम
night: night raat رات ليل الليل مساء-متأخر شب रात
problem: problem problems prblm masla masle masail mushkil mushkilat مسئلہ مسائل مشکل مشکلات مشكلة مشاكل المشكلة المشكلات مسأله مشکل-ها समस्या परेशानी प्रॉब्लम
issue: issue issues ishu ایشو مسئلے قضية قضايا موضوع-مشكلة मुद्दा इश्यू
solution: solution solutions solushan hal حل حلول ہل-مسئلہ راه‌حل समाधान हल सॉल्यूशन
idea: idea ideas aidia khayal خیال آئیڈیا آئیڈیاز فکرة أفكار افكار ایده विचार आइडिया
plan: plan plans plaan منصوبہ پلان پلانز خطة خطط برنامه योजना प्लान
meeting: meeting meetings miting میٹنگ میٹنگز اجلاس اجتماع اجتماعات جلسه जलسا मीटिंग बैठक
contract: contract contracts kontract kantrakt معاہدہ کنٹریکٹ عقد عقود قرارداد अनुबंध कॉन्ट्रैक्ट
agreement: agreement agreements agrement samjhota ایگریمنٹ سمجھوتہ اتفاق اتفاقية اتفاقیه समझौता एग्रीमेंट
license: license licence lisence lisans لائسنس اجازت-نامہ ترخيص رخصة رخصت پروانه लाइसेंस
permit: permit permits parmit پرمٹ اجازت تصریح مجوز परमिट
registration: registration registeration rajistration رجسٹریشن اندراج تسجيل ثبت‌نام पंजीकरण रजिस्ट्रेशन
fee: fee fees fees fiss فیس فیسیں فیسوں رسوم رسم شهریه शुल्क फीस
tuition: tuition tution tuishan ٹیوشن ٹیوشن-فیس دروس-خصوصية دروس-خصوصیة ट्यूशन
admission: admission admissions admisan داخلہ داخلے ایڈمیشن قبول التسجيل ثبت-نام प्रवेश एडमिशन
exam: exam exams examination imtihan imtihaan امتحان امتحانات ایگزام اختبار اختبارات امتحان-ها परीक्षा एग्जाम
class: class classes klas kaksha جماعت کلاس کلاسز صف-دراسي فصل-دراسي صفوف کلاس-ها कक्षा क्लास
pharmacy: pharmacy pharmacies farmasi dawakhana medical-store فارمیسی دوا-خانہ دواخانہ صيدلية صيدليات داروخانه फार्मेसी दवाखाना
bakery: bakery bakeries bekri bekary بیکری بیکریز مخبز مخابز نانوایی बेकरी
factory: factory factories factry karkhana karkhanah فیکٹری فیکٹریاں کارخانہ مصنع مصانع کارخانه फैक्ट्री कारखाना
truck: truck trucks trak ٹرک ٹرکس شاحنة شاحنات کامیون ट्रक
fleet: fleet fleets گاڑیاں-کا-بیڑہ اسطول أسطول ناوگان बेड़ा
vehicle: vehicle vehicles gaari gaadi gari گاڑی گاڑیاں مركبة مركبات سيارة سيارات خودرو वाहन गाड़ी
fuel: fuel petrol diesel ईंधन ایندھن پیٹرول ڈیزل وقود بنزین وقود-ديزل पेट्रोल डीजल ईंधन
route: route routes rasta raasta رستہ راستہ روٹ روٹس مسار طريق مسیر रास्ता रूट
tracking: tracking tracker trackng ٹریکنگ ٹریکر تتبع تعقب ردیابی ट्रैकिंग
inspection: inspection inspections muaina muayena معائنہ انسپیکشن فحص تفتيش بازرسی निरीक्षण
training: training trainings tarbiyat tarbiat تربیت ٹریننگ تدريب تدریب آموزش प्रशिक्षण ट्रेनिंग
hiring: hiring recruit recruitment bharti bharti-karna بھرتی ریکروٹمنٹ توظيف تعيين استخدام استخدام-نیرو भर्ती
firing: firing barkhast barkhasti برطرفی برخاستگی إنهاء-خدمة اخراج बर्खास्त
resignation: resignation resign istifa استعفیٰ استعفی استقالة استعفا इस्तीफा
promotion: promotion promotions pramoshan ترقی پروموشن ترقيه ترقية ارتقاء पदोन्नति प्रमोशन
advertising: advertising advertisement ad ads ishtihar ishtehar اشتہار اشتہارات ایڈ ایڈز إعلان إعلانات اعلان تبلیغات विज्ञापन
marketing: marketing market-karna ماركيتنگ مارکیٹنگ تسويق تسویق بازاریابی मार्केटिंग
social: social-media facebook instagram tiktok فیس-بک فیسبک انسٹاگرام ٹک-ٹاک فيسبوك انستغرام تيك-توك फेसबुक इंस्टाग्राम
loyalty: loyalty loyal wafadari وفاداری لائلٹی ولاء وفاء وفادارى निष्ठा
member: membership member members rukniyat رکنیت ممبرشپ ممبر ممبرز عضوية عضو أعضاء اعضاء عضویت सदस्यता सदस्य मेंबर
subscription: subscription subscriptions subscrption sabskripshan سبسکرپشن اشتراک اشتراک-ماہانہ اشتراکات اشتراك اشتراک-ماهانه सब्सक्रिप्शन
rental: rental rentals rentl kiraye-par کرایہ-پر ریئنٹل تأجير تاجیر إيجارات اجاره-دهی किराये
property: property properties jaidad jayedad جائیداد پراپرٹی عقار عقارات ملک ملکیت संपत्ति प्रॉपर्टी जायदाद
flat: flat flats apartment apartments flaat فلیٹ فلیٹس اپارٹمنٹ شقة شقق آپارتمان अपार्टमेंट फ्लैट
construction: construction tameer tamir تعمیر-سازی تعمیراتی کنسٹرکشن إنشاء بناء ساخت‌وساز निर्माण कंस्ट्रक्शन
repairs: marammat-kaam مرمتی-کام ترميم ترمیم بازسازی जीर्णोद्धार
clinic: clinic clinics clinik kliniq کلینک کلینکس عيادة عيادات کلینیک क्लिनिक
hospital: hospital hospitals haspatal aspatal ہسپتال اسپتال ہسپتالوں مستشفى مستشفيات بیمارستان अस्पताल हॉस्पिटल
medicine: medicine medicines dawai dawa dawaiyan دوا دوائیں دوائی ادویات دواء أدوية ادویه दवा दवाई
prescription: prescription prescriptions parchi parchiyan نسخہ پرچی پرچیاں وصفة وصفات نسخه पर्ची नुस्खा
lab: lab labs laboratory test-lab لیب لیبارٹری مختبر مختبرات آزمایشگاه लैब प्रयोगशाला
school: school schools skool madrasa madrasah اسکول سکول مدرسہ مدارس مدرسة مدارس-أهلية دبستان स्कूल मदरसा
college: college colleges kalij کالج کالجز کلیة کليات دانشکده कॉलेज
university: university universities yunivarsity جامعہ یونیورسٹی جامعة جامعات دانشگاه विश्वविद्यालय यूनिवर्सिटी
salon: salon salons saloon سیلون سیلونز صالون صالونات سالن सैलून
hotel: hotel hotels hotal ہوٹل ہوٹلز فندق فنادق هتل होटल
restaurant: restaurant restaurants resturant restorant ریسٹورنٹ ریسٹورنٹس مطعم مطاعم رستوران रेस्टोरेंट रेस्तरां
kitchen: kitchen kitchens kichan bawarchi khana-khana باورچی-خانہ کچن مطبخ مطابخ آشپزخانه रसोई किचन
menu: menu menus mainu مینو مینیو قائمة قوائم منو मेन्यू
food: food khana khaana کھانا خوراک کھانے طعام أكل اکل غذا खाना भोजन
vegetable: vegetable vegetables sabzi sabji sabziyan سبزی سبزیاں خضار خضروات سبزیجات सब्जी सब्ज़ी
fruit: fruit fruits phal fal پھل پھلوں فاکهة فواكه فاكهة میوه फल
mango: mango mangoes aam آم مانجو منجا انبه आम
milk: milk doodh dudh دودھ حليب حلیب شیر दूध
dairy: dairy dairies dairi ڈیری ڈیریاں ألبان البان لبنیات डेयरी
poultry: poultry murghi murgi مرغی پولٹری دواجن دجاج مرغداری मुर्गी पोल्ट्री
cattle: cattle janwar mawashi مویشی جانور ماشیہ ماشية ماشیه पशु मवेशी
fertilizer: fertilizer fertilizers khaad khad کھاد فرٹیلائزر سماد أسمدة اسمدة کود खाद उर्वरक
seed: seed seeds beej bij بیج بیجوں بذور بذرة بذر बीज
water: water pani paani پانی ماء مياه میاه آب पानी
electricity: electricity bijli bijlee بجلی کرنٹ كهرباء کهرباء برق बिजली
gas: gas gaas گیس غاز گاز गैस
generator: generator generators jaenretar جنریٹر جنریٹرز مولد مولدات ژنراتور जनरेटर
solar: solar solar-panel سولر سولر-پینل شمسي طاقة-شمسية خورشیدی सोलर
electrician: electrician electricians bijli-wala الیکٹریشن بجلی-والا كهربائي كهربائيين برقکار इलेक्ट्रीशियन
plumber: plumber plumbers plamber پلمبر نلکے-والا سباك سباكين لوله‌کش प्लंबर
carpenter: carpenter carpenters barhai badhai بڑھئی کارپینٹر نجار نجارين نجار-ها बढ़ई कारपेंटर
tailor: tailor tailors darzi درزی ٹیلر خياط خياطين خیاط दर्ज़ी टेलर
cloth: cloth clothes clothing kapra kapray kapre کپڑا کپڑے کلاتھ ملبوسات قماش ثياب پارچه कपड़ा कपड़े
garment: garment garments garmnt گارمنٹ گارمنٹس ملابس لباس गारमेंट
shoes: shoes shoe joota jootay جوتا جوتے شوز أحذية احذیه کفش जूता जूते
furniture: furniture furnitur fernichar فرنیچر فرنیچرز أثاث اثاث مبلمان फर्नीचर
electronics: electronics electronic ilectronics الیکٹرانکس الیکٹرانک إلكترونيات الکترونیک इलेक्ट्रॉनिक्स
mobile: mobile-shop mobile-phone موبائل-شاپ هاتف-محمول موبایل
grocery: grocery groceries kiryana karyana kariyana کریانہ گروسری بقالة بقالات خواربار किराना ग्रोसरी
pharma: pharma pharmaceutical pharmaceuticals فارما ادویہ-سازی صيدلاني صیدلانیه फार्मा
cosmetics: cosmetics makeup kosmetiks کاسمیٹکس میک-اپ مستحضرات-التجميل لوازم-آرایشی कॉस्मेटिक्स
jewellery: jewellery jewelry zewar zeywar زیور زیورات جیولری مجوهرات مجوهرات-ذهب جواهر ज़ेवर आभूषण ज्वेलरी
gold: gold sona سونا گولڈ ذهب طلا सोना
silver: silver chandi چاندی سلور فضة نقره चांदी
currency: currency currencies karansi کرنسی عملة عملات ارز मुद्रा
rupee: rupee rupees rupay rupaye rupya روپیہ روپے روپیہ-پاکستانی روبية روپیه रुपया रुपये
dirham: dirham dirhams dhs aed درہم دراہم درهم دراهم दिरहम
dollar: dollar dollars dolar ڈالر ڈالرز دولار دولارات دلار डॉलर
exchange_rate: exchange-rate rate-of-exchange شرح-التحويل نرخ-ارز विनिमय-दर
interest: interest sood sud سود فائدة-بنكية فوائد بهره ब्याज सूद
insurance: insurance bima insurans انشورنس بیمہ تأمين تامين-ضد بیمه बीमा इंश्योरेंस
guarantee: guarantee warranty guaranty gaarantee گارنٹی وارنٹی ضمان ضمانة کفالت گارانتی वारंटी गारंटी
suggestion: complaint-box suggestion suggestions mashwara mashwarah مشورہ تجویز مشورے اقتراح اقتراحات پیشنهاد सुझाव सलाह
approval: approval manzoori manzuri منظوری منظور موافقة اعتماد تأیید تاییدیه मंज़ूरी अनुमोदन
signature: signature signatures dastkhat dastakhat دستخط دستخطوں توقيع توقیع امضاء امضا हस्ताक्षर दस्तख़त
document: document documents documnt dastavez dastawez دستاویز دستاویزات ڈاکومنٹ ڈاکومنٹس وثيقة وثائق مستند مستندات سند दस्तावेज़ डॉक्यूमेंट
file: file files faail فائل فائلیں فائلز ملف ملفات پرونده फाइल
photo: photo photos pic pics tasveer tasvir تصویر تصاویر فوٹو فوٹوز صورة صور عکس फोटो तस्वीर
video: video videos vidio ویڈیو ویڈیوز فيديو فيديوهات ویدیو वीडियो
voice: voice-note voicenote voice-message وائس-نوٹ وائس-میسج رسالة-صوتية پیام-صوتی वॉइस-नोट
link: link links lnk لنک لنکس رابط روابط لینک लिंक
screenshot: screenshot screenshots skreenshot اسکرین-شاٹ اسکرین‌شاٹ لقطة-شاشة لقطات-شاشة اسکرین‌شات स्क्रीनशॉट
pdf: pdf pdfs پی-ڈی-ایف پی‌دی‌اف بی-دی-اف पीडीएफ
excel: excel spreadsheet spreadsheets ایکسل شیٹ اسپریڈ-شیٹ جدول-بيانات اکسل एक्सेल
paper: paper kaghaz kagaz kaghzaat کاغذ کاغذی کاغذات ورق أوراق اوراق کاغذبازی कागज़ कागज
manual: manual manually haath-se hath-se ہاتھ-سے دستی یدوي يدوي یدوی हाथ-से मैनुअल
automatic: automatic khud-ba-khud khudkar خودکار آٹومیشن آٹومیٹک آلي تلقائي أوتوماتيك اتوماتیک ऑटोमैटिक ऑटोमेशन
digital: digital dijital ڈیجیٹل رقمي رقمی دیجیتال डिजिटल
online: online onlain آن-لائن آنلائن اونلاين اون-لاين أونلاين آنلاین ऑनलाइन
offline: offline oflain آف-لائن آفلائن غير-متصل آفلاین ऑफलाइन
delivery_charges: delivery-charges shipping shiping ڈیلیوری-چارجز شپنگ رسوم-التوصيل رسوم-الشحن هزینه-ارسال शिपिंग
discount_code: coupon coupons voucher vouchers kupon کوپن واؤچر قسيمة قسائم كوبون کوپن-تخفیف कूपन वाउचर
loyalty_points_scheme: inam-points پوائنٹس ریوارڈ ریوارڈز نقاط مكافآت امتیاز पॉइंट्स रिवॉर्ड
cashier: cashier cashiers kashiyar کیشیئر کیشیر أمين-الصندوق امين-الصندوق صندوق‌دار कैशियर
counter: counter counters kaunter کاؤنٹر کاؤنٹرز نضد عداد काउंटर
register_cash: cash-register cash-counter گلہ گلا کیش-رجسٹر صندوق-النقد صندوق गल्ला
stockout: stockout out-of-stock stock-out stockkhatam اسٹاک-آؤٹ اسٹاک-ختم نفاد-المخزون نفاد ناموجود स्टॉक-खत्म
overstock: overstock overstocking dead-stock deadstock اوور-اسٹاک ڈیڈ-اسٹاک مخزون-راكد مخزون-زائد اضافی-موجودی ओवरस्टॉक
reorder: reorder re-order reorder-level ری-آرڈر دوبارہ-آرڈر إعادة-الطلب سفارش-مجدد रीऑर्डर
expiry: expiry expire expired expiration expirydate میعاد میعاد-ختم ایکسپائری تاريخ-الانتهاء انقضاء انقضا تاریخ-انقضا एक्सपायरी
batch: batch batches batchain بیچ بیچز دفعة-إنتاج دفعات دسته बैच
payable: payable payables udhaar-dena واجب-الدفع ذمم-دائنة قابل-پرداخت देय
receivable: receivable receivables udhaar-lena قابل-وصول ذمم-مدينة مطالبات دریافتنی प्राप्य
collection: collection collections wasooli wasuli وصولی کلیکشن تحصيل تحصیل مجموعة جمع‌آوری वसूली कलेक्शन
dues: dues due baqaya baqaye بقایا واجبات مستحقات متأخرات بدهی बकाया
installment: installment installments instalment qist qisten قسط قسطیں اقساط قسط-ها किस्त क़िस्त
tip: tip tips baksheesh bakshish بخشش ٹپ ٹپس إكرامية اكرامیه बख्शीश टिप
complaints_handling: helpline hotline helplines ہیلپ-لائن ہاٹ-لائن خط-مساعدة خط-ساخن هات-لاین हेल्पलाइन
employee_id: id-card idcard shanakhti-card شناختی-کارڈ آئی-ڈی-کارڈ بطاقة-هوية بطاقة-الهوية كارت-الهوية کارت-ملی पहचान-पत्र आईडी-कार्ड
cnic: cnic emirates-id شناختی-کارڈ-نمبر هوية-إماراتية هویت
uniform: uniform uniforms yoonifarm یونیفارم وردی زی-موحد زي-موحد لباس-فرم यूनिफॉर्म वर्दी
safety: safety hifazat hifazati حفاظت سیفٹی سلامة أمان ايمنی ایمنی सुरक्षा सेफ्टी
security: security guard guards chowkidar chaukidar سیکیورٹی گارڈ چوکیدار حارس حراسة أمن امن حراست सिक्योरिटी चौकीदार
cleaning: cleaning safai sifai صفائی کلیننگ تنظيف نظافة نظافت सफाई क्लीनिंग
parking: parking parkin پارکنگ مواقف موقف پارکینگ पार्किंग
tickets: ticket tickets tikat ٹکٹ ٹکٹس تذكرة تذاكر بلیط टिकट
events: event events ایونٹ ایونٹس تقریب تقریبات حفل حفلات فعالیت इवेंट
wedding: wedding weddings shaadi shadi شادی شادیاں شادی-ہال حفل-زفاف زفاف عروسی शादी विवाह
hall: hall halls marquee ہال میرج-ہال قاعة قاعات سالن-همایش हॉल
catering: catering cateringwala کیٹرنگ کیٹررز تموين ضيافة کترینگ केटरिंग
photography: photography fotography فوٹوگرافی فوٹوگرافر مصور تصویربرداری फोटोग्राफी फोटोग्राफर
travel: travel travels tour tours safar سفر ٹریول ٹور ٹورز سياحة رحلات سفر-ها यात्रा ट्रैवल टूर
visa: visa visas vizah ویزا ویزے تأشيرة تاشيرة تأشيرات ویزای वीज़ा
flight: flight flights flite فلائٹ فلائٹس رحلة-جوية رحلات-جوية پرواز फ्लाइट उड़ान
shipping_line: freight cargo cargoes fraight کارگو فریٹ شحن-بضائع بضائع بار माल-भाड़ा कार्गो
customs: customs kastam کسٹم کلیئرنس جمارك جمرك ترخيص-جمركي گمرک कस्टम
import: import imports imported darakhmad dar-amad درآمد-مال امپورٹ استيراد واردات واردات-کالا आयात इम्पोर्ट
export: export exports exported bar-amad baramad برآمد ایکسپورٹ تصدير صادرات صادرات-کالا निर्यात एक्सपोर्ट
offer: offer offers pesh-kash پیشکش آفر آفرز عرض عروض ऑफर
sample: sample samples namuna نمونہ نمونے سیمپل عينة عينات نمونه नमूना सैंपल
trial: trial demo ڈیمو آزمائشی تجربة تجریبی ٹرائل ट्रायल डेमो
wholesale: wholesale wholesaler thok تھوک ہول-سیل ہولسیل جملة تجارة-الجملة عمده थोक होलसेल
retail: retail retailer khudra خردہ ریٹیل تجزئة خرده खुदरा रिटेल
agent: agent agents broker brokers dalal ایجنٹ ایجنٹس دلال وسيط وكلاء وکیل एजेंट दलाल
supervisor: supervisor supervisors nigran نگران سپروائزر مشرف مشرفين سرپرست सुपरवाइज़र निगरानी
helper: helper helpers madadgar مددگار ہیلپر مساعد معاون सहायक हेल्पर
payslip: payslip salary-slip تنخواہ-سلپ كشف-راتب فیش-حقوق
stationery: stationery stationary اسٹیشنری قرطاسية स्टेशनरी
hardware: hardware ہارڈ-ویئر ہارڈویئر عتاد सख्त-हार्डवेयर हार्डवेयर
paint: paint colour color rang رنگ پینٹ دهان طلاء ألوان पेंट रंग
printing: printing print press chhapai چھپائی پرنٹنگ طباعة چاپ प्रिंटिंग छपाई
laundry: laundry dhobi لانڈری دھوبی مغسلة غسيل लॉन्ड्री धोबी
gym: gym fitness جم فٹنس نادي-رياضي صالة-رياضية باشگاه जिम फिटनेस
ecommerce: ecommerce e-commerce shopify daraz ای-کامرس ایکامرس تجارة-إلكترونية ई-कॉमर्स
""".strip().splitlines()
