<script setup lang="ts">
// The montage played in the browser, as near to what «Собрать ролик» makes as a browser gets: two <video> taking
// turns (the next clip waits loaded on the other one, so a cut has no pause), a dissolve by their opacity, through
// black by both fading on the black stage; a clip's speed is the video's rate; the scenes' sound at its level and
// the clip's, the track on an <audio> from its offset with its fades, each sound from a file on an <audio> of its
// own where it stands. The clock is the playing video itself (its time in the shot -> the timeline), so the picture
// and the playhead never part; a scene not shot yet runs on the wall clock over a black frame. The track giving way
// to the scenes (ducking) is heard only in the built video.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ED, FLASH_S, at, colorSteps, fileUrl, gradeSteps, overlayAt, type ColorStep } from '../../lib/edit'

const props = defineProps<{ pid: string; aspect: string }>()
const { t } = useI18n()
const a = ref<HTMLVideoElement | null>(null)
const b = ref<HTMLVideoElement | null>(null)
const o = ref<HTMLVideoElement | null>(null)   // «Поверх»: the overlay on screen, silent, over both
const music = ref<HTMLAudioElement | null>(null)
const vid = (k: number) => (k % 2 ? b.value : a.value)
const url = (f: string) => (f.startsWith('@') ? fileUrl(f) : `/api/projects/${props.pid}/files/${encodeURIComponent(f).replace(/%2F/g, '/')}`)
const track = computed(() => ED.view?.track || null)
const sceneVol = computed(() => (track.value ? track.value.scene_volume ?? 0.3 : 1))
const volOf = (i: number, part = 1) => Math.max(0, Math.min(1, sceneVol.value * (ED.clips[i]?.vol ?? 1) * part))
const ratio = computed(() => props.aspect.replace(':', ' / '))
// the stage fits its box both ways (the screen's CSS: the box's width, or its height times this)
const ar = computed(() => { const [w, h] = props.aspect.split(':').map(Number); return w && h ? w / h : 16 / 9 })
// the clip on screen: its number and name over the picture
const now = computed(() => ED.clips[at(ED.t).k] || null)
// the colour, in the render's order: the clip's, its scene's, the video's look, the video's adjustment - an SVG
// filter on each <video> for the clip it holds now (a dissolve shows both, each in its own colour)
const held = ref<[number, number]>([-1, -1])
const uid = `ep${Math.random().toString(36).slice(2, 8)}`
const colorOf = (i: number): ColorStep[] => {
  const c = ED.clips[i]
  if (!c) return []
  return [...colorSteps(c.color), ...colorSteps(ED.sceneColors[c.scene]), ...gradeSteps(ED.look.grade), ...colorSteps(ED.look.color)]
}
// an overlay gets the video's look only (the render lays it before the look, after the clips' own colour)
const grades = computed(() => [...held.value.map(colorOf), [...gradeSteps(ED.look.grade), ...colorSteps(ED.look.color)]])
const filterOf = (n: number) => (grades.value[n].length && !ED.bare ? `url(#${uid}-${n})` : 'none')
// the finish over the stage: the vignette (a grade's own, or the slider's, the stronger), the grain as a still
// texture - the built video's grain moves; «До / после» held - none of it
const vignetteOp = computed(() => (ED.bare ? 0 : Math.max(ED.look.grade && ED.look.grade !== 'lut' ? 0.6 : 0, ED.look.vignette)))
const grainOp = computed(() => (ED.bare ? 0 : ED.look.grain * 0.35))
const overOn = ref(false)
// the overlay under the playhead: its piece of the shot at the timeline's time, playing with the rest
function syncOverlay(force = false) {
  const v = o.value, x = overlayAt(ED.t)
  overOn.value = !!x
  if (!v) return
  if (!x) { if (!v.paused) v.pause(); return }
  const f = x.file!
  if (v.dataset.f !== f) { v.src = url(f); v.dataset.f = f; v.load() }
  const local = x.in + (ED.t - x.start)
  if (force || !ED.playing || Math.abs(v.currentTime - local) > 0.12) v.currentTime = local
  if (ED.playing && v.paused) v.play().catch(() => {})
  else if (!ED.playing && !v.paused) v.pause()
}
// a flash cut (a clip's entry into a loud part): white over the first 4 frames, fading
const flash = computed(() => { const c = now.value; return c && c.tr === 'flash' ? Math.max(0, 1 - (ED.t - c.start) / FLASH_S) : 0 })

let k = 0, raf = 0, wall = 0, warm = false
const LEAD = 0.35, SLOW = 0.0625   // 0.35 s at 1/16 speed: under a frame of the next clip goes by before the join
const missing = ref<number | null>(null)   // a scene not shot yet is on screen: its number
const missingName = ref('')
const loading = ref(false)
let waitingFor: number | null = null, waitAt = 0
const hasFrame = (v: HTMLVideoElement | null) => !!v && v.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && v.videoWidth > 0

function load(i: number, local: number) {
  const c = ED.clips[i], v = vid(i)
  if (!c || !v) return
  if (!c.file) return
  if (v.dataset.f !== c.file) { v.src = url(c.file); v.dataset.f = c.file; v.load() }
  held.value[i % 2] = i
  if (Math.abs(v.currentTime - local) > 0.04) v.currentTime = local
}
function look(i: number, op: number, other = 0) {
  const v = vid(i), w = vid(i + 1)
  if (v) v.style.opacity = String(op)
  if (w) w.style.opacity = String(other)
}
function gain(t: number) {
  const tr = track.value
  if (!tr) return 0
  const fi = tr.fade_in || 0, fo = tr.fade_out || 0, d = ED.duration
  let g = Math.min(1, tr.volume ?? 0.9)
  if (fi > 0 && t < fi) g *= t / fi
  if (fo > 0 && t > d - fo) g *= Math.max(0, (d - t) / fo)
  return Math.max(0, Math.min(1, g))
}
// the sounds from files: one <audio> each, playing while the playhead is over it
const sfx = new Map<string, HTMLAudioElement>()
function syncSounds(force = false) {
  const live = new Set<string>()
  for (const x of ED.sounds) {
    live.add(x.id)
    let el = sfx.get(x.id)
    if (!el) { el = new Audio(url(x.file)); el.preload = 'auto'; sfx.set(x.id, el) }
    const local = ED.t - x.start, n = x.out - x.in
    if (ED.playing && local >= 0 && local < n) {
      if (force || Math.abs(el.currentTime - (x.in + local)) > 0.2) el.currentTime = x.in + local
      let g = x.vol
      if (x.fade_in > 0 && local < x.fade_in) g *= local / x.fade_in
      if (x.fade_out > 0 && local > n - x.fade_out) g *= Math.max(0, (n - local) / x.fade_out)
      el.volume = Math.max(0, Math.min(1, g))
      if (el.paused) el.play().catch(() => {})
    } else if (!el.paused) el.pause()
  }
  for (const [id, el] of sfx) if (!live.has(id)) { el.pause(); sfx.delete(id) }
}
function syncMusic(force = false) {
  const m = music.value, tr = track.value
  if (!m || !tr) return
  const target = (tr.offset || 0) + ED.t
  if (force || Math.abs(m.currentTime - target) > 0.4) m.currentTime = target
  m.volume = gain(ED.t)
}

// a still frame where the playhead stands
function show(t: number) {
  const p = at(t)
  k = p.k
  waitingFor = null
  const c = ED.clips[k]
  missing.value = c && !c.file ? c.index + 1 : null
  missingName.value = c && !c.file ? c.name : ''
  load(k, p.local)
  const active = vid(k)
  loading.value = !!c?.file && !hasFrame(active)
  if (loading.value && active) {
    const ready = () => { if (vid(k) === active && hasFrame(active)) loading.value = false }
    active.addEventListener('loadeddata', ready, { once: true })
    active.addEventListener('seeked', ready, { once: true })
  }
  look(k, 1, 0)
  warm = false
  ;[a.value, b.value].forEach((v) => { if (v) { v.pause(); v.playbackRate = 1 } })
  syncMusic(true)
  syncSounds(true)
  syncOverlay(true)
}

function play() {
  if (!ED.clips.length) return
  if (ED.t >= ED.duration - 0.05) ED.t = 0
  show(ED.t)
  ED.playing = true
  const v = vid(k)
  if (ED.clips[k].file && v) { v.volume = volOf(k); v.playbackRate = ED.clips[k].speed; v.play().catch(() => {}) }
  wall = performance.now()
  if (track.value && music.value) { syncMusic(true); music.value.play().catch(() => {}) }
  syncSounds(true)
  raf = requestAnimationFrame(tick)
}
function pause() {
  ED.playing = false
  cancelAnimationFrame(raf)
  ;[a.value, b.value, music.value, o.value].forEach((v) => v?.pause())
  syncSounds()
}
const toggle = () => (ED.playing ? pause() : play())

function tick(now: number) {
  if (!ED.playing) return
  const c = ED.clips[k], n = ED.clips[k + 1], v = vid(k)
  if (!c) { pause(); return }
  if (waitingFor !== null) {
    const incoming = vid(waitingFor)
    if (!hasFrame(incoming)) {
      ED.t = waitAt
      wall = now
      if (music.value && track.value) syncMusic()
      syncSounds()
      raf = requestAnimationFrame(tick)
      return
    }
    waitingFor = null
    loading.value = false
    if (v && c.file && waitAt < c.start + c.dur - 0.03) { v.playbackRate = c.speed; v.play().catch(() => {}) }
    const next = ED.clips[k + 1], nv = vid(k + 1)
    if (next?.file && nv) { nv.playbackRate = next.speed; nv.volume = 0; nv.play().catch(() => {}) }
    wall = now
    if (track.value && music.value) { syncMusic(true); music.value.play().catch(() => {}) }
    syncSounds(true)
  }
  // the clock: the video's own time, or the wall clock over a scene not shot
  const end = c.start + c.dur
  // a shot's last frame can come a moment before its length says: its end (or its trim) is the clip's end
  if (c.file && v) ED.t = v.ended || v.currentTime >= c.out - 0.02 ? end : c.start + (v.currentTime - c.in) / c.speed
  else ED.t += (now - wall) / 1000
  wall = now
  missing.value = c.file ? null : c.index + 1
  missingName.value = c.file ? '' : c.name
  if (n) {
    const nv = vid(k + 1)
    if (ED.t > n.start - 1.5 && nv && nv.paused && !warm) load(k + 1, n.in)
    // the next video starts a moment early, nearly still and silent: at the join its decoder is running already
    if (ED.t > n.start - LEAD && nv && n.file && !warm) { warm = true; nv.playbackRate = SLOW; nv.volume = 0; nv.play().catch(() => {}) }
    const transitionStarted = n.tr === 'cut' || n.tr === 'flash' ? ED.t >= n.start - 0.01 : ED.t >= n.start
    if (transitionStarted && n.file && !hasFrame(nv)) {
      // Keep the outgoing frame visible until the next decoder has produced a real frame.
      waitingFor = k + 1
      waitAt = ED.t
      loading.value = true
      look(k, 1, 0)
      v?.pause()
      nv?.pause()
      if (music.value) music.value.pause()
      for (const el of sfx.values()) el.pause()
      wall = now
      raf = requestAnimationFrame(tick)
      return
    }
    if (transitionStarted) {
      if (nv && nv.playbackRate !== n.speed) nv.playbackRate = n.speed
      if (n.tr === 'cut' || n.tr === 'flash' || ED.t >= end - 0.01) {   // ours is over: the next one is the clock now
        v?.pause()
        k += 1
        warm = false
        loading.value = false
        look(k, 1, 0)
        const w = vid(k)
        if (w) { w.volume = volOf(k); if (ED.clips[k]?.file && w.paused) w.play().catch(() => {}) }
        wall = now
      } else {                                        // a dissolve / through black: both on screen
        const p = Math.min(1, Math.max(0, (ED.t - n.start) / n.td))
        if (n.tr === 'fade') look(k, 1, p)
        else look(k, Math.max(0, 1 - 2 * p), Math.max(0, 2 * p - 1))
        if (v) v.volume = volOf(k, 1 - p)
        if (nv) nv.volume = volOf(k + 1, p)
      }
    }
  } else if (ED.t >= end - 0.01 || (v && v.ended)) {
    ED.t = ED.duration
    pause()
    return
  }
  if (music.value && track.value) syncMusic()
  syncSounds()
  syncOverlay()
  raf = requestAnimationFrame(tick)
}

// the playhead moved or the clips changed while paused: the still follows
let pending = 0
const shape = () => ED.clips.map((c) => `${c.id}${c.in}${c.out}${c.tr}${c.td}${c.speed}`).join() + ED.overlays.map((x) => `${x.id}${x.file}${x.start}${x.in}${x.out}`).join()
watch(() => [ED.t, shape()], () => {
  if (ED.playing) return
  cancelAnimationFrame(pending)
  pending = requestAnimationFrame(() => show(ED.t))
}, { immediate: true, flush: 'post' })
// A timeline gesture has its own revision; the playhead clock changing during playback does not trigger this.
watch(() => ED.seekRev, () => {
  if (!ED.playing) return
  const t = ED.t
  ;[a.value, b.value].forEach((v) => v?.pause())
  show(t)
  const next = ED.clips[k], v = vid(k)
  wall = performance.now()
  if (next?.file && v) { v.volume = volOf(k); v.playbackRate = next.speed; v.play().catch(() => {}) }
}, { flush: 'post' })
// a clip changed while it plays: start again from here
watch(shape, () => { if (ED.playing) { pause(); play() } })

onBeforeUnmount(() => { pause(); for (const el of sfx.values()) el.pause(); sfx.clear() })
defineExpose({ play, pause, toggle })
</script>

<template>
  <div class="ep-stage" :style="{ aspectRatio: ratio, '--ar': ar }" @click="toggle">
    <!-- the opacity is the player's (look()); bound here, a re-render would put it back -->
    <video ref="a" class="ep-v" :style="{ filter: filterOf(0) }" playsinline preload="auto" />
    <video ref="b" class="ep-v ep-v-b" :style="{ filter: filterOf(1) }" playsinline preload="auto" />
    <video ref="o" class="ep-v ep-v-o" :style="{ filter: filterOf(2), opacity: overOn ? 1 : 0 }" muted playsinline preload="auto" />
    <svg class="ep-defs" aria-hidden="true">
      <filter v-for="(g, n) in grades" :id="`${uid}-${n}`" :key="n" color-interpolation-filters="sRGB">
        <template v-for="(s, j) in g" :key="j">
          <feColorMatrix v-if="'matrix' in s" type="matrix" :values="s.matrix" />
          <feComponentTransfer v-else>
            <feFuncR type="linear" :slope="s.slope[0]" :intercept="s.intercept" />
            <feFuncG type="linear" :slope="s.slope[1]" :intercept="s.intercept" />
            <feFuncB type="linear" :slope="s.slope[2]" :intercept="s.intercept" />
          </feComponentTransfer>
        </template>
      </filter>
    </svg>
    <div v-if="vignetteOp" class="ep-vignette" :style="{ opacity: vignetteOp / 0.6 }" />
    <div v-if="grainOp" class="ep-grain" :style="{ opacity: grainOp }" />
    <audio v-if="track" ref="music" :src="url(track.file)" preload="auto" />
    <div v-if="loading && now?.file" class="ep-loading"><i />{{ t('edit.loadingFrame') }}</div>
    <div v-if="missing" class="ep-miss">{{ t('edit.notShotYet', { name: missingName || t('edit.sceneN', { n: missing }) }) }}</div>
    <div v-if="!ED.clips.length" class="ep-miss">{{ t('edit.noScenes') }}</div>
    <div v-if="flash > 0" class="ep-flash" :style="{ opacity: flash }" />
    <span v-if="now" class="ep-now"><b>{{ now.index + 1 }}</b>{{ now.name }}</span>
  </div>
</template>
