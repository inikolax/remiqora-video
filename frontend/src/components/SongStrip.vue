<script setup lang="ts">
// Phase 11: a song as a clip sees it - its loudness, its parts (quiet or loud, the chorus found from the repeated
// lines), the sung lines, and the stretch the clip takes. On the home screen a click on it moves the stretch (to the
// nearest bar); on the storyboard it shows the scenes' cuts on the bars, the selected scene lit. `head` - where the
// song is playing now (a line over the wave); while it plays, a click inside the stretch seeks there («seek»).
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Song } from '../lib/types'
import { mmss } from '../lib/format'

const { t } = useI18n()
const props = defineProps<{ song: Song; from?: number; to?: number; cuts?: number[]; sel?: number; editable?: boolean; zoom?: boolean; head?: number | null }>()
const emit = defineEmits<{ pick: [t: number]; seek: [t: number]; scene: [i: number] }>()
const box = ref<HTMLElement | null>(null)
const cv = ref<HTMLCanvasElement | null>(null)
const W = ref(600)
const H = 64
// the view: the whole song, or (zoom) the clip's stretch
const v0 = computed(() => (props.zoom && props.from != null ? props.from : 0))
const v1 = computed(() => (props.zoom && props.to != null ? props.to : props.song.duration))
const x = (t: number) => ((t - v0.value) / Math.max(0.01, v1.value - v0.value)) * W.value
const PART = ['intro', 'groove', 'break', 'drop', 'outro', 'chorus']
const peak = computed(() => Math.max(0.01, ...props.song.sections.map((s) => s.energy)))
const loud = (s: { kind: string; energy: number }) => s.kind === 'drop' || s.energy >= 0.8 * peak.value
const inChorus = (a: number, b: number) => props.song.chorus.some(([ca, cb]) => Math.min(b, cb) - Math.max(a, ca) > 0.5 * (b - a))
const parts = computed(() => props.song.sections.filter((s) => s.end > v0.value && s.start < v1.value)
  .map((s) => ({ ...s, l: x(Math.max(s.start, v0.value)), w: x(Math.min(s.end, v1.value)) - x(Math.max(s.start, v0.value)), loud: loud(s),
    name: inChorus(s.start, s.end) ? t('idea.part.chorus') : PART.includes(s.kind) ? t(`idea.part.${s.kind}`) : s.kind })))
const chorus = computed(() => props.song.chorus.filter(([a, b]) => b > v0.value && a < v1.value).map(([a, b]) => ({ l: x(Math.max(a, v0.value)), w: x(Math.min(b, v1.value)) - x(Math.max(a, v0.value)) })))
const lines = computed(() => props.song.lines.filter((l) => l.end > v0.value && l.start < v1.value)
  .map((l) => ({ ...l, l: x(Math.max(l.start, v0.value)), w: Math.max(3, x(Math.min(l.end, v1.value)) - x(Math.max(l.start, v0.value))) })))
const cutsX = computed(() => (props.cuts || []).map((t, i) => ({ i, l: x(t), w: x((props.cuts || [])[i + 1] ?? (props.to ?? props.song.duration)) - x(t) })))

function draw() {
  const c = cv.value
  if (!c) return
  const dpr = devicePixelRatio || 1, w = Math.round(W.value)
  c.width = w * dpr; c.height = H * dpr
  c.style.width = `${w}px`; c.style.height = `${H}px`
  const g = c.getContext('2d')!
  g.scale(dpr, dpr)
  g.clearRect(0, 0, w, H)
  const rate = 50, pk = props.song.peaks, a = v0.value * rate, per = ((v1.value - v0.value) * rate) / w
  const on = (t: number) => props.from == null || (t >= props.from && t <= (props.to ?? Infinity))
  for (let px = 0; px < w; px += 3) {
    let m = 0
    for (let i = Math.floor(a + px * per); i < Math.floor(a + (px + 3) * per) && i < pk.length; i++) m = Math.max(m, pk[i] || 0)
    const bh = Math.max(1.5, (m / 255) * (H - 10))
    g.fillStyle = on(v0.value + px * per / rate) ? 'rgba(236,228,250,.78)' : 'rgba(154,154,171,.32)'
    g.fillRect(px, (H - bh) / 2, 2, bh)
  }
}
let ro: ResizeObserver | null = null
onMounted(() => {
  ro = new ResizeObserver(() => { W.value = box.value?.clientWidth || 600; draw() })
  if (box.value) ro.observe(box.value)
})
onUnmounted(() => ro?.disconnect())
watch(() => [props.song.id, props.from, props.to, props.zoom, W.value], draw)

function click(e: MouseEvent) {
  if (!props.editable || !box.value) return
  const r = box.value.getBoundingClientRect()
  const t = v0.value + ((e.clientX - r.left) / r.width) * (v1.value - v0.value)
  if (props.head != null && props.from != null && t >= props.from && t <= (props.to ?? props.song.duration)) { emit('seek', t); return }
  const bar = props.song.bars.reduce((best, b) => (Math.abs(b - t) < Math.abs(best - t) ? b : best), props.song.bars[0] ?? 0)
  emit('pick', bar)
}
</script>

<template>
  <div class="song-strip" :class="{ editable }">
    <div ref="box" class="ss-wave" :title="editable ? t('idea.clip.clickTitle') : undefined" @click="click">
      <div class="ss-parts" aria-hidden="true">
        <span v-for="(p, i) in parts" :key="i" class="ss-part" :class="{ loud: p.loud }" :style="{ left: p.l + 'px', width: p.w + 'px' }" />
        <span v-for="(c, i) in chorus" :key="'c' + i" class="ss-chorus" :style="{ left: c.l + 'px', width: c.w + 'px' }" />
      </div>
      <canvas ref="cv" />
      <span v-if="from != null && !zoom" class="ss-pick" :style="{ left: x(from) + 'px', width: x(to ?? song.duration) - x(from) + 'px' }" />
      <i v-if="head != null" class="ss-head" :style="{ left: x(head) + 'px' }" />
      <button v-for="c in cutsX" :key="c.i" type="button" class="ss-cut" :class="{ sel: c.i === sel }" :style="{ left: c.l + 'px', width: c.w + 'px' }"
        :aria-label="t('idea.sceneN', { n: c.i + 1 })" @click.stop="emit('scene', c.i)" />
    </div>
    <div class="ss-lanes" :style="{ width: W + 'px' }">
      <span v-for="(p, i) in parts" :key="i" class="ss-name" :style="{ left: p.l + 'px', maxWidth: p.w + 'px' }">{{ p.name }}</span>
    </div>
    <div v-if="lines.length" class="ss-lines" :style="{ width: W + 'px' }" aria-hidden="true">
      <span v-for="(l, i) in lines" :key="i" class="ss-line" :style="{ left: l.l + 'px', width: l.w + 'px' }" :title="`${mmss(l.start)} · ${l.text}`" />
    </div>
  </div>
</template>
