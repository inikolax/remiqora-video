<script setup lang="ts">
// The templates window: built-in ones and the user's, each a card with the graph drawn small, what is in it, and
// «Вставить» (the canvas) or «Создать граф» (home). A template goes out as a JSON file («JSON» on its card, «Скачать
// выделенное как JSON») and comes back in from one («Загрузить из JSON»: it becomes the user's template).
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import HelpModal from '../help/HelpModal.vue'
import { banner } from '../../lib/store'
import { download, list, load, preview, summary, type Tpl } from '../../lib/templates'
import { api } from '../../lib/api'
import { currentLocale } from '../../i18n'

const props = defineProps<{ open: boolean; mode: 'insert' | 'new'; selected?: number }>()
const emit = defineEmits<{ close: []; pick: [t: Tpl | null]; save: []; export: [] }>()
const { t } = useI18n()
const all = ref<Tpl[]>([])
const q = ref('')
const fresh = ref<string | null>(null)
const fileEl = ref<HTMLInputElement | null>(null)
const busy = ref(false)

async function reload() { try { all.value = await list() } catch (e) { banner((e as Error).message) } }
watch(() => props.open, (on) => { if (on) { q.value = ''; reload() } })
defineExpose({ reload })

const shown = computed(() => {
  const w = q.value.trim().toLowerCase()
  return all.value.filter((x) => !w || (x.name + ' ' + x.about).toLowerCase().includes(w))
})
const builtin = computed(() => shown.value.filter((x) => !x.own))
const own = computed(() => shown.value.filter((x) => x.own))
const pics = computed(() => Object.fromEntries(all.value.map((x) => [x.id, preview(x)])))

async function onFile(e: Event) {
  const files = [...((e.target as HTMLInputElement).files || [])]
  ;(e.target as HTMLInputElement).value = ''
  busy.value = true
  for (const f of files) {
    try {
      const tpl = await load(f)
      fresh.value = tpl.id
      const d = tpl.dropped, lost = d && (d.nodes || d.edges)
        ? t('graph.tp.skipped', { what: [d.nodes && t('graph.tp.nodes', d.nodes), d.edges && t('graph.tp.edges', d.edges)].filter(Boolean).join(t('graph.tp.and')) }) : ''
      banner(t('graph.tp.loaded', { name: tpl.name, lost }), 'info')
    } catch (err) { banner((err as Error).message) }
  }
  busy.value = false
  await reload()
}
async function drop(tpl: Tpl) {
  if (!confirm(t('graph.tp.dropAsk', { name: tpl.name }))) return
  try { await api(`/api/graph/templates/${encodeURIComponent(tpl.id)}`, { method: 'DELETE' }); await reload() } catch (e) { banner((e as Error).message) }
}
const when = (s?: number | null) => (s ? new Date(s * 1000).toLocaleDateString(currentLocale() === 'en' ? 'en-US' : 'ru-RU', { day: 'numeric', month: 'long' }) : '')
</script>

<template>
  <HelpModal :open="open" :title="mode === 'new' ? t('graph.tp.newGraph') : t('graph.tp.title')" icon="layers" wide @close="emit('close')">
    <div class="tp">
      <div class="tp-bar">
        <input v-model="q" type="search" class="field-in" :placeholder="t('graph.tp.find')" :aria-label="t('graph.tp.findLabel')">
        <button type="button" class="btn" :disabled="busy" @click="fileEl?.click()"><Icon name="download" />{{ t('graph.tp.fromJson') }}</button>
        <input ref="fileEl" type="file" accept=".json,application/json" multiple hidden @change="onFile">
      </div>
      <div v-if="mode === 'insert'" class="tp-sel">
        <span class="muted">{{ selected ? t('graph.tp.selected', selected) : t('graph.tp.nothingSel') }}</span>
        <button type="button" class="gm-link" @click="emit('save')"><Icon name="plus" :size="13" />{{ t('graph.tp.saveAs') }}</button>
        <button type="button" class="gm-link" @click="emit('export')"><Icon name="download" :size="13" />{{ t('graph.tp.asJson') }}</button>
      </div>

      <section v-if="mode === 'new' && !q">
        <div class="tp-grid">
          <button type="button" class="tp-card tp-empty" @click="emit('pick', null)"><Icon name="plus" :size="22" /><b>{{ t('graph.tp.empty') }}</b><p>{{ t('graph.tp.emptyText') }}</p></button>
        </div>
      </section>

      <section v-if="own.length">
        <h3>{{ t('graph.tp.own') }} <small>{{ own.length }}</small></h3>
        <div class="tp-grid">
          <article v-for="tp in own" :key="tp.id" class="tp-card" :class="{ fresh: tp.id === fresh }">
            <svg class="tp-pic" :viewBox="pics[tp.id].view" aria-hidden="true">
              <path v-for="(l, i) in pics[tp.id].lines" :key="'l' + i" :d="l" />
              <rect v-for="(r, i) in pics[tp.id].rects" :key="'r' + i" :x="r.x" :y="r.y" :width="r.w" :height="r.h" rx="3" :fill="r.fill" :class="r.type" />
            </svg>
            <b>{{ tp.name }}</b><p>{{ tp.about || summary(tp) }}</p>
            <span class="tp-meta">{{ summary(tp) }}{{ tp.saved ? ` · ${when(tp.saved)}` : '' }}</span>
            <div class="tp-acts">
              <button type="button" class="btn tp-main" @click="emit('pick', tp)">{{ mode === 'new' ? t('graph.tp.create') : t('graph.tp.insert') }}</button>
              <button type="button" class="ghost" :title="t('graph.tp.asJson')" @click="download(tp.name, tp.about, tp.nodes, tp.edges)"><Icon name="download" />JSON</button>
              <button type="button" class="ghost danger-ic" :aria-label="t('graph.tp.drop')" :title="t('graph.tp.dropTitle')" @click="drop(tp)"><Icon name="trash" /></button>
            </div>
          </article>
        </div>
      </section>

      <section v-if="builtin.length">
        <h3>{{ t('graph.tp.builtin') }} <small>{{ builtin.length }}</small></h3>
        <div class="tp-grid">
          <article v-for="tp in builtin" :key="tp.id" class="tp-card">
            <svg class="tp-pic" :viewBox="pics[tp.id].view" aria-hidden="true">
              <path v-for="(l, i) in pics[tp.id].lines" :key="'l' + i" :d="l" />
              <rect v-for="(r, i) in pics[tp.id].rects" :key="'r' + i" :x="r.x" :y="r.y" :width="r.w" :height="r.h" rx="3" :fill="r.fill" :class="r.type" />
            </svg>
            <b>{{ tp.name }}</b><p>{{ tp.about }}</p>
            <span class="tp-meta">{{ summary(tp) }}</span>
            <div class="tp-acts">
              <button type="button" class="btn tp-main" @click="emit('pick', tp)">{{ mode === 'new' ? t('graph.tp.create') : t('graph.tp.insert') }}</button>
              <button type="button" class="ghost" :title="t('graph.tp.jsonEdit')" @click="download(tp.name, tp.about, tp.nodes, tp.edges)"><Icon name="download" />JSON</button>
            </div>
          </article>
        </div>
      </section>
      <p v-if="!shown.length" class="muted">{{ t('graph.tp.none', { q }) }}</p>
    </div>
    <template #foot>
      <span class="muted">{{ t('graph.tp.foot') }}</span>
    </template>
  </HelpModal>
</template>
