<script setup lang="ts">
// The «Герой» node's actor (app/actors.py): pick one from the library, save this hero into it, the sheet (face +
// turnaround, «Нарисовать лист») and the «Пробы» (the face in up to four looks x two seeds; a click makes one the look).
// With an actor the node takes the actor's look, outfit and face panel; the hero's own fields stay under it, unused.
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import { GE, flush, loadState, touch } from '../../lib/graphDoc'
import { api, post } from '../../lib/api'
import { banner } from '../../lib/store'
import { L, loadLooks } from '../../lib/looks'
import type { Job } from '../../lib/types'

interface Actor {
  id: string; name: string; look_en: string; look_ru: string; outfit_en: string; outfit_ru: string; kind: string; look: string
  images: Record<string, number>; tries?: { file: string; look: string; seed: number }[]
}
const props = defineProps<{ data: Record<string, any>; nodeId: string }>()
const { t: tx } = useI18n()
const list = ref<Actor[]>([])
const picking = ref(false)
const triesOpen = ref(false)
const chosen = ref<string[]>(['anime', 'cartoon3d', 'clay', 'live_cinema'])
const job = ref<{ what: string; secs: number; queued: boolean } | null>(null)
const busy = computed(() => !!job.value)
const actor = computed(() => list.value.find((a) => a.id === props.data.actor))
const img = (a: Actor, w: string) => (a.images[w] ? `/api/actors/${a.id}/image/${w}?v=${a.images[w]}` : '')
const tryUrl = (a: Actor, f: string) => `/api/actors/${a.id}/tries/${f}`
const lookName = (k: string) => L.looks.find((x) => x.id === k)?.name || k
// the looks the page offers, the four of the brief first
const FIRST = ['anime', 'cartoon3d', 'clay', 'live_cinema']
const looks = computed(() => [...L.looks].sort((a, b) => (FIRST.indexOf(a.id) + 1 || 99) - (FIRST.indexOf(b.id) + 1 || 99)))

async function refresh() {
  try { list.value = (await api<{ actors: Actor[] }>('/api/actors')).actors } catch (e) { banner((e as Error).message) }
}
onMounted(() => { refresh(); loadLooks().catch(() => {}) })
watch(() => props.nodeId, () => { picking.value = false; triesOpen.value = false })

function use(id: string) { props.data.actor = id; picking.value = false; touch(50) }
function unuse() { delete props.data.actor; touch(50) }

// a job in the studio's queue, polled each second until it ends; the actor is read again
async function wait(first: Job, what: string): Promise<boolean> {
  let j = first
  job.value = { what, secs: 0, queued: true }
  while (j.status === 'queued' || j.status === 'running') {
    await new Promise((ok) => setTimeout(ok, 1000))
    try { j = await api<Job>(`/api/jobs/${j.id}`) } catch { job.value = null; return false }
    job.value = { what, secs: Math.round(j.elapsed || 0), queued: j.status === 'queued' }
  }
  job.value = null
  if (j.status !== 'done') { banner(j.error || tx('actors.failed')); return false }
  await refresh()
  await loadState()   // the hero card's picture (and its ?v=) comes from the graph state
  return true
}
async function run(path: string, body: unknown, what: string) {
  if (busy.value) return
  try { await wait(await post<Job>(path, body), what) } catch (e) { banner((e as Error).message); job.value = null }
}
const sheet = () => actor.value && run(`/api/actors/${actor.value.id}/sheet`, {}, tx('actors.drawing'))

function toggle(k: string) {
  chosen.value = chosen.value.includes(k) ? chosen.value.filter((x) => x !== k) : chosen.value.length < 4 ? [...chosen.value, k] : chosen.value
}
const tries = () => actor.value && chosen.value.length && run(`/api/actors/${actor.value.id}/tries`, { looks: chosen.value, seeds: 2 }, tx('actors.trying'))
async function pickTry(f: string) {
  const a = actor.value
  if (!a || busy.value || !confirm(tx('actors.pickAsk'))) return
  try {
    const r = await post<{ actor: Actor; job: Job | null }>(`/api/actors/${a.id}/tries/${f}/pick`, { sheet: true })
    await refresh()
    if (r.job) await wait(r.job, tx('actors.drawing'))
  } catch (e) { banner((e as Error).message) }
}
async function clearTries() {
  if (actor.value) { try { await api(`/api/actors/${actor.value.id}/tries`, { method: 'DELETE' }); await refresh() } catch (e) { banner((e as Error).message) } }
}
async function toLibrary() {
  const name = (props.data.title || '').trim() || (prompt(tx('actors.namePrompt')) || '').trim()
  if (!name) return
  try {
    await flush()   // the server reads the hero from the saved graph
    const a = await post<Actor>('/api/actors/from-hero', { project: GE.id, node: props.nodeId, name })
    await refresh()
    banner(tx('actors.saved', { name: a.name }))
  } catch (e) { banner((e as Error).message) }
}
async function upload(ev: Event) {
  const f = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!f || !actor.value) return
  const fd = new FormData()
  fd.append('file', f)
  try { await api(`/api/actors/${actor.value.id}/photo`, { method: 'POST', body: fd }); await refresh() } catch (e) { banner((e as Error).message) }
}
</script>

<template>
  <div class="actor-box">
    <div class="ni-row">
      <b class="grow">{{ tx('actors.title') }}</b>
      <button type="button" class="btn" :disabled="busy" @click="picking = !picking"><Icon name="user" />{{ tx('actors.fromLib') }}</button>
      <button type="button" class="btn" :disabled="busy" :title="tx('actors.toLibTitle')" @click="toLibrary"><Icon name="plus" />{{ tx('actors.toLib') }}</button>
    </div>

    <div v-if="picking" class="actor-pick">
      <p v-if="!list.length" class="muted small">{{ tx('actors.empty') }}</p>
      <button v-for="a in list" :key="a.id" type="button" class="actor-item" :class="{ on: a.id === data.actor }" @click="use(a.id)">
        <img v-if="a.images.face" :src="img(a, 'face')" alt="">
        <span v-else class="actor-noface">?</span>
        <span>{{ a.name }}</span>
      </button>
    </div>

    <template v-if="data.actor">
      <p v-if="!actor" class="muted small warn">{{ tx('actors.gone') }}</p>
      <template v-else>
        <div class="ni-row"><b class="grow">{{ actor.name }}</b>
          <button type="button" class="btn" :disabled="busy" @click="unuse">{{ tx('actors.unuse') }}</button></div>
        <p class="muted small">{{ tx('actors.hint') }}</p>
        <div class="actor-sheet">
          <img v-if="actor.images.face" :src="img(actor, 'face')" alt="" :title="tx('actors.face')">
          <img v-if="actor.images.turn" class="turn" :src="img(actor, 'turn')" alt="" :title="tx('actors.turn')">
          <p v-if="!actor.images.face && !actor.images.turn" class="muted small">{{ tx('actors.noSheet') }}</p>
        </div>
        <p v-if="actor.look" class="muted small">{{ tx('actors.lookIs', { look: lookName(actor.look) }) }}</p>
        <div class="ni-row">
          <button type="button" class="btn" :disabled="busy" :title="tx('actors.sheetTitle')" @click="sheet"><Icon name="brush" />{{ tx('actors.sheet') }}</button>
          <label class="btn"><Icon name="image" />{{ tx('actors.photo') }}<input type="file" accept="image/*" hidden :disabled="busy" @change="upload"></label>
          <button type="button" class="btn" :disabled="busy" @click="triesOpen = !triesOpen"><Icon name="layers" />{{ tx('actors.tries') }}</button>
        </div>
        <span v-if="job" class="muted small">{{ job.queued ? tx('actors.queue') : tx('actors.working', { what: job.what, s: job.secs }) }}</span>

        <div v-if="triesOpen" class="actor-tries">
          <p class="muted small">{{ tx('actors.triesHint') }}</p>
          <div class="actor-looks">
            <button v-for="x in looks" :key="x.id" type="button" class="chip" :class="{ on: chosen.includes(x.id) }" @click="toggle(x.id)">{{ x.name }}</button>
          </div>
          <button type="button" class="btn" :disabled="busy || !chosen.length" @click="tries"><Icon name="spark" />{{ tx('actors.makeTries', { n: chosen.length * 2 }) }}</button>
          <div v-if="actor.tries?.length" class="actor-grid">
            <button v-for="t in actor.tries" :key="t.file" type="button" class="actor-try" :disabled="busy" :title="tx('actors.pickTitle')" @click="pickTry(t.file)">
              <img :src="tryUrl(actor, t.file)" alt=""><span>{{ lookName(t.look) }}</span>
            </button>
          </div>
          <button v-if="actor.tries?.length" type="button" class="btn" :disabled="busy" @click="clearTries">{{ tx('actors.clear') }}</button>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.actor-box { display: flex; flex-direction: column; gap: 8px; padding: 10px; border: 1px solid var(--line, #4443); border-radius: 10px; }
.actor-pick { display: grid; grid-template-columns: repeat(auto-fill, minmax(88px, 1fr)); gap: 6px; }
.actor-item, .actor-try { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 4px; border: 1px solid var(--line, #4443); border-radius: 8px; background: none; color: inherit; cursor: pointer; font-size: 12px; }
.actor-item.on { border-color: var(--accent); }
.actor-item img, .actor-try img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; background: #000; }
.actor-noface { width: 100%; aspect-ratio: 1; display: grid; place-items: center; background: #000; border-radius: 6px; color: #888; }
.actor-sheet { display: flex; gap: 6px; align-items: stretch; background: #000; border-radius: 10px; padding: 4px; }
.actor-sheet img { height: 120px; width: auto; max-width: 40%; object-fit: contain; }
.actor-sheet img.turn { max-width: 60%; flex: 1; }
.actor-tries { display: flex; flex-direction: column; gap: 8px; }
.actor-looks { display: flex; flex-wrap: wrap; gap: 4px; }
.chip { padding: 2px 8px; border: 1px solid var(--line, #4443); border-radius: 12px; background: none; color: inherit; font-size: 12px; cursor: pointer; }
.chip.on { border-color: var(--accent); background: var(--accent-soft, #6a4ad533); }
.actor-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
</style>
