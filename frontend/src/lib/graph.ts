// Phase 9, G1: the storyboard as a graph, to look at. The nodes and links come from the plan and from the server's
// /graph (who is in a scene, whose photos Ref2VA gets, what a scene starts from - prompts.py's rules, not the page's).
// Layout: the people, the style and LoRA on the left; the scenes in rows, a chain to a row (a long chain wraps every
// ROW scenes, as text does); the assembly, the music and the output on the right.
// Ports are typed: look (a person's or the world's text), image (a photo or a last frame),
// clip (a shot), video. The header's colour says who does the work, as in the status strip.
import type { Edge, Node } from '@vue-flow/core'
import { castName } from './board'
import { chainColor } from './consts'
import type { Project } from './types'
import { t } from '../i18n'

export interface Rect { x: number; y: number; width: number; height: number }
export interface SceneLink { index: number; written: boolean; start: 'prev' | 'photo' | null; from?: number | null; who: number[]; refs: number[] }
export interface Port { id: string; label: string; type: string }
export interface InfoData { icon: string; title: string; sub?: string; text?: string; img?: string | null; who: 'h3' | 'writer' | 'ffmpeg' | 'user'
  inputs?: Port[]; outputs?: Port[]; note?: string }

export const SCENE_W = 236, SCENE_H = 228, GAP_X = 104, GAP_Y = 56, ROW = 6
const LEFT_X = 0, PHOTO_X = 330, SCENE_X = 660, SIDE_H = 250

export const WHO_COLOR: Record<InfoData['who'], string> = { h3: 'var(--accent)', writer: 'var(--ok)', ffmpeg: '#378ADD', user: 'var(--faint)' }
// read through t() when read (the interface's language): a getter each, enumerable for a v-for
export const WHO_NAME = {} as Record<InfoData['who'], string>
for (const k of ['h3', 'writer', 'ffmpeg', 'user'] as const) Object.defineProperty(WHO_NAME, k, { get: () => t(`graph.whoView.${k}`), enumerable: true })
export const PORT_COLOR: Record<string, string> = { look: 'var(--ok)', image: 'var(--soft)', face: '#eab308', clip: '#378ADD', video: '#378ADD' }

const sceneCol = (r: number) => SCENE_X + r * (SCENE_W + GAP_X)

export function build(proj: Project, links: SceneLink[]): { nodes: Node[]; edges: Edge[]; rows: number; top: Rect; all: Rect } {
  const plan = proj.plan!, st = proj.settings, nodes: Node[] = [], edges: Edge[] = []
  const people = plan.mode !== 'none', cast = (plan.cast || []) as Record<string, any>[]
  const fileUrl = (name: string) => `/api/projects/${proj.id}/files/${encodeURIComponent(name)}`
  const castPhoto = (c: Record<string, any>) => (c.photo ? fileUrl(c.photo) : c.from_photo && st.photo ? `/api/projects/${proj.id}/photo` : null)

  // the scenes: a row per chain, wrapped every ROW scenes
  let row = -1, col = 0, cols = 1
  const pos: { x: number; y: number }[] = []
  for (const s of plan.scenes) {
    if (s.kind === 'new' || row < 0 || col === ROW) { row += 1; col = 0 }
    pos.push({ x: sceneCol(col), y: row * (SCENE_H + GAP_Y) })
    col += 1
    cols = Math.max(cols, col)
  }
  const rows = row + 1
  plan.scenes.forEach((_s, i) => nodes.push({ id: `scene-${i}`, type: 'scene', position: pos[i], data: { index: i }, draggable: false, connectable: false }))

  // the left column: the people (or the world), the style, LoRA
  let y = 0
  const left = (id: string, data: InfoData, h = SIDE_H) => { nodes.push({ id, type: 'info', position: { x: LEFT_X, y }, data, draggable: false, connectable: false }); y += h }
  if (people) {
    cast.forEach((c, k) => left(`hero-${k}`, { icon: 'user', title: cast.length > 1 ? castName(c, k) : t('graph.hero'), who: 'writer', img: castPhoto(c),
      text: c.ru || '', sub: c.from_photo ? t('graph.fromPhoto') : '',
      outputs: [{ id: 'look', label: t('graph.look'), type: 'look' }, ...(castPhoto(c) ? [{ id: 'photo', label: t('graph.photo'), type: 'face' }] : [])] }, 280))
  } else {
    left('world', { icon: 'layers', title: t('graph.world'), who: 'writer', text: plan.world?.ru || '', outputs: [{ id: 'look', label: t('graph.worldPort'), type: 'look' }] })
  }
  if (plan.style_en) left('style', { icon: 'spark', title: t('graph.style'), who: 'writer', text: plan.style_en, note: t('graph.everyScene') }, 200)
  const loras = (st.loras || []) as Record<string, any>[]
  if (loras.length) left('lora', { icon: 'layers', title: 'LoRA', who: 'user', text: loras.map((l) => `${String(l.id).split(/[\\/]/).pop()} · ${l.strength}`).join('\n'), note: t('graph.allScenes') }, 180)

  // what each scene is made of
  const link = (id: string, source: string, sourceHandle: string, target: string, targetHandle: string, type: string, extra: Partial<Edge> = {}) =>
    edges.push({ id, source, sourceHandle, target, targetHandle, data: { type }, class: `e-${type}`, ...extra } as Edge)
  links.forEach((l) => {
    const i = l.index, s = plan.scenes[i]
    if (!s) return
    if (l.start === 'prev' && i > 0) {   // from the scene before it, or from any earlier one («с кадра сцены N»)
      const f = l.from ?? i - 1, wraps = pos[i].y !== pos[f].y || f !== i - 1
      link(`f${i}`, `scene-${f}`, 'frame', `scene-${i}`, 'start', 'frame', { type: wraps ? 'smoothstep' : 'default', style: { stroke: chainColor(s.chain) } })
    } else if (l.start === 'photo') {
      nodes.push({ id: `photo-${i}`, type: 'info', position: { x: PHOTO_X, y: pos[i].y }, draggable: false, connectable: false,
        data: { icon: 'image', title: t('graph.scenePhoto', { n: i + 1 }), who: 'user', img: fileUrl(s.start_photo), outputs: [{ id: 'image', label: t('graph.frame'), type: 'image' }] } as InfoData })
      link(`p${i}`, `photo-${i}`, 'image', `scene-${i}`, 'start', 'image')
    }
    // the look: where a chain opens, and where a continuation changes who is in it
    const prevWho = i > 0 ? links[i - 1]?.who.join() : null
    if (s.kind === 'new' || l.who.join() !== prevWho) {
      if (people) l.who.forEach((k) => link(`w${i}-${k}`, `hero-${k}`, 'look', `scene-${i}`, 'who', 'look'))
      else link(`w${i}`, 'world', 'look', `scene-${i}`, 'who', 'look')
    }
    l.refs.forEach((k) => link(`r${i}-${k}`, `hero-${k}`, 'photo', `scene-${i}`, 'faces', 'face'))
    link(`c${i}`, `scene-${i}`, 'clip', 'join', 'clips', 'clip')
  })

  // the right column: the assembly, the music, the output
  const rx = sceneCol(cols) + 40, track = st.track
  nodes.push({ id: 'join', type: 'info', position: { x: rx, y: 0 }, draggable: false, connectable: false,
    data: { icon: 'film', title: t('graph.join'), who: 'ffmpeg', text: t('graph.joinText'),
      inputs: [{ id: 'clips', label: t('graph.scenesPort'), type: 'clip' }], outputs: [{ id: 'video', label: t('graph.videoPort'), type: 'video' }] } as InfoData })
  let last = 'join'
  if (track) {
    nodes.push({ id: 'music', type: 'info', position: { x: rx, y: 230 }, draggable: false, connectable: false,
      data: { icon: 'music', title: t('graph.music'), who: 'ffmpeg', sub: track.name, text: t('graph.musicText', { a: Math.round((track.volume ?? 0.9) * 100), b: Math.round((track.scene_volume ?? 0.3) * 100) }),
        inputs: [{ id: 'video', label: t('graph.videoPort'), type: 'video' }], outputs: [{ id: 'video', label: t('graph.withSound'), type: 'video' }] } as InfoData })
    link('jm', 'join', 'video', 'music', 'video', 'video')
    last = 'music'
  }
  nodes.push({ id: 'out', type: 'info', position: { x: rx, y: track ? 460 : 230 }, draggable: false, connectable: false,
    data: { icon: 'download', title: t('graph.output'), who: 'ffmpeg', inputs: [{ id: 'video', label: t('graph.videoPort'), type: 'video' }] } as InfoData })
  link('o', last, 'video', 'out', 'video', 'video')
  // rectangles from the known sizes: the canvas draws only the nodes on screen, and a node it has not drawn has no
  // size, so its own fitView would leave it out. `top` - what a long video opens on: the first rows, what they are
  // made of and where the shots go
  const all = bounds(nodes), top = { ...all, height: Math.min(all.height, 3 * (SCENE_H + GAP_Y) + 40) }
  return { nodes, edges, rows, top, all }
}

function bounds(nodes: Node[]): Rect {
  const xs = nodes.map((n) => n.position.x), ys = nodes.map((n) => n.position.y)
  const x = Math.min(...xs) - 70, y = Math.min(...ys) - 20   // 70: the port labels left of the left column
  return { x, y, width: Math.max(...xs) + SCENE_W + 140 - x, height: Math.max(...ys) + 300 - y }
}

// the nodes a node is linked with, for lighting its links up
export function neighbours(edges: Edge[], id: string) {
  const out = new Set<string>([id])
  for (const e of edges) if (e.source === id || e.target === id) { out.add(e.source); out.add(e.target) }
  return out
}
