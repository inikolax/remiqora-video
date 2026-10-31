<script setup lang="ts">
// 4. The montage (#/p/<id>/edit, phase 8; #/g/<id>/edit/<node> - a graph's «Монтаж»), one screen high as in an
// editing program: a bar (back, the name, whether the video is built by this montage, one main button: «Собрать
// ролик», or «Открыть ролик» once it is built by this montage), the viewer
// over the timeline (a border dragged between them), the panel a column beside both, the whole height, in tabs
// (Клип / Цвет / Звук / Вывод) that follow the selection. The shots of the storyboard on a timeline - trimmed, cut in two, copied,
// slower or faster, joined by a cut, a dissolve or through black, the chains moved as one, the scenes' sound with
// them, sounds from files and your track under them - played in the browser and built into the video by «Собрать
// ролик» (nothing is shot again). Every change can be undone.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from '../components/Icon.vue'
import SidePanel from '../components/SidePanel.vue'
import GuideButton from '../components/help/GuideButton.vue'
import EditPlayer from '../components/edit/EditPlayer.vue'
import EditTimeline from '../components/edit/EditTimeline.vue'
import EditInspector from '../components/edit/EditInspector.vue'
import { ED, FRAME, addSound, cutsOnBeats, tapBeat, duplicate, flushEdit, loadBeats, loadEdit, redo, remove, setMagnet, split, tc, undo } from '../lib/edit'
import { api } from '../lib/api'
import { P, openProject, reloadProject } from '../lib/project'
import { S, banner, onJobEnd } from '../lib/store'
import { QL } from '../lib/consts'
import { mins } from '../lib/format'
import { BUILD_SAY, build, buildEst, buildState } from '../lib/editBuild'
import '../styles/edit.css'

const props = defineProps<{ id: string; node?: string }>()   // node: a graph's «Монтаж» (#/g/<id>/edit/<node>)
const router = useRouter()
const { t } = useI18n()
const loaded = ref(false)
const player = ref<InstanceType<typeof EditPlayer> | null>(null)
const aspect = computed(() => P.proj?.settings.aspect || '16:9')
const zoom = (k: number) => { ED.px = Math.max(4, Math.min(240, ED.px * k)) }
const fit = () => { const w = (document.querySelector('.et')?.clientWidth || 900) - 140; ED.px = Math.max(4, Math.min(160, w / Math.max(1, ED.duration))) }
// your track from a file: the panel's upload (whatever tab it shows)
const inspector = ref<InstanceType<typeof EditInspector> | null>(null)
const trackIn = ref<HTMLInputElement | null>(null)
function addTrack() { trackIn.value?.click() }
// a sound from a file onto the «Звуки» lane, where the playhead is
const soundIn = ref<HTMLInputElement | null>(null)
async function soundUp(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  try { addSound(await api(`/api/projects/${props.id}/sounds`, { method: 'POST', body: fd })) } catch (err) { banner((err as Error).message) }
}
const nothing = (what: string) => banner(what)

// the border of the viewer and the timeline: dragged, the viewer's height (remembered); null - the timeline takes
// what it needs, the viewer the rest
const SPLIT = 'h3_edit_split'
const top = ref<HTMLElement | null>(null)
const topH = ref<number | null>((() => { try { return +(localStorage.getItem(SPLIT) || '') || null } catch { return null } })())
watch(topH, (h) => { try { if (h === null) localStorage.removeItem(SPLIT); else localStorage.setItem(SPLIT, String(h)) } catch { /* not remembered */ } })
const clampTop = (h: number) => { const room = (top.value?.parentElement?.clientHeight || innerHeight) - 200; return Math.round(Math.max(200, Math.min(room, h))) }
function splitDown(e: PointerEvent) {
  if (e.button !== 0 || !top.value) return
  e.preventDefault()
  const bar = e.currentTarget as HTMLElement, y0 = top.value.getBoundingClientRect().top
  bar.setPointerCapture(e.pointerId)
  const move = (ev: PointerEvent) => { topH.value = clampTop(ev.clientY - y0) }
  const up = () => { bar.removeEventListener('pointermove', move); bar.removeEventListener('pointerup', up) }
  bar.addEventListener('pointermove', move)
  bar.addEventListener('pointerup', up)
}
function splitKey(e: KeyboardEvent) {
  if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
  e.preventDefault()
  e.stopPropagation()
  topH.value = clampTop((topH.value ?? top.value?.offsetHeight ?? 400) + (e.key === 'ArrowUp' ? -24 : 24))
}
// the track changed (added, another offset): its beats again
watch(() => [ED.view?.track?.file, ED.view?.track?.offset], (n, o) => { if (o && n.join() !== o.join()) loadBeats() })
// the panel's «Проиграть стык»: from a moment before the seam
watch(() => ED.cue, (t) => { if (t === null) return; ED.cue = null; player.value?.pause(); ED.t = t; player.value?.play() })

// the keys: Space plays, arrows step a frame (Shift - a second), Home / End
const typing = (e: KeyboardEvent) => e.target instanceof Element && !!e.target.closest('input, textarea, select, [contenteditable]')
function onKey(e: KeyboardEvent) {
  if (typing(e) || !loaded.value || e.altKey) return
  if (e.ctrlKey || e.metaKey) {   // by the key's place: Ctrl+Z is Ctrl+Я on the Russian layout
    if (e.code === 'KeyZ') { e.preventDefault(); player.value?.pause(); if (!(e.shiftKey ? redo() : undo())) nothing(e.shiftKey ? t('edit.nothingRedo') : t('edit.nothingUndo')) }
    else if (e.code === 'KeyY') { e.preventDefault(); player.value?.pause(); if (!redo()) nothing(t('edit.nothingRedo')) }
    else if (e.code === 'KeyD') { e.preventDefault(); if (!duplicate()) nothing(t('edit.pickClip')) }
    return
  }
  const step = e.shiftKey ? 1 : FRAME
  if (e.code === 'Space') { e.preventDefault(); player.value?.toggle() }
  else if (e.code === 'KeyS') { e.preventDefault(); player.value?.pause(); if (!split()) nothing(t('edit.cantSplit')) }
  else if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); player.value?.pause(); remove() }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); player.value?.pause(); ED.t = Math.max(0, ED.t - step) }
  else if (e.key === 'ArrowRight') { e.preventDefault(); player.value?.pause(); ED.t = Math.min(ED.duration, ED.t + step) }
  else if (e.key === 'Home') { e.preventDefault(); ED.t = 0 }
  else if (e.key === 'End') { e.preventDefault(); ED.t = ED.duration }
  else if (e.code === 'KeyM') { e.preventDefault(); setMagnet(!ED.magnet) }
  else if (e.code === 'KeyB' && ED.beats.length) { e.preventDefault(); tapBeat() }
  else if (e.key === 'Escape') ED.sel = null
  else if (e.key === '?') { e.preventDefault(); S.keys = true }
}

let off: (() => void) | undefined
onMounted(async () => {
  ED.sel = null
  ED.t = 0
  ED.playing = false
  try {
    await openProject(props.id)
    if (!props.node && !P.proj!.plan) { router.replace(`/p/${props.id}`); return }
    await loadEdit(props.id, props.node || '')
    loadBeats()
  } catch (e) { banner((e as Error).message); router.push('/'); return }
  loaded.value = true
  addEventListener('keydown', onKey)
  // a render of this project ended: the shots and the built video are new
  off = onJobEnd((j) => { if (j.params?.project === props.id) { reloadProject(); loadEdit(props.id, props.node || '') } })
})
onUnmounted(() => { removeEventListener('keydown', onKey); off?.(); flushEdit() })
</script>

<template>
  <div v-if="loaded && P.proj && ED.view" class="edit-screen" :class="{ sized: topH !== null }" :style="topH !== null ? { '--top': `${topH}px` } : {}">
    <!-- the bar: where it came from, what it is, whether the video is built by it -->
    <header class="edit-bar">
      <router-link class="ghost eb-back" :to="node ? `/g/${id}` : `/p/${id}`" :title="node ? t('edit.toGraph') : t('edit.toBoard')"><Icon name="back" />{{ node ? t('edit.graph') : t('edit.board') }}</router-link>
      <div class="eb-name">
        <h1>{{ node ? ED.view.title || t('edit.montage') : P.proj.name }}</h1>
        <span class="eb-facts"><b>{{ tc(ED.duration) }}</b><span>{{ t('edit.clips', ED.clips.length) }}</span><span>{{ QL[ED.view.quality] }}</span>
          <span class="eb-save" :class="{ on: ED.saving }">{{ ED.saving ? t('edit.saving') : t('edit.saved') }}</span></span>
      </div>
      <span class="eb-state" :class="buildState" :title="buildState === 'error' ? ED.view.error || '' : ''">
        <Icon :name="buildState === 'same' ? 'check' : buildState === 'building' ? 'clapper' : 'warn'" :size="14" />{{ BUILD_SAY[buildState] }}</span>
      <!-- one main action: build the video, or - built by this montage - open it -->
      <router-link v-if="buildState === 'same' && !node" class="primary eb-build" :to="`/p/${id}/video`" :title="t('edit.videoTitle')"><Icon name="play" :size="18" />{{ t('edit.openVideo') }}</router-link>
      <button v-else type="button" class="primary eb-build" :disabled="buildState === 'same' || buildState === 'building'" @click="build">
        <Icon name="film" :size="18" />{{ ED.view.to_shoot ? t('edit.shootBuild') : t('edit.buildVideo') }}<small v-if="buildEst && buildState !== 'same' && buildState !== 'building'">~{{ mins(buildEst.seconds) }}</small></button>
      <div class="eb-tools">
        <button type="button" class="ghost" :aria-label="t('edit.keys')" :title="t('edit.keysTitle')" @click="S.keys = true"><Icon name="grip" :size="16" /></button>
        <GuideButton guide="edit" />
      </div>
    </header>

    <!-- the work: the viewer over the timeline; the panel a column beside them, the whole height -->
    <div class="edit-body"><div class="edit-work">
      <section ref="top" class="edit-view" :aria-label="t('edit.viewer')">
        <div class="edit-stage"><EditPlayer ref="player" :pid="id" :aspect="aspect" /></div>
        <div class="edit-transport">
          <button type="button" class="ghost" :aria-label="t('edit.toStart')" :title="t('edit.toStartTitle')" @click="ED.t = 0"><Icon name="back" /></button>
          <button type="button" class="primary round" :aria-label="ED.playing ? t('edit.pause') : t('edit.play')" :title="ED.playing ? t('edit.pauseTitle') : t('edit.playTitle')" @click="player?.toggle()">
            <Icon :name="ED.playing ? 'pause' : 'play'" :size="18" /></button>
          <span class="edit-tc">{{ tc(ED.t) }} <small>/ {{ tc(ED.duration) }}</small></span>
        </div>
      </section>

    <div class="edit-split" role="separator" aria-orientation="horizontal" tabindex="0" :aria-valuenow="topH ?? undefined"
      :aria-label="t('edit.splitLabel')" :title="t('edit.splitTitle')"
      @pointerdown="splitDown" @dblclick="topH = null" @keydown="splitKey" />

    <!-- the timeline and its tools -->
    <section class="edit-lower" :aria-label="t('edit.timeline')">
      <div class="edit-tools">
        <button type="button" class="ghost" :disabled="!ED.undo" :title="t('edit.undoTitle')" :aria-label="t('edit.undo')" @click="player?.pause(); undo()"><Icon name="reset" /></button>
        <button type="button" class="ghost" :disabled="!ED.redo" :title="t('edit.redoTitle')" :aria-label="t('edit.redo')" @click="player?.pause(); redo()"><Icon name="retake" /></button>
        <span class="sep" />
        <button type="button" class="ghost" :title="t('edit.splitClip')" @click="player?.pause(); split() || nothing(t('edit.cantSplit'))"><Icon name="cut" />{{ t('edit.cut') }}</button>
        <template v-if="ED.beats.length">
          <span class="sep" />
          <button type="button" class="ghost" :aria-pressed="ED.magnet" :title="t('edit.magnetTitle', { bpm: ED.bpm ? ` · ${ED.bpm} BPM` : '' })" @click="setMagnet(!ED.magnet)"><Icon name="music" />{{ t('edit.magnet') }}</button>
          <button type="button" class="ghost" :title="t('edit.beatsTitle')" @click="player?.pause(); cutsOnBeats() || nothing(t('edit.onBeatsDone'))"><Icon name="splice" />{{ t('edit.onBeats') }}</button>
          <button type="button" class="ghost" :title="t('edit.tapTitle')" @click="tapBeat()"><Icon name="dot" />{{ t('edit.tap') }}<b v-if="ED.taps.length || ED.fixed" class="eb-n">{{ ED.taps.length || ED.fixed }}</b></button>
          <button v-if="ED.fixed || ED.taps.length" type="button" class="ghost" :title="t('edit.tapResetTitle')" @click="tapBeat(true)"><Icon name="reset" />{{ t('edit.tapReset') }}</button>
        </template>
        <span class="grow" />
        <button type="button" class="ghost" :aria-label="t('edit.zoomOut')" :title="t('edit.zoomOutTitle')" @click="zoom(1 / 1.4)"><Icon name="minus" /></button>
        <button type="button" class="ghost" @click="fit"><Icon name="expand" />{{ t('edit.whole') }}</button>
        <button type="button" class="ghost" :aria-label="t('edit.zoomIn')" :title="t('edit.zoomInTitle')" @click="zoom(1.4)"><Icon name="plus" /></button>
      </div>
      <EditTimeline :pid="id" @add-track="addTrack" @add-sound="soundIn?.click()" />
      <input ref="soundIn" type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg" hidden @change="soundUp">
      <input ref="trackIn" type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg" hidden @change="inspector?.upload($event)">
    </section>
    </div>
    <SidePanel id="edit" class="side right edit-side" :label="t('edit.montage')" :width="380"><EditInspector ref="inspector" @add-sound="soundIn?.click()" /></SidePanel></div>
  </div>
</template>
