<script setup lang="ts">
// Phase 11: the home's «Клип из песни». The song first: dropped here, it is analysed at once (its parts, the bars) and
// drawn; a click on it starts the clip at that bar, the length chips say how much; ▶ plays that stretch. Its words - recognised by a job
// (Demucs + Whisper) or typed - are the singing scenes' lines. Then who sings, the idea, the frame, the model, and
// «Расписать клип»: the scenes are cut on the song, the writer gives each a shot kind and content.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import HelpQ from './HelpQ.vue'
import GuideButton from './help/GuideButton.vue'
import ModelPick from './ModelPick.vue'
import LoraCard from './LoraCard.vue'
import SongStrip from './SongStrip.vue'
import { api, post } from '../lib/api'
import { S, banner, keep, onJobEnd } from '../lib/store'
import { ASPECTS, GENDERS, MODES } from '../lib/consts'
import { dec, mmss } from '../lib/format'
import type { Song } from '../lib/types'

const router = useRouter()
const { t } = useI18n()
const f = S.form
const set = (k: keyof typeof f, v: any) => { (f as any)[k] = v; keep() }
const song = ref<Song | null>(null)
const loading = ref(false)
const over = ref(false)
const err = ref('')
const busy = ref(false)
const text = ref('')
const LENS = computed<[number, string][]>(() => [[30, `30 ${t('common.s')}`], [45, `45 ${t('common.s')}`], [60, `1 ${t('common.min')}`],
  [90, `${dec(1.5)} ${t('common.min')}`], [0, t('idea.clip.wholeSong')]])

async function load(id: string) {
  if (!id) return
  try { song.value = await api<Song>(`/api/songs/${id}`); text.value = song.value.text } catch { song.value = null; set('song', '') }
}
async function upload(file?: File) {
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  loading.value = true
  try {
    song.value = await api<Song>('/api/songs', { method: 'POST', body: fd })
    text.value = song.value.text
    set('song', song.value.id)
    set('songFrom', 0)
  } catch (e) { banner((e as Error).message) } finally { loading.value = false }
}
const onDrop = (e: DragEvent) => { over.value = false; upload(e.dataTransfer?.files[0]) }

// the stretch of the song: from a bar, this long (0 = the whole song)
// what is asked: the length, or the whole song; the start moves back when it doesn't fit (as clip.fragment does)
const secs = computed(() => (song.value ? Math.max(4, f.songSecs ? Math.min(f.songSecs, song.value.duration) : song.value.duration) : 0))
const from = computed(() => (song.value ? Math.max(0, Math.min(f.songFrom, song.value.duration - secs.value)) : 0))
const to = computed(() => from.value + secs.value)
// ▶: the clip's stretch of the song, played here; while it plays a click inside the stretch seeks there, outside it
// moves the stretch and plays it from its new start
const audio = ref<HTMLAudioElement | null>(null)
const head = ref<number | null>(null)
function listen() {
  const a = audio.value
  if (!a || !song.value) return
  if (head.value !== null) { a.pause(); head.value = null; return }
  a.currentTime = from.value
  head.value = from.value
  a.play().catch(() => { head.value = null })
}
function seek(t: number) {
  if (audio.value) { audio.value.currentTime = t; head.value = t }
}
function onTime() {
  const a = audio.value
  if (!a || head.value === null) return
  if (a.currentTime >= to.value) { a.pause(); head.value = null } else head.value = a.currentTime
}
watch(from, (v) => { if (head.value !== null && audio.value) { audio.value.currentTime = v; head.value = v } })
watch(() => song.value?.id, () => { audio.value?.pause(); head.value = null })
const scenesAbout = computed(() => Math.max(1, Math.round(secs.value / 4)))
const sungIn = computed(() => (song.value?.lines || []).filter((l) => l.end > from.value && l.start < to.value).length)

// the words: a GPU job, or the user's own text (aligned on the recognised words)
const lyricsJob = computed(() => S.jobs.find((j) => j.kind === 'lyrics' && j.params.song === f.song && ['queued', 'running'].includes(j.status)))
async function recognise() {
  try { const j = await post(`/api/songs/${f.song}/lyrics`, {}); S.jobs = [...S.jobs, j] } catch (e) { banner((e as Error).message) }
}
async function saveText() {
  try { song.value = await api<Song>(`/api/songs/${f.song}/text`, { method: 'PUT', body: { text: text.value } }) } catch (e) { banner((e as Error).message) }
}
const textDirty = computed(() => song.value && text.value.trim() !== (song.value.text || '').trim())

// the singer's photo: the look of the hero, described by the writer (in a clip the scenes are cut on the bars, so
// it is not the first frame)
async function uploadPhoto(file?: File) {
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  try { set('photo', await api('/api/frames', { method: 'POST', body: fd })) } catch (e) { banner((e as Error).message) }
}
const sings = computed(() => (S.cfg?.video_models || []).find((m) => m.id === f.clipVideo))
const ltx23 = computed(() => (S.cfg?.video_models || []).find((m) => m.id === 'ltx23'))

// «Что пишет сценарист»: the hero's look (the writer's, the user's words, a photo), the story (the writer's, the idea as
// it is), the scenes (all; or the clip's skeleton first: «only the empty ones», «none»)
const LOOKS = ['writer', 'own', 'photo'] as const, STORIES = ['writer', 'idea'] as const, SCENES = ['all', 'empty', 'none'] as const
const look = computed(() => f.clipLook || (f.photo ? 'photo' : 'writer'))
const story = computed(() => f.clipStory || 'writer')
const scenes = computed(() => f.clipScenes || 'all')

async function write() {
  if (!song.value) { err.value = t('idea.clip.loadSong'); return }
  const people = f.mode !== 'none'
  if (people && look.value === 'own' && !(f.clipLookRu || '').trim()) { err.value = t('idea.clip.lookNeeded'); return }
  if (people && look.value === 'photo' && !f.photo) { err.value = t('idea.clip.photoNeeded'); return }
  if (story.value === 'idea' && !f.idea.trim()) { err.value = t('idea.clip.ideaNeeded'); return }
  err.value = ''
  busy.value = true
  const all = scenes.value === 'all'
  try {
    const r = await post('/api/clips', { song: f.song, start: from.value, seconds: secs.value, idea: f.idea, mode: f.mode, aspect: f.aspect,
      mood: 'Клип', photo: people && look.value === 'photo' && f.photo ? f.photo.name : null, model: S.llm || null, video_model: f.clipVideo || 'ltx23',
      look: people ? look.value : 'writer', look_ru: f.clipLookRu || '', gender: f.clipGender || 'female', story: story.value, scenes: scenes.value,
      // Krea and FLUX run only when the user asks (they can be started later on the storyboard)
      loras: f.loras || [], pic_loras: f.picLoras || {},
      draw_singer: all && look.value === 'writer' && f.clipSinger === true, frames: all && f.clipFrames === true, places: all && f.clipFrames === true && f.clipPlaces === true })
    if (r.job) S.jobs = [...S.jobs, r.job]
    router.push(`/p/${r.project}`)
  } catch (e) { err.value = (e as Error).message; busy.value = false }
}

let off: () => void
onMounted(() => { load(f.song); off = onJobEnd((j) => { if (j.kind === 'lyrics' && j.params.song === f.song) load(f.song) }) })
onUnmounted(() => { off?.(); audio.value?.pause() })
watch(() => f.song, (id) => { if (id && id !== song.value?.id) load(id) })
</script>

<template>
  <div class="idea-head sf-head"><div class="title-row"><h1>{{ t('idea.clip.title') }}</h1><GuideButton guide="idea" /></div>
    <p>{{ t('idea.clip.about') }}</p></div>

  <div class="sf-main">
  <div class="stack"><span class="lbl">{{ t('idea.clip.song') }} <HelpQ id="clip" term="Песня" /></span>
    <label v-if="!song" class="drop" :class="{ over }" @dragover.prevent="over = true" @dragleave="over = false" @drop.prevent="onDrop">
      <input type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg" hidden @change="upload(($event.target as HTMLInputElement).files?.[0])">
      <Icon name="music" :size="28" cls="muted-ic" />
      <span>{{ loading ? t('idea.clip.parsing') : t('idea.clip.drop') }}<small>{{ t('idea.clip.dropSub') }}</small></span>
    </label>
    <template v-else>
      <div class="song-head"><Icon name="music" :size="16" /><b :title="song.name">{{ song.name }}</b>
        <span class="muted">{{ mmss(song.duration) }} · {{ Math.round(song.bpm) }} BPM</span>
        <button type="button" class="btn song-play" :class="{ on: head !== null }" :title="t('idea.clip.listenTitle')" @click="listen">
          <Icon :name="head !== null ? 'stop' : 'play'" :size="13" />{{ head !== null ? t('idea.clip.listenStop') : t('idea.clip.listen') }}</button>
        <audio ref="audio" :src="`/api/songs/${song.id}/file`" preload="none" @timeupdate="onTime" @ended="head = null" @pause="head = null" />
        <label class="link-btn" style="cursor:pointer">{{ t('idea.clip.another') }}<input type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg" hidden @change="upload(($event.target as HTMLInputElement).files?.[0])"></label></div>
      <SongStrip :song="song" :from="from" :to="to" :head="head" editable @pick="set('songFrom', $event)" @seek="seek" />
      <div class="chips"><button v-for="[s, l] in LENS" :key="s" type="button" class="chip" :class="{ on: f.songSecs === s }" @click="set('songSecs', s)">{{ l }}</button>
        <span class="muted chips-note">{{ mmss(from) }}–{{ mmss(to) }} · ≈ {{ t('idea.scenesN', scenesAbout) }}</span></div>
      <p class="muted clip-hint">{{ t('idea.clip.clickWave') }}</p>
    </template>
  </div>

  <div v-if="song" class="stack"><span class="lbl">{{ t('idea.clip.words') }} <HelpQ id="clip" term="Слова" />
      <small>{{ song.recognised ? t('idea.clip.linesIn', { lines: t('idea.clip.lines', song.lines.length), n: sungIn }) : t('idea.clip.notRecognised') }}</small></span>
    <template v-if="!song.recognised">
      <p class="muted clip-hint">{{ t('idea.clip.recogniseHint') }}</p>
      <button type="button" class="btn" :disabled="!!lyricsJob" @click="recognise"><Icon name="quill" />{{ lyricsJob ? t('idea.clip.recognising') : t('idea.clip.recognise') }}</button>
    </template>
    <template v-else>
      <textarea v-model="text" class="field-in" rows="5" spellcheck="false" :aria-label="t('idea.clip.songWords')" />
      <div class="acts"><button type="button" class="btn" :disabled="!textDirty" @click="saveText"><Icon name="check" />{{ t('idea.clip.saveText') }}</button>
        <small class="muted">{{ t('idea.clip.saveTextNote') }}</small></div>
    </template>
  </div>
  </div>

  <div class="sf-mid">
  <label class="stack"><span class="lbl">{{ t('idea.idea') }} <small>{{ t('idea.optional') }}</small> <HelpQ id="clip" term="Идея клипа" /></span>
    <textarea class="field-in" rows="3" :value="f.idea" :placeholder="t('idea.clip.ideaPh')"
      @input="set('idea', ($event.target as HTMLTextAreaElement).value)" /></label>
  <div class="stack"><span class="lbl">{{ t('idea.who') }} <HelpQ id="idea" term="Кто в кадре" /></span>
    <div class="chips"><button v-for="[m, l] in MODES" :key="m" type="button" class="chip" :class="{ on: f.mode === m }" @click="set('mode', m)">{{ l }}</button></div></div>
  <!-- what the writer writes: the hero's look, the story, the scenes - the rest is the user's -->
  <div class="stack cw"><span class="lbl">{{ t('idea.clip.writes') }} <small>{{ t('idea.clip.writesSub') }}</small></span>
    <template v-if="f.mode !== 'none'">
      <div class="cw-row"><span>{{ t('idea.clip.lookLbl') }}</span>
        <div class="chips"><button v-for="k in LOOKS" :key="k" type="button" class="chip" :class="{ on: look === k }" @click="set('clipLook', k)">{{ t(`idea.clip.look.${k}`) }}</button></div></div>
      <template v-if="look === 'own'">
        <div class="cw-row"><span>{{ t('idea.clip.lookGender') }}</span>
          <select class="field-in cw-sel" :value="f.clipGender || 'female'" @change="set('clipGender', ($event.target as HTMLSelectElement).value)"><option v-for="[k, l] in GENDERS" :key="k" :value="k">{{ l }}</option></select></div>
        <textarea class="field-in" rows="2" :value="f.clipLookRu || ''" :placeholder="t('idea.clip.lookPh')" :aria-label="t('idea.clip.lookLbl')"
          @input="set('clipLookRu', ($event.target as HTMLTextAreaElement).value)" />
      </template>
      <template v-if="look === 'photo'">
        <label class="drop small"><input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="uploadPhoto(($event.target as HTMLInputElement).files?.[0])">
          <img v-if="f.photo" :src="f.photo.url" :alt="t('idea.clip.singerPhoto')"><Icon v-else name="user" :size="22" cls="muted-ic" />
          <span>{{ f.photo ? t('idea.photoLoaded') : t('idea.photoDrop') }}<small>{{ f.photo ? t('idea.clip.photoHero') : t('idea.clip.singerPhotoSub') }}</small></span></label>
        <button v-if="f.photo" type="button" class="ghost" @click="set('photo', null)">{{ t('idea.removePhoto') }}</button>
      </template>
    </template>
    <div class="cw-row"><span>{{ t('idea.clip.storyLbl') }}</span>
      <div class="chips"><button v-for="k in STORIES" :key="k" type="button" class="chip" :class="{ on: story === k }" @click="set('clipStory', k)">{{ t(`idea.clip.story.${k}`) }}</button></div></div>
    <div class="cw-row"><span>{{ t('idea.clip.scenesLbl') }}</span>
      <div class="chips"><button v-for="k in SCENES" :key="k" type="button" class="chip" :class="{ on: scenes === k }" @click="set('clipScenes', k)">{{ t(`idea.clip.scenes.${k}`) }}</button></div></div>
    <p v-if="scenes !== 'all'" class="muted clip-hint">{{ t('idea.clip.scenesNote') }}</p></div>
  <div v-if="f.mode !== 'none' && scenes === 'all'" class="stack"><span class="lbl">{{ t('idea.clip.after') }} <small>{{ t('idea.clip.afterSub') }}</small></span>
    <label v-if="look === 'writer'" class="check-row" :title="t('idea.clip.singerTitle')"><input type="checkbox" :checked="f.clipSinger === true" @change="set('clipSinger', ($event.target as HTMLInputElement).checked)">{{ t('idea.clip.singer') }}</label>
    <label class="check-row" :title="t('idea.clip.framesTitle')"><input type="checkbox" :checked="f.clipFrames === true" @change="set('clipFrames', ($event.target as HTMLInputElement).checked)">{{ t('idea.clip.frames') }}</label>
    <label class="check-row sub-check" :title="t('idea.clip.placesTitle')"><input type="checkbox" :disabled="f.clipFrames !== true" :checked="f.clipFrames === true && f.clipPlaces === true" @change="set('clipPlaces', ($event.target as HTMLInputElement).checked)">{{ t('idea.clip.places') }} <HelpQ id="look" term="Места" /></label></div>
  </div>

  <div class="sf-side">
  <div class="stack"><span class="lbl">{{ t('idea.frame') }}</span>
    <div class="chips"><button v-for="[a, w, h] in ASPECTS" :key="a" type="button" class="chip" :class="{ on: f.aspect === a }" @click="set('aspect', a)"><i class="box" :style="{ width: w + 'px', height: h + 'px' }" />{{ a }}</button></div></div>
  <div class="stack"><span class="lbl">{{ t('idea.model') }} <small>{{ t('idea.clip.modelLater') }}</small></span>
    <ModelPick :model-value="f.clipVideo" compact @update:model-value="set('clipVideo', $event)" />
    <p v-if="sings && !sings.track && ltx23 && f.mode !== 'none'" class="muted clip-hint"><Icon name="music" :size="13" /> {{ ltx23.missing.length ? t('idea.clip.singsNoWeights', { a: ltx23.name, b: sings.name }) : t('idea.clip.sings', { a: ltx23.name, b: sings.name }) }}</p></div>
  <LoraCard :video="f.clipVideo || 'ltx23'" :loras="f.loras || []" :pics="f.picLoras || {}"
    :off="{ krea: f.mode === 'none' || scenes !== 'all' || !((look === 'writer' && f.clipSinger === true) || (f.clipFrames === true && f.clipPlaces === true)), flux2: f.mode === 'none' || scenes !== 'all' || f.clipFrames !== true }"
    @update:loras="set('loras', $event)" @update:pics="set('picLoras', $event)" />
  </div>

  <div class="sf-foot">
    <div v-if="err" class="error">{{ err }}</div>
    <span class="foot-note">{{ song ? t(song.recognised ? 'idea.clip.writeNote' : 'idea.clip.writeNoteWords', { s: 10 + 4 * scenesAbout + (song.recognised ? 0 : 40) }) : t('idea.clip.songFirst') }}</span>
    <button type="button" class="primary" :disabled="busy || !song" @click="write"><Icon name="spark" />{{ t('idea.clip.write') }}</button>
  </div>
</template>
