<script setup lang="ts">
// «+ добавить»: a small list under the button - the LoRA of each group's library not picked yet, with a search when
// there are many; a click picks one. Esc or a click beside it closes it.
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'

export type Lib = { id: string; name: string; strength?: number }
export type Group = { key: string; label?: string; items: Lib[]; total: number }
const { t } = useI18n()
const props = defineProps<{ groups: Group[]; more?: boolean }>()
const emit = defineEmits<{ pick: [key: string, l: Lib] }>()
const open = ref(false)
const q = ref('')
const root = ref<HTMLElement | null>(null)
const search = ref<HTMLInputElement | null>(null)
const many = computed(() => props.groups.reduce((n, g) => n + g.total, 0) > 8)
const shown = computed(() => props.groups.map((g) => ({ ...g, items: g.items.filter((l) => l.name.toLowerCase().includes(q.value.trim().toLowerCase())) })))
async function toggle() {
  open.value = !open.value
  q.value = ''
  await nextTick()
  search.value?.focus()
}
function pick(key: string, l: Lib) { emit('pick', key, l); open.value = false }
const away = (e: MouseEvent) => { if (open.value && root.value && !root.value.contains(e.target as Node)) open.value = false }
const esc = (e: KeyboardEvent) => { if (e.key === 'Escape' && open.value) { open.value = false; e.stopPropagation() } }
onMounted(() => { document.addEventListener('mousedown', away); document.addEventListener('keydown', esc, true) })
onUnmounted(() => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', esc, true) })
</script>

<template>
  <span ref="root" class="la">
    <button type="button" class="la-btn" :class="{ on: open }" :aria-expanded="open" @click="toggle"><Icon name="plus" :size="12" />{{ more ? t('loraset.more') : t('loraset.addShort') }}</button>
    <div v-if="open" class="la-pop">
      <input v-if="many" ref="search" v-model="q" class="field-in" :placeholder="t('loraset.search')" :aria-label="t('loraset.search')">
      <div v-for="g in shown" :key="g.key" class="la-g">
        <span v-if="g.label" class="la-gh">{{ g.label }}</span>
        <button v-for="l in g.items" :key="l.id" type="button" class="la-item" :title="l.name" @click="pick(g.key, l)">{{ l.name }}</button>
        <span v-if="!g.items.length" class="la-none">{{ g.total ? t('loraset.nothing') : t('loraset.empty') }}</span>
      </div>
    </div>
  </span>
</template>
