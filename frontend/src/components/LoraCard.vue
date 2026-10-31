<script setup lang="ts">
// The new video's LoRA in one card under «Модель»: folded, a line of what is picked for each of the three; open, a
// row each - the video (its model's, every scene), the portraits (Krea 2: the heroes, the places), the scene frames
// (FLUX.2 Klein) - with the picks as chips whose fill is the strength (LoraChip) and «+ добавить» (LoraAdd). A row
// whose pictures are not drawn after the script (`off`) dims and says so; its picks stay.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import LoraChip from './LoraChip.vue'
import LoraAdd, { type Lib } from './LoraAdd.vue'
import type { PicLoras, Pick } from './LoraSet.vue'
import { S, loadKreaLoras, lorasFor } from '../lib/store'

type Key = 'video' | 'krea' | 'flux2'
const { t } = useI18n()
const props = defineProps<{ video: string; loras: Pick[]; pics: PicLoras; off?: { krea?: boolean; flux2?: boolean } }>()
const emit = defineEmits<{ 'update:loras': [v: Pick[]]; 'update:pics': [v: PicLoras] }>()
onMounted(loadKreaLoras)
const open = ref(false)

const modelName = computed(() => S.cfg?.video_models?.find((m: any) => m.id === props.video)?.name || props.video)
const libOf = (k: Key): Lib[] => (k === 'video' ? lorasFor(props.video) : k === 'krea' ? S.kreaLoras : lorasFor('flux2')).filter((l) => l.verdict !== 'blocked')
const listOf = (k: Key): Pick[] => (k === 'video' ? props.loras : props.pics[k]) || []
const rows = computed(() => (['video', 'krea', 'flux2'] as Key[]).map((k) => ({
  k, list: listOf(k), lib: libOf(k), off: k !== 'video' && !!props.off?.[k],
  title: t(`loraset.row.${k}`), sub: k === 'video' ? t('loraset.row.videoSub', { m: modelName.value }) : t(`loraset.row.${k}Sub`),
})))
const picked = computed(() => rows.value.reduce((n, r) => n + r.list.length, 0))
function put(k: Key, list: Pick[]) {
  if (k === 'video') emit('update:loras', list)
  else emit('update:pics', { ...props.pics, [k]: list })
}
const add = (k: Key, l: Lib) => put(k, [...listOf(k), { id: l.id, name: l.name, strength: l.strength ?? 0.8 }])
const setStrength = (k: Key, id: string, v: number) => put(k, listOf(k).map((u) => (u.id === id ? { ...u, strength: v } : u)))
const remove = (k: Key, id: string) => put(k, listOf(k).filter((u) => u.id !== id))
</script>

<template>
  <section class="lcard" :class="{ open }">
    <button type="button" class="lcard-head" :aria-expanded="open" @click="open = !open">
      <Icon name="layers" :size="16" /><b>LoRA</b><span class="lcard-sub">{{ t('loraset.cardSub') }}</span><span class="grow" />
      <span v-if="!open && picked" class="lcard-n">{{ picked }}</span><i class="lcard-chev" aria-hidden="true" /></button>
    <!-- folded: what is picked, a pill per row -->
    <div v-if="!open" class="lcard-sum">
      <button v-for="r in rows" :key="r.k" type="button" class="lcard-pill" :class="{ on: r.list.length, off: r.off }" :title="r.sub" @click="open = true">
        {{ r.title }}: {{ r.list.length ? r.list.map((x) => x.name).join(', ') : t('loraset.none') }}</button>
    </div>
    <div v-else class="lcard-rows">
      <div v-for="r in rows" :key="r.k" class="lcard-row" :class="{ off: r.off }">
        <div class="lcard-who"><b>{{ r.title }}</b><small>{{ r.off ? t('loraset.row.off') : r.sub }}</small></div>
        <div class="lcard-chips">
          <LoraChip v-for="u in r.list" :key="u.id" :name="u.name" :strength="u.strength" @update:strength="setStrength(r.k, u.id, $event)" @remove="remove(r.k, u.id)" />
          <LoraAdd :groups="[{ key: r.k, items: r.lib.filter((l) => !r.list.some((u) => u.id === l.id)), total: r.lib.length }]" :more="!!r.list.length" @pick="(_k, l) => add(r.k, l)" />
        </div>
      </div>
      <p class="lcard-note">{{ t('loraset.cardNote') }}</p>
    </div>
  </section>
</template>
