// The lab's scene form: the prompt as fields (style, place, camera, what happens by seconds, sound, the tail), in
// Russian and in English, composed into the prompt H3 gets - the storyboard's formula (app/planner/prompts.py) - and
// parsed back out of a text: a preset, a take's prompt, the text mode. The timeline is counted here: the actions share
// the scene's length, so it never disagrees with it.
import { CAMERAS } from './consts'
import { type Lang, labelSide, paragraphs } from './promptParts'

export interface Beat { text: string; secs: number | null }   // null: an even share of what the fixed ones leave
export interface Fields { style: string; place: string; shot: string; move: string; cameraText: string; beats: Beat[]; audio: string; keep: boolean; noText: boolean }

// the shot sizes and the camera moves: [Russian, English]; the moves are the studio's (CAMERAS), with the handheld shake
export const SHOTS: Record<string, [string, string]> = {
  xclose: ['Деталь крупно', 'extreme close-up'], close: ['Крупный план', 'close-up'], mclose: ['Средний крупный', 'medium close-up'],
  medium: ['Средний план', 'medium shot'], full: ['Во весь рост', 'full shot'], wide: ['Общий план', 'wide shot'],
}
const MOVE_EN: Record<string, string> = {
  static: 'static shot', push_in: 'slow push-in', pull_back: 'slow pull-back', track_side: 'smooth tracking shot alongside',
  track_front: 'leading shot, the camera stays ahead as they walk toward it', follow: 'the camera follows from behind',
  orbit: 'slow arc shot around', pan: 'slow pan', rise: 'the camera slowly rises', shake: 'the camera shakes slightly',
}
export const MOVES: Record<string, [string, string]> = Object.fromEntries(Object.keys(MOVE_EN).map((id) => [id, [CAMERAS[id] || 'Слегка трясётся, как с рук', MOVE_EN[id]]]))

export const empty = (): Fields => ({ style: '', place: '', shot: '', move: '', cameraText: '', beats: [{ text: '', secs: null }, { text: '', secs: null }], audio: '', keep: true, noText: true })
export const MAX_BEATS = 6
const r2 = (x: number) => Math.round(x * 2) / 2
export const fmtS = (x: number) => (Number.isInteger(x) ? String(x) : x.toFixed(1))

// [from, to] of every beat: fixed seconds as given, the others share the rest evenly, the last one ends the scene;
// three even beats of 5 s go 2-2-1, as in the tested prompts and the storyboard
export function cuts(beats: Beat[], seconds: number): [number, number][] {
  const n = beats.length
  if (!n) return []
  const fixed = beats.map((b) => (b.secs && b.secs > 0 ? b.secs : null))
  const used = fixed.reduce<number>((s, x) => s + (x || 0), 0), auto = fixed.filter((x) => x == null).length
  const even = auto ? Math.max(0.5, r2((seconds - used) / auto)) : 0
  const special = n === 3 && seconds === 5 && auto === 3 ? [2, 2, 1] : null
  const out: [number, number][] = []
  let t = 0
  beats.forEach((_, i) => {
    const d = special ? special[i] : fixed[i] ?? even, a = t
    t = i === n - 1 ? seconds : Math.min(seconds, r2(a + d))
    out.push([a, t])
  })
  return out
}

const TAIL = {
  en: { keep: 'Keep every face, hair and outfit exactly the same.', noText: 'No text, subtitles, logos or watermarks.' },
  ru: { keep: 'Лицо, волосы и одежда не меняются.', noText: 'Без текста, субтитров, логотипов и водяных знаков.' },
}
const FRAME_LINE = { en: 'Continue seamlessly from <Picture 1>.', ru: 'Продолжить с кадра <Picture 1>.' }
const FRAME_RE = { en: /^Continue seamlessly from/i, ru: /^(Начать|Продолжить) с кадра/i }

// the fields -> the prompt, in the lab's format (the parts the markup and the checks know)
export function compose(f: Fields, own: Lang, seconds: number, frame: boolean): string {
  const lang = labelSide(own), en = lang === 'en', k = en ? 1 : 0   // labels: Russian only for a Russian sheet
  const cam = [f.shot && SHOTS[f.shot]?.[k].toLowerCase(), f.move && MOVES[f.move]?.[k].toLowerCase(), f.cameraText.trim()].filter(Boolean)
  const beats = f.beats.filter((b) => b.text.trim()), c = cuts(beats, seconds)
  const tail = [f.keep && TAIL[lang].keep, f.noText && TAIL[lang].noText].filter(Boolean).join(' ')
  return [
    frame ? FRAME_LINE[lang] : '',
    f.style.trim() ? (en ? '' : 'Стиль: ') + f.style.trim() : '',
    f.place.trim() ? (en ? 'Scene: ' : 'Место: ') + f.place.trim() : '',
    cam.length ? (en ? 'Camera: ' : 'Камера: ') + cam.join(', ').replace(/[.。]?$/, '.') : '',
    beats.length ? (en ? 'Timeline:\n' : 'Таймлайн:\n') + beats.map((b, i) => `[${fmtS(c[i][0])}s-${fmtS(c[i][1])}s] ${b.text.trim()}`).join('\n') : '',
    f.audio.trim() ? (en ? 'Audio: ' : 'Звук: ') + f.audio.trim() : '',
    tail,
  ].filter(Boolean).join('\n\n')
}

// the prompt form of the lab's model: H3's labelled parts, or LTX's / WAN's one paragraph (app/llm/translate.py form)
export type Form = 'h3' | 'ltx' | 'wan'
export const formOf = (model: string): Form => (model === 'h3' ? 'h3' : model.startsWith('wan5b') ? 'wan' : 'ltx')

// a spoken line (videomodels._SAYS), in any quotes the translator leaves («», “”, ""): WAN has no voice
const SAYS = /\b(says|said|whispers|shouts|sings|asks)\b[^:]*:\s*["«“]/i
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const sentence = (s: string) => { const x = cap(s.trim().replace(/\s+/g, ' ')); return x && !/[.!?"”]$/.test(x) ? x + '.' : x }

// the English fields -> one paragraph in the model's order, as the storyboard's LTX / WAN prompts (app/planner/
// model_prompts.py): LTX - the look, the place, the action, the camera, the sound; WAN - the place, the motion, the
// camera, the look, no sound; from a start frame WAN gets only the motion and the camera (the frame shows the rest)
export function composeFor(f: Fields, form: Form, seconds: number, frame: boolean): string {
  if (form === 'h3') return compose(f, 'en', seconds, frame)
  const cam = [f.shot && SHOTS[f.shot]?.[1], f.move && MOVES[f.move]?.[1], f.cameraText.trim()].filter(Boolean).join(', ')
  const camera = cam ? sentence(cam) : ''
  const beats = f.beats.map((b) => b.text).filter((b) => b.trim() && (form === 'ltx' || !SAYS.test(b))).map(sentence)
  const parts = form === 'ltx' ? [f.style, f.place, ...beats, camera, f.audio]
    : frame ? [...beats, camera] : [f.place, ...beats, camera, f.style]
  return parts.map(sentence).filter(Boolean).join(' ')
}

// a text -> the fields: by the parts the markup finds; a paragraph without a part goes to the place (and is named in
// `lost`, so the lab can say so); the camera line is matched against the lists, what is left is the addition
export function parse(text: string, own: Lang): { fields: Fields; lost: string[] } {
  const lang = labelSide(own), f = empty(), en = lang === 'en', lost: string[] = []
  f.beats = []
  f.keep = f.noText = false
  const strip = (s: string, re: RegExp) => s.replace(re, '').trim()
  for (const p of paragraphs(text, own)) {
    const body = text.slice(p.start, p.end).trim()
    if (FRAME_RE[lang].test(body)) continue
    switch (p.key) {
      case 'style': f.style = strip(body, /^(Стиль|Style):\s*/i); break
      case 'place': f.place = strip(body, en ? /^Scene( continues)?:\s*/i : /^(Место|Сцена):\s*/i); break
      case 'camera': parseCamera(f, strip(body, en ? /^Camera:\s*/i : /^Камера:\s*/i).replace(/\.$/, '')); break
      case 'time':
        for (const m of body.matchAll(/\[\s*(\d+(?:\.\d+)?)\s*s?\s*-\s*(\d+(?:\.\d+)?)\s*s?\s*\]\s*([^\n]*)/g)) f.beats.push({ text: m[3].trim(), secs: r2(+m[2] - +m[1]) })
        break
      case 'audio': f.audio = strip(body, en ? /^Audio:\s*/i : /^(Звук|Музыка):\s*/i); break
      case 'tail': f.keep = /exactly the same|не меняются/i.test(body); f.noText = /no text|без текста/i.test(body); break
      default: lost.push(body)
    }
  }
  // even beats, or the storyboard's 2-2-1, share the length by themselves and follow it when it changes
  const d = f.beats.map((b) => b.secs || 0)
  if (d.length && (d.every((x) => Math.abs(x - d[0]) < 0.75) || (d.length === 3 && d.join() === '2,2,1'))) f.beats.forEach((b) => { b.secs = null })
  if (!f.beats.length) f.beats = [{ text: '', secs: null }]
  if (lost.length) f.place = [f.place, ...lost].filter(Boolean).join('\n')
  return { fields: f, lost }
}

// the camera line's words -> the lists: the list phrases in both languages plus how the presets and people say them;
// the longest phrase wins ("medium close-up" before "close-up"), what matches nothing stays as the addition
const SAID: [string, 'shot' | 'move', string][] = [
  ['средний крупный план', 'shot', 'mclose'], ['общий план во весь рост', 'shot', 'full'], ['во весь рост', 'shot', 'full'], ['полный план', 'shot', 'full'],
  ['деталь', 'shot', 'xclose'], ['камера стоит', 'move', 'static'], ['статичная камера', 'move', 'static'], ['без движения', 'move', 'static'],
  ['наезд', 'move', 'push_in'], ['отъезжает', 'move', 'pull_back'], ['отъезд', 'move', 'pull_back'], ['едет рядом', 'move', 'track_side'],
  ['пятится', 'move', 'track_front'], ['следом', 'move', 'follow'], ['облет', 'move', 'orbit'], ['по дуге', 'move', 'orbit'], ['панорам', 'move', 'pan'],
  ['поднимается', 'move', 'rise'], ['трясётся', 'move', 'shake'], ['с рук', 'move', 'shake'], ['handheld', 'move', 'shake'], ['arc shot', 'move', 'orbit'],
  ['orbit', 'move', 'orbit'], ['push in', 'move', 'push_in'], ['pull out', 'move', 'pull_back'], ['pull back', 'move', 'pull_back'],
  ['tracking shot', 'move', 'track_side'], ['follows', 'move', 'follow'], ['rises', 'move', 'rise'], ['static', 'move', 'static'],
]
const KNOWN: [string, 'shot' | 'move', string][] = [
  ...Object.entries(SHOTS).flatMap(([id, v]) => v.map((x): [string, 'shot' | 'move', string] => [x.toLowerCase(), 'shot', id])),
  ...Object.entries(MOVES).flatMap(([id, v]) => v.map((x): [string, 'shot' | 'move', string] => [x.toLowerCase(), 'move', id])),
  ...SAID,
].sort((a, b) => b[0].length - a[0].length)
function parseCamera(f: Fields, line: string) {
  const rest: string[] = []
  for (const part of line.split(',').map((s) => s.trim()).filter(Boolean)) {
    const low = part.toLowerCase().replace('ё', 'е')
    const hit = KNOWN.find(([phrase, kind]) => low.includes(phrase.replace('ё', 'е')) && !f[kind])
    if (hit) f[hit[1]] = hit[2]
    else rest.push(part)
  }
  f.cameraText = rest.join(', ')
}

// the fields of the Russian layer for the writer: what it translates (the lists are copied over as they are)
export const forTranslation = (f: Fields) => ({ style: f.style, place: f.place, camera: f.cameraText, beats: f.beats.map((b) => b.text), audio: f.audio })
