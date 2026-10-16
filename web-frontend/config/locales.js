/**
 * Shared locales configuration for all Baserow modules.
 * This is the single source of truth for supported languages.
 *
 * To add a new language:
 * 1. Add the locale entry here
 * 2. Create the corresponding .json translation files in each module's locales/
 *    directory, in web-frontend/locales/, and add the code to LANGUAGES in
 *    backend/src/baserow/config/settings/base.py (the account language API
 *    validates against it). A missing file fails the Nuxt build.
 */
export const locales = [
  { code: 'en', name: 'English', file: 'en.json' },
  { code: 'pt-BR', name: 'Português (Brasil)', file: 'pt_BR.json' },
]
