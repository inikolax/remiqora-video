<script setup lang="ts">
// The header's cloud chip (cloud mode only): the rented card, its price, how long it runs, «Стоп»; stopped - «Запустить»;
// two minutes before the auto-stop - «Не выключать». A click opens «Настройки» → «Где работают модели».
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import { api } from '../lib/api'
import { S, banner, pollSystem } from '../lib/store'

const { t } = useI18n()
const st = ref<Record<string, any> | null>(null)
const busy = ref(false)
const shown = computed(() => !!st.value?.pod && ['cloud', 'local'].includes(st.value?.mode))
const cloudOn = computed(() => st.value?.mode === 'cloud')
// «На ПК»: first what runs or waits (its models are on the other side), then what becomes of the server
const asking = ref(false)
const pending = computed(() => S.jobs.filter((j) => j.status === 'running' || j.status === 'queued').length)
async function toPc(stopPod: boolean) {
  asking.value = false
  await act('/api/cloud/mode', { mode: 'local', stop_pod: stopPod }, 'PUT')
}
const live = computed(() => st.value?.live || {})
const hm = (s: number) => { const m = Math.floor((s || 0) / 60); return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}` }

async function load() { try { st.value = await api('/api/cloud') } catch { /* no chip this round */ } }
async function act(path: string, body?: object, method = 'POST') {
  busy.value = true
  try { st.value = await api(path, { method, body }) } catch (e) { banner((e as Error).message) } finally { busy.value = false }
  pollSystem()
}
let timer: ReturnType<typeof setTimeout> | undefined
function schedule() {
  clearTimeout(timer)
  timer = setTimeout(async () => { await load(); schedule() }, live.value.warn || live.value.status === 'starting' ? 5000 : 20000)
}
onMounted(async () => { await load(); schedule() })
onUnmounted(() => clearTimeout(timer))
</script>

<template>
  <div v-if="shown && !cloudOn" class="cloud-chip pc" :class="{ off: live.status !== 'running' }">
    <router-link to="/settings/cloud" :title="t('cloud.chip.pcTitle', { gpu: st!.pod.gpu_name })">
      <Icon name="cloud" :size="14" />
      <template v-if="live.status === 'running'">{{ t('cloud.chip.pcRunning', { gpu: st!.pod.gpu_name, v: (live.cost || 0).toFixed(2) }) }}</template>
      <template v-else>{{ st!.pod.gpu_name }} · {{ t(`cloud.pod.${live.status || 'unknown'}`) }}</template>
    </router-link>
    <button v-if="live.status === 'running'" type="button" :disabled="busy || live.busy" @click="act('/api/cloud/stop')">{{ t('cloud.chip.stop') }}</button>
    <button type="button" :disabled="busy || pending > 0" :title="pending ? t('cloud.chip.waitJobs', { n: pending }) : t('cloud.chip.toCloudTitle')"
      @click="act('/api/cloud/mode', { mode: 'cloud' }, 'PUT')">{{ t('cloud.chip.toCloud') }}</button>
  </div>
  <div v-if="shown && cloudOn" class="cloud-chip" :class="{ warn: live.warn, off: live.status !== 'running' }">
    <router-link to="/settings/cloud" :title="t('cloud.chip.title', { gpu: st!.pod.gpu_name, p: st!.pod.price.toFixed(2) })">
      <Icon name="cloud" :size="14" />
      <template v-if="live.status === 'running'">{{ st!.pod.gpu_name }} · {{ hm(live.running_for) }} · ≈ ${{ (live.cost || 0).toFixed(2) }}</template>
      <template v-else>{{ t(`cloud.pod.${live.status || 'unknown'}`) }}</template>
    </router-link>
    <template v-if="live.warn">
      <span class="w">{{ t('cloud.chip.warn') }}</span>
      <button type="button" :disabled="busy" @click="act('/api/cloud/keepalive')">{{ t('cloud.chip.keep') }}</button>
    </template>
    <button v-else-if="live.status === 'running'" type="button" :disabled="busy || live.busy" @click="act('/api/cloud/stop')">{{ t('cloud.chip.stop') }}</button>
    <button v-else-if="live.status === 'stopped'" type="button" :disabled="busy" @click="act('/api/cloud/start')">{{ t('cloud.chip.start') }}</button>
    <button type="button" class="pc-btn" :disabled="busy" :title="t('cloud.chip.toPcTitle')" @click="asking = !asking">{{ t('cloud.chip.toPc') }}</button>
    <div v-if="asking" class="cc-ask" role="dialog" :aria-label="t('cloud.chip.toPc')" @click.stop>
      <template v-if="pending">
        <p>{{ t('cloud.chip.busyJobs', { n: pending }) }}</p>
        <div class="cc-acts"><button type="button" @click="asking = false">{{ t('cloud.cancel') }}</button></div>
      </template>
      <template v-else>
        <p>{{ t('cloud.chip.askPc') }}</p>
        <p v-if="live.status === 'running' || live.status === 'starting'" class="cc-warn">{{ t('cloud.chip.pcKeepWarn') }}</p>
        <div class="cc-acts">
          <button v-if="live.status === 'running' || live.status === 'starting'" type="button" class="main" :disabled="busy" @click="toPc(true)">{{ t('cloud.chip.pcStop') }}</button>
          <button type="button" :disabled="busy" @click="toPc(false)">{{ live.status === 'running' || live.status === 'starting' ? t('cloud.chip.pcKeep') : t('cloud.chip.pcGo') }}</button>
          <button type="button" @click="asking = false">{{ t('cloud.cancel') }}</button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.cloud-chip { display: inline-flex; align-items: center; gap: 8px; height: 30px; padding: 0 4px 0 12px; border-radius: 15px; border: 1px solid rgba(168, 85, 247, .55);
  background: #1f1a2b; color: #e9d5ff; font-size: 12px; white-space: nowrap; }
.cloud-chip a { display: inline-flex; align-items: center; gap: 6px; color: inherit; text-decoration: none; }
.cloud-chip button { height: 22px; padding: 0 10px; border: 0; border-radius: 11px; background: #2a2235; color: #f0abfc; font-size: 11px; }
.cloud-chip button:hover:not(:disabled) { filter: brightness(1.2); }
.cloud-chip.off { border-color: var(--rule); background: var(--field); color: var(--soft); }
.cloud-chip.warn { border-color: var(--warn); }
.cloud-chip .w { color: var(--warn); }
.cloud-chip { position: relative; }
.cloud-chip.pc { border-style: dashed; }
.cc-ask { position: absolute; top: calc(100% + 8px); right: 0; z-index: 50; width: 320px; padding: 12px; border: 1px solid var(--rule); border-radius: 10px;
  background: var(--deep); color: var(--text); white-space: normal; font-size: 13px; box-shadow: 0 8px 24px rgba(0, 0, 0, .4); }
.cc-ask p { margin: 0 0 10px; line-height: 1.4; }
.cc-acts { display: flex; flex-wrap: wrap; gap: 6px; }
.cc-acts button { height: 28px; padding: 0 12px; border-radius: 14px; font-size: 12px; }
.cc-acts button.main { background: #7c3aed; color: white; }
.cc-warn { color: var(--warn); }
</style>
