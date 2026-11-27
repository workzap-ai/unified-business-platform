/**
 * Live captions in Roman Urdu: Hindi (Devanagari) and Urdu script become Latin letters, in the
 * browser, so a caption never shows Hindi letters. The same letter-by-letter rewrite as the
 * server's `roman_urdu.rules` (the saved transcript is rewritten by a model on the server and is
 * more polished; a caption has to appear at once, so it uses the plain rewrite). English words and
 * digits are left as they are.
 */

const CONSONANTS: Record<string, string> = {
  क: "k",
  ख: "kh",
  ग: "g",
  घ: "gh",
  ङ: "ng",
  च: "ch",
  छ: "chh",
  ज: "j",
  झ: "jh",
  ञ: "n",
  ट: "t",
  ठ: "th",
  ड: "d",
  ढ: "dh",
  ण: "n",
  त: "t",
  थ: "th",
  द: "d",
  ध: "dh",
  न: "n",
  प: "p",
  फ: "f",
  ब: "b",
  भ: "bh",
  म: "m",
  य: "y",
  र: "r",
  ल: "l",
  व: "w",
  श: "sh",
  ष: "sh",
  स: "s",
  ह: "h",
  ळ: "l",
};
const NUKTA: Record<string, string> = {
  क: "q",
  ख: "kh",
  ग: "gh",
  ज: "z",
  ड: "r",
  ढ: "rh",
  फ: "f",
};
const VOWELS: Record<string, string> = {
  अ: "a",
  आ: "aa",
  इ: "i",
  ई: "ee",
  उ: "u",
  ऊ: "oo",
  ऋ: "ri",
  ए: "e",
  ऐ: "ai",
  ओ: "o",
  औ: "au",
  ऑ: "o",
};
const MATRAS: Record<string, string> = {
  "ा": "aa",
  "ि": "i",
  "ी": "ee",
  "ु": "u",
  "ू": "oo",
  "ृ": "ri",
  "े": "e",
  "ै": "ai",
  "ो": "o",
  "ौ": "au",
  "ॉ": "o",
};
const NASAL: Record<string, string> = { "ं": "n", "ँ": "n", "ः": "h" };
const VIRAMA = "्";
const NUKTA_MARK = "़";

const URDU: Record<string, string> = {
  ا: "a",
  آ: "aa",
  ب: "b",
  پ: "p",
  ت: "t",
  ٹ: "t",
  ث: "s",
  ج: "j",
  چ: "ch",
  ح: "h",
  خ: "kh",
  د: "d",
  ڈ: "d",
  ذ: "z",
  ر: "r",
  ڑ: "r",
  ز: "z",
  ژ: "zh",
  س: "s",
  ش: "sh",
  ص: "s",
  ض: "z",
  ط: "t",
  ظ: "z",
  ع: "",
  غ: "gh",
  ف: "f",
  ق: "q",
  ک: "k",
  ك: "k",
  گ: "g",
  ل: "l",
  م: "m",
  ن: "n",
  ں: "n",
  ہ: "h",
  ھ: "h",
  ۃ: "h",
  ء: "",
  ئ: "",
  ؤ: "o",
  ی: "ee",
  ي: "ee",
  ے: "e",
  ۓ: "e",
  و: "o",
  "ّ": "",
  "َ": "a",
  "ِ": "i",
  "ُ": "u",
  "ً": "",
  "ٍ": "",
  "ٰ": "a",
  "ْ": "",
  "،": ",",
  "؟": "?",
  "۔": ".",
};

const COMMON: Record<string, string> = {
  में: "mein",
  मैं: "main",
  है: "hai",
  हैं: "hain",
  नहीं: "nahi",
  क्या: "kya",
  और: "aur",
  का: "ka",
  की: "ki",
  के: "ke",
  को: "ko",
  से: "se",
  पर: "par",
  यह: "yeh",
  वह: "woh",
  हम: "hum",
  आप: "aap",
  मेरा: "mera",
  मेरी: "meri",
  मुझे: "mujhe",
  तुम: "tum",
  कुछ: "kuch",
  बहुत: "bohat",
  लेकिन: "lekin",
  तो: "to",
  भी: "bhi",
  ही: "hi",
  कर: "kar",
  करो: "karo",
  बताओ: "batao",
  चाहिए: "chahiye",
  सकते: "sakte",
  सकती: "sakti",
  हो: "ho",
  था: "tha",
  थी: "thi",
  थे: "the",
  कौन: "kaun",
  कैसे: "kaise",
  कब: "kab",
  कहाँ: "kahan",
  अब: "ab",
  जी: "ji",
  हाँ: "haan",
  ठीक: "theek",
  अच्छा: "acha",
  सलूशन: "solution",
  सिस्टम: "system",
  बेकरी: "bakery",
  टीम: "team",
  ऑर्डर: "order",
  ऑर्डर्स: "orders",
  बिज़नेस: "business",
  कारोबार: "karobar",
  नाम: "naam",
  लोग: "log",
  काम: "kaam",
  हेलो: "hello",
  ہے: "hai",
  ہیں: "hain",
  میں: "mein",
  میرا: "mera",
  میری: "meri",
  کا: "ka",
  کی: "ki",
  کے: "ke",
  کو: "ko",
  سے: "se",
  پر: "par",
  اور: "aur",
  نہیں: "nahi",
  کیا: "kya",
  آپ: "aap",
  ہم: "hum",
  مجھے: "mujhe",
  یہ: "yeh",
  وہ: "woh",
  بہت: "bohat",
  لیکن: "lekin",
  تو: "to",
  بھی: "bhi",
  ہی: "hi",
  کر: "kar",
  کریں: "karein",
  بتاؤ: "batao",
  چاہیے: "chahiye",
  سکتے: "sakte",
  سکتی: "sakti",
  ہو: "ho",
  تھا: "tha",
  تھی: "thi",
  تھے: "the",
  کون: "kaun",
  کیسے: "kaise",
  کب: "kab",
  کہاں: "kahan",
  اب: "ab",
  جی: "ji",
  ہاں: "haan",
  ٹھیک: "theek",
  اچھا: "acha",
  سلوشن: "solution",
  سسٹم: "system",
  بیکری: "bakery",
  ٹیم: "team",
  آرڈر: "order",
  آرڈرز: "orders",
  بزنس: "business",
  نام: "naam",
  کاروبار: "karobar",
  دکان: "dukan",
  لوگ: "log",
  کام: "kaam",
  ہیلو: "hello",
};

const SCRIPT = /[ऀ-ॿ؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]+/g;
const DEVANAGARI = /[ऀ-ॿ]/;
const NATIVE_DIGITS: Record<string, string> = Object.fromEntries(
  [..."०१२३४५६७८९"]
    .map((d, i) => [d, String(i)])
    .concat([..."٠١٢٣٤٥٦٧٨٩"].map((d, i) => [d, String(i)]))
    .concat([..."۰۱۲۳۴۵۶۷۸۹"].map((d, i) => [d, String(i)])),
);

type Unit = { letters: string; vowel: string; kind: "C" | "V" };

function devanagariWord(word: string): string {
  const units: Unit[] = [];
  const chars = [...word];
  for (let i = 0; i < chars.length; i += 1) {
    const ch = chars[i];
    if (ch in CONSONANTS) {
      let letters = CONSONANTS[ch];
      if (chars[i + 1] === NUKTA_MARK) {
        letters = NUKTA[ch] ?? letters;
        i += 1;
      }
      units.push({ letters, vowel: "a", kind: "C" });
    } else if (ch in VOWELS) {
      units.push({ letters: "", vowel: VOWELS[ch], kind: "V" });
    } else if (ch in MATRAS && units.length) {
      units[units.length - 1].vowel = MATRAS[ch];
    } else if (ch === VIRAMA && units.length) {
      units[units.length - 1].vowel = "";
    } else if (ch in NASAL && units.length) {
      units[units.length - 1].vowel += NASAL[ch];
    } else if (ch !== NUKTA_MARK) {
      units.push({ letters: ch, vowel: "", kind: "V" });
    }
  }
  let out = "";
  units.forEach((u, n) => {
    let vowel = u.vowel;
    if (u.kind === "C" && vowel === "a") {
      const last = n === units.length - 1;
      const before = n > 0 && units[n - 1].vowel !== "";
      const after = units[n + 1];
      const longNext =
        !!after &&
        after.kind === "C" &&
        after.vowel !== "" &&
        after.vowel !== "a";
      if (
        last ||
        (n > 0 && before && longNext && !units[n - 1].vowel.endsWith("a"))
      ) {
        vowel = "";
      }
    }
    out += u.letters + vowel;
  });
  return out
    .replace(/(.)\1{2,}/g, "$1$1")
    .replace("chchh", "chh")
    .replace("shsh", "sh");
}

const URDU_VOWELS = new Set(["a", "e", "i", "o", "u"]);

function urduWord(word: string): string {
  let out = "";
  for (const ch of word) {
    const part = URDU[ch];
    if (part === undefined) {
      out += ch;
      continue;
    }
    if (
      out &&
      part &&
      !URDU_VOWELS.has(part[0]) &&
      !URDU_VOWELS.has(out[out.length - 1])
    ) {
      if (!(out.endsWith("h") && part === "h")) out += "a";
    }
    out += part;
  }
  return out.replace(/(.)\1{2,}/g, "$1$1");
}

function tidy(word: string): string {
  return word
    .replace(/(?<=.)aa/g, "a")
    .replace(/(?<=.)ee/g, "i")
    .replace(/(?<=.)oo/g, "u");
}

/** True when the text has Hindi or Urdu letters. */
export function needsRoman(text: string): boolean {
  return new RegExp(SCRIPT.source).test(text);
}

/** The text with every Hindi and Urdu word in Latin letters (Roman Urdu). */
export function toRomanUrdu(text: string): string {
  if (!needsRoman(text)) return text;
  const digits = text.replace(/[०-९٠-٩۰-۹]/g, (d) => NATIVE_DIGITS[d] ?? d);
  return digits.replace(SCRIPT, (w) => {
    if (w in COMMON) return COMMON[w];
    return tidy(DEVANAGARI.test(w) ? devanagariWord(w) : urduWord(w));
  });
}
