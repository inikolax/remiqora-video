<script setup lang="ts">
// A beat clip's shot on the canvas: its role (hero / atmos / close / impact / riser) as a select and its framing as a
// small badge (data.role, data.framing of a scene node made by «Развернуть» of the pool writer). A change of the role is
// a plain graph save. Shown only when the scene has a role.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { nodeOf, touch } from '../../lib/graphDoc'
import { ROLES } from '../../lib/beat'

const props = defineProps<{ id: string; compact?: boolean }>()
const { t } = useI18n()
const d = computed(() => (nodeOf(props.id)?.data || {}) as Record<string, any>)
function setRole(e: Event) { const n = nodeOf(props.id); if (!n) return; (n.data as any).role = (e.target as HTMLSelectElement).value; touch() }
</script>

<template>
  <div v-if="d.role" class="rs-role nodrag nopan" :class="{ compact }">
    <select class="rs-sel" :value="d.role" :aria-label="t('beat.role.lbl')" :title="t('beat.role.hint')" @change="setRole" @pointerdown.stop @mousedown.stop>
      <option v-for="r in ROLES" :key="r" :value="r">{{ t(`beat.role.${r}`) }}</option></select>
    <span v-if="d.framing" class="rs-fr" :title="t('beat.framing.lbl')">{{ t(`beat.framing.${d.framing}`) }}</span>
  </div>
</template>

<style scoped>
.rs-role { display: flex; align-items: center; gap: 6px; margin: 4px 0 2px; }
.rs-role.compact { margin: 8px 10px 0; }
.rs-sel { min-width: 0; max-width: 100%; padding: 2px 6px; border-radius: 6px; border: 1px solid var(--rule-input); background: var(--field); color: var(--text); font: inherit; font-size: 12px; }
.rs-fr { padding: 1px 7px; border-radius: 99px; background: var(--accent-bg); color: var(--accent-hi); font-size: 11px; white-space: nowrap; }
.rs-role:not(.compact) .rs-sel { font-size: 13px; padding: 5px 8px; }
</style>
