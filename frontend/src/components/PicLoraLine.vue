<script setup lang="ts">
// «LoRA картинок» next to the buttons that draw: the picks as chips whose fill is the strength (LoraChip), «+ добавить»
// with the libraries of the models drawing here (LoraAdd). They are the project's settings.pic_loras, the same as in
// the shooting panel, saved at once - or, in a new video's form, the form's picks (`pics`, «update:pics»).
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import LoraChip from './LoraChip.vue'
import LoraAdd, { type Lib } from './LoraAdd.vue'
import type { PicLoras, Pick } from './LoraSet.vue'
import { P, scheduleSave } from '../lib/project'
import { S, loadKreaLoras, lorasFor } from '../lib/store'

type Model = 'krea' | 'flux2'
const { t } = useI18n()
const props = defineProps<{ models: Model[]; pics?: PicLoras; hint?: string }>()
const emit = defineEmits<{ 'update:pics': [v: PicLoras] }>()
onMounted(loadKreaLoras)

const pics = computed<PicLoras>(() => props.pics || ((P.proj?.settings.pic_loras || {}) as PicLoras))
const chips = computed(() => props.models.flatMap((m) => (pics.value[m] || []).map((x) => ({ m, x }))))
const lib = (m: Model): Lib[] => (m === 'krea' ? S.kreaLoras : lorasFor('flux2')).filter((l) => l.verdict !== 'blocked')
const groups = computed(() => props.models.map((m) => ({
  key: m, label: props.models.length > 1 ? t(`loraset.${m}`) : undefined, total: lib(m).length,
  items: lib(m).filter((l) => !(pics.value[m] || []).some((u) => u.id === l.id)),
})))
function put(m: Model, list: Pick[]) {
  const v = { ...pics.value, [m]: list }
  if (props.pics) { emit('update:pics', v); return }
  if (!P.proj) return
  P.proj.settings.pic_loras = v
  scheduleSave('settings')
}
const add = (m: string, l: Lib) => put(m as Model, [...(pics.value[m as Model] || []), { id: l.id, name: l.name, strength: l.strength ?? 0.8 }])
const setStrength = (m: Model, id: string, v: number) => put(m, (pics.value[m] || []).map((u) => (u.id === id ? { ...u, strength: v } : u)))
const remove = (m: Model, id: string) => put(m, (pics.value[m] || []).filter((u) => u.id !== id))
</script>

<template>
  <div class="plr" :class="{ boxed: !!hint }">
    <div v-if="hint" class="plr-head"><b><Icon name="layers" :size="15" />LoRA</b><span>{{ hint }}</span></div>
    <span v-else class="plr-lbl" :title="t('loraset.lineTitle', { m: models.map((m) => t(`loraset.short.${m}`)).join(', ') })"><Icon name="layers" :size="13" />LoRA</span>
    <LoraChip v-for="c in chips" :key="c.m + c.x.id" :name="c.x.name" :strength="c.x.strength" :tag="models.length > 1 ? t(`loraset.short.${c.m}`) : undefined"
      @update:strength="setStrength(c.m, c.x.id, $event)" @remove="remove(c.m, c.x.id)" />
    <LoraAdd :groups="groups" :more="!!chips.length" @pick="add" />
  </div>
</template>
