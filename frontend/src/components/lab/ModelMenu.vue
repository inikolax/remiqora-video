<script setup lang="ts">
// «H3 ▾» on the monitor's readout: the model that shoots, its name on the button and the cards of ModelPick in a list
// that drops down from it. Fixed to the window like «Заготовка ▾»; a click outside, Escape or a pick closes it.
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ModelPick from '../ModelPick.vue'
import { modelName } from '../../lib/store'

const { t } = useI18n()
const model = defineModel<string>({ required: true })
const open = ref(false)
const btn = ref<HTMLElement | null>(null)
const pop = ref<HTMLElement | null>(null)
const pos = ref<Record<string, string>>({})

async function toggle() {
  open.value = !open.value
  if (!open.value) return
  const r = btn.value!.getBoundingClientRect()
  pos.value = { left: `${Math.max(16, Math.min(r.left, innerWidth - 396))}px`, top: `${r.bottom + 6}px`, maxHeight: `${Math.max(240, innerHeight - r.bottom - 24)}px` }
  await nextTick()
  pop.value?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus()
}
function pick(id: string) { model.value = id; open.value = false; btn.value?.focus() }
const outside = (e: MouseEvent) => { if (open.value && !pop.value?.contains(e.target as Node) && !btn.value?.contains(e.target as Node)) open.value = false }
const esc = (e: KeyboardEvent) => { if (e.key === 'Escape' && open.value) { open.value = false; btn.value?.focus() } }
onMounted(() => { document.addEventListener('click', outside); document.addEventListener('keydown', esc) })
onUnmounted(() => { document.removeEventListener('click', outside); document.removeEventListener('keydown', esc) })
</script>

<template>
  <button ref="btn" class="model-btn" type="button" aria-haspopup="dialog" :aria-expanded="open" :title="t('lab.modelTitle')" @click="toggle">
    {{ modelName(model) }}<span class="caret" aria-hidden="true">▾</span></button>
  <div v-if="open" ref="pop" class="model-pop" role="dialog" :aria-label="t('lab.model')" :style="pos">
    <ModelPick :model-value="model" compact @update:model-value="pick" />
  </div>
</template>
