// Phase 9: a graph project being edited (#/g/<id>). The canvas works on Vue Flow's own node and edge arrays
// (GE.nodes / GE.edges); every change is saved as the server's document (graph.json: nodes with their type, edges,
// rev) a moment later. The server says what every node is (GET …/nodes/state: ready / to make / waiting / error,
// its key and files); a running job's progress lies on top of that.
import { reactive } from 'vue'
import type { Edge, Node } from '@vue-flow/core'
import { api, post } from './api'
import { S, banner } from './store'
import { t as tr } from '../i18n'
import nodesText from '../locales/nodes'

export interface PortSpec { type: string; multi: boolean }
export interface TypeSpec { title: string; who: string; in: Record<string, PortSpec>; out: Record<string, string> }
export interface NodeState { state: string; key: string | null; file: string | null; png: string | null; error: string | null
  refs: boolean; seconds: number; takes: { seed: number; key: string; cached: boolean }[]; start_of: string | null
  text?: string; warn?: string; alpha?: string
  model?: string; ref_mode?: string; voice?: { sim: number | null; verdict: 'alike' | 'partly' | 'unlike' | null }
  checks?: { code: string; name: string; at: number; length: number; severe: boolean }[]   // a scene: its prompt with the spoken lines woven in; the face-drift warning
  note?: { frames: number; faces: number; runs: number; anchors: number; fixed: number; seconds: Record<string, number> } }   // «Лица»: what it found (app/facefix.py)
export interface GraphState { quality: string; width: number; height: number; auto_size: [number, number]; own_size: boolean
  rev: number; nodes: Record<string, NodeState>
  to_shoot: number; pictures: number; per_scene: number; seconds: number }

interface GEState {
  id: string
  proj: Record<string, any> | null
  types: Record<string, TypeSpec>
  picture: string                      // krea2-ui's model, or why a picture can't be made
  nodes: Node[]
  edges: Edge[]
  rev: number
  state: GraphState | null
  sel: string | null
  saving: boolean
}
// typed by hand: Vue's unwrapping of Vue Flow's node type is too deep for TypeScript
export const GE = reactive({ id: '', proj: null, types: {}, picture: '', nodes: [], edges: [], rev: 0, state: null, sel: null, saving: false }) as unknown as GEState

// the colour of a node's header: who does the work (the status strip's colours)
export const WHO_COLOR: Record<string, string> = { h3: 'var(--accent)', writer: 'var(--ok)', ffmpeg: '#378ADD', user: 'var(--faint)', krea: '#f59e0b', v2v: '#14b8a6', facefix: '#2dd4bf', none: 'var(--rule-3)' }
// a table of labels that follows the interface's language: each key read through t() when it is read (enumerable, so
// a v-for over it works); read in a template or a computed, it changes with the switch
export function labels<K extends string>(area: string, keys: readonly K[]): Record<K, string> {
  const o = {} as Record<K, string>
  for (const k of keys) Object.defineProperty(o, k, { get: () => tr(`${area}.${k}`), enumerable: true })
  return o
}
export const WHO_NAME: Record<string, string> = labels('nodes.who', ['h3', 'writer', 'ffmpeg', 'user', 'krea', 'v2v', 'facefix'])
export const PORT_COLOR: Record<string, string> = { text: 'var(--soft)', look: 'var(--ok)', image: '#e879f9', clip: '#378ADD', video: '#378ADD', audio: '#eab308', lora: 'var(--accent-hi)' }
export const PORT_NAME: Record<string, string> = labels('nodes.portType', ['text', 'look', 'image', 'clip', 'video', 'audio', 'lora'])
// a node's icon: one look each (lib/nodeHelp.ts says what each is for)
export const ICON: Record<string, string> = { idea: 'bulb', hero: 'user', writer: 'quill', prompt: 'text', photo: 'image', picture: 'brush', scene: 'clapper', v2v: 'film', facefix: 'face',
  frame: 'crop', sound: 'volume', lora: 'sliders', join: 'merge', montage: 'cut', track: 'music', music: 'mix', output: 'export', note: 'note', group: 'box' }
export const PORT_LABEL: Record<string, string> = labels('nodes.port', ['text', 'look', 'image', 'idea', 'cast', 'prompt', 'start', 'end', 'faces', 'lora',
  'frame', 'clip', 'clips', 'video', 'audio', 'voice', 'ref'])
// a node type's title in the interface's language (the server's /api/graph/types title - Russian - for a type the page
// doesn't know); ruTitle - always the Russian one: the help finds a node's card by it (HelpQ term)
export const typeTitle = (type: string): string => (type in nodesText.ru.title ? tr(`nodes.title.${type}`) : GE.types[type]?.title || type)
export const ruTitle = (type: string): string => (nodesText.ru.title as Record<string, string>)[type] || GE.types[type]?.title || type
export const MAKES = ['picture', 'scene', 'v2v', 'facefix', 'sound', 'frame', 'join', 'montage', 'music', 'output']
// the add menu, in the order of the work: a group's key (its name: t('graph.addGroup.<key>')) and its types
export const ADD_MENU: [string, string[]][] = [
  ['writer', ['idea', 'hero', 'writer']],
  ['scenes', ['prompt', 'photo', 'picture', 'scene', 'v2v', 'facefix', 'frame', 'sound', 'lora']],
  ['video', ['join', 'montage', 'track', 'music', 'output']],
  ['canvas', ['note', 'group']],
]

export const uid = () => Math.random().toString(16).slice(2, 10)
export const rseed = () => 1 + Math.floor(Math.random() * 2147483646)
// a scene's length: its own `seconds` (3-15), 5 when it says nothing; a prompt's - of the first scene it feeds
export const SCENE_S = [3, 15] as const
export const secondsOf = (n: Node | null) => { const v = Number((n?.data as any)?.seconds); return v >= SCENE_S[0] && v <= SCENE_S[1] ? Math.round(v) : 5 }
export function feedSeconds(id: string) {
  const e = GE.edges.find((x) => x.source === id && x.targetHandle === 'prompt')
  return e ? secondsOf(nodeOf(e.target)) : 5
}
// who may speak in a prompt (app/planner/prompts.py speakers_in): the storyboard's names, else "The woman", "The man"
export function speakersIn(text: string): string[] {
  const out: string[] = []
  for (const m of (text || '').matchAll(/\b(The (?:heroine|hero|main character)|Character \d+)\b/g)) if (!out.includes(m[1])) out.push(m[1])
  if (!out.length) for (const m of (text || '').matchAll(/\b(?:an?|the)\s+(?:[\w-]+\s+){0,3}?(woman|man|lady|person)\b/gi)) { const w = 'The ' + m[1].toLowerCase(); if (!out.includes(w)) out.push(w) }
  return out
}
export const fileUrl = (f: string | null | undefined) => (!f ? null : f.startsWith('@') ? `/api/projects/${f.slice(1).replace('/', '/files/')}` : `/api/projects/${GE.id}/files/${f}`)
export const nodeOf = (id: string | null) => (id ? GE.nodes.find((n) => n.id === id) || null : null)
export const tOf = (n: Node) => (n.data as any).t as string
export const live = () => S.jobs.find((j) => (j.kind === 'graph' || j.kind === 'graph-llm') && (j.status === 'running' || j.status === 'queued') && j.params?.project === GE.id)

// the server's document <-> Vue Flow's arrays
function toFlow(doc: { nodes: any[]; edges: any[]; rev: number }) {
  GE.nodes = doc.nodes.map((n) => ({ id: n.id, type: n.type === 'group' ? 'ggroup' : 'gnode', position: n.position, data: { ...n.data, t: n.type },
    zIndex: n.type === 'group' ? -1 : undefined, draggable: true }))
  // a Krea 2 «Картинка» has no «образцы» (an older graph may still link a picture there: the server never read it)
  const krea = new Set(doc.nodes.filter((n) => n.type === 'picture' && n.data?.model !== 'flux2').map((n) => n.id))
  GE.edges = doc.edges.filter((e) => !(e.targetHandle === 'ref' && krea.has(e.target))).map(edgeFlow)
  GE.rev = doc.rev
  saved = body()
}
export function edgeFlow(e: any): Edge {
  const s = doc_type(e.source), type = s ? GE.types[s]?.out[e.sourceHandle] : ''
  return { id: e.id, source: e.source, sourceHandle: e.sourceHandle, target: e.target, targetHandle: e.targetHandle, class: `ge-${type || 'x'}`, data: { type } }
}
function doc_type(id: string) { const n = nodeOf(id); return n ? tOf(n) : null }
// the graph as saved, without its rev: what the undo steps hold
const body = () => { const { rev: _rev, ...d } = toDoc(); return JSON.stringify(d) }
function toDoc() {
  return {
    rev: GE.rev,
    nodes: GE.nodes.map((n) => { const { t, ...data } = n.data as any; return { id: n.id, type: t, position: { x: Math.round(n.position.x), y: Math.round(n.position.y) }, data } }),
    edges: GE.edges.map((e) => ({ id: e.id, source: e.source, sourceHandle: e.sourceHandle, target: e.target, targetHandle: e.targetHandle })),
  }
}

export async function openGraph(id: string) {
  forgetSteps()
  GE.id = id
  GE.sel = null
  const [proj, types, doc] = await Promise.all([api(`/api/projects/${id}`), api('/api/graph/types'), api(`/api/projects/${id}/nodes`)])
  GE.proj = proj
  GE.types = types.types
  GE.picture = types.picture
  toFlow(doc)
  await loadState()
}
export async function loadState() {
  try { GE.state = await api(`/api/projects/${GE.id}/nodes/state`) } catch (e) { banner(tr('graph.stateFailed', { e: (e as Error).message })) }
}
export async function reloadDoc() {
  toFlow(await api(`/api/projects/${GE.id}/nodes`))
  await loadState()
}

let timer: ReturnType<typeof setTimeout> | undefined
let pending = false
// undo / redo: every save is a step - the graph as it was saved before it (a pause in typing makes a step too)
let saved = ''
const undoSteps: string[] = [], redoSteps: string[] = []
const STEPS = 60
export function touch(delay = 500) {
  pending = true
  clearTimeout(timer)
  timer = setTimeout(flush, delay)
}
export async function flush() {
  clearTimeout(timer)
  if (!pending || !GE.id) return
  pending = false
  GE.saving = true
  const now = body()
  if (saved && now !== saved) {
    undoSteps.push(saved)
    if (undoSteps.length > STEPS) undoSteps.shift()
    redoSteps.length = 0
  }
  saved = now
  try {
    const r = await api(`/api/projects/${GE.id}/nodes`, { method: 'PUT', body: toDoc() })
    GE.rev = r.rev
    await loadState()
  } catch (e) {
    const err = e as Error & { status?: number; detail?: any }
    if (err.status === 409 && err.detail?.graph) {   // a job wrote a result meanwhile: the server's graph wins
      toFlow(err.detail.graph)
      banner(tr('graph.conflict'))
      await loadState()
    } else banner(tr('graph.notSaved', { e: err.message }))
  } finally { GE.saving = false }
}
export const dirty = () => pending
export const canUndo = () => undoSteps.length > 0 || pending
export const canRedo = () => redoSteps.length > 0

// Ctrl+Z / Ctrl+Shift+Z: the graph a save back (or forward); the result is saved as any edit
async function step(from: string[], to: string[]) {
  await flush()   // an edit not saved yet becomes a step first
  const doc = from.pop()
  if (!doc) return false
  to.push(saved)
  toFlow({ ...JSON.parse(doc), rev: GE.rev })
  if (GE.sel && !nodeOf(GE.sel)) GE.sel = null
  pending = true
  await flush()
  return true
}
export const undo = () => step(undoSteps, redoSteps)
export const redo = () => step(redoSteps, undoSteps)
export function forgetSteps() { undoSteps.length = 0; redoSteps.length = 0; saved = '' }

// a group's nodes: those whose corner lies inside its frame; a selected group brings them along (copy, a template)
export function insideGroup(g: Node): Node[] {
  const d = g.data as any, x0 = g.position.x, y0 = g.position.y
  return GE.nodes.filter((n) => n.id !== g.id && n.position.x >= x0 && n.position.y >= y0 && n.position.x <= x0 + (d.w || 720) && n.position.y <= y0 + (d.h || 420))
}
export function withGroups(ids: string[]): string[] {
  const out = new Set(ids)
  for (const id of ids) { const g = nodeOf(id); if (g && tOf(g) === 'group') for (const n of insideGroup(g)) out.add(n.id) }
  return [...out]
}

// Ctrl+C / Ctrl+V / Ctrl+D: the selected nodes with the links between them; a paste lands a little lower right,
// with new ids (scenes keep their seeds - a copy is the same shot until it is changed)
let clip: { nodes: any[]; edges: any[] } | null = null
let pastes = 0
// a copied «Монтаж»: its clips point at the copied scenes (and get ids of their own)
function remapMontage(data: any, ids: Record<string, string>) {
  if (!data.edit) return
  data.edit = { ...data.edit, clips: (data.edit.clips || []).map((c: any) => ({ ...c, scene: ids[c.scene] || c.scene, id: uid() })),
    off: (data.edit.off || []).map((x: string) => ids[x] || x) }
}
export function copy(ids: string[]) {
  const set = new Set(ids)
  if (!set.size) return 0
  clip = {
    nodes: GE.nodes.filter((n) => set.has(n.id)).map((n) => ({ id: n.id, position: { ...n.position }, data: JSON.parse(JSON.stringify(n.data)) })),
    edges: GE.edges.filter((e) => set.has(e.source) && set.has(e.target)).map((e) => ({ source: e.source, sourceHandle: e.sourceHandle, target: e.target, targetHandle: e.targetHandle })),
  }
  pastes = 0
  return set.size
}
export function paste(): string[] {
  if (!clip?.nodes.length) return []
  pastes += 1
  const ids: Record<string, string> = Object.fromEntries(clip.nodes.map((n) => [n.id, uid()]))
  const nodes: Node[] = clip.nodes.map((n) => {
    const data = JSON.parse(JSON.stringify(n.data))
    if (data.t === 'join') data.order = (data.order || []).map((x: string) => ids[x] || x)
    if (data.t === 'montage') remapMontage(data, ids)
    return { id: ids[n.id], type: data.t === 'group' ? 'ggroup' : 'gnode', position: { x: n.position.x + 60 * pastes, y: n.position.y + 60 * pastes }, data,
      zIndex: data.t === 'group' ? -1 : undefined }
  })
  GE.nodes = [...GE.nodes, ...nodes]
  GE.edges = [...GE.edges, ...clip.edges.map((e) => edgeFlow({ ...e, id: uid(), source: ids[e.source], target: ids[e.target] }))]
  touch(150)
  return nodes.map((n) => n.id)
}

// a node at a place, with the data a new node of its type starts with
export function addNode(t: string, x: number, y: number, data: Record<string, any> = {}) {
  const base: Record<string, any> = {
    scene: { takes: [rseed()], take: 0 }, output: { output: { size: '1080p', hdr: false, fps48: false } },
    picture: { seed: rseed() }, writer: { seconds: 15, mode: 'auto', mood: 'cinematic live-action film', music: '', ref_photo: false },
    lora: { items: [] }, join: { order: [] }, group: { title: tr('nodes.title.group'), w: 720, h: 420 }, note: { text: '' },
    frame: { at: 'last' }, sound: { voice: true }, v2v: { strength: 1, guide: 1, seed: rseed() }, facefix: { mode: 'far', strength: 1, seed: rseed() }, music: { volume: 0.9, scene_volume: 0.3, offset: 0, fade_in: 0.5, fade_out: 2 },
  }
  // a free spot: down from where it was asked for, past the nodes it would lie on (a group's frame doesn't count)
  if (t !== 'group') {
    const busy = (yy: number) => GE.nodes.some((m) => tOf(m) !== 'group' && Math.abs(m.position.x - x) < 260 && Math.abs(m.position.y - yy) < 200)
    for (let k = 0; k < 40 && busy(y); k++) y += 110
  }
  const n: Node = { id: uid(), type: t === 'group' ? 'ggroup' : 'gnode', position: { x, y }, data: { ...(base[t] || {}), ...data, t }, zIndex: t === 'group' ? -1 : undefined }
  GE.nodes = [...GE.nodes, n]
  GE.sel = n.id
  touch(200)
  return n
}

// a link, if the ports fit: the same type; a single input loses its old link; a join remembers the order
export function canLink(c: { source: string; sourceHandle?: string | null; target: string; targetHandle?: string | null }) {
  const s = nodeOf(c.source), t = nodeOf(c.target)
  if (!s || !t || s === t || !c.sourceHandle || !c.targetHandle) return false
  const out = GE.types[tOf(s)]?.out[c.sourceHandle], inp = GE.types[tOf(t)]?.in[c.targetHandle]
  if (tOf(t) === 'picture' && c.targetHandle === 'ref' && (t.data as any).model !== 'flux2') return false   // Krea 2 reads no pictures
  return !!out && !!inp && out === inp.type
}
export function link(c: { source: string; sourceHandle?: string | null; target: string; targetHandle?: string | null }) {
  if (!canLink(c)) return
  const t = nodeOf(c.target)!, inp = GE.types[tOf(t)].in[c.targetHandle!]
  let edges = GE.edges
  if (!inp.multi) edges = edges.filter((e) => !(e.target === c.target && e.targetHandle === c.targetHandle))
  if (edges.some((e) => e.source === c.source && e.sourceHandle === c.sourceHandle && e.target === c.target && e.targetHandle === c.targetHandle)) return
  GE.edges = [...edges, edgeFlow({ id: uid(), ...c })]
  if (tOf(t) === 'join') { const d = t.data as any; d.order = [...(d.order || []).filter((x: string) => x !== c.source), c.source] }
  touch(150)
}
export function removeNodes(ids: string[]) {
  const gone = new Set(ids)
  GE.nodes = GE.nodes.filter((n) => !gone.has(n.id))
  GE.edges = GE.edges.filter((e) => !gone.has(e.source) && !gone.has(e.target))
  for (const n of GE.nodes) if (tOf(n) === 'join') (n.data as any).order = ((n.data as any).order || []).filter((x: string) => !gone.has(x))
  if (GE.sel && gone.has(GE.sel)) GE.sel = null
  touch(150)
}
export const inputsOf = (id: string, port: string) => GE.edges.filter((e) => e.target === id && e.targetHandle === port)
// a scene's LoRA by reference (app/v2v.py profiles: it reads a clip or a photo + a voice) among its «LoRA» nodes' items
export const refLoraOf = (id: string) => {
  for (const e of inputsOf(id, 'lora')) {
    for (const u of ((nodeOf(e.source)?.data as any)?.items || []) as { id: string }[]) {
      const l = S.loras.find((x) => x.id === u.id)
      if (l?.v2v) return l
    }
  }
  return null
}
export const ENGINE_NAME: Record<string, string> = { h3: 'H3 Ref2VA', ltx23: 'LTX 2.3', ltx25: 'LTX 2.5' }

// «Дублировать ветку»: the node and everything after it, with the links into the branch from outside - a second
// ending, a short version; the copies sit under the originals
export function duplicateBranch(id: string) {
  const branch = new Set([id])
  let grew = true
  while (grew) {
    grew = false
    for (const e of GE.edges) if (branch.has(e.source) && !branch.has(e.target)) { branch.add(e.target); grew = true }
  }
  // the prompts of the copied scenes come along, so the copy's text is edited apart from the original's
  for (const e of GE.edges) {
    const src = nodeOf(e.source)
    if (branch.has(e.target) && e.targetHandle === 'prompt' && src && tOf(src) === 'prompt') branch.add(e.source)
  }
  const nodes = GE.nodes.filter((n) => branch.has(n.id))
  const ys = nodes.map((n) => n.position.y), dy = Math.max(...ys) - Math.min(...ys) + 320
  const ids: Record<string, string> = Object.fromEntries(nodes.map((n) => [n.id, uid()]))
  const copies = nodes.map((n) => {
    const data = JSON.parse(JSON.stringify(n.data))
    if (data.t === 'join') data.order = (data.order || []).map((x: string) => ids[x] || x)
    if (data.t === 'montage') remapMontage(data, ids)
    if (data.title && n.id === id) data.title = `${data.title} · ${tr('nodes.copy')}`
    return { ...n, id: ids[n.id], position: { x: n.position.x, y: n.position.y + dy }, data, selected: false }
  })
  const edges = GE.edges.filter((e) => branch.has(e.target)).map((e) => edgeFlow({ ...e, id: uid(), source: ids[e.source] || e.source, target: ids[e.target] }))
  GE.nodes = [...GE.nodes, ...copies]
  GE.edges = [...GE.edges, ...edges]
  GE.sel = ids[id]
  touch(150)
}

// a template's nodes at a place (new ids)
export function insert(t: { nodes: any[]; edges: any[] }, x: number, y: number) {
  const ids: Record<string, string> = Object.fromEntries(t.nodes.map((n) => [n.id, uid()]))
  const minX = Math.min(...t.nodes.map((n) => n.position.x)), minY = Math.min(...t.nodes.map((n) => n.position.y))
  const nodes: Node[] = t.nodes.map((n) => {
    const data = JSON.parse(JSON.stringify(n.data || {}))
    if (n.type === 'join') data.order = (data.order || []).map((s: string) => ids[s] || s)
    if (n.type === 'montage') remapMontage(data, ids)
    if (n.type === 'scene') { data.takes = (data.takes?.length ? data.takes : [0]).map(() => rseed()); data.take = 0 }
    return { id: ids[n.id], type: n.type === 'group' ? 'ggroup' : 'gnode', position: { x: x + n.position.x - minX, y: y + n.position.y - minY }, data: { ...data, t: n.type },
      zIndex: n.type === 'group' ? -1 : undefined }
  })
  GE.nodes = [...GE.nodes, ...nodes]
  GE.edges = [...GE.edges, ...t.edges.filter((e) => ids[e.source] && ids[e.target]).map((e) => edgeFlow({ ...e, id: uid(), source: ids[e.source], target: ids[e.target] }))]
  touch(150)
  return nodes.map((n) => n.id)
}

// the server's actions
export async function runTo(targets: string[] = [], quality?: string) {
  await flush()
  try { S.jobs = [...S.jobs, await post(`/api/projects/${GE.id}/nodes/run`, { targets, quality: quality || null })] }
  catch (e) { banner((e as Error).message) }
}
export async function runLlm(ids: string[]) {
  await flush()
  try { S.jobs = [...S.jobs, await post(`/api/projects/${GE.id}/nodes/llm`, { ids, model: S.llm || null })] }
  catch (e) { banner((e as Error).message) }
}
export async function expand(id: string) {
  await flush()
  try { toFlow(await post(`/api/projects/${GE.id}/nodes/expand`, { node: id })); await loadState() }
  catch (e) { banner((e as Error).message) }
}
export async function upload(file: File, kind: 'image' | 'audio') {
  const fd = new FormData()
  fd.append('file', file)
  return api<{ file: string; name: string }>(`/api/projects/${GE.id}/nodes/upload?kind=${kind}`, { method: 'POST', body: fd })
}
