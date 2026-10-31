<script setup lang="ts">
// The home's shelf of videos: found by name and narrowed by what they are - kind (storyboard, clip, graph), the models
// that shot them, the frame, the state - each choice with how many videos it would leave; sorted by when they changed,
// were made, by length or by name. The choices are kept for the next visit. A card shows its frame as it is (a
// vertical video stays vertical, on its own blurred frame) and, under it, a ribbon in the colours of the models that
// shot it, each as long as its share of the scenes.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import { api } from '../lib/api'
import { S, banner, live, loadProjects, modelColor, modelName } from '../lib/store'
import { mmss, when } from '../lib/format'

const { t } = useI18n()

type P = Record<string, any>
type Kind = 'all' | 'board' | 'clip' | 'graph'
type State = '' | 'ready' | 'unshot' | 'check' | 'draft' | 'busy'
const KEY = 'h3studio.shelf.v1'
const saved = (() => { try { return JSON.parse(localStorage.getItem(KEY) || '{}') } catch { return {} } })()
const kind = ref<Kind>(saved.kind || 'all')
const models = ref<string[]>(Array.isArray(saved.models) ? saved.models : [])
const aspect = ref<string>(saved.aspect || '')
const state = ref<State>(saved.state || '')
const sort = ref<string>(saved.sort || 'updated')
const q = ref('')
const open = ref(false)   // the filters on a phone
watch([kind, models, aspect, state, sort], () => {
  try { localStorage.setItem(KEY, JSON.stringify({ kind: kind.value, models: models.value, aspect: aspect.value, state: state.value, sort: sort.value })) } catch { /* private window */ }
}, { deep: true })

// the work going on now: a project's running or queued jobs, the most telling first (the writer, then the shooting).
// Read through a key that changes only when that work does, so a jobs poll that changes nothing here redraws nothing.
const WORK: Record<string, string> = { write: 'writing', rewrite: 'writing', render: 'shooting', take: 'shooting',
  graph: 'building', 'graph-llm': 'writing' }
const workKey = computed(() => S.jobs.filter((j) => live(j) && j.params?.project).map((j) => `${j.params!.project}\t${j.kind}`).sort().join('\n'))
const working = computed(() => {
  const m = new Map<string, string>(), rank = Object.keys(WORK)
  for (const line of workKey.value ? workKey.value.split('\n') : []) {
    const [pid, k] = line.split('\t'), was = m.get(pid)
    if (was === undefined || (rank.indexOf(k) + 1 || 99) < (rank.indexOf(was) + 1 || 99)) m.set(pid, k)
  }
  return m
})

// what a video is, worked out once per change of the list (or the model cards): the filters, the card and the counts
// all read this. Its state is this plus the work going on.
const KIND_NAME = ['board', 'manual', 'clip', 'graph']
const kindName = (k: string) => t(`shelf.kind.${KIND_NAME.includes(k) ? k : 'board'}`)
interface Fact { kind: Kind; models: string[]; aspect: string; state: State; ribbon: { id: string; pct: number; name: string; n: number }[]; line: string; title: string }
const facts = computed(() => new Map(S.projects.map((p): [string, Fact] => {
  const ms: P[] = p.models || []
  const total = ms.reduce((a, m) => a + (m.n || 0), 0)
  const ribbon = ms.map((m) => ({ id: m.id, pct: total ? (100 * m.n) / total : 100 / ms.length, name: modelName(m.id), n: m.n }))
  return [p.id, {
    kind: p.kind === 'graph' || p.kind === 'clip' ? p.kind : 'board', models: ms.map((m) => m.id), aspect: p.aspect || '16:9',
    state: p.video ? 'ready' : p.kind !== 'graph' && !p.written ? 'draft' : p.checks ? 'check' : 'unshot',
    ribbon, line: ribbon.map((r) => r.name).join(' + '),
    title: ribbon.map((r) => `${r.name}: ${t('shelf.scenesN', r.n)}`).join(', '),
  }]
})))
const fact = (p: P) => facts.value.get(p.id)!
const stateOf = (p: P): State => (working.value.has(p.id) ? 'busy' : fact(p).state)
const STATES: State[] = ['ready', 'unshot', 'check', 'draft', 'busy']
// the card's badge: its state in a word (a graph not yet put together says so)
function badge(p: P) {
  switch (stateOf(p)) {
    case 'busy': { const w = WORK[working.value.get(p.id)!]; return { cls: 'accent', text: w ? t(`shelf.work.${w}`) : t('shelf.work.busy') } }
    case 'ready': return { cls: '', text: t('shelf.badge.ready') }
    case 'draft': return { cls: 'warn', text: t('shelf.badge.draft') }
    case 'check': return { cls: 'warn', text: t('shelf.badge.check', { n: p.checks }) }
    default: return { cls: '', text: p.kind === 'graph' ? t('shelf.badge.unbuilt') : t('shelf.badge.unshot') }
  }
}

// the filters in one pass: a video shown passes them all; one that fails a single filter still counts for that
// filter's other choices - so each choice says how many it would leave
type Facet = 'kind' | 'models' | 'aspect' | 'state'
const tally = computed(() => {
  const w = q.value.trim().toLowerCase()
  const n: Record<Facet, Record<string, number>> = { kind: {}, models: {}, aspect: {}, state: {} }
  const shown: P[] = []
  for (const p of S.projects) {
    if (w && !(p.name || '').toLowerCase().includes(w)) continue
    const f = fact(p), st = stateOf(p)
    const miss = ([
      ['kind', kind.value === 'all' || f.kind === kind.value], ['models', !models.value.length || f.models.some((m) => models.value.includes(m))],
      ['aspect', !aspect.value || f.aspect === aspect.value], ['state', !state.value || st === state.value],
    ] as [Facet, boolean][]).filter(([, ok]) => !ok).map(([x]) => x)
    if (miss.length > 1) continue
    if (!miss.length) shown.push(p)
    const add = (x: Facet, keys: string[]) => { if (!miss.length || miss[0] === x) for (const k of keys) n[x][k] = (n[x][k] || 0) + 1 }
    add('kind', ['all', f.kind]); add('models', f.models); add('aspect', [f.aspect]); add('state', [st])
  }
  return { n, shown }
})
const kinds = computed(() => (['all', 'board', 'clip', 'graph'] as Kind[])
  .map((k) => ({ k, l: t(`shelf.kinds.${k}`), n: tally.value.n.kind[k] || 0 })))
// the models: the ones the server knows that shoot (an imported Remiqora model counts as its own version), then any other
const modelList = computed(() => {
  const ids = (S.cfg?.video_models || []).filter((m) => !m.imported).map((m) => m.id)
  for (const f of facts.value.values()) for (const m of f.models) if (!ids.includes(m)) ids.push(m)
  return ids.map((id) => ({ id, name: modelName(id), n: tally.value.n.models[id] || 0 })).filter((m) => m.n || models.value.includes(m.id))
})
const toggleModel = (id: string) => { models.value = models.value.includes(id) ? models.value.filter((x) => x !== id) : [...models.value, id] }
const aspects = computed(() => ['16:9', '9:16', '1:1'].map((a) => ({ a, n: tally.value.n.aspect[a] || 0 })))
const states = computed(() => STATES.map((k) => ({ k, l: t(`shelf.state.${k}`), n: tally.value.n.state[k] || 0 })))
const SORTS = computed<[string, string][]>(() => ['updated', 'created', 'long', 'name'].map((k) => [k, t(`shelf.sort.${k}`)]))
const active = computed(() => (kind.value !== 'all' ? 1 : 0) + models.value.length + (aspect.value ? 1 : 0) + (state.value ? 1 : 0))
function reset() { kind.value = 'all'; models.value = []; aspect.value = ''; state.value = ''; q.value = '' }

const BY: Record<string, (a: P, b: P) => number> = {
  updated: (a, b) => (b.updated || 0) - (a.updated || 0), created: (a, b) => (b.created || 0) - (a.created || 0),
  long: (a, b) => (b.seconds || 0) - (a.seconds || 0), name: (a, b) => (a.name || '').localeCompare(b.name || '', 'ru'),
}
const shown = computed(() => [...tally.value.shown].sort(BY[sort.value] || BY.updated))
const vertical = (p: P) => p.aspect === '9:16' || p.aspect === '1:1'

// what deleting takes away, said for what the video is
function goes(p: P) {
  const name = `«${p.name}»`
  if (p.kind === 'graph') return t('shelf.del.graph', { name })
  if (p.source === 'remiqora') return t('shelf.del.remiqora', { name })
  if (p.kind === 'clip') return t('shelf.del.clip', { name })
  return t('shelf.del.video', { name })
}
async function del(p: P) {
  if (!confirm(goes(p))) return
  try { await api(`/api/projects/${p.id}`, { method: 'DELETE' }) } catch (e) { banner((e as Error).message) }
  await loadProjects()
}
</script>

<template>
  <section class="stack shelf">
    <div class="shelf-head">
      <h2>{{ t('shelf.title') }} <span>{{ S.projects.length }}</span></h2>
      <label class="shelf-find"><Icon name="search" :size="16" /><input v-model="q" type="search" :placeholder="t('shelf.find')" :aria-label="t('shelf.findLabel')"></label>
      <button type="button" class="btn shelf-filters-btn" :aria-expanded="open" @click="open = !open"><Icon name="sliders" :size="16" />{{ t('shelf.filters') }}<b v-if="active" class="bh-n">{{ active }}</b></button>
    </div>

    <div class="shelf-bar" :class="{ open }">
      <div class="seg shelf-kind" role="radiogroup" :aria-label="t('shelf.whichShow')">
        <button v-for="x in kinds" :key="x.k" type="button" role="radio" :aria-checked="kind === x.k" :class="{ on: kind === x.k }" :disabled="!x.n && kind !== x.k" @click="kind = x.k">
          {{ x.l }} <small>{{ x.n }}</small></button></div>
      <div class="shelf-models" role="group" :aria-label="t('shelf.models')">
        <button v-for="m in modelList" :key="m.id" type="button" class="mchip" :class="{ on: models.includes(m.id) }" :aria-pressed="models.includes(m.id)"
          :disabled="!m.n && !models.includes(m.id)" :style="{ '--m': modelColor(m.id) }" @click="toggleModel(m.id)">
          <i aria-hidden="true" />{{ m.name }} <small>{{ m.n }}</small></button></div>
      <div class="shelf-selects">
        <label class="sel"><span class="lbl">{{ t('shelf.frame') }}</span><select v-model="aspect"><option value="">{{ t('shelf.anyFrame') }}</option>
          <option v-for="x in aspects" :key="x.a" :value="x.a" :disabled="!x.n && aspect !== x.a">{{ x.a }} · {{ x.n }}</option></select></label>
        <label class="sel"><span class="lbl">{{ t('shelf.stateLbl') }}</span><select v-model="state"><option value="">{{ t('shelf.anyState') }}</option>
          <option v-for="x in states" :key="x.k" :value="x.k" :disabled="!x.n && state !== x.k">{{ x.l }} · {{ x.n }}</option></select></label>
        <label class="sel"><span class="lbl">{{ t('shelf.order') }}</span><select v-model="sort"><option v-for="[k, l] in SORTS" :key="k" :value="k">{{ l }}</option></select></label>
      </div>
    </div>
    <div v-if="active || q.trim()" class="shelf-found"><span>{{ shown.length ? t('shelf.foundOf', { found: t('shelf.videosN', shown.length), all: S.projects.length }) : t('shelf.nothing') }}</span>
      <button type="button" class="link-btn" @click="reset">{{ t('shelf.reset') }}</button></div>

    <div class="reels">
      <router-link v-for="p in shown" :key="p.id" class="reel" :to="p.type === 'graph' ? `/g/${p.id}` : `/p/${p.id}`">
        <div class="pic" :class="{ tall: vertical(p) }">
          <template v-if="p.poster || p.photo">
            <img v-if="vertical(p)" class="pic-bg" :src="p.poster || p.photo" alt="">
            <img class="pic-img" :src="p.poster || p.photo" alt="" :style="p.poster ? 'opacity:1' : ''"></template>
          <span v-else class="pic-ic" aria-hidden="true"><Icon :name="p.kind === 'graph' ? 'layers' : 'film'" :size="34" /></span>
          <span class="badge reel-state" :class="badge(p).cls"><Icon :name="p.kind === 'graph' ? 'layers' : p.kind === 'clip' ? 'music' : 'film'" :size="12" />{{ badge(p).text }}</span>
          <span class="badge len">{{ mmss(p.seconds || 0) }}<template v-if="p.kind !== 'graph' && p.video"> · {{ p.video }}</template><template v-else-if="p.aspect"> · {{ p.aspect }}</template></span>
          <span class="ribbon" :title="fact(p).title">
            <i v-for="r in fact(p).ribbon" :key="r.id" :style="{ width: `${r.pct}%`, background: modelColor(r.id) }" /></span>
        </div>
        <span class="name">{{ p.name }}</span>
        <span class="meta"><span>{{ kindName(p.kind) }}</span><span class="m-name">{{ fact(p).line }}</span><span v-if="p.source === 'remiqora'" :title="t('shelf.fromRemiqoraTitle')">{{ t('shelf.fromRemiqora') }}</span>
          <span>{{ t('shelf.scenesN', p.scenes) }}</span><span>{{ when(sort === 'created' ? p.created : p.updated) }}</span></span>
        <button type="button" class="del" :aria-label="t('shelf.delLabel', { name: p.name })" :title="t('common.delete')" @click.prevent.stop="del(p)"><Icon name="trash" /></button></router-link>
    </div>
    <p v-if="!shown.length" class="shelf-none">{{ t('shelf.none') }} <button type="button" class="link-btn" @click="reset">{{ t('shelf.showAll') }}</button></p>
  </section>
</template>
