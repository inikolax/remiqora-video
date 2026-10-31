<script setup lang="ts">
// The home's «Граф»: the templates right in the form - an empty canvas, the user's two newest, then the built-in ones
// in their order, each drawn small. A click picks one, «Создать граф» (or a double click) opens the canvas;
// «Все шаблоны» opens the templates window (search, JSON, deleting one's own). The name, the frame and the model stand
// on the right, as in the other ways to start.
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import HelpQ from './HelpQ.vue'
import GuideButton from './help/GuideButton.vue'
import ModelPick from './ModelPick.vue'
import TemplatesModal from './graph/TemplatesModal.vue'
import { post } from '../lib/api'
import { S, banner, keep } from '../lib/store'
import { ASPECTS } from '../lib/consts'
import { list, preview, type Tpl } from '../lib/templates'

const router = useRouter()
const { t } = useI18n()
const f = S.form
const set = (k: keyof typeof f, v: any) => { (f as any)[k] = v; keep() }

const all = ref<Tpl[]>([])
const own = computed(() => all.value.filter((x) => x.own))
const builtin = computed(() => all.value.filter((x) => !x.own))
// seven cards besides the empty canvas and «Все шаблоны»: two rows of four on a wide screen
const row = computed(() => [...[...own.value].sort((a, b) => (b.saved || 0) - (a.saved || 0)).slice(0, 2), ...builtin.value].slice(0, 6))
const pics = computed(() => Object.fromEntries(row.value.map((x) => [x.id, preview(x)])))
const pick = ref<string | null>(null)   // null: the empty canvas
const picked = computed(() => all.value.find((x) => x.id === pick.value) || null)
onMounted(async () => { try { all.value = await list() } catch (e) { banner((e as Error).message) } })

const tplOpen = ref(false)
const busy = ref(false)
async function create(tpl: Tpl | null) {
  busy.value = true
  try {
    const r = await post('/api/graphs', { name: f.idea.trim().slice(0, 60) || tpl?.name || t('idea.graph'), aspect: f.aspect, template: tpl?.id || null, video_model: f.video || 'h3' })
    tplOpen.value = false
    router.push(`/g/${r.project}`)
  } catch (e) { banner((e as Error).message); busy.value = false }
}
</script>

<template>
  <div class="idea-head sf-head"><div class="title-row"><h1>{{ t('idea.graph') }}</h1><GuideButton guide="graph-edit" /></div>
    <p>{{ t('idea.graphAbout') }}</p></div>

  <div class="sf-main">
    <div class="gs-grid" role="radiogroup" :aria-label="t('idea.how.graphLong')">
      <button type="button" role="radio" :aria-checked="pick === null" class="tp-card gs-card gs-empty" :class="{ on: pick === null }"
        @click="pick = null" @dblclick="create(null)">
        <span class="tp-pic gs-plus"><Icon name="plus" :size="22" /></span><b>{{ t('idea.tplEmpty') }}</b><p>{{ t('idea.tplEmptySub') }}</p></button>
      <button v-for="tp in row" :key="tp.id" type="button" role="radio" :aria-checked="pick === tp.id" class="tp-card gs-card" :class="{ on: pick === tp.id }"
        :title="tp.about" @click="pick = tp.id" @dblclick="create(tp)">
        <svg class="tp-pic" :viewBox="pics[tp.id].view" aria-hidden="true">
          <path v-for="(l, i) in pics[tp.id].lines" :key="'l' + i" :d="l" />
          <rect v-for="(r, i) in pics[tp.id].rects" :key="'r' + i" :x="r.x" :y="r.y" :width="r.w" :height="r.h" rx="3" :fill="r.fill" :class="r.type" />
        </svg>
        <b>{{ tp.name }}</b><p><small v-if="tp.own" class="gs-own">{{ t('idea.tplOwn') }}</small>{{ tp.about }}</p></button>
      <button type="button" class="tp-card gs-card gs-all" @click="tplOpen = true">
        <Icon name="layers" :size="20" /><b>{{ t('idea.tplAll') }}</b><p>{{ t('idea.tplAllSub', { b: builtin.length, o: own.length }) }}</p></button>
    </div>
  </div>

  <div class="sf-side">
    <label class="stack"><span class="lbl">{{ t('idea.name') }} <small>{{ t('idea.optional') }}</small></span>
      <input class="field-in" :value="f.idea" :placeholder="picked?.name || t('idea.graphNamePh')" @input="set('idea', ($event.target as HTMLInputElement).value)"></label>
    <div class="stack"><span class="lbl">{{ t('idea.frame') }} <HelpQ id="idea" term="Кадр" /></span>
      <div class="chips"><button v-for="[a, w, h] in ASPECTS" :key="a" type="button" class="chip" :class="{ on: f.aspect === a }" @click="set('aspect', a)"><i class="box" :style="{ width: w + 'px', height: h + 'px' }" />{{ a }}</button></div></div>
    <div class="stack"><span class="lbl">{{ t('idea.model') }} <small>{{ t('idea.modelLater') }}</small></span><ModelPick :model-value="f.video" compact @update:model-value="set('video', $event)" /></div>
  </div>

  <div class="sf-foot">
    <span class="foot-note">{{ t('idea.createNote') }}</span>
    <button type="button" class="primary" :disabled="busy" @click="create(picked)"><Icon name="layers" />{{ t('idea.createGraph') }}</button>
  </div>
  <TemplatesModal :open="tplOpen" mode="new" @close="tplOpen = false" @pick="create" />
</template>
