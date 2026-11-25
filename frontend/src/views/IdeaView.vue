<script setup lang="ts">
// 1. The home: «Что снимаем?» - box → slate → route → button. The box takes the idea in words
// and the files dropped on it or given by its three ways in (a song goes into the song library as «Клип» puts it there,
// a photo into the frames, a video gives its frame as the photo); a file that does not fit says so under the box. «Поняли
// так» (lib/home.ts) with «Не так? Изменить ▾»; one row of the big choices - «Подача · Вид», the frame, the length (a
// song's piece with its wave, a story's seconds); the route «Как снимаем» (RouteStrip.vue: the autopilot's steps, each
// switchable, their time from the server, the stops of «Спрашивать меня», the model in «Съёмка»). «Сделать ролик» runs
// the autopilot to a finished video (app/autopilot.py; the route becomes its bar, StageBar.vue, until the project exists,
// then the project opens), «Пошагово» makes the project as «Расписать сцены» / «Расписать клип» do and opens its
// storyboard. «Тонкая настройка» (a story's who is in the frame, its music; the LoRA live in the route's steps), «Свои промты» and «Клип: все настройки» are small
// links under the buttons. Under the card the second way in: «Или соберите на холсте» - the graph's templates, one click
// to a canvas (GraphStart.vue). «Ваши ролики» below (Shelf.vue).
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from '../components/Icon.vue'
import GuideButton from '../components/help/GuideButton.vue'
import HelpQ from '../components/HelpQ.vue'
import ModelPick from '../components/ModelPick.vue'
import ClipStart from '../components/ClipStart.vue'
import BeatStart from '../components/BeatStart.vue'
import GraphStart from '../components/GraphStart.vue'
import LookPick from '../components/LookPick.vue'
import SongStrip from '../components/SongStrip.vue'
import StageBar from '../components/StageBar.vue'
import RouteStrip from '../components/RouteStrip.vue'
import Shelf from '../components/Shelf.vue'
import { api, post } from '../lib/api'
import { S, banner, keep, live, loadProjects, onJobEnd, pickClipVideo, pickVideo } from '../lib/store'
import { LENGTHS, MODES } from '../lib/consts'
import { dec, mmss } from '../lib/format'
import { type LookChoice, formChoice, lookOf, toForm } from '../lib/looks'
import { type RouteEstimate, type Step, type What, WHATS, fits, understand } from '../lib/home'
import type { Song } from '../lib/types'
import { B, checkBeatJob } from '../lib/beat'
import HeroKind from '../components/board/HeroKind.vue'

const router = useRouter()
const { t } = useI18n()
const f = S.form
const set = (k: keyof typeof f, v: any) => { (f as any)[k] = v; keep() }
const choice = computed(() => formChoice(f))
const setChoice = (v: LookChoice) => { Object.assign(f, toForm(v)); keep() }

// ---- what was given: the words, a song, a photo (or a video's frame)
const song = ref<Song | null>(null)
const loading = ref(0)
const over = ref(false)
let overDepth = 0   // dragenter / dragleave of the children: the hint stays until the file leaves the form itself
const ideaEl = ref<HTMLTextAreaElement | null>(null)
const AUDIO = /\.(mp3|wav|m4a|flac|ogg|aac)$/i, IMAGE = /\.(png|jpe?g|webp)$/i, VIDEO = /\.(mp4|mov|webm|mkv|m4v)$/i
const ACCEPT = { song: 'audio/*,.mp3,.wav,.m4a,.flac,.ogg', photo: 'image/png,image/jpeg,image/webp', video: 'video/*,.mp4,.mov,.webm,.mkv' }
const SOURCES = ['song', 'photo', 'video'] as const
const SRC_ICON = { song: 'music', photo: 'image', video: 'camera' }
async function loadSong(id: string) {
  if (!id) return
  try { song.value = await api<Song>(`/api/songs/${id}`) } catch { song.value = null; set('song', '') }
}
// a file that does not fit: said under the box, with what stays
const err = ref('')
function badFile(name: string) {
  const k = song.value && photo.value ? 'both' : song.value ? 'song' : photo.value ? 'photo' : 'none'
  err.value = t('home.badFile', { name, kept: t(`home.kept.${k}`) }).trim()
}
async function upload(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  const kind = file.type.startsWith('audio/') || AUDIO.test(file.name) ? 'song' : file.type.startsWith('image/') || IMAGE.test(file.name) ? 'photo'
    : file.type.startsWith('video/') || VIDEO.test(file.name) ? 'video' : ''
  if (!kind) { badFile(file.name); return }
  err.value = ''
  loading.value++
  try {
    if (kind === 'song') { song.value = await api<Song>('/api/songs', { method: 'POST', body: fd }); set('song', song.value.id); set('songFrom', 0) }
    else set('autoPhoto', await api(kind === 'photo' ? '/api/frames' : '/api/frames/video', { method: 'POST', body: fd }))
  } catch (e) { err.value = (e as Error).message } finally { loading.value-- }
}
const addFiles = (files?: FileList | null) => { for (const x of Array.from(files || [])) upload(x) }
const fromInput = (e: Event) => { const el = e.target as HTMLInputElement; addFiles(el.files); el.value = '' }
const dragIn = () => { overDepth++; over.value = true }
const dragOut = () => { overDepth = Math.max(0, overDepth - 1); if (!overDepth) over.value = false }
const onDrop = (e: DragEvent) => { overDepth = 0; over.value = false; addFiles(e.dataTransfer?.files) }
const dropSong = () => { song.value = null; set('song', '') }
const photo = computed(() => f.autoPhoto as { name: string; url: string; from_video?: string } | null)
const empty = computed(() => !(f.idea || '').trim() && !song.value && !photo.value && !loading.value)
// the «+» chip: what is still missing
const addLabel = computed(() => (!song.value && !photo.value ? t('home.addAny') : song.value && !photo.value ? t('home.addPhoto') : t('home.add')))
const addAccept = computed(() => (song.value ? `${ACCEPT.photo},${ACCEPT.video}` : `${ACCEPT.song},${ACCEPT.photo},${ACCEPT.video}`))

// ---- «Поняли так» and «Не так? Изменить»
const has = computed(() => ({ song: !!song.value, photo: !!photo.value, text: f.idea || '' }))
const guessed = computed(() => understand(has.value.song, has.value.photo, has.value.text))
const what = computed<What | ''>(() => (f.what && f.what !== 'beat' && fits(f.what as What, has.value.song, has.value.photo, has.value.text) ? f.what as What : guessed.value))
const options = computed(() => WHATS.filter((w) => fits(w, has.value.song, has.value.photo, has.value.text)))
const menu = ref(false)
// «Бит-клип» is not a way of the box's own route: it opens its own form (BeatStart.vue), the song stays
const force = (w: What) => { menu.value = false; if (w === 'beat') { panel.value = 'beat'; return } set('what', w === guessed.value ? '' : w) }
const isClip = computed(() => what.value.startsWith('clip'))
const menuEl = ref<HTMLElement | null>(null)
const outside = (e: Event) => { if (menu.value && menuEl.value && !menuEl.value.contains(e.target as Node)) menu.value = false }
const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') menu.value = false }

// ---- the length: a song's piece (whole / the best minute / own piece / 30 s), a story's seconds
const length = computed(() => f.autoLength || 'whole')
const ownSecs = computed(() => (song.value ? Math.max(4, Math.min(f.songSecs || 60, song.value.duration)) : 0))
const ownFrom = computed(() => (song.value ? Math.max(0, Math.min(f.songFrom, song.value.duration - ownSecs.value)) : 0))
const OWN = computed<[number, string][]>(() => [[30, `30 ${t('common.s')}`], [45, `45 ${t('common.s')}`], [60, `1 ${t('common.min')}`], [90, `${dec(1.5)} ${t('common.min')}`]])
const songSecs = computed(() => (!song.value ? 0 : length.value === 'own' ? ownSecs.value : length.value === 'best' && song.value.duration > 75 ? 60
  : length.value === 's30' && song.value.duration > 45 ? 30 : song.value.duration))
const CLIP_LENGTHS = ['whole', 'best', 'own', 's30'] as const
const ask = computed(() => f.ask !== false)
// ▶ the own piece of the song, as the clip form plays it: while it plays a click inside the piece seeks there, a click
// outside moves the piece and plays on from its new start; it stops at the piece's end
const audio = ref<HTMLAudioElement | null>(null)
const head = ref<number | null>(null)
function listen() {
  const a = audio.value
  if (!a || !song.value) return
  if (head.value !== null) { a.pause(); head.value = null; return }
  a.currentTime = ownFrom.value
  head.value = ownFrom.value
  a.play().catch(() => { head.value = null })
}
function seek(t: number) {
  if (audio.value) { audio.value.currentTime = t; head.value = t }
}
function onTime() {
  const a = audio.value
  if (!a || head.value === null) return
  if (a.currentTime >= ownFrom.value + ownSecs.value) { a.pause(); head.value = null } else head.value = a.currentTime
}
watch(ownFrom, (v) => { if (head.value !== null && audio.value) { audio.value.currentTime = v; head.value = v } })
watch(() => [song.value?.id, isClip.value, length.value], () => { audio.value?.pause(); head.value = null })

// ---- the route «Как снимаем»: what the autopilot runs. Defaults: everything. A look that draws every frame
// (`needs_frame`) holds the frames on; the places only with the frames.
const own = computed(() => f.autoScript === 'own')
const hero = computed(() => f.autoHero !== false)
const forced = computed(() => !!lookOf(choice.value.look)?.needs_frame)
const frames = computed(() => f.autoFrames !== false || forced.value)
const places = computed(() => frames.value && f.autoPlaces !== false)
const runs = () => ({ script: own.value ? 'own' : 'writer', hero: hero.value, frames: frames.value, places: places.value })
function toggle(s: Step) {
  if (s === 'write') set('autoScript', own.value ? 'writer' : 'own')
  else if (s === 'hero') set('autoHero', !hero.value)
  else if (s === 'frames' && !forced.value) set('autoFrames', !frames.value)
  else if (s === 'places') {   // places need the frames: turning them on turns those on too
    if (!frames.value) { set('autoFrames', true); set('autoPlaces', true) } else set('autoPlaces', !places.value)
  }
}
const videoId = computed(() => (isClip.value ? pickClipVideo(f.clipVideo) : pickVideo(f.video)))
const setModel = (id: string) => set(isClip.value ? 'clipVideo' : 'video', id)
const aspect = computed(() => (f.aspect === '9:16' ? '9:16' : '16:9'))

// ---- the request of either button
const runErr = ref('')
const busy = ref(false)
const songLength = () => (length.value === 'own' ? { length: 'own', start: ownFrom.value, seconds: ownSecs.value }
  : length.value === 's30' ? { length: 'best', seconds: 30 } : { length: length.value })
const storyIdea = () => (f.idea || '').trim() || (photo.value ? t('home.photoIdea') : '')
const usesPhoto = () => ['clip_hero', 'story_hero', 'story_start'].includes(what.value) && photo.value ? photo.value.name : null
const heroReq = () => ((f.heroText || '').trim() ? { hero_text: (f.heroText || '').trim(), hero_kind: f.heroKind || 'person' } : {})
const looksReq = () => ({ delivery: choice.value.delivery, look: choice.value.look, look_own: choice.value.look_own })
// the autopilot's request without the words and the writer (the estimate's too)
const plan = () => (isClip.value
  ? { what: what.value, song: f.song, photo: usesPhoto(), aspect: aspect.value, ...songLength(), video_model: videoId.value, ask: ask.value, ...runs(), ...looksReq() }
  : { what: what.value, photo: usesPhoto(), seconds: f.seconds, mode: f.who || 'auto', aspect: aspect.value, video_model: videoId.value, ask: ask.value, ...runs(), ...looksReq(), ...heroReq() })
function ready() {
  err.value = ''
  runErr.value = ''
  if (!what.value) { err.value = t('home.nothing'); ideaEl.value?.focus(); return false }
  if (loading.value) return false
  return true
}

// the route's time: the server's own estimate, asked again a moment after the form settles (the idea's words don't
// change it - only that there is one)
const est = ref<RouteEstimate | null>(null)
let estTimer = 0, estSeq = 0
const estBody = computed(() => (what.value ? JSON.stringify({ ...plan(), idea: (f.idea || '').trim().length >= 3 ? 'idea' : '' }) : ''))
watch(estBody, (b) => {
  clearTimeout(estTimer)
  if (!b) { est.value = null; return }
  const seq = ++estSeq
  estTimer = window.setTimeout(async () => {
    try { const r = await post('/api/autopilot/estimate', JSON.parse(b)); if (seq === estSeq) est.value = r } catch { if (seq === estSeq) est.value = null }
  }, 350)
}, { immediate: true })

// «Сделать ролик»: the autopilot; its project opens as soon as there is one
const job = computed(() => (f.autoJob ? S.jobs.find((j) => j.id === f.autoJob) : undefined))
const showBar = computed(() => !!job.value && (live(job.value) || job.value.status === 'error'))
watch(() => job.value?.params?.project, (pid) => { if (pid && job.value && (live(job.value) || job.value.status === 'done')) { set('autoJob', ''); router.push(`/p/${pid}`) } })
async function make() {
  if (!ready()) return
  busy.value = true
  try {
    const idea = isClip.value ? (f.idea || '').trim().slice(0, 600) : (f.idea || '').trim()
    const r = await post('/api/autopilot', { ...plan(), idea, model: S.llm || null })
    S.jobs = [...S.jobs, r]
    set('autoJob', r.id)
  } catch (e) { runErr.value = (e as Error).message } finally { busy.value = false }
}

// «Пошагово»: the project as «Расписать клип» / «Расписать сцены» make it, its storyboard opened
async function steps() {
  if (!ready()) return
  busy.value = true
  try {
    let r
    if (isClip.value) {
      const lq = songLength() as Record<string, any>
      const q = new URLSearchParams({ song_id: f.song, length: lq.length, ...(lq.seconds ? { seconds: String(lq.seconds) } : {}), ...(lq.start ? { start: String(lq.start) } : {}) })
      const w = await api(`/api/autopilot/window?${q}`)
      r = await post('/api/clips', { song: f.song, start: w.start, seconds: w.seconds, idea: (f.idea || '').trim(), mode: 'one', aspect: aspect.value,
        delivery: choice.value.delivery, look_id: choice.value.look, look_own: choice.value.look_own, photo: usesPhoto(), model: S.llm || null,
        video_model: pickClipVideo(f.clipVideo), look: usesPhoto() ? 'photo' : 'writer', story: 'writer', scenes: 'all', loras: f.loras || [], pic_loras: f.picLoras || {},
        draw_singer: false, frames: false, places: false })
    } else {
      r = await post('/api/projects', { idea: storyIdea(), seconds: f.seconds, mode: f.who || 'auto', aspect: aspect.value, music: f.music,
        delivery: choice.value.delivery, look: choice.value.look, look_own: choice.value.look_own, ...heroReq(),
        photo: usesPhoto(), photo_start: what.value === 'story_start', model: S.llm || null, video_model: pickVideo(f.video), loras: f.loras || [], pic_loras: f.picLoras || {} })
    }
    if (r.job) S.jobs = [...S.jobs, r.job]
    router.push(`/p/${r.project}`)
  } catch (e) { runErr.value = (e as Error).message; busy.value = false }
}

// ---- «Тонкая настройка» and the small links: own prompts (an empty storyboard), a graph, the clip's whole form
const fine = ref(false)
const fineEl = ref<HTMLElement | null>(null)
const openFine = () => { fine.value = true; requestAnimationFrame(() => fineEl.value?.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })) }
const panel = ref<'' | 'manual' | 'clip' | 'beat'>(B.job ? 'beat' : '')   // a beat clip going on shows its bar
const openPanel = (p: typeof panel.value) => { panel.value = panel.value === p ? '' : p }
const manualName = ref('')
const manualSecs = ref(30)
async function openManual() {
  busy.value = true
  try {
    const r = await post('/api/projects', { idea: manualName.value, seconds: manualSecs.value, mode: 'one', aspect: aspect.value, manual: true,
      video_model: pickVideo(f.video), loras: f.loras || [], pic_loras: f.picLoras || {} })
    router.push(`/p/${r.project}`)
  } catch (e) { banner((e as Error).message); busy.value = false }
}

// a writer's job just ended: the videos' badges and names change
let off: () => void
onMounted(() => {
  loadProjects(); loadSong(f.song); off = onJobEnd(() => loadProjects())
  if (B.job) checkBeatJob().then(() => { if (!B.job && panel.value === 'beat') panel.value = '' })   // the job is over or unknown: the form is not "going on"
  document.addEventListener('pointerdown', outside); document.addEventListener('keydown', esc)
})
onUnmounted(() => {
  off?.(); audio.value?.pause(); clearTimeout(estTimer)
  document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', esc)
})
watch(() => f.song, (id) => { if (id && id !== song.value?.id) loadSong(id) })
</script>

<template>
  <div class="home">
    <section class="create-wrap">
      <div class="create" @dragenter.prevent="dragIn" @dragover.prevent @dragleave="dragOut" @drop.prevent="onDrop">
        <div class="cr-head"><h1>{{ t('home.title') }}</h1><span class="cr-about">{{ t('home.about') }}</span><GuideButton guide="idea" class="cr-guide" /></div>

        <div class="cr-box" :class="{ over }">
          <textarea ref="ideaEl" class="cr-text" rows="2" :value="f.idea" :placeholder="song ? `${t('home.ph')} ${t('home.ideaOptional')}` : t('home.ph')" :aria-label="t('home.title')"
            @input="set('idea', ($event.target as HTMLTextAreaElement).value)" />
          <template v-if="empty">
            <small class="cr-example">{{ t('home.example') }}</small>
            <div class="cr-sources">
              <label v-for="k in SOURCES" :key="k" class="src" :title="t(`home.srcTitle.${k}`)"><Icon :name="SRC_ICON[k]" :size="16" />{{ t(`home.src.${k}`) }}
                <small class="src-hint">{{ t(`home.srcHint.${k}`) }}</small>
                <input type="file" class="src-in" :accept="ACCEPT[k]" :aria-label="t(`home.srcTitle.${k}`)" @change="fromInput"></label>
              <span class="cr-or">{{ t('home.orDrop') }}</span>
            </div>
          </template>
          <div v-else class="cr-files">
            <span v-if="song" class="cr-file"><Icon name="music" :size="16" /><b :title="song.name">{{ song.name }}</b><span class="cr-file-t">{{ mmss(song.duration) }}</span>
              <button type="button" class="cr-x" :aria-label="`${t('home.remove')}: ${song.name}`" :title="t('home.remove')" @click="dropSong"><Icon name="close" :size="14" /></button></span>
            <span v-if="photo" class="cr-file"><img :src="photo.url" alt=""><b :title="photo.name">{{ photo.from_video || t('home.src.photo') }}</b><span v-if="photo.from_video" class="cr-file-t">{{ t('home.fromVideo') }}</span>
              <button type="button" class="cr-x" :aria-label="`${t('home.remove')}: ${photo.from_video || t('home.src.photo')}`" :title="t('home.remove')" @click="set('autoPhoto', null)"><Icon name="close" :size="14" /></button></span>
            <span v-if="loading" class="cr-file muted"><i class="spin" />{{ t('home.loading') }}</span>
            <label class="cr-add" :title="t('home.addTitle')"><Icon name="plus" :size="14" /><span class="l-full">{{ addLabel }}</span><span class="l-short">{{ song && !photo ? t('home.addPhotoShort') : addLabel }}</span>
              <input type="file" class="src-in" multiple :accept="addAccept" :aria-label="t('home.addTitle')" @change="fromInput"></label>
          </div>
          <div v-if="over" class="cr-drop-hint" aria-hidden="true"><div><Icon name="drop" :size="18" /> {{ t('home.dropTitle') }}<small>{{ t('home.dropSub') }}</small></div></div>
        </div>
        <div v-if="err" class="cr-err" role="alert"><Icon name="warn" :size="16" /><span>{{ err }}</span><button type="button" class="link-btn" @click="err = ''">{{ t('home.got') }}</button></div>

        <div v-if="what" ref="menuEl" class="cr-slate">
          <span class="cr-lead"><Icon name="spark" :size="16" />{{ t('home.understood') }}</span><b>{{ t(`home.what.${what}`) }}</b>
          <small class="cr-slate-sub">{{ t(`home.whatSub.${what}`) }}</small>
          <button v-if="options.length > 1" type="button" class="cr-change" :aria-expanded="menu" aria-haspopup="menu" :title="t('home.changeTitle')" @click="menu = !menu">
            <span class="l-full">{{ t('home.change') }}</span><span class="l-short">{{ t('home.short.change') }}</span><Icon name="down" :size="14" /></button>
          <div v-if="menu" class="cr-menu" role="menu">
            <button v-for="w in options" :key="w" type="button" role="menuitemradio" :aria-checked="w === what" :class="{ on: w === what }" @click="force(w)">
              <b>{{ t(`home.what.${w}`) }}</b><small>{{ t(`home.whatSub.${w}`) }}</small></button></div>
        </div>

        <template v-if="what">
          <div class="cr-row">
            <span class="cr-look"><LookPick :model-value="choice" :video="videoId" @update:model-value="setChoice" /><HelpQ id="idea" term="Вид" /></span>
            <span class="cr-grp"><span class="lbl"><Icon name="wide" :size="14" />{{ t('home.frame') }}</span>
              <span class="chips" role="radiogroup" :aria-label="t('home.frame')"><button v-for="a in ['16:9', '9:16']" :key="a" type="button" role="radio" :aria-checked="aspect === a" class="chip" :class="{ on: aspect === a }" @click="set('aspect', a)">
                <Icon :name="a === '16:9' ? 'wide' : 'tall'" :size="16" />{{ a }}</button></span></span>
            <span class="cr-grp"><span class="lbl"><Icon name="clock" :size="14" />{{ t('home.length') }}</span>
              <span v-if="isClip" class="chips" role="radiogroup" :aria-label="t('home.length')">
                <button v-for="k in CLIP_LENGTHS" :key="k" type="button" role="radio" :aria-checked="length === k" class="chip" :class="{ on: length === k }"
                  :title="k === 'best' ? t('home.bestTitle') : k === 's30' ? t('home.s30Title') : undefined" @click="set('autoLength', k)">
                  <Icon v-if="k === 'own' && length === 'own'" name="wave" :size="16" />
                  <template v-if="k === 's30'">{{ t('home.s30') }}</template>
                  <template v-else><span class="l-full">{{ t(`home.${k}`) }}</span><span class="l-short">{{ t(`home.short.${k}`) }}</span></template>
                  <span v-if="k === 'whole' && song" class="chip-t l-full">{{ mmss(song.duration) }}</span></button>
                <span v-if="song && (length === 'best' || length === 's30')" class="note">≈ {{ mmss(songSecs) }}</span></span>
              <span v-else class="chips" role="radiogroup" :aria-label="t('home.length')"><button v-for="s in LENGTHS" :key="s" type="button" role="radio" :aria-checked="f.seconds === s" class="chip" :class="{ on: f.seconds === s }" @click="set('seconds', s)">{{ s >= 120 ? `${s / 60} ${t('common.min')}` : `${s} ${t('common.s')}` }}</button></span></span>
          </div>
          <template v-if="isClip && song && length === 'own'">
            <div class="cr-wave">
              <button type="button" class="cr-play" :class="{ on: head !== null }" :title="t('idea.clip.listenTitle')"
                :aria-label="head !== null ? t('idea.clip.listenStop') : t('idea.clip.listen')" @click="listen"><Icon :name="head !== null ? 'stop' : 'play'" :size="16" /></button>
              <SongStrip :song="song" :from="ownFrom" :to="ownFrom + ownSecs" :head="head" editable @pick="set('songFrom', $event)" @range="(a, s) => { set('songFrom', a); set('songSecs', s) }" @seek="seek" /></div>
            <audio ref="audio" :src="`/api/songs/${song.id}/file`" preload="none" @timeupdate="onTime" @ended="head = null" @pause="head = null" />
            <div class="chips cr-own"><button v-for="[s, l] in OWN" :key="s" type="button" class="chip" :class="{ on: ownSecs === s }" :aria-pressed="ownSecs === s" @click="set('songSecs', s)">{{ l }}</button>
              <span class="note">{{ mmss(ownFrom) }}–{{ mmss(ownFrom + ownSecs) }}<span class="l-full"> · {{ t('home.ownNote') }}</span></span></div>
          </template>
        </template>

        <StageBar v-if="showBar" :job-id="job!.id" @again="make" />
        <RouteStrip v-else :idle="!what" :clip="isClip" :est="est" :ask="ask" :own="own" :hero="hero" :frames="frames" :places="places" :forced="forced"
          :photo="usesPhoto() ? photo!.url : null" :model="videoId" :aspect="aspect" :loras="f.loras || []" :pics="f.picLoras || {}"
          @toggle="toggle" @update:ask="set('ask', $event)" @update:model="setModel" @update:loras="set('loras', $event)" @update:pics="set('picLoras', $event)" />
        <p v-if="job && live(job)" class="muted cr-opens">{{ t('home.opens') }}</p>

        <div v-if="fine && what && !isClip" ref="fineEl" class="cr-fine">
          <div v-if="!isClip" class="cr-fine-col"><span class="lbl"><Icon name="users" :size="14" />{{ t('home.who') }} <HelpQ id="idea" term="Кто в кадре" /></span>
            <span class="chips" role="radiogroup" :aria-label="t('home.who')"><button v-for="[m, l, ic] in [['auto', t('home.whoAuto'), 'spark'], ...MODES.map(([a, b]) => [a, b, a === 'one' ? 'user' : a === 'none' ? 'scenery' : 'users'])]" :key="m" type="button" role="radio"
              :aria-checked="(f.who || 'auto') === m" class="chip" :class="{ on: (f.who || 'auto') === m }" @click="set('who', m)"><Icon :name="ic" :size="16" />{{ l }}</button></span>
            <small class="cr-fine-note">{{ t('home.whoNote') }}</small></div>
          <div v-if="!isClip" class="cr-fine-col cr-hero"><span class="lbl"><Icon name="user" :size="14" />{{ t('home.heroOwn') }}</span>
            <HeroKind :model-value="f.heroKind || 'person'" @update:model-value="set('heroKind', $event)" />
            <textarea class="field-in" rows="2" maxlength="1200" :aria-label="t('home.heroOwn')" :value="f.heroText || ''" :placeholder="t('home.heroOwnPh')" @input="set('heroText', ($event.target as HTMLTextAreaElement).value)" />
            <small class="cr-fine-note">{{ t('home.heroOwnNote') }}</small></div>
          <label v-if="!isClip" class="cr-fine-col"><span class="lbl"><Icon name="music" :size="14" />{{ t('home.music') }} <HelpQ id="idea" term="Музыка и звук" /></span>
            <input class="field-in" :value="f.music" :placeholder="t('home.musicPh')" @input="set('music', ($event.target as HTMLInputElement).value)">
            <small class="cr-fine-note">{{ t('home.musicNote') }}</small></label>
        </div>

        <div class="cr-actions">
          <button type="button" class="primary cr-make" :class="{ dim: !what }" :aria-disabled="!what || undefined" :disabled="busy || !!loading || (!!job && live(job))" @click="make"><Icon name="play" />{{ t('home.make') }}</button>
          <button type="button" class="btn cr-steps" :disabled="busy || !!loading" @click="steps"><Icon name="steps" />{{ t('home.steps') }}</button>
          <button type="button" class="btn cr-beat" :aria-expanded="panel === 'beat'" :title="t('beat.openTitle')" @click="openPanel('beat')"><Icon name="wave" />{{ t('beat.open') }}</button>
          <div class="cr-note"><span>{{ !what ? t('home.nothing') : isClip ? t('home.makeNoteClip') : t('home.makeNote') }}</span>
            <span class="cr-links">
              <button v-if="what && !isClip" type="button" class="link-btn" :aria-expanded="fine" @click="fine ? (fine = false) : openFine()"><Icon name="sliders" :size="14" /> {{ fine ? t('home.fineFold') : t('home.fine') }}</button>
              <button type="button" class="link-btn quiet" :aria-expanded="panel === 'manual'" @click="openPanel('manual')">{{ t('home.ownPrompts') }}</button>
              <button v-if="!what || isClip" type="button" class="link-btn quiet" :aria-expanded="panel === 'clip'" @click="openPanel('clip')">{{ t('home.clipAll') }}</button></span></div>
        </div>
        <div v-if="runErr" class="cr-err" role="alert"><Icon name="warn" :size="16" /><span>{{ runErr }}</span><button type="button" class="link-btn" @click="runErr = ''">{{ t('home.got') }}</button></div>
      </div>

      <div v-if="panel" class="start-form" :class="`is-${panel}`">
        <button type="button" class="link-btn sf-fold" @click="panel = ''"><Icon name="collapse" :size="14" />{{ t('home.fold') }}</button>
        <ClipStart v-if="panel === 'clip'" />
        <BeatStart v-else-if="panel === 'beat'" />
        <template v-else>
          <div class="idea-head sf-head"><div class="title-row"><h1>{{ t('idea.how.manual') }}</h1><GuideButton guide="idea" /></div>
            <p>{{ t('idea.manualAbout') }}</p></div>
          <div class="sf-main">
            <label class="stack"><span class="lbl">{{ t('idea.name') }} <small>{{ t('idea.optional') }}</small> <HelpQ id="idea" term="Без сценариста" /></span>
              <input v-model="manualName" class="field-in" :placeholder="t('idea.manualNamePh')"></label>
            <div class="stack"><span class="lbl">{{ t('idea.length') }}</span>
              <div class="chips"><button v-for="s in LENGTHS" :key="s" type="button" class="chip" :class="{ on: manualSecs === s }" @click="manualSecs = s">{{ s >= 120 ? `${s / 60} ${t('common.min')}` : `${s} ${t('common.s')}` }}</button></div></div>
          </div>
          <div class="sf-side">
            <div class="stack"><span class="lbl">{{ t('idea.model') }}</span><ModelPick :model-value="f.video" compact @update:model-value="set('video', $event)" /></div>
          </div>
          <div class="sf-foot">
            <span class="foot-note">{{ t('idea.manualNote') }}</span>
            <button type="button" class="primary" :disabled="busy" @click="openManual"><Icon name="plus" />{{ t('idea.openBoard') }}</button>
          </div>
        </template>
      </div>
      <GraphStart />
    </section>

    <main class="main">
      <p v-if="!S.projects.length" class="shelf-empty">{{ t('idea.empty') }}</p>
      <Shelf v-if="S.projects.length" />
    </main>
  </div>
</template>

<style scoped>
.create-wrap { display: flex; flex-direction: column; gap: 14px; padding: 22px 36px 24px; border-bottom: 1px solid var(--rule); }
.create { container-type: inline-size; display: flex; flex-direction: column; gap: 16px; padding: 22px 26px 20px; border-radius: 18px; border: 1px solid var(--rule-2); background: var(--panel); }
.cr-head { display: flex; align-items: center; gap: 12px; }
.cr-head h1 { margin: 0; font-size: 28px; font-weight: 600; letter-spacing: -.4px; }
.cr-about { margin-left: 6px; color: var(--soft); font-size: 14px; }
.cr-guide { margin-left: auto; }
.l-short { display: none; }

/* the box: words and files in one field */
.cr-box { position: relative; display: flex; flex-direction: column; gap: 10px; padding: 16px 18px 14px; border: 1px solid var(--rule-input); border-radius: 14px; background: var(--field); }
.cr-box:focus-within { border-color: var(--faint); }
.cr-box.over { border-style: dashed; border-color: var(--accent); background: #211a2e; }
.cr-text { width: 100%; min-height: 54px; resize: vertical; border: 0; background: transparent; color: var(--text); font: 17px/1.45 var(--ui); outline: none; padding: 0; }
.cr-text::placeholder { color: var(--faint); }
.cr-example { margin-top: -4px; color: var(--faint); font-size: 12.5px; }
.cr-sources { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding-top: 8px; border-top: 1px dashed var(--rule-2); }
.src { position: relative; display: inline-flex; align-items: center; gap: 7px; min-height: 40px; padding: 0 14px 0 10px; border-radius: 99px; border: 1px solid var(--rule-2);
  background: var(--panel); color: var(--soft); font-size: 13.5px; cursor: pointer; }
.src:hover { border-color: var(--accent); color: var(--text); }
.src:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
.src > :deep(svg) { color: var(--accent-hi); }
.src-hint { color: var(--faint); font-size: 12.5px; }
.src-in { position: absolute; width: 1px; height: 1px; opacity: 0; overflow: hidden; pointer-events: none; }
.cr-or { margin-left: 4px; color: var(--faint); font-size: 12.5px; }
.cr-files { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.cr-file { display: inline-flex; align-items: center; gap: 8px; max-width: 100%; min-height: 40px; padding: 3px 6px 3px 10px; border-radius: 99px; border: 1px solid var(--rule-2); background: var(--panel); font-size: 13.5px; }
.cr-file > :deep(svg) { color: var(--accent-hi); flex: none; }
.cr-file b { font-weight: 500; min-width: 0; max-width: 26ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cr-file-t { color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.cr-file img { width: 26px; height: 26px; border-radius: 50%; object-fit: cover; flex: none; }
.cr-x { display: grid; place-items: center; flex: none; width: 30px; height: 30px; border: 0; border-radius: 50%; background: none; color: var(--muted); cursor: pointer; }
.cr-x:hover { background: var(--hover); color: #fff; }
.cr-add { position: relative; display: inline-flex; align-items: center; gap: 6px; min-height: 40px; padding: 0 14px; border-radius: 99px; border: 1px dashed var(--rule-3); color: var(--soft); font-size: 13.5px; cursor: pointer; }
.cr-add:hover { border-color: var(--accent); color: var(--text); }
.cr-add:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
.cr-drop-hint { position: absolute; inset: 0; display: grid; place-items: center; border-radius: 14px; background: rgba(33, 23, 47, .92); color: var(--accent-hi); font-size: 18px; font-weight: 600; pointer-events: none; }
.cr-drop-hint > div { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 6px; }
.cr-drop-hint small { flex: 1 1 100%; text-align: center; color: var(--soft); font-size: 13.5px; font-weight: 400; }
.cr-err { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-left: 3px solid var(--bad); border-radius: 0 8px 8px 0; background: rgba(239, 68, 68, .1); color: #fca5a5; font-size: 13.5px; }
.cr-err > :deep(svg) { flex: none; }
.cr-err .link-btn { margin-left: auto; flex: none; color: #fff; min-height: 32px; }

/* «Поняли так»: the slate under the box */
.cr-slate { position: relative; display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; font-size: 14.5px; }
.cr-lead { display: inline-flex; align-items: center; gap: 6px; color: var(--accent-hi); font-weight: 600; }
.cr-slate b { font-weight: 600; color: var(--text); }
.cr-slate-sub { color: var(--muted); font-size: 13px; }
.cr-change { display: inline-flex; align-items: center; gap: 4px; min-height: 36px; margin-left: 2px; padding: 0 12px; border-radius: 99px; border: 1px solid var(--rule-2); background: none; color: var(--soft); font-size: 13px; cursor: pointer; }
.cr-change:hover, .cr-change[aria-expanded="true"] { border-color: var(--accent); color: var(--text); }
.cr-menu { position: absolute; z-index: 20; top: calc(100% + 6px); left: 0; display: flex; flex-direction: column; min-width: 330px; max-width: 100%; padding: 6px; border-radius: 12px; border: 1px solid var(--rule-2); background: var(--panel); box-shadow: 0 12px 34px rgba(0, 0, 0, .45); }
.cr-menu button { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; min-height: 44px; padding: 8px 10px; border: 0; border-radius: 8px; background: none; color: var(--text); text-align: left; cursor: pointer; font: inherit; font-size: 14px; }
.cr-menu button:hover { background: var(--hover); }
.cr-menu button.on { background: var(--accent-bg); }
.cr-menu small { color: var(--muted); font-size: 12px; }

/* the one row of the big choices */
.cr-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; }
.cr-look { display: inline-flex; align-items: center; gap: 8px; max-width: 100%; }
.cr-grp { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; }
.cr-row .lbl { display: inline-flex; align-items: center; gap: 5px; margin: 0; }
.chip-t { color: var(--muted); font-variant-numeric: tabular-nums; }
.chip.on .chip-t { color: rgba(255, 255, 255, .8); }
.note { color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }
/* the own piece: ▶ right at the wave's left, where the eye already is */
.cr-wave { display: flex; align-items: flex-start; gap: 10px; }
.cr-wave > :last-child { flex: 1; min-width: 0; }
.cr-play { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 44px; height: 44px; margin-top: 6px;
  border-radius: 50%; border: 0; background: var(--grad); color: #fff; cursor: pointer; box-shadow: 0 4px 14px rgba(168, 85, 247, .3); }
.cr-play:focus-visible { outline: 2px solid var(--accent); box-shadow: 0 0 0 2px #fff; }
.cr-play.on { background: var(--field); color: var(--accent-hi); box-shadow: inset 0 0 0 2px var(--accent); }
.cr-own { padding-left: 54px; }
.cr-opens { margin: -6px 0 0; font-size: 12px; }
/* the small «?»: its tap zone grown to ~32 px without moving it */
.create :deep(.q) { position: relative; }
.create :deep(.q)::after { content: ""; position: absolute; inset: -7px; }

/* «Тонкая настройка»: what does not change the route */
.cr-fine { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; padding: 14px 0 4px; border-top: 1px solid var(--rule); }
.cr-fine-col { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.cr-fine-col .lbl { display: inline-flex; align-items: center; gap: 5px; margin: 0; }
.cr-fine-note { color: var(--muted); font-size: 12.5px; }

/* the actions */
.cr-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 14px 18px; padding-top: 2px; }
.cr-make { flex: none; width: auto; min-width: 250px; min-height: 54px; padding: 0 28px; font-size: 17px; border-radius: 99px; box-shadow: 0 8px 24px rgba(168, 85, 247, .25); }
.cr-make:focus-visible { outline: 2px solid var(--accent); box-shadow: 0 0 0 2px #fff; }
.cr-make.dim { opacity: .5; box-shadow: none; }
.cr-steps { gap: 8px; min-height: 54px; min-width: 170px; padding: 0 22px; justify-content: center; border-radius: 99px; font-size: 16px; }
.cr-note { display: flex; flex-direction: column; gap: 4px; flex: 1 1 320px; color: var(--muted); font-size: 13px; }
.cr-links { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; }
.cr-links .link-btn.quiet { color: var(--soft); font-weight: 400; }
.cr-links .link-btn { display: inline-flex; align-items: center; gap: 4px; min-height: 32px; margin: 0; }

@container (max-width: 760px) {
  .cr-fine { grid-template-columns: 1fr; }
}
/* a phone: the box full width, the ways in without their hints, the choices on their own lines, the buttons stuck to the bottom */
@container (max-width: 480px) {
  .create { gap: 14px; }
  .cr-head h1 { font-size: 24px; }
  .cr-about, .src-hint, .cr-slate-sub, .cr-or { display: none; }
  .cr-box { padding: 14px 14px 12px; }
  .cr-text { font-size: 16px; }
  .l-full { display: none; }
  .l-short { display: inline; }
  .cr-look { width: 100%; }
  .cr-look :deep(.lpk), .cr-look :deep(.lpk-btn) { width: 100%; }
  .cr-look :deep(.lpk-btn) { flex-wrap: wrap; justify-content: flex-start; min-height: 40px; padding: 6px 10px; row-gap: 2px; text-align: left; }
  .cr-look :deep(.lpk-down) { margin-left: auto; }
  .cr-grp > .lbl { display: none; }
  .cr-actions { position: sticky; bottom: 0; z-index: 5; margin: 0 -16px -14px; padding: 12px 16px 14px; background: var(--panel); border-radius: 0 0 18px 18px; }
  .cr-make, .cr-steps { flex: 1 1 100%; min-width: 0; }
}
@media (max-width: 760px) {
  .create-wrap { padding: 14px 16px 16px; }
  .create { padding: 16px 16px 14px; }
}
@media (prefers-reduced-motion: reduce) {
  .cr-box, .cr-drop-hint { transition: none; }
}
</style>
