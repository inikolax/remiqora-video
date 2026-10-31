<script setup lang="ts">
// The LoRA of a video: the model's that shoots it (settings.loras) and «LoRA картинок» (settings.pic_loras) - Krea 2's
// for the heroes' portraits and the places, FLUX.2 Klein's for the scenes' start frames (app/picture.project_loras).
// The new video's forms show all of it folded; the board's shooting panel only the pictures' (its own LoRA is above).
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { S, loadKreaLoras, lorasFor } from '../lib/store'

export type Pick = { id: string; name: string; strength: number }
export type PicLoras = { krea?: Pick[]; flux2?: Pick[] }
const { t } = useI18n()
const props = defineProps<{ video?: string; loras?: Pick[]; pics: PicLoras; picsOnly?: boolean }>()
const emit = defineEmits<{ 'update:loras': [v: Pick[]]; 'update:pics': [v: PicLoras] }>()
onMounted(loadKreaLoras)

const groups = computed(() => [
  ...(props.picsOnly ? [] : [{ k: 'video', label: t('loraset.video'), list: props.loras || [], lib: lorasFor(props.video || 'h3') }]),
  { k: 'krea', label: t('loraset.krea'), list: props.pics.krea || [], lib: S.kreaLoras },
  { k: 'flux2', label: t('loraset.flux2'), list: props.pics.flux2 || [], lib: lorasFor('flux2') },
])
const count = computed(() => groups.value.reduce((n, g) => n + g.list.length, 0))
function put(k: string, list: Pick[]) {
  if (k === 'video') emit('update:loras', list)
  else emit('update:pics', { ...props.pics, [k]: list })
}
function add(k: string, lib: { id: string; name: string; strength?: number }[], cur: Pick[], e: Event) {
  const sel = e.target as HTMLSelectElement
  const l = lib.find((x) => x.id === sel.value)
  sel.value = ''
  if (l) put(k, [...cur, { id: l.id, name: l.name, strength: l.strength ?? 0.8 }])
}
const rest = (lib: { id: string; name: string; verdict: string }[], cur: Pick[]) => lib.filter((l) => l.verdict !== 'blocked' && !cur.some((u) => u.id === l.id))
</script>

<template>
  <div class="ls">
    <div v-for="g in groups" :key="g.k" class="ls-g">
      <div class="sec-head"><span class="lbl">{{ g.label }}</span>
        <select v-if="rest(g.lib, g.list).length" class="ghost" :aria-label="t('loraset.add', { x: g.label })" value="" @change="add(g.k, g.lib, g.list, $event)">
          <option value="">{{ t('loraset.fromLibrary') }}</option><option v-for="l in rest(g.lib, g.list)" :key="l.id" :value="l.id">{{ l.name }}</option></select>
        <span v-else-if="!g.lib.length" class="muted ls-none">{{ t('loraset.empty') }}</span></div>
      <div v-for="(u, i) in g.list" :key="u.id" class="lora"><span :title="u.name">{{ u.name }}</span>
        <input type="range" min="0" max="1.5" step="0.05" :value="u.strength" :aria-label="t('loraset.strengthOf', { x: u.name })"
          @change="put(g.k, g.list.map((x, j) => (j === i ? { ...x, strength: +($event.target as HTMLInputElement).value } : x)))">
        <b>{{ (+u.strength).toFixed(2) }}</b><button type="button" :aria-label="t('loraset.remove', { x: u.name })" @click="put(g.k, g.list.filter((_, j) => j !== i))">×</button></div>
    </div>
    <slot :count="count" />
  </div>
</template>
