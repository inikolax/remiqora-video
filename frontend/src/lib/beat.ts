// «Бит-клип»: the types of the server's answers (GET /api/beat/info, the beat montage's and the
// output's panels) and the small helpers the home form and the node panels share.
import { reactive } from 'vue'
import { api } from './api'
import type { Job } from './types'
import { currentLocale } from '../i18n'
import { AUTO } from './looks'

// a preset / genre as the server names it: {id, ru, en}
export interface Named { id: string; ru: string; en: string }
export const nameOf = (x: { ru: string; en: string }) => (currentLocale() === 'en' ? x.en || x.ru : x.ru || x.en)

export const GENRES = ['auto', 'techno', 'dnb', 'hardstyle', 'pop'] as const
export type Genre = typeof GENRES[number]
// the faceless hero presets (the server's list rules; this one orders the cards before /api/beat/info answers)
export const HERO_PRESETS = ['chrome', 'visor', 'porcelain', 'hood', 'silhouette'] as const

export interface BeatInfo {
  bpm: number; genre: string; drop: number; window: { start: number; seconds: number }; build_bars: number; drop_bars: number; seconds: number
  presets: Named[]; genres: Named[]
}
// the shot roles and framings a pool's shot can take (app: scene nodes carry data.role / data.framing)
export const ROLES = ['hero', 'atmos', 'close', 'impact', 'riser'] as const
export const FRAMINGS = ['macro', 'close', 'medium', 'wide'] as const
export interface PoolShot { title: string; framing: string; role: string; picture_en: string; motion_en: string }

// the video models a beat clip's scenes can be shot with (app/beat_models.py MODELS): H3 and LTX 2.5
export const BEAT_VIDEOS = ['h3', 'ltx25'] as const
export type BeatVideo = typeof BEAT_VIDEOS[number]

// the home form of the beat clip, kept between visits (the shared home form S.form holds the song)
interface BeatForm { idea: string; hero: string; heroOwn: boolean; heroText: string; faceHidden: boolean; look: string; genre: Genre; quality: 'draft' | 'final'; length: 'drop'; picture: string; video: BeatVideo; job: string }
const KEY = 'remiqora.beat.form'
const saved = (() => { try { return JSON.parse(localStorage.getItem(KEY) || '{}') } catch { return {} } })()
export const B = reactive<BeatForm>({ idea: '', hero: 'chrome', heroOwn: false, heroText: '', faceHidden: true, look: AUTO, genre: 'auto', quality: 'draft', length: 'drop', picture: 'krea2', video: 'h3', job: '', ...saved })
if (!BEAT_VIDEOS.includes(B.video)) B.video = 'h3'   // a stored value the form does not offer any more
export const keepBeat = () => { try { localStorage.setItem(KEY, JSON.stringify(B)) } catch { /* private window */ } }

// The beat clip's writer job (B.job, kept in localStorage) outlives the page: a job that failed or was stopped, or one the
// server forgot (a restart), would make the home page open the beat form forever. Ask the server; forget what is over.
// Returns the job while it is still there (a finished one too, so the form can open its graph), else null.
export async function checkBeatJob(): Promise<Job | null> {
  if (!B.job) return null
  try {
    const j = await api<Job>(`/api/jobs/${B.job}`)
    if (j.status !== 'queued' && j.status !== 'running') { B.job = ''; keepBeat() }
    return j
  } catch (e) {
    if ((e as { status?: number }).status === 404) { B.job = ''; keepBeat() }   // unknown to the server; a network error says nothing
    return null
  }
}

export const beatInfo = (song: string) => api<BeatInfo>(`/api/beat/info?song=${encodeURIComponent(song)}`)

// the palette comes as BGR triples (OpenCV's order), <input type=color> wants #rrggbb
export type BGR = [number, number, number]
const h2 = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0')
export const bgrToHex = (c: BGR | number[] | undefined) => (c && c.length === 3 ? `#${h2(c[2])}${h2(c[1])}${h2(c[0])}` : '#000000')
export function hexToBgr(h: string): BGR {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(h.trim())
  return m ? [parseInt(m[3], 16), parseInt(m[2], 16), parseInt(m[1], 16)] : [0, 0, 0]
}

// the beat montage's panel (GET/PUT /api/projects/{pid}/nodes/{nid}/beat)
export interface BeatSpec { key: string; kind: 'float' | 'int' | 'bool'; min?: number; max?: number; step?: number; group: 'length' | 'kick' | 'snare' | 'effects' | 'grade' | 'sound'; ru: string; en: string; help_ru: string; help_en: string }
export interface CaptionWord { i: number; start: number; end: number; word: string; hidden?: boolean; edited?: boolean }
export interface BeatView {
  node: string; state: string; error?: string | null; preset: string; presets: Named[]
  params: Record<string, number | boolean>; overrides: Record<string, number | boolean>; spec: BeatSpec[]
  palette: { a: BGR; b: BGR; tint: BGR }; title: string; hud: string; fps: number; loudness: number
  captions: { on: boolean; words: CaptionWord[] }; drop: number; bpm: number
  file: string | null; preview: string | null; scenes_ready: boolean; cleaned?: { title?: boolean; hud?: boolean }
  graph_rev?: number; node_data?: Record<string, any>   // a PUT's answer: the graph's new rev and the node's keys as saved
}
export const SPEC_GROUPS = ['length', 'kick', 'snare', 'effects', 'grade', 'sound'] as const

// the output's publication panel (GET/PUT /api/projects/{pid}/nodes/{nid}/publish)
export interface PublishView {
  phone: boolean; cover: boolean; file: string | null; phone_file: string | null; phone_mb: number | null; cover_file: string | null; cover_at: number | null
  duration: number; drop: number | null; text: string; removed?: boolean; state?: string
  graph_rev?: number; node_data?: Record<string, any>
}
