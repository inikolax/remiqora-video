<script setup lang="ts">
// A help window over the screen (after Remiqora's HelpModal): a dimmed backdrop, a panel with its title and a round
// close button, the body scrolling inside. Esc and a click on the backdrop close it; focus goes in and comes back.
import { nextTick, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'

const props = defineProps<{ open: boolean; title: string; icon?: string; wide?: boolean; narrow?: boolean; gradient?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const panel = ref<HTMLElement | null>(null)
let before: HTMLElement | null = null

function onKey(e: KeyboardEvent) {
  if (!props.open) return
  if (e.key === 'Escape') { e.stopPropagation(); emit('close'); return }
  if (e.key !== 'Tab' || !panel.value) return
  // focus stays inside the window
  const f = [...panel.value.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])')]
  if (!f.length) return
  if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus() }
  else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus() }
}
watch(() => props.open, async (on) => {
  if (on) {
    before = document.activeElement as HTMLElement | null
    document.addEventListener('keydown', onKey, true)
    document.body.classList.add('modal-open')
    await nextTick()
    panel.value?.focus()
  } else {
    document.removeEventListener('keydown', onKey, true)
    document.body.classList.remove('modal-open')
    before?.focus?.()
  }
}, { immediate: true })
onUnmounted(() => { document.removeEventListener('keydown', onKey, true); document.body.classList.remove('modal-open') })
</script>

<template>
  <Teleport to="body">
    <Transition name="hm-fade">
      <div v-if="open" class="hm-back" @click.self="emit('close')">
        <div ref="panel" class="hm-panel" :class="{ wide, narrow }" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1">
          <header class="hm-head">
            <span v-if="icon" class="hm-icon"><Icon :name="icon" :size="18" /></span>
            <h2 :class="{ grad: gradient }">{{ title }}</h2>
            <button type="button" class="hm-close" :aria-label="t('common.close')" :title="t('helpui.closeEsc')" @click="emit('close')"><Icon name="close" :size="15" /></button>
          </header>
          <div class="hm-body"><slot /></div>
          <footer v-if="$slots.foot" class="hm-foot"><slot name="foot" /></footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
