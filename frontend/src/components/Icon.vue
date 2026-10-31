<script setup lang="ts">
// One icon of the app's family (lib/icons.ts): 16 in buttons and text, 20 in navigation, 28 in empty states.
import { ICONS } from '../lib/icons'

withDefaults(defineProps<{ name: string; size?: number; cls?: string }>(), { size: 16, cls: '' })
</script>

<template>
  <svg :class="['ic', cls]" :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" v-html="ICONS[name] || ''" />
</template>
