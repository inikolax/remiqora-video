<script setup lang="ts">
// The lab: one scene by hand. The bench on the left (the prompt and its parts, the start frame, length, LoRA, the
// shoot button), the monitor on the right (the take being watched and the takes, grouped by prompt).
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, shallowReactive, watch, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import HelpQ from '../components/HelpQ.vue'
import Icon from '../components/Icon.vue'
import ModelMenu from '../components/lab/ModelMenu.vue'
import PresetMenu from '../components/lab/PresetMenu.vue'
import PromptSheet from '../components/lab/PromptSheet.vue'
import SceneForm from '../components/lab/SceneForm.vue'
import { api, post } from '../lib/api'
import { S, banner, loadLoras, lorasFor, modelName, onJobEnd, pollJobs } from '../lib/store'
import { minsTenth as mins, secs } from '../lib/format'
import { PARTS, PART_COLOR, type Lang, labelSide, markup, paragraphs } from '../lib/promptParts'
import { FRAME_LINE, type Fix, checkPrompt, fitTimeline } from '../lib/promptChecks'
import type { Preset } from '../lib/presets'
import { presets } from '../lib/content'
import { TL, setTextLang } from '../lib/textLang'
import { type Fields, compose, composeFor, empty, formOf, forTranslation, parse } from '../lib/sceneForm'
import type { Job, Lora, Take } from '../lib/types'

const { t, locale } = useI18n()
const DEFAULT_STRENGTH = 0.8, MAX_STRENGTH = 5
const LENGTHS = [3, 5, 8, 10]

// ---- the form, kept in the browser between visits ----
const KEY = 'h3studio.v1'
const BENCH_W = 468
const saved = (() => { try { return JSON.parse(localStorage.getItem(KEY) || '{}') } catch { return {} } })()
const F = reactive({
  prompt: (saved.prompt || '') as string, seed: (saved.seed || '') as string, count: +(saved.count || 1),
  used: (saved.used || {}) as Record<string, { strength: number }>, last: (saved.last || {}) as Record<string, number>,
  aspect: (saved.aspect || '16:9') as string, quality: (saved.quality || 'draft') as string, seconds: +(saved.seconds || 5),
  model: (saved.model || 'h3') as string,     // phase 10: which model shoots the scene
  markup: (saved.markup ?? true) as boolean,
  lang: (saved.lang || 'en') as Lang,          // the tab: the English prompt (to H3) or the Russian one (to translate)
  ru: (saved.ru || '') as string,
  ruDone: (saved.ruDone || '') as string,      // the Russian text the English one was translated from
  enDone: (saved.enDone || '') as string,      // and that translation: was the English edited since?
  frame: (saved.frame || null) as null | { name: string; url: string; ratio: number },
  benchW: +(saved.benchW || BENCH_W),          // the bench's width, dragged at its edge
  mode: (saved.mode || (saved.prompt || saved.ru ? 'text' : 'fields')) as 'fields' | 'text',   // the prompt as fields, or as a whole text
  fieldsEn: (saved.fieldsEn || empty()) as Fields,
  fieldsRu: (saved.fieldsRu || empty()) as Fields,
  fieldsRuDone: (saved.fieldsRuDone || '') as string,   // the Russian fields the English ones were translated from
})
watch(F, () => {
  try { localStorage.setItem(KEY, JSON.stringify({ prompt: F.prompt, seed: F.seed, count: F.count, used: F.used, last: F.last, aspect: F.aspect, quality: F.quality, seconds: F.seconds, frame: F.frame, markup: F.markup, model: F.model,
    lang: F.lang, ru: F.ru, ruDone: F.ruDone, enDone: F.enDone, benchW: F.benchW,
    mode: F.mode, fieldsEn: F.fieldsEn, fieldsRu: F.fieldsRu, fieldsRuDone: F.fieldsRuDone })) }
  catch { /* private window */ }
}, { deep: true })

const cfg = computed(() => S.cfg!)
// the prompt fields: one (the open tab) on the bench, both side by side when «Развернуть» is on; the functions below work
// on the one in focus (F.lang)
const sheets = shallowReactive<Record<string, InstanceType<typeof PromptSheet> | null>>({})
const setSheet = (lang: Lang, c: unknown) => { sheets[lang] = c as InstanceType<typeof PromptSheet> | null }
const promptEl = computed(() => sheets[F.lang]?.el ?? null)
const wide = ref(false)
// the texts' language is English: the prompt is the text, so one tab and one column, nothing to translate
const enOnly = computed(() => TL.code === 'en')
watchEffect(() => { if (enOnly.value) F.lang = 'en' })
const langs = computed<Lang[]>(() => (enOnly.value ? ['en'] : wide.value ? ['ru', 'en'] : [F.lang]))
// the first tab is the texts' language itself: pick another right here (the same setting as «Модели и настройки» → «Сценарист»)
async function pickLang(e: Event) {
  const code = (e.target as HTMLSelectElement).value
  try { await api('/api/lang', { method: 'PUT', body: { text: code } }); setTextLang(code); if (code !== 'en') F.lang = 'ru' } catch (err) { banner((err as Error).message) }
}
const val = (lang: Lang) => (lang === 'ru' ? F.ru : F.prompt)
const put = (lang: Lang, v: string) => { if (lang === 'ru') F.ru = v; else F.prompt = v }
const PH = (lang: Lang) => (lang === 'en' && formOf(F.model) !== 'h3' ? t(`lab.ph.${formOf(F.model)}`, { model: mShort.value }) : t(`lab.ph.${lang}`))
watch(wide, async (on) => { await nextTick(); promptEl.value?.focus(); if (!on) popOpen.value && showPop(false) })

// the bench's width: dragged at its right edge (or the arrow keys on it), double click - back to the default
const clampW = (w: number) => Math.round(Math.max(360, Math.min(innerWidth - 420, w)))
function dragSplit(e: PointerEvent) {
  const x0 = e.clientX, w0 = Math.min(F.benchW, innerWidth - 420), bar = e.currentTarget as HTMLElement
  bar.setPointerCapture(e.pointerId)
  const move = (ev: PointerEvent) => { F.benchW = clampW(w0 + ev.clientX - x0) }
  const up = () => { bar.removeEventListener('pointermove', move); bar.removeEventListener('pointerup', up) }
  bar.addEventListener('pointermove', move)
  bar.addEventListener('pointerup', up)
}
const formError = ref('')
const going = ref(false)

// ---- the fields: in the «Поля» mode the texts are composed from them (the model shoots the English one, in its own
// form: H3's parts, LTX's / WAN's one paragraph); «Текст» edits the texts themselves, and going back to the fields
// parses them ----
const form = computed(() => formOf(F.model))
const wholeTag = computed(() => (form.value === 'h3' ? undefined : t('lab.tag.whole', { model: mShort.value })))
const enComposed = () => composeFor(F.fieldsEn, form.value, F.seconds, !!F.frame)
const fields = computed(() => ({ en: F.fieldsEn, ru: F.fieldsRu }))
watch(() => [F.mode, F.seconds, !!F.frame, form.value, JSON.stringify(F.fieldsEn), JSON.stringify(F.fieldsRu)],
  () => { if (F.mode !== 'fields') return; F.prompt = enComposed(); F.ru = compose(F.fieldsRu, 'ru', F.seconds, !!F.frame) },
  { immediate: true })
function setMode(m: 'fields' | 'text') {
  if (m === F.mode) return
  if (m === 'fields') {
    // the English text as the fields composed it stays those fields; LTX's / WAN's paragraph edited by hand has no
    // parts to parse: all of it goes to the place, as a text without labels does
    const en = F.prompt === enComposed() ? { fields: F.fieldsEn, lost: [] as string[] }
      : form.value !== 'h3' && F.prompt.trim() ? { fields: { ...empty(), place: F.prompt.trim() }, lost: [F.prompt] } : parse(F.prompt, 'en')
    const ru = parse(F.ru, 'ru')
    F.fieldsEn = en.fields
    F.fieldsRu = ru.fields
    if (en.lost.length || ru.lost.length) banner(t('lab.lostToPlace'))
  }
  F.mode = m
}

// ---- the prompt and its parts: the open tab's text, English (to H3) or Russian (for the writer to translate) ----
const text = computed({ get: () => (F.lang === 'ru' ? F.ru : F.prompt), set: (v: string) => { if (F.lang === 'ru') F.ru = v; else F.prompt = v } })
const hasBy = computed(() => ({ en: new Set(paragraphs(F.prompt, 'en').map((p) => p.key)), ru: new Set(paragraphs(F.ru, 'ru').map((p) => p.key)) }))
// what to look at before shooting, each with its fix (lib/promptChecks.ts)
const issuesBy = computed(() => ({ en: checkPrompt(F.prompt, 'en', F.seconds, !!F.frame, F.model), ru: checkPrompt(F.ru, 'ru', F.seconds, !!F.frame) }))
function fix(f: Fix) {
  const t = promptEl.value
  if (f.act === 'select' && f.at && t) { t.focus(); t.setSelectionRange(f.at[0], f.at[1]) }
  else if (f.act === 'len' && f.secs) setLen(f.secs)
  else if (f.act === 'fit') text.value = fitTimeline(text.value, F.seconds)
  else if (f.act === 'part' && f.key) onPart(f.key)
  else if (f.act === 'frameline') text.value = FRAME_LINE[labelSide(F.lang)].line + '\n\n' + text.value.replace(/^\s+/, '')
  else if (f.act === 'noframeline') text.value = text.value.replace(FRAME_LINE[labelSide(F.lang)].re, '')
}
// a whole preset from «Заготовка ▾», in the open tab's language; its length comes with it (the timeline is cut to it)
function usePreset(p: Preset) {
  if (F.mode === 'fields') {
    const filled = [F.fieldsEn, F.fieldsRu].some((f) => f.style || f.place || f.audio || f.beats.some((b) => b.text))
    if (filled && !confirm(t('lab.confirmPresetFields', { name: p.name }))) return
    F.fieldsEn = parse(p.en, 'en').fields
    F.fieldsRu = parse(p.ru, 'ru').fields
    setLen(p.seconds)
    return
  }
  if (text.value.trim() && !confirm(t('lab.confirmPresetText', { name: p.name }))) return
  text.value = p[labelSide(F.lang)]   // a preset's Russian version only on a Russian sheet
  setLen(p.seconds)
  selectDots(0)
}
async function selectDots(from: number, to?: number) {   // the first "..." from `from`, or the stub's end
  await nextTick()
  const t = promptEl.value!, at = text.value.indexOf('...', from)
  t.focus()
  if (at >= 0 && (to == null || at < to)) t.setSelectionRange(at, at + 3)
  else if (to != null) t.setSelectionRange(to, to)
}
function onPart(key: string) {
  const t = promptEl.value!, now = text.value, paras = paragraphs(now, F.lang), here = paras.find((p) => p.key === key)
  if (here) { t.focus(); t.setSelectionRange(here.start, here.end); return }
  // the missing part goes before the first paragraph of a later part, or to the end
  const order = PARTS.findIndex((p) => p.key === key), stub = PARTS[order][labelSide(F.lang)].stub
  const next = paras.find((p) => p.key && PARTS.findIndex((x) => x.key === p.key) > order)
  const at = next ? next.start : now.replace(/\s+$/, '').length
  const before = now.slice(0, at).replace(/\s+$/, ''), after = now.slice(at)
  const glue = before ? '\n\n' : ''
  text.value = before + glue + stub + (after.trim() ? '\n\n' + after.replace(/^\s+/, '') : '')
  selectDots(before.length + glue.length, before.length + glue.length + stub.length)
}

// the writer translates the Russian tab into the English one (spoken lines in quotes stay Russian); only by the button
const tr = ref<null | { state: 'wait' | 'queue' | 'error' | 'done'; text?: string; model?: string; secs?: number }>(null)
const stale = computed(() => (F.mode === 'fields' ? !!F.fieldsRuDone && JSON.stringify(forTranslation(F.fieldsRu)) !== F.fieldsRuDone
  : !!F.enDone && !!F.ru.trim() && F.ru !== F.ruDone))
async function translate() {
  if (F.mode === 'fields') return translateFields()
  const ru = F.ru.trim()
  if (!ru || (tr.value && (tr.value.state === 'wait' || tr.value.state === 'queue'))) return
  if (F.prompt.trim() && F.prompt !== F.enDone && !confirm(t('lab.confirmTrText'))) return
  tr.value = { state: 'wait' }
  let job: Job
  try { job = await post('/api/llm/translate', { text: ru, seconds: F.seconds, model: S.llm || null, video_model: F.model, frame: !!F.frame }) }
  catch (e) { tr.value = { state: 'error', text: (e as Error).message }; return }
  while (job.status === 'queued' || job.status === 'running') {
    await new Promise((ok) => setTimeout(ok, 1000))
    try { job = await api(`/api/jobs/${job.id}`) } catch { return }
    tr.value = { state: job.status === 'queued' ? 'queue' : 'wait', secs: Math.round(job.elapsed || 0) }
  }
  if (job.status !== 'done' || !job.result?.en) { tr.value = { state: 'error', text: job.error || t('lab.noTranslation') }; return }
  F.prompt = F.enDone = job.result.en
  F.ruDone = F.ru
  F.lang = 'en'
  tr.value = { state: 'done', model: job.result.model, secs: Math.round(job.elapsed) }
}
async function translateFields() {
  const src = forTranslation(F.fieldsRu)
  if (!(src.style || src.place || src.audio || src.beats.some(Boolean)) || (tr.value && (tr.value.state === 'wait' || tr.value.state === 'queue'))) return
  const en = F.fieldsEn
  if ((en.style || en.place || en.audio || en.beats.some((b) => b.text)) && !confirm(t('lab.confirmTrFields'))) return
  tr.value = { state: 'wait' }
  let job: Job
  try { job = await post('/api/llm/translate-fields', { fields: src, seconds: F.seconds, model: S.llm || null, video_model: F.model }) }
  catch (e) { tr.value = { state: 'error', text: (e as Error).message }; return }
  while (job.status === 'queued' || job.status === 'running') {
    await new Promise((ok) => setTimeout(ok, 1000))
    try { job = await api(`/api/jobs/${job.id}`) } catch { return }
    tr.value = { state: job.status === 'queued' ? 'queue' : 'wait', secs: Math.round(job.elapsed || 0) }
  }
  const r = job.result
  if (job.status !== 'done' || !r) { tr.value = { state: 'error', text: job.error || t('lab.noTranslation') }; return }
  const ru = F.fieldsRu
  F.fieldsEn = { style: r.style, place: r.place, shot: ru.shot, move: ru.move, cameraText: r.camera, audio: r.audio, keep: ru.keep, noText: ru.noText,
    beats: ru.beats.map((b, i) => ({ text: r.beats[i] || '', secs: b.secs })) }
  F.fieldsRuDone = JSON.stringify(src)
  F.lang = 'en'
  tr.value = { state: 'done', model: r.model, secs: Math.round(job.elapsed) }
}

// ---- length, format, quality ----
const quality = computed(() => cfg.value.qualities.find((q) => q.id === F.quality) || cfg.value.qualities[0])
const aspects = computed(() => [...cfg.value.aspects, ...(F.frame ? [{ id: 'frame', ratio: F.frame.ratio }] : [])])
const ratio = computed(() => (F.aspect === 'frame' && F.frame ? F.frame.ratio : (cfg.value.aspects.find((a) => a.id === F.aspect) || cfg.value.aspects[0]).ratio))
function canvas(r: number, mp: number) {   // the same rounding as graphs.canvas on the server
  const area = mp * 1024 * 1024, w = Math.sqrt(area * r), h = w / r
  return [Math.max(32, Math.round(w / 32) * 32), Math.max(32, Math.round(h / 32) * 32)]
}
// the model's frame grid (H3 17k+5, LTX 8k+1, WAN 4k+1), no longer than it shoots - as videomodels.frames on the server
const grid = () => (F.model === 'h3' ? [17, 5] : F.model.startsWith('wan5b') ? [4, 1] : [8, 1])
const frames = (s: number) => {
  const [g, a] = grid(), cap = card.value?.max_seconds || 15
  let n = Math.max(g + a, Math.round(Math.min(s, cap) * 24)); while (n % g !== a) n++; return n
}
// phase 10: another model's own sizes (its megapixels, its step: LTX wants multiples of 64)
const card = computed(() => (cfg.value.video_models || []).find((m) => m.id === F.model) || null)
const mShort = computed(() => modelName(F.model))   // the chosen model, in the lines about the prompt
const size = computed(() => {
  const c = card.value
  if (!c || c.id === 'h3') return canvas(ratio.value, quality.value.mp)
  const area = (c.mp[F.quality] || c.mp.draft) * 1024 * 1024, w = Math.sqrt(area * ratio.value), h = w / ratio.value
  return [Math.max(c.step, Math.round(w / c.step) * c.step), Math.max(c.step, Math.round(h / c.step) * c.step)]
})
const count = computed(() => Math.min(8, Math.max(1, F.count || 1)))
const takes = (n: number) => t('lab.takesN', n)
// seconds with the interface's decimal mark (5,5 с / 5.5 s); the quality's name
const num = (x: number) => (locale.value === 'ru' ? String(x).replace('.', ',') : String(x))
const qlName = (id: string) => (id === 'draft' || id === 'final' ? t(`lab.ql.${id}`) : '')
const eta = computed(() => {
  const q = quality.value, [w, h] = size.value, c = card.value
  const one = c && c.id !== 'h3'
    ? c.per_scene[F.quality] * (w * h / (c.sizes[F.quality].w * c.sizes[F.quality].h)) * (frames(F.seconds) / frames(5))
    : q.per_scene * (w * h / (q.w * q.h)) * (frames(F.seconds) / 124)
  return `≈ ${mins(one * count.value)}${count.value > 1 ? ' ' + t('lab.etaFor', { takes: takes(count.value) }) : ''}`
})
const setLen = (s: number) => { F.seconds = s }
const box = (r: number) => { const k = 14 / Math.max(r, 1); return { width: `${Math.round(r * k)}px`, height: `${Math.round(k)}px` } }
function ownLen(e: Event) { const v = Math.round(+(e.target as HTMLInputElement).value * 2) / 2; if (v >= 1 && v <= 15) F.seconds = v }
// what «Снять» will shoot, in one line above it
const presetGroups = computed(() => [...new Set(presets().map((x) => x.group))])
const summary = computed(() => [t('lab.secsN', { s: num(F.seconds) }), F.aspect === 'frame' ? t('lab.asFrame') : F.aspect,
  `${(qlName(F.quality) || F.quality).toLowerCase()} ${size.value[0]}×${size.value[1]}`, F.seed === '' ? t('lab.seedRandom') : t('lab.seedN', { seed: F.seed }),
  active.value.length ? `LoRA: ${active.value.length}` : '', F.frame ? t('lab.fromFrame') : ''].filter(Boolean).join(', '))
// the timeline under the frame: the open tab's "[0s-3s] ..." lines on the scene's length; one running past the end shows so.
// LTX's / WAN's English paragraph has no timestamps: the own-language sheet's then
const beatsRu = computed(() => F.lang === 'en' && form.value !== 'h3')
const beatsSrc = computed(() => (beatsRu.value ? F.ru : text.value))
const beats = computed(() => [...beatsSrc.value.matchAll(/^[ \t]*\[\s*(\d+(?:[.,]\d+)?)\s*[sс]?\s*-\s*(\d+(?:[.,]\d+)?)\s*[sс]?\s*\][ \t]*(.*)$/gm)]
  .map((m) => ({ from: +m[1].replace(',', '.'), to: +m[2].replace(',', '.'), text: m[3].trim(), at: [m.index!, m.index! + m[0].length] as [number, number] }))
  .filter((b) => b.to > b.from))
const span = computed(() => Math.max(F.seconds, ...beats.value.map((b) => b.to)))
const ticks = computed(() => { const k = span.value > 10 ? 2 : 1, out = []; for (let s = 0; s <= span.value + 0.01; s += k) out.push(s); return out })
function goBeat(b: { at: [number, number] }) {
  const el = promptEl.value
  if (F.mode !== 'text' || !el || beatsRu.value) return
  el.focus(); el.setSelectionRange(b.at[0], b.at[1])
}
const step = (d: number) => { F.count = Math.min(8, Math.max(1, count.value + d)) }
watch(() => F.frame, (f) => { if (!f && F.aspect === 'frame') F.aspect = '16:9' })

// ---- the start frame ----
const over = ref(false)
const hero = ref<null | { state: 'wait' | 'queue' | 'error' | 'done'; text?: string; model?: string; secs?: number; ru?: string; en?: string }>(null)
const withRatio = (f: any) => new Promise<any>((ok) => {   // the frame's proportions, for "как у кадра"
  const img = new Image()
  img.onload = () => ok({ ...f, ratio: img.naturalWidth / img.naturalHeight })
  img.onerror = () => ok({ ...f, ratio: 16 / 9 })
  img.src = f.url
})
function setFrame(f: any) {
  const had = !!F.frame
  F.frame = f
  hero.value = null
  if (f && !had) F.aspect = 'frame'   // a picture brings its own proportions; the user can still pick another
  if (f) show(null)                   // the monitor shows it in the frame
}
function pickFrame(e: Event) { const i = e.target as HTMLInputElement; uploadFrame(i.files?.[0]); i.value = '' }
async function uploadFrame(file?: File) {
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  try { setFrame(await withRatio(await api('/api/frames', { method: 'POST', body: fd }))) } catch (e) { formError.value = (e as Error).message }
}
// the writer looks at the start frame: the hero's look in English, to paste into the prompt
async function describeFrame() {
  if (!F.frame) return
  hero.value = { state: 'wait' }
  let job: Job
  try { job = await post('/api/llm/describe', { frame: F.frame.name, model: S.llm || null }) }
  catch (e) { hero.value = { state: 'error', text: (e as Error).message }; return }
  while (job.status === 'queued' || job.status === 'running') {
    await new Promise((ok) => setTimeout(ok, 1000))
    try { job = await api(`/api/jobs/${job.id}`) } catch { return }
    if (job.status === 'queued') hero.value = { state: 'queue' }
  }
  if (job.status !== 'done') { hero.value = { state: 'error', text: job.error || t('lab.failed') }; return }
  const d = job.result, has = (a: string, b: string) => a.toLowerCase().includes(b.toLowerCase().replace(/\.$/, ''))
  hero.value = { state: 'done', model: d.model, secs: Math.round(job.elapsed),
    en: d.en + (d.outfit_en && !has(d.en, d.outfit_en) ? ` Wearing ${d.outfit_en.replace(/^./, (c: string) => c.toLowerCase())}` : ''),
    ru: d.ru + (d.outfit_ru && !has(d.ru, d.outfit_ru) ? ' ' + d.outfit_ru : '') }
}
function pasteHero() {   // the look in the open tab's language
  const t = promptEl.value!, now = text.value, at = t.selectionStart ?? now.length
  text.value = now.slice(0, at) + (F.lang === 'ru' ? hero.value!.ru : hero.value!.en) + now.slice(t.selectionEnd ?? at)
  t.focus()
}

// ---- LoRA: the rack in work and the library under «Добавить» ----
const KIND: Record<string, string> = { lora: 'LoRA', lokr: 'LoKr', loha: 'LoHa', dora: 'DoRA' }
const kindName = (k: string) => KIND[k] || (k === 'weights' || k === 'unreadable' ? t(`lab.kind.${k}`) : k)
const fmt = (v: number) => (Math.round(v * 100) / 100).toString()
const active = computed(() => Object.keys(F.used).map((id) => lorasFor(F.model).find((l) => l.id === id)).filter(Boolean) as Lora[])
const search = ref('')
const rest = computed(() => lorasFor(F.model).filter((l) => !F.used[l.id]))
const found = computed(() => { const q = search.value.trim().toLowerCase(); return rest.value.filter((l) => !q || (l.folder + '/' + l.name).toLowerCase().includes(q)) })
const loraTitle = (l: Lora) => l.note || [l.base, l.rank && t('lab.rank', { n: l.rank }), l.blocks && t('lab.blocks', { n: l.blocks })].filter(Boolean).join(', ') || l.name
const setStrength = (id: string, v: number) => { F.used[id].strength = v; F.last[id] = v }
const popOpen = ref(false)
const addBtn = ref<HTMLElement | null>(null)
const searchEl = ref<HTMLInputElement | null>(null)
const popPos = ref<Record<string, string>>({})
// fixed to the window, so the bench's scroll doesn't clip it: down from the button, or up when the room is above
function place() {
  const r = addBtn.value!.getBoundingClientRect(), down = innerHeight - r.bottom > 400 || r.top < 400
  popPos.value = { right: `${Math.max(16, innerWidth - r.right)}px`, top: down ? `${r.bottom + 6}px` : '', bottom: down ? '' : `${innerHeight - r.top + 6}px` }
}
async function showPop(on: boolean) {
  popOpen.value = on
  if (!on) return
  place()
  await nextTick()
  searchEl.value?.focus()
}
function addLora(l: Lora) {
  if (l.verdict === 'blocked') return
  F.used[l.id] = { strength: F.last[l.id] ?? DEFAULT_STRENGTH }
  showPop(false)
  addBtn.value?.focus()
}
const away = () => { if (popOpen.value) showPop(false) }
const escKey = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && popOpen.value) { showPop(false); addBtn.value?.focus() }
  else if (e.key === 'Escape' && wide.value && !document.querySelector('.preset-pop, .help-card')) wide.value = false
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); shoot() }
}

// ---- shooting ----
// `all` (phase 10): the same prompt and seed on every model whose weights are there - one take each, to compare
async function shoot(all = false) {
  formError.value = ''
  const prompt = F.prompt.trim()
  if (!prompt) {
    formError.value = F.lang === 'ru' && F.ru.trim() ? t('lab.needEn', { model: mShort.value }) : t('lab.noPrompt')
    promptEl.value?.focus(); return
  }
  if (F.lang === 'ru' && stale.value && !confirm(t('lab.confirmStale', { v: TL.name }))) return
  if (checkPrompt(prompt, 'en', F.seconds, !!F.frame, F.model).some((i) => i.id === 'fill') && !confirm(t('lab.confirmFill'))) return
  const loras = active.value.map((l) => ({ id: l.id, strength: F.used[l.id].strength }))
  const body: Record<string, unknown> = { prompt, seconds: F.seconds, quality: F.quality, aspect: F.aspect, seed: F.seed === '' ? -1 : +F.seed, count: count.value, loras,
    video_model: F.model }
  if (F.frame) { body.first_frame = F.frame.name; body.frame_ratio = F.frame.ratio }
  going.value = true
  try {
    if (!all) await post('/api/scenes', body)
    else {
      const seed = F.seed === '' ? Math.floor(Math.random() * 2 ** 30) : +F.seed
      for (const m of (cfg.value.video_models || []).filter((x) => !x.missing.length && !x.imported)) {
        await post('/api/scenes', { ...body, seed, count: 1, video_model: m.id,
          loras: Object.keys(F.used).filter((id) => lorasFor(m.id).some((l) => l.id === id)).map((id) => ({ id, strength: F.used[id].strength })) })
      }
    }
    await pollJobs()
  } catch (e) { formError.value = (e as Error).message } finally { going.value = false }
}

const PHASES = ['starting', 'loading', 'encoding', 'decoding', 'saving']
const labJobs = computed(() => S.jobs.filter((j) => j.kind === 'scene' && (j.status === 'running' || j.status === 'queued')))
const running = computed(() => labJobs.value.find((j) => j.status === 'running') || null)
const jobPct = (j: Job) => (j.phase === 'sampling' && j.steps ? Math.round((100 * j.step) / j.steps) : j.phase === 'decoding' || j.phase === 'saving' ? 100
  : j.estimate ? Math.min(99, Math.round((100 * j.elapsed) / j.estimate)) : 0)
const jobStep = (j: Job) => (j.status === 'queued' ? t('lab.queued') : j.phase === 'sampling' ? t('lab.stepOf', { step: j.step, steps: j.steps }) : PHASES.includes(j.phase) ? t(`lab.phase.${j.phase}`) : t('lab.preparing'))

// ---- the monitor ----
const videos = ref<Take[]>([])
const shown = ref<Take | null>(null)
const promptOpen = ref(false)
// «Копировать» on the take: the seed or the whole prompt; the button shows a check mark for a moment
const copied = ref('')
async function copy(text: string, what: string) {
  let ok = false
  try { await navigator.clipboard.writeText(text); ok = true } catch { /* no clipboard API (an unfocused page, an old browser): the old way below */ }
  if (!ok) {
    const ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta); ta.select()
    try { ok = document.execCommand('copy') } catch { ok = false }
    ta.remove()
  }
  if (!ok) { banner(t('lab.copyFail')); return }
  copied.value = what
  setTimeout(() => { if (copied.value === what) copied.value = '' }, 1500)
}
// the shot's prompt is cut to a few lines: a visible «Весь промт» under it says there is more
const longPrompt = computed(() => { const p = shown.value?.params.prompt || ''; return p.split(/\r?\n/).length > 3 || p.length > 180 })
// the frame's proportions: the take being watched, or what «Снять» will shoot
const vfRatio = computed(() => (shown.value?.params.width && shown.value.params.height ? shown.value.params.width / shown.value.params.height : ratio.value))
const autoplay = ref(false)
async function loadVideos() { try { videos.value = await api<Take[]>('/api/videos') } catch { /* the server is restarting */ } }
function show(v: Take | null, play = false) { shown.value = v; promptOpen.value = false; autoplay.value = play }
const when = (v: Take) => (v.created || '').replace('T', ' ').slice(0, 16)
const out = (path: string) => `/outputs/${encodeURIComponent(path)}`
const loraLine = (p: Record<string, any>) => (p.loras || []).map((l: any) => `${l.name} ${fmt(l.strength)}`).join(', ')
async function continueFrom(v: Take) {
  try { setFrame(await withRatio(await post(`/api/frames/from-video/${encodeURIComponent(v.file)}`))); F.aspect = 'frame' }
  catch (e) { formError.value = (e as Error).message }
}
function reuse(p: Record<string, any>, withSeed: boolean) {
  F.prompt = p.prompt || ''
  F.lang = 'en'
  if (F.mode === 'fields') F.fieldsEn = parse(F.prompt, 'en').fields
  if (p.seconds) F.seconds = p.seconds
  if (p.quality) F.quality = p.quality
  F.model = p.model || 'h3'   // phase 10: the take's model too
  if (p.aspect && p.aspect !== 'frame') F.aspect = p.aspect
  F.seed = withSeed ? String(p.seed) : ''
  F.used = {}
  for (const l of p.loras || []) if (S.loras.some((x) => x.id === l.id)) F.used[l.id] = { strength: l.strength }
  promptEl.value?.focus()
}
async function del(v: Take) {
  if (!confirm(t('lab.confirmDel'))) return
  try { await api(`/api/videos/${encodeURIComponent(v.file)}`, { method: 'DELETE' }) } catch (e) { banner((e as Error).message); return }
  await loadVideos()
  show(videos.value[0] || null)
}

// the takes: grouped by prompt, the lab's running and queued ones first in their group; a group is named by what
// happens in it: the place, else the first beat, else the first line
function gist(prompt: string) {
  const lines = (prompt || '').split('\n').map((l) => l.trim()).filter(Boolean)
  const place = lines.find((l) => /^Scene( continues)?:/i.test(l)), beat = lines.find((l) => /^\[\s*\d/.test(l))
  return place ? place.replace(/^Scene( continues)?:\s*/i, '') : beat ? beat.replace(/^\[[^\]]*\]\s*/, '') : lines[0] || t('lab.noPromptGist')
}
const groups = computed(() => {
  const by = new Map<string, { prompt: string; takes: Take[]; jobs: Job[] }>()
  const add = (prompt: string) => { const k = (prompt || '').trim(); if (!by.has(k)) by.set(k, { prompt: k, takes: [], jobs: [] }); return by.get(k)! }
  for (const j of labJobs.value) add(j.params.prompt).jobs.push(j)
  for (const v of videos.value) add(v.params?.prompt).takes.push(v)
  return [...by.values()]
})
const monitor = ref<HTMLElement | null>(null)
// the prompt field on the bench is never taller than the bench shows below the field's top: its scroll bar and its last
// lines stay in sight above the footer with «Снять». A bench that does not scroll (a phone) leaves it to the CSS.
const benchBody = ref<HTMLElement | null>(null)
const fieldMax = ref(0)
function fitField() {
  const body = benchBody.value, el = promptEl.value
  if (!body || !el || wide.value) return
  if (getComputedStyle(body).overflowY === 'visible') { fieldMax.value = 0; return }
  const top = el.getBoundingClientRect().top - body.getBoundingClientRect().top + body.scrollTop
  fieldMax.value = Math.max(220, Math.floor(body.clientHeight - top - 16))
}
const fitObs = new ResizeObserver(() => fitField())
watch(() => [F.lang, wide.value], () => nextTick(fitField))
const still = matchMedia('(prefers-reduced-motion: reduce)')
const hovered = ref<string | null>(null)
const takeCap = (v: Take) => [t('lab.secsN', { s: secs(v.params.length || 0) }), v.params.quality === 'final' && t('lab.final'),
  (v.params.loras || []).length && 'LoRA', v.params.first_frame && t('lab.fromFrame')].filter(Boolean).join(', ')
function watchTake(v: Take) { show(v, true); monitor.value?.scrollTo({ top: 0, behavior: still.matches ? 'auto' : 'smooth' }) }

const openFolder = (which: string) => post(`/api/open-folder/${which}`)
let off: () => void, loraTimer: ReturnType<typeof setInterval>
onMounted(async () => {
  if (F.frame) fetch(F.frame.url, { method: 'HEAD' }).then((r) => { if (!r.ok) setFrame(null) }).catch(() => {})
  await loadVideos()
  show(videos.value[0] || null)
  // a take of the lab is done: watch it; a failed one says why
  off = onJobEnd(async (j) => {
    if (j.kind !== 'scene') return
    if (j.status === 'error') banner(j.error || t('lab.shootError'))
    if (j.status !== 'done') return
    await loadVideos()
    const v = videos.value.find((x) => x.file === j.file)
    if (v) show(v, true)
  })
  loraTimer = setInterval(loadLoras, 8000)   // a LoRA dropped into the folder shows up by itself
  document.addEventListener('click', away)
  document.addEventListener('keydown', escKey)
  addEventListener('resize', away)
  if (benchBody.value) fitObs.observe(benchBody.value)
  nextTick(fitField)
})
onUnmounted(() => { fitObs.disconnect(); off?.(); clearInterval(loraTimer); document.removeEventListener('click', away); document.removeEventListener('keydown', escKey); removeEventListener('resize', away) })
</script>

<template>
  <div class="bench-wrap" :style="{ '--bench': `${F.benchW}px`, '--field-max': fieldMax ? `${fieldMax}px` : undefined }">
    <aside class="bench" :aria-label="t('lab.bench')">
      <div ref="benchBody" class="bench-body" @scroll="popOpen && place()">
        <section class="sheet-sec" :class="{ wide }" :role="wide ? 'dialog' : undefined" :aria-label="wide ? t('lab.promptBig') : undefined">
          <div class="sec-row">
            <div v-if="wide" class="wide-title"><b>{{ t('lab.scenePrompt') }}</b><HelpQ id="lab" term="Развернуть" /></div>
            <div v-else class="lang-row">
              <div class="lang-tabs" role="tablist" :aria-label="t('lab.promptLang')">
                <span class="tab-pick" :class="{ on: !enOnly && F.lang === 'ru' }" :title="enOnly ? t('lab.enOnlyTitle') : t('lab.ruTabTitle', { v: TL.name })">
                  <select :value="TL.code" :aria-label="t('lab.pickLang')" @mousedown="!enOnly && (F.lang = 'ru')" @focus="!enOnly && (F.lang = 'ru')" @change="pickLang">
                    <option v-for="l in TL.langs" :key="l.code" :value="l.code">{{ locale === 'en' ? l.en || l.name : l.name }}</option></select>
                  <i v-if="stale && !enOnly" class="stale-dot" :title="t('lab.staleTitle', { v: TL.name })" /></span>
                <button v-if="!enOnly" type="button" role="tab" :aria-selected="F.lang === 'en'" :title="t('lab.enTabTitle', { model: mShort })" @click="F.lang = 'en'">English</button>
              </div>
              <div class="lang-tabs mode-tabs" role="tablist" :aria-label="t('lab.howWrite')">
                <button type="button" role="tab" :aria-selected="F.mode === 'fields'" :title="t('lab.fieldsTitle')" @click="setMode('fields')">{{ t('lab.fields') }}</button>
                <button type="button" role="tab" :aria-selected="F.mode === 'text'" :title="t('lab.textTitle')" @click="setMode('text')">{{ t('lab.text') }}</button>
              </div><HelpQ id="lab" term="Промт сцены" />
            </div>
            <div class="sheet-tools">
              <label v-if="F.mode === 'text'" class="markup-tog" :title="t('lab.markupTitle')"><input v-model="F.markup" type="checkbox">{{ t('lab.markup') }}<HelpQ id="lab" term="Разметка" /></label>
              <PresetMenu :has-frame="!!F.frame" @pick="usePreset" />
              <template v-if="wide">
                <span class="wide-sum" :title="summary">{{ summary }}</span>
                <button class="primary wide-go" type="button" :disabled="going" title="Ctrl + Enter" @click="shoot()"><Icon name="clapper" />{{ count > 1 ? t('lab.shootN', { takes: takes(count) }) : t('lab.shootScene') }}</button>
                <button class="ghost" type="button" :title="t('lab.collapseTitle')" @click="wide = false"><Icon name="collapse" />{{ t('lab.collapse') }}</button>
              </template>
              <button v-else class="ghost only-ic" type="button" :title="t('lab.expandTitle')" :aria-label="t('lab.expandAria')" @click="wide = true"><Icon name="expand" /></button>
            </div>
          </div>
          <div class="cols">
            <div v-for="lang in langs" :key="lang" class="col" :class="{ on: wide && F.lang === lang }" @focusin="F.lang = lang">
              <div v-if="wide" class="col-head"><b>{{ lang === 'ru' ? t('lab.russian', { v: TL.name }) : 'English' }}</b><small>{{ lang === 'ru' ? t('lab.forTranslation') : t('lab.goesTo', { model: mShort }) }}</small>
                <i v-if="lang === 'ru' && stale" class="stale-dot" :title="t('lab.staleTitle', { v: TL.name })" /></div>
              <SceneForm v-if="F.mode === 'fields'" v-model="fields[lang]" :lang="lang" :seconds="F.seconds" />
              <details v-if="F.mode === 'fields'" class="params composed">
                <summary><span>{{ lang === 'ru' ? t('lab.ruText') : t('lab.promptFor', { model: mShort }) }}</span><em>{{ t('lab.composed') }}</em></summary>
                <pre class="ex-code">{{ val(lang) || '—' }}</pre>
                <button type="button" class="ghost" :title="t('lab.editAsTextTitle')" @click="setMode('text')"><Icon name="pen" />{{ t('lab.editAsText') }}</button>
              </details>
              <PromptSheet v-if="F.mode === 'text'" :ref="(c) => setSheet(lang, c)" :model-value="val(lang)" :lang="lang" :markup="F.markup" :placeholder="PH(lang)" :whole="lang === 'en' ? wholeTag : undefined"
                :label="lang === 'ru' ? t('lab.ruLabel') : t('lab.enLabel', { model: mShort })" @update:model-value="put(lang, $event)" />
              <!-- what the prompt already has, in the colours of the help's anatomy; a missing part is added by a click -->
              <div v-if="F.mode === 'text'" class="parts" role="group" :aria-label="t('lab.parts')">
                <!-- LTX's / WAN's English is one paragraph: no parts to add -->
                <button v-for="p in (lang === 'en' && form !== 'h3' ? [] : PARTS)" :key="p.key" type="button" class="part" :class="{ has: hasBy[lang].has(p.key) }" :style="{ '--c': `var(${PART_COLOR[p.key]})` }"
                  :title="hasBy[lang].has(p.key) ? t('lab.goPart', { name: p.name }) : t('lab.addStub', { stub: p[lang].stub.split('\n')[0] })" @click="onPart(p.key)"><Icon name="plus" :size="12" />{{ p.name }}</button>
                <HelpQ v-if="lang !== 'en' || form === 'h3'" id="lab" term="Части промта" />
                <span v-else class="kv">{{ t('lab.oneParagraph', { model: mShort }) }}</span>
                <span v-if="val(lang).length >= cfg.max_prompt * 0.6" class="count" :class="{ bad: val(lang).length > cfg.max_prompt }">{{ val(lang).length }} / {{ cfg.max_prompt }}</span>
              </div>
              <div v-if="lang === 'ru'" class="tr-row">
                <button type="button" class="btn" :disabled="!F.ru.trim() || tr?.state === 'wait' || tr?.state === 'queue'" :title="t('lab.trTitle', { model: mShort })" @click="translate"><Icon name="spark" />{{ t('lab.translate') }}</button><HelpQ id="lab" term="Перевести на английский" />
                <span v-if="tr?.state === 'wait'" class="kv">{{ t('lab.translating', { s: tr.secs || 0 }) }}</span>
                <span v-else-if="tr?.state === 'queue'" class="kv">{{ t('lab.waitGpu') }}</span>
                <span v-else-if="tr?.state === 'error'" class="error">{{ tr.text }}</span>
                <span v-else-if="stale" class="kv">{{ t('lab.staleLong', { v: TL.name }) }}</span>
              </div>
              <p v-if="lang === 'en' && tr?.state === 'done'" class="tr-done"><Icon name="check" :size="14" /><span><b>{{ t('lab.trDoneHead', { s: tr.secs, model: tr.model }) }}</b>{{ t('lab.trDoneHint') }}</span></p>
              <ul v-if="issuesBy[lang].length" class="checks" :aria-label="t('lab.checks')">
                <li v-for="i in issuesBy[lang]" :key="i.id" :title="i.more"><Icon name="warn" :size="14" /><span class="check-text">{{ i.text }}</span>
                  <span v-for="f in (F.mode === 'fields' ? i.fixes.filter((x) => x.act === 'len') : i.fixes)" :key="f.label" class="check-fix"><button type="button" class="ghost" @click="fix(f)">{{ f.label }}</button></span></li>
              </ul>
            </div>
          </div>
        </section>

        <!-- the writer's look at the start frame: here, by the prompt it is pasted into -->
        <section v-if="hero" class="framebox">
          <div class="hero">
            <div v-if="hero.state === 'wait'" class="kv">{{ t('lab.looking') }}</div>
            <div v-else-if="hero.state === 'queue'" class="kv">{{ t('lab.waitGpu') }}</div>
            <div v-else-if="hero.state === 'error'" class="error">{{ hero.text }}</div>
            <template v-else><div class="kv">{{ hero.model }}, {{ t('lab.secsN', { s: hero.secs }) }}</div><div class="ru">{{ hero.ru }}</div><div class="en">{{ hero.en }}</div>
              <button type="button" class="ghost" :title="t('lab.pasteTitle')" @click="pasteHero"><Icon name="pen" />{{ t('lab.paste') }}</button></template>
          </div>
        </section>

        <section class="rack-sec">
          <div class="sec-row">
            <span class="lbl">LoRA <small>{{ active.length ? t('lab.inWork', { n: active.length }) : '' }}</small><HelpQ id="lab" term="LoRA" /></span>
            <div class="rack-tools">
              <button v-if="active.length > 1" class="ghost" type="button" @click="F.used = {}">{{ t('lab.offAll') }}</button>
              <button ref="addBtn" class="ghost" type="button" aria-haspopup="dialog" :aria-expanded="popOpen" :disabled="!lorasFor(F.model).length && !cfg.lora_dirs.length" @click.stop="showPop(!popOpen)"><Icon name="plus" />{{ t('lab.add') }}</button>
            </div>
          </div>
          <div class="rack">
            <div v-for="l in active" :key="l.id" class="rack-item">
              <div class="rack-row"><div v-if="l.preview" class="thumb" :style="{ backgroundImage: `url('${l.preview}')` }" />
                <div class="name" :title="l.name">{{ l.name }}</div>
                <input type="range" min="-1" max="2" step="0.05" :value="F.used[l.id].strength" :aria-label="t('lab.strength', { name: l.name })" @input="setStrength(l.id, +($event.target as HTMLInputElement).value)">
                <input type="number" :min="-MAX_STRENGTH" :max="MAX_STRENGTH" step="0.05" :value="fmt(F.used[l.id].strength)" :aria-label="t('lab.strengthNum', { name: l.name })"
                  @input="($event.target as HTMLInputElement).value !== '' && !isNaN(+($event.target as HTMLInputElement).value) && setStrength(l.id, +($event.target as HTMLInputElement).value)">
                <button type="button" class="ghost" :title="t('lab.reset', { v: DEFAULT_STRENGTH })" :aria-label="t('lab.reset', { v: DEFAULT_STRENGTH })" @click="setStrength(l.id, DEFAULT_STRENGTH)"><Icon name="reset" /></button>
                <button type="button" class="ghost" :aria-label="t('lab.offOne', { name: l.name })" :title="t('lab.off')" @click="delete F.used[l.id]"><Icon name="close" /></button></div>
              <div v-if="l.note" class="note">{{ l.note }}</div>
              <div v-if="l.trigger" class="kv">{{ t('lab.trigger', { x: l.trigger }) }}</div>
            </div>
          </div>
          <div v-if="!active.length" class="rack-empty">{{ t('lab.noLora', { model: mShort }) }}</div>
        </section>

      </div>

      <footer class="bench-foot">
        <div class="go-row">
          <div class="with-q"><div class="stepper" :title="t('lab.countTitle')">
            <button type="button" :aria-label="t('lab.fewer')" @click="step(-1)"><Icon name="minus" /></button>
            <input v-model.number="F.count" type="number" min="1" max="8" :aria-label="t('lab.howMany')">
            <button type="button" :aria-label="t('lab.more')" @click="step(1)"><Icon name="plus" /></button>
          </div><HelpQ id="lab" term="Сколько дублей" /></div>
          <button class="primary" type="button" :disabled="going" title="Ctrl + Enter" @click="shoot()"><Icon name="clapper" :size="20" /><span class="p-lbl"><b>{{ count > 1 ? t('lab.shootN', { takes: takes(count) }) : t('lab.shootScene') }}{{ F.frame ? ' ' + t('lab.fromFrame') : '' }}</b><small>{{ eta }}</small></span></button>
        </div>
        <button type="button" class="ghost compare-all" :disabled="going" :title="t('lab.compareTitle')" @click="shoot(true)">
          <Icon name="layers" />{{ t('lab.compare') }}</button>
        <div v-if="formError" class="error">{{ formError }}</div>
      </footer>
    </aside>
    <div class="splitter" role="separator" aria-orientation="vertical" :aria-label="t('lab.splitter')" tabindex="0" :aria-valuenow="F.benchW"
      :title="t('lab.splitterTitle')" @pointerdown.prevent="dragSplit" @dblclick="F.benchW = BENCH_W"
      @keydown.left.prevent="F.benchW = clampW(F.benchW - 24)" @keydown.right.prevent="F.benchW = clampW(F.benchW + 24)" />

    <main ref="monitor" class="monitor" :aria-label="t('lab.monitor')">
      <!-- the rig: what the camera will shoot - its settings on the frame's top edge, the frame in its real proportions,
           the prompt's timeline laid on the scene's length under it -->
      <div class="rig" :style="{ '--r': String(vfRatio) }">
        <div class="readout" role="group" :aria-label="t('lab.shooting')">
          <ModelMenu v-model="F.model" />
          <div class="aspects" role="group" :aria-label="t('lab.frame')">
            <button v-for="a in aspects" :key="a.id" type="button" :class="{ on: a.id === F.aspect }" :aria-pressed="a.id === F.aspect" @click="F.aspect = a.id">
              <span class="box" :style="box(a.ratio)" />{{ a.id === 'frame' ? t('lab.asFrame') : a.id }}</button>
            <HelpQ id="lab" term="Формат" />
          </div>
          <div class="ql-row"><div class="seg" role="group" :aria-label="t('lab.quality')">
            <button v-for="q in cfg.qualities" :key="q.id" type="button" :class="{ on: q.id === F.quality }" :aria-pressed="q.id === F.quality"
              :title="(card && card.id !== 'h3' ? `${card.sizes[q.id]?.w}×${card.sizes[q.id]?.h}, ~${mins(card.per_scene[q.id])}` : `${q.w}×${q.h}, ~${mins(q.per_scene)}`) + ' ' + t('lab.per5')"
              @click="F.quality = q.id">{{ qlName(q.id) || q.id }}</button></div><HelpQ id="lab" term="Качество" /></div>
          <label class="seed-in" :title="t('lab.seedPh')"><span>{{ t('lab.seed') }}</span><input v-model="F.seed" type="number" min="0" :placeholder="t('lab.seedAny')"><HelpQ id="lab" term="Сид" /></label>
          <div class="frame-chip">
            <button v-if="F.frame" type="button" class="fc-pic" :class="{ on: !shown }" :title="t('lab.toFrame')" @click="show(null)"><img :src="F.frame.url" alt="">{{ t('lab.startFrame') }}</button>
            <button v-if="F.frame" type="button" class="fc-off" :title="t('lab.removeFrame')" :aria-label="t('lab.removeFrame')" @click="setFrame(null)"><Icon name="close" :size="16" /></button>
            <label v-else class="fc-add" :title="t('lab.frameTitle')"><input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="pickFrame"><Icon name="image" :size="16" />{{ t('lab.startFrame') }}</label>
            <HelpQ id="lab" term="Стартовый кадр" />
          </div>
        </div>

        <!-- a picture dropped anywhere on the frame becomes the start frame -->
        <div class="vf" :class="{ over, playing: !!shown }" :aria-label="shown ? undefined : t('lab.viewfinder')"
          @dragover.prevent="over = true" @dragleave.self="over = false" @drop.prevent="over = false; uploadFrame($event.dataTransfer?.files[0])">
          <video v-if="shown" :key="shown.file" :src="out(shown.file)" :poster="shown.poster ? out(shown.poster) : undefined" controls playsinline :autoplay="autoplay" />
          <div v-else-if="running" class="shooting"><Icon name="clapper" :size="28" />
            <b>{{ jobStep(running) }}</b>
            <span class="bar big"><i :style="{ width: `${jobPct(running)}%`, background: 'var(--accent)' }" /></span>
            <span>{{ t('lab.firstTake') }}</span></div>
          <template v-else>
            <i class="c tl" /><i class="c tr" /><i class="c bl" /><i class="c br" />
            <span class="vf-size">{{ size[0] }} × {{ size[1] }}</span>
            <template v-if="F.frame">
              <img class="vf-pic" :src="F.frame.url" :alt="t('lab.startFrame')">
              <div class="vf-tools">
                <button class="btn" type="button" :title="t('lab.describeTitle')" @click="describeFrame"><Icon name="spark" />{{ t('lab.describe') }}</button>
                <button class="btn" type="button" @click="setFrame(null)"><Icon name="close" />{{ t('lab.removeFrame') }}</button>
              </div>
            </template>
            <label v-else class="vf-drop"><input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="pickFrame">
              <Icon name="image" :size="28" /><b>{{ t('lab.startFrame') }}</b><span>{{ t('lab.vfHint', { model: mShort }) }}</span>
              <span class="btn">{{ t('lab.chooseFile') }}</span></label>
          </template>
          <div v-if="over" class="vf-over">{{ t('lab.dropHere') }}</div>
        </div>

        <div class="tl">
          <div class="tl-ruler">
            <div class="tl-beats" role="group" :aria-label="t('lab.timeline')">
              <component :is="F.mode === 'text' ? 'button' : 'span'" v-for="(b, i) in beats" :key="i" :type="F.mode === 'text' ? 'button' : undefined" class="tl-beat"
                :class="{ over: b.to > F.seconds + 0.01 }" :style="{ left: `${(b.from / span) * 100}%`, width: `${(Math.max(0.25, b.to - b.from) / span) * 100}%` }"
                :title="b.to > F.seconds + 0.01 ? t('lab.beatOver', { s: num(F.seconds) }) : b.text" @click="goBeat(b)">
                <small>{{ num(b.from) }}–{{ num(b.to) }} {{ t('lab.sec') }}</small>{{ b.text || '…' }}</component>
              <span v-if="!beats.length" class="tl-none">{{ t('lab.noBeats', { model: mShort }) }}
                <button v-if="F.mode === 'text' && !beatsRu" type="button" class="ghost" @click="onPart('time')"><Icon name="plus" :size="14" />{{ t('lab.addBeats') }}</button></span>
              <i v-if="span > F.seconds" class="tl-end" :style="{ left: `${(F.seconds / span) * 100}%` }" />
            </div>
            <div class="tl-ticks" aria-hidden="true"><span v-for="s in ticks" :key="s" :style="{ left: `${(s / span) * 100}%` }">{{ s }}</span></div>
          </div>
          <div class="tl-len">
            <div class="seg five-col" role="group" :aria-label="t('lab.length')">
              <button v-for="l in LENGTHS.filter((x) => x <= (card?.max_seconds || 15))" :key="l" type="button" :class="{ on: l === F.seconds }" :aria-pressed="l === F.seconds" @click="setLen(l)">{{ l }}</button>
              <label class="own" :class="{ on: !LENGTHS.includes(F.seconds) }" :title="t('lab.ownLenTitle')"><input type="number" min="1" max="15" step="0.5"
                :value="LENGTHS.includes(F.seconds) ? '' : F.seconds" :placeholder="t('lab.other')" :aria-label="t('lab.ownLenAria')" @change="ownLen"></label>
            </div>
            <span class="tl-frames">{{ t('lab.lenLine', { s: num(F.seconds), n: frames(F.seconds) }) }}<HelpQ id="lab" term="Длина" /></span>
          </div>
        </div>

        <div v-if="shown" class="take-info">
          <!-- what the take is: the model and the frame in bold, the seed copies with a click, the rest quieter -->
          <div class="take-meta"><b>{{ shown.params.model_name || 'H3' }}</b><b>{{ shown.params.width }}×{{ shown.params.height }}</b><span>{{ t('lab.secsN', { s: secs(shown.params.length || 0) }) }}</span><span>{{ qlName(shown.params.quality) }}</span>
            <span v-if="shown.params.first_frame">{{ t('lab.fromFrame') }}</span><span v-if="loraLine(shown.params)">LoRA: {{ loraLine(shown.params) }}</span>
            <button type="button" class="chip-copy" :class="{ done: copied === 'seed' }" :title="t('lab.copySeed')" @click="copy(String(shown.params.seed), 'seed')">{{ t('lab.seedN', { seed: shown.params.seed }) }}<Icon :name="copied === 'seed' ? 'check' : 'copy'" :size="12" /></button>
            <span class="take-when"><template v-if="shown.seconds">{{ t('lab.shotIn', { t: mins(shown.seconds) }) }} · </template>{{ when(shown) }}</span></div>
          <!-- the prompt as a card: its parts tagged as in the editor, copy and the fold in the head -->
          <div class="take-card" :class="{ open: promptOpen }">
            <div class="take-card-head"><span class="lbl">{{ t('lab.takePrompt') }}</span>
              <button type="button" class="ghost" :class="{ done: copied === 'prompt' }" :title="t('lab.copyPrompt')" @click="copy(shown.params.prompt || '', 'prompt')"><Icon :name="copied === 'prompt' ? 'check' : 'copy'" :size="14" />{{ copied === 'prompt' ? t('lab.copied') : t('lab.copy') }}</button>
              <button v-if="longPrompt" type="button" class="take-prompt-tog" :class="{ open: promptOpen }" :aria-expanded="promptOpen" @click="promptOpen = !promptOpen">{{ promptOpen ? t('lab.hidePrompt') : t('lab.wholePrompt') }}</button></div>
            <pre class="take-prompt hl" :title="promptOpen || !longPrompt ? undefined : t('lab.showPrompt')" @click="!promptOpen && (promptOpen = true)" v-html="markup(shown.params.prompt || '', 'en', formOf(shown.params.model || 'h3') === 'h3' ? undefined : t('lab.tag.whole', { model: modelName(shown.params.model) }))" />
          </div>
          <div class="take-acts">
            <div><button type="button" class="btn lead" :disabled="!shown.poster" :title="t('lab.contTitle')" @click="continueFrom(shown)"><Icon name="link" />{{ t('lab.cont') }}</button>
              <button type="button" class="btn" :title="t('lab.reuseTitle')" @click="reuse(shown.params, false)"><Icon name="retake" />{{ t('lab.reuse') }}</button>
              <button type="button" class="btn" :title="t('lab.reuseSeedTitle')" @click="reuse(shown.params, true)">{{ t('lab.reuseSeed', { seed: shown.params.seed }) }}</button><HelpQ id="lab" term="Под дублем" /></div>
            <div><a class="btn" :href="out(shown.file)" download><Icon name="download" />{{ t('common.download') }}</a>
              <button type="button" class="btn quiet-danger" :title="t('lab.toBin')" @click="del(shown)"><Icon name="trash" />{{ t('common.delete') }}</button></div>
          </div>
        </div>
      </div>

      <!-- nothing shot yet: the presets, the same list as «Заготовка ▾», laid out where there is room -->
      <section v-if="!videos.length && !labJobs.length" class="start-sec">
        <h2>{{ t('lab.emptyTitle') }}</h2>
        <p>{{ t('lab.emptyText') }}</p>
        <div class="start" :aria-label="t('lab.readyPrompts')">
          <section v-for="g in presetGroups" :key="g" class="start-group"><h3>{{ g }}</h3>
            <button v-for="x in presets().filter((y) => y.group === g)" :key="x.id" type="button" class="start-item" @click="usePreset(x)">
              <b>{{ x.name }}</b><small :class="{ warn: x.frame && !F.frame }">{{ x.frame && !F.frame ? t('lab.needFrame') : x.hint }}</small></button>
          </section>
        </div>
      </section>
      <div v-if="groups.length" class="takes-head">
        <h2>{{ t('lab.takes') }} <small>{{ videos.length || '' }}</small><HelpQ id="lab" term="Дубли" /></h2>
        <button class="ghost" type="button" @click="openFolder('outputs')"><Icon name="folder" />{{ t('common.openFolder') }}</button>
      </div>
      <div class="takes">
        <section v-for="g in groups" :key="g.prompt" class="take-group">
          <div class="group-head"><p :title="g.prompt">{{ gist(g.prompt) }}</p><span>{{ takes(g.takes.length + g.jobs.length) }}</span></div>
          <div class="group-grid">
            <div v-for="j in g.jobs" :key="j.id" class="take running" :class="{ queued: j.status === 'queued' }"><Icon name="clapper" :size="20" /><b>{{ jobStep(j) }}</b>
              <span v-if="j.status === 'running'" class="bar big"><i :style="{ width: `${jobPct(j)}%`, background: 'var(--accent)' }" /></span></div>
            <!-- hovering a take plays it without sound (not when the system asks for less motion) -->
            <button v-for="v in g.takes" :key="v.file" type="button" class="take" :class="{ sel: shown && shown.file === v.file }" :aria-label="t('lab.takeAria', { seed: v.params.seed })"
              @click="watchTake(v)" @mouseenter="hovered = still.matches ? null : v.file" @mouseleave="hovered = null">
              <video v-if="hovered === v.file" :src="out(v.file)" muted loop playsinline autoplay />
              <img v-if="v.poster" :src="out(v.poster)" alt="" loading="lazy"><span v-else class="noimg" />
              <span class="take-cap"><b>{{ t('lab.seedN', { seed: v.params.seed }) }}</b><span>{{ takeCap(v) }}</span></span></button>
          </div>
        </section>
      </div>
    </main>

    <div v-if="popOpen" class="lora-pop" role="dialog" :aria-label="t('lab.library')" :style="popPos" @click.stop>
      <div class="lora-pop-head">
        <input ref="searchEl" v-model="search" class="field-in" type="search" :placeholder="t('lab.find')" :aria-label="t('lab.find')">
        <button class="ghost" type="button" :title="t('lab.reread')" :aria-label="t('lab.reread')" @click="loadLoras"><Icon name="retake" /></button>
        <button class="ghost" type="button" :title="t('lab.openLoraFolder')" :aria-label="t('lab.openLoraFolder')" @click="openFolder('loras')"><Icon name="folder" /></button>
      </div>
      <div class="lora-list">
        <button v-for="l in found" :key="l.id" type="button" class="lora-item" :disabled="l.verdict === 'blocked'" :title="loraTitle(l)" @click="addLora(l)">
          <span v-if="l.preview" class="thumb" :style="{ backgroundImage: `url('${l.preview}')` }" /><span class="name">{{ l.name }}</span>
          <span class="kind" :class="l.verdict">{{ kindName(l.kind) }}</span><span class="size">{{ Math.round(l.size_mb) }} {{ t('common.mb') }}</span></button>
        <div v-if="S.loras.length && !found.length" class="none">{{ search.trim() ? t('lab.nothing') : t('lab.allInUse') }}</div>
      </div>
      <div v-if="!lorasFor(F.model).length" class="lora-empty">{{ F.model === 'h3' ? t('lab.emptyH3', { dirs: cfg.lora_dirs.join(` ${t('lab.or')} `) })
        : t('lab.emptyOther', { name: card?.name || F.model }) }}</div>
    </div>
  </div>
</template>
