<script setup lang="ts">
// Phase 10: which model shoots the video - H3, LTX 2.5, LTX 2.3, WAN 2.2 5B (the server's cards, /api/config). Each
// row: its name, what it is for, and what it can do (its own sound, Russian lines, faces from photos, a track);
// a model whose weights are missing says so and links to «Модели и настройки».
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import { S } from '../lib/store'
import type { VideoModel } from '../lib/types'

const { t } = useI18n()
const props = defineProps<{ modelValue: string | undefined | null; compact?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [id: string] }>()
const cards = computed<VideoModel[]>(() => (S.cfg?.video_models || []).filter((m) => !m.imported))
const cur = computed(() => props.modelValue || 'h3')
const can = (m: VideoModel) => [
  m.sound ? ['volume', t('idea.pick.sound')] : ['minus', t('idea.pick.noSound')],
  ...(m.voice ? [['quill', t('idea.pick.lines')]] : []),
  ...(m.refs ? [['face', t('idea.pick.faces')]] : []),
  ...(m.track ? [['music', t('idea.pick.track')]] : []),
  ['clapper', t('idea.pick.upTo', { s: m.max_seconds })],
]
</script>

<template>
  <div class="mpick" :class="{ compact }" role="radiogroup" :aria-label="t('idea.pick.label')">
    <button v-for="m in cards" :key="m.id" type="button" role="radio" :aria-checked="cur === m.id" class="mp-row" :class="{ on: cur === m.id, miss: m.missing.length }"
      @click="emit('update:modelValue', m.id)">
      <span class="mp-head"><b>{{ m.name }}</b><small v-if="m.missing.length" class="mp-miss" :title="m.missing.join(', ')"><Icon name="warn" :size="12" />{{ t('idea.pick.noWeights') }}</small></span>
      <span v-if="!compact || cur === m.id" class="mp-text">{{ m.text }}</span>
      <span class="mp-can"><i v-for="[ic, label] in can(m)" :key="label" :class="{ off: ic === 'minus' }"><Icon :name="ic" :size="12" />{{ label }}</i></span>
    </button>
    <router-link v-if="cards.some((m) => m.missing.length)" class="mp-link" to="/models">{{ t('idea.pick.download') }}</router-link>
  </div>
</template>
