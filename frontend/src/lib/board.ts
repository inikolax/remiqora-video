// The storyboard's small rules, shared by its parts.
import { reactive, ref } from 'vue'
import { P, flushSave, projectCall, reloadProject, rewrite, scheduleSave } from './project'
import { S, banner, onJobEnd } from './store'
import { post } from './api'
import { t } from '../i18n'
import { dec } from './format'
import type { Plan, Scene } from './types'

// the last frame of scene i's shot: its chosen take as the storyboard is now, else its shot in the latest render of this
// quality (older than the scene's text, maybe). Both go by the scene's id: they went by its place, and a scene deleted or
// moved gave every scene after it its neighbour's picture and the last one none (2026-10-29)
export function shotPng(i: number) {
  const proj = P.proj   // null for a moment while another project opens
  if (!proj) return null
  const est = P.est?.[proj.settings.quality], s = proj.plan?.scenes?.[i]
  if (est?.ids && s) {
    const k = est.ids.indexOf(s.id || `#${i}`)
    if (k >= 0 && est.scenes[k] === 'cached' && est.keys[k]) return `/api/projects/${proj.id}/files/scenes/${est.keys[k]}.png`
    const raw = rawTake(s)
    if (k >= 0 && raw) return `/api/projects/${proj.id}/files/scenes/${raw}.png`
  }
  // a render before the ids is matched by the place only while the estimate can't say
  const r = (proj.renders || {})[proj.settings.quality]
  const x = r && r.shots.find((y: any) => (y.id ? !!s && y.id === s.id : !est?.ids && y.index === i))
  return x ? `/api/projects/${proj.id}/files/${x.png}` : null
}
// a scene shot before but not as it is now (its text, start or length changed since): the card still shows that old
// shot, marked «переснять»
export function staleShot(i: number) {
  const proj = P.proj, est = proj && P.est?.[proj.settings.quality], s = proj?.plan?.scenes?.[i]
  if (!proj || !est?.ids || !s) return false
  const k = est.ids.indexOf(s.id || `#${i}`)
  return k >= 0 && est.scenes[k] !== 'cached' && !rawTake(s) && !!shotPng(i)
}
// «Починить лица» on: «Ещё дубль» shoots the take, the faces are fixed by «Снять ролик» - till then the card shows and
// plays the shot itself (render.preview's takes: `raw`, `raw_cached`)
export function rawTake(s: Scene) {
  const x = takesOf(s).find((y) => y.seed === s.seed)
  return x && !x.cached && x.raw && x.raw_cached ? x.raw : null
}
// the take a card or a player plays: the chosen one, its faces fixed or still the shot itself
export const playKey = (s: Scene) => takesOf(s).find((x) => x.seed === s.seed && x.cached && x.key)?.key || rawTake(s)
// who wrote a scene's text: the user (their own words, pinned), the writer, or nobody yet
export const authorOf = (s: Scene): 'me' | 'ai' | 'none' =>
  isRaw(s) || (s.source === 'user' && !!(s.ru || '').trim()) ? 'me' : (s.beats_en || []).some((b: string) => (b || '').trim()) ? 'ai' : 'none'
// Scenes out of the storyboard (their places in it). A clip is cut on its song, and a singing scene is shot to its own
// piece of it: shifted along the song, every scene after a removed one had to be shot again (2026-10-29). So in a clip
// every other scene stays on its bars: scenes removed at the start move the song's start on (the clip begins later in
// it), one in the middle gives its time to the scene before it, or after it, when that stays within its model's longest
// scene; only when neither can take it do the scenes after it shift, as before.
export function removeScenes(p: Plan, drop: Set<number>) {
  const scenes = p.scenes, proj = P.proj
  if (p.clip && proj) {
    const maxOf = (s: Scene) => (S.cfg?.video_models || []).find((m) => m.id === (s.model || proj.settings.video_model || 'h3'))?.max_seconds || 10
    const len = (s: Scene) => Number(s.seconds) || 5
    const grow = (s: Scene | undefined, by: number) => {
      if (!s || drop.has(s.index) || len(s) + by > maxOf(s) + 0.01) return false
      s.seconds = Math.round((len(s) + by) * 1e4) / 1e4
      return true
    }
    let head = 0
    while (head < scenes.length && drop.has(scenes[head].index)) head++
    const lead = scenes.slice(0, head).reduce((a, s) => a + len(s), 0)
    let offset: number | null = null
    if (lead && head < scenes.length) {
      p.clip.from = Math.round(((Number(p.clip.from) || 0) + lead) * 1e4) / 1e4
      if (proj.settings.track) offset = Math.round(((Number(proj.settings.track.offset) || 0) + lead) * 1e4) / 1e4
    }
    for (let i = head; i < scenes.length; i++) {
      const s = scenes[i]
      if (!drop.has(s.index)) continue
      let k = i - 1
      while (k >= 0 && drop.has(scenes[k].index)) k--
      if (!grow(scenes[k], len(s))) grow(scenes.slice(i + 1).find((x) => !drop.has(x.index)), len(s))
    }
    p.scenes = scenes.filter((s) => !drop.has(s.index))
    // the track's offset is the song's start in the video: saved after the storyboard (projectCall saves that first)
    if (offset !== null) { scheduleSave(); void projectCall('PUT', '/track', { offset }) }
    return
  }
  p.scenes = scenes.filter((s) => !drop.has(s.index))
}
// a scene's takes in the shooting quality (the estimate knows which are shot; scenes/<key>.mp4 and .png) and picking one:
// the chosen seed goes into the video and the continuations, the list of takes stays
export type Take = { seed: number; key: string | null; cached: boolean; raw?: string; raw_cached?: boolean }
export const takesOf = (s: Scene): Take[] => ((P.est && P.proj && P.est[P.proj.settings.quality || 'draft']?.takes?.[s.index]) || [{ seed: s.seed, key: null, cached: false }])
export function pickTake(s: Scene, seed: number) {
  if (seed === s.seed) return
  s.takes = takesOf(s).map((x) => x.seed)
  s.seed = seed
  scheduleSave()
}
// «Ещё дубль»: this scene shot once more now, alone, with a new seed; the earlier takes stay
// the scene in the «Просмотр» window (ScenePeek.vue), null - closed
export const peek = ref<number | null>(null)
// the scene panel's open tab (Начало / Сцена / Съёмка / Реплики / Дубли): it stays as the selection moves
export const inspTab = ref<'start' | 'scene' | 'shoot' | 'lines' | 'takes'>('scene')
export const taking = () => S.jobs.some((j) => j.kind === 'take' && (j.status === 'running' || j.status === 'queued') && j.params?.project === P.proj?.id)
export async function moreTake(s: Scene) {
  await flushSave()
  try {
    S.jobs = [...S.jobs, await post(`/api/projects/${P.proj!.id}/takes`, { scene: s.index })]
    await reloadProject()
    banner(t('board.takes.shooting', { n: s.index + 1 }), 'info')
  } catch (e) { banner((e as Error).message) }
}
// «Переписать» / «Другой вариант» / «Улучшить» of one scene: what the writer may change in it is kept first, so when
// the job is done «Вернуть» (in the panel and in the news) puts the scene back as it was - its prompt is then the old
// one again and its shot comes back from the cache. Kept for this page's session; an edit of the scene by hand drops it.
const REWRITE_KEYS = ['who', 'ru', 'ru_dirty', 'beats_en', 'framing', 'camera', 'sound_en', 'place_en', 'to_en', 'shot', 'shot_user', 'source', 'locked', 'problems', 'problems_ru', 'status']
type Before = { job?: string; done: boolean; n: number; fields: Record<string, unknown> }
export const rewritten = reactive<Record<string, Before>>({})   // `${project}:${scene id}`
const beforeKey = (pid: string, s: Scene) => `${pid}:${s.id || `#${s.index}`}`
export const canUndoRewrite = (s: Scene) => !!P.proj && !!rewritten[beforeKey(P.proj.id, s)]?.done
export const forgetRewrite = (s: Scene) => { if (P.proj) delete rewritten[beforeKey(P.proj.id, s)] }
export async function rewriteScene(s: Scene, how: 'variant' | 'improve') {
  const pid = P.proj!.id, k = beforeKey(pid, s)
  const fields = Object.fromEntries(REWRITE_KEYS.map((x) => [x, s[x] === undefined ? undefined : JSON.parse(JSON.stringify(s[x]))]))
  rewritten[k] = { done: false, n: s.index + 1, fields }
  if (how === 'variant') { Object.assign(s, { locked: false, source: 'llm' }); scheduleSave() }   // the writer's again, not pinned
  const job = await rewrite(how, [s.index])
  if (job) rewritten[k].job = job.id
  else delete rewritten[k]
}
export async function undoRewrite(pid: string, k: string) {
  const b = rewritten[k]
  delete rewritten[k]
  if (!b || P.proj?.id !== pid) return
  await reloadProject()   // the job's scene first (a click right as it ended could land before the board's reload)
  const s = P.proj?.id === pid ? P.proj.plan?.scenes.find((x) => beforeKey(pid, x) === k) : undefined
  if (!s) return
  for (const [x, v] of Object.entries(b.fields)) { if (v === undefined) delete s[x]; else s[x] = v }
  scheduleSave()
}
onJobEnd((j) => {
  for (const [k, b] of Object.entries(rewritten)) {
    if (b.job !== j.id) continue
    if (j.status !== 'done') { delete rewritten[k]; continue }
    b.done = true
    const pid = k.slice(0, k.indexOf(':'))
    banner(t('board.insp.rewritten', { n: b.n }), 'info', undefined, { label: t('board.insp.undoRewrite'), run: () => undoRewrite(pid, k) })
  }
})
export const undoRewriteOf = (s: Scene) => { if (P.proj) undoRewrite(P.proj.id, beforeKey(P.proj.id, s)) }

// a scene's place on the video's time; the episodes - the chains in order (a chain is shot as one piece, frame after
// frame), each with what it is about from the writer's plan (plan.outline), else the first words of its first scene
export const startOf = (s: Scene) => Number(s.start) || 0
export const lenOf = (s: Scene) => (Number(s.end) - Number(s.start)) || Number(s.seconds) || 5
export interface Episode { n: number; chain: number; scenes: Scene[]; start: number; end: number; about: string }
export function episodes(p: Plan): Episode[] {
  const out: Episode[] = [], outline = ((p as any).outline || []) as { chain: number; ru?: string; en?: string }[]
  for (const s of p.scenes) {
    const last = out[out.length - 1]
    if (last && last.chain === s.chain) { last.scenes.push(s); last.end = startOf(s) + lenOf(s) }
    else out.push({ n: out.length + 1, chain: s.chain, scenes: [s], start: startOf(s), end: startOf(s) + lenOf(s), about: '' })
  }
  for (const e of out) e.about = outline.find((o) => o.chain === e.chain)?.ru || e.scenes[0].ru || ''
  return out
}
// picking scenes: a plain click selects one; Ctrl adds or takes one away; Shift picks from the selected one up to it
export function pickScene(i: number, e?: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean }) {
  if (e?.shiftKey) {
    const a = Math.min(P.sel, i), b = Math.max(P.sel, i)
    P.picked = a === b ? [] : Array.from({ length: b - a + 1 }, (_, k) => a + k)
    return
  }
  if (e?.ctrlKey || e?.metaKey) {
    const set = new Set(P.picked.length ? P.picked : [P.sel])
    if (set.has(i)) set.delete(i); else set.add(i)
    const list = [...set].sort((x, y) => x - y)
    if (list.length <= 1) { P.picked = []; P.sel = list[0] ?? i } else { P.picked = list; if (!set.has(P.sel)) P.sel = i }
    return
  }
  P.picked = []
  P.sel = i
}
export const isPicked = (i: number) => P.picked.includes(i)

// the user's own prompt (prompts.is_raw): it goes to H3 as it is, the scene's fields and the writer are out of it
// a scene's notes: the writer's «проверь» (problems) and what the shot clip's auto-check found (app/checks.py: a cut
// inside, black, frozen, smeared, the face) - the grid marks them, the scene panel says them
// `quiet` («почти не движется»): a calm shot to glance at, not a fault - grey, not among the notes (checks.calm);
// `line`: the measure's line the note names (the motion's, the face's similarity)
export interface Found { code: string; name: string; at: number; length?: number; value?: number; line?: number; severe: boolean; quiet?: boolean }
const allFound = (i: number): Found[] => ((P.est?.[P.proj?.settings.quality || 'draft']?.checks?.[String(i)]) || []) as Found[]
const isQuiet = (x: Found) => !!x.quiet || x.code === 'still'
export const foundOf = (i: number): Found[] => allFound(i).filter((x) => !isQuiet(x))
export const calmOf = (i: number): Found[] => allFound(i).filter(isQuiet)
export const problemsOf = (s: Scene) => (s.status === 'check' ? (s.problems_ru || s.problems || []).join('; ') : '')
export const hasNotes = (s: Scene) => !!problemsOf(s) || foundOf(s.index!).length > 0
// a check in words: a whole shot's one says its measure and its line, not «на 0,0 с» (the face as a share, like the
// cast tab's «75 %»); a moment's one says when
export const pct = (v: number) => `${Math.round(v * 100)}%`   // as the cast tab says it (CastingCard)
export function foundLabel(x: Found) {
  if (x.code === 'still' && x.value != null && x.line != null) return t('board.card.foundStill', { name: x.name, v: dec(x.value.toFixed(2)), line: dec(String(x.line)) })
  if ((x.code === 'hero' || x.code === 'frame') && x.value != null && x.line != null) return t('board.card.foundFace', { name: x.name, v: pct(Math.max(0, x.value)), line: pct(x.line) })
  if (['still', 'hero', 'frame'].includes(x.code) || (!x.at && !x.length)) return x.name
  return t('board.card.foundAt', { name: x.name, at: dec(x.at.toFixed(1)) })
}
// the notes of the shot in a line: «В клипе: …» for the clip's, «Кадр: …» for its start frame's (`frame`)
export function foundLines(list: Found[]) {
  const clip = list.filter((x) => x.code !== 'frame'), frame = list.filter((x) => x.code === 'frame')
  return [...(clip.length ? [t('board.card.found', { x: clip.map(foundLabel).join('; ') })] : []),
    ...(frame.length ? [t('board.card.foundFrame', { x: frame.map(foundLabel).join('; ') })] : [])]
}
// whether a scene's actions name someone in the frame (as app/planner/prompts.py has_people): a clip's insert of the
// empty coat on the chair names nobody - no hero's portrait, its frame drawn empty
const PEOPLE = /\b(she|he|her|his|him|woman|women|man|men|girl|boy|person|people|crowd|figure|hand|hands|silhouette|someone|anyone)\b/i
const ROLES = /\b(heroine|hero|singer|dancer|character|protagonist|performer|musician|guitarist|drummer|band|couple|crowd)\b/i
export function hasPeople(s: Scene, p?: Plan) {
  const b = (s.beats_en || []).join(' ').trim()
  if (!b || PEOPLE.test(b) || ROLES.test(b)) return true
  const looks = (p?.cast || []).map((c: any) => `${c.en || ''} ${c.ru || ''}`).join(' ')   // a hero by the name their look uses
  return (b.match(/\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b/g) || []).some((w: string) => new RegExp(`(?<!\\p{L})${w}(?!\\p{L})`, 'u').test(looks))
}
export const isRaw = (s: Scene) => s.raw !== undefined && s.raw !== null
// text a Russian reader needs translated: more Latin letters than Cyrillic (translate.english)
export const english = (s: string) => (s || '').replace(/[^a-z]/gi, '').length > (s || '').replace(/[^а-яё]/gi, '').length
// «Перевести на русский» has work here: an English «what happens», or an English own prompt without its Russian copy
export const needsRussian = (s: Scene) => english(s.ru || '') || (isRaw(s) && english(s.raw || '') && !s.raw_ru)
// a new scene that starts from a photo (prompts.starts_from_photo): H3 animates that picture
export const startsFromPhoto = (s: Scene) => s.kind === 'new' && !!s.start_photo
// several people: who is in a scene (a new scene says it, its continuations keep it); only their looks go into its prompt
// a continuation starts from the last frame of the scene it names (`from`, any earlier one) or of the one before it
export const fromOf = (p: Plan, s: Scene): Scene | null => (s.kind !== 'continue' ? null
  : (s.from && p.scenes.slice(0, s.index).find((x) => x.id === s.from)) || p.scenes[s.index - 1] || null)
export function openerOf(p: Plan, s: Scene): Scene | undefined {
  let x: Scene | null = s
  for (let n = 0; x && x.kind !== 'new' && n <= p.scenes.length; n++) x = fromOf(p, x)
  return x || undefined
}
export const castName = (c: Record<string, any>, i: number) => `${i + 1}. ${(c.ru || '').replace(/^\d+[-\s]*лет[а-я]*\s*/i, '').split(/[,.]/)[0].slice(0, 40)}`
export function whoShort(p: Plan, s: Scene) {
  if (p.mode !== 'several') return ''
  const who = (s.who && s.who.length ? s.who : (openerOf(p, s) || {}).who) || []
  return who.length ? ` · ${who.length === (p.cast || []).length ? t('board.whoAll') : t('board.whoSome', { who: who.join(', ') })}` : ''
}
// the lab's template, and a continuation starts from the previous scene's last frame
export const rawTemplate = (s: Scene) => (s.kind === 'continue' ? 'Continue seamlessly from <Picture 1>.\n\n' : '') + `Realistic live-action cinematic look, soft natural light, shallow depth of field, film grain.

Scene: ...

Camera: medium shot, static camera.

Timeline:
[0s-2s] ...
[2s-5s] ...

Audio: ...

No text, subtitles, logos or watermarks.`
