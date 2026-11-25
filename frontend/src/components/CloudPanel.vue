<script setup lang="ts">
// «Настройки» → «Где работают модели»: this computer, a server the studio rents itself
// (provider, key, card, models, auto-stop, «Развернуть» with its steps) or the user's own server. /api/cloud (app/cloud).
// The page re-reads it every 3 s while a deploy runs, else every 15 s.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import HelpQ from './HelpQ.vue'
import { api, post } from '../lib/api'
import { banner } from '../lib/store'
import { gb } from '../lib/format'

const { t } = useI18n()
const st = ref<Record<string, any> | null>(null)
const err = ref('')
const gpus = ref<any[] | null>(null)
const sets = ref<Record<string, any>>({})
const price = ref(0.07)
const balance = ref<number | null>(null)
const keyIn = ref('')
const replacing = ref(false)
const gpuId = ref('')
const picked = ref<string[]>(['ltx23'])   // H3 is not preselected: its licence excludes some countries
const h3Ok = ref(false)   // the licence question, as in the installer
const needsH3 = computed(() => want.value.includes('h3') || want.value.includes('ref2va'))
const moreH3 = computed(() => more.value.includes('h3') || more.value.includes('ref2va'))   // sets added later need the same tick
const hfToken = ref('')
const autoStop = ref(15)
const asking = ref<'' | 'deploy' | 'delete' | 'swap' | 'update' | 'move'>('')
const url = ref('')
const token = ref('')
const serverOk = ref('')
const view = ref<'local' | 'cloud' | 'server'>('local')
const STOPS = [5, 15, 30, 60, 0]

const prov = computed(() => (st.value?.providers || []).find((p: any) => p.id === st.value?.provider) || { id: 'runpod', name: 'RunPod', key_url: '', can_grow: true, can_swap: true, stays: true })
// the provider chosen before its key: the catalog and the key's state are that provider's
async function pickProvider(id: string) {
  if (id === st.value?.provider) return
  gpus.value = null
  gpuId.value = ''
  balance.value = null
  await act(() => api('/api/cloud/provider', { method: 'PUT', body: { provider: id } }))
  await loadCatalog()
}
const pod = computed(() => st.value?.pod)
const live = computed(() => st.value?.live || {})
const dep = computed(() => st.value?.deploy || {})
const gpu = computed(() => (gpus.value || []).find((g) => g.id === gpuId.value))
const want = computed(() => [...new Set([...picked.value, 'writer'])])
// the disk as the server sizes it (app/cloud/manager.py disk_gb): the sets with 5 % and 5 GB, up to 10 GB
const diskGb = computed(() => Math.max(20, Math.ceil(((want.value.reduce((a, k) => a + (sets.value[k]?.bytes || 0), 0) / 1e9) * 1.05 + 5) / 10) * 10))
const perMonth = computed(() => (diskGb.value * price.value).toFixed(2))
const money = (v: number) => v.toFixed(2)
const hm = (s: number) => { const m = Math.floor((s || 0) / 60); return m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}` : `${m} ${t('common.min')}` }
const SHOWN_SETS = ['h3', 'writer', 'krea', 'flux2', 'ref2va', 'ltx25', 'ltx23', 'wan']
const deploying = computed(() => !!dep.value.running)
const DSTEPS = ['volume', 'pod', 'boot', 'models', 'engine', 'done']
const stepIdx = computed(() => DSTEPS.indexOf(dep.value.step || ''))
const mdl = computed(() => dep.value.models || live.value.models || {})
// the deploy card: a clock for the timers, how long each step took, what the step now does and how far it is
const now = ref(Date.now())
let tick: ReturnType<typeof setInterval> | undefined
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
function stepTime(i: number): string {
  const times = dep.value.times || {}
  const a = times[DSTEPS[i]]
  if (!a) return ''
  const next = DSTEPS.slice(i + 1).map((s) => times[s]).find((x) => x)
  return mmss(((next ? next * 1000 : deploying.value ? now.value : (dep.value.finished || a) * 1000) - a * 1000) / 1000)
}
const pull = computed(() => dep.value.pull as { done: number; seen: number } | null)
const stepPct = computed<number | null>(() => {
  if (dep.value.step === 'models' && mdl.value.total) return Math.floor((100 * mdl.value.done) / mdl.value.total)
  // every part met is in: docker unpacks the image now - no measure for that, the stripe runs
  if (dep.value.step === 'boot' && pull.value?.seen && pull.value.done < pull.value.seen) return Math.floor((100 * pull.value.done) / pull.value.seen)
  return null   // no measure: the bar runs as a stripe
})
const stepText = computed(() => {
  const s = dep.value.step
  if (s === 'wait') return t('cloud.waitCard', { n: dep.value.tries })
  if (s === 'boot') return !pull.value?.seen ? t('cloud.bootNote') : pull.value.done < pull.value.seen ? t('cloud.pullOf', { a: pull.value.done, b: pull.value.seen }) : t('cloud.unpack')
  if (s === 'models' && mdl.value.total) return t('cloud.modelsOf', { a: gb(mdl.value.done / 2 ** 30), b: gb(mdl.value.total / 2 ** 30) }) + (mdl.value.file ? ` · ${mdl.value.file}` : '')
  return t(`cloud.dstepText.${s || 'volume'}`)
})

async function load() {
  try { st.value = await api('/api/cloud'); err.value = '' } catch (e) { err.value = (e as Error).message }
}
async function loadCatalog() {
  if (!st.value?.has_key) return
  try {
    const [g, s, a] = await Promise.all([api('/api/cloud/gpus'), api('/api/cloud/sets'), api('/api/cloud/account').catch(() => ({ balance: null }))])
    gpus.value = g.gpus
    sets.value = s.sets
    price.value = pod.value?.storage_price || s.storage_price   // Vast: the chosen machine's own disk price
    balance.value = a.balance
    if (!gpuId.value) gpuId.value = (g.gpus.find((x: any) => x.recommended && x.availability !== 'none') || g.gpus.find((x: any) => x.availability !== 'none'))?.id || ''
  } catch (e) { err.value = (e as Error).message }
}
async function act(fn: () => Promise<any>) {
  try { const r = await fn(); if (r && r.mode) st.value = { ...st.value, ...r }; err.value = '' } catch (e) { err.value = (e as Error).message }
  await load()
}
async function setMode(m: 'local' | 'cloud' | 'server') {
  view.value = m
  if (m === 'local' || (m === 'cloud' && pod.value)) await act(() => api('/api/cloud/mode', { method: 'PUT', body: { mode: m } }))
}
async function saveKey() {
  try {
    const r = await api('/api/cloud/key', { method: 'PUT', body: { provider: st.value!.provider, key: keyIn.value } })
    balance.value = r.balance
    keyIn.value = ''
    replacing.value = false
    await load()
    await loadCatalog()
  } catch (e) { err.value = (e as Error).message }
}
const forgetKey = () => act(() => api('/api/cloud/key', { method: 'DELETE' })).then(() => { gpus.value = null })
function toggleSet(k: string) {
  if (k === 'writer') return
  picked.value = picked.value.includes(k) ? picked.value.filter((x) => x !== k) : [...picked.value, k]
}
async function deploy() {
  asking.value = ''
  await act(() => post('/api/cloud/deploy', { gpu_id: gpuId.value, sets: want.value, auto_stop: autoStop.value, hf_token: hfToken.value, accept_h3: h3Ok.value }))
}
const cancelWait = () => act(() => post('/api/cloud/deploy/cancel'))
// «Развернуть в другом дата-центре»: any card free anywhere; the disk and its models are made anew
const moveTo = ref('')
const moveCards = computed(() => (gpus.value || []).filter((g) => g.availability !== 'none'))
const moveGpu = computed(() => moveCards.value.find((g) => g.id === moveTo.value))
async function doMove() {
  asking.value = ''
  await act(() => post('/api/cloud/move', { gpu_id: moveTo.value, hf_token: hfToken.value }))
  moveTo.value = ''
}
async function remove() {
  asking.value = ''
  await act(() => post('/api/cloud/delete'))
}
async function connectServer() {
  serverOk.value = ''
  try {
    await api('/api/cloud/mode', { method: 'PUT', body: { mode: 'server', url: url.value, token: token.value || null } })
    const r = await post('/api/cloud/server/check')
    serverOk.value = t('cloud.serverOk', { v: r.version || '?' })
    token.value = ''
    err.value = ''
  } catch (e) { err.value = (e as Error).message }
  await load()
}
// another card on the same disk: the cards free now in the disk's data center
const swapTo = ref('')
const swapCards = computed(() => (gpus.value || []).filter((g) => g.id !== pod.value?.gpu_id && g.datacenters.some((x: any) => x.id === pod.value?.datacenter)))
const swapGpu = computed(() => swapCards.value.find((g) => g.id === swapTo.value))
async function doSwap() {
  asking.value = ''
  await act(() => post('/api/cloud/gpu', { gpu_id: swapTo.value }))
  swapTo.value = ''
}
// the same card and disk, the current image («Обновить сервер»)
async function doUpdate() {
  asking.value = ''
  await act(() => post('/api/cloud/update'))
}
// more sets onto a deployed server's disk: what is ticked beyond what it has, and the disk it will need
const more = ref<string[]>([])
const podSets = computed<string[]>(() => pod.value?.sets || [])
const moreDisk = computed(() => Math.max(pod.value?.disk_gb || 0, Math.max(20, Math.ceil(((([...podSets.value, ...more.value]).reduce((a, k) => a + (sets.value[k]?.bytes || 0), 0) / 1e9) * 1.05 + 5) / 10) * 10)))
const toggleMore = (k: string) => { more.value = more.value.includes(k) ? more.value.filter((x) => x !== k) : [...more.value, k] }
async function addMore() {
  await act(() => post('/api/cloud/models', { sets: more.value, hf_token: hfToken.value, accept_h3: h3Ok.value }))
  more.value = []
}
const setAutoStop = (m: number) => { autoStop.value = m; if (pod.value) act(() => api('/api/cloud/auto_stop', { method: 'PUT', body: { minutes: m } })) }

let timer: ReturnType<typeof setTimeout> | undefined
function schedule() {
  clearTimeout(timer)
  timer = setTimeout(async () => { await load(); schedule() }, deploying.value || live.value.status === 'starting' ? 3000 : 15000)
}
watch(deploying, (now, was) => { schedule(); if (was && !now && !dep.value.error) banner(t('cloud.deployed'), 'info') })
onMounted(async () => {
  await load()
  if (st.value) {
    view.value = st.value.mode
    autoStop.value = st.value.auto_stop
    url.value = st.value.server?.url || ''
  }
  await loadCatalog()
  schedule()
})
onMounted(() => { tick = setInterval(() => { now.value = Date.now() }, 1000) })
onUnmounted(() => { clearTimeout(timer); clearInterval(tick) })
</script>

<template>
  <div class="cloud">
    <div class="m-title"><h2>{{ t('cloud.title') }}</h2><HelpQ id="cloud" /></div>
    <p class="muted">{{ t('cloud.intro') }}</p>
    <div v-if="err" class="warn-line" role="alert"><Icon name="warn" :size="14" />{{ err }}</div>
    <p v-if="!st && !err" class="muted">…</p>
    <template v-if="st">
      <!-- the three modes -->
      <div class="cl-modes" role="radiogroup" :aria-label="t('cloud.title')">
        <button v-for="m in (['local', 'cloud', 'server'] as const)" :key="m" type="button" role="radio" class="cl-mode"
                :class="{ on: view === m }" :aria-checked="view === m" @click="setMode(m)">
          <span class="cl-mode-top"><span class="cl-mode-ic"><Icon :name="m === 'local' ? 'film' : m === 'cloud' ? 'cloud' : 'link'" :size="17" /></span>
            <b>{{ t(`cloud.mode.${m}`) }}</b><small v-if="st.mode === m" class="cl-active">{{ t('cloud.active') }}</small></span>
          <span>{{ t(`cloud.mode.${m}Text`) }}</span>
          <em class="cl-mode-fact">{{ t(`cloud.mode.${m}Fact`) }}</em>
        </button>
      </div>

      <!-- the rented server: it exists -->
      <template v-if="view === 'cloud' && pod">
        <div class="cl-pod">
          <div class="cl-pod-head">
            <span class="cl-gpu"><span class="cl-gpu-ic"><Icon name="cloud" :size="18" /></span>
              <span><b>{{ pod.gpu_name }}</b><small>{{ prov.name }} · {{ pod.place || pod.datacenter }}</small></span></span>
            <span class="cl-price"><b>${{ money(pod.price) }}</b><small>/{{ t('cloud.hour') }}</small></span>
            <span class="pill-state" :class="{ on: live.status === 'running', busy: deploying }">{{ deploying ? t('cloud.deploying') : t(`cloud.pod.${live.status || 'unknown'}`) }}</span>
          </div>
          <div class="cl-facts">
            <span><Icon name="box" :size="13" />{{ t('cloud.diskShort', { n: pod.disk_gb, v: money(pod.disk_gb * (pod.storage_price || price)) }) }}</span>
            <span v-if="pod.tls_fp" :title="pod.tls_fp"><Icon name="lock" :size="13" />{{ t('cloud.tlsShort') }}</span>
            <span v-if="live.status === 'running' && !deploying"><Icon name="play" :size="13" />{{ t('cloud.runningFor', { v: hm(live.running_for) }) }}<template v-if="live.idle != null"> · {{ t('cloud.idle', { v: hm(live.idle) }) }}</template></span>
          </div>
          <div v-if="!prov.stays" class="cl-callout"><Icon name="bulb" :size="15" /><span>{{ t('cloud.vastNote') }}</span></div>
          <div v-if="live.outdated" class="cl-row">
            <div class="warn-line"><Icon name="warn" :size="14" />{{ t('cloud.outdated', { v: live.version }) }}</div>
            <template v-if="asking === 'update'">
              <span class="cl-ask">{{ t('cloud.updateAsk') }}</span>
              <button type="button" class="btn grad" :disabled="deploying" @click="doUpdate">{{ t('cloud.updateYes') }}</button>
              <button type="button" class="btn" @click="asking = ''">{{ t('cloud.cancel') }}</button>
            </template>
            <button v-else type="button" class="btn grad" :disabled="deploying" @click="asking = 'update'">{{ t('cloud.updateGo') }}</button>
          </div>
          <!-- the deploy still running / failed -->
          <template v-if="deploying || dep.error">
            <ol class="cl-stepper">
              <li v-for="(s, i) in DSTEPS" :key="s" :class="{ done: i < stepIdx || s === 'done' && dep.step === 'done', now: i === stepIdx && deploying, bad: i === stepIdx && dep.error }">
                <i><Icon v-if="i < stepIdx || s === 'done' && dep.step === 'done'" name="check" :size="12" /><template v-else>{{ i + 1 }}</template></i>
                <span>{{ t(`cloud.dstep.${s}`) }}<small v-if="stepTime(i)">{{ stepTime(i) }}</small></span></li>
            </ol>
            <div v-if="deploying" class="cl-now">
              <div class="cl-now-head"><b>{{ t(`cloud.dstep.${dep.step || 'volume'}`) }}</b>
                <span v-if="stepPct != null" class="cl-pct">{{ stepPct }}%</span>
                <button v-if="dep.step === 'wait'" type="button" class="ghost" @click="cancelWait">{{ t('cloud.cancel') }}</button></div>
              <span class="cl-track" :class="{ run: stepPct == null }"><i :style="stepPct != null ? { width: `${stepPct}%` } : {}" /></span>
              <p>{{ stepText }}</p>
              <code v-if="dep.step === 'boot' && dep.note" class="cl-note">{{ dep.note }}</code>
            </div>
            <div v-if="dep.error" class="warn-line" role="alert"><Icon name="warn" :size="14" />{{ t('cloud.deployFailed') }}: {{ dep.error }}</div>
          </template>
          <div class="cl-row">
            <button v-if="live.status === 'stopped' || live.status === 'error'" type="button" class="btn" @click="act(() => post('/api/cloud/start'))"><Icon name="play" :size="14" />{{ t('cloud.start') }}</button>
            <button v-if="live.status === 'running' || live.status === 'starting'" type="button" class="btn" :disabled="deploying" @click="act(() => post('/api/cloud/stop'))">{{ t('cloud.stopNow') }}</button>
            <template v-if="asking === 'delete'">
              <span class="cl-ask">{{ t('cloud.askDelete', { n: pod.disk_gb }) }}</span>
              <button type="button" class="btn danger" @click="remove">{{ t('cloud.deleteYes') }}</button>
              <button type="button" class="btn" @click="asking = ''">{{ t('cloud.cancel') }}</button>
            </template>
            <button v-else type="button" class="btn danger" :disabled="deploying" @click="asking = 'delete'"><Icon name="trash" :size="14" />{{ dep.error ? t('cloud.retry') : t('cloud.deleteAll') }}</button>
          </div>
        </div>
        <section v-if="prov.can_swap" class="cl-card">
        <h3 class="cl-h"><Icon name="sliders" :size="15" />{{ t('cloud.swap') }}</h3>
        <div class="cl-row">
          <select v-model="swapTo" class="field-in cl-swap" :disabled="deploying || !swapCards.length" :aria-label="t('cloud.swap')">
            <option value="">{{ swapCards.length ? t('cloud.swapPick', { dc: pod.datacenter }) : t('cloud.swapNone', { dc: pod.datacenter }) }}</option>
            <option v-for="g in swapCards" :key="g.id" :value="g.id">{{ g.name }} · {{ g.memory }} {{ t('common.gb') }} · ${{ money(g.price) }}/{{ t('cloud.hour') }}</option>
          </select>
          <template v-if="asking === 'swap' && swapGpu">
            <span class="cl-ask">{{ t('cloud.swapAsk', { gpu: swapGpu.name, p: money(swapGpu.price) }) }}</span>
            <button type="button" class="btn grad" @click="doSwap">{{ t('cloud.swapYes') }}</button>
            <button type="button" class="btn" @click="asking = ''">{{ t('cloud.cancel') }}</button>
          </template>
          <button v-else type="button" class="btn" :disabled="!swapGpu || deploying" @click="asking = 'swap'">{{ t('cloud.swapGo') }}</button>
        </div>
        <p class="muted small">{{ t('cloud.swapNote') }}</p>
        </section>
        <section v-if="!deploying" class="cl-card">
        <h3 class="cl-h"><Icon name="pin" :size="15" />{{ t(prov.stays ? 'cloud.move' : 'cloud.moveVast') }}</h3>
        <div class="cl-row">
          <select v-model="moveTo" class="field-in cl-swap" :disabled="deploying || !moveCards.length" :aria-label="t('cloud.move')">
            <option value="">{{ t('cloud.movePick') }}</option>
            <option v-for="g in moveCards" :key="g.id" :value="g.id">{{ g.name }} · {{ g.memory }} {{ t('common.gb') }} · ${{ money(g.price) }}/{{ t('cloud.hour') }}{{ g.recommended ? ' · ' + t('cloud.recommended') : '' }}</option>
          </select>
          <template v-if="asking === 'move' && moveGpu">
            <span class="cl-ask">{{ t('cloud.moveAsk', { gpu: moveGpu.name, p: money(moveGpu.price), dc: pod.datacenter }) }}</span>
            <button type="button" class="btn grad" @click="doMove">{{ t('cloud.moveYes') }}</button>
            <button type="button" class="btn" @click="asking = ''">{{ t('cloud.cancel') }}</button>
          </template>
          <button v-else type="button" class="btn" :disabled="!moveGpu || deploying" @click="asking = 'move'">{{ t('cloud.moveGo') }}</button>
        </div>
        <p class="muted small">{{ !prov.stays ? t('cloud.moveVastNote') : swapCards.length ? t('cloud.moveNote') : t('cloud.moveNeeded', { dc: pod.datacenter }) }}</p>
        </section>
        <section class="cl-card">
        <h3 class="cl-h"><Icon name="layers" :size="15" />{{ t('cloud.step.models') }}</h3>
        <label v-for="k in SHOWN_SETS.filter((x) => sets[x])" :key="k" class="cl-set" :class="{ fixed: podSets.includes(k) }">
          <input type="checkbox" :checked="podSets.includes(k) || more.includes(k)" :disabled="podSets.includes(k) || deploying" @change="toggleMore(k)">
          <span>{{ sets[k].title }}<small v-if="podSets.includes(k)" class="muted"> · {{ t('cloud.onDisk') }}</small><small v-else-if="sets[k].gated" class="muted"> · {{ t('cloud.gated') }}</small></span>
          <span class="muted">{{ gb(sets[k].bytes / 2 ** 30) }} {{ t('common.gb') }}</span>
        </label>
        <input v-if="more.includes('ltx25')" v-model="hfToken" type="password" class="field-in" autocomplete="off" :placeholder="t('cloud.hfToken')" :aria-label="t('cloud.hfToken')">
        <template v-if="!deploying && live.fast?.state === 'copying' && live.fast.total">
          <p class="muted" :title="t('cloud.fastNote')">{{ t('cloud.fastOf', { a: gb(live.fast.done / 2 ** 30), b: gb(live.fast.total / 2 ** 30) }) }}<template v-if="live.fast.file"> · {{ t('cloud.modelsFile', { v: live.fast.file }) }}</template></p>
          <span class="bar"><i :style="{ width: `${Math.floor((100 * live.fast.done) / live.fast.total)}%` }" /></span>
        </template>
        <template v-if="!deploying && live.models?.state === 'downloading' && live.models.total">
          <p class="muted">{{ t('cloud.modelsOf', { a: gb(live.models.done / 2 ** 30), b: gb(live.models.total / 2 ** 30) }) }}<template v-if="live.models.file"> · {{ t('cloud.modelsFile', { v: live.models.file }) }}</template></p>
          <span class="bar"><i :style="{ width: `${Math.floor((100 * live.models.done) / live.models.total)}%` }" /></span>
        </template>
        <template v-if="moreH3"><p class="muted small">{{ t('cloud.h3Licence') }} <a href="https://huggingface.co/MiniMaxAI/MiniMax-H3" target="_blank" rel="noopener">{{ t('cloud.h3Link') }}</a></p>
          <label class="check-row"><input v-model="h3Ok" type="checkbox"><span>{{ t('cloud.h3Accept') }}</span></label></template>
        <div v-if="more.length" class="cl-row">
          <button type="button" class="btn grad" :disabled="(moreDisk > pod.disk_gb && !prov.can_grow) || (moreH3 && !h3Ok)" @click="addMore"><Icon name="download" :size="14" />{{ t('cloud.addSets') }}</button>
          <span class="muted small">{{ moreDisk <= pod.disk_gb ? t('cloud.addSetsFits') : prov.can_grow ? t('cloud.addSetsGrow', { n: moreDisk, v: money(moreDisk * price) }) : t('cloud.addSetsNoGrow', { n: moreDisk }) }}</span>
        </div>
        </section>
        <section class="cl-card">
        <h3 class="cl-h"><Icon name="stop" :size="15" />{{ t('cloud.step.autoStop') }}</h3>
        <div class="cl-chips"><button v-for="m in STOPS" :key="m" type="button" class="chip" :class="{ on: autoStop === m }" @click="setAutoStop(m)">{{ t(`cloud.stop.${m}`) }}</button></div>
        <p class="muted small">{{ prov.stays ? t('cloud.stopNote') : t('cloud.vastStopNote') }}</p>
        </section>
      </template>

      <!-- the rented server: the steps to deploy one -->
      <template v-else-if="view === 'cloud'">
        <div class="cl-two">
          <div>
            <h3 class="cl-h">1 · {{ t('cloud.step.provider') }}</h3>
            <div class="cl-provs" role="radiogroup" :aria-label="t('cloud.step.provider')">
              <button v-for="p in st.providers" :key="p.id" type="button" role="radio" class="cl-prov" :class="{ on: p.id === st.provider }"
                      :aria-checked="p.id === st.provider" @click="pickProvider(p.id)"><b>{{ p.name }}</b><small>{{ t(`cloud.providerNote.${p.id}`) }}</small></button>
              <button v-for="p in st.soon" :key="p.id" type="button" class="cl-prov" disabled><b>{{ p.name }}</b><small>{{ t(`cloud.providerNote.${p.id}`) }} · {{ t('cloud.soon') }}</small></button>
            </div>
            <p v-if="!prov.stays" class="muted small">{{ t('cloud.vastNote') }}</p>
          </div>
          <div>
            <h3 class="cl-h">2 · {{ t('cloud.step.key', { name: prov.name }) }} <a :href="prov.key_url" target="_blank" rel="noopener">{{ t('cloud.whereKey') }} ↗</a> <HelpQ id="cloud" term="Ключ провайдера" /></h3>
            <div v-if="st.has_key && !replacing" class="cl-row">
              <span class="cl-ok"><Icon name="check" :size="14" />{{ t('cloud.keySaved') }}<template v-if="balance != null"> · {{ t('cloud.balance', { v: money(balance) }) }}</template></span>
              <button type="button" class="btn" @click="replacing = true">{{ t('cloud.replaceKey') }}</button>
              <button type="button" class="ghost" @click="forgetKey">{{ t('cloud.forgetKey') }}</button>
            </div>
            <form v-else class="cl-row" @submit.prevent="saveKey">
              <input v-model="keyIn" type="password" class="field-in" autocomplete="off" :placeholder="t('cloud.keyPh')" :aria-label="t('cloud.step.key', { name: prov.name })">
              <button type="submit" class="btn" :disabled="!keyIn.trim()">{{ t('cloud.saveKey') }}</button>
            </form>
            <p class="muted small">{{ t('cloud.keyNote') }}</p>
          </div>
        </div>

        <template v-if="st.has_key">
          <div class="cl-two">
            <div>
              <h3 class="cl-h">3 · {{ t('cloud.step.gpu') }} <small class="muted">{{ t('cloud.gpusNote') }}</small> <HelpQ id="cloud" term="Видеокарта" /></h3>
              <p v-if="!gpus" class="muted">{{ t('cloud.gpusLoading') }}</p>
              <table v-else class="cl-gpus">
                <thead><tr><th>{{ t('cloud.gpuCol') }}</th><th>{{ t('cloud.memCol') }}</th><th>{{ t('cloud.priceCol') }}</th><th>{{ t('cloud.nowCol') }}</th></tr></thead>
                <tbody>
                  <tr v-for="g in gpus" :key="g.id" :class="{ on: g.id === gpuId, off: g.availability === 'none' }" @click="g.availability !== 'none' && (gpuId = g.id)">
                    <td><input type="radio" name="gpu" :checked="g.id === gpuId" :disabled="g.availability === 'none'" :aria-label="g.name"> {{ g.name }}
                      <span v-if="g.recommended" class="cl-badge">{{ t('cloud.recommended') }}</span></td>
                    <td>{{ t('cloud.gb', { n: g.memory }) }}</td><td>${{ money(g.price) }}<small v-if="g.extra" class="muted" :title="t('cloud.traffic', { v: money(g.extra) })"> + ${{ money(g.extra) }}</small></td>
                    <td :class="`av-${g.availability}`">● {{ t(`cloud.avail.${g.availability}`) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div>
              <h3 class="cl-h">4 · {{ t('cloud.step.models') }}</h3>
              <label v-for="k in SHOWN_SETS.filter((x) => sets[x])" :key="k" class="cl-set" :class="{ fixed: k === 'writer' }">
                <input type="checkbox" :checked="want.includes(k)" :disabled="k === 'writer'" @change="toggleSet(k)">
                <span>{{ sets[k].title }}<small v-if="k === 'writer'" class="muted"> · {{ t('cloud.always') }}</small><small v-else-if="sets[k].gated" class="muted"> · {{ t('cloud.gated') }}</small></span>
                <span class="muted">{{ gb(sets[k].bytes / 2 ** 30) }} {{ t('common.gb') }}</span>
              </label>
              <template v-if="needsH3"><p class="muted small">{{ t('cloud.h3Licence') }} <a href="https://huggingface.co/MiniMaxAI/MiniMax-H3" target="_blank" rel="noopener">{{ t('cloud.h3Link') }}</a></p>
                <label class="check-row"><input v-model="h3Ok" type="checkbox"><span>{{ t('cloud.h3Accept') }}</span></label></template>
              <input v-if="want.includes('ltx25')" v-model="hfToken" type="password" class="field-in" autocomplete="off" :placeholder="t('cloud.hfToken')" :aria-label="t('cloud.hfToken')">
              <p class="muted small">{{ t('cloud.disk', { n: diskGb, v: perMonth }) }}</p>
            </div>
          </div>
          <h3 class="cl-h">5 · {{ t('cloud.step.autoStop') }}</h3>
          <div class="cl-chips"><button v-for="m in STOPS" :key="m" type="button" class="chip" :class="{ on: autoStop === m }" @click="setAutoStop(m)">{{ t(`cloud.stop.${m}`) }}</button></div>
          <p class="muted small">{{ prov.stays ? t('cloud.stopNote') : t('cloud.vastStopNote') }}</p>

          <div class="cl-total">
            <div><span class="muted">{{ t('cloud.total') }}</span>
              <b v-if="gpu">{{ t('cloud.perHour', { v: money(gpu.price) }) }}</b> <span v-if="gpu && gpu.extra" class="muted">{{ t('cloud.traffic', { v: money(gpu.extra) }) }}</span> <span class="muted">{{ t('cloud.perMonth', { v: perMonth, n: diskGb }) }}</span></div>
            <template v-if="asking === 'deploy' && gpu">
              <span class="cl-ask">{{ t('cloud.confirm', { gpu: gpu.name, p: money(gpu.price), n: diskGb, name: prov.name }) }}</span>
              <button type="button" class="btn grad" @click="deploy">{{ t('cloud.yes') }}</button>
              <button type="button" class="btn" @click="asking = ''">{{ t('cloud.cancel') }}</button>
            </template>
            <button v-else type="button" class="btn grad big" :disabled="!gpu || deploying || (needsH3 && !h3Ok)" @click="asking = 'deploy'"><Icon name="cloud" :size="16" />{{ t('cloud.deploy') }}</button>
          </div>
          <p v-if="deploying && dep.step === 'wait'" class="muted">{{ t('cloud.waitCard', { n: dep.tries }) }} <button type="button" class="ghost" @click="cancelWait">{{ t('cloud.cancel') }}</button></p>
          <p v-else-if="deploying" class="muted">{{ t(`cloud.dstep.${dep.step || 'volume'}`) }}…</p>
          <div v-else-if="dep.error && dep.code !== 'cancelled'" class="cl-row">
            <div class="warn-line" role="alert"><Icon name="warn" :size="14" />{{ t('cloud.deployFailed') }}: {{ dep.error }}</div>
            <button type="button" class="btn" :disabled="!gpu" @click="deploy">{{ t('cloud.tryAgain') }}</button>
          </div>
        </template>
      </template>

      <!-- the user's own server -->
      <template v-else-if="view === 'server'">
        <form class="cl-server" @submit.prevent="connectServer">
          <label>{{ t('cloud.serverUrl') }}<input v-model="url" class="field-in" placeholder="https://…-8188.proxy.runpod.net"></label>
          <label>{{ t('cloud.serverToken') }}<input v-model="token" type="password" class="field-in" autocomplete="off" :placeholder="st.server?.token_set ? t('cloud.serverTokenSet') : ''"></label>
          <button type="submit" class="btn" :disabled="!url.trim()">{{ t('cloud.check') }}</button>
        </form>
        <p v-if="serverOk" class="cl-ok"><Icon name="check" :size="14" />{{ serverOk }}</p>
        <p class="muted small">{{ t('cloud.serverHow') }}</p>
      </template>
    </template>
  </div>
</template>

<style scoped>
.cloud { display: grid; gap: 14px; }
.cl-modes { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; }
.cl-mode { display: grid; gap: 8px; align-content: start; text-align: left; padding: 14px; border-radius: 14px; border: 1px solid var(--rule); background: var(--field);
  color: var(--text); cursor: pointer; transition: border-color .15s, background .15s; }
.cl-mode:hover { border-color: var(--rule-3); }
.cl-mode-top { display: flex; align-items: center; gap: 10px; }
.cl-mode-top b { font-size: 15px; }
.cl-mode-ic { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 9px; background: var(--deep); color: var(--soft); flex: none; }
.cl-mode > span:not(.cl-mode-top) { color: var(--muted); font-size: 12.5px; line-height: 1.45; }
.cl-mode-fact { font-style: normal; font-size: 12px; color: var(--soft); }
.cl-mode.on { border-color: rgba(168, 85, 247, .7); background: linear-gradient(135deg, rgba(168, 85, 247, .16), rgba(236, 72, 153, .07)); }
.cl-mode.on .cl-mode-ic { background: var(--grad); color: #fff; }
.cl-active { margin-left: auto; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; color: #3ddc97; background: rgba(61, 220, 151, .1); white-space: nowrap; }
.cl-card { display: grid; gap: 10px; padding: 14px 16px; border-radius: 14px; border: 1px solid var(--rule); background: var(--field); }
.cl-card .cl-h { margin: 0; }
.cl-card .cl-h svg { color: #c084fc; }
.cl-card p { margin: 0; }
.cl-h { margin: 6px 0 8px; font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); display: flex; gap: 8px; align-items: center; }
.cl-h a { text-transform: none; letter-spacing: 0; font-weight: 500; color: var(--accent); }
.cl-two { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 24px; }
.cl-provs { display: flex; gap: 10px; }
.cl-prov { display: grid; gap: 2px; min-width: 180px; text-align: left; padding: 10px 14px; border-radius: 10px; border: 1px solid var(--rule); background: var(--field); color: var(--text); }
.cl-prov.on { border-color: var(--accent); }
.cl-prov small { color: var(--muted); font-size: 11px; }
.cl-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.cl-row .field { flex: 1; min-width: 220px; }
.cl-ok { display: inline-flex; gap: 6px; align-items: center; color: var(--good, #3ddc97); font-size: 13px; }
.cl-gpus { width: 100%; border-collapse: separate; border-spacing: 0 4px; font-size: 13px; }
.cl-gpus th { text-align: left; font-size: 11px; font-weight: 600; color: var(--muted); padding: 0 8px; }
.cl-gpus td { padding: 9px 8px; background: var(--field); }
.cl-gpus td:first-child { border-radius: 10px 0 0 10px; }
.cl-gpus td:last-child { border-radius: 0 10px 10px 0; }
.cl-gpus tr { cursor: pointer; }
.cl-gpus tr.on td { background: rgba(168, 85, 247, .16); }
.cl-gpus tr.off { opacity: .45; cursor: default; }
.cl-badge { margin-left: 6px; padding: 1px 8px; border-radius: 10px; background: #2a2235; color: #f0abfc; font-size: 11px; }
.av-high, .av-medium { color: var(--good, #3ddc97); }
.av-low { color: var(--warn); }
.av-none { color: var(--muted); }
.cl-set { display: grid; grid-template-columns: auto 1fr auto; gap: 10px; align-items: center; padding: 6px 0; font-size: 13px; }
.cl-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.small { font-size: 12px; }
.cl-total { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; padding-top: 14px; border-top: 1px solid var(--rule); }
.cl-total > div { display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; }
.cl-total b { font-size: 18px; }
.cl-ask { flex: 1 1 320px; font-size: 13px; color: var(--soft); }
.btn.grad { border: 0; background: var(--grad); color: #fff; font-weight: 600; }
.btn.big { min-height: 48px; padding: 0 22px; font-size: 15px; }
.cl-pod { display: grid; gap: 8px; padding: 14px 16px; border-radius: 14px; border: 1px solid var(--rule); background: var(--field); }
.cl-pod-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.cl-gpu { display: flex; gap: 10px; align-items: center; margin-right: auto; }
.cl-gpu-ic { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 10px; background: var(--grad); color: #fff; }
.cl-gpu > span:last-child { display: grid; line-height: 1.25; }
.cl-gpu b { font-size: 15px; }
.cl-gpu small { color: var(--muted); font-size: 12px; }
.cl-price b { font-size: 16px; font-variant-numeric: tabular-nums; }
.cl-price small { color: var(--muted); font-size: 12px; }
.pill-state.busy { color: #e9d5ff; border-color: rgba(168, 85, 247, .55); }
.cl-facts { display: flex; flex-wrap: wrap; gap: 6px 16px; color: var(--muted); font-size: 12px; }
.cl-facts span { display: inline-flex; gap: 5px; align-items: center; }
.cl-callout { display: flex; gap: 8px; align-items: flex-start; padding: 9px 12px; border-radius: 10px; background: rgba(168, 85, 247, .08);
  border: 1px solid rgba(168, 85, 247, .22); color: var(--soft); font-size: 12.5px; line-height: 1.45; }
.cl-callout svg { flex: none; margin-top: 1px; color: #c084fc; }
.cl-stepper { display: grid; grid-template-columns: repeat(6, 1fr); gap: 0; list-style: none; margin: 6px 0 0; padding: 0; counter-reset: s; }
.cl-stepper li { position: relative; display: grid; justify-items: center; gap: 6px; text-align: center; font-size: 12px; color: var(--muted); }
.cl-stepper li::before { content: ''; position: absolute; top: 13px; left: calc(-50% + 16px); right: calc(50% + 16px); height: 2px; background: var(--rule); }
.cl-stepper li:first-child::before { display: none; }
.cl-stepper li.done::before, .cl-stepper li.now::before { background: linear-gradient(90deg, #3ddc97, #a855f7); }
.cl-stepper i { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; border: 1.5px solid var(--rule); background: var(--deep);
  font-style: normal; font-size: 12px; z-index: 1; }
.cl-stepper span { display: grid; gap: 1px; line-height: 1.2; }
.cl-stepper small { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
.cl-stepper li.done { color: var(--soft); }
.cl-stepper li.done i { border-color: #2e7d5b; background: rgba(61, 220, 151, .12); color: #3ddc97; }
.cl-stepper li.now { color: var(--text); font-weight: 600; }
.cl-stepper li.now i { border: 0; background: var(--grad); color: #fff; box-shadow: 0 0 0 5px rgba(168, 85, 247, .18); }
.cl-stepper li.bad i { border-color: var(--bad); color: var(--bad); }
.cl-now { display: grid; gap: 8px; padding: 12px 14px; border-radius: 12px; background: var(--deep); border: 1px solid var(--rule); }
.cl-now-head { display: flex; gap: 10px; align-items: center; }
.cl-now-head b { margin-right: auto; }
.cl-now p { margin: 0; color: var(--soft); font-size: 13px; }
.cl-pct { font-weight: 600; font-variant-numeric: tabular-nums; }
.cl-track { position: relative; display: block; height: 8px; border-radius: 4px; background: var(--rule); overflow: hidden; }
.cl-track i { display: block; height: 100%; border-radius: 4px; background: var(--grad); transition: width .6s; }
.cl-track.run i { position: absolute; width: 35%; animation: cl-run 1.4s ease-in-out infinite; }
@keyframes cl-run { from { left: -35%; } to { left: 100%; } }
@media (prefers-reduced-motion: reduce) { .cl-track.run i { animation: none; left: 0; width: 100%; opacity: .4; } }
.cl-note { display: block; font-size: 11.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
@media (max-width: 640px) { .cl-stepper small { display: none; } .cl-stepper { font-size: 11px; } }
.cl-steps { display: flex; flex-wrap: wrap; gap: 6px 18px; list-style: none; margin: 4px 0; padding: 0; font-size: 13px; color: var(--muted); }
.cl-steps li { display: flex; gap: 6px; align-items: center; }
.cl-steps i { display: inline-grid; place-items: center; width: 20px; height: 20px; border-radius: 50%; border: 1px solid var(--rule); font-style: normal; font-size: 11px; }
.cl-steps li.done { color: var(--soft); }
.cl-steps li.done i { border-color: #2e7d5b; color: #3ddc97; }
.cl-steps li.now { color: #fff; font-weight: 600; }
.cl-steps li.now i { border: 0; background: var(--grad); color: #fff; }
.cl-steps li.bad i { border-color: var(--bad); color: var(--bad); }
.bar { display: block; height: 6px; border-radius: 3px; background: var(--rule); overflow: hidden; }
.bar i { display: block; height: 100%; background: var(--grad); }
.cl-swap { max-width: 420px; }
.cl-server { display: grid; grid-template-columns: 2fr 1fr auto; gap: 10px; align-items: end; }
.cl-server label { display: grid; gap: 4px; font-size: 12px; color: var(--muted); }
@media (max-width: 900px) { .cl-two, .cl-server { grid-template-columns: 1fr; } }
</style>
