"""
Backend-side counterpart to frontend/src/lib/languages.js.

Listing a language here means the UI is allowed to *offer* it as a
choice, not that Bhashini can currently translate into it — pipeline
support depends on the configured Bhashini models/pipeline and can
change independently of this static list. The backend stays
authoritative for actual capability: GET /api/v1/languages reports both
this catalog and whether a real translation backend is configured at
all (see ai.translation.translator_configured), never a promise that
every pair here works.

Kept in one place, in this shape, specifically so it never has to be
hand-copied in sync with the frontend file — a future iteration could
serve the frontend list from this endpoint directly instead of
duplicating it, but until then the two are kept in lockstep by hand and
this docstring is the reminder to do so.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageEntry:
    code: str  # None-equivalent is "en" here; the API always has a real code
    name: str
    native_name: str


LANGUAGE_CATALOG: tuple[LanguageEntry, ...] = (
    LanguageEntry("en", "English", "English"),
    LanguageEntry("hi", "Hindi", "हिन्दी"),
    LanguageEntry("bn", "Bengali", "বাংলা"),
    LanguageEntry("te", "Telugu", "తెలుగు"),
    LanguageEntry("mr", "Marathi", "मराठी"),
    LanguageEntry("ta", "Tamil", "தமிழ்"),
    LanguageEntry("ur", "Urdu", "اردو"),
    LanguageEntry("gu", "Gujarati", "ગુજરાતી"),
    LanguageEntry("kn", "Kannada", "ಕನ್ನಡ"),
    LanguageEntry("or", "Odia", "ଓଡ଼ିଆ"),
    LanguageEntry("ml", "Malayalam", "മലയാളം"),
    LanguageEntry("pa", "Punjabi", "ਪੰਜਾਬੀ"),
    LanguageEntry("as", "Assamese", "অসমীয়া"),
    LanguageEntry("mai", "Maithili", "मैथिली"),
    LanguageEntry("sat", "Santali", "ᱥᱟᱱᱛᱟᱲᱤ"),
    LanguageEntry("ks", "Kashmiri", "كٲشُر"),
    LanguageEntry("ne", "Nepali", "नेपाली"),
    LanguageEntry("sd", "Sindhi", "سنڌي"),
    LanguageEntry("kok", "Konkani", "कोंकणी"),
    LanguageEntry("doi", "Dogri", "डोगरी"),
    LanguageEntry("mni", "Manipuri", "মৈতৈলোন্"),
    LanguageEntry("bo", "Bodo", "བོད་སྐད"),
    LanguageEntry("sa", "Sanskrit", "संस्कृतम्"),
)
