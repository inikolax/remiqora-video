// «Упорядочить»: the graph laid out by its flow, left to right. A node's column is how far down the flow it is, and
// a node that only feeds sits right before what it feeds (a track by its music, a LoRA by its scenes); the order in a
// column keeps the links short (barycenters, a few sweeps both ways). A group is laid out inside and placed as one
// block, its frame fitted to it; notes go in a row above. Only positions (and group frames) change - the save is an
// undo step like any edit, so Ctrl+Z brings the old layout back.
import type { Node } from '@vue-flow/core'
import { GE, insideGroup, nodeOf, tOf } from './graphDoc'

export interface Size { w: number; h: number }
interface Item { id: string; w: number; h: number; y0: number; t: string }
// the video's tail: what the scenes go into. The rest - the chains that make the scenes - is laid out chain by chain
const TAIL = new Set(['join', 'montage', 'music', 'track', 'output'])
const ONE_STACK = 3200   // a head taller than this is wrapped into several stacks, about a screen's proportion
type Pos = Map<string, { x: number; y: number }>
const GAP_X = 90, GAP_Y = 40, NOTE_GAP = 60
const PAD = { x: 32, top: 56, bottom: 32 }   // a group's frame around its nodes (its title takes the top)

// items with links between them -> their top-left corners, the block from 0,0; and its size
function layered(items: Item[], links: [string, string][]): { pos: Pos; w: number; h: number } {
  const pos: Pos = new Map()
  if (!items.length) return { pos, w: 0, h: 0 }
  const by = new Map(items.map((i) => [i.id, i]))
  const succ = new Map(items.map((i) => [i.id, new Set<string>()])), pred = new Map(items.map((i) => [i.id, new Set<string>()]))
  for (const [a, b] of links) if (a !== b && by.has(a) && by.has(b)) { succ.get(a)!.add(b); pred.get(b)!.add(a) }

  // the flow's order (Kahn, the upper first); a cycle's leftovers go last as they lie
  const indeg = new Map(items.map((i) => [i.id, pred.get(i.id)!.size]))
  const ready = items.filter((i) => !indeg.get(i.id)).sort((a, b) => a.y0 - b.y0).map((i) => i.id)
  const order: string[] = []
  while (ready.length) {
    const v = ready.shift()!
    order.push(v)
    for (const w of succ.get(v)!) { indeg.set(w, indeg.get(w)! - 1); if (!indeg.get(w)) ready.push(w) }
  }
  for (const i of [...items].sort((a, b) => a.y0 - b.y0)) if (!order.includes(i.id)) order.push(i.id)

  // columns: the longest way from a source; then a feeder moves right up to just before what it feeds
  const col = new Map<string, number>()
  for (const v of order) col.set(v, Math.max(0, ...[...pred.get(v)!].map((u) => (col.get(u) ?? -1) + 1)))
  for (const v of [...order].reverse()) {
    const next = [...succ.get(v)!].map((w) => col.get(w)!)
    if (next.length) col.set(v, Math.max(col.get(v)!, Math.min(...next) - 1))
  }
  const n = Math.max(...col.values()) + 1
  const cols: string[][] = Array.from({ length: n }, () => [])
  for (const i of [...items].sort((a, b) => a.y0 - b.y0)) cols[col.get(i.id)!].push(i.id)

  // the order in a column: where its links lead (their middle), a few sweeps right and left
  const mid = new Map<string, number>()
  const stack = (c: string[]) => { let y = 0; for (const id of c) { mid.set(id, y + by.get(id)!.h / 2); y += by.get(id)!.h + GAP_Y } }
  cols.forEach(stack)
  const sweep = (c: string[], near: Map<string, Set<string>>) => {
    const key = (id: string) => { const ys = [...near.get(id)!].map((x) => mid.get(x)!).filter((y) => y !== undefined); return ys.length ? ys.reduce((a, b) => a + b) / ys.length : mid.get(id)! }
    const keys = new Map(c.map((id) => [id, key(id)]))
    c.sort((a, b) => keys.get(a)! - keys.get(b)!)
    stack(c)
  }
  for (let k = 0; k < 4; k++) {
    for (let i = 1; i < n; i++) sweep(cols[i], pred)
    for (let i = n - 2; i >= 0; i--) sweep(cols[i], succ)
  }

  // the coordinates: columns as wide as their widest, each centred on the tallest
  const heights = cols.map((c) => c.reduce((a, id) => a + by.get(id)!.h, 0) + GAP_Y * Math.max(0, c.length - 1))
  const H = Math.max(...heights)
  let x = 0
  cols.forEach((c, i) => {
    let y = (H - heights[i]) / 2
    for (const id of c) { pos.set(id, { x, y }); y += by.get(id)!.h + GAP_Y }
    x += Math.max(...c.map((id) => by.get(id)!.w)) + GAP_X
  })
  return { pos, w: x - GAP_X, h: H }
}

// the flow of a block: the chains that make scenes (its head) each laid out on its own, stacked in the order they
// were and wrapped into columns when tall - a hundred scenes into one join made a tower before; the tail (join,
// montage, music, track, output) laid out to their right, in the middle
function flowLayout(items: Item[], links: [string, string][]): { pos: Pos; w: number; h: number } {
  const head = items.filter((i) => !TAIL.has(i.t)), tail = items.filter((i) => TAIL.has(i.t))
  // the head's chains: what is linked, the tail apart
  const root = new Map(head.map((i) => [i.id, i.id]))
  const find = (x: string): string => (root.get(x) === x ? x : (root.set(x, find(root.get(x)!)), root.get(x)!))
  for (const [a, b] of links) if (root.has(a) && root.has(b)) root.set(find(a), find(b))
  const chains = new Map<string, Item[]>()
  for (const i of head) { const r = find(i.id); chains.set(r, [...(chains.get(r) || []), i]) }
  if (!tail.length || chains.size < 2) return layered(items, links)

  const parts = [...chains.values()].map((c) => ({ y0: Math.min(...c.map((i) => i.y0)), ...layered(c, links) })).sort((a, b) => a.y0 - b.y0)
  const total = parts.reduce((a, p) => a + p.h, 0) + GAP_Y * (parts.length - 1)
  const area = parts.reduce((a, p) => a + (p.w + GAP_X) * (p.h + GAP_Y), 0)
  const maxH = total <= ONE_STACK ? total : Math.max(...parts.map((p) => p.h), Math.sqrt((area * 9) / 16))
  const pos: Pos = new Map()
  let x = 0, y = 0, colW = 0, H = 0
  for (const p of parts) {
    if (y > 0 && y + p.h > maxH) { x += colW + GAP_X * 1.5; y = 0; colW = 0 }
    for (const [id, q] of p.pos) pos.set(id, { x: x + q.x, y: y + q.y })
    y += p.h + GAP_Y; colW = Math.max(colW, p.w); H = Math.max(H, y - GAP_Y)
  }
  const headW = x + colW
  const t = layered(tail, links)
  const tx = headW + GAP_X * 2, ty = Math.max(0, (H - t.h) / 2)
  for (const [id, q] of t.pos) pos.set(id, { x: tx + q.x, y: ty + q.y })
  return { pos, w: tx + t.w, h: Math.max(H, t.h) }
}

// a block of nodes: its notes in a row on top, the rest laid out by their links under them
function block(items: Item[], notes: Item[], links: [string, string][]): { pos: Pos; w: number; h: number } {
  const flow = flowLayout(items, links)
  const pos: Pos = new Map()
  let x = 0, top = 0
  for (const t of notes) { pos.set(t.id, { x, y: 0 }); x += t.w + GAP_Y; top = Math.max(top, t.h) }
  const dy = notes.length ? top + NOTE_GAP : 0
  for (const [id, p] of flow.pos) pos.set(id, { x: p.x, y: p.y + dy })
  return { pos, w: Math.max(flow.w, x - GAP_Y), h: dy + flow.h }
}

// lay out these nodes (a selection; null - the whole graph). sizeOf: a node's drawn size. -> how many moved
export function arrange(ids: string[] | null, sizeOf: (id: string) => Size): number {
  const scope = (ids ? ids.map((id) => nodeOf(id)).filter(Boolean) as Node[] : GE.nodes)
  if (scope.length < 2) return 0
  const inScope = new Set(scope.map((n) => n.id))
  const item = (n: Node): Item => { const s = sizeOf(n.id); return { id: n.id, w: s.w, h: s.h, y0: n.position.y, t: tOf(n) } }
  const groups = scope.filter((n) => tOf(n) === 'group')
  // a node in two frames belongs to the smaller one
  const owner = new Map<string, Node>()
  const area = (g: Node) => ((g.data as any).w || 720) * ((g.data as any).h || 420)
  for (const g of [...groups].sort((a, b) => area(b) - area(a))) for (const m of insideGroup(g)) if (inScope.has(m.id) && tOf(m) !== 'group') owner.set(m.id, g)
  const top = (id: string) => owner.get(id)?.id ?? id   // what a node is in the outer layout: itself or its group
  const links: [string, string][] = GE.edges.filter((e) => inScope.has(e.source) && inScope.has(e.target)).map((e) => [e.source, e.target])

  // each group with nodes: laid out inside, the frame around it
  const inner = new Map<string, { pos: Pos; w: number; h: number }>()
  for (const g of groups) {
    const ms = scope.filter((n) => owner.get(n.id) === g)
    if (!ms.length) continue
    inner.set(g.id, block(ms.filter((n) => tOf(n) !== 'note').map(item), ms.filter((n) => tOf(n) === 'note').map(item), links))
  }
  // the outer layout: the free nodes, and each group as one block
  const outer: Item[] = [], notes: Item[] = []
  for (const n of scope) {
    if (owner.has(n.id)) continue
    if (tOf(n) === 'group') {
      const b = inner.get(n.id), d = n.data as any
      outer.push({ id: n.id, w: b ? b.w + 2 * PAD.x : d.w || 720, h: b ? b.h + PAD.top + PAD.bottom : d.h || 420, y0: n.position.y, t: 'group' })
    } else (tOf(n) === 'note' ? notes : outer).push(item(n))
  }
  const outerLinks = links.map(([a, b]) => [top(a), top(b)] as [string, string])
  const all = block(outer, notes, outerLinks)

  // where the block goes: where the nodes were (their top-left corner)
  const x0 = Math.min(...scope.map((n) => n.position.x)), y0 = Math.min(...scope.map((n) => n.position.y))
  let moved = 0
  const put = (n: Node, x: number, y: number) => {
    x = Math.round(x); y = Math.round(y)
    if (n.position.x !== x || n.position.y !== y) { n.position = { x, y }; moved++ }
  }
  for (const n of scope) {
    if (owner.has(n.id)) continue
    const p = all.pos.get(n.id)
    if (!p) continue
    put(n, x0 + p.x, y0 + p.y)
    const b = inner.get(n.id)
    if (b) {
      const d = n.data as any
      d.w = Math.round(b.w + 2 * PAD.x)
      d.h = Math.round(b.h + PAD.top + PAD.bottom)
      for (const m of scope) if (owner.get(m.id) === n) { const q = b.pos.get(m.id)!; put(m, x0 + p.x + PAD.x + q.x, y0 + p.y + PAD.top + q.y) }
    }
  }
  return moved
}
