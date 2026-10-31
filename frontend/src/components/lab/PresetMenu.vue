<script setup lang="ts">
// «Заготовка ▾»: the whole-prompt presets of lib/presets.ts by group, in the open tab's language. Fixed to the window,
// so the bench's scroll doesn't clip it; a click outside, Escape or a pick closes it.
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import type { Preset } from '../../lib/presets'
import { presets } from '../../lib/content'

const { t } = useI18n()
defineProps<{ hasFrame: boolean }>()
const emit = defineEmits<{ pick: [p: Preset] }>()
const open = ref(false)
const btn = ref<HTMLElement | null>(null)
const pop = ref<HTMLElement | null>(null)
const pos = ref<Record<string, string>>({})
const groups = computed(() => [...new Set(presets().map((p) => p.group))])

async function toggle() {
  open.value = !open.value
  if (!open.value) return
  const r = btn.value!.getBoundingClientRect(), down = innerHeight - r.bottom > 360 || r.top < 360
  pos.value = { left: `${Math.max(16, Math.min(r.left, innerWidth - 376))}px`, top: down ? `${r.bottom + 6}px` : '', bottom: down ? '' : `${innerHeight - r.top + 6}px`,
    maxHeight: `${Math.max(240, (down ? innerHeight - r.bottom : r.top) - 24)}px` }
  await nextTick()
  pop.value?.querySelector<HTMLElement>('button')?.focus()
}
function pick(p: Preset) { open.value = false; emit('pick', p); }
const outside = (e: MouseEvent) => { if (open.value && !pop.value?.contains(e.target as Node) && !btn.value?.contains(e.target as Node)) open.value = false }
const esc = (e: KeyboardEvent) => { if (e.key === 'Escape' && open.value) { open.value = false; btn.value?.focus() } }
onMounted(() => { document.addEventListener('click', outside); document.addEventListener('keydown', esc) })
onUnmounted(() => { document.removeEventListener('click', outside); document.removeEventListener('keydown', esc) })
</script>

<template>
  <button ref="btn" class="ghost" type="button" aria-haspopup="menu" :aria-expanded="open" :title="t('lab.preset.title')" @click="toggle">
    <Icon name="pen" />{{ t('lab.preset.name') }}<span class="caret" aria-hidden="true">▾</span></button>
  <div v-if="open" ref="pop" class="preset-pop" role="menu" :aria-label="t('lab.preset.aria')" :style="pos">
    <section v-for="g in groups" :key="g" class="preset-group">
      <h3>{{ g }}</h3>
      <button v-for="p in presets().filter((x) => x.group === g)" :key="p.id" type="button" role="menuitem" class="preset-item" @click="pick(p)">
        <span class="preset-name">{{ p.name }}<small>{{ t('lab.secsN', { s: p.seconds }) }}</small></span>
        <span class="preset-hint" :class="{ warn: p.frame && !hasFrame }">{{ p.frame && !hasFrame ? t('lab.preset.needFrame') : p.hint }}</span>
      </button>
    </section>
  </div>
</template>
