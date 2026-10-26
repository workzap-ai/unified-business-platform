# ruff: noqa: E501  (one language per line reads better than wrapped patterns)
"""The reply linter's phrase sets for Urdu script, Arabic, Hindi, French, Spanish and Persian.

`constitution.py` builds its rules from English and Roman Urdu; each pattern below is the same rule
in the other languages, appended to the matching English pattern (every string starts with "|").
Roman Urdu, English, Urdu script and Arabic have fixed lines in `constitution.py`; French, Spanish,
Hindi and Persian replies are written by the model in the person's language, and these patterns
are what catches a rule break in them. Non-Latin patterns carry no word boundaries (prefixes and
combining marks stick to the word); Latin ones use them.

Only the rules the answer-first, tone, echo, closer, secrets and forecast work added, plus the
sentence ends, the AI words and the "are you human?" question, are here. The older safety lines
(card and password words, "payment received") are English, Roman Urdu, Urdu and Arabic only."""

import re
import unicodedata

ZW = "‌"  # the Persian half-space
WORD = r"[^\s.!?؟۔।]+"

# --- R-DISC-01 (the first message says pi is an AI) and the "are you human?" question -----------
AI_WORDS = r"|\bIA\b|intelligence artificielle|inteligencia artificial|هوش مصنوعی|एआई|कृत्रिम"
SELF_WORDS = r"|\bje\b|\bj'|\bsoy\b|\bestoy\b|\byo\b|هستم|من\s+pi"
ASKS_IF_AI = (
    r"|\b(?:êtes|etes)[- ]vous\b[^.?!]{0,20}\b(?:humain|robot|bot|personne|ia)\b"
    r"|\b(?:eres|es usted|usted es)\b[^.?!¿]{0,20}\b(?:humano|humana|persona|robot|bot|ia)\b"
    r"|\bhablo con (?:un|una)\b[^.?!¿]{0,20}\b(?:humano|persona|robot|bot|ia)\b"
    r"|क्या\s+(?:आप|तुम)[^?।]{0,20}(?:इंसान|इन्सान|इनसान|रोबोट|बॉट|मशीन|असली)"
    r"|آیا\s+(?:شما|تو)[^؟?]{0,20}(?:انسان|ربات|آدم|هوش مصنوعی)"
)

# --- R-ANS-01/02: a thank-you or "noted" is not an answer; yes/no questions ---------------------
ACK_OPENER = (
    r"|^\W*(?:شکریہ|نوٹ کر لیا|شكرا|شكراً|تم تسجيل|धन्यवाद|शुक्रिया|नोट कर लिया|ممنون|متشکرم|ثبت شد"
    r"|merci|c'est noté|noté|gracias|anotado|entendido)(?!\w)"
)
YES_NO_QUESTION = (
    r"|هل\s+(?:يمكنك|يمكن|تستطيع|تقدر|هناك)|کیا\s+آپ|क्या\s+(?:आप|तुम)|\b(?:pouvez|savez)-vous\b"
    r"|\best-ce que\b|\bpeut-on\b|¿(?:puede|puedes|pueden|se puede|tiene|tienen)\b|آیا"
)

# --- R-ECHO-01: the noted frame, in each language ---------------------------------------------
NOTED_FRAME = r"|نوٹ کر لیا|تم تسجيل(?:\s+ذلك)?|नोट कर लिया|c'est noté|\bnoté|\banotado|ثبت شد"
TITLE_STOP = "۔؟।"  # the Urdu and Hindi sentence ends the title must stop at

# --- R-TONE-01: verdict openers and judgements --------------------------------------------------
VERDICT_OPENER = (
    r"|^\W*(?:یہ|یہ ایک)\s+(?:ایک\s+)?(?:حقیقی|اصل|سنگین|بڑا|اہم)\s+(?:مسئلہ|مسلہ|بات)"
    r"|^\W*(?:هذه|هذا)\s+(?:مشكلة|مسألة)\s+(?:حقيقية|كبيرة|خطيرة|مهمة)"
    r"|^\W*(?:यह|ये)\s+(?:एक\s+)?(?:असली|वास्तविक|गंभीर|बड़ी|बड़ा|सच्ची)\s+(?:समस्या|परेशानी|बात)"
    r"|^\W*(?:c'est|il s'agit d')\s*(?:un|une)?\s*(?:vrai|véritable|réel|gros|sérieux|grave)\w*\s+(?:problème|souci)"
    r"|^\W*(?:es|esto es|eso es)\s+(?:un|una)\s+(?:verdadero\s+|gran\s+|serio\s+|grave\s+)?(?:problema|asunto)\s+(?:real|serio|grave)"
    r"|^\W*(?:es|esto es|eso es)\s+(?:un|una)\s+(?:verdadero|gran|serio|grave)\s+(?:problema|asunto)"
    r"|^\W*(?:این|اين)\s+(?:یک\s+)?(?:مشکل|مسئله)\s+(?:واقعی|جدی|بزرگ)"
)
THANKS_THEN_NOTED = r"|^\W*شکریہ[۔.،,!]?\s+(?:میں نے\s+)?نوٹ"
JUDGEMENT = (
    r"|\b(?:votre|ton|ta) (?:entreprise|commerce|activité|boutique) (?:va mal|est un échec|est nulle?)\b|\bvous vous y prenez mal\b"
    r"|\bsu negocio (?:va mal|es un desastre|está fracasando)\b|\b(?:lo|la) está haciendo mal\b|\blo estás haciendo mal\b"
    r"|आपका\s+(?:बिज़नेस|बिजनेस|व्यापार|धंधा)\s+(?:ख़राब|खराब|फेल)|आप\s+ग़लत\s+कर\s+रहे|आप\s+गलत\s+कर\s+रहे"
    r"|آپ\s+کا\s+(?:کاروبار|دھندا)\s+(?:خراب|ناکام|فیل)|آپ\s+غلط\s+کر\s+رہے"
    r"|عملك\s+(?:فاشل|سيء|سيئ)|أنت\s+تفعل\s+ذلك\s+بشكل\s+خاطئ|أنت\s+تخطئ"
    r"|کسب[" + ZW + r"\s]?وکار\s+شما\s+(?:بد|خراب|شکست)|شما\s+اشتباه\s+می[" + ZW + r"\s]?کنید"
)

# --- R-TONE-03: "please be patient", "I only ask because..." ------------------------------------
PATIENCE = (
    r"|براہ\s+کرم\s+صبر|يرجى\s+التحلي\s+بالصبر|الرجاء\s+الصبر|कृपया\s+धैर्य|\bveuillez\s+patienter\b|\bmerci de patienter\b"
    r"|\bsoyez\s+patient\b|\bayez\s+de la patience\b|\btenga\s+paciencia\b|\bpor favor,?\s+(?:sea\s+)?paciente\b"
    r"|لطفاً?\s+صبور\s+باشید|لطفاً?\s+صبر\s+کنید"
)

# --- R-ASK-05: the generic closer ("anything else?") -------------------------------------------
GENERIC_CLOSER = (
    r"|کچھ\s+اور\s+(?:بتانا|شامل|کہنا)|اور\s+کوئی\s+(?:مسئلہ|بات)|هل\s+(?:هناك|تريد)\s+(?:شيء|شي)\s+آخر|شيء\s+آخر|कुछ\s+और\s+(?:जोड़ना|बताना|कहना)|और\s+कोई\s+(?:समस्या|बात)"
    r"|\bautre chose\b|\bquelque chose d'autre\b|\bautre problème\b|\balgo más\b|\balguna otra\b|\botro problema\b"
    r"|چیز\s+دیگری|مورد\s+دیگری|مشکل\s+دیگری"
)

# --- A2-1.5-SECRETS: methods, vendors, pricing logic, how the catalogue is built -----------------
_V = r"(?:openai|chatgpt|gpt-?\d|anthropic|claude|gemini|llama|mistral|neon|railway|fastapi|postgres|twilio|supabase|vercel|aws|azure|langchain|pinecone)"
_USE = (
    r"(?:nous utilisons|on utilise|j'utilise|basé sur|propulsé par|fonctionne avec|construit avec|développé avec"
    r"|usamos|utilizamos|funciona con|basado en|impulsado por|construido con|desarrollado con"
    r"|उपयोग\s+करते|इस्तेमाल\s+करते|पर\s+आधारित|से\s+चलता|द्वारा\s+संचालित"
    r"|استعمال\s+کرتے|استعمال\s+کرتا|پر\s+مبنی|سے\s+چلتا"
    r"|نستخدم|أستخدم|مبني\s+على|يعمل\s+(?:بـ|على|مع)|مدعوم\s+(?:من|بـ)"
    r"|استفاده\s+می[" + ZW + r"\s]?کنیم|استفاده\s+می[" + ZW + r"\s]?کنم|بر\s+پایه|مبتنی\s+بر)"
)
SECRETS = (
    r"|" + _USE + r"[^.!?؟۔।\n]{0,30}?(?<![\w])" + _V + r"(?!\w)"
    r"|(?<![\w])"
    + _V
    + r"(?!\w)[^.!?؟۔।\n]{0,25}?"
    + _USE
    + r"|notre (?:méthode|processus|formule|algorithme|outil)s? (?:interne|secret|propriétaire)|logique de (?:tarification|prix)|formule de prix"
    r"|le catalogue est (?:construit|généré|créé) (?:par|à partir|avec)|comment (?:nous )?(?:construisons|le catalogue (?:est|se) (?:construit|génère))"
    r"|nuestro método (?:interno|secreto)|nuestra (?:fórmula|lógica) (?:interna|secreta|de precios)|lógica de precios|fórmula de precios"
    r"|el catálogo (?:se )?(?:construye|genera|crea|está construido)|cómo (?:construimos|se construye)"
    r"|हमारी?\s+(?:आंतरिक|गुप्त)\s+(?:विधि|प्रक्रिया|तकनीक|फॉर्मूला)|प्राइसिंग\s+लॉजिक|कीमत\s+(?:का|तय\s+करने\s+का)\s+(?:फॉर्मूला|लॉजिक)|कैटलॉग\s+(?:कैसे\s+)?(?:बनता|बनाया\s+जाता)"
    r"|ہمارا\s+(?:اندرونی|خفیہ)\s+(?:طریقہ|فارمولا|عمل)|قیمت\s+(?:کا|طے\s+کرنے\s+کا)\s+(?:فارمولا|منطق|لاجک)|پرائسنگ\s+لاجک|کیٹلاگ\s+(?:کیسے\s+)?(?:بنتا|بنایا\s+جاتا)"
    r"|طريقتنا\s+(?:الداخلية|السرية)|منطق\s+التسعير|معادلة\s+التسعير|صيغة\s+التسعير|كيف\s+(?:يتم\s+)?(?:بناء|يُبنى|يبنى)\s+الكتالوج|الكتالوج\s+(?:يُبنى|يبنى|مبني)\s+(?:من|بواسطة|باستخدام)"
    r"|روش\s+(?:داخلی|محرمانه)\s+ما|منطق\s+قیمت["
    + ZW
    + r"\s]?گذاری|فرمول\s+قیمت["
    + ZW
    + r"\s]?گذاری|کاتالوگ\s+چگونه\s+ساخته"
)

# --- R-PROM-01/03: guarantees and forecasts of the person's own numbers -------------------------
PROMISE = (
    r"|\bgaranti(?:e|es|s|t|ssons|rons|rai)\b|\bsans risque\b|\bgarantiz\w*|\bgarant[ií]a\b|\bsin riesgo\b"
    r"|(?:les ventes|le chiffre d'affaires|les bénéfices|les profits|les clients|les commandes|vos ventes|vos clients)\s+(?:vont|va)\s+(?:certainement |sûrement |forcément )?(?:augmenter|monter|doubler|grimper|exploser|revenir)\b"
    r"|\bvous\s+(?:allez|gagnerez|économiserez)\s+(?:plus|beaucoup|de l'argent)\b"
    r"|(?:las ventas|los ingresos|las ganancias|los clientes|los pedidos|sus ventas|sus clientes)\s+(?:van a\s+|vamos a\s+)?(?:definitivamente |seguro )?(?:subir|aumentar|crecer|duplicar|mejorar|volver)\b"
    r"|\b(?:las ventas|los ingresos|las ganancias|los clientes|los pedidos)\s+(?:aumentar[aá]n|subir[aá]n|crecer[aá]n|se duplicar[aá]n|mejorar[aá]n)\b"
    r"|\busted\s+(?:ganar[aá]|ahorrar[aá]|vender[aá])\b"
    r"|गारंटी|गारण्टी|(?:बिक्री|मुनाफ़ा|मुनाफा|ग्राहक|आमदनी|आय|ऑर्डर)\s+(?:ज़रूर\s+|जरूर\s+)?(?:बढ़ेगी|बढ़ेगा|बढ़ेंगे|बढ़\s+जाएगी|बढ़\s+जाएंगे|बढ़\s+जाएगा|दोगुनी\s+हो\s+जाएगी)"
    r"|आप\s+(?:ज़्यादा|ज्यादा|और)\s+(?:कमाएंगे|कमाएँगे|बचाएंगे|बचाएँगे)"
    r"|گارنٹی|ضمانت|(?:فروخت|سیل|منافع|آمدنی|گاہک|آرڈرز?)\s+(?:ضرور\s+)?(?:بڑھ\s+جائے\s+گی|بڑھے\s+گی|بڑھیں\s+گے|بڑھ\s+جائیں\s+گے|دوگنی\s+ہو\s+جائے\s+گی)"
    r"|نضمن|أضمن|اضمن|مضمون|بدون\s+مخاطر"
    r"|(?:ستزيد|سترتفع|سوف\s+تزيد|سوف\s+ترتفع|ستتضاعف|سوف\s+تتضاعف)\s+(?:ال)?(?:مبيعات|أرباح|ارباح|إيرادات|طلبات|عملاء|زبائن)"
    r"|(?:المبيعات|الأرباح|الطلبات|الإيرادات|الزبائن|العملاء)\s+(?:ستزيد|سترتفع|ستتضاعف|سوف\s+تزيد|سوف\s+ترتفع)"
    r"|تضمین|بدون\s+ریسک|(?:فروش|سود|درآمد|مشتری|مشتریان|سفارش(?:["
    + ZW
    + r"]?ها)?)\s+(?:شما\s+)?(?:قطعاً\s+|حتماً\s+|قطعا\s+|حتما\s+)?(?:افزایش\s+می["
    + ZW
    + r"\s]?یابد|زیاد\s+می["
    + ZW
    + r"\s]?شود|بالا\s+می["
    + ZW
    + r"\s]?رود|دو\s+برابر\s+می["
    + ZW
    + r"\s]?شود)"
)
# --- R-VOICE-02: the fixed offer ends "...? You can say no." (the tail only says no is fine) ----
OFFER_TAIL = (
    r"|vous\s+pouvez\s+(?:aussi\s+)?refuser|puede\s+(?:también\s+)?decir\s+que\s+no|आप\s+मना\s+भी\s+कर\s+सकते\s+हैं"
    r"|آپ\s+منع\s+بھی\s+کر\s+سکتے\s+ہیں|می[" + ZW + r"\s]?توانید\s+(?:هم\s+)?رد\s+کنید"
)


# --- The older safety lines (R-PAY-02, R-PRIV-03, R-PAY-05, R-DISC-03, R-DISC-04, R-HONEST-01) --------
SENSITIVE = (
    r"|numéro de (?:votre )?carte|carte (?:bancaire|de crédit|de débit)|\bmot de passe\b|\bcode (?:secret|pin|de sécurité|de vérification|otp)\b|\bcryptogramme\b|\bcvv\b|\biban\b|numéro de compte"
    r"|número de (?:su )?tarjeta|tarjeta (?:de crédito|de débito|bancaria)|\bcontraseña\b|\bclave\b|código (?:de verificación|de seguridad|otp|pin)|\bcódigo secreto\b|número de cuenta"
    r"|कार्ड\s+(?:नंबर|नम्बर)|क्रेडिट\s+कार्ड|डेबिट\s+कार्ड|पासवर्ड|ओटीपी|ओ\s?टी\s?पी|पिन\s+(?:कोड|नंबर)|सीवीवी|अकाउंट\s+नंबर|खाता\s+(?:संख्या|नंबर)|बैंक\s+(?:खाता|अकाउंट)"
    r"|شماره\s+کارت|کارت\s+(?:بانکی|اعتباری)|رمز\s+(?:عبور|کارت|دوم|یک["
    + ZW
    + r"\s]?بار["
    + ZW
    + r"\s]?مصرف|پویا)|گذرواژه|کد\s+(?:تایید|تأیید|امنیتی)|\bپین\b|شماره\s+حساب|شبا"
)
NATIONAL_ID = (
    r"|carte d'identité|numéro de passeport|\bpasseport\b|numéro de sécurité sociale"
    r"|\b(?:dni|nie|pasaporte|cédula|curp|rfc)\b|número de identificación|documento de identidad"
    r"|आधार|पैन\s+कार्ड|पासपोर्ट|पहचान\s+पत्र|राष्ट्रीय\s+पहचान"
    r"|کد\s+ملی|کارت\s+ملی|شماره\s+ملی|شناسنامه|پاسپورت|گذرنامه"
    r"|جواز\s+السفر|رقم\s+الجواز|الرقم\s+القومي|بطاقة\s+الرقم\s+القومي"
)
ASKING = (
    r"|\b(?:envoyez|envoyer|partagez|donnez|fournissez|indiquez|saisissez|tapez|communiquez)\b|\bj'ai besoin\b|\bquel(?:le)? est votre\b|\bpouvez-vous (?:m'envoyer|me donner|partager|me communiquer)\b"
    r"|\b(?:envíe(?:me)?|envíen|comparta|déme|proporcione|indique|escriba|dígame)\b|\bnecesito\b|\bme puede (?:enviar|dar)\b|\bcuál es su\b"
    r"|भेजिए|भेजें|भेज\s+दीजिए|बताइए|बताएं|दीजिए|शेयर\s+कीजिए|साझा\s+कीजिए|लिखिए|मुझे\s+चाहिए|चाहिए"
    r"|بفرستید|ارسال\s+کنید|به\s+من\s+بدهید|بدهید|بگویید|وارد\s+کنید|بنویسید|نیاز\s+دارم|چیست|ارسال\s+کریں"
)
REFUSING = (
    r"|\bne\s+[^.?!]{0,30}?\bpas\b|\bjamais\b|\bsans\b|\bpas besoin\b"
    r"|\bno\s+(?:me\s+)?(?:env[ií]e|comparta|d[eé]|escriba|necesito|le pido|pido)\b|\bnunca\b|\bsin\b|\bno hace falta\b|\bno es necesario\b"
    r"|नहीं|मत\s|बिना|ज़रूरत\s+नहीं|(?<!\w)न\s+(?:भेजें|भेजिए|दें|बताएं|लिखें|शेयर)"
    r"|نفرستید|نیازی\s+نیست|هرگز|هیچ["
    + ZW
    + r"\s]?وقت|بدون|نمی["
    + ZW
    + r"\s]?(?:خواهم|خواهیم|فرستید)|نکنید|مبادا"
)
PAYMENT_RECEIVED = (
    r"|\bpaiement\s+(?:bien\s+)?(?:reçu|confirmé|effectué|validé)\b|\b(?:nous\s+)?avons\s+(?:bien\s+)?reçu\s+(?:votre|le)\s+(?:paiement|virement|règlement|argent)\b|\bvirement\s+(?:reçu|confirmé)\b|\bj'ai\s+bien\s+reçu\s+(?:votre|le)\s+(?:paiement|virement)\b"
    r"|\bpago\s+(?:recibido|confirmado|acreditado)\b|\b(?:hemos|he)\s+recibido\s+(?:su|el)\s+(?:pago|transferencia|dinero)\b|\btransferencia\s+(?:recibida|confirmada)\b|\bya\s+recibimos\s+(?:su|el)\s+(?:pago|transferencia)\b"
    r"|भुगतान\s+(?:प्राप्त|मिल)|पेमेंट\s+(?:मिल|प्राप्त|हो\s+गया)|पैसे\s+मिल\s+गए|राशि\s+(?:प्राप्त|मिल)|हमें\s+(?:आपका\s+)?(?:भुगतान|पेमेंट)\s+मिल"
    r"|پرداخت\s+(?:شما\s+)?(?:دریافت|تأیید|تایید)\s+شد|مبلغ\s+(?:به\s+دست|دریافت)|پول\s+(?:رسید|دریافت)|واریز\s+(?:شما\s+)?(?:تأیید|تایید|دریافت)"
)
HUMAN_CLAIM = (
    r"|\bje suis (?:un |une )?(?:humain|humaine|vraie personne|personne réelle|homme|femme|mère|père)\b|\bma (?:famille|femme|mère|sœur)\b|\bmon (?:mari|père|frère|fils)\b|\bje m'appelle (?!pi\b)\w+|\bj'habite à\b|\bje suis de (?!workzap)\w{3,}"
    r"|\bsoy (?:un |una )?(?:humano|humana|persona real|persona|hombre|mujer|madre|padre)\b|\bmi (?:familia|esposa|esposo|madre|padre|hermano|hermana|hijo|hija)\b|\bme llamo (?!pi\b)\w+|\bvivo en\b|\bsoy de (?!workzap)\w{3,}"
    r"|मैं\s+(?:एक\s+)?(?:इंसान|इन्सान|असली\s+इंसान|आदमी|औरत|महिला)\s+हूँ|मेरा\s+परिवार|मेरी\s+(?:पत्नी|माँ|बहन|बेटी)|मेरे\s+(?:पति|पिता|भाई|बेटे)|मेरा\s+नाम\s+(?!pi\b)\S+"
    r"|میں\s+(?:ایک\s+)?(?:انسان|حقیقی\s+انسان|آدمی|عورت)\s+ہوں|میرا\s+خاندان|میری\s+(?:بیوی|ماں|بہن|بیٹی)|میرے\s+(?:شوہر|والد|بھائی|بیٹے)|میرا\s+نام\s+(?!pi\b)\S+"
    r"|أنا\s+(?:ال)?(?:إنسان|انسان|شخص\s+حقيقي|رجل|امرأة|إنسانة)\b|عائلتي|زوجتي|زوجي|\bأمي\b|\bأبي\b|اسمي\s+(?!pi\b)\S+|أعيش\s+في"
    r"|من\s+(?:یک\s+)?(?:انسان|آدم|مرد|زن)\s+(?:هستم|واقعی)|خانواده["
    + ZW
    + r"\s]?ام|همسرم|مادرم|پدرم|اسم\s+من\s+(?!pi\b)\S+|من\s+در\s+\S+\s+زندگی"
)
TEAM_READS = (
    r"|(?:notre )?(?:équipe|une personne|quelqu'un|un humain)\b[^.?!\n]{0,40}\b(?:lit|lira|lisent|consulte|surveille|voit)\b[^.?!\n]{0,25}\b(?:ce|cette|votre|vos)\s+(?:chat|conversation|messages?|discussion)"
    r"|(?:el equipo|nuestro equipo|una persona|alguien)\b[^.?!\n]{0,40}\b(?:lee|leerá|leen|revisa|ve|supervisa)\b[^.?!\n]{0,25}\b(?:este|esta|su|sus)\s+(?:chat|conversación|mensajes?)"
    r"|(?:टीम|कोई\s+व्यक्ति|कोई\s+इंसान)[^.?!।\n]{0,40}(?:पढ़|देख)[^.?!।\n]{0,25}(?:चैट|बातचीत|संदेश|मैसेज)"
    r"|(?:चैट|बातचीत|संदेश|मैसेज)[^.?!।\n]{0,40}(?:टीम|कोई\s+व्यक्ति)[^.?!।\n]{0,20}(?:पढ़|देख)"
    r"|(?:ٹیم|کوئی\s+شخص|کوئی\s+انسان)[^.؟!۔\n]{0,40}(?:پڑھ|دیکھ)[^.؟!۔\n]{0,25}(?:چیٹ|بات\s*چیت|پیغام|میسج)"
    r"|(?:چیٹ|بات\s*چیت|پیغام|میسج)[^.؟!۔\n]{0,40}(?:ٹیم|کوئی\s+شخص)[^.؟!۔\n]{0,20}(?:پڑھ|دیکھ)"
    r"|(?:الفريق|فريقنا|شخص|أحد)[^.؟!\n]{0,40}(?:يقرأ|سيقرأ|يقرؤون|يراجع|يرى|يشاهد)[^.؟!\n]{0,25}(?:المحادثة|الدردشة|الرسائل|الشات)"
    r"|(?:تیم|یک\s+نفر|کسی)[^.؟!\n]{0,40}(?:می["
    + ZW
    + r"\s]?خواند|خواهد\s+خواند|می["
    + ZW
    + r"\s]?بیند|بررسی\s+می["
    + ZW
    + r"\s]?کند)[^.؟!\n]{0,25}(?:چت|گفتگو|پیام)"
)
# R-HONEST-01: a duration or date pi was not given.
TIMELINE_STRONG = (
    r"|\b(?:dans|en|sous|d'ici)\s+(?:environ\s+|à peu près\s+|seulement\s+)?(?:\d+|un|une|deux|trois|quatre|cinq|six|sept|huit|dix|quelques)\s+(?:jours?|semaines?|mois|heures?|ans?)\b|\bd'ici (?:demain|la fin)\b"
    r"|\b(?:en|dentro de|para)\s+(?:unos\s+|alrededor de\s+|solo\s+)?(?:\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|diez)\s+(?:días?|semanas?|meses|horas?|años?)\b"
    r"|(?:\d+|एक|दो|तीन|चार|पाँच|पांच|छह|सात|आठ|दस)\s+(?:दिन|हफ्ते|हफ़्ते|सप्ताह|महीने|घंटे|घंटों)\s+(?:में|के\s+अंदर|तक)|कल\s+तक|अगले\s+(?:हफ्ते|सप्ताह|महीने)"
    r"|\d+\s+(?:ہفتے|دن|مہینے|گھنٹے)\s+(?:میں|تک)|اگلے\s+(?:ہفتے|مہینے)"
    r"|في\s+غضون\s+\S+|بعد\s+(?:\d+|يوم|يومين|أسبوع|أسبوعين|شهر|شهرين)"
    r"|(?:ظرف|طی|در)\s+(?:\d+|یک|دو|سه|چهار|پنج|شش|هفت|ده)\s+(?:روز|هفته|ماه|ساعت)|تا\s+فردا"
)
TIMELINE_WEAK = (
    r"|\b(?:demain|ce soir|la semaine prochaine|le mois prochain|cette semaine|le jour même)\b"
    r"|\b(?:mañana|esta noche|la próxima semana|el próximo mes|esta semana|el mismo día)\b"
    r"|(?:कल|आज\s+रात|अगले\s+हफ्ते|इस\s+हफ्ते|अगले\s+महीने|उसी\s+दिन)(?!\w)"
    r"|(?:کل|آج\s+رات|اگلے\s+ہفتے|اس\s+ہفتے|اگلے\s+مہینے)(?!\w)"
    r"|(?:غداً?|الليلة|الأسبوع\s+(?:القادم|المقبل)|هذا\s+الأسبوع|الشهر\s+(?:القادم|المقبل))(?!\w)"
    r"|(?:فردا|امشب|هفته\s+(?:بعد|آینده)|این\s+هفته|ماه\s+(?:بعد|آینده))(?!\w)"
)
PROMISE_CUE = (
    r"|\b(?:sera|seront|serai|pourra|pouvons|pouvez|peut|prêt|prête|livré|livrée|terminé|terminée|lancé|livrons|enverrons|aurez|aura|prend|prendra|devrait|normalement|généralement|habituellement)\b"
    r"|\b(?:será|serán|estará|estarán|podrá|podemos|listo|lista|entregado|terminado|lanzado|entregamos|enviaremos|tendrá|tarda|tardará|debería|normalmente|generalmente|habitualmente)\b"
    r"|होगा|होगी|होंगे|तैयार|भेज\s+देंगे|मिल\s+जाएगा|मिल\s+जाएगी|लगेंगे|लगेगा|आमतौर\s+पर"
    r"|ہو\s+جائے\s+گا|ہو\s+جائے\s+گی|ہوگا|ہوگی|تیار|بھیج\s+دیں\s+گے|ملے\s+گا|لگیں\s+گے|عام\s+طور\s+پر"
    r"|سيكون|ستكون|سيتم|جاهز|سنرسل|سنسلم|يستغرق|\bعادة|\bيجب"
    r"|خواهد\s+بود|می["
    + ZW
    + r"\s]?شود|آماده|ارسال\s+می["
    + ZW
    + r"\s]?کنیم|معمولاً|طول\s+می["
    + ZW
    + r"\s]?کشد"
)
NOTING = r"|\bnoté\b|\banotado\b|\banoté\b|नोट\s+कर\s+लिया|نوٹ\s+کر\s+لیا|تم\s+تسجيل|ثبت\s+شد"
HEARD_TIME = r"|jours?|semaines?|\bmois\b|d[ií]as?|semanas?|\bmes\b|दिन|हफ्ते|महीने|ہفتے|دن|مہینے|أسبوع|يوم|شهر|روز|هفته|ماه"

# --- slots.py: the generic closer and the one-word answers that skip it ------------------------
ANYTHING_ELSE = GENERIC_CLOSER + (
    r"|\bautre chose\b|\bd'autres? (?:problèmes?|questions?)\b|\botros? (?:problemas?|asuntos)\b|\balgo más\b"
    r"|कोई\s+और\s+(?:समस्या|बात|परेशानी)|کوئی\s+اور\s+(?:مسئلہ|بات)|هل\s+من\s+مشكلة\s+أخرى|مشكلة\s+أخرى|مشکل\s+دیگری"
)
SKIP_ACK = (
    r"^\W*(?:(?:d'accord|ok|oui|bon|merci|bien|hum+|hmm+|vale|bueno|gracias|sí|si|aja|ठीक(?:\s+है)?|हाँ|हां|जी|अच्छा|ओके|हम्म|धन्यवाद|शुक्रिया"
    r"|ٹھیک(?:\s+ہے)?|جی|اچھا|ہاں|شکریہ|ہمم|او\s+کے|حسنا|حسناً|طيب|تمام|نعم|شكرا|شكراً|أوكي|اوكي|همم|ماشي"
    r"|باشه|خب|بله|آره|مرسی|ممنون|اوکی|هوم|حله)(?!\w)\W*){1,3}$"
)

# --- open_requests.py: a timeline or a person asked for, and what addresses each ----------------
OPEN_TIMELINE = (
    r"combien de temps|dans combien de temps|quand (?:sera|aurai|est-ce)|d'ici quand|\bdélai\b|\blivraison\b"
    r"|cu[aá]nto (?:tiempo|tarda|demora)|cu[aá]ndo (?:estar[aá]|tendr[eé])|\bplazo\b|en cu[aá]nto tiempo"
    r"|कितने\s+दिन|कितना\s+समय|कब\s+तक|कब\s+मिलेगा|समय\s+सीमा"
    r"|کتنے\s+دن|کتنا\s+وقت|کب\s+تک|کب\s+ملے\s+گا|کتنی\s+دیر"
    r"|كم\s+(?:يستغرق|يأخذ|من\s+الوقت|يوم)|متى\s+(?:سيكون|يكون|تنتهون|سأحصل)|\bالمدة\b"
    r"|چقدر\s+(?:طول|زمان)|چند\s+روز|کی\s+(?:آماده|تحویل)|تا\s+کی\b|\bمدت\b"
)
OPEN_HUMAN = (
    r"parler (?:à|avec) (?:une personne|un humain|quelqu'un|un conseiller|un responsable)|une vraie personne|un vrai humain"
    r"|hablar con (?:una persona|un humano|alguien|un asesor|un responsable)|una persona real|un humano de verdad"
    r"|किसी\s+(?:इंसान|इन्सान|व्यक्ति)\s+से\s+बात|असली\s+इंसान|इंसान\s+से\s+बात|मैनेजर\s+से\s+बात"
    r"|کسی\s+انسان\s+سے\s+بات|حقیقی\s+انسان|انسان\s+سے\s+بات|مینیجر\s+سے\s+بات"
    r"|(?:أتحدث|اتحدث|أكلم|اكلم|التحدث|كلام)\s+(?:مع|إلى)\s+(?:شخص|إنسان|انسان|موظف|مدير)|شخص\s+حقيقي|إنسان\s+حقيقي"
    r"|با\s+(?:یک\s+)?(?:انسان|آدم|شخص|کارمند|مدیر)\s+(?:صحبت|حرف)|آدم\s+واقعی|انسان\s+واقعی"
)
ADDRESS_TIMELINE = (
    r"devis|document|plan|estimation|calendrier|équipe|délai|durée|cotización|presupuesto|documento|estimación"
    r"|cronograma|equipo|plazo|duración|कोट|दस्तावेज़|डॉक्यूमेंट|योजना|अनुमान|टीम|समय|दिन|کوٹ|دستاویز"
    r"|ڈاکیومنٹ|منصوبہ|اندازہ|ٹیم|وقت|عرض\s+السعر|المستند|الوثيقة|الخطة|التقدير|الفريق|المدة|الوقت"
    r"|پیشنهاد|قیمت|سند|برنامه|برآورد|تیم|زمان|مدت"
)
ADDRESS_HUMAN = (
    r"équipe|personne|humain|collègue|quelqu'un|responsable|equipo|persona|humano|colega|alguien"
    r"|टीम|व्यक्ति|इंसान|सहकर्मी|कोई|मैनेजर|ٹیم|شخص|انسان|ساتھی|کوئی|مینیجر|الفريق|إنسان|زميل|أحد|المدير|موظف"
    r"|تیم|انسان|همکار|کسی|مدیر|کارمند"
)

# Hindi, Urdu and Persian put the verb last: "the team reads your chat" is team, chat, verb (SOV).
TEAM_READS += (
    r"|(?:टीम|कोई\s+व्यक्ति|कोई\s+इंसान)[^.?!।\n]{0,25}(?:चैट|बातचीत|संदेश|मैसेज)[^.?!।\n]{0,25}(?:पढ़|देख)"
    r"|(?:ٹیم|کوئی\s+شخص|کوئی\s+انسان)[^.؟!۔\n]{0,25}(?:چیٹ|بات\s*چیت|پیغام|میسج)[^.؟!۔\n]{0,25}(?:پڑھ|دیکھ)"
    r"|(?:تیم|یک\s+نفر|کسی)[^.؟!\n]{0,25}(?:چت|گفتگو|پیام)[^.؟!\n]{0,25}(?:می["
    + ZW
    + r"\s]?خواند|خواهد\s+خواند|می["
    + ZW
    + r"\s]?بیند)"
)

# One form for combined letters (Hindi "ढ़" is one character or two): every phrase set is normalised
# the way `constitution.lint` normalises the reply.
for _name, _value in list(globals().items()):
    if _name.isupper() and isinstance(_value, str) and _name != "ZW":
        globals()[_name] = unicodedata.normalize("NFC", _value)

_NEG = unicodedata.normalize(
    "NFC",
    r"(?:pas|jamais|aucune?|sans|nunca|ninguna?|sin|no|नहीं|नही|कोई|कभी|نہیں|کوئی|لا|لن|ليس|بدون|نمی|هیچ|نه)",
)
# A promise word the sentence negates ("aucune garantie", "कोई गारंटी नहीं", "لا يمكننا ضمان")
NEGATED_BEFORE = re.compile(
    r"(?<!\w)" + _NEG + r"(?!\w)[\s" + ZW + r"]*(?:" + WORD + r"\s+){0,3}$", re.IGNORECASE
)
NEGATED_AFTER = re.compile(
    r"^\s*(?:" + WORD + r"\s+){0,2}(?<!\w)" + _NEG + r"(?!\w)", re.IGNORECASE
)
