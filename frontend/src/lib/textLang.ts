// The texts' language (app/i18n.py): ideas and scene texts are in it, the translator goes from it to the English
// prompt and back to it («Перевести на …»). Set on «Модели и настройки» → «Сценарист»; read once at start.
import { reactive } from 'vue'
import { api } from './api'
import { currentLocale } from '../i18n'
import type { Scene } from './types'

type Lang = { code: string; name: string; en?: string }
// `name` goes into sentences («Перевести на …», «Translate to …»): its own name under the Russian interface, the English
// one under the English interface (an English page read «Translate to Русский»)
export const TL = reactive({
  code: 'ru', langs: [] as Lang[],
  get name(): string {
    const l = this.langs.find((x) => x.code === this.code)
    return (currentLocale() === 'en' ? l?.en : l?.name) || l?.name || (this.code === 'ru' && currentLocale() === 'en' ? 'Russian' : this.code === 'ru' ? 'Русский' : this.code)
  },
})

export async function loadTextLang() {
  try {
    const r = await api<{ text: string; langs: Lang[] }>('/api/lang')
    TL.langs = r.langs
    setTextLang(r.text)
  } catch { /* Russian, as before */ }
}

export function setTextLang(code: string) {
  TL.code = code
}

// the same reading as the server's (app/llm/translate.py in_lang): the alphabet, and for Latin ones English or not
const CYR = /[а-яёіїєґўқғүұһә]/gi, LAT = /[a-zà-ÿąćęłńóśźżčďěňřšťůž]/gi, CJK = /[぀-ヿ㐀-鿿가-힯]/g
const EN = /\b(the|and|of|is|are|with|her|his|she|he|in|on|a|to|at|from|into|their)\b/gi
const count = (s: string, re: RegExp) => (s.match(re) || []).length
export function inLang(text: string, code: string): boolean {
  const s = text || ''
  if (!s.trim()) return true
  const cyr = count(s, CYR), lat = count(s, LAT), cjk = count(s, CJK)
  if (['ru', 'uk', 'be', 'kk'].includes(code)) return cyr > lat
  if (['zh', 'ja', 'ko'].includes(code)) return cjk > lat
  if (cyr > lat || cjk > lat) return false
  const en = count(s, EN) >= Math.max(1, Math.floor(s.split(/\s+/).length / 8))
  return code === 'en' ? en : !en
}

// «Перевести на …» has work here: its «what happens» in another language, or its own prompt without a copy in this one
export function needsTranslation(s: Scene, code = TL.code): boolean {
  const tagged = (s as any).ru_lang as string | undefined
  const text = tagged ? tagged === code : inLang(s.ru || '', code)
  const raw = typeof s.raw === 'string' && s.raw.trim() && code !== 'en' && !inLang(s.raw, code) && !(s.raw_ru && (tagged || 'ru') === code)
  return !text || !!raw
}
