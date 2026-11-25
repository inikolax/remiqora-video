<script setup lang="ts">
// A "?" of the beat clip's fields: its own words (locales/beat.ts q.<k>.t / .d) in the help card, in place.
import { useI18n } from 'vue-i18n'
import HelpQ from './HelpQ.vue'

defineProps<{ k: string }>()
const { t } = useI18n()
</script>

<template>
  <HelpQ id="beat" :title="t(`beat.q.${k}.t`)" :text="t(`beat.q.${k}.d`)" />
</template>
