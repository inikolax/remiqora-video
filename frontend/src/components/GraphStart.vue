<script setup lang="ts">
// The home's second way to start, under «Что снимаем?»: «Или соберите на холсте» - the graph with its templates right
// there (an empty canvas, the user's two newest, then the built-in ones in their order, each drawn small, «Все
// шаблоны»). One click on a card makes the graph and opens its canvas; the frame, the model and an optional name stand
// above the cards. «Все шаблоны» opens the templates window (search, JSON, deleting one's own).
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import GuideButton from './help/GuideButton.vue'
import TemplatesModal from './graph/TemplatesModal.vue'
import { post } from '../lib/api'
import { S, banner, keep, pickVideo } from '../lib/store'
import { list, preview, type Tpl } from '../lib/templates'
import type { VideoModel } from '../lib/types'

const router = useRouter()
const { t, locale } = useI18n()
const f = S.form
const set = (k: keyof typeof f, v: any) => { (f as any)[k] = v; keep() }

const all = ref<Tpl[]>([])
const own = computed(() => all.value.filter((x) => x.own))
const builtin = computed(() => all.value.filter((x) => !x.own))
// six cards besides the empty canvas and «Все шаблоны»: two rows of four on a wide screen
const row = computed(() => [...[...own.value].sort((a, b) => (b.saved || 0) - (a.saved || 0)).slice(0, 2), ...builtin.value].slice(0, 6))
const pics = computed(() => Object.fromEntries(row.value.map((x) => [x.id, preview(x)])))
const load = async () => { try { all.value = await list() } catch (e) { banner((e as Error).message) } }
onMounted(load)
// the built-in templates have an English twin: after RU ↔ EN the cards (and the graph a click makes) in the new language
watch(locale, load)

const name = ref('')
const aspect = computed(() => (['16:9', '9:16', '1:1'].includes(f.aspect) ? f.aspect : '16:9'))
const models = computed<VideoModel[]>(() => (S.cfg?.video_models || []).filter((m) => !m.imported))
const model = computed(() => pickVideo(f.video))
const tplOpen = ref(false)
const busy = ref('')   // the card being created
async function create(tpl: Tpl | null) {
  if (busy.value) return
  busy.value = tpl?.id || 'empty'
  try {
    const r = await post('/api/graphs', { name: name.value.trim().slice(0, 60) || tpl?.name || t('idea.graph'), aspect: aspect.value, template: tpl?.id || null, video_model: model.value })
    tplOpen.value = false
    router.push(`/g/${r.project}`)
  } catch (e) { banner((e as Error).message); busy.value = '' }
}
</script>

<template>
  <section class="gs-home" :aria-labelledby="'gs-h'">
    <div class="gs-head">
      <h2 id="gs-h"><Icon name="layers" :size="20" />{{ t('home.canvas') }}</h2>
      <p class="gs-about">{{ t('home.canvasAbout') }}</p>
      <GuideButton guide="graph-edit" class="gs-guide" />
    </div>
    <div class="gs-opts">
      <span class="gs-opt"><span class="lbl"><Icon name="wide" :size="14" />{{ t('idea.frame') }}</span>
        <span class="chips" role="radiogroup" :aria-label="t('idea.frame')"><button v-for="a in ['16:9', '9:16', '1:1']" :key="a" type="button" role="radio" :aria-checked="aspect === a" class="chip" :class="{ on: aspect === a }" @click="set('aspect', a)">{{ a }}</button></span></span>
      <label class="gs-opt"><span class="lbl"><Icon name="chip" :size="14" />{{ t('home.canvasModel') }}</span>
        <select class="field-in gs-sel" :value="model" @change="set('video', ($event.target as HTMLSelectElement).value)">
          <option v-for="m in models" :key="m.id" :value="m.id" :disabled="m.missing.length > 0 && m.id !== model">{{ m.name }}{{ m.missing.length ? ` · ${t('idea.pick.noWeights')}` : '' }}</option></select></label>
      <label class="gs-opt gs-name"><span class="lbl">{{ t('home.canvasName') }} <small>{{ t('idea.optional') }}</small></span>
        <input v-model="name" class="field-in" :placeholder="t('idea.graphNamePh')"></label>
    </div>
    <div class="gs-cards">
      <button type="button" class="tp-card gs-card gs-empty" :disabled="!!busy" :aria-label="t('home.canvasOpen', { name: t('idea.tplEmpty') })" @click="create(null)">
        <span class="tp-pic gs-plus"><Icon name="plus" :size="22" /></span><b>{{ busy === 'empty' ? t('home.canvasBusy') : t('idea.tplEmpty') }}</b><p>{{ t('idea.tplEmptySub') }}</p></button>
      <button v-for="tp in row" :key="tp.id" type="button" class="tp-card gs-card" :disabled="!!busy" :title="tp.about" :aria-label="t('home.canvasOpen', { name: tp.name })" @click="create(tp)">
        <svg class="tp-pic" :viewBox="pics[tp.id].view" aria-hidden="true">
          <path v-for="(l, i) in pics[tp.id].lines" :key="'l' + i" :d="l" />
          <rect v-for="(r, i) in pics[tp.id].rects" :key="'r' + i" :x="r.x" :y="r.y" :width="r.w" :height="r.h" rx="3" :fill="r.fill" :class="r.type" />
        </svg>
        <b>{{ busy === tp.id ? t('home.canvasBusy') : tp.name }}</b><p><small v-if="tp.own" class="gs-own">{{ t('idea.tplOwn') }}</small>{{ tp.about }}</p></button>
      <button type="button" class="tp-card gs-card gs-all" :disabled="!!busy" @click="tplOpen = true">
        <Icon name="layers" :size="20" /><b>{{ t('idea.tplAll') }}</b><p>{{ t('idea.tplAllSub', { b: builtin.length, o: own.length }) }}</p></button>
    </div>
    <TemplatesModal :open="tplOpen" mode="new" @close="tplOpen = false" @pick="create" />
  </section>
</template>

<style scoped>
.gs-home { container-type: inline-size; display: flex; flex-direction: column; gap: 14px; padding: 20px 26px 22px; border-radius: 18px; border: 1px solid var(--rule-2); background: var(--panel); }
.gs-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; }
.gs-head h2 { display: inline-flex; align-items: center; gap: 9px; margin: 0; font-size: 22px; font-weight: 600; }
.gs-head h2 :deep(svg) { color: var(--accent-hi); }
.gs-about { flex: 1 1 420px; margin: 0; color: var(--soft); font-size: 14px; }
.gs-guide { margin-left: auto; }
.gs-opts { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 22px; }
.gs-opt { display: inline-flex; align-items: center; gap: 10px; }
.gs-opt .lbl { display: inline-flex; align-items: center; gap: 5px; margin: 0; }
.gs-sel { width: auto; min-height: 36px; padding: 0 10px; }
.gs-name { flex: 1 1 220px; }
.gs-name .field-in { flex: 1; min-width: 0; min-height: 36px; }
.gs-cards { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 10px; }
.gs-card { min-height: 44px; border: 1px solid var(--rule-2); background: var(--deep); }
.gs-card:hover:not(:disabled) { border-color: var(--accent); }
.gs-card:disabled { cursor: progress; opacity: .7; }
@container (max-width: 1100px) { .gs-cards { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
@container (max-width: 480px) {
  .gs-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .gs-head h2 { font-size: 20px; }
  .gs-opt { flex-wrap: wrap; }
  .gs-name { flex: 1 1 100%; }
}
@media (max-width: 760px) { .gs-home { padding: 16px; } }
</style>
