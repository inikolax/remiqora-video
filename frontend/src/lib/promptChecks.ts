// The lab's checks of a prompt before shooting, each with what to do about it: the storyboard's validator (app/planner/
// prompts.py: SEQUENCE, VAGUE_WALK, CAMERA_DIRECTION, TEXT_IN_FRAME) for a prompt written by hand, plus what only the lab
// has: "..." left from a preset, a timeline longer or shorter than the scene, the start frame without its line.
import { type Lang, labelSide, paragraphs, russianOutside } from './promptParts'
import { t } from '../i18n'
import { dec } from './format'
import { modelName } from './store'

export type Fix = { label: string; act: 'select' | 'len' | 'fit' | 'part' | 'frameline' | 'noframeline'; at?: [number, number]; secs?: number; key?: string }
export interface Issue { id: string; text: string; more: string; fixes: Fix[] }   // text: one short line; more: the why, in its tooltip

const TS = /\[\s*(\d+(?:\.\d+)?)\s*s?\s*-\s*(\d+(?:\.\d+)?)\s*s?\s*\]/g
const QUOTED = /"[^"\n]*(?:"|$)|«[^»\n]*(?:»|$)|“[^”\n]*(?:”|$)/gm
const SEQUENCE = { en: /\b(then|after that|afterwards|and finally)\b/i, ru: /(?<![а-яё])(потом|затем|после этого|а после)(?![а-яё])/i }
const VAGUE_WALK = /\b(walk(s|ing)?|stroll(s|ing)?|mov(e|es|ing)|step(s|ping)?|head(s|ing)?|go(es|ing)?)\s+(forward|forwards|ahead|on|onward|deeper|further|farther|along|down|up)\b/i
const CAMERA_DIRECTION = /\b(toward|towards|away from|to|past)\s+(the\s+)?(camera|lens|viewer)\b|\bfrom behind\b|\bfacing\b/i
const TEXT_IN_FRAME = /\b(captions?|lettering|typography|title card|(sign|banner|screen|poster|note) (that )?(reads?|says?|reading|saying)|writ(es|ing) (on|in)|the words)\b/i
export const FRAME_LINE: Record<Lang, { re: RegExp; line: string }> = {
  en: { re: /^\s*Continue seamlessly from\b[^\n]*\n*/i, line: 'Continue seamlessly from <Picture 1>.' },
  ru: { re: /^\s*(Начать|Продолжить) с кадра\b[^\n]*\n*/i, line: 'Продолжить с кадра <Picture 1>.' },
}

const fmt = (x: number) => dec(Math.round(x * 2) / 2)
// the timeline's end: the largest second in its [Xs-Ys] marks
export function timelineEnd(text: string) {
  let end = 0
  for (const m of text.matchAll(TS)) end = Math.max(end, +m[2])
  return end
}
// every mark scaled so the timeline ends at `to` seconds, in halves of a second
export function fitTimeline(text: string, to: number) {
  const end = timelineEnd(text), k = end ? to / end : 1, f = (x: number) => String(Math.round(x * k * 2) / 2)
  return text.replace(TS, (_, a: string, b: string) => `[${f(+a)}s-${f(+b)}s]`)
}

// H3's labels and timestamps in a prompt for LTX or WAN, which read one flowing paragraph
const H3_FORM = /^\s*(Scene( continues)?:|Camera:|Timeline:|Audio:|\[\s*\d+(?:\.\d+)?\s*s?\s*-)|<Picture \d+>/im
const SPOKEN = /\b(says|said|whispers|shouts|sings|asks)\b[^:\n]*:\s*["«“]/i

// `model`: a card id (the lab's model) - the English prompt for LTX / WAN is one paragraph, so H3's checks of its
// parts (the timeline, the frame line) are not for it
export function checkPrompt(text: string, lang: Lang, seconds: number, hasFrame: boolean, model = 'h3'): Issue[] {
  if (!text.trim()) return []
  const masked = text.replace(QUOTED, (q) => ' '.repeat(q.length))   // what a character says is not checked
  const lines = [...masked.matchAll(/[^\n]+/g)].map((m) => ({ at: m.index!, s: m[0] }))
  if (lang === 'en' && model !== 'h3') return [...checkOther(text, masked, model), ...checkWords(text, masked, lines)]
  return checkH3(text, masked, lines, lang, seconds, hasFrame)
}

function checkOther(text: string, masked: string, model: string): Issue[] {
  const out: Issue[] = [], name = modelName(model)
  const m = masked.match(H3_FORM)
  if (m) out.push({ id: 'form', text: t('checks.h3Form', { model: name }), more: t('checks.h3FormMore', { model: name }),
    fixes: [{ label: t('checks.show'), act: 'select', at: [m.index! + m[0].length - m[0].trimStart().length, m.index! + m[0].length] }] })
  const s = model.startsWith('wan5b') ? text.match(SPOKEN) : null
  if (s) out.push({ id: 'silent', text: t('checks.silent', { model: name }), more: t('checks.silentMore', { model: name }),
    fixes: [{ label: t('checks.show'), act: 'select', at: [s.index!, s.index! + s[0].length] }] })
  return out
}

// "..." left from a preset, Russian outside the quotes, a vague walk, text in the frame: for every model's English
function checkWords(text: string, masked: string, lines: { at: number; s: string }[]): Issue[] {
  const out: Issue[] = []
  const dots = [...masked.matchAll(/\.\.\.|…/g)]
  if (dots.length) out.push({ id: 'fill', text: dots.length > 1 ? t('checks.fillN', { n: dots.length }) : t('checks.fill'),
    more: t('checks.fillMore'),
    fixes: [{ label: t('checks.goTo'), act: 'select', at: [dots[0].index!, dots[0].index! + dots[0][0].length] }] })
  const ru = russianOutside(text)
  if (ru) out.push({ id: 'russian', text: t('checks.russian', { word: ru.word }), more: t('checks.russianMore'),
    fixes: [{ label: t('checks.show'), act: 'select', at: [ru.at, ru.at + ru.word.length] }] })
  out.push(...checkEnglish(lines))
  return out
}

function checkEnglish(lines: { at: number; s: string }[]): Issue[] {
  const out: Issue[] = []
  for (const l of lines) {
    const m = l.s.match(VAGUE_WALK)
    if (m && !CAMERA_DIRECTION.test(l.s)) {
      out.push({ id: 'walk', text: t('checks.walk', { word: m[0] }), more: t('checks.walkMore'),
        fixes: [{ label: t('checks.show'), act: 'select', at: [l.at + m.index!, l.at + m.index! + m[0].length] }] })
      break
    }
  }
  for (const l of lines) {
    if (/^\s*(Audio:|No text)/i.test(l.s)) continue
    const m = l.s.match(TEXT_IN_FRAME)
    if (m) { out.push({ id: 'text', text: t('checks.text', { word: m[0] }), more: t('checks.textMore'), fixes: [{ label: t('checks.show'), act: 'select', at: [l.at + m.index!, l.at + m.index! + m[0].length] }] }); break }
  }
  return out
}

function checkH3(text: string, masked: string, lines: { at: number; s: string }[], lang: Lang, seconds: number, hasFrame: boolean): Issue[] {
  const out: Issue[] = []
  const dots = [...masked.matchAll(/\.\.\.|…/g)]
  if (dots.length) out.push({ id: 'fill', text: dots.length > 1 ? t('checks.fillN', { n: dots.length }) : t('checks.fill'),
    more: t('checks.fillMore'),
    fixes: [{ label: t('checks.goTo'), act: 'select', at: [dots[0].index!, dots[0].index! + dots[0][0].length] }] })

  const end = timelineEnd(text)
  if (end && Math.abs(end - seconds) >= 0.5) {
    const fixes: Fix[] = [{ label: t('checks.fit', { s: fmt(seconds) }), act: 'fit' }]
    if (end >= 1 && end <= 15) fixes.unshift({ label: t('checks.sceneLen', { s: fmt(end) }), act: 'len', secs: Math.round(end * 2) / 2 })
    out.push({ id: 'timeline', text: t('checks.timeline', { end: fmt(end), s: fmt(seconds) }), more: t('checks.timelineMore'), fixes })
  } else if (!end && text.trim().length > 60 && !paragraphs(text, lang).some((p) => p.key === 'time'))
    out.push({ id: 'no-timeline', text: t('checks.noTimeline'), more: t('checks.noTimelineMore'), fixes: [{ label: t('checks.add'), act: 'part', key: 'time' }] })

  if (lang === 'en') {
    const ru = russianOutside(text)
    if (ru) out.push({ id: 'russian', text: t('checks.russian', { word: ru.word }), more: t('checks.russianMore'),
      fixes: [{ label: t('checks.show'), act: 'select', at: [ru.at, ru.at + ru.word.length] }] })
  }

  for (const l of lines) {
    if (!/^\s*\[\s*\d/.test(l.s)) continue
    const m = l.s.match(SEQUENCE[lang])
    if (m) { out.push({ id: 'seq' + l.at, text: t('checks.seq', { word: m[1] }), more: t('checks.seqMore'), fixes: [{ label: t('checks.show'), act: 'select', at: [l.at, l.at + l.s.length] }] }); break }
  }
  if (lang === 'en') out.push(...checkEnglish(lines))

  const hasLine = FRAME_LINE[labelSide(lang)].re.test(text)
  if (hasFrame && !hasLine) out.push({ id: 'frame', text: t('checks.frame'), more: t('checks.frameMore', { line: FRAME_LINE[labelSide(lang)].line }), fixes: [{ label: t('checks.addLine'), act: 'frameline' }] })
  if (!hasFrame && hasLine) out.push({ id: 'noframe', text: t('checks.noFrame'), more: t('checks.noFrameMore'), fixes: [{ label: t('checks.removeLine'), act: 'noframeline' }] })
  return out
}
