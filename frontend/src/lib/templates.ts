// Graph templates as files: the JSON a template is saved to and loaded from, the way a template is drawn small.
// The server keeps them (app/graph_templates - built in, data/graph_templates - the user's) and checks a loaded one
// like any graph: unknown node types and links between ports of other types are dropped.
import { api, post } from './api'
import { t } from '../i18n'

export const FORMAT = 'h3studio-graph-template'
export interface Tpl { id: string; name: string; about: string; own: boolean; nodes: any[]; edges: any[]; saved?: number | null }

// what a node is, for the picture: who works (the canvas's header colours)
const WHO_OF: Record<string, string> = { idea: 'user', hero: 'writer', writer: 'writer', prompt: 'user', photo: 'user', picture: 'krea', scene: 'h3',
  frame: 'ffmpeg', lora: 'user', join: 'ffmpeg', track: 'user', music: 'ffmpeg', output: 'ffmpeg', note: 'note', group: 'group' }
const COLOR: Record<string, string> = { h3: '#a855f7', writer: '#22c55e', ffmpeg: '#378ADD', krea: '#f59e0b', user: '#8a8a9b', note: '#b59a3a', group: '#3a3a48' }
const SIZE = (t: string) => (t === 'scene' ? [240, 220] : t === 'group' ? [0, 0] : [240, 130])

// a template drawn small: its nodes in place, coloured by who works, its links as lines
export function preview(t: { nodes: any[]; edges: any[] }, W = 300, H = 120) {
  const nodes = t.nodes.map((n) => {
    const [w, h] = n.type === 'group' ? [n.data?.w || 720, n.data?.h || 420] : SIZE(n.type)
    return { id: n.id, type: n.type, x: n.position.x, y: n.position.y, w, h }
  })
  if (!nodes.length) return { view: `0 0 ${W} ${H}`, rects: [], lines: [] }
  const x0 = Math.min(...nodes.map((n) => n.x)), y0 = Math.min(...nodes.map((n) => n.y))
  const x1 = Math.max(...nodes.map((n) => n.x + n.w)), y1 = Math.max(...nodes.map((n) => n.y + n.h))
  const k = Math.min((W - 12) / (x1 - x0 || 1), (H - 12) / (y1 - y0 || 1), 0.2)   // one node stays a node, not the whole picture
  const ox = (W - (x1 - x0) * k) / 2, oy = (H - (y1 - y0) * k) / 2
  interface Box { x: number; y: number; w: number; h: number; type: string }
  const at: Record<string, Box> = Object.fromEntries(nodes.map((n) => [n.id, { x: ox + (n.x - x0) * k, y: oy + (n.y - y0) * k, w: n.w * k, h: n.h * k, type: n.type }]))
  const rects = Object.values(at).map((r) => ({ ...r, fill: COLOR[WHO_OF[r.type] || 'user'] }))
  const lines = t.edges.filter((e) => at[e.source] && at[e.target]).map((e) => {
    const a = at[e.source], b = at[e.target], x1_ = a.x + a.w, y1_ = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2, d = Math.max(8, (x2 - x1_) / 2)
    return `M${x1_.toFixed(1)} ${y1_.toFixed(1)} C${(x1_ + d).toFixed(1)} ${y1_.toFixed(1)} ${(x2 - d).toFixed(1)} ${y2.toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}`
  })
  return { view: `0 0 ${W} ${H}`, rects, lines }
}

export function summary(tp: { nodes: any[]; edges?: any[] }) {
  const c = (type: string) => tp.nodes.filter((n) => n.type === type).length
  const parts: string[] = []
  const s = c('scene'), o = c('output')
  if (s) parts.push(t('shelf.tpl.scenes', s))
  if (o) parts.push(t('shelf.tpl.outputs', o))
  if (c('writer')) parts.push(t('shelf.tpl.writer'))
  if (c('picture')) parts.push('Krea 2')
  if (c('track')) parts.push(t('shelf.tpl.track'))
  if (tp.nodes.some((n) => n.type === 'hero') && tp.edges?.some?.((e: any) => e.targetHandle === 'faces')) parts.push('Ref2VA')
  return parts.join(' · ')
}

// a node's data without what belongs to its project: files, the writer's result
const KEEP_OUT = ['file', 'photo', 'plan', 'sig', 'from', 'scene']
export function portable(nodes: any[], edges: any[]) {
  const ids = new Set(nodes.map((n) => n.id))
  return {
    nodes: nodes.map((n) => ({ id: n.id, type: n.type, position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
      data: Object.fromEntries(Object.entries(n.data || {}).filter(([k]) => !KEEP_OUT.includes(k))) })),
    edges: edges.filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({ id: e.id, source: e.source, sourceHandle: e.sourceHandle, target: e.target, targetHandle: e.targetHandle })),
  }
}

// a template into a file the browser saves
export function download(name: string, about: string, nodes: any[], edges: any[]) {
  const body = { format: FORMAT, version: 1, name, about, ...portable(nodes, edges) }
  const blob = new Blob([JSON.stringify(body, null, 1)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${(name || t('shelf.tpl.file')).replace(/[\\/:*?"<>|]+/g, ' ').trim()}.json`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

// a file the user picked -> a saved template. Takes our format, a project's graph.json and a built-in template file.
export async function load(file: File): Promise<Tpl & { dropped?: { nodes: number; edges: number } }> {
  let d: any
  try { d = JSON.parse(await file.text()) } catch { throw new Error(t('shelf.tpl.notJson', { name: file.name })) }
  if (!d || !Array.isArray(d.nodes) || (d.edges && !Array.isArray(d.edges))) throw new Error(t('shelf.tpl.notTemplate', { name: file.name }))
  if (d.format && d.format !== FORMAT) throw new Error(t('shelf.tpl.otherFormat', { name: file.name, format: d.format }))
  const name = String(d.name || file.name.replace(/\.json$/i, '')).slice(0, 80)
  return post('/api/graph/templates', { name, about: String(d.about || '').slice(0, 300), nodes: d.nodes, edges: d.edges || [], replace: false })
}

export const list = () => api<Tpl[]>('/api/graph/templates')
