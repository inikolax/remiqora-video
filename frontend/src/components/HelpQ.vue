<script setup lang="ts">
// A "?" next to a field: its own entry of the help (a <dt> of the section) in a card, or the whole section without a term.
// `text` (+ `title`): the field's own explanation given right here (the beat clip's fields, the server's slider texts) - the
// same card, "more" leads to the section `id`.
import { useI18n } from 'vue-i18n'
import { S } from '../lib/store'

const { t } = useI18n()
const p = withDefaults(defineProps<{ id: string; term?: string; text?: string; title?: string }>(), { term: '', text: '', title: '' })

function toggle(e: MouseEvent) {
  const key = p.id + p.term + p.text
  if (S.help && S.help.key === key) { S.help = null; return }
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
  S.help = { section: p.id, term: p.term, x: r.left, y: r.bottom, key, ...(p.text ? { text: p.text, title: p.title } : {}) }
}
</script>

<template>
  <button type="button" class="q" :title="t('helpui.whatIsIt')" :aria-label="t('helpui.helpOn', { term: title || term || id })" @click.stop.prevent="toggle">?</button>
</template>
