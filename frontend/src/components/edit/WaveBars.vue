<script setup lang="ts">
// The waveform of a piece of a file (a shot's sound, a sound, the track) on a lane: its loudness 50 times a second
// from the server (app/edit.py peaks, kept next to the file), drawn as bars from `from` to `to` seconds of it -
// at `speed` a second of the lane holds `speed` seconds of the file.
import { onMounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ pid: string; file: string; from: number; to: number; width: number; height: number; color?: string }>(), { color: 'rgba(255,255,255,.55)' })
const cv = ref<HTMLCanvasElement | null>(null)
const cache = (window as any).__h3peaks || ((window as any).__h3peaks = new Map<string, Promise<{ rate: number; peaks: number[] }>>())
function load(f: string): Promise<{ rate: number; peaks: number[] }> {
  const k = `${props.pid}/${f}`
  // a shot in another project's cache ("@<project>/scenes/…"): that project's peaks
  const [pid, file] = f.startsWith('@') ? [f.slice(1).split('/')[0], f.slice(1).split('/').slice(1).join('/')] : [props.pid, f]
  if (!cache.has(k)) cache.set(k, fetch(`/api/projects/${pid}/peaks?file=${encodeURIComponent(file)}`).then((r) => (r.ok ? r.json() : { rate: 50, peaks: [] })).catch(() => ({ rate: 50, peaks: [] })))
  return cache.get(k)!
}
async function draw() {
  const c = cv.value
  if (!c || props.width < 2) return
  const { rate, peaks } = await load(props.file)
  const dpr = devicePixelRatio || 1, w = Math.round(props.width), h = props.height
  c.width = w * dpr; c.height = h * dpr
  c.style.width = `${w}px`; c.style.height = `${h}px`
  const g = c.getContext('2d')!
  g.scale(dpr, dpr)
  g.clearRect(0, 0, w, h)
  g.fillStyle = props.color
  const a = props.from * rate, b = props.to * rate, per = (b - a) / w
  for (let x = 0; x < w; x += 2) {
    let m = 0
    for (let i = Math.floor(a + x * per); i < Math.floor(a + (x + 2) * per) && i < peaks.length; i++) m = Math.max(m, peaks[i] || 0)
    const bh = Math.max(1, (m / 255) * h)
    g.fillRect(x, (h - bh) / 2, 1.4, bh)
  }
}
onMounted(draw)
watch(() => [props.file, props.from, props.to, Math.round(props.width), props.height], draw)
</script>

<template><canvas ref="cv" class="wave" aria-hidden="true" /></template>
