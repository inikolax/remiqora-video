<script setup lang="ts">
// 1. The home: four ways to start as tiles on top - the writer (what the video is about), a clip from a song, your own
// prompts (an empty storyboard), a graph (a canvas, from a template); the chosen one opens its form across the whole
// width under them (what it starts from on the left, the frame and the model on the right, the button at the bottom
// right). The home opens folded - the tiles and the shelf of your videos under them: a search, a filter by kind, each
// with its cover, its kind and its state; a click on the open tile or «Свернуть» folds the form again. The four steps of a video only while the shelf is empty.
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from '../components/Icon.vue'
import GuideButton from '../components/help/GuideButton.vue'
import HelpQ from '../components/HelpQ.vue'
import { api, post } from '../lib/api'
import ModelPick from '../components/ModelPick.vue'
import LoraCard from '../components/LoraCard.vue'
import ClipStart from '../components/ClipStart.vue'
import GraphStart from '../components/GraphStart.vue'
import Shelf from '../components/Shelf.vue'
import { S, banner, keep, loadProjects, onJobEnd } from '../lib/store'
import { ASPECTS, LENGTHS, MODES } from '../lib/consts'
import { moodName } from '../lib/moods'

const router = useRouter()
const { t } = useI18n()
const f = S.form
// the scenes the grid will make (planner/grid.lengths): 5 s each, or the model's longer scene (LTX: 10 s) and a 5 s rest
const sceneSecs = computed(() => (S.cfg?.video_models || []).find((m) => m.id === (f.video || 'h3'))?.grid_seconds || 5)
const lens = computed(() => {
  const total = Math.max(1, Math.round(f.seconds / 5)) * 5, k = sceneSecs.value
  return [...Array(Math.floor(total / k)).fill(k), ...(total % k ? [total % k] : [])]
})
const n = computed(() => lens.value.length)
const lensText = computed(() => (sceneSecs.value === 5 ? (f.manual ? t('idea.lensEach', { s: 5 }) : '')
  : lens.value.every((x) => x === sceneSecs.value) ? t('idea.lensEach', { s: sceneSecs.value }) : t('idea.lensSum', { sum: lens.value.join(' + ') })))
const err = ref('')
const busy = ref(false)
const ideaEl = ref<HTMLElement | null>(null)
const over = ref(false)
const set = (k: keyof typeof f, v: any) => { (f as any)[k] = v; keep() }

// the photo: the first frame of the video (the video model animates it, the writer goes on from it) or only the hero's look
// described in words; without people it can only be the first frame
const ratioOf = (a: string) => { const [w, h] = a.split(':').map(Number); return w / h }
const photoStarts = computed(() => !!f.photo && (f.mode === 'none' || f.photoRole !== 'hero'))
const near = computed(() => {
  const r = f.photo?.ratio
  return r ? ASPECTS.map((a) => a[0]).sort((a, b) => Math.abs(Math.log(ratioOf(a) / r)) - Math.abs(Math.log(ratioOf(b) / r)))[0] : null
})
const crops = computed(() => photoStarts.value && f.photo?.ratio && Math.abs(Math.log(ratioOf(f.aspect) / f.photo.ratio)) > 0.12)
const photoNote = computed(() => (!f.photo ? t('idea.photoNoteNone')
  : photoStarts.value ? t('idea.photoNoteStart')
    : t('idea.photoNoteHero')))

async function uploadPhoto(file?: File) {
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  try {
    const ph = await api('/api/frames', { method: 'POST', body: fd })
    ph.ratio = await new Promise((ok) => { const img = new Image(); img.onload = () => ok(img.naturalWidth / img.naturalHeight); img.onerror = () => ok(null); img.src = ph.url })
    set('photo', ph)
  } catch (e) { banner((e as Error).message) }
}
const onDrop = (e: DragEvent) => { over.value = false; uploadPhoto(e.dataTransfer?.files[0]) }

async function write() {
  const manual = !!f.manual
  err.value = ''
  if (!manual && f.idea.trim().length < 3) { err.value = t('idea.writeIdea'); ideaEl.value?.focus(); return }
  busy.value = true
  try {
    const r = await post('/api/projects', { idea: f.idea, seconds: f.seconds, mode: manual ? 'one' : f.mode, aspect: f.aspect,
      mood: manual ? '' : f.mood, music: manual ? '' : f.music,
      photo: f.photo && !manual && (f.mode !== 'none' || photoStarts.value) ? f.photo.name : null, photo_start: !manual && photoStarts.value,
      model: S.llm || null, manual, video_model: f.video || 'h3', loras: f.loras || [], pic_loras: f.picLoras || {} })
    if (r.job) S.jobs = [...S.jobs, r.job]
    router.push(`/p/${r.project}`)
  } catch (e) { err.value = (e as Error).message; busy.value = false }
}

// how to start: the writer, a clip from a song (phase 11), your own prompts or a graph; the open tile again folds the form
type How = 'writer' | 'clip' | 'manual' | 'graph'
const how = computed<How>(() => (f.graph ? 'graph' : f.clip ? 'clip' : f.manual ? 'manual' : 'writer'))
const WAYS: [How, string][] = [['writer', 'quill'], ['clip', 'music'], ['manual', 'pen'], ['graph', 'layers']]
const wayName = (h: How) => (h === 'graph' ? t('idea.graph') : t(`idea.how.${h}`))
const folded = ref(true)
async function setHow(h: How) {
  if (h === how.value && !folded.value) { folded.value = true; return }
  folded.value = false
  set('graph', h === 'graph'); set('manual', h === 'manual'); set('clip', h === 'clip')
  await nextTick(); if (h === 'writer' || h === 'manual') ideaEl.value?.focus()
}

// a writer's job just ended: the videos' badges and names change
let off: () => void
onMounted(() => { loadProjects(); off = onJobEnd(() => loadProjects()) })
onUnmounted(() => off?.())
</script>

<template>
  <div class="home">
    <section class="start" :class="{ folded }">
      <div class="ways" role="radiogroup" :aria-label="t('idea.howStart')">
        <button v-for="[h, ic] in WAYS" :key="h" type="button" role="radio" :aria-checked="!folded && how === h" :aria-expanded="!folded && how === h"
          class="way" :class="{ on: !folded && how === h }" @click="setHow(h)">
          <span class="way-ic"><Icon :name="ic" :size="20" /></span>
          <span><b>{{ wayName(h) }}</b><small>{{ t(`idea.how.${h}Long`) }}</small></span>
        </button>
      </div>

      <div v-if="!folded" class="start-form" :class="`is-${how}`">
        <button type="button" class="link-btn sf-fold" :title="t('idea.foldTitle')" @click="folded = true"><Icon name="collapse" :size="14" />{{ t('idea.fold') }}</button>
        <ClipStart v-if="how === 'clip'" />
        <GraphStart v-else-if="how === 'graph'" />
        <template v-else-if="f.manual">
          <div class="idea-head sf-head"><div class="title-row"><h1>{{ t('idea.how.manual') }}</h1><GuideButton guide="idea" /></div>
            <p>{{ t('idea.manualAbout') }}</p></div>
          <div class="sf-main">
            <label class="stack"><span class="lbl">{{ t('idea.name') }} <small>{{ t('idea.optional') }}</small> <HelpQ id="idea" term="Без сценариста" /></span>
              <input ref="ideaEl" class="field-in" :value="f.idea" :placeholder="t('idea.manualNamePh')" @input="set('idea', ($event.target as HTMLInputElement).value)"></label>
          </div>
        </template>
        <template v-else>
          <div class="idea-head sf-head"><div class="title-row"><h1>{{ t('idea.title') }}</h1><GuideButton guide="idea" /></div>
            <p>{{ t('idea.about', { s: sceneSecs }) }}</p></div>
          <div class="sf-main">
            <label class="stack"><span class="lbl">{{ t('idea.idea') }} <HelpQ id="idea" term="Идея" /></span>
              <textarea ref="ideaEl" class="field-in" rows="5" :value="f.idea" :placeholder="t('idea.ideaPh')"
                @input="set('idea', ($event.target as HTMLTextAreaElement).value)" /></label>
            <div class="stack"><span class="lbl">{{ t('idea.photo') }} <small>{{ t('idea.optional') }}</small> <HelpQ id="idea" term="Фото" /></span>
              <label class="drop" :class="{ over }" @dragover.prevent="over = true" @dragleave="over = false" @drop.prevent="onDrop">
                <input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="uploadPhoto(($event.target as HTMLInputElement).files?.[0])">
                <img v-if="f.photo" :src="f.photo.url" :alt="t('idea.photoAlt')"><Icon v-else name="image" :size="28" cls="muted-ic" />
                <span>{{ f.photo ? t('idea.photoLoaded') : t('idea.photoDrop') }}<small>{{ photoNote }}</small></span>
              </label>
              <div v-if="f.photo && f.mode !== 'none'" class="seg" role="radiogroup" :aria-label="t('idea.photoRole')">
                <button type="button" role="radio" :aria-checked="photoStarts" :class="{ on: photoStarts }" @click="set('photoRole', 'start')">{{ t('idea.roleStart') }}<small>{{ t('idea.roleStartSub') }}</small></button>
                <button type="button" role="radio" :aria-checked="!photoStarts" :class="{ on: !photoStarts }" @click="set('photoRole', 'hero')">{{ t('idea.roleHero') }}<small>{{ t('idea.roleHeroSub') }}</small></button></div>
              <div v-if="crops" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('idea.crops', { aspect: f.aspect }) }}</span>
                <button v-if="near !== f.aspect" type="button" class="link-btn" @click="set('aspect', near)">{{ t('idea.take', { aspect: near }) }}</button></div>
              <button v-if="f.photo" type="button" class="ghost" @click="set('photo', null)">{{ t('idea.removePhoto') }}</button>
            </div>
          </div>
        </template>

        <template v-if="how === 'writer' || how === 'manual'">
          <div class="sf-mid">
            <div class="stack"><span class="lbl">{{ t('idea.length') }} <HelpQ id="idea" term="Длина" /></span>
              <div class="chips"><button v-for="s in LENGTHS" :key="s" type="button" class="chip" :class="{ on: f.seconds === s }" @click="set('seconds', s)">{{ s >= 120 ? `${s / 60} ${t('common.min')}` : `${s} ${t('common.s')}` }}</button>
                <span class="muted chips-note">= {{ t('idea.scenesN', n) }}{{ lensText }}</span></div></div>
            <template v-if="!f.manual">
              <div class="stack"><span class="lbl">{{ t('idea.mood') }} <HelpQ id="idea" term="Настроение" /></span>
                <div class="chips"><button v-for="m in S.moods" :key="m" type="button" class="chip" :class="{ on: f.mood === m }" @click="set('mood', m)">{{ moodName(m) }}</button></div></div>
              <div class="stack"><span class="lbl">{{ t('idea.who') }} <HelpQ id="idea" term="Кто в кадре" /></span>
                <div class="chips"><button v-for="[m, l] in MODES" :key="m" type="button" class="chip" :class="{ on: f.mode === m }" @click="set('mode', m)">{{ l }}</button></div></div>
              <label class="stack"><span class="lbl">{{ t('idea.music') }} <small>{{ t('idea.musicSub') }}</small> <HelpQ id="idea" term="Музыка и звук" /></span>
                <input class="field-in" :value="f.music" :placeholder="t('idea.musicPh')" @input="set('music', ($event.target as HTMLInputElement).value)"></label>
            </template>
          </div>
          <div class="sf-side">
            <div class="stack"><span class="lbl">{{ t('idea.frame') }} <HelpQ id="idea" term="Кадр" /></span>
              <div class="chips"><button v-for="[a, w, h] in ASPECTS" :key="a" type="button" class="chip" :class="{ on: f.aspect === a }" @click="set('aspect', a)"><i class="box" :style="{ width: w + 'px', height: h + 'px' }" />{{ a }}</button></div></div>
            <div class="stack"><span class="lbl">{{ t('idea.model') }} <small>{{ t('idea.modelSets', { s: sceneSecs }) }}</small> <HelpQ id="idea" term="Модель" /></span><ModelPick :model-value="f.video" compact @update:model-value="set('video', $event)" /></div>
            <LoraCard :video="f.video || 'h3'" :loras="f.loras || []" :pics="f.picLoras || {}" @update:loras="set('loras', $event)" @update:pics="set('picLoras', $event)" />
          </div>
          <div class="sf-foot">
            <div v-if="err" class="error">{{ err }}</div>
            <span class="foot-note">{{ f.manual ? t('idea.manualNote') : t('idea.writerNote', { s: 10 + 3 * n }) }}</span>
            <button v-if="f.manual" type="button" class="primary" :disabled="busy" @click="write"><Icon name="plus" />{{ t('idea.openBoard') }}</button>
            <button v-else type="button" class="primary" :disabled="busy" @click="write"><Icon name="spark" />{{ t('idea.writeScenes') }}</button>
          </div>
        </template>
      </div>
    </section>

    <main class="main">
      <p v-if="!S.projects.length" class="shelf-empty">{{ t('idea.empty') }}</p>
      <section v-if="!S.projects.length" class="how">
        <template v-if="f.manual"><div><b>{{ t('idea.steps.m1') }}</b><span>{{ t('idea.steps.m1Sub') }}</span></div>
          <div><b>{{ t('idea.steps.s2') }}</b><span>{{ t('idea.steps.m2Sub') }}</span></div></template>
        <template v-else><div><b>{{ t('idea.steps.s1') }}</b><span>{{ t('idea.steps.s1Sub') }}</span></div>
          <div><b>{{ t('idea.steps.s2') }}</b><span>{{ t('idea.steps.s2Sub', { s: sceneSecs }) }}</span></div></template>
        <div><b>{{ t('idea.steps.s3') }}</b><span>{{ t('idea.steps.s3Sub') }}</span></div>
        <div><b>{{ t('idea.steps.s4') }}</b><span>{{ t('idea.steps.s4Sub') }}</span></div>
      </section>
      <Shelf v-if="S.projects.length" />
    </main>
  </div>
</template>
