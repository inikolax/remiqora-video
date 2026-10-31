<script setup lang="ts">
// A clip's song over its storyboard. On top the player: play / pause, where it is, the clip's piece of the song or the
// whole song, «С выбранной сцены»; the song's strip under it (its parts, the chorus, the sung lines, the scenes' cuts on
// the bars) with the playhead - a click on a scene's piece selects it and plays from it. Below, the cue sheet: every
// scene a row - its frame, its time, the part of the song it is in, what kind of shot it is, the words sung in it; the
// row that plays is lit and its words follow the voice; a click on a row plays from there and selects the scene.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import SongStrip from '../SongStrip.vue'
import HelpQ from '../HelpQ.vue'
import { api } from '../../lib/api'
import { P } from '../../lib/project'
import { shotPng } from '../../lib/board'
import { mmss } from '../../lib/format'
import type { Plan, Song } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan }>()
const song = ref<Song | null>(null)
const clip = computed(() => props.p.clip || {})
const from = computed(() => clip.value.from || 0)
const to = computed(() => from.value + (props.p.seconds || 0))
const cuts = computed(() => props.p.scenes.map((s) => from.value + (s.start || 0)))
async function load() {
  if (!clip.value.song || song.value?.id === clip.value.song) return
  try { song.value = await api<Song>(`/api/songs/${clip.value.song}`) } catch { song.value = null }
}
onMounted(load)
watch(() => clip.value.song, load)
const SHOT = ['sing', 'perform', 'insert']
const PART = ['intro', 'groove', 'break', 'drop', 'outro', 'chorus']
const counts = computed(() => {
  const c: Record<string, number> = {}
  for (const s of props.p.scenes) if (s.shot) c[s.shot] = (c[s.shot] || 0) + 1
  return Object.entries(c).map(([k, n]) => `${SHOT.includes(k) ? t(`board.shot.${k}`) : k} ${n}`).join(', ')
})

// ---- the player: the clip's piece by default, the whole song on demand ----
const audio = ref<HTMLAudioElement | null>(null)
const now = ref(0)          // seconds into the song
const playing = ref(false)
const whole = ref(false)
const src = computed(() => (song.value ? `/api/songs/${song.value.id}/file` : ''))
const end = computed(() => (whole.value ? song.value?.duration || to.value : to.value))
const start0 = computed(() => (whole.value ? 0 : from.value))
let raf = 0
function tick() {
  const a = audio.value
  if (a) {
    now.value = a.currentTime
    if (!whole.value && a.currentTime >= to.value) { a.pause(); a.currentTime = from.value }
  }
  if (playing.value) raf = requestAnimationFrame(tick)
}
async function play(at?: number) {
  const a = audio.value
  if (!a) return
  if (at != null) a.currentTime = at
  else if (a.currentTime < start0.value || a.currentTime >= end.value - 0.05) a.currentTime = start0.value
  try { await a.play() } catch { /* the browser said no: the button stays «play» */ }
}
const toggle = () => (playing.value ? audio.value?.pause() : play())
function onPlay() { playing.value = true; cancelAnimationFrame(raf); raf = requestAnimationFrame(tick) }
function onPause() { playing.value = false; cancelAnimationFrame(raf); now.value = audio.value?.currentTime || 0 }
onBeforeUnmount(() => { cancelAnimationFrame(raf); audio.value?.pause() })
const fromScene = () => play(cuts.value[P.sel] ?? from.value)
watch(whole, () => { if (!whole.value && (now.value < from.value || now.value > to.value)) { audio.value && (audio.value.currentTime = from.value); now.value = from.value } })

// the playhead over the strip (the strip shows the clip's piece)
const head = computed(() => ((now.value - from.value) / Math.max(0.01, to.value - from.value)) * 100)
const inPiece = computed(() => now.value >= from.value && now.value <= to.value)

// ---- the cue sheet ----
const partOf = (k?: string) => (k ? (PART.includes(k) ? t(`idea.part.${k}`) : k) : '')
const rows = computed(() => props.p.scenes.map((s, i) => {
  const a = from.value + (s.start || 0), b = from.value + (s.end || (s.start || 0) + (s.seconds || 5))
  const sung = ((s.sung || []) as { start: number; end: number; text: string }[]).map((x) => ({ a: a + x.start, b: a + x.end, text: x.text }))
  return { s, i, a, b, sung, png: shotPng(s.index!), part: partOf(s.part), shot: s.shot && SHOT.includes(s.shot) ? s.shot : '' }
}))
const current = computed(() => rows.value.findIndex((r) => now.value >= r.a && now.value < r.b))
// the row that plays stays in sight
const sheet = ref<HTMLElement | null>(null)
watch(current, (i) => { if (playing.value && i >= 0) sheet.value?.querySelector<HTMLElement>(`[data-row="${i}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) })
function pickRow(i: number) { P.picked = []; P.sel = i; play(rows.value[i].a) }
function pickScene(i: number) { P.picked = []; P.sel = i; if (playing.value) { play(cuts.value[i]) } else { now.value = cuts.value[i]; if (audio.value) audio.value.currentTime = cuts.value[i] } }
</script>

<template>
  <section v-if="song" class="board-song" :style="{ '--ar': (P.proj?.settings.aspect || '16:9').replace(':', ' / ') }">
    <audio ref="audio" :src="src" preload="metadata" @play="onPlay" @pause="onPause" @ended="onPause" />
    <!-- the player -->
    <div class="bsg-player">
      <button type="button" class="bsg-play" :aria-label="playing ? t('board.song.pause') : t('board.song.play')" @click="toggle"><Icon :name="playing ? 'pause' : 'play'" :size="22" /></button>
      <div class="bsg-what">
        <b>{{ clip.name || song.name }}</b>
        <span class="bsg-time"><b>{{ mmss(now) }}</b> / {{ mmss(end) }}<span>{{ Math.round(song.bpm) }} BPM</span><span>{{ counts }}</span></span>
      </div>
      <span class="grow" />
      <button type="button" class="btn" :title="t('board.song.fromSceneTitle')" @click="fromScene"><Icon name="play" :size="13" />{{ t('board.song.fromScene', { n: P.sel + 1 }) }}</button>
      <nav class="seg bsg-range" :aria-label="t('board.song.range')">
        <button type="button" :class="{ on: !whole }" :aria-pressed="!whole" @click="whole = false">{{ t('board.song.piece', { a: mmss(from), b: mmss(to) }) }}</button>
        <button type="button" :class="{ on: whole }" :aria-pressed="whole" @click="whole = true">{{ t('board.song.whole', { d: mmss(song.duration) }) }}</button>
      </nav>
      <HelpQ id="clip" term="Сцены по тактам" />
    </div>
    <!-- the strip with the playhead -->
    <div class="bsg-strip">
      <SongStrip :song="song" :from="from" :to="to" :cuts="cuts" :sel="P.sel" zoom @scene="pickScene" />
      <i v-if="inPiece" class="bsg-head" :style="{ left: `${head}%` }" />
    </div>
    <!-- the cue sheet: a row a scene -->
    <div ref="sheet" class="bsg-sheet" role="list">
      <button v-for="r in rows" :key="r.i" type="button" role="listitem" class="bsg-row" :data-row="r.i" :class="{ on: r.i === P.sel, now: r.i === current }" @click="pickRow(r.i)">
        <span class="bsg-pic"><img v-if="r.png" :src="r.png" alt="" loading="lazy"><b>{{ r.i + 1 }}</b></span>
        <span class="bsg-t">{{ mmss(r.a) }}–{{ mmss(r.b) }}</span>
        <span class="bsg-part" :class="{ loud: r.s.loud }">{{ r.part }}</span>
        <span class="bsg-shot" :class="r.shot"><Icon :name="r.shot === 'sing' ? 'music' : r.shot === 'insert' ? 'image' : 'user'" :size="13" />{{ r.shot ? t(`board.shot.${r.shot}`) : '' }}</span>
        <span class="bsg-words">
          <template v-if="r.sung.length"><span v-for="(w, k) in r.sung" :key="k" :class="{ lit: r.i === current && now >= w.a, live: r.i === current && now >= w.a && now < w.b }">{{ w.text }}</span></template>
          <em v-else>{{ t('board.song.noWords') }}</em>
        </span>
      </button>
    </div>
  </section>
  <p v-else class="muted">{{ t('board.song.loading') }}</p>
</template>
