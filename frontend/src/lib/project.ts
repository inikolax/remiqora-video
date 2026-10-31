// The project being worked on (the storyboard and the video screens share it). It lives on disk
// (projects/<id>/project.json); every hand edit is saved at once and comes back with the prompts composed and
// validated by the server.
import { reactive } from 'vue'
import { api, post } from './api'
import { S, banner, onJobEnd } from './store'
import type { Job, Project } from './types'
import router from '../router'
import { t } from '../i18n'

export const P = reactive({
  proj: null as Project | null,
  est: null as Record<string, any> | null,   // how long «Снять ролик» takes for each quality, knowing the cache
  sel: 0,
  picked: [] as number[],   // several scenes picked at once (Ctrl / Shift, an episode's number): the group panel
  view: '' as '' | 'grid' | 'frame' | 'script' | 'clip',   // the board's centre: the frame of the scene or the script; '' - by the shots
  tab: 'scenes' as 'scenes' | 'cast' | 'places' | 'song' | 'video',
  showEn: false, editLook: false, openEn: false,
  after: null as null | { job: string; pid: string; quality?: string },   // a render waiting for the prompts of edited scenes (startRender)
  saveState: '' as '' | 'saving' | 'saved' | 'error',   // the board's save, said quietly in its bar
})

type Parts = Record<string, boolean>   // what of the project has edits: plan, settings, name
let saving: Parts | null = null
let timer: ReturnType<typeof setTimeout> | undefined

// The page's copy and the server's: a job saves the project while the board is open (a retake writes the scene's
// seed, takes and camera, a frame its start_photo and frame). The page never sends a whole stale plan over that: every
// PUT carries the project's `updated` its copy was made from (409 when a job saved since), and whenever the server's
// project comes back while there are edits not in it, the edits are kept on top - field by field, scene by scene (by
// id): what the user changed against `base` (the server's last word the copy was made from) stays, the rest is the
// server's. Saves, reloads and the calls that answer with the project go one after another, never two at once.
type Snap = { plan: any; settings: any; name: any }
let base: Snap | null = null
let chain: Promise<unknown> = Promise.resolve()
const serial = <T>(fn: () => Promise<T>): Promise<T> => { const r = chain.then(fn, fn); chain = r.catch(() => {}); return r }
const copy = <T>(x: T): T => (x === undefined || x === null ? x : JSON.parse(JSON.stringify(x)))
const snap = (p: Project): Snap => ({ plan: copy(p.plan), settings: copy(p.settings), name: p.name })
function eq(a: any, b: any): boolean {
  if (a === b) return true
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false
  const ka = Object.keys(a).filter((k) => a[k] !== undefined), kb = Object.keys(b).filter((k) => b[k] !== undefined)
  return ka.length === kb.length && ka.every((k) => eq(a[k], b[k]))
}
// a field the user changed against the base is theirs, any other is the server's
function mergeObj(b: any, l: any, s: any) {
  const out: Record<string, any> = {}
  for (const k of new Set([...Object.keys(s || {}), ...Object.keys(l || {})])) {
    const v = eq(l?.[k], b?.[k]) ? s?.[k] : l?.[k]
    if (v !== undefined) out[k] = v
  }
  return out
}
const sceneKey = (x: any, i: number) => (x?.id ? String(x.id) : `#${i}`)
function mergeScenes(b: any[], l: any[], s: any[]) {
  const B = new Map(b.map((x, i) => [sceneKey(x, i), x])), L = new Map(l.map((x, i) => [sceneKey(x, i), x]))
  const S = new Map(s.map((x, i) => [sceneKey(x, i), x]))
  const one = (k: string, lx: any) => (!B.has(k) ? lx : !S.has(k) ? undefined : mergeObj(B.get(k), lx, S.get(k)))
  // the order is the server's unless the user moved scenes here (the script's drag)
  if (eq(l.map(sceneKey), b.map(sceneKey))) return s.map((sx, i) => (L.has(sceneKey(sx, i)) ? one(sceneKey(sx, i), L.get(sceneKey(sx, i))) : sx)).filter(Boolean)
  const out = l.map((lx, i) => one(sceneKey(lx, i), lx)).filter(Boolean)
  s.forEach((sx, i) => { const k = sceneKey(sx, i); if (!L.has(k) && !B.has(k)) out.splice(Math.min(i, out.length), 0, sx) })   // added by a job meanwhile
  return out
}
function mergePlan(b: any, l: any, s: any) {
  const { scenes: bs, ...b0 } = b, { scenes: ls, ...l0 } = l, { scenes: ss, ...s0 } = s
  return { ...mergeObj(b0, l0, s0), scenes: mergeScenes(bs || [], ls || [], ss || []) }
}
// the server's project into the page: the parts with edits pending (`pend`, made after `from` was the server's
// copy) keep them on top of it
function adopt(fresh: Project, from: Snap | null = base, pend: Parts | null = saving) {
  const cur = P.proj
  const keep: Parts = cur && cur.id === fresh.id && from ? pend || {} : {}
  P.proj = {
    ...fresh,
    plan: keep.plan && cur!.plan && fresh.plan && from!.plan ? mergePlan(from!.plan, cur!.plan, fresh.plan) as Project['plan'] : fresh.plan,
    settings: keep.settings ? mergeObj(from!.settings, cur!.settings, fresh.settings) : fresh.settings,
    name: keep.name && cur!.name !== from!.name ? cur!.name : fresh.name,
  }
  base = snap(fresh)
}

export async function openProject(id: string) {
  if (P.proj && P.proj.id === id) return
  if (P.proj && saving) await flushSave()   // the other project's edits go out first
  const fresh = await api<Project>(`/api/projects/${id}`)
  adopt(fresh)
  P.saveState = ''
  P.sel = 0
  P.picked = []
  P.tab = 'scenes'
  await loadEstimate()
}
// the project again from the server (a job of it ended): edits not saved yet stay on top, and go out as they would
export async function reloadProject() {
  if (!P.proj) return
  const pid = P.proj.id
  await serial(async () => {
    const fresh = await api<Project>(`/api/projects/${pid}`)
    if (P.proj?.id === pid) adopt(fresh)
  })
  await loadEstimate()
}
export async function loadEstimate() {
  if (!P.proj || !P.proj.plan) { P.est = null; return }
  try { P.est = await api(`/api/projects/${P.proj.id}/estimate`) } catch { P.est = null }
}
export function scheduleSave(what: 'plan' | 'settings' | 'name' = 'plan') {
  clearTimeout(timer)
  saving = saving || {}
  saving[what] = true
  P.saveState = 'saving'
  timer = setTimeout(flushSave, 350)
}
export function flushSave(): Promise<void> {
  clearTimeout(timer)
  return serial(save)
}
async function save() {
  const what = saving
  saving = null
  if (!what || !P.proj) return
  const pid = P.proj.id
  P.saveState = 'saving'
  for (let tries = 0; ; tries++) {
    const cur = P.proj!
    const body: Record<string, unknown> = { rev: cur.updated ?? null }
    if (what.plan) body.plan = cur.plan
    if (what.settings) body.settings = cur.settings
    if (what.name) body.name = cur.name
    const sent = snap(cur)   // what the server gets: edits made while it answers stay on top of its answer
    try {
      const r = await api<Project>(`/api/projects/${pid}`, { method: 'PUT', body })
      if (P.proj?.id === pid) adopt(r, sent, saving)
      P.saveState = saving ? 'saving' : 'saved'
      await loadEstimate()
      return
    } catch (e) {
      // a job saved the project since the copy was made: take its project, put the edits on top, send again
      if ((e as { status?: number }).status === 409 && tries < 3 && P.proj?.id === pid) {
        try { adopt(await api<Project>(`/api/projects/${pid}`), base, { ...what, ...(saving || {}) }); continue } catch { /* said below */ }
      }
      // the edit stays pending, so «Повторить» (or the next edit) sends it again; the banner stays until closed
      saving = { ...what, ...(saving || {}) }
      P.saveState = 'error'
      banner(t('board.notSaved', { msg: (e as Error).message }))
      return
    }
  }
}
export const unsaved = () => !!saving
// a server call that answers with the whole project (a photo, the track, a retake): saved edits first
export async function projectCall(method: string, path: string, body?: unknown) {
  await flushSave()
  const pid = P.proj!.id
  try {
    await serial(async () => { const r = await api<Project>(`/api/projects/${pid}${path}`, { method, body }); if (P.proj?.id === pid) adopt(r) })
    await loadEstimate()
    return true
  } catch (e) { banner((e as Error).message); return false }
}
export async function rewrite(how: string, scenes: number[] = []): Promise<Job | null> {
  await flushSave()
  try { const job = await post<Job>(`/api/projects/${P.proj!.id}/rewrite`, { how, scenes }); S.jobs = [...S.jobs, job]; return job }
  catch (e) { banner((e as Error).message); return null }
}
// the scenes whose text was edited after their prompt was written (SceneInspector setRu): the prompt that goes to the
// model is still the old one until the writer puts the new text into it (rewrite 'translate')
export const dirtyScenes = (p = P.proj?.plan) => (p?.scenes || []).filter((s) => s.ru_dirty && (s.raw === undefined || s.raw === null)).map((s) => s.index as number)
// «Снять ролик»: edited scenes first get their prompts from the text (`sync`), the render starts when that job ends -
// so the video shows what the user wrote, not the prompt from before the edit
export async function startRender(quality?: string, sync = true) {
  await flushSave()
  const pid = P.proj!.id, dirty = sync ? dirtyScenes() : []
  if (dirty.length) {
    try {
      const job = await post(`/api/projects/${pid}/rewrite`, { how: 'translate', scenes: dirty })
      S.jobs = [...S.jobs, job]
      P.after = { job: job.id, pid, quality }
      banner(t('board.pre.syncing', { x: t('board.scenesAcc', dirty.length) }), 'info')
    } catch (e) { banner((e as Error).message) }
    return
  }
  await render(pid, quality)
}
async function render(pid: string, quality?: string) {
  try {
    const job = await post(`/api/projects/${pid}/render`, { quality: quality || null })
    S.jobs = [...S.jobs, job]
    if (quality && P.proj?.id === pid) P.proj.settings.quality = quality
    // to the video's page - unless the user went to another video while the prompts were being written
    if (router.currentRoute.value.path.startsWith(`/p/${pid}`)) router.push(`/p/${pid}/video`)
  } catch (e) { banner((e as Error).message) }
}
onJobEnd(async (j) => {
  const a = P.after
  if (!a || j.id !== a.job) return
  P.after = null
  // a failed rewrite says so in its own banner (store.jobFailed): nothing is shot by the old prompts
  if (j.status !== 'done') { banner(t('board.pre.notStarted'), j.status === 'error' ? 'error' : 'info'); return }
  if (P.proj?.id === a.pid) await reloadProject()
  await render(a.pid, a.quality)
})

// the project's jobs
export const liveRender = (pid: string) => S.jobs.find((j) => j.kind === 'render' && (j.status === 'running' || j.status === 'queued') && j.params?.project === pid)
export const liveWriter = (pid: string) => S.jobs.find((j) => (j.kind === 'write' || j.kind === 'rewrite') && (j.status === 'running' || j.status === 'queued') && j.params?.project === pid)
export const lastRender = (pid: string) => S.jobs.filter((j) => j.kind === 'render' && j.params?.project === pid).sort((a, b) => (b.created || 0) - (a.created || 0))[0]
export const file = (path: string) => `/api/projects/${P.proj!.id}/files/${path}`

// the output: as shot / 1080p / 4K by RTX, HDR10 by TrueHDR, 48 fps by RIFE (post.py)
export const output = (st: Record<string, any>) => ({ size: st.rtx === false ? 'off' : '1080p', hdr: false, fps48: false, ...(st.output || {}) })
export function outLabel(st: Record<string, any>) {
  const o = output(st), parts: string[] = []
  if (o.size !== 'off') parts.push(o.size === '4k' ? '4K' : '1080p')
  if (o.hdr && o.size !== 'off') parts.push('HDR10')
  if (o.fps48) parts.push('48 fps')
  return parts.join(' · ') || t('video.asShot')
}
