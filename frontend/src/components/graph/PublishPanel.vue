<script setup lang="ts">
// The output's publication panel of a beat clip: GET/PUT /api/projects/{pid}/nodes/{nid}/publish. «Копия для телефона
// (≤ 10 МБ)» with its size once made, the cover (a frame of the clip: a time slider, «Кадр удара» = the drop), the text for
// the publication (title + hashtags; the server removes drug-hint words and says so) and the downloads.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import BeatHelp from '../BeatHelp.vue'
import { GE, adoptSaved, fileUrl, flush } from '../../lib/graphDoc'
import { api } from '../../lib/api'
import { banner } from '../../lib/store'
import type { PublishView } from '../../lib/beat'
import { dec } from '../../lib/format'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const url = computed(() => `/api/projects/${GE.id}/nodes/${props.id}/publish`)
const v = ref<PublishView | null>(null)
const state = computed(() => GE.state?.nodes[props.id])

async function load() {
  try { await flush(); v.value = await api<PublishView>(url.value) } catch { v.value = null }
}
let pending: Record<string, any> = {}
let timer = 0
function patch(p: Record<string, any>, now = false) {
  Object.assign(pending, p)
  clearTimeout(timer)
  timer = window.setTimeout(send, now ? 0 : 400)
}
async function send() {
  const body = pending
  pending = {}
  if (!Object.keys(body).length) return
  try {
    const r = await api<PublishView>(url.value, { method: 'PUT', body })
    await adoptSaved(props.id, r.graph_rev, r.node_data)
    if (!Object.keys(pending).length) v.value = r
  } catch (e) { banner((e as Error).message) }
}
onMounted(load)
watch(() => [props.id, GE.id], load)
// the clip was made again: its phone copy and cover are new
watch(() => [state.value?.state, state.value?.seconds], load)
onBeforeUnmount(() => { clearTimeout(timer); if (Object.keys(pending).length) send() })

const at = computed(() => (v.value ? v.value.cover_at ?? v.value.drop ?? 0 : 0))
function setAt(s: number) { if (v.value) v.value.cover_at = s; patch({ cover_at: s }) }
const atDrop = () => { if (v.value?.drop != null) { setAt(v.value.drop); clearTimeout(timer); send() } }
const stamp = computed(() => `?at=${v.value?.cover_at ?? ''}&m=${v.value?.phone_mb ?? ''}`)
</script>

<template>
  <div v-if="v" class="pb">
    <span class="lbl">{{ t('beat.pub.title') }}</span>

    <label class="check-row"><input type="checkbox" :checked="v.phone" @change="v.phone = ($event.target as HTMLInputElement).checked; patch({ phone: v.phone }, true)">{{ t('beat.pub.phone') }} <BeatHelp k="phone" /></label>
    <p v-if="v.phone" class="muted small">{{ v.phone_file ? t('beat.pub.phoneSize', { mb: dec((v.phone_mb ?? 0).toFixed(1)) }) : t('beat.pub.phoneLater') }}</p>
    <a v-if="v.phone && v.phone_file" class="btn" :href="fileUrl(v.phone_file)!" :download="`${GE.proj?.name || 'beat'}-phone.mp4`"><Icon name="download" />{{ t('beat.pub.phoneDl') }}</a>

    <label class="check-row"><input type="checkbox" :checked="v.cover" @change="v.cover = ($event.target as HTMLInputElement).checked; patch({ cover: v.cover }, true)">{{ t('beat.pub.cover') }} <BeatHelp k="cover" /></label>
    <template v-if="v.cover">
      <img v-if="v.cover_file" class="pb-cover" :src="fileUrl(v.cover_file)! + stamp" :alt="t('beat.pub.cover')">
      <p v-else class="muted small">{{ t('beat.pub.coverLater') }}</p>
      <div v-if="v.duration" class="stack"><span class="lbl">{{ t('beat.pub.coverAt') }} <small>{{ dec(at.toFixed(2)) }} {{ t('common.s') }}</small></span>
        <input type="range" min="0" :max="v.duration" step="0.04" :value="at" :aria-label="t('beat.pub.coverAt')" @input="setAt(+($event.target as HTMLInputElement).value)"></div>
      <div class="ni-row">
        <button type="button" class="btn" :disabled="v.drop == null" :title="t('beat.pub.hitTitle')" @click="atDrop"><Icon name="wave" />{{ t('beat.pub.hit') }}</button>
        <a v-if="v.cover_file" class="btn" :href="fileUrl(v.cover_file)!" :download="`${GE.proj?.name || 'beat'}-cover.png`"><Icon name="download" />{{ t('beat.pub.coverDl') }}</a></div>
    </template>

    <label class="stack"><span class="lbl">{{ t('beat.pub.text') }} <BeatHelp k="pubText" /></span>
      <textarea class="field-in" rows="4" :value="v.text" :placeholder="t('beat.pub.textPh')" @input="v.text = ($event.target as HTMLTextAreaElement).value; patch({ text: v.text })" /></label>
    <p v-if="v.removed" class="muted small">{{ t('beat.cleaned') }}</p>
  </div>
</template>

<style scoped>
.pb { display: flex; flex-direction: column; gap: 8px; padding-top: 6px; border-top: 1px solid var(--rule); }
.pb-cover { width: 100%; max-width: 200px; aspect-ratio: 9 / 16; object-fit: cover; border-radius: 8px; background: #000; }
</style>
