// The parts of an H3 prompt, in their order and in the colours of the help's anatomy, and the lab's markup of a prompt:
// each paragraph tagged in Russian with what it is, labels, timestamps, spoken lines and <Picture N> coloured, and
// Russian words outside quotes underlined (H3 reads them worse; inside quotes they are what a character says).
// The lab has two prompts: the English one that goes to H3, and a Russian one that the writer translates into it
// (/api/llm/translate); each part has its label and stub in both languages.
import { t } from '../i18n'
import { TL } from './textLang'

// 'ru': the lab's own-language sheet (the texts' language, app/i18n.py). It is marked up with Russian labels only
// when that language is Russian; in any other the labels are the English ones (Scene:, Camera:…) around the user's
// words, and the translator reads them so (app/llm/translate.py).
export type Lang = 'en' | 'ru'
export const labelSide = (lang: Lang): Lang => (lang === 'ru' && TL.code !== 'ru' ? 'en' : lang)
interface Side { stub: string; re?: RegExp }
export interface Part { key: string; name: string; tag: string; en: Side; ru: Side }

// A part is found by its paragraph (its `re` in that language: the Russian ones stay Russian, they parse the Russian
// prompt); its name and tag follow the interface's language; a missing one is put in its place with "..." selected, ready to be typed over.
export const PARTS: Part[] = [
  { key: 'style', get name() { return t('lab.part.style') }, get tag() { return t('lab.tag.style') },
    en: { stub: 'Realistic live-action cinematic look, soft natural light, shallow depth of field, film grain.' },
    ru: { stub: 'Стиль: реалистичное кино, мягкий естественный свет, малая глубина резкости, плёночное зерно.', re: /^Стиль:/i } },
  { key: 'place', get name() { return t('lab.part.place') }, get tag() { return t('lab.tag.place') },
    en: { stub: 'Scene: ...', re: /^(Scene( continues)?:|Continue seamlessly from)/i },
    ru: { stub: 'Место: ...', re: /^((Место|Сцена):|(Начать|Продолжить) с кадра)/i } },
  { key: 'camera', get name() { return t('lab.part.camera') }, get tag() { return t('lab.tag.camera') },
    en: { stub: 'Camera: medium shot, slow push-in.', re: /^Camera:/i },
    ru: { stub: 'Камера: средний план, медленный наезд.', re: /^Камера:/i } },
  { key: 'time', get name() { return t('lab.part.time') }, get tag() { return t('lab.tag.time') },
    en: { stub: 'Timeline:\n[0s-2s] ...\n[2s-5s] ...', re: /^(Timeline:|\[\s*\d)/i },
    ru: { stub: 'Таймлайн:\n[0s-2s] ...\n[2s-5s] ...', re: /^((Таймлайн|Действия):|\[\s*\d)/i } },
  { key: 'audio', get name() { return t('lab.part.audio') }, get tag() { return t('lab.tag.audio') },
    en: { stub: 'Audio: ...', re: /^Audio:/i },
    ru: { stub: 'Звук: ...', re: /^(Звук|Музыка):/i } },
  { key: 'tail', get name() { return t('lab.part.tail') }, get tag() { return t('lab.tag.tail') },
    en: { stub: 'No text, subtitles, logos or watermarks.', re: /(no text|watermark|exactly the same)/i },
    ru: { stub: 'Без текста, субтитров, логотипов и водяных знаков.', re: /(без текста|водяных знаков|не меняются)/i } },
]
export const PART_COLOR: Record<string, string> = { style: '--p-style', place: '--p-place', camera: '--p-camera', time: '--p-time', audio: '--p-audio', tail: '--p-tail' }
const PLACE_STUB: Record<Lang, string> = { en: 'Scene: an adult woman, about 30, ...', ru: 'Место: взрослая женщина, около 30 лет, ...' }
export const template = (own: Lang) => { const lang = labelSide(own); return PARTS.map((p) => (p.key === 'place' ? PLACE_STUB[lang] : p[lang].stub)).join('\n\n') }

// which part each paragraph is: a labelled one by its label; an unlabelled paragraph at the top (or right after the
// "Continue seamlessly from <Picture 1>." line) is the style
const FRAME_LINE: Record<Lang, RegExp> = { en: /^Continue seamlessly from/i, ru: /^(Начать|Продолжить) с кадра/i }
// a line that starts a part even with no blank line before it (the writer's translations often have none, and the style
// glued to the frame line was lost): a part's label, the tail; and any line after the frame line
const LABEL: Record<Lang, RegExp> = {
  en: /^(Scene( continues)?:|Camera:|Timeline:|Audio:|Continue seamlessly from)/i,
  ru: /^((Стиль|Место|Сцена|Камера|Таймлайн|Действия|Звук|Музыка):|(Начать|Продолжить) с кадра)/i,
}
const TAIL_LINE: Record<Lang, RegExp> = { en: /^(No text|Keep every face)/i, ru: /^(Без текста|Лицо, волосы)/i }
function blocks(text: string, own: Lang) {
  const lang = labelSide(own)
  const out: [number, number][] = []
  const re = /[^\n]+(\n[^\n]+)*/g   // a paragraph: lines without a blank line between them
  let m
  while ((m = re.exec(text))) {
    let start = m.index, first = m[0].split('\n')[0].trim(), at = m.index
    for (const line of m[0].split('\n')) {
      const s = line.trim()
      if (at > start && (LABEL[lang].test(s) || FRAME_LINE[lang].test(first) || (TAIL_LINE[lang].test(s) && !TAIL_LINE[lang].test(first)))) {
        out.push([start, at - 1])
        start = at
        first = s
      }
      at += line.length + 1
    }
    out.push([start, m.index + m[0].length])
  }
  return out
}
export function paragraphs(text: string, own: Lang = 'en') {
  const lang = labelSide(own)
  const out: { start: number; end: number; key: string | null }[] = []
  let top = true
  for (const [start, end] of blocks(text, lang)) {
    const body = text.slice(start, end).trim()
    if (!body) continue
    const part = PARTS.find((p) => p[lang].re && p[lang].re!.test(body)) || (top && body.split(/\s+/).length >= 4 ? PARTS[0] : null)
    top = top && FRAME_LINE[lang].test(body)
    out.push({ start, end, key: part ? part.key : null })
  }
  return out
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!))
// in a paragraph, in this order: a label at a line's start, the frame instruction, <Picture N>, a timestamp, a line in
// quotes (an unclosed quote runs to the line's end, so a line being typed is not flagged), "...", a Russian run (only
// in the English prompt: in the Russian one it is the text itself)
const tokens = (lang: Lang, runs = lang === 'en') => new RegExp([
  lang === 'en' ? /(^(?:Scene(?: continues)?|Camera|Timeline|Audio):)/.source : /(^(?:Стиль|Место|Сцена|Камера|Таймлайн|Действия|Звук|Музыка):)/.source,
  lang === 'en' ? /(Continue seamlessly from)/.source : /((?:Начать|Продолжить) с кадра)/.source,
  /(<Picture \d+>)/.source,
  /(\[\s*\d+(?:\.\d+)?\s*s?\s*-\s*\d+(?:\.\d+)?\s*s?\s*\])/.source,
  /("[^"\n]*(?:"|$)|«[^»\n]*(?:»|$)|“[^”\n]*(?:”|$))/.source,
  /(\.\.\.|…)/.source,
  runs ? /([А-Яа-яЁё](?:[А-Яа-яЁё \t,.!?-]*[А-Яа-яЁё])?)/.source : /(?!)()/.source,
].join('|'), 'gm')
const TOKEN: Record<Lang, RegExp> = { en: tokens('en'), ru: tokens('ru') }
// the own-language sheet in another language than Russian: the English labels, no Russian runs underlined (Cyrillic may be the text itself)
const TOKEN_OWN = tokens('en', false)
const CLASS = ['lb', 'lb', 'pic', 'ts', 'say', 'fill', 'ru']

// The prompt as HTML for the layer under the textarea: the same characters in the same places, only coloured.
// `whole`: the prompt is one text without H3's parts (LTX's, WAN's paragraph) - one tag over it, this one
export function markup(text: string, own: Lang = 'en', whole?: string) {
  const lang = labelSide(own), tok = own === 'ru' && lang === 'en' ? TOKEN_OWN : TOKEN[lang]
  const paras = whole == null ? paragraphs(text, own) : text.trim() ? [{ start: text.search(/\S/), end: text.trimEnd().length, key: null }] : []
  let html = '', at = 0
  for (const [i, p] of paras.entries()) {
    html += esc(text.slice(at, p.start))
    const body = text.slice(p.start, p.end), color = p.key ? `var(${PART_COLOR[p.key]})` : 'var(--dim)'
    const tag = whole != null ? whole : FRAME_LINE[lang].test(body.trim()) ? t('lab.tag.frame')
      : p.key ? PARTS.find((x) => x.key === p.key)!.tag : i ? t('lab.tag.noLabel') : t('lab.tag.text')
    html += `<span class="pp" style="--c:${color}"><i class="mk" data-tag="${esc(tag)}"></i>`
    let last = 0
    for (const m of body.matchAll(tok)) {
      const g = m.slice(1).findIndex((x) => x !== undefined)
      html += esc(body.slice(last, m.index)) + `<span class="${CLASS[g]}">${esc(m[0])}</span>`
      last = m.index! + m[0].length
    }
    html += esc(body.slice(last)) + '</span>'
    at = p.end
  }
  html += esc(text.slice(at))
  return text.endsWith('\n') ? html + ' ' : html   // a pre drops a last empty line that the textarea shows
}

// Russian words outside quotes in the English prompt: the first run and where it is, for the checks under the prompt
export function russianOutside(text: string) {
  for (const m of text.matchAll(TOKEN.en)) if (m[7]) return { word: m[7], at: m.index! }
  return null
}
