// The interface's language, as in Remiqora (its frontend/src/i18n): Russian or English, the system's until the user
// picks one in the header, kept in the browser. The strings live in locales/<area>.ts, each `{ ru: {...}, en: {...} }`,
// and are found as t('<area>.<key>') - one file per area, so areas can be translated side by side. The server is told
// the language too (api.ts's X-Lang, and /api/lang for jobs running in the background); the texts' language (ideas,
// scenes, the translator's) is another setting, on «Модели и настройки».
import { createI18n } from 'vue-i18n'

export type LocaleCode = 'ru' | 'en'
const STORAGE_KEY = 'remiqora_video_locale'

type Area = { ru: Record<string, unknown>; en: Record<string, unknown> }
const files = import.meta.glob<{ default: Area }>('../locales/*.ts', { eager: true })
const messages: Record<LocaleCode, Record<string, unknown>> = { ru: {}, en: {} }
for (const [path, mod] of Object.entries(files)) {
  const area = path.replace(/^.*\/|\.ts$/g, '')
  messages.ru[area] = mod.default.ru
  messages.en[area] = mod.default.en
}

// any Russian among the preferred languages counts: people in Ukraine, Belarus or Kazakhstan often list it second
function systemLocale(): LocaleCode {
  const preferred = navigator.languages?.length ? navigator.languages : [navigator.language ?? '']
  return preferred.some((lang) => lang.toLowerCase().startsWith('ru')) ? 'ru' : 'en'
}

function initialLocale(): LocaleCode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'ru' || saved === 'en') return saved
  } catch { /* private window: the system's */ }
  return systemLocale()
}

// the server's messages of jobs in the background, and the texts' language until one is picked, follow the interface
function tellServer(locale: LocaleCode) {
  fetch('/api/lang', { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Lang': locale }, body: JSON.stringify({ ui: locale }) }).catch(() => {})
}

const start = initialLocale()
document.documentElement.lang = start
// told at once, not only on a switch: a first start on an English system would leave the server on its default
// (Russian), and the writer would write the storyboard in Russian
tellServer(start)

// Russian plurals: t('x', n) with 'сцена | сцены | сцен' (1, 2-4, 5+ - and 11-14, 21, 22…); English 'scene | scenes'
function ruPlural(n: number, choices: number) {
  if (choices < 3) return n === 1 ? 0 : 1
  const a = Math.abs(n) % 100, b = a % 10
  return a > 10 && a < 20 ? 2 : b === 1 ? 0 : b >= 2 && b <= 4 ? 1 : 2
}
export const i18n = createI18n({ legacy: false, locale: start, fallbackLocale: 'ru', messages: messages as any,
  pluralRules: { ru: ruPlural }, missingWarn: false, fallbackWarn: false })
// for code outside components (lib/*.ts): the same t, reactive where it is read inside a computed or a template
export const t = i18n.global.t

export function currentLocale(): LocaleCode {
  return (i18n.global.locale as any).value
}

export function setLocale(locale: LocaleCode) {
  ;(i18n.global.locale as any).value = locale
  document.documentElement.lang = locale
  try { localStorage.setItem(STORAGE_KEY, locale) } catch { /* won't persist */ }
  tellServer(locale)
}
