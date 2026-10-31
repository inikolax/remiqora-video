<script setup lang="ts">
// The video's track under the board: every scene as wide as its time, a chain's scenes close together, the selected
// one outlined, picked ones tinted, a scene not shot yet hatched. When the video does not fit the width with a scene
// at 65 px at least, the track has two floors: on top the whole video as a strip of episodes with a frame round the
// part shown, below that part big with its episodes named. The part follows the selected scene; the wheel over the
// track, the ‹ › at its edges (shown while there is more that way) or a drag of the frame on the strip shows another
// part without selecting anything, a click on the strip selects the scene there. A click selects (Ctrl / Shift pick
// several), a double click opens the scene on the whole page. Under the contact sheet (mini) the track is only its
// map: the episodes as a strip, the selected one framed; a click or a drag goes to the scene at that point.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import { P } from '../../lib/project'
import { episodes, isPicked, lenOf, pickScene, shotPng, startOf } from '../../lib/board'
import { chainColor } from '../../lib/consts'
import { mmss } from '../../lib/format'
import type { Plan } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan; mini?: boolean }>()
const emit = defineEmits<{ open: [i: number] }>()
const box = ref<HTMLElement | null>(null)
const width = ref(1000)
let ro: ResizeObserver | null = null
onMounted(() => { if (box.value) { ro = new ResizeObserver(([e]) => { width.value = e.contentRect.width }); ro.observe(box.value) } })
onBeforeUnmount(() => ro?.disconnect())

const MIN = 13   // px a second: a 5 s scene is 65 px - its number and a picture
const eps = computed(() => episodes(props.p))
const total = computed(() => Math.max(1, ...props.p.scenes.map((s) => startOf(s) + lenOf(s))))
const fits = computed(() => width.value / total.value >= MIN)
const pps = computed(() => (fits.value ? width.value / total.value : MIN))
const span = computed(() => width.value / pps.value)
const sel = computed(() => props.p.scenes[P.sel] || props.p.scenes[0])
// the part shown: round the selected scene, or where the wheel or the strip moved it (until another scene is selected)
const off = ref<number | null>(null)
watch(() => P.sel, () => { off.value = null })
const clampFrom = (x: number) => Math.max(0, Math.min(total.value - span.value, x))
const from = computed(() => (fits.value ? 0 : clampFrom(off.value ?? startOf(sel.value) + lenOf(sel.value) / 2 - span.value / 2)))
const atStart = computed(() => from.value <= 0.01)
const atEnd = computed(() => from.value >= total.value - span.value - 0.01)
const page = (dir: number) => { off.value = clampFrom(from.value + dir * span.value * 0.8) }
function wheel(e: WheelEvent) {
  if (fits.value || props.mini) return
  e.preventDefault()
  off.value = clampFrom(from.value + (Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY) / pps.value)
}
// the map's frame: the part shown, or - the map alone - the selected scene's episode
const selEp = computed(() => eps.value.find((e) => e.scenes.some((x) => x.index === sel.value.index)) || eps.value[0])
const win = computed(() => (props.mini ? { a: selEp.value.start, w: selEp.value.end - selEp.value.start } : { a: from.value, w: span.value }))
const inView = (a: number, b: number) => b > from.value && a < from.value + span.value
const cells = computed(() => props.p.scenes.filter((s) => inView(startOf(s), startOf(s) + lenOf(s)))
  .map((s) => ({ s, left: (startOf(s) - from.value) * pps.value, w: Math.max(4, lenOf(s) * pps.value - 2), png: shotPng(s.index) })))
const labels = computed(() => eps.value.filter((e) => inView(e.start, e.end)).map((e) => ({ e, left: (e.start - from.value) * pps.value, w: (e.end - e.start) * pps.value - 2 })))
const short = (x: string) => x.split(/[.,;:—]/)[0].trim()
// the ruler: about six ticks on round seconds
const ticks = computed(() => {
  const step = [5, 10, 15, 20, 30, 60, 120, 300].find((x) => span.value / x <= 7) || 600
  const out: number[] = []
  for (let x = Math.ceil(from.value / step) * step; x <= from.value + span.value + 0.01; x += step) out.push(x)
  return out
})
const pickAt = (t: number) => {
  const s = props.p.scenes.find((x) => t >= startOf(x) && t < startOf(x) + lenOf(x)) || props.p.scenes[props.p.scenes.length - 1]
  if (s.index !== P.sel) pickScene(s.index)
}
// the strip: dragged, the part shown follows the pointer; a plain click selects the scene there
function stripDown(e: PointerEvent) {
  if (e.button !== 0) return
  const el = e.currentTarget as HTMLElement, r = el.getBoundingClientRect(), x0 = e.clientX
  const at = (x: number) => (x - r.left) / r.width * total.value
  let moved = false
  const move = (ev: PointerEvent) => {
    if (!moved && Math.abs(ev.clientX - x0) < 4) return
    moved = true
    if (props.mini) pickAt(at(ev.clientX)); else off.value = clampFrom(at(ev.clientX) - span.value / 2)
  }
  const up = (ev: PointerEvent) => {
    removeEventListener('pointermove', move)
    if (!moved) pickAt(at(ev.clientX))
  }
  addEventListener('pointermove', move)
  addEventListener('pointerup', up, { once: true })
}
</script>

<template>
  <section ref="box" class="bt" :class="{ mini }" :aria-label="t('board.track.label')" @wheel="wheel">
    <template v-if="mini">
      <div class="bt-ov bt-map" role="button" tabindex="-1" :title="t('board.track.mapTitle')" @pointerdown="stripDown">
        <i v-for="e in eps" :key="e.n" :style="{ flexGrow: e.end - e.start, '--c': chainColor(e.chain) }" :class="{ on: e.chain === sel.chain }" />
        <span class="bt-win" :style="{ left: `${(win.a / total) * 100}%`, width: `${(win.w / total) * 100}%` }" />
      </div>
      <div class="bt-ovr"><span>0:00</span><span>{{ t('board.track.mapSeen', { n: selEp.n, a: mmss(selEp.start), b: mmss(selEp.end) }) }} · <i>{{ t('board.track.mapHow') }}</i></span><span>{{ mmss(total) }}</span></div>
    </template>
    <template v-else-if="!fits">
      <div class="bt-ov" role="button" tabindex="-1" :title="t('board.track.overview')" @pointerdown="stripDown">
        <i v-for="e in eps" :key="e.n" :style="{ flexGrow: e.end - e.start, '--c': chainColor(e.chain) }" :class="{ on: e.chain === sel.chain }" />
        <span class="bt-win" :style="{ left: `${(win.a / total) * 100}%`, width: `${(win.w / total) * 100}%` }" />
      </div>
      <div class="bt-ovr"><span>0:00</span><span>{{ t('board.track.seen', { a: mmss(from), b: mmss(Math.min(total, from + span)) }) }} · <i>{{ t('board.track.how') }}</i></span><span>{{ mmss(total) }}</span></div>
      <div class="bt-eps">
        <span v-for="l in labels" :key="l.e.n" :style="{ left: `${l.left}px`, width: `${l.w}px`, '--c': chainColor(l.e.chain) }" :title="l.e.about">
          {{ t('board.script.episode', { n: l.e.n }) }}<template v-if="l.w > 120"> · {{ short(l.e.about) }}</template></span>
      </div>
    </template>
    <div v-if="!mini" class="bt-row">
      <button v-if="!fits && !atStart" type="button" class="bt-page l" :aria-label="t('board.track.back')" :title="t('board.track.back')" @click="page(-1)"><Icon name="back" :size="18" /></button>
      <button v-if="!fits && !atEnd" type="button" class="bt-page r" :aria-label="t('board.track.next')" :title="t('board.track.next')" @click="page(1)"><Icon name="forward" :size="18" /></button>
      <button v-for="c in cells" :key="c.s.index" type="button" class="bt-cell" :class="{ on: c.s.index === P.sel, pick: isPicked(c.s.index), raw: !c.png }"
        :style="{ left: `${c.left}px`, width: `${c.w}px`, '--c': chainColor(c.s.chain) }" :title="`${c.s.index + 1} · ${mmss(startOf(c.s))} · ${c.s.ru || ''}`"
        @click="pickScene(c.s.index, $event)" @dblclick="emit('open', c.s.index)">
        <img v-if="c.png && c.w > 18" :src="c.png" alt=""><b v-if="c.w > 22">{{ c.s.index + 1 }}</b></button>
    </div>
    <div v-if="!mini" class="bt-ruler"><span v-for="x in ticks" :key="x" :style="{ left: `${(x - from) * pps}px` }">{{ mmss(x) }}</span></div>
  </section>
</template>
