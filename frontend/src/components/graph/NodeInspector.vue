<script setup lang="ts">
// The selected node, editable: its own fields by type, and what can be done with it - «Снять до сюда», «Ещё дубль»,
// «Описать по фото», «Написать», «Развернуть в сцены», «Дублировать ветку». The video card is busy only by a button.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import HelpQ from '../HelpQ.vue'
import SceneForm from '../lab/SceneForm.vue'
import VoiceRecorder from '../VoiceRecorder.vue'
import { ENGINE_NAME, GE, ICON, MAKES, SCENE_S, WHO_COLOR, addNode, duplicateBranch, expand, feedSeconds, fileUrl, flush, inputsOf, link, live, nodeOf, refLoraOf, removeNodes, rseed,
  drawFirstFrame, graphPics, ruTitle, runLlm, runTo, secondsOf, speakersIn, tOf, touch, typeTitle, upload } from '../../lib/graphDoc'
import { S, banner, h3Ready, lorasFor, v2vLoras } from '../../lib/store'
import { api, post } from '../../lib/api'
import type { Job } from '../../lib/types'
import { compose, empty, parse, type Fields } from '../../lib/sceneForm'
import { checkPrompt } from '../../lib/promptChecks'
import { inLang } from '../../lib/textLang'
import { GENDERS, HOW_RU, LENGTHS } from '../../lib/consts'
import HeroKind from '../board/HeroKind.vue'
import PoolPanel from './PoolPanel.vue'
import BeatPanel from './BeatPanel.vue'
import PublishPanel from './PublishPanel.vue'
import RoleSelect from './RoleSelect.vue'
import BeatHelp from '../BeatHelp.vue'
import { HERO_PRESETS, type Named, beatInfo, nameOf as beatName } from '../../lib/beat'
import ActorPanel from './ActorPanel.vue'
import { NODE_HELP, nextStep, nodeWhat, whoName } from '../../lib/nodeHelp'
import { dec, mmss } from '../../lib/format'
import { L, loadLooks, lookName, lookOf } from '../../lib/looks'
import { screenplayStats } from '../../lib/screenplay'
import { openZoom } from '../../lib/zoom'

const props = defineProps<{ id: string }>()
const { t: tx } = useI18n()
const n = computed(() => nodeOf(props.id))
const d = computed(() => (n.value?.data || {}) as Record<string, any>)
const t = computed(() => (n.value ? tOf(n.value) : ''))
const spec = computed(() => GE.types[t.value])
const st = computed(() => GE.state?.nodes[props.id])
const busy = computed(() => !!live())
// the .srt is made from the saved graph: save first, then let the browser download it
async function downloadSrt() {
  await flush()
  const a = document.createElement('a')
  a.href = `/api/projects/${GE.id}/nodes/${props.id}/srt`
  a.download = 'screenplay.srt'
  document.body.appendChild(a); a.click(); a.remove()
}
const set = (k: string, v: unknown) => { d.value[k] = v; touch() }
// «Стиль проекта» (the bar above the canvas): the writer reads the delivery and the look, not its mood; a scene may
// have its own look (app/graph.look_text)
const styled = computed(() => 'delivery' in (GE.proj?.settings || {}))
loadLooks().catch(() => {})
// Krea 2 reads its text alone: switching to it lets go of the pictures on «образцы»
function setPictureModel(m: string) {
  if (m !== 'flux2') GE.edges = GE.edges.filter((e) => !(e.target === props.id && e.targetHandle === 'ref'))
  set('model', m)
}
const help = computed(() => NODE_HELP[t.value])
const next = computed(() => nextStep(props.id))

// the translator (the writer, as in the lab): an idea into the graph model's English prompt, a hero's Russian look into
// the English one that goes into the prompts. A job in the GPU queue; only by the button
const tr = ref<{ state: string; secs?: number; text?: string } | null>(null)
async function translateJob(path: string, body: Record<string, unknown>): Promise<Record<string, any> | null> {
  tr.value = { state: 'wait' }
  let job: Job
  try { job = await post(path, { ...body, model: S.llm || null }) } catch (e) { tr.value = { state: 'error', text: (e as Error).message }; return null }
  while (job.status === 'queued' || job.status === 'running') {
    await new Promise((ok) => setTimeout(ok, 1000))
    try { job = await api(`/api/jobs/${job.id}`) } catch { tr.value = null; return null }
    tr.value = { state: job.status === 'queued' ? 'queue' : 'wait', secs: Math.round(job.elapsed || 0) }
  }
  if (job.status !== 'done' || !job.result) { tr.value = { state: 'error', text: job.error || tx('nodesPanel.noTranslation') }; return null }
  tr.value = { state: 'done', secs: Math.round(job.elapsed || 0) }
  return job.result as Record<string, any>
}
const trBusy = computed(() => !!tr.value && (tr.value.state === 'wait' || tr.value.state === 'queue'))
// What to make from an idea (app/llm/idea.py, POST /api/llm/idea): a video prompt, a picture prompt, a draft script, or the
// writer's free talk. Prompts come with the idea's links each takes (they move onto the prompt - the model would get the
// Russian as it is); a script and a talk go to a «Заметка» beside the idea and change no links. Only by the buttons.
const IDEA_MODES = ['video', 'picture', 'script'] as const
const ideaFeeds = computed(() => GE.edges.filter((e) => e.source === props.id && ['scene', 'picture'].includes(tOf(nodeOf(e.target)!))).map((e) => tOf(nodeOf(e.target)!)))
// no mode picked: by the wiring - pictures only -> a picture prompt, scenes only (or nothing) -> a video one, both -> two
const ideaAuto = computed(() => (ideaFeeds.value.includes('scene') && ideaFeeds.value.includes('picture') ? 'both' : ideaFeeds.value.length && !ideaFeeds.value.includes('scene') ? 'picture' : 'video'))
const ideaMode = computed(() => (IDEA_MODES as readonly string[]).includes(d.value.mode) ? d.value.mode as string : '')
const ideaGo = computed(() => ideaMode.value || ideaAuto.value)
function setIdeaMode(v: string) { if (v) set('mode', v); else { delete d.value.mode; touch() } }
async function ideaMake(mode: string) {
  const idea = n.value, text = (d.value.text || '').trim()
  if (!idea || !text || trBusy.value) return
  const data = idea.data as Record<string, any>
  const into = GE.edges.filter((e) => e.source === idea.id && ['scene', 'picture'].includes(tOf(nodeOf(e.target)!)))
  const targets = into.map((e) => {
    const x = nodeOf(e.target)!, scene = tOf(x) === 'scene'
    return { id: e.id, kind: scene ? 'scene' : 'picture', seconds: scene ? secondsOf(x) : 5, frame: scene && inputsOf(x.id, 'start').length > 0,
      flux: !scene && (x.data as any).model === 'flux2' && inputsOf(x.id, 'ref').length > 0 }
  })
  const r = await translateJob('/api/llm/idea', { text, mode, targets, video_model: graphModel.value })
  if (!r) return
  const name = data.title || tx('nodes.title.idea')
  if (r.note) {
    // a script / a talk: a note beside the idea (the same one again; the user's edits ask first)
    const key = mode === 'think' ? 'think' : 'script'
    let nn = data[`note_${key}_id`] ? nodeOf(data[`note_${key}_id`]) : null
    const body = r.note.title && key === 'script' ? `${r.note.title}

${r.note.text}` : r.note.text
    if (nn && tOf(nn) === 'note') {
      const nd = nn.data as Record<string, any>
      if ((nd.text || '').trim() && nd.text !== data[`note_${key}_text`] && !confirm(tx('nodesPanel.replaceNote'))) return
      nd.text = body
    } else {
      nn = addNode('note', idea.position.x + 320, idea.position.y, { title: tx(key === 'think' ? 'nodes.ideaThink' : 'nodes.ideaScript', { name }), text: body })
      data[`note_${key}_id`] = nn.id
    }
    data[`note_${key}_text`] = body
    touch()
    banner(tx(key === 'think' ? 'nodesPanel.thinkReady' : 'nodesPanel.scriptReady'))
    return
  }
  let moved = 0
  for (const pr of (r.prompts || []) as { form: string; en: string; targets: string[] }[]) {
    const pic = pr.form !== 'video', key = pic ? 'prompt_pic_id' : 'prompt_id'
    let p = data[key] ? nodeOf(data[key]) : null
    if (p && tOf(p) === 'prompt') {
      const pd = p.data as Record<string, any>
      if ((pd.text || '').trim() && pd.text !== data[pic ? 'prompt_pic_en' : 'prompt_en'] && !confirm(tx('nodesPanel.replacePrompt'))) continue
      pd.text = pd.enDone = pr.en; pd.ru = pd.ruDone = text
      // an older prompt that still feeds a picture keeps its still's text
      if (!GE.edges.some((x) => x.source === p!.id && tOf(nodeOf(x.target)!) === 'picture')) delete pd.text_picture
    } else {
      p = addNode('prompt', idea.position.x + 320, idea.position.y, { title: tx(pic ? 'nodes.ideaPromptPic' : 'nodes.ideaPrompt', { name }), text: pr.en, ru: text, enDone: pr.en, ruDone: text })
      data[key] = p.id
    }
    data[pic ? 'prompt_pic_en' : 'prompt_en'] = pr.en
    for (const id of pr.targets) {
      const e = into.find((x) => x.id === id)
      if (e) { link({ source: p.id, sourceHandle: 'text', target: e.target, targetHandle: e.targetHandle }); moved++ }
    }
  }
  touch()
  banner(tx('nodesPanel.promptReady', { rest: moved ? tx('nodesPanel.linkedTo', { what: moved === 1 ? tx('nodesPanel.toScene') : tx('nodesPanel.toScenes') }) : tx('nodesPanel.linkIt') }))
}
// what a hero is: age and gender are a person's only; a look written for another kind is the user's to redo («В английский»)
function setKind(k: string) {
  set('kind', k === 'person' ? '' : k)
  if (k !== 'person') { set('age', ''); set('gender', '') }
  if (k === 'faceless') applyHero()
}
// «Без лица» (a beat clip's hero): one of the five presets; the server writes the look from it (PUT .../hero-preset -> {data})
const presets = ref<Named[]>([])
const songId = computed(() => { const s = GE.nodes.find((x) => tOf(x) === 'song' && (x.data as any).song); return s ? (s.data as any).song as string : '' })
watch(() => [d.value.kind === 'faceless', songId.value], async ([on, sid]) => {
  if (!on || !sid) return
  try { presets.value = (await beatInfo(sid as string)).presets } catch { /* the page's own names stay */ }
}, { immediate: true })
const presetList = computed<Named[]>(() => (presets.value.length ? presets.value : HERO_PRESETS.map((id) => ({ id, ru: tx(`beat.hero.${id}`), en: tx(`beat.hero.${id}`) }))))
// a preset, a preset with the user's details (`desc`), or «Свой герой» (`own`: the words alone; `face_hidden` off lets a face show)
async function applyHero(patch: { preset?: string; own?: boolean; face_hidden?: boolean } = {}) {
  const own = patch.own ?? !!d.value.own
  try {
    await flush()
    const r = await api<{ data: Record<string, any> }>(`/api/projects/${GE.id}/nodes/${props.id}/hero-preset`, { method: 'PUT',
      body: { preset: own ? '' : patch.preset ?? (d.value.preset || HERO_PRESETS[0]), own, text: d.value.desc || '', face_hidden: patch.face_hidden ?? d.value.face_hidden !== false } })
    for (const k of ['own', 'desc', 'face_hidden', 'head_en']) if (!(k in r.data)) delete d.value[k]
    Object.assign(d.value, r.data, { kind: 'faceless' })
    touch(50)
  } catch (e) { banner((e as Error).message) }
}
// a hero's Russian look -> the English look and outfit
async function heroToEnglish() {
  const ru = (d.value.ru || '').trim()
  if (!ru || trBusy.value) return
  if (((d.value.en || '').trim() || (d.value.outfit_en || '').trim()) && !confirm(tx('nodesPanel.replaceLook'))) return
  const hero = d.value
  const r = await translateJob('/api/llm/translate-look', { ru, gender: hero.gender || '', age: hero.age || null, kind: hero.kind || 'person' })
  if (!r) return
  hero.en = r.en; hero.outfit_en = r.outfit_en
  touch()
}
const srcNode = (port: string) => { const e = inputsOf(props.id, port)[0]; return e ? nodeOf(e.source) : null }

// a prompt: the lab's fields (English) or its text; the frame line goes in when a scene it feeds starts from a frame
// where the prompt goes: only into «Картинка» nodes (Krea, a still) - the translation takes the picture's form, not the video model's
const feedsTypes = computed(() => GE.edges.filter((e) => e.source === props.id && e.sourceHandle === 'text').map((e) => nodeOf(e.target)).filter(Boolean).map((x) => tOf(x!)))
const feedsPicture = computed(() => feedsTypes.value.includes('picture') && !feedsTypes.value.includes('scene'))
// ... into a picture AND a scene: two texts - the scene's (the video model's form) and the picture's (text_picture, a
// still's form); the picture node takes the second when it is there
const feedsBoth = computed(() => feedsTypes.value.includes('picture') && feedsTypes.value.includes('scene'))
// the picture's form: Krea 2 (a still from the text) or FLUX.2 Klein (a still from reference pictures: "the first image")
const pictureTarget = (from: string) => {
  const pics = GE.edges.filter((e) => e.source === from && e.sourceHandle === 'text').map((e) => nodeOf(e.target)).filter((x) => x && tOf(x) === 'picture')
  return pics.some((x) => (x!.data as any).model === 'flux2' && inputsOf(x!.id, 'ref').length) ? 'frame' : 'picture'
}
const feedsStart = computed(() => GE.edges.some((e) => e.source === props.id && GE.edges.some((x) => x.target === e.target && x.targetHandle === 'start')))
const fields = ref<Fields>(empty())
watch(() => props.id, () => { if (d.value.fields) fields.value = JSON.parse(JSON.stringify(d.value.fields)) }, { immediate: true })
function setMode(m: 'text' | 'fields') {
  if (m === 'fields') { fields.value = parse(d.value.text || '', 'en').fields; d.value.fields = JSON.parse(JSON.stringify(fields.value)) }
  else delete d.value.fields
  touch()
}
// the timeline runs to the length of the scene the prompt feeds
const secs = computed(() => feedSeconds(props.id))
watch(fields, (f) => { if (!d.value.fields || t.value !== 'prompt') return; d.value.fields = JSON.parse(JSON.stringify(f)); d.value.text = compose(f, 'en', secs.value, feedsStart.value); touch() }, { deep: true })
watch(secs, (v) => { if (d.value.fields && t.value === 'prompt') { d.value.text = compose(fields.value, 'en', v, feedsStart.value); touch() } })
// a still has no timeline, camera move or sound: the video checks (H3's parts) do not apply to a picture's prompt
const issues = computed(() => (t.value === 'prompt' && d.value.text && !feedsPicture.value ?checkPrompt(d.value.text, 'en', secs.value, feedsStart.value) : []))

// spoken lines (as on the storyboard): who - how the prompt names them; the server weaves them into the timeline and
// the audio of every scene the prompt feeds (2 words a second fit)
const speakers = computed(() => speakersIn(d.value.text || ''))
const lineList = computed(() => (d.value.lines || []) as { who: string; text: string; how: string; audio?: string }[])
const lineWords = computed(() => lineList.value.reduce((s, l) => s + (l.text || '').trim().split(/\s+/).filter(Boolean).length, 0))
function addLine() { set('lines', [...lineList.value, { who: speakers.value[lineList.value.length % Math.max(1, speakers.value.length)] || 'The woman', text: '', how: '' }]) }
function setLine(i: number, k: string, v: string) { const ls = lineList.value.map((l) => ({ ...l })); (ls[i] as any)[k] = v; set('lines', ls) }
// a line's own sound (an uploaded or recorded file of the project): a scene with only this line is drawn under it
async function putLineSound(i: number, f: File) {
  try { const r = await upload(f, 'audio'); setLine(i, 'audio', r.file) } catch (e) { banner((e as Error).message) }
}
async function pickLineSound(i: number, ev: Event) {
  const el = ev.target as HTMLInputElement
  const f = el.files?.[0]
  el.value = ''
  if (f) await putLineSound(i, f)
}
function dropLineSound(i: number) { const ls = lineList.value.map((l) => ({ ...l })); delete ls[i].audio; set('lines', ls) }
function dropLine(i: number) { const ls = [...lineList.value]; ls.splice(i, 1); set('lines', ls) }

// a scene's length
const sceneSecs = computed(() => secondsOf(n.value))
// phase 10: the project's model and the longest scene it makes (WAN 5 s, LTX 10 s, H3 15 s)
const vm = computed(() => (S.cfg?.video_models || []).find((m) => m.id === (GE.proj?.settings.video_model || 'h3')) || null)
const maxSecs = computed(() => Math.min(SCENE_S[1], vm.value?.max_seconds || SCENE_S[1]))

// a scene's takes: the chosen one goes on; «Ещё дубль» shoots one more with another seed
const takes = computed(() => (st.value?.takes?.length ? st.value.takes : (d.value.takes || []).map((s: number) => ({ seed: s, key: '', cached: false, png: null }))) as any[])
const takeImg = (x: any) => fileUrl(x.png)
// a look drawn by every frame (clay, oil, watercolour…) holds only from a first frame drawn in it (a test 2026-11-08: the words alone gave a
// photo): choosing one on a scene without «старт» adds that «Картинка» at once
function setSceneLook(v: string | undefined) {
  set('look', v)
  if (v && lookOf(v)?.needs_frame && !inputsOf(props.id, 'start').length) drawFirstFrame(props.id, v)
}
function pickTake(i: number) { d.value.take = i; touch(100) }
function moreTake() { d.value.takes = [...(d.value.takes || []), rseed()]; d.value.take = d.value.takes.length - 1; touch(50); runTo([props.id]) }
function dropTake(i: number) {
  const ts = [...d.value.takes]; ts.splice(i, 1)
  d.value.takes = ts.length ? ts : [rseed()]
  d.value.take = Math.min(d.value.take || 0, d.value.takes.length - 1)
  touch()
}
const promptText = computed(() => (srcNode('prompt')?.data as any)?.text || '')

// LoRA from the library of the graph's model (one model shoots the whole graph); one of another model stays, unused
const graphModel = computed(() => GE.proj?.settings.video_model || 'h3')

// A prompt in the texts' language -> the English one the model gets, as in the lab: the Writer translates it in the
// form of the graph's model (H3's labelled parts, LTX/WAN's one paragraph); lines in quotes stay Russian. The source
// is the «По-русски» text, or the prompt itself when it is not English yet. Only by the button. As in the lab: ruDone is
// the Russian the English was translated from (has it changed since?), enDone that English (was it edited since?)
const promptRu = computed(() => (d.value.ru || '').trim() || (inLang(d.value.text || '', 'en') ? '' : (d.value.text || '').trim()))
const promptStale = computed(() => !!d.value.ruDone && !!promptRu.value && promptRu.value !== d.value.ruDone)
async function promptToEnglish() {
  const ru = promptRu.value
  if (!ru || trBusy.value) return
  if ((d.value.text || '').trim() && d.value.text !== d.value.enDone && !confirm(tx('nodesPanel.replacePrompt'))) return
  const r = await translateJob('/api/llm/translate', { text: ru, seconds: secs.value, video_model: graphModel.value, frame: feedsStart.value, target: feedsPicture.value ? pictureTarget(props.id) : 'video' })
  if (!r?.en) return
  d.value.ru = d.value.ruDone = ru
  d.value.text = d.value.enDone = r.en
  if (d.value.fields) fields.value = parse(r.en, 'en').fields   // the fields are the prompt: they follow the translation
  if (feedsBoth.value) {   // the picture's own text, a still's: the same source in Krea's form
    const rp = await translateJob('/api/llm/translate', { text: ru, seconds: secs.value, video_model: graphModel.value, target: pictureTarget(props.id) })
    if (rp?.en) d.value.text_picture = rp.en
  } else delete d.value.text_picture
  touch()
}
const loraRest = computed(() => lorasFor(graphModel.value).filter((l) => l.verdict !== 'blocked' && !(d.value.items || []).some((u: any) => u.id === l.id)))
// LoRA by reference (they read a clip or a voice): of any model - the scene is shot by theirs
const refRest = computed(() => v2vLoras().filter((l) => !(d.value.items || []).some((u: any) => u.id === l.id)))
const isRef = (id: string) => !!S.loras.find((l) => l.id === id)?.v2v
const foreignLora = (id: string) => !isRef(id) && !lorasFor(graphModel.value).some((l) => l.id === id) && S.loras.some((l) => l.id === id)
// a scene's LoRA by reference and its profile (app/v2v.py)
const sref = computed(() => (t.value === 'scene' ? refLoraOf(props.id) : null))
function addLora(e: Event) {
  const l = S.loras.find((x) => x.id === (e.target as HTMLSelectElement).value)
  if (l) set('items', [...(d.value.items || []), { id: l.id, name: l.name, strength: l.v2v ? 1 : 0.8 }]);
  (e.target as HTMLSelectElement).value = ''
}

// «Видео → видео»: its LoRA and that LoRA's profile (app/v2v.py)
const vl = computed(() => (t.value === 'v2v' ? S.loras.find((l) => l.id === d.value.lora) || null : null))
const V2V_GROUPS = [['ltx25', 'LTX 2.5 · IC-LoRA'], ['ltx23', 'LTX 2.3 · IC-LoRA'], ['h3', 'H3 · Ref2VA']]

// a picture's Krea LoRA (app/krea_loras.py: KREA_LORA_DIRS), read each time a picture is opened (a LoRA put in the
// folder shows without reloading the page). A graph node's own type is data.t (tOf): node.type is Vue Flow's
// component - checking it, the list was never read (the user: «узел KREA не видел LORA»)
const krea = ref<{ id: string; name: string; verdict: string; kind: string; note: string; trigger: string; strength?: number }[]>([])
watch(() => (props.id && nodeOf(props.id) && tOf(nodeOf(props.id)!) === 'picture' ? props.id : null), async (pic) => {
  if (!pic) return
  try { krea.value = (await api('/api/krea/loras')).loras } catch (e) { banner((e as Error).message) }
}, { immediate: true })
const kreaRest = computed(() => krea.value.filter((l) => l.verdict !== 'blocked' && !(d.value.loras || []).some((u: any) => u.id === l.id)))
// FLUX.2 Klein's LoRA (loras.py, ids flux2:…) share the node's `loras` list with Krea's: each model draws with its own
const fluxUsed = computed(() => ((d.value.loras || []) as any[]).filter((u) => String(u.id).startsWith('flux2:')))
const fluxRest = computed(() => lorasFor('flux2').filter((l) => l.verdict !== 'blocked' && !(d.value.loras || []).some((u: any) => u.id === l.id)))
function addFlux(e: Event) {
  const l = S.loras.find((x) => x.id === (e.target as HTMLSelectElement).value)
  if (l) set('loras', [...(d.value.loras || []), { id: l.id, name: l.name, strength: l.strength ?? 0.8 }]);
  (e.target as HTMLSelectElement).value = ''
}
const kreaOf = (id: string) => krea.value.find((l) => l.id === id)
function addKrea(e: Event) {
  const l = kreaOf((e.target as HTMLSelectElement).value)
  if (l) set('loras', [...(d.value.loras || []), { id: l.id, name: l.name, strength: l.strength ?? 0.8 }]);
  (e.target as HTMLSelectElement).value = ''
}
// a LoRA's trigger words into the picture's own prompt
const addTrigger = (w: string) => set('prompt', `${(d.value.prompt || '').trim()}${(d.value.prompt || '').trim() ? ', ' : ''}${w}`)
// the trigger of a LoRA from the common library (FLUX.2, the video models): a `<name>.json` with trainedWords beside the file
const triggerOf = (id: string) => S.loras.find((l) => l.id === id)?.trigger || ''

// a join's order
const order = computed(() => {
  const ids = inputsOf(props.id, 'clips').map((e) => e.source)
  const o = (d.value.order || []).filter((x: string) => ids.includes(x))
  return [...o, ...ids.filter((x) => !o.includes(x))]
})
function move(i: number, by: number) {
  const o = [...order.value], j = i + by
  if (j < 0 || j >= o.length) return
  ;[o[i], o[j]] = [o[j], o[i]]
  set('order', o)
}
// «Склейка» -> «Монтаж»: the same ports, so the links and the order stay; a join's default title (none, or «Склейка» /
// «Join») becomes the montage's own: the title is the type's, in the interface's language
function toMontage() { if (!n.value) return; (n.value.data as any).t = 'montage'; if (!d.value.title || d.value.title === ruTitle('join') || d.value.title === typeTitle('join')) d.value.title = typeTitle('montage'); touch(50) }
const nameOf = (id: string) => { const x = nodeOf(id); return x ? ((x.data as any).title || typeTitle(tOf(x)) || id) : id }

// files
async function pick(kind: 'image' | 'audio', key: string, ev: Event) {
  const f = (ev.target as HTMLInputElement).files?.[0]
  if (f) await put(kind, key, f)
  ;(ev.target as HTMLInputElement).value = ''
}
async function put(kind: 'image' | 'audio', key: string, f: File) {
  try { const r = await upload(f, kind); d.value[key] = r.file; if (kind === 'audio' || !d.value.title) d.value[kind === 'audio' ? 'name' : 'title'] = r.name; touch(50) }
  catch (e) { banner((e as Error).message) }
}
const out = computed(() => ({ size: '1080p', hdr: false, fps48: false, ...(d.value.output || {}) }))
const setOut = (k: string, v: unknown) => { const o = { ...out.value, [k]: v }; if (o.size === 'off') o.hdr = false; set('output', o) }
const clipSecs = computed(() => secondsOf(srcNode('clip')))
const frameAt = computed(() => (d.value.at === 'last' || d.value.at == null || d.value.at === '' ? null : Number(d.value.at)))
const writerStale = computed(() => st.value?.state === 'stale' || st.value?.state === 'empty')
const ready = computed(() => st.value?.state === 'ready')

// «Песня»: a song of the song library (POST /api/songs finds its bars on upload), copied into the project; its words
// recognised by the GPU job «Распознать слова» (or by the clip writer before it writes)
const songBusy = ref<'' | 'upload' | 'words'>('')
async function pickSong(ev: Event) {
  const f = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!f) return
  songBusy.value = 'upload'
  try {
    const fd = new FormData()
    fd.append('file', f)
    const s = await api<{ id: string }>('/api/songs', { method: 'POST', body: fd })
    const r = await post<{ file: string; name: string; duration: number; bpm: number; recognised: boolean }>(`/api/projects/${GE.id}/nodes/song`, { song: s.id })
    Object.assign(d.value, { song: s.id, file: r.file, name: r.name, duration: r.duration, bpm: r.bpm, recognised: r.recognised })
    touch(50)
  } catch (e) { banner((e as Error).message) } finally { songBusy.value = '' }
}
async function recogniseWords() {
  if (!d.value.song || songBusy.value) return
  songBusy.value = 'words'
  try {
    let job: Job = await post(`/api/songs/${d.value.song}/lyrics`)
    S.jobs = [...S.jobs, job]
    while (job.status === 'queued' || job.status === 'running') {
      await new Promise((ok) => setTimeout(ok, 1500))
      job = await api(`/api/jobs/${job.id}`)
    }
    if (job.status !== 'done') throw new Error(job.error || tx('nodesPanel.song.noWords'))
    d.value.recognised = true
    touch(50)
  } catch (e) { banner((e as Error).message) } finally { songBusy.value = '' }
}
const piece = computed(() => st.value?.piece || null)
// a scene of its own model: the models a scene may take (installed first, as the pickers list them)
const sceneModels = computed(() => (S.cfg?.video_models || []).filter((m) => !m.imported && m.id !== graphModel.value))
const shotName = (s: any) => (s.shot === 'sing' ? tx('nodesPanel.clipw.sing') : s.shot === 'insert' ? tx('nodesPanel.clipw.insert') : tx('nodesPanel.clipw.perform'))
</script>

<template>
  <div v-if="n" class="ni">
    <div class="ni-head"><span class="ni-type" :style="{ color: WHO_COLOR[spec?.who || 'none'] }"><Icon :name="ICON[t] || 'layers'" />{{ typeTitle(t) }}</span>
      <span class="muted" style="font-size:12px">{{ sref?.v2v ? tx('nodesPanel.shootsByLora', { e: ENGINE_NAME[sref.v2v.engine] }) : whoName(spec?.who || '') }}</span><HelpQ :id="t === 'pool_writer' || t === 'beat_montage' ? 'beat' : 'graph-nodes'" :term="t === 'pool_writer' ? 'Пул и роли' : t === 'beat_montage' ? 'Панель Бит-монтажа' : ruTitle(t)" /></div>
    <p v-if="help" class="ni-what">{{ sref?.v2v ? tx('nodesPanel.refScene') : t === 'prompt' && feedsPicture ? tx('nodes.what.promptPicture') : nodeWhat(t) }}<small v-if="help.ports">{{ t === 'prompt' && feedsPicture ? tx('nodes.ports.promptPicture') : help.ports }}</small></p>
    <div v-if="next" class="ni-next" :class="{ need: next.setup }"><b>{{ tx('nodesPanel.next') }}</b><span>{{ next.text }}</span></div>
    <input v-if="t !== 'note'" class="field-in" :value="d.title || ''" :placeholder="typeTitle(t)" :aria-label="tx('nodesPanel.nodeName')" @input="set('title', ($event.target as HTMLInputElement).value)">

    <!-- prompt / idea / note -->
    <template v-if="t === 'prompt'">
      <div class="seg"><button type="button" :class="{ on: !d.fields }" @click="setMode('text')">{{ tx('nodesPanel.text') }}</button><button type="button" :class="{ on: !!d.fields }" @click="setMode('fields')">{{ tx('nodesPanel.fields') }}</button></div>
      <label class="stack"><span class="lbl">{{ tx('nodesPanel.promptRu') }} <small>{{ tx('nodesPanel.promptRuSub') }}</small></span>
        <textarea class="field-in" rows="3" :value="d.ru || ''" spellcheck="false" :placeholder="tx('nodesPanel.promptRuPh')" @input="set('ru', ($event.target as HTMLTextAreaElement).value)" /></label>
      <div class="ni-row">
        <button type="button" class="btn" :disabled="!promptRu || trBusy" :title="tx('nodesPanel.promptToEnTitle', { m: vm?.short || 'H3' })" @click="promptToEnglish"><Icon name="spark" />{{ tx('nodesPanel.toEn') }}</button>
        <span v-if="tr" class="muted small" :class="{ warn: tr.state === 'error' }">{{ tr.state === 'queue' ? tx('nodesPanel.queue') : tr.state === 'wait' ? tx('nodesPanel.translating', { s: tr.secs || 0 })
          : tr.state === 'error' ? tr.text : tx('nodesPanel.doneIn', { s: tr.secs }) }}</span>
      </div>
      <p v-if="promptStale" class="muted small warn">{{ tx('nodesPanel.promptStale') }}</p>
      <SceneForm v-if="d.fields" v-model="fields" lang="en" :seconds="5" />
      <textarea v-else class="field-in mono" rows="12" :value="d.text || ''" spellcheck="false" :placeholder="feedsPicture ? tx('nodesPanel.promptPhPicture') : tx('nodesPanel.promptPh', { m: vm?.short || 'H3' })" @input="set('text', ($event.target as HTMLTextAreaElement).value)" />
      <div v-for="x in issues" :key="x.id" class="warn-line" :title="x.more"><Icon name="warn" :size="14" /><span>{{ x.text }}</span></div>
      <label v-if="feedsBoth" class="stack"><span class="lbl">{{ tx('nodesPanel.promptPicture') }} <small>{{ tx('nodesPanel.promptPictureSub') }}</small></span>
        <textarea class="field-in mono" rows="5" :value="d.text_picture || ''" spellcheck="false" :placeholder="tx('nodesPanel.promptPhPicture')" @input="set('text_picture', ($event.target as HTMLTextAreaElement).value)" /></label>
      <div class="stack lines-box" style="gap:8px">
        <div class="sec-head"><span class="lbl">{{ tx('nodesPanel.lines') }} <HelpQ id="graph-edit" term="Реплики" /> <small :class="{ warn: lineWords > 2 * secs }">{{ lineWords ? tx('nodesPanel.words', { n: lineWords, max: 2 * secs }) : tx('nodesPanel.linesSub') }}</small></span></div>
        <div v-for="(l, i) in lineList" :key="i" class="line-row">
          <div class="line-head"><input class="field-in line-who-in" :value="l.who" list="g-speakers" :placeholder="tx('nodesPanel.who')" :aria-label="tx('nodesPanel.whoSpeaks')" spellcheck="false" @change="setLine(i, 'who', ($event.target as HTMLInputElement).value)">
            <select class="line-how" :value="l.how" :aria-label="tx('nodesPanel.how')" @change="setLine(i, 'how', ($event.target as HTMLSelectElement).value)"><option v-for="[k, v] in HOW_RU" :key="k" :value="k">{{ v }}</option></select>
            <button type="button" class="ghost" :aria-label="tx('nodesPanel.dropLine')" @click="dropLine(i)"><Icon name="close" /></button></div>
          <textarea class="field-in line-text" rows="2" :value="l.text" :placeholder="tx('nodesPanel.says')" :aria-label="tx('nodesPanel.lineN', { n: i + 1 })" @change="setLine(i, 'text', ($event.target as HTMLTextAreaElement).value)" />
          <audio v-if="l.audio" :src="fileUrl(l.audio)!" controls style="width:100%;height:32px" />
          <div class="ni-row"><label class="btn" :title="tx('nodesPanel.ownSoundTitle')"><Icon name="music" />{{ tx('nodesPanel.ownSound') }}<input type="file" accept="audio/*" hidden @change="pickLineSound(i, $event)"></label>
            <VoiceRecorder @done="putLineSound(i, $event)" />
            <button v-if="l.audio" type="button" class="ghost" :aria-label="tx('nodesPanel.dropOwnSound')" :title="tx('nodesPanel.dropOwnSound')" @click="dropLineSound(i)"><Icon name="close" /></button></div>
        </div>
        <datalist id="g-speakers"><option v-for="x in [...speakers, 'The woman', 'The man'].filter((v, k, a) => a.indexOf(v) === k)" :key="x" :value="x" /></datalist>
        <div class="ni-row"><button type="button" class="btn" @click="addLine"><Icon name="plus" />{{ tx('nodesPanel.line') }}</button>
          <button type="button" class="btn" :disabled="busy || !d.text" :title="tx('nodesPanel.inventTitle')" @click="runLlm([id])"><Icon name="spark" />{{ tx('nodesPanel.invent') }}</button></div>
        <p class="muted small">{{ tx('nodesPanel.linesHint') }}</p>
        <p v-if="lineList.some((l) => l.audio)" class="muted small">{{ tx('nodesPanel.ownSoundHint') }}</p>
      </div>
    </template>
    <template v-else-if="t === 'idea'">
      <textarea class="field-in" rows="6" :value="d.text || ''" :placeholder="tx('nodesPanel.ideaPh')" @input="set('text', ($event.target as HTMLTextAreaElement).value)" />
      <div class="ni-row idea-make" style="flex-wrap:wrap">
        <span class="lbl">{{ tx('nodesPanel.ideaMake') }} <HelpQ id="graph-nodes" term="Идея" :title="tx('nodesPanel.ideaMake')" :text="tx('nodesPanel.ideaModesHelp')" /></span>
      </div>
      <div class="ni-row idea-make" style="flex-wrap:wrap">
        <select class="field-in idea-mode" :value="ideaMode" :aria-label="tx('nodesPanel.ideaMake')" @change="setIdeaMode(($event.target as HTMLSelectElement).value)">
          <option value="">{{ tx('nodesPanel.modeAuto', { m: tx(`nodesPanel.mode.${ideaAuto}`) }) }}</option>
          <option v-for="m in IDEA_MODES" :key="m" :value="m">{{ tx(`nodesPanel.mode.${m}`) }}</option>
        </select>
        <button type="button" class="btn" :disabled="!(d.text || '').trim() || trBusy" :title="tx(`nodesPanel.modeTitle.${ideaGo}`)"
          @click="ideaMake(ideaMode || 'auto')"><Icon name="spark" />{{ tx(`nodesPanel.go.${ideaGo}`) }}</button>
        <button type="button" class="btn" :disabled="!(d.text || '').trim() || trBusy" :title="tx('nodesPanel.askWriterTitle')"
          @click="ideaMake('think')"><Icon name="quill" />{{ tx('nodesPanel.askWriter') }}</button>
      </div>
      <span v-if="tr" class="muted small" :class="{ warn: tr.state === 'error' }">{{ tr.state === 'queue' ? tx('nodesPanel.queue') : tr.state === 'wait' ? tx('nodesPanel.translating', { s: tr.secs || 0 })
        : tr.state === 'error' ? tr.text : tx('nodesPanel.doneIn', { s: tr.secs }) }}</span>
      <p class="muted small">{{ tx('nodesPanel.ideaHint') }}</p>
    </template>
    <textarea v-else-if="t === 'note'" class="field-in" rows="6" :value="d.text || ''" :placeholder="tx('nodesPanel.notePh')" @input="set('text', ($event.target as HTMLTextAreaElement).value)" />

    <!-- photo / hero / track -->
    <template v-else-if="t === 'photo'">
      <img v-if="d.file" class="ni-img zoomable" :src="fileUrl(d.file)!" alt="" :title="tx('zoom.open')" @click="openZoom(fileUrl(d.file)!, d.title || typeTitle(t), graphPics())">
      <label class="btn"><Icon name="image" />{{ d.file ? tx('nodesPanel.otherPhoto') : tx('nodesPanel.loadPhoto') }}<input type="file" accept="image/*" hidden @change="pick('image', 'file', $event)"></label>
      <p class="muted small">{{ tx('nodesPanel.photoHint') }}</p>
    </template>
    <template v-else-if="t === 'hero'">
      <ActorPanel :data="d" :node-id="id" />
      <img v-if="d.photo" class="ni-img zoomable" :src="fileUrl(d.photo)!" alt="" :title="tx('zoom.open')" @click="openZoom(fileUrl(d.photo)!, d.title || typeTitle(t), graphPics())">
      <label class="btn"><Icon name="image" />{{ d.photo ? tx('nodesPanel.otherPhoto') : tx('nodesPanel.heroPhoto') }}<input type="file" accept="image/*" hidden @change="pick('image', 'photo', $event)"></label>
      <button type="button" class="btn" :disabled="!d.photo || busy" @click="runLlm([id])"><Icon name="spark" />{{ tx('nodesPanel.describe') }}</button>
      <HeroKind faceless :model-value="d.kind || 'person'" @update:model-value="setKind($event)" />
      <div v-if="d.kind === 'faceless'" class="stack"><span class="lbl">{{ tx('beat.hero.lbl') }} <BeatHelp k="heroPreset" /></span>
        <div class="chips" role="radiogroup" :aria-label="tx('beat.hero.lbl')"><button v-for="p in presetList" :key="p.id" type="button" role="radio" class="chip" :class="{ on: !d.own && d.preset === p.id }" :aria-checked="!d.own && d.preset === p.id" @click="applyHero({ preset: p.id, own: false })">{{ beatName(p) }}</button><button type="button" role="radio" class="chip" :class="{ on: !!d.own }" :aria-checked="!!d.own" @click="applyHero({ own: true })">{{ tx('beat.hero.own') }}</button></div>
        <p class="muted small">{{ tx('beat.hero.presetHint') }}</p>
        <label class="stack"><span class="lbl">{{ tx('beat.hero.descLbl') }} <BeatHelp k="heroText" /></span>
          <textarea class="field-in" rows="2" maxlength="600" :value="d.desc || ''" :placeholder="tx('beat.hero.descPh')" @input="set('desc', ($event.target as HTMLTextAreaElement).value)" /></label>
        <p class="muted small">{{ tx('beat.hero.ownHint') }}</p>
        <label v-if="d.own" style="display:flex;align-items:center;gap:8px;cursor:pointer"><input type="checkbox" :checked="d.face_hidden !== false" @change="applyHero({ face_hidden: ($event.target as HTMLInputElement).checked })">
          <span>{{ tx('beat.hero.faceHidden') }}</span> <BeatHelp k="faceHidden" /></label></div>
      <div v-if="(d.kind || 'person') === 'person'" class="ni-row"><select class="field-in" :value="d.gender || ''" :aria-label="tx('nodesPanel.gender')" @change="set('gender', ($event.target as HTMLSelectElement).value)"><option value="">{{ tx('nodesPanel.genderPh') }}</option><option v-for="g in GENDERS" :key="g[0]" :value="g[0]">{{ g[1] }}</option></select>
        <input class="field-in" type="number" min="21" max="90" :value="d.age || ''" :placeholder="tx('nodesPanel.agePh')" :aria-label="tx('nodesPanel.age')" @input="set('age', +($event.target as HTMLInputElement).value || '')"></div>
      <label class="stack"><span class="lbl">{{ tx('nodesPanel.inRu') }} <small>{{ tx('nodesPanel.inRuSub') }}</small></span><textarea class="field-in" rows="3" :value="d.ru || ''" @input="set('ru', ($event.target as HTMLTextAreaElement).value)" /></label>
      <button type="button" class="btn" :disabled="!(d.ru || '').trim() || trBusy" :title="tx('nodesPanel.toEnTitle')" @click="heroToEnglish">
        <Icon name="spark" />{{ tx('nodesPanel.toEn') }}</button>
      <span v-if="tr" class="muted small" :class="{ warn: tr.state === 'error' }">{{ tr.state === 'queue' ? tx('nodesPanel.queue') : tr.state === 'wait' ? tx('nodesPanel.translating', { s: tr.secs || 0 })
        : tr.state === 'error' ? tr.text : tx('nodesPanel.doneIn', { s: tr.secs }) }}</span>
      <label class="stack"><span class="lbl">{{ tx('nodesPanel.lookEn') }} <small>{{ tx('nodesPanel.lookEnSub') }}</small></span><textarea class="field-in" rows="4" :value="d.en || ''" @input="set('en', ($event.target as HTMLTextAreaElement).value)" /></label>
      <label class="stack"><span class="lbl">{{ tx('nodesPanel.outfitEn') }}</span><textarea class="field-in" rows="2" :value="d.outfit_en || ''" @input="set('outfit_en', ($event.target as HTMLTextAreaElement).value)" /></label>
      <p class="muted small">{{ tx('nodesPanel.heroHint') }}</p>
      <p v-if="d.kind && d.kind !== 'person'" class="muted small">{{ tx('nodesPanel.heroNoFace') }}</p>
    </template>
    <template v-else-if="t === 'track'">
      <audio v-if="d.file" :src="fileUrl(d.file)!" controls style="width:100%" />
      <div class="ni-row"><label class="btn"><Icon name="music" />{{ d.file ? tx('nodesPanel.otherTrack') : tx('nodesPanel.loadTrack') }}<input type="file" accept="audio/*" hidden @change="pick('audio', 'file', $event)"></label>
        <VoiceRecorder @done="put('audio', 'file', $event)" /></div>
      <p class="muted small">{{ tx('nodesPanel.trackHint') }}</p>
    </template>
    <template v-else-if="t === 'sound'">
      <audio v-if="ready && st?.file" :src="fileUrl(st.file)!" controls style="width:100%" />
      <label class="check-row"><input type="radio" :checked="d.voice !== false" @change="set('voice', true)">{{ tx('nodesPanel.voiceOnly') }}</label>
      <label class="check-row"><input type="radio" :checked="d.voice === false" @change="set('voice', false)">{{ tx('nodesPanel.allSound') }}</label>
      <p class="muted small">{{ tx('nodesPanel.soundHint') }}</p>
    </template>

    <!-- picture -->
    <template v-else-if="t === 'picture'">
      <img v-if="ready && st?.file" class="ni-img zoomable" :src="fileUrl(st.file)!" alt="" :title="tx('zoom.open')" @click="openZoom(fileUrl(st.file)!, d.title || typeTitle(t), graphPics())">
      <label class="stack"><span class="lbl">{{ tx('nodesPanel.pictureModel') }}</span>
        <select class="field-in" :value="d.model || 'krea2'" @change="setPictureModel(($event.target as HTMLSelectElement).value)">
          <option value="krea2">{{ tx('nodesPanel.pictureKrea') }}</option><option value="flux2">{{ tx('nodesPanel.pictureFlux') }}</option></select></label>
      <p v-if="d.model === 'flux2'" class="muted small">{{ tx('nodesPanel.fluxHint') }}</p>
      <textarea v-if="!inputsOf(id, 'text').length" class="field-in" rows="5" :value="d.prompt || ''" :placeholder="d.model === 'flux2' ? tx('nodesPanel.picturePhFlux') : tx('nodesPanel.picturePh')" @input="set('prompt', ($event.target as HTMLTextAreaElement).value)" />
      <p v-else class="muted small">{{ tx('nodesPanel.promptFrom', { name: nameOf(inputsOf(id, 'text')[0].source) }) }}</p>
      <div class="ni-row"><span class="lbl">{{ tx('nodesPanel.seed', { n: d.seed }) }}</span><button type="button" class="ghost" @click="set('seed', rseed())"><Icon name="shuffle" />{{ tx('nodesPanel.other') }}</button></div>
      <template v-if="d.model !== 'flux2'">
      <span class="lbl">{{ tx('nodesPanel.kreaLora') }} <small>{{ tx('nodesPanel.kreaLoraSub') }}</small></span>
      <div v-for="(u, i) in d.loras || []" :key="u.id" class="stack" style="gap:2px">
        <div class="ni-row"><span class="grow" :title="u.name">{{ u.name || u.id }}<small v-if="kreaOf(u.id)?.kind === 'lokr'" class="muted"> · LoKr</small></span>
          <input class="field-in" type="number" step="0.05" min="-30" max="30" style="width:84px" :value="u.strength" :aria-label="tx('nodesPanel.strength')" @input="u.strength = +($event.target as HTMLInputElement).value; touch()">
          <button type="button" class="ghost" :aria-label="tx('nodesPanel.remove')" @click="d.loras.splice(i, 1); touch()"><Icon name="close" /></button></div>
        <span v-if="kreaOf(u.id)?.trigger" class="muted small">{{ tx('nodesPanel.trigger', { w: kreaOf(u.id)!.trigger }) }}
          <button v-if="!inputsOf(id, 'text').length" type="button" class="link-btn" @click="addTrigger(kreaOf(u.id)!.trigger)">{{ tx('nodesPanel.toPromptBtn') }}</button></span>
        <span v-if="kreaOf(u.id)?.verdict === 'warn'" class="warn-line small"><Icon name="warn" :size="12" />{{ kreaOf(u.id)!.note }}</span></div>
      <select class="field-in" @change="addKrea"><option value="">{{ tx('nodesPanel.addLora') }}</option><option v-for="l in kreaRest" :key="l.id" :value="l.id">{{ l.name }}{{ l.verdict === 'warn' ? ' (?)' : '' }}</option></select>
      <p class="muted small">{{ tx('nodesPanel.kreaHint', { s: GE.picture }) }}</p>
      </template>
      <template v-else>
      <span class="lbl">{{ tx('nodesPanel.fluxLora') }} <small>{{ tx('nodesPanel.fluxLoraSub') }}</small></span>
      <div v-for="u in fluxUsed" :key="u.id" class="stack" style="gap:2px">
        <div class="ni-row"><span class="grow" :title="u.name">{{ u.name || u.id }}</span>
          <input class="field-in" type="number" step="0.05" min="-5" max="5" style="width:84px" :value="u.strength" :aria-label="tx('nodesPanel.strength')" @input="u.strength = +($event.target as HTMLInputElement).value; touch()">
          <button type="button" class="ghost" :aria-label="tx('nodesPanel.remove')" @click="set('loras', d.loras.filter((x: any) => x.id !== u.id))"><Icon name="close" /></button></div>
        <span v-if="triggerOf(u.id)" class="muted small">{{ tx('nodesPanel.trigger', { w: triggerOf(u.id) }) }}
          <button v-if="!inputsOf(id, 'text').length" type="button" class="link-btn" @click="addTrigger(triggerOf(u.id))">{{ tx('nodesPanel.toPromptBtn') }}</button></span>
        <span v-if="lorasFor('flux2').find((l) => l.id === u.id)?.verdict === 'warn'" class="warn-line small"><Icon name="warn" :size="12" />{{ lorasFor('flux2').find((l) => l.id === u.id)!.note }}</span></div>
      <select class="field-in" @change="addFlux"><option value="">{{ tx('nodesPanel.addLora') }}</option><option v-for="l in fluxRest" :key="l.id" :value="l.id">{{ l.name }}{{ l.verdict === 'warn' ? ' (?)' : '' }}</option></select>
      </template>
    </template>

    <!-- scene -->
    <template v-else-if="t === 'scene'">
      <div v-if="d.role" class="stack"><span class="lbl">{{ tx('beat.role.lbl') }} <BeatHelp k="role" /></span><RoleSelect :id="id" />
        <p class="muted small">{{ tx('beat.role.hint') }}</p></div>
      <video v-if="ready && st?.file" class="ni-img" :src="fileUrl(st.file)!" :poster="fileUrl(st.png) || undefined" controls playsinline />
      <span class="lbl">{{ tx('nodesPanel.takes') }} <small>{{ tx('nodesPanel.takesSub') }}</small></span>
      <div class="takes">
        <button v-for="(x, i) in takes" :key="x.seed" type="button" class="take" :class="{ on: i === (d.take || 0) }" :title="tx('nodesPanel.seedN', { n: x.seed })" @click="pickTake(i)">
          <img v-if="x.cached && x.png" :src="takeImg(x)!" alt="" @dblclick.stop="openZoom(takeImg(x)!, tx('nodesPanel.seedN', { n: x.seed }), takes.filter((y: any) => y.cached && y.png).map((y: any) => ({ src: takeImg(y)!, label: tx('nodesPanel.seedN', { n: y.seed }) })))"><span v-else>{{ x.cached ? tx('nodesPanel.shot') : tx('nodesPanel.notShot') }}</span><b>{{ i + 1 }}</b>
          <i v-if="takes.length > 1" role="button" :aria-label="tx('nodesPanel.dropTake')" @click.stop="dropTake(i)">×</i></button>
      </div>
      <button type="button" class="btn" :disabled="busy" @click="moreTake"><Icon name="retake" />{{ tx('nodesPanel.moreTake') }}</button>
      <label class="stack"><span class="lbl">{{ tx('looks.sceneLook') }} <HelpQ id="idea" term="Вид" /></span>
        <select class="field-in" :value="d.look || ''" :title="tx('looks.sceneLookHint')" @change="setSceneLook(($event.target as HTMLSelectElement).value || undefined)">
          <option value="">{{ tx('looks.asProject') }}</option>
          <optgroup v-for="g in L.groups.filter((x) => x.id !== 'mine')" :key="g.id" :label="g.name">
            <option v-for="x in L.looks.filter((y) => y.group === g.id)" :key="x.id" :value="x.id">{{ x.name }}</option></optgroup>
        </select></label>
      <div v-if="st?.frame_look" class="warn-line">
        <Icon name="warn" :size="14" /><span>{{ tx('looks.needFrame', { name: lookName(st.frame_look) }) }}</span></div>
      <button v-if="st?.frame_look" type="button" class="btn" @click="drawFirstFrame(id, st.frame_look)">{{ tx('looks.drawFrame') }}</button>
      <label class="stack"><span class="lbl">{{ tx('nodesPanel.sceneModel') }}</span>
        <select class="field-in" :value="d.model || ''" :title="tx('nodesPanel.sceneModelHint')" @change="set('model', ($event.target as HTMLSelectElement).value || undefined)">
          <option value="">{{ tx('nodesPanel.sceneModelGraph', { m: vm?.name || graphModel }) }}</option>
          <option v-for="m in sceneModels" :key="m.id" :value="m.id" :disabled="!!m.missing?.length && m.id !== d.model">{{ m.name }}</option>
        </select></label>
      <template v-if="inputsOf(id, 'sound').length">
        <label class="stack"><span class="lbl">{{ tx('nodesPanel.soundFrom') }}</span>
          <input class="field-in" type="number" min="0" step="0.1" :value="d.sound_from || ''" placeholder="0" :title="tx('nodesPanel.soundFromTitle')" @input="set('sound_from', +($event.target as HTMLInputElement).value || undefined)"></label>
        <p class="muted small">{{ tx('nodesPanel.sceneSoundHint') }}</p>
      </template>
      <p v-if="d.cut" class="muted small">{{ tx('nodesPanel.bars') }}: {{ tx('nodesPanel.barsVal', { a: dec(Number(d.cut.start).toFixed(2)), b: dec(Number(d.cut.end).toFixed(2)), s: dec(Number(d.seconds).toFixed(2)) }) }}{{ inputsOf(id, 'voice').length ? ' · ' + (d.cut.voice === false ? tx('nodesPanel.barsNoVoice') : tx('nodesPanel.barsVoice')) : '' }}</p>
      <p v-if="ready && st?.lips" class="muted small" :class="{ warn: st.lips.mute }" :title="tx('nodesPanel.lipsTitle')">{{ st.lips.mute ? tx('nodesPanel.lipsMute') : tx('nodesPanel.lipsIn', { v: st.lips.voiced ?? '–', s: st.lips.silent ?? '–' }) }}</p>
      <div v-if="ready && st?.checks?.length" class="warn-line" :title="tx('nodesPanel.checksTitle')">
        <Icon name="warn" :size="14" /><span>{{ tx('nodesPanel.inClip', { list: st.checks.map((x) => tx('nodesPanel.checkAt', { name: x.name, at: dec(x.at.toFixed(1)) })).join('; ') }) }}</span></div>
      <template v-if="ready && st?.alpha">
        <div class="ni-row">
          <a class="btn" :href="fileUrl(st.alpha.replace(/\.webm$/, '.mov'))!" :download="tx('nodesPanel.noBgMov', { name: d.title || tx('nodesPanel.scene') })" :title="tx('nodesPanel.movTitle')"><Icon name="download" />{{ tx('nodesPanel.forEdit') }}</a>
          <a class="btn" :href="fileUrl(st.alpha)!" :download="tx('nodesPanel.noBgWebm', { name: d.title || tx('nodesPanel.scene') })" :title="tx('nodesPanel.webmTitle')"><Icon name="download" />{{ tx('nodesPanel.forWeb') }}</a></div>
        <p class="muted small">{{ tx('nodesPanel.sceneAlphaHint') }}</p>
      </template>
      <!-- a LoRA by reference: what it reads, who shoots (app/v2v.py profiles) -->
      <div v-if="sref?.v2v" class="ref-box stack">
        <span class="lbl">{{ tx('nodesPanel.byRef') }} <small>{{ sref.name }}</small></span>
        <p v-if="sref.v2v.note" class="ni-what">{{ sref.v2v.note }}</p>
        <dl class="gs-dl">
          <dt>{{ tx('nodesPanel.shoots') }}</dt><dd>{{ ENGINE_NAME[sref.v2v.engine] }}{{ sref.v2v.engine !== graphModel ? tx('nodesPanel.loraNeeds', { m: vm?.name || 'H3' }) : '' }}</dd>
          <dt>{{ tx('nodesPanel.reads') }}</dt><dd>{{ sref.v2v.reads === 'voice' ? tx('nodesPanel.readsVoice') : tx('nodesPanel.readsClip') + (sref.v2v.engine === 'h3' ? tx('nodesPanel.readsFaces') : '') }}</dd>
          <dt>{{ tx('nodesPanel.result') }}</dt><dd>{{ sref.v2v.reads === 'voice' ? tx('nodesPanel.resVoice') : sref.v2v.out === 'matte' ? tx('nodesPanel.resMatte') : sref.v2v.scale > 1 ? tx('nodesPanel.resScale', { n: sref.v2v.scale }) : tx('nodesPanel.resClip') }}</dd>
        </dl>
        <div v-if="!sref.v2v.known" class="warn-line"><Icon name="warn" :size="14" /><span>{{ tx('nodesPanel.noProfile') }}<code>{{ sref.name }}.v2v.json</code>{{ tx('nodesPanel.noProfile2') }}</span></div>
        <div v-if="sref.v2v.reads === 'voice'" class="ni-row">
          <label class="stack grow"><span class="lbl">{{ tx('nodesPanel.voiceFrom') }}</span>
            <input class="field-in" type="number" step="0.5" min="0" :value="d.voice_from ?? 0" @input="set('voice_from', +($event.target as HTMLInputElement).value)"></label>
          <label class="stack grow"><span class="lbl">{{ tx('nodesPanel.sample') }} <small>{{ tx('nodesPanel.sampleSub') }}</small></span>
            <input class="field-in" type="number" step="0.5" min="1" max="20" :value="d.voice_secs ?? sref.v2v.voice_secs ?? 5" @input="set('voice_secs', +($event.target as HTMLInputElement).value)"></label></div>
        <label v-else-if="sref.v2v.engine !== 'h3'" class="stack"><span class="lbl">{{ tx('nodesPanel.clipStrength') }} <small>{{ tx('nodesPanel.clipStrengthSub') }}</small></span>
          <input class="field-in" type="number" step="0.05" min="0" max="2" :value="d.guide ?? 1" @input="set('guide', +($event.target as HTMLInputElement).value)"></label>
        <div v-if="ready && st?.voice" class="ni-row" :class="{ 'warn-line': st!.voice!.verdict === 'unlike' }"
          :title="tx('nodesPanel.voiceTitle')">
          <Icon :name="st!.voice!.verdict === 'alike' ? 'check' : 'warn'" :size="14" />
          <span>{{ tx(`nodesPanel.voice.${st!.voice!.verdict || 'none'}`) }}{{ st!.voice!.sim != null ? ` · ${dec(st!.voice!.sim)}` : '' }}</span></div>
        <p v-if="sref.v2v.reads === 'voice'" class="muted small">{{ tx('nodesPanel.idloraHint') }}</p>
      </div>
      <p v-if="sref?.v2v?.reads === 'clip'" class="muted small">{{ tx('nodesPanel.lengthAsClip') }}</p>
      <div v-else class="stack"><span class="lbl">{{ tx('nodesPanel.length') }} <small>{{ tx('nodesPanel.secs', { s: sceneSecs }) }} · {{ !vm || vm.id === 'h3' ? tx('nodesPanel.h3Trained') : tx('nodesPanel.modelUpTo', { m: vm.name, s: vm.max_seconds }) }}</small></span>
        <div class="seg"><button v-for="v in [3, 5, 8, 10, 15].filter((x) => x <= maxSecs)" :key="v" type="button" :class="{ on: sceneSecs === v }" @click="set('seconds', v)">{{ tx('nodesPanel.secs', { s: v }) }}</button></div>
        <input type="range" :min="SCENE_S[0]" :max="maxSecs" step="1" :value="Math.min(sceneSecs, maxSecs)" :aria-label="tx('nodesPanel.sceneLength')" @change="set('seconds', +($event.target as HTMLInputElement).value)">
        <div v-if="sceneSecs > maxSecs" class="warn-line"><Icon name="warn" :size="14" /><span>{{ tx('nodesPanel.onlyShoots', { m: vm?.name, a: maxSecs, b: sceneSecs }) }}</span></div></div>
      <div v-if="st?.warn" class="warn-line"><Icon name="warn" :size="14" /><span>{{ st.warn }}</span></div>
      <dl class="gs-dl">
        <dt>{{ tx('nodesPanel.start') }}</dt><dd>{{ srcNode('start') ? nameOf(srcNode('start')!.id) + (st?.start_of ? tx('nodesPanel.lastFrame') : '') : tx('nodesPanel.fromText') }}</dd>
        <dt>{{ tx('nodesPanel.faces') }}</dt><dd>{{ !inputsOf(id, 'faces').length ? tx('nodesPanel.none') : vm && !vm.refs ? tx('nodesPanel.facesNoRefs', { n: inputsOf(id, 'faces').length, m: vm.name })
          : tx('nodesPanel.facesRef', { n: inputsOf(id, 'faces').length }) }}</dd>
        <dt>{{ tx('nodesPanel.key') }}</dt><dd><code>{{ st?.key || tx('nodesPanel.keyLater') }}</code></dd>
      </dl>
      <details v-if="st?.text || promptText" class="gs-prompt"><summary>{{ st?.text ? (sref?.v2v?.reads === 'voice' ? tx('nodesPanel.promptIdLora') : tx('nodesPanel.promptLines')) : tx('nodesPanel.prompt') }}</summary><pre>{{ st?.text || promptText }}</pre></details>
    </template>

    <!-- video to video -->
    <template v-else-if="t === 'v2v'">
      <video v-if="ready && st?.alpha" class="ni-img ni-alpha" :src="fileUrl(st.alpha)!" controls loop playsinline />
      <video v-else-if="ready && st?.file" class="ni-img" :src="fileUrl(st.file)!" :poster="fileUrl(st.png) || undefined" controls playsinline />
      <template v-if="ready && st?.alpha">
        <div class="ni-row">
          <a class="btn" :href="fileUrl(st.alpha.replace(/\.webm$/, '.mov'))!" :download="tx('nodesPanel.noBgMov', { name: d.title || tx('nodesPanel.clip') })" :title="tx('nodesPanel.movTitle2')"><Icon name="download" />{{ tx('nodesPanel.forEdit') }}</a>
          <a class="btn" :href="fileUrl(st.alpha)!" :download="tx('nodesPanel.noBgWebm', { name: d.title || tx('nodesPanel.clip') })" :title="tx('nodesPanel.webmTitle')"><Icon name="download" />{{ tx('nodesPanel.forWeb') }}</a>
          <a class="btn" :href="fileUrl(st.file)!" :download="tx('nodesPanel.matteMp4', { name: d.title || tx('nodesPanel.clip') })"><Icon name="download" />{{ tx('nodesPanel.matte') }}</a></div>
        <p class="muted small">{{ tx('nodesPanel.v2vAlphaHint') }}</p>
      </template>
      <a v-else-if="ready && st?.file" class="btn" :href="fileUrl(st.file)!" :download="`${d.title || tx('nodesPanel.clip')}.mp4`"><Icon name="download" />{{ tx('nodesPanel.downloadMp4') }}</a>
      <label class="stack"><span class="lbl">LoRA <small>{{ tx('nodesPanel.v2vLoraSub') }}</small></span>
        <select class="field-in" :value="d.lora || ''" @change="set('lora', ($event.target as HTMLSelectElement).value || null)">
          <option value="">{{ tx('nodesPanel.choose') }}</option>
          <optgroup v-for="[eng, label] in V2V_GROUPS" :key="eng" :label="eng === 'h3' && !h3Ready() ? `${label} · ${tx('nodesPanel.needH3')}` : label">
            <option v-for="l in v2vLoras().filter((x) => x.model === eng && x.v2v?.reads !== 'voice')" :key="l.id" :value="l.id" :disabled="eng === 'h3' && !h3Ready() && l.id !== d.lora">{{ l.folder && l.name.startsWith('lora_weights') ? `${l.folder} · ${l.name}` : l.name }}</option></optgroup>
        </select></label>
      <p v-if="!v2vLoras().length" class="muted small">{{ tx('nodesPanel.noV2v') }}</p>
      <template v-if="vl?.v2v">
        <p v-if="vl.v2v.note" class="ni-what">{{ vl.v2v.note }}</p>
        <dl class="gs-dl">
          <dt>{{ tx('nodesPanel.engine') }}</dt><dd>{{ vl.v2v.engine === 'h3' ? tx('nodesPanel.engH3') : tx('nodesPanel.engLtx', { e: vl.v2v.engine === 'ltx23' ? 'LTX 2.3' : 'LTX 2.5', down: vl.v2v.ref_down > 1 ? tx('nodesPanel.down', { n: vl.v2v.ref_down }) : '', stages: vl.v2v.stages === 2 ? tx('nodesPanel.twoStages') : tx('nodesPanel.oneStage') }) }}</dd>
          <dt>{{ tx('nodesPanel.result') }}</dt><dd>{{ vl.v2v.out === 'matte' ? tx('nodesPanel.v2vMatte') : vl.v2v.scale > 1 ? tx('nodesPanel.v2vScale', { n: vl.v2v.scale }) : tx('nodesPanel.v2vClip') }}{{ tx('nodesPanel.soundOf', { what: vl.v2v.sound === 'model' ? tx('nodesPanel.soundModel') : tx('nodesPanel.soundClip') }) }}</dd>
          <dt>{{ tx('nodesPanel.length') }}</dt><dd>{{ tx('nodesPanel.upTo', { n: vl.v2v.max_frames }) }}{{ vl.v2v.engine !== 'h3' ? tx('nodesPanel.inPieces') : '' }}</dd>
        </dl>
        <div v-if="!vl.v2v.known" class="warn-line"><Icon name="warn" :size="14" /><span>{{ tx('nodesPanel.noProfile') }}<code>{{ vl.name }}.v2v.json</code>{{ tx('nodesPanel.noProfile2') }}</span></div>
        <template v-if="vl.v2v.prompt !== 'none'">
          <textarea v-if="!inputsOf(id, 'prompt').length" class="field-in" rows="4" :value="d.prompt || ''" :placeholder="vl.v2v.template || tx('nodesPanel.v2vPh')"
            @input="set('prompt', ($event.target as HTMLTextAreaElement).value)" />
          <p v-else class="muted small">{{ tx('nodesPanel.promptFrom', { name: nameOf(inputsOf(id, 'prompt')[0].source) }) }}</p>
          <p class="muted small">{{ vl.v2v.prompt === 'required' ? tx('nodesPanel.promptNeeded') : tx('nodesPanel.promptOptional') }}{{ vl.v2v.engine === 'h3' ? tx('nodesPanel.promptH3') : '' }}</p>
        </template>
        <p v-else class="muted small">{{ tx('nodesPanel.noPrompt') }}</p>
        <div class="ni-row"><label class="stack grow"><span class="lbl">{{ tx('nodesPanel.loraStrength') }}</span>
          <input class="field-in" type="number" step="0.05" min="0" max="2" :value="d.strength ?? 1" @input="set('strength', +($event.target as HTMLInputElement).value)"></label>
          <label v-if="vl.v2v.engine !== 'h3'" class="stack grow"><span class="lbl">{{ tx('nodesPanel.clipStrength') }}</span>
            <input class="field-in" type="number" step="0.05" min="0" max="2" :value="d.guide ?? 1" @input="set('guide', +($event.target as HTMLInputElement).value)"></label></div>
      </template>
      <div class="ni-row"><span class="lbl">{{ tx('nodesPanel.seed', { n: d.seed }) }}</span><button type="button" class="ghost" @click="set('seed', rseed())"><Icon name="shuffle" />{{ tx('nodesPanel.other') }}</button></div>
      <div v-if="st?.warn" class="warn-line"><Icon name="warn" :size="14" /><span>{{ st.warn }}</span></div>
    </template>

    <!-- faces: the clip's far faces made sharp (app/facefix.py) -->
    <template v-else-if="t === 'facefix'">
      <video v-if="ready && st?.file" class="ni-img" :src="fileUrl(st.file)!" :poster="fileUrl(st.png) || undefined" controls playsinline />
      <a v-if="ready && st?.file" class="btn" :href="fileUrl(st.file)!" :download="`${d.title || tx('nodesPanel.clip')}.mp4`"><Icon name="download" />{{ tx('nodesPanel.downloadMp4') }}</a>
      <p v-if="ready && st?.note" class="muted small">{{ st.note.faces ? tx('nodesPanel.ffNote', st.note) : tx('nodesPanel.ffNone') }}<template v-if="st.note.seconds?.ltx"><br>{{ tx('nodesPanel.ffSecs', st.note.seconds) }}</template></p>
      <label class="stack"><span class="lbl">{{ tx('nodesPanel.ffMode') }} <small>{{ tx('nodesPanel.ffModeSub') }}</small></span>
        <select class="field-in" :value="d.mode || 'far'" @change="set('mode', ($event.target as HTMLSelectElement).value)">
          <option v-for="m in ['very_far', 'far', 'medium', 'all']" :key="m" :value="m">{{ tx(`nodesPanel.ffModes.${m}`) }}</option></select></label>
      <label class="stack"><span class="lbl">{{ tx('nodesPanel.ffWho') }} <small>{{ tx('nodesPanel.ffWhoSub') }}</small></span>
        <textarea v-if="!inputsOf(id, 'prompt').length" class="field-in" rows="3" :value="d.prompt || ''" :placeholder="tx('nodesPanel.ffWhoPh')"
          @input="set('prompt', ($event.target as HTMLTextAreaElement).value)" />
        <p v-else class="muted small">{{ tx('nodesPanel.promptFrom', { name: nameOf(inputsOf(id, 'prompt')[0].source) }) }}</p></label>
      <label class="stack"><span class="lbl">{{ tx('nodesPanel.ffStrength') }} <small>{{ tx('nodesPanel.ffStrengthSub') }}</small></span>
        <input class="field-in" type="number" step="0.05" min="0" max="1" :value="d.strength ?? 1" @input="set('strength', +($event.target as HTMLInputElement).value)"></label>
      <div class="ni-row"><span class="lbl">{{ tx('nodesPanel.seed', { n: d.seed }) }}</span><button type="button" class="ghost" @click="set('seed', rseed())"><Icon name="shuffle" />{{ tx('nodesPanel.other') }}</button></div>
      <p class="muted small">{{ tx('nodesPanel.ffHow') }}</p>
    </template>

    <!-- frame -->
    <template v-else-if="t === 'frame'">
      <img v-if="ready && st?.file" class="ni-img zoomable" :src="fileUrl(st.file)!" alt="" :title="tx('zoom.open')" @click="openZoom(fileUrl(st.file)!, d.title || typeTitle(t), graphPics())">
      <label class="check-row"><input type="radio" :checked="frameAt === null" @change="set('at', 'last')">{{ tx('nodesPanel.lastSceneFrame') }}</label>
      <label class="check-row"><input type="radio" :checked="frameAt !== null" @change="set('at', 2.5)">{{ tx('nodesPanel.frameMoment') }}</label>
      <div v-if="frameAt !== null" class="ni-row"><input type="range" min="0" :max="clipSecs - 0.1" step="0.1" :value="frameAt" @input="set('at', +($event.target as HTMLInputElement).value)"><b>{{ tx('nodesPanel.secs', { s: dec(frameAt) }) }}</b></div>
      <p class="muted small">{{ tx('nodesPanel.frameHint') }}</p>
    </template>

    <!-- lora -->
    <template v-else-if="t === 'lora'">
      <div v-for="(u, i) in d.items || []" :key="u.id" class="stack" style="gap:2px">
        <div class="ni-row"><span class="grow" :class="{ muted: foreignLora(u.id) }"
            :title="foreignLora(u.id) ? tx('nodesPanel.foreignLora', { m: vm?.name || tx('nodesPanel.graphModel') }) : u.name">{{ u.name || u.id }}<small v-if="isRef(u.id)" class="muted">{{ tx('nodesPanel.byRefMark') }}</small></span>
          <input class="field-in" type="number" step="0.05" min="-2" max="2" style="width:84px" :value="u.strength" :aria-label="tx('nodesPanel.strength')" @input="u.strength = +($event.target as HTMLInputElement).value; touch()">
          <button type="button" class="ghost" :aria-label="tx('nodesPanel.remove')" @click="d.items.splice(i, 1); touch()"><Icon name="close" /></button></div>
        <!-- the trigger words of a video LoRA: shown here, written into the scene's text by hand (the LoRA node has no prompt of its own) -->
        <span v-if="triggerOf(u.id)" class="muted small" :title="tx('nodesPanel.triggerWhere')">{{ tx('nodesPanel.trigger', { w: triggerOf(u.id) }) }}</span></div>
      <select class="field-in" @change="addLora"><option value="">{{ tx('nodesPanel.addLora') }}</option>
        <optgroup :label="tx('nodesPanel.regular', { m: vm?.name || 'H3' })"><option v-for="l in loraRest" :key="l.id" :value="l.id">{{ l.name }}</option></optgroup>
        <optgroup :label="tx('nodesPanel.refGroup')"><option v-for="l in refRest" :key="l.id" :value="l.id">{{ l.v2v?.reads === 'voice' ? tx('nodesPanel.voiceKind') : tx('nodesPanel.clipKind') }} · {{ ENGINE_NAME[l.model] }} · {{ l.folder && l.name.startsWith('lora_weights') ? `${l.folder} · ${l.name}` : l.name }}</option></optgroup></select>
      <p class="muted small">{{ tx('nodesPanel.loraHint', { m: vm?.name || 'H3' }) }}</p>
    </template>

    <!-- join -->
    <template v-else-if="t === 'join'">
      <video v-if="ready && st?.file" class="ni-img" :src="fileUrl(st.file)!" controls playsinline />
      <span class="lbl">{{ tx('nodesPanel.order') }}</span>
      <ol class="order"><li v-for="(x, i) in order" :key="x"><span class="grow">{{ i + 1 }}. {{ nameOf(x) }}</span>
        <button type="button" class="ghost" :aria-label="tx('nodesPanel.up')" :disabled="i === 0" @click="move(i, -1)">↑</button>
        <button type="button" class="ghost" :aria-label="tx('nodesPanel.down2')" :disabled="i === order.length - 1" @click="move(i, 1)">↓</button></li></ol>
      <p class="muted small">{{ tx('nodesPanel.joinHint') }}</p>
      <button type="button" class="btn" :title="tx('nodesPanel.toMontageTitle')" @click="toMontage"><Icon name="cut" />{{ tx('nodesPanel.toMontage') }}</button>
    </template>

    <!-- montage -->
    <template v-else-if="t === 'montage'">
      <video v-if="ready && st?.file" class="ni-img" :src="fileUrl(st.file)!" controls playsinline />
      <router-link class="primary" :to="`/g/${GE.id}/edit/${id}`"><Icon name="cut" :size="18" />{{ tx('nodesPanel.openMontage') }}</router-link>
      <label class="check-row" :title="tx('nodesPanel.beatsTitle')"><input type="checkbox" :checked="!!d.beats" @change="set('beats', ($event.target as HTMLInputElement).checked || undefined)">{{ tx('nodesPanel.beats') }}</label>
      <p v-if="d.beats" class="muted small">{{ tx('nodesPanel.beatsHint') }}</p>
      <label class="check-row" :title="tx('nodesPanel.faceCheckTitle')"><input type="checkbox" :checked="!!d.faces" @change="set('faces', ($event.target as HTMLInputElement).checked || undefined)">{{ tx('nodesPanel.faceCheck') }}</label>
      <p v-if="d.faces" class="muted small">{{ inputsOf(id, 'face').length ? tx('nodesPanel.faceCheckHint') : tx('nodesPanel.faceCheckNoInput') }}</p>
      <p class="muted small">{{ tx('nodesPanel.montageHint') }}</p>
      <dl class="gs-dl"><dt>{{ tx('nodesPanel.scenesCount') }}</dt><dd>{{ inputsOf(id, 'clips').length }}</dd><dt>{{ tx('nodesPanel.montage') }}</dt><dd>{{ d.edit ? tx('nodesPanel.own') : tx('nodesPanel.asInput') }}</dd>
        <dt>{{ tx('nodesPanel.length') }}</dt><dd>{{ st?.seconds ? mmss(st.seconds) : '—' }}</dd></dl>
    </template>

    <!-- the beat montage: preset, sliders by group, palette, texts, captions, preview (BeatPanel.vue) -->
    <BeatPanel v-else-if="t === 'beat_montage'" :id="id" />

    <!-- the pool writer: the beat clip's shots (PoolPanel.vue) -->
    <PoolPanel v-else-if="t === 'pool_writer'" :id="id" />

    <!-- music -->
    <template v-else-if="t === 'music'">
      <label v-for="[k, max, step] in ([['volume', 1.5, 0.05], ['scene_volume', 1, 0.05], ['offset', 120, 0.5], ['fade_in', 5, 0.5], ['fade_out', 10, 0.5]] as [string, number, number][])" :key="k" class="stack">
        <span class="lbl">{{ tx(`nodesPanel.mus.${k}`) }} <small>{{ k.includes('volume') ? Math.round((d[k] ?? 0) * 100) + '%' : (d[k] ?? 0) }}</small></span>
        <input type="range" min="0" :max="max" :step="step" :value="d[k] ?? 0" @input="set(k, +($event.target as HTMLInputElement).value)"></label>
    </template>

    <!-- output -->
    <template v-else-if="t === 'output'">
      <video v-if="ready && st?.file" class="ni-img" :src="fileUrl(st.file)!" controls playsinline />
      <a v-if="ready && st?.file" class="btn" :href="fileUrl(st.file)!" :download="`${d.title || GE.proj?.name || 'h3'}.mp4`"><Icon name="download" />{{ tx('nodesPanel.downloadMp4') }}</a>
      <div class="seg"><button v-for="[v, l] in [['off', tx('nodesPanel.asShot')], ['1080p', '1080p'], ['4k', '4K']]" :key="v" type="button" :class="{ on: out.size === v }" @click="setOut('size', v)">{{ l }}</button></div>
      <label class="check-row"><input type="checkbox" :checked="out.hdr" :disabled="out.size === 'off'" @change="setOut('hdr', ($event.target as HTMLInputElement).checked)">HDR10</label>
      <label class="check-row"><input type="checkbox" :checked="out.fps48" @change="setOut('fps48', ($event.target as HTMLInputElement).checked)">{{ tx('nodesPanel.fps48') }}</label>
      <span v-if="st?.seconds" class="muted small">{{ mmss(st.seconds) }}</span>
      <PublishPanel v-if="GE.nodes.some((x) => tOf(x) === 'beat_montage')" :id="id" />
    </template>

    <!-- writer -->
    <template v-else-if="t === 'writer'">
      <div class="ni-row"><label class="stack grow"><span class="lbl">{{ tx('nodesPanel.length') }}</span><select class="field-in" :value="d.seconds || 15" @change="set('seconds', +($event.target as HTMLSelectElement).value)">
        <option v-for="s in LENGTHS" :key="s" :value="s">{{ s < 60 ? tx('nodesPanel.secs', { s }) : tx('nodesPanel.sMin', { n: s / 60 }) }}</option></select></label>
        <label class="stack grow"><span class="lbl">{{ tx('nodesPanel.people') }}</span><select class="field-in" :value="d.mode || 'auto'" @change="set('mode', ($event.target as HTMLSelectElement).value)">
          <option value="auto">{{ tx('nodesPanel.byHeroes') }}</option><option value="one">{{ tx('nodesPanel.oneHero') }}</option><option value="several">{{ tx('nodesPanel.several') }}</option><option value="none">{{ tx('nodesPanel.noPeople') }}</option></select></label></div>
      <template v-if="!styled">
        <label class="stack"><span class="lbl">{{ tx('nodesPanel.mood') }}</span><input class="field-in" list="g-moods" :value="d.mood || ''" @input="set('mood', ($event.target as HTMLInputElement).value)"></label>
        <datalist id="g-moods"><option v-for="m in S.moods" :key="m" :value="m" /></datalist></template>
      <p v-else class="muted small">{{ tx('looks.writerNote') }}</p>
      <label class="stack"><span class="lbl">{{ tx('nodesPanel.musicSound') }}</span><input class="field-in" :value="d.music || ''" :placeholder="tx('nodesPanel.musicPh')" @input="set('music', ($event.target as HTMLInputElement).value)"></label>
      <label class="check-row"><input type="checkbox" :checked="!!d.ref_photo" :disabled="!h3Ready()" @change="set('ref_photo', ($event.target as HTMLInputElement).checked)">{{ tx('nodesPanel.keepFace', { rest: !h3Ready() ? '; ' + tx('nodesPanel.needH3') : vm && !vm.refs ? tx('nodesPanel.onlyH3', { m: vm.name }) : '' }) }}</label>
      <label v-if="(d.mode || 'auto') !== 'none'" class="check-row"><input type="checkbox" :checked="!!d.lines" @change="set('lines', ($event.target as HTMLInputElement).checked || undefined)">{{ tx('nodesPanel.writerLines') }}</label>
      <button type="button" class="primary" :disabled="busy" @click="runLlm([id])"><Icon name="spark" :size="18" />{{ d.plan ? (writerStale ? tx('nodesPanel.rewrite') : tx('nodesPanel.writeAgain')) : tx('nodesPanel.write') }}</button>
      <button type="button" class="btn" :disabled="!d.plan" @click="expand(id)"><Icon name="layers" />{{ tx('nodesPanel.expand') }}</button>
      <div v-if="d.plan" class="plan-list"><span class="lbl">{{ d.plan.title_ru }}</span>
        <p v-for="s in d.plan.scenes" :key="s.index"><b>{{ s.index + 1 }}</b> {{ s.ru }}</p></div>
      <p class="muted small">{{ tx('nodesPanel.writerHint') }}</p>
    </template>

    <!-- series: the bible of a mini-series -->
    <template v-else-if="t === 'series'">
      <label class="stack"><span class="lbl">{{ tx('screenplay.series.title') }}</span><input class="field-in" :value="d.title || ''" :placeholder="tx('screenplay.series.titlePh')" @input="set('title', ($event.target as HTMLInputElement).value)"></label>
      <label class="stack"><span class="lbl">{{ tx('screenplay.series.look') }}</span>
        <select class="field-in" :value="d.look || ''" @change="set('look', ($event.target as HTMLSelectElement).value || undefined)">
          <option value="">{{ tx('screenplay.series.lookNone') }}</option>
          <option v-for="x in L.looks.filter((l) => l.id !== 'auto')" :key="x.id" :value="x.id">{{ x.name }}</option></select></label>
      <label class="stack"><span class="lbl">{{ tx('screenplay.series.style') }}</span><input class="field-in" :value="d.style || ''" :placeholder="tx('screenplay.series.stylePh')" @input="set('style', ($event.target as HTMLInputElement).value)"></label>
      <label class="stack"><span class="lbl">{{ tx('screenplay.series.world') }}</span><textarea class="field-in" rows="2" :value="d.world || ''" :placeholder="tx('screenplay.series.worldPh')" @input="set('world', ($event.target as HTMLTextAreaElement).value)" /></label>
      <label class="stack"><span class="lbl">{{ tx('screenplay.series.characters') }}</span><textarea class="field-in" rows="3" :value="d.characters || ''" :placeholder="tx('screenplay.series.charactersPh')" @input="set('characters', ($event.target as HTMLTextAreaElement).value)" /></label>
      <label class="stack"><span class="lbl">{{ tx('screenplay.series.recap') }}</span><textarea class="field-in" rows="4" :value="d.recap || ''" :placeholder="tx('screenplay.series.recapPh')" @input="set('recap', ($event.target as HTMLTextAreaElement).value)" /></label>
      <p class="muted small">{{ tx('screenplay.series.hint') }}</p>
    </template>

    <!-- screenplay: «ИМЯ (как): реплика» -> a shot per line -->
    <template v-else-if="t === 'screenplay'">
      <label class="stack"><span class="lbl">{{ tx('screenplay.play.seconds') }}</span><select class="field-in" :value="d.seconds || 30" @change="set('seconds', +($event.target as HTMLSelectElement).value)">
        <option v-for="s in [15, 30, 45, 60, 90]" :key="s" :value="s">{{ s }}</option></select></label>
      <label class="stack"><span class="lbl">{{ tx('screenplay.play.text') }}</span>
        <textarea class="field-in" rows="12" :value="d.text || ''" :placeholder="tx('screenplay.play.textPh')" @input="set('text', ($event.target as HTMLTextAreaElement).value)" /></label>
      <p v-if="d.text" class="muted small">{{ tx('screenplay.play.lines', { l: screenplayStats(d.text).lines, a: screenplayStats(d.text).actions, n: screenplayStats(d.text).shots }) }}</p>
      <button type="button" class="primary" :disabled="busy || !inputsOf(id, 'idea').length" @click="runLlm([id])"><Icon name="spark" :size="18" />{{ d.text ? tx('screenplay.play.writeAgain') : tx('screenplay.play.write') }}</button>
      <button type="button" class="btn" :disabled="!(d.text || '').trim()" @click="expand(id)"><Icon name="layers" />{{ tx('screenplay.play.expand') }}</button>
      <button type="button" class="btn" :disabled="!(d.text || '').trim()" @click="downloadSrt"><Icon name="download" />{{ tx('screenplay.play.srt') }}</button>
      <button type="button" class="btn" :disabled="busy || !(d.text || '').trim() || !inputsOf(id, 'series').length" @click="runLlm([id], 'recap')"><Icon name="plus" />{{ tx('screenplay.play.recap') }}</button>
      <p class="muted small">{{ tx('screenplay.play.hintIntro') }}</p>
      <ul class="muted small"><li>{{ tx('screenplay.play.hScene') }}</li><li>{{ tx('screenplay.play.hLine') }}</li><li>{{ tx('screenplay.play.hAction') }}</li><li>{{ tx('screenplay.play.hHow') }}</li></ul>
      <p class="muted small">{{ tx('screenplay.play.expandHint') }}</p>
    </template>

    <!-- song: the song's piece, bars and words («Песня → клип» in parts) -->
    <template v-else-if="t === 'song'">
      <audio v-if="d.file" :src="fileUrl(d.file)!" controls style="width:100%" />
      <label class="btn" :class="{ disabled: !!songBusy }"><Icon name="music" />{{ songBusy === 'upload' ? tx('nodesPanel.song.uploading') : d.file ? tx('nodesPanel.song.other') : tx('nodesPanel.song.load') }}
        <input type="file" accept="audio/*" hidden :disabled="!!songBusy" @change="pickSong"></label>
      <p v-if="d.file" class="muted small">{{ tx('nodesPanel.song.info', { bpm: dec(d.bpm ?? '—'), d: mmss(d.duration || 0), w: d.recognised ? tx('nodesPanel.song.words') : tx('nodesPanel.song.noWords') }) }}</p>
      <button v-if="d.file && !d.recognised" type="button" class="btn" :disabled="!!songBusy || busy" :title="tx('nodesPanel.song.recogniseTitle')" @click="recogniseWords">
        <Icon name="spark" />{{ songBusy === 'words' ? tx('nodesPanel.song.recognising') : tx('nodesPanel.song.recognise') }}</button>
      <label class="stack"><span class="lbl">{{ tx('nodesPanel.song.piece') }}</span>
        <div class="seg"><button v-for="v in ['whole', 'best', 'own']" :key="v" type="button" :class="{ on: (d.length || 'whole') === v }" @click="set('length', v)">{{ tx(`nodesPanel.song.${v}`) }}</button></div></label>
      <div v-if="d.length === 'own'" class="ni-row">
        <label class="stack grow"><span class="lbl">{{ tx('nodesPanel.song.from') }}</span>
          <input class="field-in" type="number" step="0.5" min="0" :value="d.start ?? 0" @change="set('start', +($event.target as HTMLInputElement).value)"></label>
        <label class="stack grow"><span class="lbl">{{ tx('nodesPanel.song.secs') }}</span>
          <input class="field-in" type="number" step="1" min="5" max="300" :value="d.seconds ?? 60" @change="set('seconds', +($event.target as HTMLInputElement).value)"></label></div>
      <p v-if="piece" class="muted small">{{ tx('nodesPanel.song.picked', { a: mmss(piece[0]), b: mmss(piece[1]), s: mmss(piece[1] - piece[0]) }) }}</p>
      <p class="muted small">{{ tx('nodesPanel.song.hint') }}</p>
    </template>

    <!-- the clip writer: the «Песня → клип» button's script, into the graph -->
    <template v-else-if="t === 'clip_writer'">
      <p v-if="styled" class="muted small">{{ tx('looks.writerNote') }}</p>
      <button type="button" class="primary" :disabled="busy || !inputsOf(id, 'song').length" @click="runLlm([id])"><Icon name="spark" :size="18" />{{ d.plan ? (writerStale ? tx('nodesPanel.rewrite') : tx('nodesPanel.writeAgain')) : tx('nodesPanel.write') }}</button>
      <button type="button" class="btn" :disabled="!d.plan" @click="expand(id)"><Icon name="layers" />{{ tx('nodesPanel.expand') }}</button>
      <div v-if="d.plan" class="plan-list"><span class="lbl">{{ d.plan.title_ru }}</span>
        <p v-for="s in d.plan.scenes" :key="s.index"><b>{{ s.index + 1 }}</b> <small class="muted">{{ dec(Number(s.seconds).toFixed(1)) }} · {{ shotName(s) }}</small> {{ s.ru }}</p></div>
      <p class="muted small">{{ tx('nodesPanel.clipw.hint') }}</p>
      <p class="muted small">{{ tx('nodesPanel.clipw.expandHint') }}</p>
    </template>

    <!-- group -->
    <template v-else-if="t === 'group'">
      <div class="ni-row"><label class="stack grow"><span class="lbl">{{ tx('nodesPanel.width') }}</span><input class="field-in" type="number" step="20" :value="d.w || 720" @input="set('w', +($event.target as HTMLInputElement).value)"></label>
        <label class="stack grow"><span class="lbl">{{ tx('nodesPanel.height') }}</span><input class="field-in" type="number" step="20" :value="d.h || 420" @input="set('h', +($event.target as HTMLInputElement).value)"></label></div>
      <p class="muted small">{{ tx('nodesPanel.groupHint') }}</p>
    </template>

    <div v-if="st?.error && st.state === 'error'" class="warn-line"><Icon name="warn" :size="14" /><span>{{ st.error }}</span></div>
    <div class="ni-acts">
      <button v-if="MAKES.includes(t)" type="button" class="btn" :disabled="busy" @click="runTo([id])"><Icon name="clapper" />{{ t === 'scene' ? tx('nodesPanel.shootTo') : t === 'picture' ? tx('nodesPanel.draw') : tx('nodesPanel.makeTo') }}</button>
      <button v-if="!['note', 'group'].includes(t)" type="button" class="btn" @click="duplicateBranch(id)"><Icon name="shuffle" />{{ tx('nodesPanel.dupBranch') }}</button>
      <button type="button" class="btn danger" @click="removeNodes([id])"><Icon name="trash" />{{ tx('nodesPanel.delNode') }}</button>
    </div>
  </div>
</template>
