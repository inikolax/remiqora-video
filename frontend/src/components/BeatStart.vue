<script setup lang="ts">
// The home's third way, «Бит-клип»: a song's drop cut to the beat. The song (the same wave as the clip's, with the drop
// marked), the idea in a line, the faceless hero, the look, the genre preset, the picture model, the quality - and one
// button, «Сделать бит-клип»: the autopilot with `what: 'beat'` (app/autopilot.py). The writer runs only by that button.
// Under it the route слова → окно → план → картинки → сцены → монтаж → ролик with the server's estimate; once started the
// same row is the stage bar (StageBar.vue), and the project (a graph) opens as soon as it exists.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import BeatHelp from './BeatHelp.vue'
import GuideButton from './help/GuideButton.vue'
import SongStrip from './SongStrip.vue'
import LookPick from './LookPick.vue'
import StageBar from './StageBar.vue'
import RouteSteps, { type RouteItem } from './RouteSteps.vue'
import { api, post } from '../lib/api'
import { AUTO, type LookChoice } from '../lib/looks'
import { S, banner, keep, live } from '../lib/store'
import { B, BEAT_VIDEOS, GENRES, HERO_PRESETS, type BeatInfo, beatInfo, keepBeat, nameOf, checkBeatJob } from '../lib/beat'
import { BEAT_ICON, BEAT_STEPS, type Step } from '../lib/home'
import { mins, mmss } from '../lib/format'
import type { Song } from '../lib/types'

const router = useRouter()
const { t } = useI18n()
const f = S.form
const setB = (k: keyof typeof B, v: any) => { (B as any)[k] = v; keepBeat() }

// ---- the song: the home's own form holds it (the box above takes a dropped file too)
const song = ref<Song | null>(null)
const info = ref<BeatInfo | null>(null)
const loading = ref(false)
const err = ref('')
async function load(id: string) {
  info.value = null
  if (!id) { song.value = null; return }
  try { song.value = await api<Song>(`/api/songs/${id}`) } catch { song.value = null; f.song = ''; keep(); return }
  try { info.value = await beatInfo(id) } catch (e) { err.value = (e as Error).message }
}
async function upload(file?: File) {
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  loading.value = true
  try { const s = await api<Song>('/api/songs', { method: 'POST', body: fd }); f.song = s.id; f.songFrom = 0; keep() } catch (e) { banner((e as Error).message) } finally { loading.value = false }
}
watch(() => f.song, (id) => { if (id !== song.value?.id) load(id) })

// ▶ the drop's stretch of the song
const from = computed(() => info.value?.window.start ?? 0)
const to = computed(() => from.value + (info.value?.window.seconds ?? 0))
const audio = ref<HTMLAudioElement | null>(null)
const head = ref<number | null>(null)
function listen() {
  const a = audio.value
  if (!a || !song.value) return
  if (head.value !== null) { a.pause(); head.value = null; return }
  a.currentTime = from.value; head.value = from.value
  a.play().catch(() => { head.value = null })
}
function onTime() {
  const a = audio.value
  if (!a || head.value === null) return
  if (a.currentTime >= to.value) { a.pause(); head.value = null } else head.value = a.currentTime
}
const dropAt = computed(() => (song.value && info.value ? `${Math.max(0, Math.min(100, (info.value.drop / song.value.duration) * 100))}%` : '0%'))

// ---- the hero: the faceless presets (labels from the server, ours until it answers)
const presets = computed(() => (info.value?.presets?.length ? info.value.presets : HERO_PRESETS.map((id) => ({ id, ru: t(`beat.hero.${id}`), en: t(`beat.hero.${id}`) }))))
// ---- the genre: «по песне» = the server's pick by BPM
const genreName = (id: string) => nameOf(info.value?.genres?.find((g) => g.id === id) || { ru: t(`beat.genre.${id}`), en: t(`beat.genre.${id}`) })
const byBpm = computed(() => (info.value ? genreName(info.value.genre) : ''))
// the look: only the look (the delivery is the writer's here), «✦ Решит сценарист» by default
const choice = computed<LookChoice>(() => ({ delivery: AUTO, look: B.look, look_own: '' }))
const setLook = (v: LookChoice) => setB('look', v.look)

// ---- the request (the estimate's too): the usual Autopilot body with what: 'beat'
const plan = () => ({ what: 'beat', song: f.song, genre: B.genre, hero_preset: B.hero, hero_text: B.heroText.trim(), hero_own: B.heroOwn, hero_face_hidden: B.faceHidden, length: 'drop', look: B.look, quality: B.quality, aspect: '9:16', picture_model: B.picture, video_model: B.video })
const est = ref<{ total: number; stages: Record<string, number>; run: string[]; scenes: number; seconds: number; gpu?: string } | null>(null)
let estTimer = 0, estSeq = 0
const heroReady = computed(() => !B.heroOwn || B.heroText.trim().length > 0)   // «Свой герой» is the words alone
const estBody = computed(() => (f.song ? JSON.stringify({ ...plan(), idea: B.idea.trim().length >= 3 ? 'idea' : '' }) : ''))
watch(estBody, (b) => {
  clearTimeout(estTimer)
  if (!b) { est.value = null; return }
  const seq = ++estSeq
  estTimer = window.setTimeout(async () => {
    try { const r = await post('/api/autopilot/estimate', JSON.parse(b)); if (seq === estSeq) est.value = r } catch { if (seq === estSeq) est.value = null }
  }, 350)
}, { immediate: true })
// the bar draws its tiles by the home's Step type; a beat step's id only keys the tile
const items = computed<RouteItem[]>(() => BEAT_STEPS.map((s) => ({ id: s as unknown as Step, name: t(`beat.step.${s}`), icon: BEAT_ICON[s], state: 'on' as const,
  time: est.value?.stages?.[s] != null ? t('home.stepTime', { t: mins(est.value.stages[s]) }) : '', label: t(`beat.stepTitle.${s}`) })))

// ---- «Сделать бит-клип»: the writer's job starts here and only here
const busy = ref(false)
const job = computed(() => (B.job ? S.jobs.find((j) => j.id === B.job) : undefined))
const showBar = computed(() => !!job.value && (live(job.value) || job.value.status === 'error'))
watch(() => job.value?.params?.project, (pid) => { if (pid && job.value && (live(job.value) || job.value.status === 'done')) { setB('job', ''); router.push(`/g/${pid}`) } })
async function make() {
  if (!song.value) { err.value = t('beat.songFirst'); return }
  err.value = ''
  busy.value = true
  try {
    const r = await post('/api/autopilot', { ...plan(), idea: B.idea.trim().slice(0, 600), model: S.llm || null })
    S.jobs = [...S.jobs, r]
    setB('job', r.id)
  } catch (e) { err.value = (e as Error).message } finally { busy.value = false }
}

onMounted(async () => {
  load(f.song)
  const j = await checkBeatJob()   // a job that ended while the page was away: forget it (a finished one opens its graph)
  if (j?.status === 'done' && j.params?.project) router.push(`/g/${j.params.project}`)
})
onUnmounted(() => { audio.value?.pause(); clearTimeout(estTimer) })
</script>

<template>
  <div class="idea-head sf-head"><div class="title-row"><h1>{{ t('beat.title') }}</h1><GuideButton guide="idea" /></div>
    <p>{{ t('beat.about') }}</p></div>

  <div class="sf-main">
    <div class="stack"><span class="lbl">{{ t('beat.song') }} <BeatHelp k="song" /></span>
      <label v-if="!song" class="drop">
        <input type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg" hidden @change="upload(($event.target as HTMLInputElement).files?.[0])">
        <Icon name="music" :size="28" cls="muted-ic" />
        <span>{{ loading ? t('idea.clip.parsing') : t('idea.clip.drop') }}<small>{{ t('beat.songSub') }}</small></span>
      </label>
      <template v-else>
        <div class="song-head"><Icon name="music" :size="16" /><b :title="song.name">{{ song.name }}</b>
          <span class="muted">{{ mmss(song.duration) }} · {{ Math.round(info?.bpm ?? song.bpm) }} BPM</span>
          <button type="button" class="btn song-play" :class="{ on: head !== null }" :disabled="!info" :title="t('beat.listenTitle')" @click="listen">
            <Icon :name="head !== null ? 'stop' : 'play'" :size="13" />{{ head !== null ? t('idea.clip.listenStop') : t('beat.listen') }}</button>
          <audio ref="audio" :src="`/api/songs/${song.id}/file`" preload="none" @timeupdate="onTime" @ended="head = null" @pause="head = null" />
          <label class="link-btn" style="cursor:pointer">{{ t('idea.clip.another') }}<input type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg" hidden @change="upload(($event.target as HTMLInputElement).files?.[0])"></label></div>
        <div class="bs-wave">
          <SongStrip :song="song" :from="from" :to="to" :head="head" />
          <i v-if="info" class="bs-drop" :style="{ left: dropAt }" :title="t('beat.dropAt', { t: mmss(info.drop) })"><span>{{ t('beat.dropMark') }}</span></i>
        </div>
        <p v-if="info" class="muted clip-hint">{{ t('beat.windowNote', { a: mmss(from), b: mmss(to), s: Math.round(info.window.seconds), drop: mmss(info.drop), build: info.build_bars, bars: info.drop_bars }) }}</p>
      </template>
    </div>
    <label class="stack"><span class="lbl">{{ t('idea.idea') }} <small>{{ t('idea.optional') }}</small> <BeatHelp k="idea" /></span>
      <input class="field-in" maxlength="300" :value="B.idea" :placeholder="t('beat.ideaPh')" @input="setB('idea', ($event.target as HTMLInputElement).value)"></label>
  </div>

  <div class="sf-mid">
    <div class="stack"><span class="lbl">{{ t('beat.hero.lbl') }} <BeatHelp k="hero" /></span>
      <div class="bs-heroes" role="radiogroup" :aria-label="t('beat.hero.lbl')">
        <button v-for="p in presets" :key="p.id" type="button" role="radio" :aria-checked="!B.heroOwn && B.hero === p.id" class="bs-hero" :class="{ on: !B.heroOwn && B.hero === p.id }" @click="setB('heroOwn', false); setB('hero', p.id)">
          <b>{{ nameOf(p) }}</b><small>{{ t(`beat.hero.sub.${p.id}`) }}</small></button>
        <button type="button" role="radio" :aria-checked="B.heroOwn" class="bs-hero" :class="{ on: B.heroOwn }" @click="setB('heroOwn', true)">
          <b>{{ t('beat.hero.own') }}</b><small>{{ t('beat.hero.ownSub') }}</small></button>
        <button type="button" class="bs-hero" disabled :title="t('beat.hero.faceTitle')"><b>{{ t('beat.hero.face') }}</b><small>{{ t('beat.later') }}</small></button>
      </div>
      <label class="stack bs-desc"><span class="lbl">{{ t('beat.hero.descLbl') }} <small v-if="!B.heroOwn">{{ t('idea.optional') }}</small> <BeatHelp k="heroText" /></span>
        <textarea class="field-in" rows="2" maxlength="600" :value="B.heroText" :placeholder="t('beat.hero.descPh')" :aria-invalid="!heroReady"
          @input="setB('heroText', ($event.target as HTMLTextAreaElement).value)" /></label>
      <p v-if="B.heroOwn && !heroReady" class="muted clip-hint">{{ t('beat.hero.ownNeed') }}</p>
      <label v-if="B.heroOwn" class="bs-face"><input type="checkbox" :checked="B.faceHidden" @change="setB('faceHidden', ($event.target as HTMLInputElement).checked)">
        <span>{{ t('beat.hero.faceHidden') }}</span> <BeatHelp k="faceHidden" /></label>
    </div>
    <div class="stack"><span class="lbl">{{ t('looks.look') }} <BeatHelp k="look" /></span>
      <LookPick :model-value="choice" @update:model-value="setLook" /></div>
    <div class="stack"><span class="lbl">{{ t('beat.length') }} <BeatHelp k="length" /></span>
      <div class="chips"><button type="button" class="chip on" aria-pressed="true">{{ t('beat.lenDrop', { s: Math.round(info?.seconds ?? 24) }) }}</button>
        <button type="button" class="chip" disabled>{{ t('beat.lenMin') }} <small>{{ t('beat.later') }}</small></button></div></div>
  </div>

  <div class="sf-side">
    <div class="stack"><span class="lbl">{{ t('beat.genre.lbl') }} <BeatHelp k="genre" /></span>
      <div class="chips"><button v-for="g in GENRES" :key="g" type="button" class="chip" :class="{ on: B.genre === g }" @click="setB('genre', g)">
        {{ g === 'auto' ? t('beat.genre.auto') : genreName(g) }}</button></div>
      <p v-if="B.genre === 'auto' && byBpm" class="muted clip-hint">{{ t('beat.genre.byBpm', { g: byBpm, bpm: Math.round(info?.bpm || 0) }) }}</p></div>
    <div class="stack"><span class="lbl">{{ t('beat.picModel') }} <BeatHelp k="picture" /></span>
      <select class="field-in" :value="B.picture" @change="setB('picture', ($event.target as HTMLSelectElement).value)"><option value="krea2">Krea 2</option></select></div>
    <div class="stack"><span class="lbl">{{ t('beat.videoModel') }} <BeatHelp k="video" /></span>
      <div class="chips" role="radiogroup" :aria-label="t('beat.videoModel')"><button v-for="m in BEAT_VIDEOS" :key="m" type="button" role="radio" :aria-checked="B.video === m" class="chip" :class="{ on: B.video === m }" @click="setB('video', m)">{{ t(`beat.video.${m}`) }}</button></div></div>
    <div class="stack"><span class="lbl">{{ t('beat.quality') }} <BeatHelp k="quality" /></span>
      <div class="chips"><button v-for="q in ['draft', 'final']" :key="q" type="button" class="chip" :class="{ on: B.quality === q }" @click="setB('quality', q)">{{ t(`board.quality.${q}`) }}</button></div></div>
  </div>

  <div class="sf-route bs-route">
    <StageBar v-if="showBar" :job-id="job!.id" @again="make" />
    <template v-else>
      <RouteSteps :items="items" />
      <p v-if="est" class="muted clip-hint">{{ t('beat.estimate', { t: mins(est.total), n: est.scenes, s: Math.round(est.seconds) }) }}</p>
    </template>
  </div>

  <div class="sf-foot">
    <div v-if="err" class="error">{{ err }}</div>
    <span class="foot-note">{{ song ? t('beat.makeNote') : t('beat.songFirst') }}</span>
    <button type="button" class="primary" :disabled="busy || !song || !heroReady || (!!job && live(job))" @click="make"><Icon name="play" />{{ t('beat.make') }}</button>
  </div>
</template>

<style scoped>
.bs-wave { position: relative; }
/* the drop's mark over the wave: a line at its second */
.bs-drop { position: absolute; top: 0; bottom: 0; width: 0; border-left: 2px solid var(--accent-hi); pointer-events: none; }
.bs-drop span { position: absolute; top: -2px; left: 4px; padding: 0 5px; border-radius: 4px; background: var(--accent); color: #fff; font-size: 10.5px; font-style: normal; font-weight: 600; line-height: 16px; white-space: nowrap; }
.bs-heroes { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.bs-hero { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; min-height: 58px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--rule-2); background: var(--panel);
  color: var(--text); text-align: left; font: inherit; cursor: pointer; }
.bs-hero b { font-size: 14px; font-weight: 600; }
.bs-hero small { color: var(--muted); font-size: 12px; }
.bs-hero:hover:not(:disabled) { border-color: var(--accent); }
.bs-hero.on { border-color: var(--accent); background: var(--accent-bg); box-shadow: 0 0 0 1px var(--accent) inset; }
.bs-hero:disabled { opacity: .5; cursor: default; border-style: dashed; }
.bs-desc { margin-top: 6px; }
.bs-desc textarea { resize: vertical; min-height: 56px; }
.bs-face { display: flex; align-items: center; gap: 8px; margin-top: 4px; cursor: pointer; font-size: 13.5px; }
.bs-route { display: flex; flex-direction: column; gap: 8px; }
</style>
