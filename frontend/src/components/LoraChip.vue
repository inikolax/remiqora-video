<script setup lang="ts">
// A picked LoRA as a chip whose fill is its strength (0-1.5): drag along it, ← → on the keyboard by 0.05; × or
// Delete removes it. A plain click only focuses it - a click to look at the name used to set the strength where it
// landed, and Backspace (deleting text in a field just before) took the LoRA away.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'

const MAX = 1.5
const DRAG = 4   // px the pointer moves before it is a drag, not a click
const { t } = useI18n()
const props = defineProps<{ name: string; strength: number; tag?: string }>()
const emit = defineEmits<{ 'update:strength': [v: number]; remove: [] }>()
const el = ref<HTMLElement | null>(null)
const dragging = ref(false)
let from: { x: number; y: number; id: number } | null = null
const snap = (v: number) => Math.round(Math.min(MAX, Math.max(0, v)) / 0.05) * 0.05
function at(e: PointerEvent) {
  const r = el.value!.getBoundingClientRect()
  emit('update:strength', +snap(((e.clientX - r.left) / r.width) * MAX).toFixed(2))
}
function down(e: PointerEvent) {
  if (e.button !== 0) return
  from = { x: e.clientX, y: e.clientY, id: e.pointerId }
}
// a press let go outside the chip before it became a drag never sends pointerup here: the strength follows only a
// pressed button (a mouse passing over the chip later used to set it), and leaving the chip unpressed forgets the press
function move(e: PointerEvent) {
  if (!from || e.pointerId !== from.id) return
  if (!(e.buttons & 1)) { up(); return }
  if (!dragging.value) {
    if (Math.hypot(e.clientX - from.x, e.clientY - from.y) < DRAG) return
    dragging.value = true
    el.value!.setPointerCapture(e.pointerId)
  }
  at(e)
}
function up() { from = null; dragging.value = false }
function leave() { if (!dragging.value) from = null }
function key(e: KeyboardEvent) {
  const d = e.key === 'ArrowRight' || e.key === 'ArrowUp' ? 0.05 : e.key === 'ArrowLeft' || e.key === 'ArrowDown' ? -0.05 : 0
  if (d) { e.preventDefault(); emit('update:strength', +snap(props.strength + d).toFixed(2)) }
  else if (e.key === 'Delete') { e.preventDefault(); emit('remove') }
}
</script>

<template>
  <span ref="el" class="lc" :class="{ drag: dragging }" :style="{ '--k': Math.min(1, strength / MAX) }" role="slider" tabindex="0"
    :aria-valuemin="0" :aria-valuemax="MAX" :aria-valuenow="strength" :aria-label="t('loraset.strengthOf', { x: name })" :title="t('loraset.dragTitle')"
    @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @lostpointercapture="up" @pointerleave="leave" @keydown="key">
    <small v-if="tag">{{ tag }}</small><span class="lc-name">{{ name }}</span><b>{{ (+strength).toFixed(2) }}</b>
    <button type="button" class="lc-x" :aria-label="t('loraset.remove', { x: name })" @pointerdown.stop @click.stop="emit('remove')"><Icon name="close" :size="11" /></button>
  </span>
</template>
