<script setup lang="ts">
// The selected scene: its number and time on top, what happens always in sight with who wrote it («Своими словами» -
// the user's and pinned, «Переписать» - back to the writer), the rest in tabs - «Начало» (how it starts: text, a photo,
// the last frame of the scene before it or of any earlier one; the first and last frames), «Сцена» (the camera, the
// story after an edit), «Съёмка» (the model and the length it allows, the faces, its own LoRA, the prompt that goes
// to H3 - or the user's own prompt, as it is - and the graph), «Реплики» (who is in it and what each says), «Дубли»
// (the chosen one goes into the video); at the foot «Ещё дубль» (one more take now), pin, delete. The tab stays as
// the selection moves. ⤢ opens the scene on the whole page (SceneDetail.vue), where this panel stands on the right
// without its head, tabs and takes, every part one under another (detail).
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import PicLoraLine from '../PicLoraLine.vue'
import HelpQ from '../HelpQ.vue'
import SceneStart from './SceneStart.vue'
import SceneTakes from './SceneTakes.vue'
import { S, banner } from '../../lib/store'
import { api, post } from '../../lib/api'
import { P, liveWriter, projectCall, rewrite, scheduleSave } from '../../lib/project'
import { vZoom } from '../../lib/zoom'
import { authorOf, calmOf, canUndoRewrite, castName, forgetRewrite, foundLabel, foundLines, foundOf,hasPeople, inspTab as tab, isRaw, moreTake, openerOf, pct, problemsOf, rawTemplate, removeScenes, rewriteScene, taking, takesOf, undoRewriteOf } from '../../lib/board'
import { CAMERAS, FRAMINGS, HOW_RU, LINE_WORDS } from '../../lib/consts'
import { dec, mmss } from '../../lib/format'
import type { Plan, Scene } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan; s: Scene; detail?: boolean }>()
const emit = defineEmits<{ expand: [] }>()
// the tabs: «Реплики» only where people speak (not with the user's own prompt)
const tabs = computed(() => ['start', 'scene', 'shoot', ...(props.p.mode !== 'none' && !isRaw(props.s) ? ['lines' as const] : []), 'takes'] as ('start' | 'scene' | 'shoot' | 'lines' | 'takes')[])
watch(tabs, (ks) => { if (!ks.includes(tab.value)) tab.value = 'scene' }, { immediate: true })
const on = (k: string) => props.detail || tab.value === k
const takeCount = computed(() => takesOf(props.s).length)
// the scene's notes: the writer's «проверь» and the shot clip's auto-check
const problems = computed(() => problemsOf(props.s))
const found = computed(() => foundOf(props.s.index))
const calm = computed(() => calmOf(props.s.index))   // «почти не движется»: grey, not a note
const busy = computed(taking)
const go = (d: number) => { P.picked = []; P.sel = Math.max(0, Math.min(props.p.scenes.length - 1, props.s.index + d)) }
// what the scene's model gets for a new shot: LTX and WAN their own prompt from the same fields (model_prompts.py)
const sent = ref<{ model: string; name: string; text: string } | null>(null)
async function loadSent() {
  if (!P.openEn || !P.proj || isRaw(props.s)) return
  try { sent.value = await api(`/api/projects/${P.proj.id}/scenes/${props.s.index}/prompt`) } catch { sent.value = null }
}
watch(() => [P.openEn, props.s.index, props.s.prompt, props.s.model, P.proj?.settings.video_model], loadSent, { immediate: true })
// «Граф для ComfyUI»: loaded when opened, dropped when the scene changes (open it again for the new one)
const peek = ref<{ model: string; key: string; cached: boolean; graph: Record<string, any>; inputs: Record<string, string>; error?: string } | null>(null)
const copied = ref(false)
async function loadGraph() {
  if (!P.proj) return
  try { peek.value = await api(`/api/projects/${P.proj.id}/scenes/${props.s.index}/graph`) } catch (e) { peek.value = { error: (e as Error).message } as any }
}
watch(() => [props.s.index, props.s.prompt, props.s.seed], () => { peek.value = null; copied.value = false })
async function copyGraph() {
  try { await navigator.clipboard.writeText(JSON.stringify(peek.value?.graph, null, 1)); copied.value = true } catch { copied.value = false }
}
const proj = computed(() => P.proj!)
const max = computed(() => S.cfg!.max_prompt)
const models = computed(() => S.cfg?.video_models || [])
const videoModel = computed(() => models.value.find((x) => x.id === (proj.value.settings.video_model || 'h3')))
// phase 11: a scene's own model - on the scene that opens a chain; a continuation goes on in its chain's model
const opener = computed(() => openerOf(props.p, props.s) || props.s)
const model = computed(() => models.value.find((x) => x.id === opener.value.model) || videoModel.value)
function setModel(id: string) {
  if (id) props.s.model = id; else delete props.s.model
  scheduleSave()
}
// phase 11: a clip's scene - its part of the song and its kind of shot; singing, its line is the words sung in it
// the options short (a long one was cut in a 380 px panel), what the picked one means in a line under it
const cap = (x: string) => x.charAt(0).toUpperCase() + x.slice(1)
const SHOTS = computed<[string, string][]>(() => ['sing', 'perform', 'insert'].map((k) => [k, cap(t(`board.shot.${k}`))]))
const PARTS = ['intro', 'groove', 'break', 'drop', 'outro', 'chorus']
const partName = (k: string) => (PARTS.includes(k) ? t(`idea.part.${k}`) : k)
const sungWords = computed(() => (props.s.sung || []).map((x: any) => x.text).join(' ').trim())
function setShot(v: string) {
  const x = props.s
  x.shot = v
  x.lines = (x.lines || []).filter((l: any) => l.how !== 'sing')
  if (v === 'sing' && sungWords.value) x.lines = [{ who: 1, text: sungWords.value, how: 'sing' }, ...x.lines.filter((l: any) => l.who !== 1)]
  const sing = props.p.clip && P.proj?.settings.clip?.sing_model
  if (sing && x.kind === 'new') { if (v === 'sing') x.model = sing; else if (x.model === sing) delete x.model }
  scheduleSave()
}
// a scene longer than its model shoots (WAN: 5 s) would play short and slip a clip's cuts after it
const tooLong = computed(() => !!(model.value && Number(props.s.seconds) > model.value.max_seconds + 0.01))
// a storyboard scene's length: 5 s, or longer where its model shoots that (LTX 10, H3 15). Part of the key: it is shot anew
const LENS = [5, 10, 15]
const lens = computed(() => (props.p.clip ? [] : LENS.filter((x) => x <= (model.value?.max_seconds || 5))))
const secs = computed(() => Number(props.s.seconds) || 5)
function setLen(x: number) {
  if (x === 5 && !props.p.scene_seconds) delete props.s.seconds; else props.s.seconds = x
  scheduleSave()
}
// the words that fit the lines: about 10 in 5 s, twice that in a 10 s grid's scene (prompts.line_problems)
const lineWords = computed(() => Math.round(LINE_WORDS * (props.p.scene_seconds ? Math.round(secs.value) : 5) / 5))
// phase 10: the scene's model may not speak (WAN): its lines would stay silent
const mute = computed(() => (model.value && !model.value.voice ? model.value.name : ''))
// «Нарисовать кадр» (app/frames.py): FLUX.2 Klein draws the first frame from the photos of the scene's people in its
// place; a new scene of a people video where someone has a photo (the hero's own, or the idea screen's) - or a scene
// whose actions name nobody, drawn empty (in its place's picture, else by Krea 2 from the words)
const canFrame = computed(() => props.s.kind === 'new' && props.p.mode !== 'none' && !isRaw(props.s)
  && (!hasPeople(props.s, props.p) || (props.p.cast || []).some((c: any) => c.photo || c.from_photo) || !!proj.value.settings.photo))
// «Кто в кадре» of the first frame (frames.people): as the scene's text says (frame_people unset), the heroes picked
// (cast indices), or nobody ([] - the place alone)
const framePeople = computed<number[] | null>(() => (Array.isArray(props.s.frame_people) ? props.s.frame_people : null))
const heroesWithPhoto = computed(() => (props.p.cast || []).map((c: any, i: number) => ({ i, c })).filter(({ c }) => c.photo || c.from_photo))
const heroLabel = (c: any, i: number) => c.name || ((props.p.cast || []).length > 1 ? t('board.cast.heroN', { n: i + 1 }) : c.gender === 'female' ? t('board.look.heroine') : t('board.look.hero'))
function setFramePeople(v: number[] | null) {
  if (v === null) delete props.s.frame_people
  else props.s.frame_people = v
  scheduleSave()
}
const toggleHero = (i: number) => {
  const cur = framePeople.value || []
  setFramePeople(cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i].sort())
}
const framing = computed(() => S.jobs.some((j) => j.kind === 'frame' && (j.status === 'running' || j.status === 'queued') && j.params?.project === proj.value.id))
const isFrame = computed(() => !!props.s.start_photo && props.s.start_photo.startsWith('frame_'))
// «Место» (app/places.py): the scene's place - its picture is the frame's second reference; a frame drawn before
// that picture changed (or without it) is drawn again by «Перерисовать кадр»
const places = computed(() => (props.p.places || []) as Record<string, any>[])
const scenePlace = computed(() => places.value.find((x) => x.id === props.s.place))
const frameOld = computed(() => !props.p.places_off && isFrame.value && !!scenePlace.value?.photo && props.s.frame?.place !== scenePlace.value.photo)
const setScenePlace = (v: string) => projectCall('PUT', `/scenes/${P.sel}/place`, { place: v || null })
async function drawFrame() {
  try { S.jobs = [...S.jobs, await post(`/api/projects/${proj.value.id}/scenes/${props.s.index}/start/draw`, {})] } catch (e) { banner((e as Error).message) }
}
const rawEl = ref<HTMLTextAreaElement | null>(null)
const rawLen = ref((props.s.raw || '').length)
defineExpose({ focusRaw: async () => { await nextTick(); rawEl.value?.focus() } })
const val = (e: Event) => (e.target as HTMLInputElement).value
const fileUrl = (path: string) => `/api/projects/${proj.value.id}/files/${path}`

function setRu(e: Event) {
  const x = props.s, v = val(e)
  if (x.ru === v) return
  x.ru = v
  if (!isRaw(x)) Object.assign(x, { ru_dirty: true, source: 'user', locked: true })   // the user's words: theirs, pinned
  forgetRewrite(x)
  scheduleSave()
}
// «Своими словами»: the text is the user's to write (an edit pins the scene, setRu); «Переписать»: the writer writes it
// anew - the scene is the writer's again, not pinned
const ruEl = ref<HTMLTextAreaElement>()
const ownWords = () => { ruEl.value?.focus(); ruEl.value?.select() }
// the user's own text (pinned) is asked about first; what the scene was is kept, «Вернуть» puts it back (lib/board.ts)
function rewriteIt() {
  const x = props.s
  if ((x.locked || x.source === 'user') && !confirm(t('board.insp.rewriteOwnAsk', { n: x.index + 1 }))) return
  rewriteScene(x, 'variant')
}
function setBeats(e: Event) {
  const x = props.s, beats = val(e).split('\n').map((b) => b.trim()).filter(Boolean)
  if (beats.join('\n') === (x.beats_en || []).join('\n')) return
  Object.assign(x, { beats_en: beats, source: 'user', locked: true })
  forgetRewrite(x)
  scheduleSave()
}
const setField = (k: string, v: unknown) => { props.s[k] = v; scheduleSave() }
// the last «Обновить сюжет» made from this scene: which scenes it rewrote and why
const mine = computed(() => (props.p.propagated?.from && props.p.propagated.from === props.s.id ? props.p.propagated : null))
const writing = computed(() => (P.proj ? liveWriter(P.proj.id) : null))
// «Починить лица»: {mode, strength} on the scene, or nothing (app/facefix.py; the fixed shot lives next to the shot)
function setFaces(on: boolean) {
  if (on) props.s.facefix = { mode: 'far', strength: 1 }; else delete props.s.facefix
  scheduleSave()
}
// saved on leaving the field: a save mid-typing would re-render under the caret
const typeRaw = (e: Event) => { props.s.raw = val(e); delete props.s.raw_ru; rawLen.value = props.s.raw.length }

// several people: who is in the scene
const who = computed(() => {
  const op = openerOf(props.p, props.s), own = props.s.who || []
  return { own, op, list: own.length ? own : props.s.kind === 'new' ? [] : (op || {}).who || [] }
})
function toggleWho(n: number, on: boolean) {
  const cur = new Set<number>(who.value.list)
  if (on) cur.add(n); else cur.delete(n)
  props.s.who = [...cur].sort((a, b) => a - b)
  scheduleSave()
}

// what the people of the scene say: a line under each of them (Russian, said in Russian); the server puts each into
// the timeline as a line of its own and the voices into the audio
const speakers = computed(() => (props.p.mode === 'none' ? [] : props.p.mode === 'several' ? who.value.list : [1]))
const lineOf = (n: number) => (props.s.lines || []).find((l: any) => l.who === n) || { who: n, text: '', how: '' }
function setLine(n: number, k: 'text' | 'how', v: string) {
  const lines = (props.s.lines || []).filter((l: any) => l.who !== n)
  const ln = { ...lineOf(n), [k]: k === 'text' ? v.trim() : v }
  if (ln.text) lines.push(ln)
  props.s.lines = lines.sort((a: any, b: any) => speakers.value.indexOf(a.who) - speakers.value.indexOf(b.who))
  scheduleSave()
}
const words = computed(() => (props.s.lines || []).filter((l: any) => speakers.value.includes(l.who))
  .reduce((a: number, l: any) => a + (l.text || '').split(/\s+/).filter(Boolean).length, 0))

// the scene's first frame: a photo of its own, the hero's photo, or the text only
function startFile(f?: File) {
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  projectCall('POST', `/scenes/${P.sel}/start`, fd)
}
// the picture the scene comes to (flf2v): LTX only
function endFile(f?: File) {
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  projectCall('POST', `/scenes/${P.sel}/end`, fd)
}
const toRaw = () => { Object.assign(props.s, { raw: props.s.prompt || '', locked: true, source: 'user' }); delete props.s.raw_ru; scheduleSave() }
function fromRaw() {
  if (!confirm(t('board.insp.fromRawAsk'))) return
  delete props.s.raw
  delete props.s.raw_ru
  scheduleSave()
}
const template = () => { props.s.raw = rawTemplate(props.s); delete props.s.raw_ru; rawLen.value = props.s.raw.length; scheduleSave() }

function del() {
  if (!confirm(t('board.insp.delAsk', { n: P.sel + 1 }))) return
  removeScenes(props.p, new Set([P.sel]))   // in a clip, the others stay on their bars
  P.sel = Math.max(0, P.sel - 1)
  scheduleSave()
}
</script>

<template>
  <!-- the head: the scene's number big, its time and kind, ‹ › to the scenes beside it, ⤢ its whole page -->
  <div v-if="!detail" class="insp-head si-head"><span class="si-n">{{ s.index + 1 }}</span>
    <span class="si-t"><b>{{ t('idea.sceneN', { n: s.index + 1 }) }}</b><small>{{ mmss(s.start) }}–{{ mmss(s.end) }}, {{ s.kind === 'new' ? t('board.insp.newScene') : t('board.card.cont') }}{{ s.source === 'user' ? ', ' + t('board.insp.yourPrompt') : '' }}</small></span>
    <span class="si-nav"><button type="button" class="ghost" :disabled="s.index === 0" :aria-label="t('board.insp.prev')" :title="t('board.insp.prev')" @click="go(-1)"><Icon name="back" :size="15" /></button>
      <button type="button" class="ghost" :disabled="s.index === p.scenes.length - 1" :aria-label="t('board.insp.next')" :title="t('board.insp.next')" @click="go(1)"><Icon name="forward" :size="15" /></button>
      <button type="button" class="ghost" :title="t('board.detail.openTitle')" :aria-label="t('board.detail.open')" @click="emit('expand')"><Icon name="expand" :size="15" /></button></span></div>
  <div class="insp stack" :class="{ 'si-body': !detail }" style="gap:14px">
    <!-- the notes: what to check, from the writer and from the shot clip; the writer's two ways to fix it. Their line
         keeps its height when a scene has none, so the panel under it doesn't jump as the selection moves (a click
         aimed at the tabs landed on «Переписать») -->
    <div v-if="problems || found.length" class="si-notes">
      <div v-if="problems" class="warn-line"><Icon name="warn" :size="14" /><span>{{ problems }}</span></div>
      <div v-for="line in foundLines(found)" :key="line" class="warn-line" :title="t('board.card.foundTitle')"><Icon name="warn" :size="14" /><span>{{ line }}</span></div>
      <div v-if="calm.length" class="si-calm" :title="t('board.card.calmTitle')">{{ t('board.card.calm', { x: calm.map(foundLabel).join('; ') }) }}</div>
      <div v-if="problems && !p.manual && !isRaw(s) && !s.locked" class="acts">
        <button type="button" class="btn" :disabled="!!writing" @click="rewriteScene(s, 'improve')"><Icon name="spark" />{{ t('board.improve') }}</button>
        <button type="button" class="btn" :disabled="!!writing" @click="rewriteScene(s, 'variant')"><Icon name="shuffle" />{{ t('board.variant') }}</button></div>
    </div>
    <div v-else-if="calm.length" class="si-notes none" :title="t('board.card.calmTitle')">{{ t('board.card.calm', { x: calm.map(foundLabel).join('; ') }) }}</div>
    <div v-else-if="!detail" class="si-notes none">{{ t('board.insp.noNotes') }}</div>
    <!-- what happens: the scene's main text, always in sight -->
    <template v-if="!isRaw(s)">
      <label><span class="lbl">{{ t('board.insp.what') }} <HelpQ id="inspector" term="Что происходит" /></span><textarea ref="ruEl" class="field-in si-what" rows="3" :value="s.ru" @change="setRu" /></label>
      <template v-if="s.ru_dirty"><div class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('board.card.textChanged') }}</span></div>
        <button type="button" class="btn" :disabled="!!writing" @click="rewrite('translate', [P.sel])"><Icon name="spark" />{{ t('board.look.updatePrompt') }}</button></template>
      <div class="si-author"><span class="cs-who" :class="authorOf(s)">{{ t(`board.skel.who.${authorOf(s)}`) }}</span>
        <button type="button" class="ghost" :title="t('board.insp.ownWordsTitle')" @click="ownWords"><Icon name="pen" :size="14" />{{ t('board.insp.ownWords') }}</button>
        <button v-if="!p.manual" type="button" class="ghost" :disabled="!!writing" :title="t('board.insp.rewriteItTitle')" @click="rewriteIt"><Icon name="spark" :size="14" />{{ t('board.insp.rewriteIt') }}</button></div>
      <button v-if="canUndoRewrite(s)" type="button" class="btn si-undo" :disabled="!!writing" :title="t('board.insp.undoRewriteTitle')" @click="undoRewriteOf(s)"><Icon name="back" :size="14" />{{ t('board.insp.undoRewriteLong') }}</button>
    </template>

    <!-- the tabs (the scene's whole page shows every part one under another) -->
    <nav v-if="!detail" class="si-tabs" role="tablist" :aria-label="t('board.insp.tabs')">
      <button v-for="k in tabs" :key="k" type="button" role="tab" :aria-selected="tab === k" :class="{ on: tab === k }" @click="tab = k">{{ t(`board.insp.tab.${k}`) }}<small v-if="k === 'takes' && takeCount > 1">{{ takeCount }}</small></button>
    </nav>

    <!-- «Начало»: a new scene or a continuation, its place, its first frame (drawn, a photo, by text) and last frame -->
    <template v-if="on('start')">
    <SceneStart :p="p" :s="s" />
    <div v-if="s.kind === 'new'" class="stack start-box"><span class="lbl">{{ t('board.insp.firstFrame') }} <HelpQ id="inspector" term="Первый кадр" /></span>
      <label v-if="places.length && p.mode !== 'none' && !p.places_off" class="stack" style="gap:4px"><span class="lbl">{{ t('board.insp.place') }} <HelpQ id="look" term="Места" /></span>
        <select class="field-in" :value="s.place || ''" @change="setScenePlace(val($event))"><option value="">{{ t('board.insp.placeNone') }}</option>
          <option v-for="x in places" :key="x.id" :value="x.id">{{ x.name_ru }}{{ x.photo ? '' : ' · ' + t('board.insp.placeNoPic') }}</option></select></label>
      <div v-if="canFrame" class="stack" style="gap:4px"><span class="lbl">{{ t('board.insp.frameWho') }} <small>{{ t('board.insp.frameWhoSub') }}</small></span>
        <div class="chips"><button type="button" class="chip" :class="{ on: framePeople === null }" :title="t('board.insp.frameWhoAutoTitle')" @click="setFramePeople(null)">{{ t('board.insp.frameWhoAuto') }}</button>
          <button v-for="h in heroesWithPhoto" :key="h.i" type="button" class="chip" :class="{ on: framePeople?.includes(h.i) }" @click="toggleHero(h.i)">{{ heroLabel(h.c, h.i) }}</button>
          <button type="button" class="chip" :class="{ on: framePeople !== null && !framePeople.length }" :title="t('board.insp.frameWhoNoneTitle')" @click="setFramePeople([])">{{ t('board.insp.frameWhoNone') }}</button></div></div>
      <PicLoraLine v-if="canFrame" :models="['flux2']" />
      <div v-if="frameOld" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('board.insp.placeChanged') }}</span></div>
      <template v-if="!s.start_photo">
        <span class="muted" style="font-size:13px">{{ t('board.insp.textOnly') }}</span>
        <div class="acts"><button v-if="canFrame" type="button" class="btn" :disabled="framing" :title="t('board.insp.drawFrameTitle')" @click="drawFrame"><Icon name="spark" />{{ t('board.insp.drawFrame') }}</button>
          <label class="btn" style="cursor:pointer"><Icon name="image" />{{ t('board.insp.startPhoto') }}<input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="startFile(($event.target as HTMLInputElement).files?.[0])"></label>
          <button v-if="proj.settings.photo" type="button" class="btn" @click="projectCall('POST', `/scenes/${P.sel}/start/hero`)"><Icon name="user" />{{ t('board.insp.heroPhoto') }}</button></div>
      </template>
      <template v-else>
        <div class="start-row"><img v-zoom :src="fileUrl(s.start_photo)" :alt="t('board.insp.firstFrameAlt', { n: s.index + 1 })">
          <span>{{ isFrame ? t('board.insp.frameDrawn') : t('board.insp.startsFromPhoto') }}<small v-if="isFrame && s.frame?.face != null"> · {{ t('board.insp.frameFace', { x: pct(s.frame.face) }) }}</small><small>{{ isRaw(s) ? t('board.insp.startRaw', { line: 'Continue seamlessly from <Picture 1>.' })
            : s.start_en ? t('board.insp.writerSees', { x: s.start_en }) : t('board.insp.writerNotLooked') }}</small></span></div>
        <div v-if="isFrame && s.frame && s.frame.ok === false" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('board.insp.frameBad') }}</span></div>
        <div class="acts"><button v-if="canFrame" type="button" class="btn" :disabled="framing" :title="t('board.insp.drawFrameTitle')" @click="drawFrame"><Icon name="spark" />{{ isFrame ? t('board.insp.drawFrameAgain') : t('board.insp.drawFrame') }}</button>
          <button v-if="!isRaw(s) && !isFrame" type="button" class="btn" @click="rewrite('frame', [P.sel])"><Icon name="spark" />{{ t('board.insp.rewriteForPhoto') }}</button>
          <label class="btn" style="cursor:pointer"><Icon name="image" />{{ t('board.look.otherPhoto') }}<input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="startFile(($event.target as HTMLInputElement).files?.[0])"></label>
          <button type="button" class="btn" @click="projectCall('DELETE', `/scenes/${P.sel}/start`)"><Icon name="close" />{{ t('board.look.remove') }}</button></div>
      </template>
    </div>

    <div v-if="model?.ends || s.end_photo" class="stack start-box"><span class="lbl">{{ t('board.insp.lastFrame') }} <small>{{ t('board.insp.lastFrameSub') }}</small></span>
      <template v-if="!s.end_photo">
        <span class="muted" style="font-size:13px">{{ t('board.insp.endsWherever') }}</span>
        <div class="acts"><label class="btn" style="cursor:pointer"><Icon name="image" />{{ t('board.insp.comeToFrame') }}<input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="endFile(($event.target as HTMLInputElement).files?.[0])"></label></div>
      </template>
      <template v-else>
        <div class="start-row"><img v-zoom :src="fileUrl(s.end_photo)" :alt="t('board.card.lastFrame', { n: s.index + 1 })">
          <span>{{ t('board.insp.comesToFrame') }}<small>{{ model?.ends ? t('board.insp.describeHow') : t('board.insp.cantEnd', { m: model?.name }) }}</small></span></div>
        <div class="acts"><label class="btn" style="cursor:pointer"><Icon name="image" />{{ t('board.insp.otherFrame') }}<input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="endFile(($event.target as HTMLInputElement).files?.[0])"></label>
          <button type="button" class="btn" @click="projectCall('DELETE', `/scenes/${P.sel}/end`)"><Icon name="close" />{{ t('board.look.remove') }}</button></div>
      </template>
    </div>

    </template>

    <!-- «Сцена»: the camera and framing, the clip's shot kind, the story after an edit -->
    <template v-if="on('scene')">
      <template v-if="!isRaw(s)">
      <div class="row2">
        <label><span class="lbl">{{ t('board.insp.camera') }} <HelpQ id="inspector" term="Камера" /></span><select class="field-in" :value="s.camera" @change="setField('camera', val($event))"><option v-for="(v, k) in CAMERAS" :key="k" :value="k">{{ v }}</option></select></label>
        <label><span class="lbl">{{ t('board.insp.framing') }} <HelpQ id="inspector" term="План" /></span><select class="field-in" :value="s.framing" @change="setField('framing', val($event))"><option v-for="(v, k) in FRAMINGS" :key="k" :value="k">{{ v }}</option></select></label>
      </div>
      <!-- «Склейки внутри сцены»: each action a shot of its own, cut hard (app/planner/prompts.py shots_timeline) -->
      <label v-if="(s.beats_en || []).length > 1" class="check-row" :title="t('board.insp.cutsTitle')"><input type="checkbox" :checked="!!s.cuts" @change="setField('cuts', ($event.target as HTMLInputElement).checked || undefined)">{{ t('board.insp.cuts') }}</label>
      <p v-if="s.cuts" class="muted small">{{ model && model.id !== 'h3' ? t('board.insp.cutsH3', { m: model.name }) : (s.lines || []).some((l: any) => l.text) ? t('board.insp.cutsLines') : t('board.insp.cutsHint') }}</p>
      </template>
    <div v-if="p.clip && s.part" class="stack clip-box" style="gap:6px">
      <span class="lbl">{{ t('board.insp.shotKind') }} <HelpQ id="clip" term="Типы сцен" />
        <small>{{ partName(s.part) }} · {{ s.loud ? t('board.insp.loud') : t('board.insp.quiet') }} · {{ dec((s.seconds || 5).toFixed(1)) }} {{ t('common.s') }}</small></span>
      <select class="field-in" :value="s.shot || 'perform'" @change="setShot(val($event))">
        <option v-for="[k, l] in SHOTS" :key="k" :value="k" :disabled="k === 'sing' && !sungWords">{{ l }}</option></select>
      <span class="muted small">{{ t(`board.shot.${s.shot || 'perform'}Tip`) }}</span>
      <span class="muted clip-sung">{{ sungWords ? `♪ ${sungWords}` : t('board.insp.noSinging') }}</span></div>


    <template v-if="isRaw(s)">
      <div class="stack" style="gap:6px"><div class="sec-head"><span class="lbl">{{ t('board.insp.rawLbl') }} <HelpQ id="inspector" term="Свой промт" /></span>
          <span class="raw-tools"><button v-if="!s.raw" type="button" class="link" @click="template">{{ t('board.insp.preset') }}</button><small>{{ rawLen }} / {{ max }}</small></span></div>
        <textarea ref="rawEl" class="field-in raw-in" rows="16" :aria-label="t('board.insp.rawAria')" :maxlength="max" spellcheck="false" :value="s.raw || ''"
          :placeholder="s.kind === 'continue' ? 'Continue seamlessly from <Picture 1>. …' : 'Cinematic shot of …'" @input="typeRaw" @change="scheduleSave()" />
        <details v-if="s.raw_ru" class="raw-ru"><summary>{{ t('board.insp.rawRu') }} <small>{{ t('board.insp.rawRuSub') }}</small></summary><p>{{ s.raw_ru }}</p></details></div>
      <label><span class="lbl">{{ t('board.insp.what') }} <small>{{ t('board.insp.whatSub') }}</small></span><input class="field-in" :value="s.ru || ''" @change="setRu"></label>
      <button v-if="!p.manual" type="button" class="btn" :title="t('board.insp.fromRawTitle')" @click="fromRaw"><Icon name="retake" />{{ t('board.insp.fromRaw') }}</button>
    </template>
      <template v-if="!isRaw(s)">
      <!-- «Обновить сюжет от этой сцены»: the scenes this one now contradicts, rewritten (app/llm/writer.py propagate) -->
      <div v-if="!p.manual && p.scenes.length > 1" class="stack start-box"><span class="lbl">{{ t('board.insp.story') }} <small>{{ t('board.insp.storySub') }}</small></span>
        <div class="acts"><button type="button" class="btn" :disabled="!!writing" :title="t('board.insp.propagateTitle')" @click="rewrite('propagate', [P.sel])"><Icon name="spark" />{{ t('board.insp.propagate') }}</button></div>
        <template v-if="mine">
          <p v-if="!mine.scenes.length" class="muted small">{{ t('board.insp.propagateNone') }}</p>
          <template v-else>
            <span class="muted small">{{ t('board.insp.propagated', mine.scenes.length) }}</span>
            <button v-for="x in mine.scenes" :key="x.id" type="button" class="link" style="text-align:left;font-size:13px;line-height:1.4" @click="P.sel = x.index"><b>{{ t('idea.sceneN', { n: x.index + 1 }) }}</b> — {{ x.reason }}</button>
            <div v-if="Object.keys(mine.before || {}).length" class="acts"><button type="button" class="btn" @click="projectCall('POST', '/propagate/undo')"><Icon name="reset" />{{ t('board.insp.propagateUndo') }}</button></div>
          </template>
        </template>
      </div>
      </template>
    </template>

    <!-- «Съёмка»: the model and the scene's length, the faces, the scene's LoRA, the prompt and the graph -->
    <template v-if="on('shoot')">
    <label v-if="s.kind === 'new'"><span class="lbl">{{ t('idea.model') }} <HelpQ id="inspector" term="Модель сцены" />
        <small>{{ s.model ? t('board.insp.ownModel') : t('board.insp.asVideo') }}</small></span>
      <select class="field-in" :value="s.model || ''" @change="setModel(val($event))">
        <option value="">{{ t('board.insp.asVideoOpt', { m: videoModel?.name }) }}</option>
        <option v-for="m in models.filter((x) => !x.imported || x.id === s.model)" :key="m.id" :value="m.id">{{ m.name }}{{ m.missing.length ? ` (${t('idea.pick.noWeights')})` : '' }}</option></select></label>
    <p v-else-if="opener.model" class="muted model-note"><Icon name="clapper" :size="13" />{{ t('board.insp.chainModel', { m: model?.name, n: opener.index + 1 }) }}</p>
    <!-- the length beside the model: the lengths a scene may have are its model's -->
    <div v-if="lens.length > 1" class="stack" style="gap:6px"><span class="lbl">{{ t('idea.length') }} <HelpQ id="inspector" term="Длина сцены" />
        <small>{{ t('board.insp.shootsUpTo', { m: model?.name, s: model?.max_seconds }) }}</small></span>
      <div class="seg"><button v-for="x in lens" :key="x" type="button" :class="{ on: secs === x }" :aria-pressed="secs === x" @click="setLen(x)">{{ x }} {{ t('common.s') }}</button></div></div>
    <div v-if="tooLong" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('board.insp.tooLong', { m: model?.name, max: model?.max_seconds, s: dec(Number(s.seconds).toFixed(1)) }) }}</span></div>
    <!-- «Починить лица» (app/facefix.py): the shot's far faces made sharp after the shot; the hero's look goes into the prompt -->
    <div v-if="p.mode !== 'none'" class="stack start-box"><span class="lbl">{{ t('board.insp.faces') }} <small>{{ t('board.insp.facesSub') }}</small></span>
      <label class="check-row"><input type="checkbox" :checked="!!s.facefix" @change="setFaces(($event.target as HTMLInputElement).checked)">{{ t('board.insp.facesOn') }}</label>
      <template v-if="s.facefix">
        <label class="stack"><span class="lbl">{{ t('board.insp.facesWhich') }}</span>
          <select class="field-in" :value="s.facefix.mode || 'far'" @change="s.facefix.mode = ($event.target as HTMLSelectElement).value; scheduleSave()">
            <option v-for="m in ['very_far', 'far', 'medium', 'all']" :key="m" :value="m">{{ t(`board.insp.facesMode.${m}`) }}</option></select></label>
        <label class="stack"><span class="lbl">{{ t('board.insp.facesStrength') }}</span>
          <input class="field-in" type="number" step="0.05" min="0" max="1" :value="s.facefix.strength ?? 1" @input="s.facefix.strength = +($event.target as HTMLInputElement).value; scheduleSave()"></label>
        <p class="muted small">{{ t('board.insp.facesHow') }}</p>
      </template>
    </div>

      <SceneTakes v-if="!detail" :s="s" lora-only />
      <details v-if="!isRaw(s)" :open="P.openEn" @toggle="P.openEn = ($event.target as HTMLDetailsElement).open"><summary>{{ t('board.insp.promptEn') }}</summary>
        <label style="margin-top:8px"><span class="lbl">{{ t('board.insp.beats') }} <HelpQ id="inspector" term="Действия по строкам" /> <small>{{ t('board.insp.beatsSub') }}</small></span>
          <textarea class="field-in" rows="4" :value="(s.beats_en || []).join('\n')" @change="setBeats" /></label>
        <pre v-if="!sent || sent.model === 'h3'">{{ s.prompt }}</pre>
        <template v-else><span class="lbl">{{ t('board.insp.gets', { m: sent.name }) }} <small>{{ t('board.insp.getsSub') }}</small></span><pre>{{ sent.text }}</pre></template>
        <button type="button" class="btn" :title="t('board.insp.toRawTitle', { m: model?.short || t('board.insp.theModel') })" @click="toRaw"><Icon name="pen" />{{ t('board.insp.toRaw') }}</button></details>
    <!-- «Граф для ComfyUI»: what a new shot of the scene sends to the worker (app/render.py scene_graph_preview) -->
    <details class="graph-peek" @toggle="($event.target as HTMLDetailsElement).open && loadGraph()"><summary>{{ t('board.insp.graph') }} <small>{{ t('board.insp.graphSub') }}</small></summary>
      <p v-if="peek?.error" class="muted small">{{ peek.error }}</p>
      <template v-else-if="peek">
        <span class="muted small">{{ t('board.insp.graphFacts', { m: peek.model, n: Object.keys(peek.graph).length, key: peek.key }) }}{{ peek.cached ? t('board.insp.graphCached') : '' }}</span>
        <ul v-if="Object.keys(peek.inputs).length" class="muted small"><li v-for="(v, k) in peek.inputs" :key="k"><code>{{ k }}</code> ← {{ v }}</li></ul>
        <pre>{{ JSON.stringify(peek.graph, null, 1) }}</pre>
        <button type="button" class="btn" @click="copyGraph"><Icon name="layers" />{{ copied ? t('board.insp.graphCopied') : t('board.insp.graphCopy') }}</button>
      </template>
    </details>

    </template>

    <!-- «Реплики»: who is in the scene and what each one says -->
    <template v-if="on('lines') && !isRaw(s)">
      <div v-if="p.mode === 'several'" class="stack" style="gap:6px"><span class="lbl">{{ t('board.insp.who') }} <HelpQ id="inspector" term="Кто в сцене" />
          <small>{{ s.kind === 'new' ? t('board.insp.whoInherit') : who.own.length ? t('board.insp.whoOwn') : t('board.insp.whoAs', { n: (who.op ? who.op.index : 0) + 1 }) }}</small></span>
        <label v-for="(c, i) in p.cast" :key="i" class="check-row"><input type="checkbox" :checked="who.list.includes(i + 1)" @change="toggleWho(i + 1, ($event.target as HTMLInputElement).checked)">{{ castName(c, i) }}</label></div>
      <div v-if="p.mode !== 'none'" class="stack lines-box" style="gap:8px">
        <div class="sec-head"><span class="lbl">{{ t('board.insp.lines') }} <HelpQ id="inspector" term="Реплики" /> <small>{{ t('board.insp.linesSub') }}</small></span>
          <small :class="{ warn: words > lineWords }">{{ t('board.insp.words', { n: words, max: lineWords }) }}</small></div>
        <div v-if="mute" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('board.insp.mute', { m: mute }) }}</span></div>
        <p v-if="!speakers.length" class="muted" style="margin:0;font-size:13px">{{ t('board.insp.markWho') }}</p>
        <div v-for="n in speakers" :key="n" class="line-row">
          <div class="line-head"><span class="line-who">{{ castName(p.cast?.[n - 1] || {}, n - 1) }}</span>
            <select class="line-how" :value="lineOf(n).how" :aria-label="t('board.insp.how')" @change="setLine(n, 'how', val($event))">
              <option v-for="[k, l] in HOW_RU" :key="k" :value="k">{{ l }}</option></select></div>
          <textarea class="field-in line-text" rows="2" :value="lineOf(n).text" :placeholder="t('board.insp.silent')" :aria-label="t('board.insp.says', { n })" @change="setLine(n, 'text', val($event))" />
        </div>
        <button v-if="speakers.length" type="button" class="btn" :title="t('board.insp.inventTitle')" @click="rewrite('lines', [P.sel])"><Icon name="spark" />{{ t('board.insp.invent') }}</button>
      </div>
    </template>

    <!-- «Дубли» (the scene's page shows the takes itself and only the LoRA here) -->
    <SceneTakes v-if="on('takes')" :s="s" :lora-only="detail" :takes-only="!detail" />

    <div v-if="detail" class="acts"><button v-if="!isRaw(s)" type="button" class="btn" @click="s.locked = !s.locked; scheduleSave()"><Icon name="lock" :size="14" />{{ s.locked ? t('board.unpin') : t('board.pin') }}</button>
      <button type="button" class="btn danger" :disabled="p.scenes.length < 2" @click="del"><Icon name="trash" />{{ t('board.insp.delete') }}</button></div>
  </div>
  <!-- the foot, always in sight: one more take now, pin, delete -->
  <div v-if="!detail" class="si-foot">
    <button type="button" class="btn si-take" :disabled="busy" :title="t('board.takes.moreTitle')" @click="moreTake(s)"><Icon name="clapper" />{{ busy ? t('board.takes.taking') : t('board.takes.more') }}</button>
    <button v-if="!isRaw(s)" type="button" class="btn" :aria-pressed="!!s.locked" @click="s.locked = !s.locked; scheduleSave()"><Icon name="lock" :size="14" />{{ s.locked ? t('board.unpin') : t('board.pin') }}</button>
    <button type="button" class="btn danger" :disabled="p.scenes.length < 2" :aria-label="t('board.insp.delete')" :title="t('board.insp.delete')" @click="del"><Icon name="trash" /></button>
  </div>
</template>
