// The home's «Что снимаем?» and the stage bar of «Сделать ролик» (app/autopilot.py).
import type { Job } from './types'

// «Поняли так»: what the box makes of what it was given - the same rules as autopilot.understand (tools/test_home.py)
export type What = 'clip' | 'clip_hero' | 'story' | 'story_hero' | 'story_start' | 'beat'
export const WHATS: What[] = ['clip', 'clip_hero', 'story', 'story_hero', 'story_start', 'beat']
export function understand(song: boolean, photo: boolean, text: string): What | '' {
  if (song) return photo ? 'clip_hero' : 'clip'
  if (photo) return 'story_hero'
  return text.trim().length >= 3 ? 'story' : ''
}
// «Не так? Изменить»: the kinds that can be made of what was given (autopilot.misfit says no to the others)
export function fits(w: What, song: boolean, photo: boolean, text: string): boolean {
  if ((w.startsWith('clip') || w === 'beat') && !song) return false   // a beat clip is cut on a song's drop, with a hero of its own (no photo)
  if (w !== 'clip' && w !== 'story' && w !== 'beat' && !photo) return false
  if (w === 'story' && text.trim().length < 3) return false
  return true
}

// the bar's seven steps for every way: the server's stages (STAGES) fall on them - the trial scene and the shooting are
// «Съёмка», the render's assembly, mixing and upscaling are «Монтаж»; a story's «Слова» are its idea, done at once
export const STEPS = ['words', 'write', 'hero', 'places', 'frames', 'shoot', 'montage'] as const
export type Step = typeof STEPS[number]
const MONTAGE = ['assembling', 'mixing', 'upscaling', 'interpolating', 'done']
export interface AutoState { stage?: string | null; done?: string[]; error?: string | null; stopped?: boolean; finished?: boolean; ask?: any; what?: string; req?: { what?: string; song?: string | null; script?: string; hero?: boolean; frames?: boolean; places?: boolean } }

export function stepOf(stage: string | null | undefined, job?: Job | null): Step | null {
  if (!stage) return null
  if (stage === 'trial') return 'shoot'
  if (stage === 'render') return MONTAGE.includes((job as any)?.progress?.stage) ? 'montage' : 'shoot'
  return (STEPS as readonly string[]).includes(stage) ? (stage as Step) : null
}

// the steps this request runs (the server's stages, mirrored from the saved request when no job is running): «пишу сам»
// stops at the script, the switches drop the hero, the places and the frames
export function stepsRun(stageIds: string[]): Step[] {
  if (!stageIds.length) return [...STEPS]
  const has = (x: string) => stageIds.includes(x)
  return STEPS.filter((s) => s === 'words' ? has('words') || has('render')   // a story's idea is its words: shown done, unless it stops at the script
    : s === 'shoot' ? has('render') || has('trial') : s === 'montage' ? has('render') : has(s))
}
export function stageIdsOf(r?: AutoState['req']): string[] {
  if (!r) return []
  if (r.script === 'own') return ['write']
  const frames = r.frames !== false
  return ['write', ...(r.hero !== false ? ['hero'] : []), ...(frames && r.places !== false ? ['places'] : []), ...(frames ? ['frames'] : []), 'render']
}

// the route «Как снимаем» (RouteStrip.vue) and the bar (StageBar.vue) draw the steps alike (RouteSteps.vue): an icon
// each, its time
export const STEP_ICON: Record<Step, string> = { words: 'music', write: 'quill', hero: 'portrait', places: 'pin', frames: 'keyframe', shoot: 'clapper', montage: 'reel' }
const STEP_OF: Record<string, Step> = { words: 'words', write: 'write', hero: 'hero', places: 'places', frames: 'frames', trial: 'shoot', render: 'shoot' }
export const ASSEMBLY = 60   // the render's assembly, mixing and 1080p (autopilot.ASSEMBLY): the montage's share of «render»
// seconds by step from the server's stages ({id, est}), the render's assembly given to the montage
export function stepSecs(stages: { id: string; est: number }[]): Partial<Record<Step, number>> {
  const out: Partial<Record<Step, number>> = {}
  for (const x of stages) { const s = STEP_OF[x.id]; if (s) out[s] = (out[s] || 0) + x.est }
  if (stages.some((x) => x.id === 'render')) { out.shoot = Math.max(0, (out.shoot || 0) - ASSEMBLY); out.montage = ASSEMBLY }
  return out
}

// the route's estimate before the start (POST /api/autopilot/estimate): the job's own figures by step
export interface RouteEstimate {
  what: string; total: number; stages: Record<string, number>; steps: Partial<Record<Step, number>>; scenes: number; seconds: number
  run: string[]; model: string; models: Record<string, number>; gpu: string; words_done: boolean
}

// which steps are done: by the stages done (a story has no song's words - its idea is them)
export function stepsDone(done: string[], clip: boolean, cur: Step | null, finished: boolean): Set<Step> {
  const out = new Set<Step>()
  if (finished) return new Set(STEPS)
  if (!clip || done.includes('words')) out.add('words')
  for (const s of ['write', 'hero', 'places', 'frames'] as Step[]) if (done.includes(s)) out.add(s)
  if (done.includes('render')) { out.add('shoot'); out.add('montage') }
  if (cur === 'montage') out.add('shoot')
  return out
}

// «Бит-клип» (what: 'beat'): its own seven steps on the same bar. The server's stages are the steps one to one:
// слова песни → окно дропа → план шотов → картинки → сцены → бит-монтаж → ролик (копия для телефона и обложка)
export const BEAT_STEPS = ['words', 'window', 'pool', 'pictures', 'scenes', 'beat', 'render'] as const
export type BeatStep = typeof BEAT_STEPS[number]
export const BEAT_ICON: Record<BeatStep, string> = { words: 'music', window: 'wave', pool: 'spark', pictures: 'image', scenes: 'clapper', beat: 'reel', render: 'film' }
// the job's counters while pictures / scenes run (progress.beat): «5/16», «3/16 · пересъёмок 1» (the second part is added by the caller)
export interface BeatProgress { pictures?: { done: number; total: number; redraws?: number }; scenes?: { done: number; total: number; reshoots?: number } }
export function beatCount(stage: string | null | undefined, b?: BeatProgress | null): { n: string; extra: number } {
  const c = stage === 'pictures' ? b?.pictures : stage === 'scenes' ? b?.scenes : null
  if (!c || !c.total) return { n: '', extra: 0 }
  return { n: `${c.done || 0}/${c.total}`, extra: (stage === 'pictures' ? (c as any).redraws : (c as any).reshoots) || 0 }
}
export const isBeatState = (a?: { what?: string; req?: { what?: string } } | null) => (a?.what || a?.req?.what) === 'beat'
