<script setup lang="ts">
// The montage's panel, in four tabs - the selection opens its own: «Клип» - the selected clip (its trims, its take,
// its speed and level, the seam before it in a line, cut / copy / remove, «Как было»), a seam (the two clips it joins,
// what the join is and why it jumps, «Вернуть стык», the transition and its length, «Проиграть стык») or a piece
// «Поверх»; «Цвет» - the look over the video and the precise correction of the clip, its scene or the whole video;
// «Звук» - a sound from a file (where, how loud, its fades) or the music lane (your track: level, the scenes' sound
// under it, where it starts, its fades, how much it gives way to the scenes); «Вывод» - the montage itself: whether
// the video is built by it (the bar above has the one main button), the seams that jump, the scenes taken out,
// «Как в раскадровке», DaVinci Resolve.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import HelpQ from '../HelpQ.vue'
import { COLOR_DEFAULT, ED, FRAME, MIN_CLIP, SEAM, SEAM_ICON, SEAM_NAME, SPEEDS, TD, TR_NAME, clipOf, duplicate, fileUrl, flushEdit, mendSeam, overlayOf, overlayScenes, remove, resetClip, resetEdit, restoreScene, seamKind, seamOf, seamWhy, setOverlayScene, setTake, setTr, soundOf, split, tc, touch, trim, trimOverlay, xn, type Clip, type ClipColor, type Overlay } from '../../lib/edit'
import { P, projectCall } from '../../lib/project'
import { api } from '../../lib/api'
import { banner } from '../../lib/store'
import { QL } from '../../lib/consts'
import { dec } from '../../lib/format'
import { buildState, graphEdit as graph } from '../../lib/editBuild'

const router = useRouter()
const { t } = useI18n()
const emit = defineEmits<{ addSound: [] }>()
const c = computed(() => (ED.sel && ED.sel !== 'music' ? clipOf(ED.sel) : null))
type Tab = 'clip' | 'color' | 'sound' | 'out'
const TABS: { k: Tab; icon: string }[] = [{ k: 'clip', icon: 'cut' }, { k: 'color', icon: 'image' }, { k: 'sound', icon: 'music' }, { k: 'out', icon: 'export' }]
const tab = ref<Tab>('out')
// a selection opens its tab: a sound or the track - «Звук», a clip, a seam, «Поверх» - «Клип» (a clip picked while
// «Цвет» is open stays there - its colour is what is being set); nothing selected leaves «Клип» for «Вывод»
watch(() => ED.sel, (s) => {
  if (!s) { if (tab.value === 'clip') tab.value = 'out'; return }
  if (s === 'music' || soundOf(s)) tab.value = 'sound'
  else if (!(tab.value === 'color' && clipOf(s))) tab.value = 'clip'
}, { immediate: true })
watch(() => c.value?.id, (id) => { ED.colorScope = id ? 'clip' : 'video'; ED.colorSceneId = c.value?.scene || null }, { immediate: true })
const snd = computed(() => soundOf(ED.sel))
// «Поверх»: the selected overlay - which scene and take, from which second of the video, which piece of the shot
const ovl = computed(() => overlayOf(ED.sel))
function setOverStart(e: Event) {
  const o = ovl.value, val = parseFloat((e.target as HTMLInputElement).value.replace(',', '.'))
  if (o && !Number.isNaN(val)) { o.start = Math.max(0, val); trimOverlay(o, 'out', o.out); touch(150) }
}
function setOverTime(o: Overlay, side: 'in' | 'out', e: Event) {
  const val = parseFloat((e.target as HTMLInputElement).value.replace(',', '.'))
  if (!Number.isNaN(val)) { const st = o.start; trimOverlay(o, side, val); o.start = st; touch(150) }
}
const setOverTake = (o: Overlay, seed: number | null) => { o.take = seed; o.file = null; o.png = null; touch(50) }
// the scenes taken out of the video (they stay in the storyboard): their numbers, from the project's plan
const offScenes = computed(() => ED.off.map((id) => ({ id, n: (P.proj?.plan?.scenes || []).findIndex((s: any) => s.id === id) + 1, name: offNames.value[id] }))
  .filter((x) => x.n > 0 || x.name))
// a scene taken out, by its name (a graph's: its node's title)
const offNames = computed<Record<string, string>>(() => (v.value as any)?.off_names || {})
const playheadIn = computed(() => !!c.value && ED.t > c.value.start + MIN_CLIP / c.value.speed && ED.t < c.value.start + c.value.dur - MIN_CLIP / c.value.speed)
// the scene's takes (from the server's view: whether each is shot, its frame); the clip shows the chosen one or its own
const sceneTakes = computed(() => c.value?.take_list || [])
const chosenSeed = computed(() => c.value?.chosen ?? null)
function setSoundStart(e: Event) { if (snd.value) { snd.value.start = Math.max(0, parseFloat((e.target as HTMLInputElement).value.replace(',', '.')) || 0); touch(150) } }
const k = computed(() => (c.value ? ED.clips.indexOf(c.value) : -1))
const v = computed(() => ED.view)
const track = computed(() => P.proj?.settings.track || null)
const q = computed(() => v.value?.quality || 'draft')
const n = computed(() => ED.clips.length)
// the video's colour: a look over every clip, each clip brought toward the others first (app/edit.py)
const LOOKS = computed<[string, string][]>(() => ['', 'film', 'warm', 'cold', 'teal', 'bw', 'lut'].map((k) => [k, t(`edit.looks.${k || 'asShot'}`)]))
const finish = computed(() => [
  ...(ED.look.grade === 'lut' ? [{ key: 'lutMix' as const, label: t('edit.lutMix'), value: ED.look.lutMix }] : []),
  { key: 'vignette' as const, label: t('edit.vignette'), value: ED.look.vignette },
  { key: 'grain' as const, label: t('edit.grain'), value: ED.look.grain },
])
function setLook(k: 'grade' | 'match', val: string | boolean) { (ED.look as any)[k] = val; if (k === 'grade' && val !== 'lut') ED.look.lut = ''; touch(150) }
async function lutUp(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  try { const r = await api<{ file: string }>(`/api/projects/${ED.id}/luts`, { method: 'POST', body: fd }); ED.look = { ...ED.look, grade: 'lut', lut: r.file }; touch(50) }
  catch (x) { banner((x as Error).message) }
}

// a seam: the clips on its two sides, what it is and why
const seam = computed(() => seamOf(ED.sel))
const seamPrev = computed(() => (seam.value ? ED.clips[ED.clips.indexOf(seam.value) - 1] : null))
const kind = computed(() => (seam.value ? seamKind(seam.value) : 'cut'))
const seamSay = computed(() => {
  const c = seam.value, a = seamPrev.value
  if (!c || !a) return ''
  const one = a.scene === c.scene
  switch (kind.value) {
    case 'flow': return one ? t('edit.say.flowOne') : t('edit.say.flow', { c: c.name, a: a.name })
    case 'fade': return t('edit.say.fade', { s: num(c.td) })
    case 'black': return t('edit.say.black', { s: num(c.td) })
    case 'cut': return t('edit.say.cut')
    case 'flash': return t('edit.say.flash')
  }
  const why = seamWhy(c)
  if (why === 'take') return one ? t('edit.say.takeOne') : t('edit.say.take', { a: a.name, c: c.name })
  if (why === 'speed') return t('edit.say.speed')
  return one ? t('edit.say.trimOne') : t('edit.say.trim', { a: a.name, c: c.name })
})
const playSeam = (c: Clip) => { ED.cue = Math.max(0, c.start - 1.5) }
// the seams that jump, for the montage's own panel
const jumps = computed(() => ED.clips.filter((c) => c.jump))

const num = (x: number) => dec(Math.round(x * 100) / 100)
function setTime(cl: Clip, side: 'in' | 'out', e: Event) {
  const val = parseFloat((e.target as HTMLInputElement).value.replace(',', '.'))
  if (!Number.isNaN(val)) { trim(cl, side, val); touch(150) }
}
const sceneClipCount = computed(() => c.value ? ED.clips.filter((x) => x.scene === c.value!.scene).length : 0)
const targetColor = computed(() => {
  if (ED.colorScope === 'video' || !c.value) return ED.look.color
  if (ED.colorScope === 'scene') return ED.sceneColors[c.value.scene]
  return c.value.color
})
const targetLabel = computed(() => {
  if (ED.colorScope === 'video' || !c.value) return t('edit.scope.videoDetail', { n: ED.clips.length })
  if (ED.colorScope === 'scene') return t('edit.scope.sceneDetail', { n: c.value.index + 1, name: c.value.name, clips: sceneClipCount.value })
  return t('edit.scope.clipDetail', { n: k.value + 1, name: c.value.name, at: tc(c.value.start) })
})
function setScope(scope: 'clip' | 'scene' | 'video') {
  if (!c.value && scope !== 'video') return
  ED.colorScope = scope
  ED.colorSceneId = c.value?.scene || null
}
function setColor(key: keyof ClipColor, e: Event) {
  if (ED.colorScope === 'video' || !c.value) { ED.look.color ||= { ...COLOR_DEFAULT }; ED.look.color[key] = +((e.target as HTMLInputElement).value) }
  else if (ED.colorScope === 'scene') { ED.sceneColors[c.value.scene] ||= { ...COLOR_DEFAULT }; ED.sceneColors[c.value.scene][key] = +((e.target as HTMLInputElement).value) }
  else { c.value.color ||= { ...COLOR_DEFAULT }; c.value.color[key] = +((e.target as HTMLInputElement).value) }
  touch(400)
}
function resetColor() {
  if (ED.colorScope === 'video' || !c.value) ED.look.color = undefined
  else if (ED.colorScope === 'scene') delete ED.sceneColors[c.value.scene]
  else delete c.value.color
  touch(150)
}
function setSoftPreset() {
  const preset = { ...COLOR_DEFAULT, exposure: 0.1, contrast: 1.05, saturation: 1.05 }
  if (ED.colorScope === 'video' || !c.value) ED.look.color = preset
  else if (ED.colorScope === 'scene') ED.sceneColors[c.value.scene] = preset
  else c.value.color = preset
  touch(150)
}
const colorSliders = computed(() => [
  { key: 'exposure' as const, min: -1, max: 1, step: 0.05, value: targetColor.value?.exposure ?? 0, format: (x: number) => `${x > 0 ? '+' : ''}${num(x)} EV` },
  { key: 'contrast' as const, min: 0.5, max: 1.5, step: 0.05, value: targetColor.value?.contrast ?? 1, format: (x: number) => `${Math.round(x * 100)}%` },
  { key: 'saturation' as const, min: 0, max: 2, step: 0.05, value: targetColor.value?.saturation ?? 1, format: (x: number) => `${Math.round(x * 100)}%` },
  { key: 'temperature' as const, min: -50, max: 50, step: 2, value: targetColor.value?.temperature ?? 0, format: (x: number) => x === 0 ? t('edit.colorNeutral') : x < 0 ? `${t('edit.colorCool')} ${Math.abs(x)}` : `${t('edit.colorWarm')} ${x}` },
])
const rangeFill = (x: { min: number; max: number; value: number }) => ({ '--range-fill': `${Math.max(0, Math.min(100, (x.value - x.min) / (x.max - x.min) * 100))}%` })
const nudge = (cl: Clip, side: 'in' | 'out', by: number) => { trim(cl, side, cl[side] + by); touch(300) }
function goScene(cl: Clip) { P.sel = cl.index; router.push(`/p/${ED.id}`) }

// the music: the project's track (the same as on «Ролик»), its changes saved at once
const pct = (x: number) => `${Math.round(x * 100)}%`, sec = (x: number) => t('edit.secs', { s: num(+x) })
const sliders = computed(() => [
  { key: 'volume', label: t('edit.trackVolume'), min: 0, max: 1.5, step: 0.05, fmt: pct },
  { key: 'scene_volume', label: t('edit.sceneUnder'), min: 0, max: 1, step: 0.05, fmt: pct },
  { key: 'offset', label: t('edit.trackFromS'), min: 0, max: Math.max(0, Math.floor((track.value?.duration || 0) - 5)), step: 0.5, fmt: sec },
  { key: 'fade_in', label: t('edit.fadeIn'), min: 0, max: 6, step: 0.5, fmt: sec },
  { key: 'fade_out', label: t('edit.fadeOutEnd'), min: 0, max: 8, step: 0.5, fmt: sec },
])
async function setTrack(key: string, val: number) { if (await projectCall('PUT', '/track', { [key]: val }) && ED.view) ED.view.track = P.proj!.settings.track }
async function upload(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  if (await projectCall('POST', '/track', fd) && ED.view) { ED.view.track = P.proj!.settings.track; ED.sel = 'music' }
  ;(e.target as HTMLInputElement).value = ''
}
async function dropTrack() { if (confirm(t('edit.dropTrack')) && await projectCall('DELETE', '/track') && ED.view) { ED.view.track = null; ED.sel = null } }
// «Для DaVinci Resolve»: Windows' folder dialog (from the last place, else the project's folder), then the montage as
// it is saved -> «<name> · Resolve» in that folder (FCPXML + its files), opened in Explorer
const exporting = ref<'' | 'pick' | 'write'>(''), exported = ref('')
async function toResolve() {
  exporting.value = 'pick'
  try {
    await flushEdit()
    const start = (v.value as any)?.resolve_dir || ''
    const dir = (await api<{ path: string | null }>('/api/models/pick', { method: 'POST', body: { kind: 'folder', start } })).path
    if (!dir) return
    exporting.value = 'write'
    const r = await api<{ dir: string; file: string; unshot: number }>(`/api/projects/${ED.id}/edit/resolve?quality=${q.value}`, { method: 'POST', body: { dir } })
    if (ED.view) (ED.view as any).resolve_dir = dir
    exported.value = `${r.dir}\\${r.file}` + (r.unshot ? t('edit.notShotN', { n: r.unshot }) : '')
  } catch (e) { banner((e as Error).message) } finally { exporting.value = '' }
}
function backToBoard() { if (confirm(t('edit.backAsk', { how: graph.value ? t('edit.asInputHow') : t('edit.asBoardHow') }))) resetEdit() }
defineExpose({ upload })
</script>

<template>
  <!-- the tabs: what is selected opens its own (a clip, a seam, «Поверх» - «Клип»; a sound, the track - «Звук») -->
  <div class="ei-tabs" role="tablist" :aria-label="t('edit.montage')">
    <button v-for="x in TABS" :key="x.k" type="button" role="tab" :aria-selected="tab === x.k" :class="{ on: tab === x.k }" @click="tab = x.k">
      <Icon :name="x.icon" :size="14" />{{ t(`edit.tab.${x.k}`) }}</button>
  </div>

  <template v-if="tab === 'clip'">
  <!-- a clip -->
  <div v-if="c" class="stack ei">
    <div class="sec-head"><span class="ei-title"><Icon name="film" />{{ c.name }}</span>
      <button type="button" class="ghost" :aria-label="t('edit.unselect')" @click="ED.sel = null"><Icon name="close" /></button></div>
    <span class="muted small">{{ t('edit.clipFacts', { len: num(c.length), dur: num(c.dur), at: tc(c.start) }) }}{{ c.kind === 'continue' ? t('edit.contChain') : '' }}</span>
    <div v-if="!c.file" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('edit.notShotWarn') }}</span></div>
    <div class="ei-trims">
      <label class="stack"><span class="lbl">{{ t('edit.start') }} <HelpQ id="edit" term="Обрезка" /></span>
        <div class="ei-num"><button type="button" class="ghost" :aria-label="t('edit.frameEarlier')" @click="nudge(c, 'in', -FRAME)">‹</button>
          <input class="field-in" :value="num(c.in)" inputmode="decimal" :aria-label="t('edit.startSecs')" @change="setTime(c, 'in', $event)">
          <button type="button" class="ghost" :aria-label="t('edit.frameLater')" @click="nudge(c, 'in', FRAME)">›</button></div></label>
      <label class="stack"><span class="lbl">{{ t('edit.end') }}</span>
        <div class="ei-num"><button type="button" class="ghost" :aria-label="t('edit.frameEarlier')" @click="nudge(c, 'out', -FRAME)">‹</button>
          <input class="field-in" :value="num(c.out)" inputmode="decimal" :aria-label="t('edit.endSecs')" @change="setTime(c, 'out', $event)">
          <button type="button" class="ghost" :aria-label="t('edit.frameLater')" @click="nudge(c, 'out', FRAME)">›</button></div></label>
    </div>
    <p class="muted small">{{ t('edit.trimHint', { s: num(MIN_CLIP) }) }}</p>
    <button v-if="k > 0" type="button" class="ei-seamline" :class="`s-${seamKind(c)}`" :title="t('edit.seamSet')" @click="ED.sel = SEAM + c.id">
      <span class="ei-glyph"><Icon :name="SEAM_ICON[seamKind(c)]" :size="13" /></span>
      <span>{{ t('edit.seamBefore') }}<b>{{ SEAM_NAME[seamKind(c)] }}{{ c.tr !== 'cut' ? ` ${t('edit.secs', { s: num(c.td) })}` : '' }}</b></span><Icon name="forward" :size="14" /></button>
    <div v-if="sceneTakes.length > 1" class="stack takes-box" style="gap:6px"><span class="lbl">{{ t('edit.take') }} <HelpQ id="edit" term="Дубли" /> <small>{{ t('edit.forClip') }}</small></span>
      <div class="takes"><button v-for="(tk, i) in sceneTakes" :key="tk.seed" type="button" class="take" :class="{ on: (c.take ?? chosenSeed) === tk.seed }"
          :title="t('edit.takeTitle', { n: i + 1, board: tk.seed === chosenSeed ? t('edit.inBoard') : '', shot: tk.cached ? '' : t('edit.notShotT') })" @click="setTake(c, tk.seed === chosenSeed ? null : tk.seed)">
          <img v-if="tk.cached && tk.png" :src="fileUrl(tk.png)" alt=""><span v-else>{{ t('edit.notShotTake') }}</span><b>{{ i + 1 }}{{ tk.seed === chosenSeed ? ' ★' : '' }}</b></button></div>
      <p class="muted small">{{ t('edit.takesHint') }}</p>
    </div>
    <span class="lbl">{{ t('edit.speed') }} <HelpQ id="edit" term="Скорость" /></span>
    <div class="seg ei-speeds"><button v-for="sp in SPEEDS" :key="sp" type="button" :class="{ on: c.speed === sp }" @click="c.speed = sp; touch(150)">{{ xn(sp) }}</button></div>
    <div class="tk"><span>{{ t('edit.sceneSoundOne') }}</span>
      <input type="range" min="0" max="2" step="0.05" :value="c.vol" :aria-label="t('edit.sceneVol')" @input="c.vol = +($event.target as HTMLInputElement).value; touch(400)"><b>{{ Math.round(c.vol * 100) }}%</b></div>
    <div class="ei-acts">
      <button type="button" class="btn" :disabled="!playheadIn" :title="playheadIn ? t('edit.splitHere') : t('edit.putInside')" @click="split()"><Icon name="cut" />{{ t('edit.cut') }}</button>
      <button type="button" class="btn" :title="t('edit.copyTitle')" @click="duplicate()"><Icon name="layers" />{{ t('edit.copy') }}</button>
      <button type="button" class="btn danger" :title="t('edit.removeTitle')" @click="remove()"><Icon name="trash" />{{ t('edit.remove') }}</button>
    </div>
    <div class="ei-acts">
      <button type="button" class="btn" @click="resetClip(c)"><Icon name="reset" />{{ t('edit.reset') }}</button>
      <button type="button" class="btn" @click="tab = 'color'; setScope('clip')"><Icon name="image" />{{ t('edit.clipColor') }}</button>
      <button v-if="!graph" type="button" class="btn" @click="goScene(c)"><Icon name="pen" />{{ t('edit.sceneInBoard') }}</button>
    </div>
  </div>

  <!-- a seam -->
  <div v-else-if="seam && seamPrev" class="stack ei">
    <div class="sec-head"><span class="ei-title"><span class="ei-glyph big" :class="`s-${kind}`"><Icon :name="SEAM_ICON[kind]" :size="15" /></span>{{ SEAM_NAME[kind] }}</span>
      <button type="button" class="ghost" :aria-label="t('edit.unselect')" @click="ED.sel = null"><Icon name="close" /></button></div>
    <div class="ei-pair" :class="`s-${kind}`">
      <button type="button" :title="t('edit.pickClipTitle', { name: seamPrev.name })" @click="ED.sel = seamPrev.id"><span class="ei-pic" :style="seamPrev.png ? { backgroundImage: `url(${fileUrl(seamPrev.png)})` } : {}" /><span><b>{{ seamPrev.index + 1 }}</b> {{ seamPrev.name }}</span></button>
      <span class="ei-join"><Icon :name="SEAM_ICON[kind]" :size="14" /></span>
      <button type="button" :title="t('edit.pickClipTitle', { name: seam.name })" @click="ED.sel = seam.id"><span class="ei-pic" :style="seam.png ? { backgroundImage: `url(${fileUrl(seam.png)})` } : {}" /><span><b>{{ seam.index + 1 }}</b> {{ seam.name }}</span></button>
    </div>
    <p class="ei-say" :class="`s-${kind}`">{{ seamSay }}</p>
    <div v-if="kind === 'jump'" class="ei-acts">
      <button type="button" class="btn" :title="t('edit.mendTitle')" @click="mendSeam(seam)"><Icon name="link" />{{ t('edit.mend') }}</button>
      <button type="button" class="btn" @click="setTr(seam, 'fade', TD)"><Icon name="dissolve" />{{ t('edit.hide') }}</button></div>
    <span class="lbl">{{ t('edit.transition') }} <HelpQ id="edit" term="Переходы" /></span>
    <div class="seg"><button v-for="t in (['cut', 'flash', 'fade', 'black'] as const)" :key="t" type="button" :class="{ on: seam.tr === t }" @click="setTr(seam, t, seam.td || TD)">{{ TR_NAME[t] }}</button></div>
    <div v-if="seam.tr === 'fade' || seam.tr === 'black'" class="tk"><span>{{ t('edit.length') }}</span>
      <input type="range" min="0.2" max="2" step="0.1" :value="seam.td || TD" :aria-label="t('edit.trLength')" @input="seam.td = +($event.target as HTMLInputElement).value; touch(400)"><b>{{ t('edit.secs', { s: num(seam.td) }) }}</b></div>
    <button type="button" class="btn" :title="t('edit.playSeamTitle')" @click="playSeam(seam)"><Icon name="play" />{{ t('edit.playSeam') }}</button>
    <p class="muted small">{{ t('edit.seamHint') }}</p>
  </div>

  <!-- «Поверх»: a piece of a shot over the video -->
  <div v-else-if="ovl" class="stack ei">
    <div class="sec-head"><span class="ei-title"><Icon name="layers" />{{ t('edit.over') }}</span>
      <button type="button" class="ghost" :aria-label="t('edit.unselect')" @click="ED.sel = null"><Icon name="close" /></button></div>
    <span class="muted small">{{ t('edit.overFacts', { len: num(ovl.dur), at: tc(ovl.start), all: num(ovl.length) }) }}</span>
    <div v-if="!ovl.file" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('edit.overNotShot') }}</span></div>
    <label class="stack"><span class="lbl">{{ t('edit.overScene') }}</span>
      <select class="field-in" :value="ovl.scene" @change="setOverlayScene(ovl, ($event.target as HTMLSelectElement).value)">
        <option v-for="x in overlayScenes()" :key="x.scene" :value="x.scene">{{ x.index + 1 }} · {{ x.name }}</option></select></label>
    <div v-if="ovl.take_list.length > 1" class="stack takes-box" style="gap:6px"><span class="lbl">{{ t('edit.take') }}</span>
      <div class="takes"><button v-for="(tk, i) in ovl.take_list" :key="tk.seed" type="button" class="take" :class="{ on: (ovl.take ?? ovl.chosen) === tk.seed }"
          :title="t('edit.takeTitle', { n: i + 1, board: tk.seed === ovl.chosen ? t('edit.inBoard') : '', shot: tk.cached ? '' : t('edit.notShotT') })" @click="setOverTake(ovl, tk.seed === ovl.chosen ? null : tk.seed)">
          <img v-if="tk.cached && tk.png" :src="fileUrl(tk.png)" alt=""><span v-else>{{ t('edit.notShotTake') }}</span><b>{{ i + 1 }}{{ tk.seed === ovl.chosen ? ' ★' : '' }}</b></button></div></div>
    <div class="ei-trims">
      <label class="stack"><span class="lbl">{{ t('edit.atSecond') }}</span>
        <input class="field-in" :value="num(ovl.start)" inputmode="decimal" :aria-label="t('edit.overWhere')" @change="setOverStart"></label>
      <div class="stack"><span class="lbl">&nbsp;</span><button type="button" class="btn" @click="ovl.start = Math.round(ED.t * 24) / 24; trimOverlay(ovl, 'out', ovl.out); touch(150)">{{ t('edit.toPlayhead') }}</button></div>
    </div>
    <div class="ei-trims">
      <label class="stack"><span class="lbl">{{ t('edit.overFrom') }}</span>
        <input class="field-in" :value="num(ovl.in)" inputmode="decimal" :aria-label="t('edit.overFrom')" @change="setOverTime(ovl, 'in', $event)"></label>
      <label class="stack"><span class="lbl">{{ t('edit.overTo') }}</span>
        <input class="field-in" :value="num(ovl.out)" inputmode="decimal" :aria-label="t('edit.overTo')" @change="setOverTime(ovl, 'out', $event)"></label>
    </div>
    <p class="muted small">{{ t('edit.overHint') }}</p>
    <div class="ei-acts">
      <button type="button" class="btn" @click="duplicate()"><Icon name="layers" />{{ t('edit.copy') }}</button>
      <button type="button" class="btn danger" @click="remove()"><Icon name="trash" />{{ t('edit.remove') }}</button>
    </div>
  </div>

  <div v-else class="stack ei ei-empty"><Icon name="cut" :size="22" /><p class="muted small">{{ t('edit.pickHint') }}</p></div>
  </template>

  <!-- the colour: the look over the video, then the precise correction of the clip, its scene or the video -->
  <div v-else-if="tab === 'color'" class="stack ei ei-look">
    <div class="ei-color-head"><span class="ei-color-icon"><Icon name="film" /></span><span class="ei-color-title"><b>{{ t('edit.globalLook') }}</b><small>{{ t('edit.scope.videoDetail', { n }) }}</small></span></div>
    <label class="lbl">{{ t('edit.color') }}</label>
    <select class="field-in" :value="ED.look.grade" :aria-label="t('edit.color')" @change="setLook('grade', ($event.target as HTMLSelectElement).value)">
      <option v-for="[key, label] in LOOKS" :key="key" :value="key" :disabled="key === 'lut' && !ED.look.lut">{{ label }}{{ key === 'lut' && ED.look.lut ? ` — ${ED.look.lut.replace(/^luts\/[0-9a-f]+_/, '')}` : '' }}</option></select>
    <label class="btn"><Icon name="image" />{{ ED.look.lut ? t('edit.otherLut') : t('edit.loadLut') }}<input type="file" accept=".cube" hidden @change="lutUp"></label>
    <label class="check-row" :title="t('edit.matchTitle')"><input type="checkbox" :checked="ED.look.match" @change="setLook('match', ($event.target as HTMLInputElement).checked)">{{ t('edit.match') }}</label>
    <!-- how much of the LUT, the vignette, the grain: over the whole video (app/edit.py look_of) -->
    <div v-for="x in finish" :key="x.key" class="ei-color-control">
      <div class="ei-color-label"><label>{{ x.label }}</label><output>{{ Math.round(x.value * 100) }}%</output></div>
      <input type="range" :style="rangeFill({ min: 0, max: 1, value: x.value })" min="0" max="1" step="0.05" :value="x.value" :aria-label="x.label"
        @input="ED.look[x.key] = +($event.target as HTMLInputElement).value; touch(400)">
    </div>
    <button type="button" class="btn ei-bare" :class="{ on: ED.bare }" :title="t('edit.bareTitle')" @pointerdown="ED.bare = true" @pointerup="ED.bare = false"
      @pointerleave="ED.bare = false" @keydown.space.prevent="ED.bare = true" @keyup.space="ED.bare = false"><Icon name="image" />{{ t('edit.bare') }}</button>
    <span v-if="ED.look.grade === 'lut' || ED.look.match || ED.look.grain" class="muted small">{{ t('edit.colorHint') }}</span>
    <div class="ei-color">
      <div class="ei-color-head"><span class="ei-color-icon"><Icon name="image" /></span><span class="ei-color-title"><b>{{ t('edit.preciseColor') }}</b><small>{{ c ? t('edit.preciseColorSub') : t('edit.scope.videoDetail', { n }) }}</small></span>
        <button v-if="targetColor" type="button" class="ghost ei-reset" @click="resetColor"><Icon name="reset" />{{ t('edit.colorReset') }}</button></div>
      <div v-if="c" class="ei-scope" role="group" :aria-label="t('edit.scope.label')">
        <button type="button" :class="{ on: ED.colorScope === 'clip' }" :aria-pressed="ED.colorScope === 'clip'" @click="setScope('clip')">{{ t('edit.scope.clip') }}</button>
        <button type="button" :class="{ on: ED.colorScope === 'scene' }" :aria-pressed="ED.colorScope === 'scene'" @click="setScope('scene')">{{ t('edit.scope.scene') }}</button>
        <button type="button" :class="{ on: ED.colorScope === 'video' }" :aria-pressed="ED.colorScope === 'video'" @click="setScope('video')">{{ t('edit.scope.video') }}</button>
      </div>
      <div class="ei-target"><Icon :name="ED.colorScope === 'video' ? 'film' : ED.colorScope === 'scene' ? 'layers' : 'cut'" :size="15" /><span>{{ targetLabel }}</span></div>
      <div class="ei-color-presets">
        <button type="button" class="ei-preset" @click="resetColor">{{ t('edit.colorOriginal') }}</button>
        <button type="button" class="ei-preset" @click="setSoftPreset">{{ t('edit.colorAuto') }}</button>
      </div>
      <div v-for="x in colorSliders" :key="x.key" class="ei-color-control" :class="`color-${x.key}`">
        <div class="ei-color-label"><label>{{ t(`edit.colorAdjust.${x.key}`) }}</label><output>{{ x.format(x.value) }}</output></div>
        <input type="range" :style="rangeFill(x)" :min="x.min" :max="x.max" :step="x.step" :value="x.value" :aria-label="t(`edit.colorAdjust.${x.key}`)" @input="setColor(x.key, $event)">
      </div>
      <p class="ei-color-note">{{ !c || ED.colorScope === 'video' ? t('edit.scope.videoHint') : ED.colorScope === 'scene' ? t('edit.scope.sceneHint') : t('edit.sceneColorHint') }}</p>
    </div>
  </div>

  <template v-else-if="tab === 'sound'">
  <!-- a sound from a file -->
  <div v-if="snd" class="stack ei">
    <div class="sec-head"><span class="ei-title"><Icon name="volume" />{{ t('edit.sound') }}</span>
      <button type="button" class="ghost" :aria-label="t('edit.unselect')" @click="ED.sel = null"><Icon name="close" /></button></div>
    <span class="muted small">{{ t('edit.soundFacts', { name: snd.name, len: num(snd.out - snd.in), all: num(snd.length) }) }}</span>
    <div class="ei-trims">
      <label class="stack"><span class="lbl">{{ t('edit.atSecond') }}</span>
        <input class="field-in" :value="num(snd.start)" inputmode="decimal" :aria-label="t('edit.soundWhere')" @change="setSoundStart"></label>
      <div class="stack"><span class="lbl">&nbsp;</span><button type="button" class="btn" @click="snd.start = Math.round(ED.t * 100) / 100; touch(150)">{{ t('edit.toPlayhead') }}</button></div>
    </div>
    <div class="tk"><span>{{ t('edit.volume') }}</span>
      <input type="range" min="0" max="2" step="0.05" :value="snd.vol" :aria-label="t('edit.soundVol')" @input="snd.vol = +($event.target as HTMLInputElement).value; touch(400)"><b>{{ Math.round(snd.vol * 100) }}%</b></div>
    <div class="tk"><span>{{ t('edit.fadeIn') }}</span>
      <input type="range" min="0" max="5" step="0.1" :value="snd.fade_in" :aria-label="t('edit.fadeIn')" @input="snd.fade_in = +($event.target as HTMLInputElement).value; touch(400)"><b>{{ t('edit.secs', { s: num(snd.fade_in) }) }}</b></div>
    <div class="tk"><span>{{ t('edit.fadeOut') }}</span>
      <input type="range" min="0" max="5" step="0.1" :value="snd.fade_out" :aria-label="t('edit.fadeOut')" @input="snd.fade_out = +($event.target as HTMLInputElement).value; touch(400)"><b>{{ t('edit.secs', { s: num(snd.fade_out) }) }}</b></div>
    <p class="muted small">{{ t('edit.soundHint') }}</p>
    <div class="ei-acts">
      <button type="button" class="btn" @click="duplicate()"><Icon name="layers" />{{ t('edit.copy') }}</button>
      <button type="button" class="btn danger" @click="remove()"><Icon name="trash" />{{ t('edit.remove') }}</button>
    </div>
  </div>

  <!-- the music -->
  <div v-else-if="track" class="stack ei">
    <div class="sec-head"><span class="ei-title"><Icon name="music" />{{ t('edit.music') }}</span>
      <button type="button" class="ghost" :aria-label="t('edit.unselect')" @click="ED.sel = null"><Icon name="close" /></button></div>
    <span class="muted small">{{ track.name }} · {{ tc(track.duration || 0) }}</span>
    <div v-for="x in sliders" :key="x.key" class="tk"><span>{{ x.label }}</span>
      <input type="range" :min="x.min" :max="x.max" :step="x.step" :value="track[x.key] ?? 0" :aria-label="x.label"
        @input="track[x.key] = +($event.target as HTMLInputElement).value" @change="setTrack(x.key, +($event.target as HTMLInputElement).value)"><b>{{ x.fmt(track[x.key] ?? 0) }}</b></div>
    <div class="tk"><span>{{ t('edit.duck') }}</span>
      <input type="range" min="0" max="1" step="0.05" :value="ED.duck" :aria-label="t('edit.duckLabel')" @input="ED.duck = +($event.target as HTMLInputElement).value; touch(500)"><b>{{ ED.duck ? Math.round(ED.duck * 100) + '%' : t('edit.no') }}</b></div>
    <p class="muted small">{{ t('edit.duckHint') }}</p>
    <div v-if="(track.duration || 0) - (track.offset || 0) < ED.duration" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('edit.trackShort') }}</span></div>
    <div class="ei-acts">
      <label class="btn"><Icon name="music" />{{ t('edit.otherTrack') }}<input type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg" hidden @change="upload"></label>
      <button type="button" class="btn danger" @click="dropTrack"><Icon name="trash" />{{ t('edit.removeTrack') }}</button>
    </div>
    <p class="muted small">{{ t('edit.trackHint') }}</p>
  </div>

  <div v-else class="stack ei">
    <span class="lbl">{{ t('edit.music') }}</span>
    <p v-if="graph" class="muted small">{{ t('edit.graphTrack') }}</p>
    <label v-if="!track && !graph" class="btn"><Icon name="music" />{{ t('edit.ownTrackAll') }}<input type="file" accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg" hidden @change="upload"></label>
    <span class="lbl">{{ t('edit.sounds') }}</span>
    <button type="button" class="btn" @click="emit('addSound')"><Icon name="volume" />{{ t('edit.soundFile') }}</button>
    <p class="muted small">{{ t('edit.soundTabHint') }}</p>
  </div>
  </template>

  <template v-else>
  <!-- the montage -->
  <div class="stack ei">
    <span class="lbl">{{ t('edit.montage') }} <HelpQ id="edit" /></span>
    <span class="ei-big">{{ tc(ED.duration) }}</span>
    <span class="muted">{{ t('edit.clips', n) }} · {{ QL[q] }}{{ v ? ` · ${v.width}×${v.height}` : '' }}{{ v?.changed ? t('edit.changed') : graph ? t('edit.asInput') : t('edit.asBoard') }}</span>
    <div v-if="buildState === 'error'" class="warn-line"><Icon name="warn" :size="14" /><span>{{ v?.error }}</span></div>
    <div v-else-if="v && v.to_shoot" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('edit.notShotScenes', v.to_shoot) }}</span></div>
    <div v-else-if="buildState === 'same'" class="ok-line"><Icon name="check" :size="14" /><span>{{ t('edit.builtSame') }}</span></div>
    <div v-else-if="buildState !== 'building'" class="warn-line"><Icon name="warn" :size="14" /><span>{{ v?.built ? t('edit.builtOld') : t('edit.notBuilt') }}</span></div>
    <div v-if="jumps.length" class="stack ei-jumps"><span class="lbl">{{ t('edit.jumps', jumps.length) }}</span>
      <div class="ei-acts"><button v-for="j in jumps" :key="j.id" type="button" class="btn" @click="ED.sel = SEAM + j.id"><Icon name="warn" />{{ tc(j.start) }} · {{ j.name }}</button></div></div>
    <p v-if="graph" class="muted small">{{ t('edit.graphHint') }}</p>
    <p v-else class="muted small">{{ t('edit.boardHint') }}</p>
    <div v-if="offScenes.length" class="stack" style="gap:6px"><span class="lbl">{{ t('edit.taken') }}</span>
      <div class="ei-acts"><button v-for="x in offScenes" :key="x.id" type="button" class="btn" :title="t('edit.restoreTitle', { n: x.n })" @click="restoreScene(x.id)"><Icon name="plus" />{{ x.name || t('edit.sceneN', { n: x.n }) }}</button></div></div>
    <button v-if="v?.changed" type="button" class="btn" @click="backToBoard"><Icon name="reset" />{{ graph ? t('edit.resetInput') : t('edit.resetBoard') }}</button>
    <template v-if="!graph">
      <button type="button" class="btn" :disabled="!ED.clips.some((x) => x.file) || !!exporting" :title="t('edit.resolveTitle')" @click="toResolve"><Icon name="export" />{{ exporting === 'pick' ? t('edit.pickFolder') : exporting ? t('edit.preparing') : t('edit.resolve') }}</button>
      <span v-if="exported" class="muted small">{{ t('edit.resolveDone') }}<code>{{ exported }}</code>{{ t('edit.resolveDone2') }}</span>
      <span v-else-if="v?.to_shoot" class="muted small">{{ t('edit.resolveEmpty') }}</span>
    </template>
  </div>
  </template>
</template>
