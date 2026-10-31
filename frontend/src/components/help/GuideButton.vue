<script setup lang="ts">
// The «Справка» button of a screen: opens its help window (lib/guides.ts). `compact` - the icon alone, for toolbars.
import Icon from '../Icon.vue'
import { useI18n } from 'vue-i18n'
import { S } from '../../lib/store'

const { t } = useI18n()
defineProps<{ guide: string; compact?: boolean; label?: string }>()
</script>

<template>
  <button type="button" class="guide-btn" :class="{ compact }" :title="compact ? t('helpui.screenHelp') : undefined" :aria-label="compact ? t('helpui.screenHelp') : undefined"
    @click.stop="S.guide = guide"><Icon name="help" :size="16" /><span v-if="!compact">{{ label || t('helpui.name') }}</span></button>
</template>
