<script setup lang="ts">
// #/models «Модели и настройки» (phase 6, after Remiqora's Models page): the weights by role, where each lies and where
// it comes from, downloads one at a time, the writer's models, the folders, the tools. The page re-reads the server
// every 10 s (1.5 s while a file downloads), so a file put into a folder by hand shows up by itself.
// Phase 10: LTX 2.5, LTX 2.3 and WAN 2.2 5B are sections like H3's - what the model can do, its speed here, its license,
// its weights by role. 2026-10-28: the nav is a tree of groups (Видео / Фото / Сценарист / Общее), every model's card
// has the same parts - «О модели», «Веса», «Параметры» (settings.NUMBERS), «LoRA» (its own folders and files); Ref2VA
// and the H3 LoRA sit under H3.
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../components/Icon.vue'
import GuideButton from '../components/help/GuideButton.vue'
import { api, post } from '../lib/api'
import { S, banner, keep, loadLlms, loadLoras } from '../lib/store'
import { gb, mins } from '../lib/format'
import { currentLocale } from '../i18n'
import { setTextLang as setTL } from '../lib/textLang'

const { t } = useI18n()
const props = defineProps<{ section?: string }>()
// the tree: [group, [[key, the name (a key of models.sec, or a name as is), icon]]]; Ref2VA is a sub-item of H3
const GROUPS: [string, [string, string, string][]][] = [
  ['video', [['h3', '', 'film'], ['ltx25', 'LTX 2.5', 'clapper'], ['ltx23', 'LTX 2.3', 'music'], ['wan5b', 'WAN 2.2 5B', 'image']]],
  ['photo', [['krea', '', 'brush'], ['flux2', '', 'spark']]],
  ['writer', [['llm', '', 'spark']]],
  ['common', [['tools', '', 'wrench']]],
]
const KEYS = GROUPS.flatMap(([, xs]) => xs.map(([k]) => k)).concat('ref')
const secName = (k: string, name: string) => name || t(`models.sec.${k}`)
// the disk bar: a video model in its own colour (its card), the rest in these
const WEIGHTS = ['h3', 'ltx25', 'ltx23', 'wan5b', 'krea', 'flux2']   // the sections whose weights are slots (Ref2VA's sit on H3's card)
// Krea's LoRA: their kind and whether they fit Krea 2 (app/krea_loras.py)
const KIND: Record<string, string> = { lora: 'LoRA', lokr: 'LoKr', loha: 'LoHa', dora: 'DoRA' }
const kindName = (k: string) => KIND[k] || (k === 'weights' || k === 'unreadable' ? t(`models.kind.${k}`) : k)
// the head's figures: a number to read at a glance, what it is under it
const specs = computed<{ v: string; l: string; n?: string }[]>(() => {
  const c = sec.value?.card
  if (c) return [{ v: `≈ ${mins(c.per_scene)}`, l: t('models.spec.scene', { v: c.size }), n: c.measured ? t('models.byMeasures', { n: c.measured }) : t('models.estimate') },
    { v: String(c.steps), l: t('models.spec.steps') }, { v: t('models.spec.secs', { n: c.max_seconds }), l: t('models.spec.longest') }]
  if (sel.value === 'krea') return [{ v: '8', l: t('models.spec.kreaSteps') }, { v: t('models.spec.kreaPicV'), l: t('models.spec.kreaPic') }]
  if (sel.value === 'flux2') return [{ v: t('models.spec.fluxPicV'), l: t('models.spec.fluxPic') }, { v: t('models.spec.vramV'), l: t('models.spec.vram') }, { v: t('models.spec.upTo3'), l: t('models.spec.fluxRefs') }]
  return []
})
// what a video model can do, as marks; «no sound» is a mark that something is missing
const caps = computed(() => {
  const c = sec.value?.card
  return c ? [{ x: c.sound ? t('models.can.sound') : t('models.can.noSound'), off: !c.sound }, ...['voice', 'refs', 'track'].filter((k) => c[k]).map((k) => ({ x: t(`models.can.${k}`), off: false }))] : []
})
const license = computed(() => sec.value?.card?.license || (sel.value === 'krea' ? 'Krea 2 Community License' : sel.value === 'flux2' ? 'Apache-2.0' : ''))
// the LoRA list draws pictures only when some LoRA has one, a column of empty squares says nothing
const loraPics = computed(() => shownLoras.value.some((l) => l.preview))
const snap = ref<Record<string, any> | null>(null)
// in the desktop app (its window gives the page this): the installer's own sets, official weights only, added from here
const desktop = (window as any).remiqoraVideo as { addSets?: () => Promise<void> } | undefined
const err = ref('')
const askDel = ref<string | null>(null)
// the old «LoRA» and «Ref2VA» sections live inside H3's card now; an old link to them opens H3
const sel = computed(() => (KEYS.includes(props.section || '') && !['lora', 'ref'].includes(props.section!) ? props.section! : 'h3'))
// H3's row counts Ref2VA and the H3 LoRA with it (they are its parts on the card)
const rowGb = (k: string) => { const s = snap.value!.sections; return k === 'h3' ? (s.h3.gb || 0) + (s.ref.gb || 0) + (s.lora.gb || 0) : s[k].gb }
const rowOk = (k: string) => { const s = snap.value!.sections; return k === 'h3' ? s.h3.ok && s.ref.ok : s[k].ok }
const sec = computed(() => snap.value?.sections[sel.value])
const gbs = (v: number | null | undefined) => (v == null ? '—' : `${gb(v)} ${t('common.gb')}`)
// the disk: one bar in three parts - the video models (Ref2VA and the H3 LoRA with them), the picture models, the writer
const GROUP_COLOR: Record<string, string> = { video: 'var(--accent)', photo: '#ec4899', writer: '#1D9E75' }
const share = computed(() => {
  const list = ['video', 'photo', 'writer'].map((g) => ({ g, gb: groupGb(g) })).filter((x) => x.gb > 0)
  const total = list.reduce((a, x) => a + x.gb, 0) || 1
  return list.map((x) => ({ ...x, pct: (100 * x.gb) / total, color: GROUP_COLOR[x.g], name: t(`models.group.${x.g}`) }))
})
// the writer's row is its model, as a video group's rows are models: the default GGUF's name (or «Сценарист» with none)
const llmName = computed(() => { const m = (snap.value?.sections.llm?.models || []).find((x: any) => x.default); return m ? m.name.replace(/-GGUF$|\.gguf$/i, '').replace(/[-.]?(Q\d[\w.]*|IQ\d[\w.]*|f16|bf16|fp8)$/i, '') : t('models.sec.llm') })
const groupGb = (g: string) => { const s = snap.value!.sections; return Object.keys(s).filter((k) => s[k].group === g && s[k].gb).reduce((a, k) => a + s[k].gb, 0) }
const ggufUrl = ref('')
const hfToken = ref('')
// the card's parts: which this section has. 2026-10-28: real tabs, one part shown at a time; what the model is (its facts)
// sits above them, always in sight. The tab last open on each card is kept in this browser.
const TABS = computed(() => {
  const s = sec.value
  if (!s) return []
  return [['weights', WEIGHTS.includes(sel.value) || sel.value === 'llm'], ['ref', sel.value === 'h3'], ['params', !!s.params?.length || sel.value === 'llm'],
    ['lora', sel.value === 'h3' || !!s.loras]].filter(([, on]) => on).map(([k]) => k as string)
})
const TAB_KEY = 'rv.models.tabs'
const lastTab = reactive<Record<string, string>>((() => { try { return JSON.parse(localStorage.getItem(TAB_KEY) || '{}') } catch { return {} } })())
const tab = computed(() => (TABS.value.includes(lastTab[sel.value]) ? lastTab[sel.value] : TABS.value[0]))
function openTab(k: string) {
  lastTab[sel.value] = k
  try { localStorage.setItem(TAB_KEY, JSON.stringify(lastTab)) } catch { /* the tab is just not remembered */ }
}
// ← / → along the tabs, as a tab list does
function tabKey(e: KeyboardEvent) {
  const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
  if (!d) return
  const next = TABS.value[(TABS.value.indexOf(tab.value) + d + TABS.value.length) % TABS.value.length]
  openTab(next)
  ;(e.currentTarget as HTMLElement).querySelector<HTMLElement>(`[data-tab="${next}"]`)?.focus()
}
// what a tab says about itself: a red dot - a file it needs is missing; a number - how many LoRA lie in the folders
const tabMark = (k: string): { bad?: boolean; n?: number } => {
  const s = snap.value!.sections
  if (k === 'weights') return { bad: sel.value === 'llm' ? !sec.value.models?.length : !sec.value.ok }
  if (k === 'ref') return { bad: !s.ref.ok }
  if (k === 'lora') return { n: loraView.value?.loras?.length || 0 }
  return {}
}
// the weight parts of the card: the model's slots; on H3's card Ref2VA's too, with its folder («Держать лицо по фото»)
const slotGroups = computed(() => {
  if (!sec.value || !WEIGHTS.includes(sel.value)) return [] as { id: string; title: string; text: string; path: Record<string, any> | null; slots: any[] }[]
  const out = [{ id: 'weights', title: t('models.tab.weights'), text: '', path: null as Record<string, any> | null, slots: sec.value.slots as any[] }]
  if (sel.value === 'h3') out.push({ id: 'ref', title: 'Ref2VA', text: t('models.refText'), path: snap.value!.ref_tool, slots: snap.value!.sections.ref.slots })
  return out
})
// the LoRA of the model shown: H3's (the old «LoRA» section), Krea's, LTX / WAN / FLUX's - their folders and files
const loraView = computed(() => {
  const s = sec.value
  if (!s) return null
  if (sel.value === 'h3') return { key: 'LORA_DIRS', dirs: snap.value!.sections.lora.dirs, loras: snap.value!.sections.lora.loras || [], label: t('models.loraDirs') }
  if (sel.value === 'krea') return { key: 'KREA_LORA_DIRS', dirs: s.loras.dirs, loras: s.loras.loras, label: t('models.kreaDirs') }
  if (s.loras && s.loras.key) return { key: s.loras.key, dirs: s.loras.dirs, loras: s.loras.loras, label: t('models.loraDirsFor', { name: s.title }) }
  return null
})

async function load() { try { snap.value = await api('/api/models'); err.value = '' } catch (e) { err.value = (e as Error).message } }
async function call(path: string, body?: unknown) {
  try { snap.value = await post(path, body || {}); err.value = '' } catch (e) { err.value = (e as Error).message }
}
const setting = (values: Record<string, unknown>) => call('/api/models/settings', { values })
const open = (path: string) => post('/api/models/open', { path }).catch((e) => banner(e.message))
async function pickPath(kind: string, start?: string) {
  try { return (await post('/api/models/pick', { kind: kind === 'folder' ? 'folder' : 'file', start })).path as string | null }
  catch (e) { banner((e as Error).message); return null }
}
const lines = (v: string) => v.split('\n').map((x) => x.trim()).filter(Boolean)
async function addFolder(key: string, list: string[]) {
  const got = await pickPath('folder', list[list.length - 1])
  if (got && !list.some((x) => x.toLowerCase() === got.toLowerCase())) setting({ [key]: [...list, got] })
}
async function pick(t: Record<string, any>) {
  const got = await pickPath(t.kind, t.path)
  if (got) setting({ [t.key]: got })
}
async function engFree() {
  try { await post('/api/engine/free') } catch (e) { banner((e as Error).message) }
  await load()
}
// the writer's model: the default for every job, and the one this page uses now (the header has no picker any more)
const llmDefault = (name: string) => setting({ LLM_MODEL: name }).then(loadLlms).then(() => { if (S.llms?.default) { S.llm = S.llms.default; keep() } })
const val = (e: Event) => (e.target as HTMLInputElement).value
// a parameter typed: within its bounds, saved on change
function setParam(p: Record<string, any>, v: string) {
  const x = Number(v)
  if (!Number.isFinite(x)) return
  setting({ [p.key]: Math.min(p.max, Math.max(p.min, x)) })
}
const fmt = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(2))
// a LoRA's own strength (app/lora_prefs.py): the one it takes when added to a scene or a node; moved - shown at once,
// let go - saved. A model's spare files fold away under «Другие файлы»; a missing file shows them all.
const draft = reactive<Record<string, number>>({})
const strengthOf = (l: Record<string, any>) => draft[l.id] ?? l.strength ?? 0.8
async function saveStrength(l: Record<string, any>, v: number | null) {
  if (v != null && !Number.isFinite(v)) return
  await call('/api/loras/strength', { id: l.id, model: sel.value, strength: v == null ? null : Math.min(5, Math.max(-5, v)) })
  delete draft[l.id]
  loadLoras()
}
const loraFind = ref('')
const shownLoras = computed(() => {
  const q = loraFind.value.trim().toLowerCase(), all = (loraView.value?.loras || []) as Record<string, any>[]
  return q ? all.filter((l) => `${l.name} ${l.folder} ${l.trigger}`.toLowerCase().includes(q)) : all
})
watch(sel, () => { loraFind.value = '' })
const spareOpen = reactive<Record<string, boolean>>({})
const mainFiles = (slot: Record<string, any>) => (slot.ok ? slot.files.filter((f: any) => f.selected || row(f).running) : slot.files)
const spareFiles = (slot: Record<string, any>) => (slot.ok ? slot.files.filter((f: any) => !f.selected && !row(f).running) : [])

// a path or a folder list being typed: the 10 s re-read must not wipe it
const page = ref<HTMLElement | null>(null)
const typing = () => { const a = document.activeElement as HTMLInputElement | null; return !!(a && page.value?.contains(a) && /^(INPUT|TEXTAREA)$/.test(a.tagName) && a.type !== 'radio') }
let timer: ReturnType<typeof setTimeout> | undefined
function schedule() {
  clearTimeout(timer)
  timer = setTimeout(async () => { if (!typing()) await load(); schedule() }, snap.value?.downloading ? 1500 : 10000)
}
watch(() => !!snap.value?.downloading, schedule)
// the texts' language (app/i18n.py): ideas, scene texts, the translator's both ways
const textLang = ref<{ text: string; langs: { code: string; name: string; en?: string }[] } | null>(null)
async function loadLang() { try { textLang.value = await api('/api/lang') } catch { /* the page works without it */ } }
async function setTextLang(code: string) {
  try { textLang.value = await api('/api/lang', { method: 'PUT', body: { text: code } }); setTL(code); banner(t('textlang.saved', { v: textLang.value!.langs.find((x) => x.code === code)?.name || code }), 'info') }
  catch (e) { banner((e as Error).message) }
}
onMounted(async () => { loadLang(); await load(); schedule() })
onUnmounted(() => clearTimeout(timer))

// one weight file: what it is, where it lies or would go, where it comes from
function row(f: Record<string, any>) {
  const d = f.download, running = d && d.status === 'running'
  return { d, running, busy: !!snap.value!.downloading && !running, pct: running && d.total ? Math.floor((100 * d.done) / d.total) : 0,
    again: f.partial || (d && (d.status === 'failed' || d.status === 'cancelled')) }
}
</script>

<template>
  <div class="screen"><main ref="page" class="main models-page">
    <p v-if="!snap && !err" class="muted">{{ t('models.checking') }}</p>
    <div v-else-if="!snap" class="warn-line"><Icon name="warn" :size="14" />{{ err || t('models.readFailed') }}</div>
    <template v-else>
      <div class="models-head"><div><div class="title-row"><h1>{{ t('models.title') }}</h1><GuideButton guide="models" /></div>
          <p class="muted">{{ t('models.intro') }}</p>
          <button v-if="desktop?.addSets" type="button" class="btn" :title="t('models.addSetsTitle')" @click="desktop.addSets()"><Icon name="download" :size="14" />{{ t('models.addSets') }}</button></div>
        <div class="disk"><b>{{ gbs(snap.gb) }}</b><span class="lbl">{{ t('models.onDisk') }}</span>
          <span class="bar big"><i v-for="x in share" :key="x.g" :style="{ width: `${x.pct}%`, background: x.color }" :title="`${x.name}: ${gbs(x.gb)}`" /></span>
          <ul class="legend"><li v-for="x in share" :key="x.g"><i :style="{ background: x.color }" />{{ x.name }} <b>{{ gbs(x.gb) }}</b></li></ul></div></div>
      <div v-if="err" class="warn-line" role="alert"><Icon name="warn" :size="14" />{{ err }}</div>
      <div class="models-grid">
        <nav class="m-nav" :aria-label="t('models.sections')">
          <!-- a group of one model is that model's row (the writer, the tools); a group of several gets a quiet title with its size -->
          <template v-for="[g, items] in GROUPS" :key="g">
            <div v-if="g !== 'common'" class="m-group"><span>{{ t(`models.group.${g}`) }}</span><small>{{ groupGb(g) ? gbs(groupGb(g)) : '' }}</small></div>
            <hr v-else class="m-rule">
            <template v-for="[k, nm] in items" :key="k">
              <router-link :to="`/models/${k}`" :class="{ on: k === sel, plain: g === 'common' }">
                <span>{{ k === 'llm' ? llmName : secName(k, nm) }}<small v-if="k === 'krea' || k === 'flux2'" class="sub-t">{{ t(`models.sub.${k}`) }}</small></span>
                <small class="m-size" :class="{ bad: !rowOk(k) }" :title="rowOk(k) ? t('models.allThere') : t('models.missing')">{{ rowOk(k) ? (rowGb(k) ? gbs(rowGb(k)) : '') : t('models.noFiles') }}</small></router-link>
            </template>
          </template>
        </nav>
        <section class="m-card">
          <!-- the head: the model, its state, what it is for -->
          <template v-if="sel === 'h3'">
            <div class="m-title"><h2>{{ t('models.sec.h3') }}</h2><span class="pill-state" :class="{ on: snap.engine.state === 'ready' }">{{ snap.engine.state === 'ready' ? t('models.inMemory') : snap.engine.state === 'starting' ? t('models.starting') : t('models.unloaded') }}</span>
              <button v-if="snap.engine.state === 'ready'" type="button" class="btn" :title="t('models.unloadTitle')" @click="engFree">{{ t('models.unload') }}</button></div>
            <p class="muted">{{ snap.engine.own ? t('models.ownEngine') : t('models.desktopEngine') }}</p>
          </template>
          <template v-else-if="sec.card">
            <div class="m-title"><h2>{{ sec.title }}</h2><span class="pill-state" :class="{ on: snap.engine.state === 'ready' }">{{ snap.engine.state === 'ready' ? t('models.workerOn') : t('models.unloaded') }}</span>
              <button v-if="snap.engine.state === 'ready'" type="button" class="btn" :title="t('models.unloadTitle1')" @click="engFree">{{ t('models.unload') }}</button></div>
            <p class="muted">{{ sec.card.text }} {{ t('models.sameWorker') }}</p>
          </template>
          <template v-else-if="sel === 'krea'">
            <div class="m-title"><h2>{{ t('models.sec.krea') }}</h2><span class="pill-state" :class="{ on: snap.engine.state === 'ready' }">{{ snap.engine.state === 'ready' ? t('models.workerOn') : t('models.unloaded') }}</span></div>
            <p class="muted">{{ t('models.kreaText') }}</p>
            <div v-if="sec.problem" class="warn-line"><Icon name="warn" :size="14" />{{ sec.problem }}</div>
          </template>
          <template v-else-if="sel === 'flux2'">
            <div class="m-title"><h2>{{ t('models.sec.flux2') }}</h2><span class="pill-state" :class="{ on: snap.engine.state === 'ready' }">{{ snap.engine.state === 'ready' ? t('models.workerOn') : t('models.unloaded') }}</span></div>
            <p class="muted">{{ t('models.fluxText') }}</p>
            <div v-if="sec.problem" class="warn-line"><Icon name="warn" :size="14" />{{ sec.problem }}</div>
          </template>
          <template v-else-if="sel === 'llm'">
            <div class="m-title"><h2>{{ t('models.sec.llm') }}</h2><span v-if="!sec.server_ok" class="warn-line"><Icon name="warn" :size="14" />{{ t('models.noServer', { v: sec.server }) }}</span></div>
            <p class="muted">{{ t('models.llmText') }}</p>
          </template>
          <template v-else-if="sel === 'tools'">
            <div class="m-title"><h2>{{ t('models.sec.tools') }}</h2></div>
            <p class="muted">{{ t('models.toolsText') }}</p>
          </template>
          <!-- what the model is: always in sight, above the tabs -->
          <dl v-if="specs.length" class="m-specs">
            <div v-for="s in specs" :key="s.l"><dt>{{ s.l }}<small v-if="s.n">{{ s.n }}</small></dt><dd>{{ s.v }}</dd></div>
          </dl>
          <ul v-if="caps.length" class="m-caps" :aria-label="t('models.canDo')">
            <li v-for="c in caps" :key="c.x" :class="{ off: c.off }">{{ c.x }}</li>
          </ul>
          <p v-if="license" class="m-lic"><span>{{ t('models.license') }}</span>{{ license }}</p>

          <div v-if="TABS.length > 1" class="m-tabs" role="tablist" :aria-label="t('models.parts')" @keydown="tabKey">
            <button v-for="k in TABS" :key="k" type="button" role="tab" :data-tab="k" :aria-selected="k === tab" :tabindex="k === tab ? 0 : -1"
              :class="{ on: k === tab }" @click="openTab(k)">{{ t(`models.tab.${k}`) }}
              <i v-if="tabMark(k).bad" class="m-dot bad" :title="t('models.missing')" /><small v-else-if="tabMark(k).n">{{ tabMark(k).n }}</small></button>
          </div>

          <!-- a path row: every tool -->
          <div v-for="tl in (sel === 'tools' ? sec.tools : [])" :key="tl.key" class="w-row path-row">
            <div class="w-main"><b><i class="m-dot" :class="tl.ok ? 'ok' : 'bad'" :title="tl.ok ? t('models.found') : t('models.notFound')" /> {{ tl.name }}</b>
              <span class="w-meta">{{ tl.text }}{{ tl.ok ? '' : ' · ' + t('models.notFound') }}</span>
              <input class="field-in mono" :value="tl.path" spellcheck="false" :aria-label="t('models.pathAria', { name: tl.name })" @change="setting({ [tl.key]: val($event) })">
              <span v-if="tl.own" class="w-meta">{{ t('models.ownHere', { v: tl.default }) }}</span></div>
            <div class="w-acts"><button type="button" class="btn" @click="pick(tl)">{{ t('models.choose') }}</button>
              <button v-if="tl.own" type="button" class="ghost" :title="t('models.asEnvTitle')" @click="setting({ [tl.key]: '' })">{{ t('models.asEnv') }}</button>
              <button v-if="!(tl.kind === 'command' && !/[\\/]/.test(tl.path))" type="button" class="ghost" :title="t('common.openFolder')" :aria-label="t('common.openFolder')" @click="open(tl.path)"><Icon name="folder" /></button></div></div>

          <!-- Веса / Ref2VA: the weights by role; the file in use first, the spare ones folded away -->
          <div v-for="sg in slotGroups.filter((g) => g.id === tab)" :key="sg.id" class="m-sec" role="tabpanel">
          <p v-if="sg.text" class="muted">{{ sg.text }}</p>
          <div v-if="sg.path" class="w-row path-row">
            <div class="w-main"><b><i class="m-dot" :class="sg.path.ok ? 'ok' : 'bad'" /> {{ sg.path.name }}</b><span class="w-meta">{{ sg.path.text }}{{ sg.path.ok ? '' : ' · ' + t('models.notFound') }}</span>
              <input class="field-in mono" :value="sg.path.path" spellcheck="false" :aria-label="t('models.pathAria', { name: sg.path.name })" @change="setting({ [sg.path.key]: val($event) })">
              <span v-if="sg.path.own" class="w-meta">{{ t('models.ownHere', { v: sg.path.default }) }}</span></div>
            <div class="w-acts"><button type="button" class="btn" @click="pick(sg.path)">{{ t('models.choose') }}</button>
              <button v-if="sg.path.own" type="button" class="ghost" :title="t('models.asEnvTitle')" @click="setting({ [sg.path.key]: '' })">{{ t('models.asEnv') }}</button>
              <button type="button" class="ghost" :title="t('common.openFolder')" :aria-label="t('common.openFolder')" @click="open(sg.path.path)"><Icon name="folder" /></button></div></div>
          <div v-for="slot in sg.slots" :key="slot.key" class="slot">
            <div class="slot-head"><i class="m-dot" :class="slot.ok ? 'ok' : 'bad'" /><b>{{ slot.title }}</b><span class="muted slot-text">{{ slot.ok ? slot.text : t('models.fileMissing') }}</span></div>
            <p v-if="!slot.ok" class="muted">{{ slot.text }}</p>
            <template v-for="f in [...mainFiles(slot), ...(spareOpen[slot.key] ? spareFiles(slot) : [])]" :key="f.name + f.folder">
            <div class="w-row" :class="{ sel: f.selected, spare: !f.selected && slot.ok }">
              <div class="w-main"><b>{{ f.name }}</b>
                <span class="w-meta">{{ gbs(f.gb) }} · {{ f.installed ? f.folder : t('models.willGoTo', { f: f.folder }) }}
                  <template v-if="f.repo"> · <a :href="f.url" target="_blank" rel="noopener">{{ f.repo }}</a></template><template v-else> · {{ t('models.ownFile') }}</template></span>
                <template v-if="row(f).running"><span class="bar big"><i :style="{ width: `${row(f).pct}%` }" /></span>
                  <span class="w-meta">{{ t('models.ofGb', { a: gb(row(f).d.done / 2 ** 30), b: row(f).d.total ? gb(row(f).d.total / 2 ** 30) : '?' }) }}, {{ row(f).pct }}%{{ row(f).d.speed ? ' · ' + t('models.mbs', { v: gb(row(f).d.speed / 2 ** 20) }) : '' }}</span></template>
                <span v-if="!row(f).running && f.partial" class="w-meta">{{ t('models.stopped', { v: gb(f.partial / 2 ** 30) }) }}</span>
                <span v-if="row(f).d && row(f).d.status === 'failed'" class="warn-line"><Icon name="warn" :size="14" />{{ row(f).d.error || t('models.failed') }}</span></div>
              <div class="w-acts">
                <template v-if="f.installed">
                  <span v-if="f.selected" class="badge accent">{{ t('models.inUse') }}</span>
                  <template v-else><button type="button" class="btn" @click="setting({ [slot.key]: f.name })">{{ t('models.use') }}</button>
                    <template v-if="askDel === f.path"><span class="m-ask">{{ t('models.askDel', { v: gbs(f.gb) }) }}</span>
                      <button type="button" class="btn danger" @click="askDel = null; call('/api/models/delete', { path: f.path })">{{ t('models.remove') }}</button><button type="button" class="btn" @click="askDel = null">{{ t('models.keep') }}</button></template>
                    <button v-else type="button" class="ghost" :title="t('models.toBin')" @click="askDel = f.path"><Icon name="trash" /></button></template>
                </template>
                <button v-else-if="row(f).running" type="button" class="btn" @click="call('/api/models/download/cancel')">{{ t('common.stop') }}</button>
                <button v-else-if="f.repo" type="button" class="btn" :disabled="row(f).busy" :title="row(f).busy ? t('models.oneAtATime') : undefined"
                  @click="call('/api/models/download', { repo: f.repo, path: f.src, slot: slot.key }).then(schedule)">{{ row(f).again ? t('models.resume') : t('common.download') }}</button>
                <button type="button" class="ghost" :title="t('common.openFolder')" :aria-label="t('common.openFolder')" @click="open(f.installed ? f.path : f.folder)"><Icon name="folder" /></button></div></div>
            </template>
            <button v-if="spareFiles(slot).length" type="button" class="m-more" :aria-expanded="!!spareOpen[slot.key]" @click="spareOpen[slot.key] = !spareOpen[slot.key]">
              <Icon :name="spareOpen[slot.key] ? 'minus' : 'plus'" :size="14" />{{ spareOpen[slot.key] ? t('models.spareHide') : t('models.spare', { n: spareFiles(slot).length }) }}</button>
          </div>
          <!-- H3's weight roots and the Hugging Face token live with its weights -->
          <details v-if="sg.id === 'weights' && sel === 'h3'" class="m-fold">
            <summary>{{ t('models.whereFrom') }}</summary>
            <label class="stack"><span class="lbl">{{ t('models.rootsLbl') }} <small>{{ t('models.onePerLine') }}</small></span>
              <textarea class="field-in mono" :rows="Math.max(2, snap.roots.length + 1)" spellcheck="false" :value="snap.roots.join('\n')" @change="setting({ H3_MODEL_ROOTS: lines(val($event)) })" /></label>
            <div class="row-inline"><button type="button" class="btn" @click="addFolder('H3_MODEL_ROOTS', snap.roots)">{{ t('models.addFolder') }}</button></div>
            <div class="stack token"><span class="lbl">{{ t('models.token') }} <small>{{ t('models.tokenSub') }}</small></span>
              <div class="row-inline"><input v-model="hfToken" class="field-in" type="password" :placeholder="snap.token ? t('models.tokenSaved') : 'hf_…'" autocomplete="off">
                <button type="button" class="btn" @click="call('/api/models/token', { token: hfToken || null })">{{ t('common.save') }}</button>
                <button v-if="snap.token" type="button" class="ghost" @click="call('/api/models/token', { token: null })">{{ t('models.remove') }}</button></div></div>
          </details>
          </div>

          <!-- Сценарист: its models are its weights, its context and the texts' language its parameters -->
          <template v-if="sel === 'llm'">
            <div v-if="tab === 'weights'" class="m-sec" role="tabpanel">
              <label v-for="m in sec.models" :key="m.name" class="w-row" :class="{ sel: m.default }"><span class="w-main"><b>{{ m.name.replace(/-GGUF$|\.gguf$/i, '') }}</b>
                  <span class="w-meta">{{ gbs(m.gb) }} · {{ m.source }}<template v-if="m.vision"> · <span class="llm-tag ok">{{ t('models.seesPhotos') }}</span></template></span></span>
                <span class="w-acts"><input type="radio" name="llmDefault" :checked="m.default" :aria-label="t('models.byDefault')" @change="llmDefault(m.name)"></span></label>
              <div class="stack"><span class="lbl">{{ t('models.ggufLbl') }} <small>{{ t('models.into', { v: sec.dest || '' }) }}</small></span>
                <div class="row-inline"><input v-model="ggufUrl" class="field-in" :placeholder="t('models.ggufPh')">
                  <button type="button" class="btn" :disabled="!!snap.downloading" @click="call('/api/models/download-url', { url: ggufUrl }).then(schedule)">{{ t('common.download') }}</button></div>
                <span v-if="snap.downloading && snap.downloading.folder === sec.dest" class="w-meta">{{ snap.downloading.name }}: {{ t('models.ofGb', { a: gb(snap.downloading.done / 2 ** 30), b: snap.downloading.total ? gb(snap.downloading.total / 2 ** 30) : '?' }) }}</span></div>
              <details class="m-fold">
                <summary>{{ t('models.llmDirs') }} · {{ sec.dirs.length }}</summary>
                <label class="stack"><span class="lbl">{{ t('models.onePerLine') }}</span>
                  <textarea class="field-in mono" :rows="Math.max(2, sec.dirs.length + 1)" spellcheck="false" :value="sec.dirs.join('\n')" @change="setting({ LLM_DIRS: lines(val($event)) })" /></label>
                <div class="row-inline"><button type="button" class="btn" @click="addFolder('LLM_DIRS', sec.dirs)">{{ t('models.addFolder') }}</button></div>
              </details>
            </div>
            <div v-if="tab === 'params'" class="m-sec" role="tabpanel">
              <div class="row2"><label class="stack"><span class="lbl">{{ t('models.context') }}</span><select class="field-in" :value="sec.ctx" @change="setting({ LLM_CTX: +val($event) })">
                <option v-for="c in sec.contexts" :key="c" :value="c">{{ t('models.tokens', { n: c.toLocaleString(currentLocale() === 'ru' ? 'ru-RU' : 'en-US') }) }}</option></select></label>
                <label v-if="textLang" class="stack"><span class="lbl">{{ t('textlang.label') }}</span><select class="field-in" :value="textLang.text" @change="setTextLang(val($event))">
                  <option v-for="l in textLang.langs" :key="l.code" :value="l.code">{{ currentLocale() === 'en' ? l.en || l.name : l.name }}</option></select></label></div>
              <p class="muted small">{{ t('textlang.hint') }}</p>
            </div>
          </template>

          <!-- Параметры: a model's numbers (settings.NUMBERS), saved at once -->
          <div v-if="tab === 'params' && sec.params && sec.params.length" class="m-sec" role="tabpanel">
            <p class="muted">{{ t('models.paramsText') }}</p>
            <div class="m-params">
              <label v-for="p in sec.params" :key="p.key"><span class="lbl">{{ p.title }}</span>
                <span class="row-inline"><input class="field-in" type="number" :min="p.min" :max="p.max" :step="p.step" :value="p.value" @change="setParam(p, val($event))">
                  <button v-if="p.own" type="button" class="ghost" :title="t('models.paramDefault', { v: fmt(p.default) })" @click="setting({ [p.key]: '' })">{{ t('models.reset') }}</button></span>
                <span class="muted small p-text">{{ p.text }}</span></label>
            </div>
          </div>

          <!-- LoRA: what lies in the model's folders, each with the strength it takes when added; the folders folded below -->
          <div v-if="tab === 'lora' && loraView" class="m-sec" role="tabpanel">
            <input v-if="loraView.loras.length > 6" v-model="loraFind" class="field-in" type="search" :placeholder="t('models.loraFind', { n: loraView.loras.length })" :aria-label="t('models.loraFind', { n: loraView.loras.length })">
            <ul v-if="shownLoras.length" class="lo-list" :class="{ 'no-pic': !loraPics }">
              <li class="lo-head" aria-hidden="true"><span>{{ t('models.loraCol') }}</span><span :title="t('models.strengthText')">{{ t('models.strengthCol') }}</span></li>
              <li v-for="l in shownLoras" :key="l.id" class="lo-row" :class="{ bad: l.verdict === 'blocked' }">
                <template v-if="loraPics"><img v-if="l.preview" class="kl-pic" :src="l.preview" alt="" loading="lazy"><span v-else class="kl-pic" /></template>
                <span class="w-main"><b class="lo-name">{{ l.name }}</b>
                  <span class="lo-meta"><span v-if="l.kind !== 'lora'" class="badge" :class="l.verdict === 'ok' ? 'ok' : l.verdict === 'warn' ? 'warn' : 'bad'">{{ kindName(l.kind) }}</span>
                    <span>{{ l.size_mb }} {{ t('common.mb') }}</span><span v-if="l.rank">{{ t('models.rank', { v: l.rank }) }}</span><span v-if="l.folder">{{ l.folder }}</span>
                    <span v-if="l.trigger" class="lo-trig">{{ t('models.trigger', { v: l.trigger }) }}</span></span>
                  <span v-if="l.note" class="lo-note" :class="{ warn: l.verdict !== 'ok' }"><Icon v-if="l.verdict !== 'ok'" name="warn" :size="14" />{{ l.note }}</span></span>
                <span v-if="l.verdict !== 'blocked' && !l.v2v" class="lo-str" :class="{ own: l.own }">
                  <input type="range" min="0" max="1.5" step="0.05" :value="strengthOf(l)" :aria-label="t('models.strengthAria', { name: l.name })"
                    @input="draft[l.id] = +val($event)" @change="saveStrength(l, +val($event))">
                  <input class="field-in lo-num" type="number" min="-5" max="5" step="0.05" :value="+strengthOf(l).toFixed(2)" :aria-label="t('models.strengthAria', { name: l.name })"
                    @change="saveStrength(l, +val($event))">
                  <button type="button" class="ghost lo-reset" :style="{ visibility: l.own ? 'visible' : 'hidden' }" :title="t('models.strengthReset')" :aria-label="t('models.strengthReset')"
                    @click="saveStrength(l, null)"><Icon name="reset" :size="14" /></button></span>
                <span v-else-if="l.v2v" class="lo-str lo-v2v">{{ t('models.v2vLora') }}</span></li>
            </ul>
            <p v-else-if="loraView.loras.length" class="muted">{{ t('models.loraNone', { v: loraFind }) }}</p>
            <p v-else class="muted">{{ t('models.loraEmpty', { name: sel === 'krea' ? 'Krea' : sec.title }) }}</p>
            <details class="m-fold" :open="!loraView.loras.length">
              <summary>{{ loraView.label }} · {{ loraView.dirs.length }}</summary>
              <p class="muted">{{ sel === 'h3' ? t('models.loraText') : t('models.loraPut') }}</p>
              <div v-for="d in loraView.dirs" :key="d.dir" class="w-row"><span class="w-main"><b>{{ d.dir }}</b><span class="w-meta">{{ d.exists ? t('models.filesGb', { n: d.count, v: gbs(d.gb) }) : t('models.noFolder') }}</span></span>
                <span class="w-acts"><button type="button" class="ghost" @click="open(d.dir)">{{ t('common.open') }}</button></span></div>
              <label class="stack"><span class="lbl">{{ t('models.onePerLine') }}</span>
                <textarea class="field-in mono" :rows="Math.max(2, loraView.dirs.length + 1)" spellcheck="false" :value="loraView.dirs.map((d: any) => d.dir).join('\n')" @change="setting({ [loraView!.key]: lines(val($event)) })" /></label>
              <div class="row-inline"><button type="button" class="btn" @click="addFolder(loraView!.key, loraView!.dirs.map((d: any) => d.dir))">{{ t('models.addFolder') }}</button></div>
            </details>
          </div>
        </section>
      </div>
    </template>
  </main></div>
</template>
