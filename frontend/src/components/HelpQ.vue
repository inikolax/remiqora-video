<script setup lang="ts">
// A "?" next to a field: its own entry of the help (a <dt> of the section) in a card, or the whole section without a term.
import { useI18n } from 'vue-i18n'
import { S } from '../lib/store'

const { t } = useI18n()
const p = withDefaults(defineProps<{ id: string; term?: string }>(), { term: '' })

function toggle(e: MouseEvent) {
  const key = p.id + p.term
  if (S.help && S.help.key === key) { S.help = null; return }
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
  S.help = { section: p.id, term: p.term, x: r.left, y: r.bottom, key }
}
</script>

<template>
  <button type="button" class="q" :title="t('helpui.whatIsIt')" :aria-label="t('helpui.helpOn', { term: term || id })" @click.stop.prevent="toggle">?</button>
</template>
