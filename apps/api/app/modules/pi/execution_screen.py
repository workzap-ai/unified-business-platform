# ruff: noqa: E501
"""Controlled execution (Level 3): conservative secret screening. Fails closed.

Used on task text, tool arguments and tool results. Stricter than the audit redactor on purpose: it
REFUSES (nothing is stored or acted on) anything that looks like a credential, key, token, password,
OTP, card, IBAN, CNIC or a long number, by shape and by keyword, even when the match may be innocent.
A false refusal costs a rewording; a false pass could store a secret. Pure; linear time; never raises.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from app.modules.pi import execution_audit as audit

MAX_NODES = 500
MAX_DEPTH = 5
MAX_TEXT = 10_000

# keyword families: any occurrence (word-bounded after normalisation) is refused
_KEYWORDS = frozenset(
    "password passwd passcode pwd otp cvv cvc ccv pin iban cnic nic ssn secret token apikey "
    "credential credentials bearer passphrase swift routing seed mnemonic".split()
)
_PHRASES = (
    "api key",
    "access key",
    "private key",
    "secret key",
    "card number",
    "credit card",
    "debit card",
    "account number",
    "one time",
    "verification code",
    "security code",
    "login code",
    "sign in",
    "log in",
    "social security",
    "pass word",
    "pass code",
    "ssh rsa",
    "begin rsa",
    "begin private",
    "begin openssh",
    "پاسورڈ",
    "पासवर्ड",
    "ओटीपी",
    "او ٹی پی",
    "کارڈ نمبر",
    "कार्ड नंबर",
    "كلمه المرور",
    "كلمة المرور",
    "رمز التحقق",
)
_DIGITS = re.compile(r"\d(?:[\s.\-_/,]{0,3}\d){7,}")  # 8 or more digits in one run
_CNIC = re.compile(r"\b\d{5}[\s-]?\d{7}[\s-]?\d\b")
_IBAN = re.compile(r"\b[A-Za-z]{2}\d{2}[\s]?[A-Za-z0-9]{4}(?:[\s]?[A-Za-z0-9]{2,8}){2,7}\b")
_LONG = re.compile(r"[A-Za-z0-9+/_\-=]{20,}")
_PREFIXED = re.compile(
    r"\b(?:sk|pk|rk|ghp|gho|ghs|xox[abpr]|akia|asia|aiza|eyj|ya29|npm|glpat|shpat|whsec)[-_A-Za-z0-9]{6,}",
    re.IGNORECASE,
)
_HEX = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_URL_SECRET = re.compile(r"[?&;](?:[a-z_]*(?:key|token|secret|sig|pass|auth|code)[a-z_]*)=", re.I)
_ASSIGN = re.compile(
    r"\b[a-z_]*(?:key|token|secret|pass|pwd|otp|pin|auth)[a-z_]*\s*[:=]\s*\S", re.IGNORECASE
)


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).casefold()
    t = "".join(c for c in t if not unicodedata.category(c).startswith("C"))
    return re.sub(r"[^\w\s]|_", " ", t)


def text_issue(text: Any) -> str | None:
    """Why this text may not be stored or acted on, or None when it is clean."""
    try:
        if not isinstance(text, str):
            return "not text"
        if len(text) > MAX_TEXT:
            return "text is too long to screen"
        if audit.looks_secret(text) or audit.has_card_like(text, 12):
            return "looks like a secret or a card number"
        if _DIGITS.search(text) or _CNIC.search(text):
            return "contains a long number (card, ID, account or code shape)"
        if _IBAN.search(text) or _PREFIXED.search(text) or _HEX.search(text):
            return "looks like an account number, key or token"
        if _LONG.search(text) and any(c.isdigit() for c in text) or _URL_SECRET.search(text):
            return "contains a long key-like string or a secret URL parameter"
        if _ASSIGN.search(text):
            return "looks like a credential assignment"
        folded = f" {' '.join(_fold(text).split())} "
        collapsed = audit.collapse_spaced(text)
        if collapsed != text and audit.looks_secret(collapsed):
            return "looks like a secret"
        for w in _KEYWORDS:
            if f" {w} " in folded:
                return f"mentions a credential word ({w})"
        for p in _PHRASES:
            if f" {p} " in folded:
                return f"mentions a credential phrase ({p})"
        return None
    except Exception:  # noqa: BLE001 - fail closed
        return "unreadable text"


def value_issue(obj: Any) -> str | None:
    """Walk keys and values of nested params or results. Anything non-plain is refused."""
    count = 0

    def walk(o: Any, depth: int) -> str | None:
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            return "too large or too deep to screen"
        if o is None or isinstance(o, (bool, int, float)):
            return None
        if isinstance(o, str):
            return text_issue(o)
        if isinstance(o, Mapping):
            for k, v in o.items():
                if not isinstance(k, str):
                    return "key is not text"
                if audit.secret_key_name(k, v):
                    return "a field name looks like a secret"
                bad = text_issue(k) or walk(v, depth + 1)
                if bad:
                    return bad
            return None
        if isinstance(o, (list, tuple)):
            for v in o:
                bad = walk(v, depth + 1)
                if bad:
                    return bad
            return None
        return "unsupported value type"

    try:
        return walk(obj, 0)
    except Exception:  # noqa: BLE001
        return "unreadable value"
