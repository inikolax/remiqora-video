<script setup lang="ts">
// The montage's timeline, after Remiqora's DAW lanes: a ruler (a click or a drag moves the playhead), the video
// lane (each clip a strip of its shot's frame, trimmed by its edges - the clips after it close up, the player shows
// the frame at the cut; dragged by its body, a clip carries its whole chain to another place), the scenes' sound
// that goes with them (its waveform), the music lane (your track from its offset, its fades), the sounds from
// files (dragged anywhere in time, trimmed by their edges); «Поверх», «Музыка» and «Звуки» a thin line while empty («Поверх» then says what it is for). Over each join, its seam: a mark of what the join is
// (without a seam, a jump, a cut, a dissolve, through black) - a click selects it for the panel, a double click plays
// it. Ctrl + wheel - zoom around the pointer, the wheel - along the time.
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import WaveBars from './WaveBars.vue'
import { ED, OVL, SEAM, SEAM_ICON, SEAM_NAME, SND, TR_NAME, addOverlay, chainsOf, fileUrl, moveChain, seamKind, snapT, tc, touch, trim, trimOverlay, xn, type Clip, type Overlay, type Sound } from '../../lib/edit'
import { chainColor } from '../../lib/consts'
import { dec, mmss } from '../../lib/format'

const props = defineProps<{ pid: string }>()
const { t } = useI18n()
const emit = defineEmits<{ addTrack: []; addSound: [] }>()
const scroller = ref<HTMLElement | null>(null)
const HEAD = 100                         // the lanes' names on the left
const end = computed(() => Math.max(ED.duration, ...ED.sounds.map((x) => x.start + x.out - x.in)))
const W = computed(() => Math.max(end.value * ED.px + 160, 600))
const x = (t: number) => t * ED.px
const url = (f: string | null) => fileUrl(f)
const track = computed(() => ED.view?.track || null)
const musicEnd = computed(() => (track.value ? Math.min(ED.duration, Math.max(0, (track.value.duration || 0) - (track.value.offset || 0))) : 0))

// the ruler's marks: a step that keeps them ~70 px apart
const step = computed(() => [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300].find((s) => s * ED.px >= 70) || 600)
const marks = computed(() => { const out: number[] = []; for (let t = 0; t <= end.value + step.value; t += step.value) out.push(+t.toFixed(2)); return out })
const label = (x: number) => (x >= 60 ? mmss(x) : t('edit.secs', { s: dec(x) }))

// zoom: fit the whole montage at first; Ctrl + wheel around the pointer
function fit() {
  const w = (scroller.value?.clientWidth || 900) - HEAD - 24
  ED.px = Math.max(4, Math.min(160, w / Math.max(1, end.value)))
}
onMounted(() => nextTick(fit))
watch(() => ED.view?.sig, (_, old) => { if (!old) nextTick(fit) })
function wheel(e: WheelEvent) {
  const el = scroller.value!
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    const r = el.getBoundingClientRect(), tAt = (el.scrollLeft + e.clientX - r.left - HEAD) / ED.px
    ED.px = Math.max(4, Math.min(240, ED.px * (e.deltaY < 0 ? 1.15 : 1 / 1.15)))
    nextTick(() => { el.scrollLeft = tAt * ED.px - (e.clientX - r.left - HEAD) })
  } else if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { e.preventDefault(); el.scrollLeft += e.deltaY }
}
// the playhead stays in sight while it plays
watch(() => ED.t, (t) => {
  const el = scroller.value
  if (!el || !ED.playing) return
  const px = x(t) + HEAD
  if (px > el.scrollLeft + el.clientWidth - 40 || px < el.scrollLeft + HEAD) el.scrollLeft = px - HEAD - 40
})

// a time under the pointer
function tOf(e: PointerEvent) {
  const el = scroller.value!, r = el.getBoundingClientRect()
  return Math.max(0, Math.min(end.value, (el.scrollLeft + e.clientX - r.left - HEAD) / ED.px))
}
function seek(e: PointerEvent) {
  if (e.button !== 0) return
  const seekTo = (ev: PointerEvent) => { ED.t = Math.min(ED.duration, tOf(ev)); ED.seekRev++ }
  seekTo(e)
  const move = (ev: PointerEvent) => seekTo(ev)
  addEventListener('pointermove', move)
  addEventListener('pointerup', () => removeEventListener('pointermove', move), { once: true })
}

// a clip: its edges trim (in its shot, at its speed), its body moves its chain; a click selects
const drop = ref<{ chain: number | null; x: number } | null>(null)
function clipDown(e: PointerEvent, c: Clip) {
  if (e.button !== 0) return
  // While playing, a gesture on a clip scrubs the playhead instead of moving the clip.
  if (ED.playing) {
    e.preventDefault()
    e.stopPropagation()
    const seekTo = (ev: PointerEvent) => { ED.t = Math.min(ED.duration, tOf(ev)); ED.seekRev++ }
    seekTo(e)
    const move = (ev: PointerEvent) => seekTo(ev)
    const up = () => removeEventListener('pointermove', move)
    addEventListener('pointermove', move)
    addEventListener('pointerup', up, { once: true })
    return
  }
  e.preventDefault()
  e.stopPropagation()
  const edge = (e.target as HTMLElement).dataset.edge as 'in' | 'out' | undefined
  const x0 = e.clientX, v0 = edge ? c[edge] : 0
  let moved = false
  const move = (ev: PointerEvent) => {
    if (!moved && Math.abs(ev.clientX - x0) < 4) return
    moved = true
    if (edge) {   // the left edge takes from the start of the shot, the right one from its end
      let v = v0 + ((ev.clientX - x0) / ED.px) * c.speed
      // the magnet: the clip's end (the cut after it) on the nearest beat
      const endAt = c.start + (edge === 'out' ? v - c.in : c.out - v) / c.speed, b = snapT(endAt)
      if (b !== endAt) v = edge === 'out' ? c.in + (b - c.start) * c.speed : c.out - (b - c.start) * c.speed
      trim(c, edge, v)
      ED.t = edge === 'in' ? c.start + 0.001 : c.start + c.dur - 0.001
    } else drop.value = target(tOf(ev), c.chain)
  }
  const up = () => {
    removeEventListener('pointermove', move)
    // a click selects; the playhead comes onto the clip (its colour on screen) only from outside it, so a cut
    // point set before is kept
    if (!moved) { ED.sel = c.id; if (ED.t < c.start - 1e-6 || ED.t >= c.start + c.dur) ED.t = c.start + 0.001 }
    else if (edge) touch(200)
    else if (drop.value) { const d = drop.value; drop.value = null; if (d.chain !== c.chain) moveChain(c.chain, d.chain) }
    drop.value = null
  }
  addEventListener('pointermove', move)
  addEventListener('pointerup', up, { once: true })
}
// where a chain dropped at time t lands: before the chain under the pointer (or the one after it, past its middle)
function target(t: number, own: number): { chain: number | null; x: number } {
  const order = chainsOf(ED.clips)
  const span = (ch: number) => { const cs = ED.clips.filter((c) => c.chain === ch); const l = cs[cs.length - 1]; return [cs[0].start, l.start + l.dur] }
  for (let i = 0; i < order.length; i++) {
    const [a, b] = span(order[i])
    if (t < b || i === order.length - 1) {
      const before = t < (a + b) / 2 ? order[i] : order[i + 1] ?? null
      const xx = before === null ? x(b) : x(span(before)[0])
      return { chain: before === own ? own : before, x: xx }
    }
  }
  return { chain: null, x: x(ED.duration) }
}
const chainStart = (c: Clip, k: number) => !k || ED.clips[k - 1].chain !== c.chain
const secs = (x: number) => t('edit.secs', { s: dec(Math.round(x * 10) / 10) })
// the seams: the join before each clip but the first, in the middle of a dissolve
const seams = computed(() => ED.clips.slice(1))
const seamTitle = (c: Clip) => t('edit.seamTitle', { name: SEAM_NAME[seamKind(c)], len: c.tr !== 'cut' ? ` ${secs(c.td)}` : '', clip: c.name })
const strip = (c: Clip) => (c.png ? { backgroundImage: `url(${url(c.png)})` } : {})

// an overlay («Поверх»): its body moves it in time (the magnet: its start on a beat), its edges trim it in its shot
function overDown(e: PointerEvent, o: Overlay) {
  if (e.button !== 0) return
  e.preventDefault()
  e.stopPropagation()
  const edge = (e.target as HTMLElement).dataset.edge as 'in' | 'out' | undefined
  const x0 = e.clientX, v0 = { start: o.start, in: o.in, out: o.out }
  let moved = false
  const move = (ev: PointerEvent) => {
    if (!moved && Math.abs(ev.clientX - x0) < 4) return
    moved = true
    const d = (ev.clientX - x0) / ED.px
    if (edge === 'in') { o.start = v0.start; o.in = v0.in; trimOverlay(o, 'in', v0.in + d) }
    else if (edge === 'out') trimOverlay(o, 'out', v0.out + d)
    else { o.start = Math.max(0, snapT(v0.start + d)); trimOverlay(o, 'out', o.out) }
    ED.t = edge === 'out' ? o.start + o.dur - 0.001 : o.start + 0.001
  }
  const up = () => { removeEventListener('pointermove', move); if (!moved) { ED.sel = OVL + o.id; ED.t = o.start + 0.001 } else touch(200) }
  addEventListener('pointermove', move)
  addEventListener('pointerup', up, { once: true })
}

// a sound: its body moves it in time, its edges trim it; a click selects
function soundDown(e: PointerEvent, s: Sound) {
  if (e.button !== 0) return
  e.preventDefault()
  e.stopPropagation()
  const edge = (e.target as HTMLElement).dataset.edge as 'in' | 'out' | undefined
  const x0 = e.clientX, v0 = { start: s.start, in: s.in, out: s.out }
  let moved = false
  const move = (ev: PointerEvent) => {
    if (!moved && Math.abs(ev.clientX - x0) < 4) return
    moved = true
    const d = (ev.clientX - x0) / ED.px
    if (edge === 'in') { const v = Math.min(Math.max(0, v0.in + d), s.out - 0.1); s.start = Math.max(0, v0.start + (v - v0.in)); s.in = +v.toFixed(3) }
    else if (edge === 'out') s.out = +Math.max(s.in + 0.1, Math.min(s.length, v0.out + d)).toFixed(3)
    else s.start = +Math.max(0, snapT(v0.start + d)).toFixed(3)
  }
  const up = () => { removeEventListener('pointermove', move); if (!moved) ED.sel = SND + s.id; else touch(200) }
  addEventListener('pointermove', move)
  addEventListener('pointerup', up, { once: true })
}
</script>

<template>
  <div ref="scroller" class="et" @wheel="wheel">
    <div class="et-in" :style="{ width: `${W + HEAD}px` }">
      <!-- the ruler -->
      <div class="et-row et-ruler" @pointerdown="seek">
        <div class="et-head">{{ t('edit.time') }}</div>
        <div class="et-lane"><span v-for="m in marks" :key="m" class="et-mark" :style="{ left: `${x(m)}px` }">{{ label(m) }}</span>
          <template v-if="ED.magnet && ED.beats.length && ED.px * 60 / (ED.bpm || 120) >= 5">
            <i v-for="b in ED.beats" :key="'b' + b" class="et-beat" :class="{ bar: ED.bars.includes(b) }" :style="{ left: `${x(b)}px` }" /></template></div>
      </div>
      <!-- «Поверх»: pieces of shots over the video, their picture only -->
      <div class="et-row et-over" :class="{ empty: !ED.overlays.length }">
        <div class="et-head"><Icon name="layers" :size="14" />{{ t('edit.overLane') }}</div>
        <div class="et-lane" @pointerdown="seek">
          <div v-for="o in ED.overlays" :key="o.id" class="et-ov" :class="{ sel: ED.sel === OVL + o.id, miss: !o.file }"
            :style="{ left: `${x(o.start)}px`, width: `${Math.max(10, x(o.dur))}px` }" :title="t('edit.overTitle', { name: o.name, t: tc(o.start), len: secs(o.dur) })"
            @pointerdown="overDown($event, o)">
            <div class="et-strip" :style="o.png ? { backgroundImage: `url(${url(o.png)})` } : {}" />
            <span class="et-cap"><b>{{ o.index + 1 }}</b><span v-if="x(o.dur) > 70">{{ o.take !== null ? t('edit.takeMark') : '' }} {{ o.name }}</span></span>
            <i data-edge="in" class="et-edge l" :title="t('edit.trimIn')" />
            <i data-edge="out" class="et-edge r" :title="t('edit.trimOut')" />
          </div>
          <button type="button" class="ghost et-add" :style="{ left: `${x(ED.t) + 8}px` }" :title="t('edit.addOverTitle')" @pointerdown.stop @click="addOverlay()"><Icon name="plus" :size="14" />{{ ED.overlays.length ? t('edit.addOver') : t('edit.addOverEmpty') }}</button>
        </div>
      </div>
      <!-- the video -->
      <div class="et-row et-video">
        <div class="et-head"><Icon name="film" :size="14" />{{ t('edit.videoLane') }}</div>
        <div class="et-lane" @pointerdown="seek">
          <div v-for="(c, k) in ED.clips" :key="c.id" class="et-clip" :class="{ sel: ED.sel === c.id, miss: !c.file, chain0: chainStart(c, k), scopeScene: ED.colorScope === 'scene' && ED.colorSceneId === c.scene }"
            :style="{ left: `${x(c.start)}px`, width: `${Math.max(6, x(c.dur))}px`, '--cc': chainColor(c.chain), zIndex: k + 1 }"
            :title="t('edit.clipTitle', { name: c.name, a: tc(c.in), b: tc(c.out), len: tc(c.length) }) + (c.speed !== 1 ? ` · ${xn(c.speed)}` : '')" @pointerdown="clipDown($event, c)" @dblclick.stop="ED.t = c.start + 0.001">
            <div class="et-strip" :style="strip(c)" />
            <span class="et-cap"><b>{{ c.index + 1 }}</b><span v-if="x(c.dur) > 84">{{ c.name }}</span><small v-if="x(c.dur) > 48">{{ secs(c.dur) }}</small></span>
            <span v-if="c.speed !== 1" class="et-speed">{{ xn(c.speed) }}</span>
            <span v-if="c.color || ED.sceneColors[c.scene]" class="et-color-mark" :title="t(ED.sceneColors[c.scene] ? 'edit.sceneColorMark' : 'edit.clipColorMark')">◐</span>
            <span v-if="c.take !== null" class="et-take" :title="t('edit.otherTake')">{{ t('edit.takeMark') }}</span>
            <span v-if="!c.file" class="et-note">{{ t('edit.notShot') }}</span>
            <span v-if="c.tr !== 'cut'" class="et-tr" :class="c.tr" :style="{ width: `${x(c.td)}px` }" :title="`${TR_NAME[c.tr]} ${t('edit.secs', { s: dec(c.td) })}`" />
            <i data-edge="in" class="et-edge l" :class="{ cut: c.in > (c.kind === 'continue' ? 0.05 : 0.01) }" :title="t('edit.trimIn')" />
            <i data-edge="out" class="et-edge r" :class="{ cut: c.out < c.length - 0.01 }" :title="t('edit.trimOut')" />
          </div>
          <button v-for="c in seams" :key="SEAM + c.id" type="button" class="et-seam" :class="[`s-${seamKind(c)}`, { sel: ED.sel === SEAM + c.id }]"
            :style="{ left: `${x(c.start + c.td / 2)}px`, '--cc': chainColor(c.chain) }" :aria-label="seamTitle(c)" :title="seamTitle(c)"
            @pointerdown.stop @click="ED.sel = SEAM + c.id" @dblclick.stop="ED.cue = Math.max(0, c.start - 1.5)"><Icon :name="SEAM_ICON[seamKind(c)]" :size="12" /></button>
          <div v-if="drop" class="et-drop" :style="{ left: `${drop.x}px` }" />
        </div>
      </div>
      <!-- the scenes' sound goes with them -->
      <div class="et-row et-audio">
        <div class="et-head"><Icon name="volume" :size="14" />{{ t('edit.sceneSound') }}</div>
        <div class="et-lane" @pointerdown="seek">
          <div v-for="(c, k) in ED.clips" :key="c.id" class="et-snd" :class="{ sel: ED.sel === c.id }"
            :style="{ left: `${x(c.start)}px`, width: `${Math.max(6, x(c.dur))}px`, zIndex: k + 1 }" @pointerdown.stop="ED.sel = c.id">
            <WaveBars v-if="c.file && x(c.dur) > 8" :pid="pid" :file="c.file" :from="c.in" :to="c.out" :width="x(c.dur)" :height="22" color="rgba(120,180,255,.75)" />
            <span v-if="c.vol !== 1" class="et-vol">{{ Math.round(c.vol * 100) }}%</span>
          </div>
          <span v-if="track" class="et-level">{{ Math.round((track.scene_volume ?? 0.3) * 100) }}%</span>
        </div>
      </div>
      <!-- the music -->
      <div class="et-row et-music" :class="{ empty: !track }">
        <div class="et-head"><Icon name="music" :size="14" />{{ t('edit.music') }}</div>
        <div class="et-lane" @pointerdown="seek">
          <div v-if="track" class="et-mus" :class="{ sel: ED.sel === 'music' }" :style="{ left: '0px', width: `${Math.max(20, x(musicEnd))}px` }"
            :title="t('edit.trackFrom', { name: track.name, s: dec(track.offset || 0) })" @pointerdown.stop="ED.sel = 'music'">
            <WaveBars :pid="pid" :file="track.file" :from="track.offset || 0" :to="(track.offset || 0) + musicEnd" :width="Math.max(20, x(musicEnd))" :height="28" color="rgba(234,179,8,.6)" />
            <span class="et-fade in" :style="{ width: `${x(track.fade_in || 0)}px` }" />
            <span class="et-fade out" :style="{ width: `${x(Math.min(musicEnd, track.fade_out || 0))}px` }" />
            <b>{{ track.name }}</b><small>{{ Math.round((track.volume ?? 0.9) * 100) }}%{{ ED.duck ? t('edit.ducks', { n: Math.round(ED.duck * 100) }) : '' }}</small>
          </div>
          <span v-else-if="ED.view?.kind === 'graph'" class="et-note-lane">{{ t('edit.graphTrack') }}</span>
          <button v-else type="button" class="ghost et-add" @pointerdown.stop @click="emit('addTrack')"><Icon name="plus" :size="14" />{{ t('edit.ownTrack') }}</button>
        </div>
      </div>
      <!-- the sounds from files -->
      <div class="et-row et-sounds" :class="{ empty: !ED.sounds.length }">
        <div class="et-head"><Icon name="volume" :size="14" />{{ t('edit.sounds') }}</div>
        <div class="et-lane" @pointerdown="seek">
          <div v-for="s in ED.sounds" :key="s.id" class="et-sfx" :class="{ sel: ED.sel === SND + s.id }"
            :style="{ left: `${x(s.start)}px`, width: `${Math.max(10, x(s.out - s.in))}px` }" :title="t('edit.soundAt', { name: s.name, t: tc(s.start) })"
            @pointerdown="soundDown($event, s)">
            <WaveBars :pid="pid" :file="s.file" :from="s.in" :to="s.out" :width="Math.max(10, x(s.out - s.in))" :height="26" color="rgba(52,211,153,.7)" />
            <b>{{ s.name }}</b>
            <i data-edge="in" class="et-edge l" :title="t('edit.trimIn')" />
            <i data-edge="out" class="et-edge r" :title="t('edit.trimOut')" />
          </div>
          <button type="button" class="ghost et-add" :style="{ left: `${ED.sounds.length ? Math.max(...ED.sounds.map((s) => x(s.start + s.out - s.in))) + 8 : 8}px` }" @pointerdown.stop @click="emit('addSound')"><Icon name="plus" :size="14" />{{ t('edit.sound') }}</button>
        </div>
      </div>
      <div class="et-play" :style="{ left: `${HEAD + x(ED.t)}px` }"><i /></div>
    </div>
  </div>
</template>
