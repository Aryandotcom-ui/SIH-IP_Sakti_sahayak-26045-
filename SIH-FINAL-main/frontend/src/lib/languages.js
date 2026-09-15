/**
 * Single source of truth for the languages the UI can offer as an answer
 * language. Previously this list (in lib/api.js) only had English, Hindi
 * and Kannada, backing three header buttons. It now covers English plus
 * all 22 languages scheduled in the Eighth Schedule to the Constitution,
 * which is what a "Language ▾" dropdown needs to be worth having.
 *
 * Listing a language here means the UI can *offer* it — it does not mean
 * Bhashini can actually translate into it right now. Pair capability
 * depends on the configured pipeline/model and can change independently
 * of this file, so the backend remains authoritative: see
 * GET /api/v1/languages (backend/app/api/routes.py), which returns the
 * catalog it actually knows how to serve plus whether a real translation
 * backend is configured at all. This file is the fallback shown before
 * that call resolves, and the shape both agree on.
 */

export const LANGUAGE_CATALOG = [
  { code: null, bhashiniCode: 'en', label: 'English', englishName: 'English', nativeName: 'English' },
  { code: 'hi', bhashiniCode: 'hi', label: 'हिन्दी', englishName: 'Hindi', nativeName: 'हिन्दी' },
  { code: 'bn', bhashiniCode: 'bn', label: 'বাংলা', englishName: 'Bengali', nativeName: 'বাংলা' },
  { code: 'te', bhashiniCode: 'te', label: 'తెలుగు', englishName: 'Telugu', nativeName: 'తెలుగు' },
  { code: 'mr', bhashiniCode: 'mr', label: 'मराठी', englishName: 'Marathi', nativeName: 'मराठी' },
  { code: 'ta', bhashiniCode: 'ta', label: 'தமிழ்', englishName: 'Tamil', nativeName: 'தமிழ்' },
  { code: 'ur', bhashiniCode: 'ur', label: 'اردو', englishName: 'Urdu', nativeName: 'اردو' },
  { code: 'gu', bhashiniCode: 'gu', label: 'ગુજરાતી', englishName: 'Gujarati', nativeName: 'ગુજરાતી' },
  { code: 'kn', bhashiniCode: 'kn', label: 'ಕನ್ನಡ', englishName: 'Kannada', nativeName: 'ಕನ್ನಡ' },
  { code: 'or', bhashiniCode: 'or', label: 'ଓଡ଼ିଆ', englishName: 'Odia', nativeName: 'ଓଡ଼ିଆ' },
  { code: 'ml', bhashiniCode: 'ml', label: 'മലയാളം', englishName: 'Malayalam', nativeName: 'മലയാളം' },
  { code: 'pa', bhashiniCode: 'pa', label: 'ਪੰਜਾਬੀ', englishName: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ' },
  { code: 'as', bhashiniCode: 'as', label: 'অসমীয়া', englishName: 'Assamese', nativeName: 'অসমীয়া' },
  { code: 'mai', bhashiniCode: 'mai', label: 'मैथिली', englishName: 'Maithili', nativeName: 'मैथिली' },
  { code: 'sat', bhashiniCode: 'sat', label: 'ᱥᱟᱱᱛᱟᱲᱤ', englishName: 'Santali', nativeName: 'ᱥᱟᱱᱛᱟᱲᱤ' },
  { code: 'ks', bhashiniCode: 'ks', label: 'كٲشُر', englishName: 'Kashmiri', nativeName: 'كٲشُر' },
  { code: 'ne', bhashiniCode: 'ne', label: 'नेपाली', englishName: 'Nepali', nativeName: 'नेपाली' },
  { code: 'sd', bhashiniCode: 'sd', label: 'سنڌي', englishName: 'Sindhi', nativeName: 'سنڌي' },
  { code: 'kok', bhashiniCode: 'kok', label: 'कोंकणी', englishName: 'Konkani', nativeName: 'कोंकणी' },
  { code: 'doi', bhashiniCode: 'doi', label: 'डोगरी', englishName: 'Dogri', nativeName: 'डोगरी' },
  { code: 'mni', bhashiniCode: 'mni', label: 'মৈতৈলোন্', englishName: 'Manipuri', nativeName: 'মৈতৈলোন্' },
  { code: 'bo', bhashiniCode: 'bo', label: 'བོད་སྐད', englishName: 'Bodo', nativeName: 'བོད་སྐད' },
  { code: 'sa', bhashiniCode: 'sa', label: 'संस्कृतम्', englishName: 'Sanskrit', nativeName: 'संस्कृतम्' },
];

/** Look up a catalog entry by the value the app uses internally (the
 * `code` field — `null` for English, matching LangCtx's existing
 * "null means detect/English" convention). */
export function findLanguage(code) {
  return LANGUAGE_CATALOG.find(l => l.code === code) ?? LANGUAGE_CATALOG[0];
}
