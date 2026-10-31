// A tile's corner: dragging it sets the node's own width and height (data.w / data.h, in the graph's units, saved
// with the graph); a double click on it returns the tile to its usual size. The groups keep their panel fields too.
import { useVueFlow } from '@vue-flow/core'
import { GE, touch } from '../../lib/graphDoc'

export const NODE_MIN = { w: 180, h: 90 }, NODE_MAX = { w: 1200, h: 1600 }

export function useResize(id: () => string, min = NODE_MIN, max = NODE_MAX) {
  const { viewport } = useVueFlow('h3-graph-edit')
  function start(e: PointerEvent) {
    const n = GE.nodes.find((x) => x.id === id())
    if (!n || e.button !== 0) return
    e.preventDefault(); e.stopPropagation()
    const el = e.currentTarget as HTMLElement, tile = el.parentElement as HTMLElement
    const d = n.data as Record<string, any>
    const w0 = d.w || tile.offsetWidth, h0 = d.h || tile.offsetHeight, x0 = e.clientX, y0 = e.clientY
    const clamp = (v: number, lo: number, hi: number) => Math.round(Math.min(hi, Math.max(lo, v)))
    const move = (ev: PointerEvent) => {
      const z = viewport.value.zoom || 1
      d.w = clamp(w0 + (ev.clientX - x0) / z, min.w, max.w)
      d.h = clamp(h0 + (ev.clientY - y0) / z, min.h, max.h)
    }
    const stop = () => { el.releasePointerCapture(e.pointerId); el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', stop); el.removeEventListener('pointercancel', stop); touch(300) }
    el.setPointerCapture(e.pointerId)
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', stop)
    el.addEventListener('pointercancel', stop)
  }
  function reset(e: Event) {
    e.stopPropagation()
    const n = GE.nodes.find((x) => x.id === id())
    if (!n) return
    const d = n.data as Record<string, any>
    delete d.w; delete d.h
    touch()
  }
  return { start, reset }
}
