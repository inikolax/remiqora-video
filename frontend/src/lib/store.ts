// What every screen shares: the server's config, the jobs (polled each second), the system (each 3 s), the
// writer's models and the one picked in the header, the LoRA library, the banners and the open help card.
import { reactive } from 'vue'
import { api } from './api'
import { t } from '../i18n'
import type { Config, Job, LlmList, Lora, Sys } from './types'

const KEY = 'h3studio.studio.v1'
interface Form { idea: string; seconds: number; aspect: string; mood: string; mode: string; music: string; photo: any; photoRole: string; manual: boolean; graph: boolean; video: string
  clip: boolean; song: string; songFrom: number; songSecs: number; clipVideo: string   // phase 11: a clip from a song
  clipSinger?: boolean; clipFrames?: boolean; clipPlaces?: boolean   // what the clip's job draws after the script: only when ticked
  clipLook?: 'writer' | 'own' | 'photo'; clipLookRu?: string; clipGender?: string; clipStory?: 'writer' | 'idea'; clipScenes?: 'all' | 'empty' | 'none'   // «Что пишет сценарист»
  loras?: { id: string; name: string; strength: number }[]; picLoras?: { krea?: { id: string; name: string; strength: number }[]; flux2?: { id: string; name: string; strength: number }[] } }   // the new video's LoRA (LoraSet)
// an error stays until closed (it may be the only word of a lost edit or a failed job); news goes by itself.
// `to`: the page the error is about, a link in the banner
// `act`: one action of the news itself («Вернуть» after a scene was rewritten)
export interface Banner { id: number; text: string; kind: 'error' | 'info'; to?: string; act?: { label: string; run: () => void } }
const saved = (() => { try { return JSON.parse(localStorage.getItem(KEY) || '{}') } catch { return {} } })()

export const S = reactive({
  cfg: null as Config | null,
  jobs: [] as Job[],
  sys: null as Sys | null,
  llms: null as LlmList | null,
  llm: (saved.llm || null) as string | null,
  loras: [] as Lora[],
  kreaLoras: [] as { id: string; name: string; verdict: string; strength?: number }[],   // Krea 2's library (/api/krea/loras)
  projects: [] as Record<string, any>[], moods: [] as string[],
  banners: [] as Banner[],
  help: null as null | { section: string; term: string; x: number; y: number; key: string },
  guide: null as string | null,   // the help window open: a screen's (lib/guides.ts) or 'app' from the header
  keys: false,                    // the graph's keys sheet
  // the idea screen's form, kept between visits
  form: { idea: '', seconds: 30, aspect: '16:9', mood: 'Кино', mode: 'one', music: '', photo: null, photoRole: 'start', manual: false, graph: false, video: 'h3',
    clip: false, song: '', songFrom: 0, songSecs: 60, clipVideo: 'ltx23', ...(saved.form || {}) } as Form,
})

export const keep = () => { try { localStorage.setItem(KEY, JSON.stringify({ form: S.form, llm: S.llm })) } catch { /* private window */ } }

let bannerId = 0
export function banner(text: string, kind: Banner['kind'] = 'error', to?: string, act?: Banner['act']) {
  if (S.banners.some((b) => b.text === text)) return   // the same words again (a retry, a poll): once is enough
  const id = ++bannerId
  S.banners.unshift({ id, text, kind, to, act })
  if (kind === 'info') setTimeout(() => closeBanner(id), 15000)
}
export const closeBanner = (id: number) => { S.banners = S.banners.filter((b) => b.id !== id) }

// a job that just ended: the screens that care (a project's writer, the lab's takes) hook in here
type EndHook = (job: Job) => void
const endHooks = new Set<EndHook>()
export const onJobEnd = (fn: EndHook) => { endHooks.add(fn); return () => endHooks.delete(fn) }

// The jobs seen queued or running (the poll's and those a screen put in S.jobs on submitting) and the ends already
// told: a job that ends between two polls, or whose submit a late answer of the poll before it wiped from S.jobs,
// still has its end told - once. One poll at a time: an answer never lands over a newer one.
const seenLive = new Set<string>(), told = new Set<string>()
let polling = false
export async function pollJobs() {
  if (polling) return
  polling = true
  let jobs: Job[]
  try { jobs = await api<Job[]>('/api/jobs') } catch { return } finally { polling = false }
  for (const b of S.jobs) if (live(b)) seenLive.add(b.id)
  S.jobs = jobs
  for (const j of jobs) {
    if (live(j)) { seenLive.add(j.id); continue }
    if (!seenLive.has(j.id) || told.has(j.id) || !['done', 'error', 'cancelled'].includes(j.status)) continue
    told.add(j.id)
    if (j.status === 'error') jobFailed(j)
    endHooks.forEach((fn) => fn(j))
  }
}
// a job seen alive that failed, in a banner wherever the user is: the board only reloads the project, so a frame, a
// take or a portrait that failed simply vanished. The video page and the lab say their own jobs' errors in place.
export const jobKindName = (j: Job) => t(`status.kind.${['render', 'take', 'graph', 'scene', 'voice', 'draw', 'frame', 'place', 'lyrics'].includes(stageKind(j)) ? stageKind(j) : stageKind(j) === 'unlike' ? 'frame' : 'writer'}`)
function jobFailed(j: Job) {
  const pid = j.params?.project as string | undefined, here = location.hash.replace(/^#/, '').split('?')[0]
  const to = !pid ? (j.kind === 'scene' ? '/lab' : undefined) : j.kind.startsWith('graph') ? `/g/${pid}` : `/p/${pid}${j.kind === 'render' ? '/video' : ''}`
  if ((j.kind === 'render' || j.kind === 'scene') && here === to) return
  const what = jobKindName(j), err = j.error || t('misc.jobFailed')
  banner(pid ? t('misc.jobErrorIn', { name: projectName(pid), what, err }) : t('misc.jobError', { what, err }), 'error', here === to ? undefined : to)
}
export async function pollSystem() {
  try { S.sys = await api<Sys>('/api/system') } catch { /* the server is restarting */ }
}
export async function loadLlms() {
  try { S.llms = await api<LlmList>('/api/llm/models') } catch { return }
  const r = S.llms!
  if (!r.models.some((m) => m.id === S.llm)) S.llm = r.default || r.models[0]?.id || null
  if (!r.server_ok) banner(t('misc.noLlamaServer'))
}
export async function loadKreaLoras() {
  try { S.kreaLoras = (await api<{ loras: typeof S.kreaLoras }>('/api/krea/loras')).loras } catch { /* no Krea folder: the list stays empty */ }
}
export async function loadLoras() {
  try {
    const list = await api<Lora[]>('/api/loras')
    // the same files: keep the array, so nothing re-renders every 8 s
    if (JSON.stringify(list.map((l) => l.id + l.verdict + l.strength)) !== JSON.stringify(S.loras.map((l) => l.id + l.verdict + l.strength))) S.loras = list
  } catch { /* the lab says it when the folder is empty */ }
}

export async function loadProjects() {
  try { const r = await api('/api/projects'); S.projects = r.projects; S.moods = r.moods } catch (e) { banner((e as Error).message) }
}
export const projectName = (id: string) => S.projects.find((p) => p.id === id)?.name || id
// a video model's card (app/videomodels.py), its short name and colour; a model the server no longer has: its id, grey
export const videoModel = (id: string) => (S.cfg?.video_models || []).find((m) => m.id === id)
export const modelName = (id: string) => videoModel(id)?.short || id
export const modelColor = (id: string) => videoModel(id)?.color || 'var(--rule-3)'
// the LoRA of a video model's own folders (app/loras.py): H3's, LTX 2.3's, LTX 2.5's; an imported model's are its version's
// a scene's LoRA of its model; never one that reads a clip («Видео → видео» picks those: v2vLoras)
export const lorasFor = (model: string) => S.loras.filter((l) => l.model === (model || 'h3').replace(/^rq_/, '').replace(/^wan5b_fast$/, 'wan5b') && !l.v2v)
export const v2vLoras = () => S.loras.filter((l) => l.v2v)

export async function start() {
  S.cfg = await api<Config>('/api/config')
  await Promise.all([loadLlms(), loadLoras(), loadProjects(), pollJobs(), pollSystem()])
  setInterval(pollJobs, 1000)
  setInterval(pollSystem, 3000)
}

// the interface's language changed: what the server says in words (model cards, problems, LoRA notes) again in it
export async function reloadWords() {
  try { S.cfg = await api<Config>('/api/config') } catch { /* the old words until the next start */ }
  await Promise.all([loadLlms(), loadLoras(), loadProjects()])
}

export const live = (j: Job) => j.status === 'running' || j.status === 'queued'
// a clip's «write» job goes on after the writer (app/clip_api.py): the song's words, the places, the singer, the
// frames - the stage it is at, as the kind of the job that does that alone (the header and the board name it so)
const WRITE_STAGES: Record<string, string> = { lyrics: 'lyrics', grouping: 'places', drawing: 'draw', frames: 'frame', unlike: 'unlike' }
export const stageKind = (j: Job) => (j.kind !== 'write' ? j.kind
  : j.progress?.stage === 'places' ? (j.progress.total ? 'place' : 'places') : WRITE_STAGES[j.progress?.stage] || 'write')
