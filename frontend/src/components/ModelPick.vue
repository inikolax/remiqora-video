<script setup lang="ts">
// Phase 10: which model shoots the video - H3, LTX 2.5, LTX 2.3, WAN 2.2 5B (the server's cards, /api/config). Each
// row: its name, what it is for, and what it can do (its own sound, Russian lines, faces from photos, a track);
// a model whose weights are missing says so and links to «Настройки».
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import { S, defaultVideo } from '../lib/store'
import type { VideoModel } from '../lib/types'

const { t } = useI18n()
const props = defineProps<{ modelValue: string | undefined | null; compact?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [id: string] }>()
const cards = computed<VideoModel[]>(() => (S.cfg?.video_models || []).filter((m) => !m.imported))
// installed models first (the server sorts them so), the missing ones at the end: not to be picked, «Установить» leads to /settings/models
const cur = computed(() => props.modelValue || defaultVideo())
const gone = (m: VideoModel) => m.missing.length > 0
const nothing = computed(() => !!S.cfg && cards.value.length > 0 && cards.value.every(gone))
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
    <p v-if="nothing" class="mp-none">{{ t('idea.pick.none') }} <router-link to="/settings/models">{{ t('idea.pick.install') }}</router-link></p>
    <component :is="gone(m) && cur !== m.id ? 'div' : 'button'" v-for="m in cards" :key="m.id" :type="gone(m) && cur !== m.id ? undefined : 'button'" :role="gone(m) && cur !== m.id ? undefined : 'radio'"
      :aria-checked="gone(m) && cur !== m.id ? undefined : cur === m.id" class="mp-row" :class="{ on: cur === m.id, miss: gone(m) }"
      @click="!gone(m) || cur === m.id ? emit('update:modelValue', m.id) : undefined">
      <span class="mp-head"><b>{{ m.name }}</b><small v-if="gone(m)" class="mp-miss" :title="m.missing.join(', ')"><Icon name="warn" :size="12" />{{ t('idea.pick.noWeights') }}</small>
        <router-link v-if="gone(m)" class="mp-install" to="/settings/models" @click.stop>{{ t('idea.pick.install') }}</router-link></span>
      <span v-if="!compact || cur === m.id" class="mp-text">{{ m.text }}</span>
      <span class="mp-can"><i v-for="[ic, label] in can(m)" :key="label" :class="{ off: ic === 'minus' }"><Icon :name="ic" :size="12" />{{ label }}</i></span>
    </component>
    <router-link v-if="cards.some(gone) && !nothing" class="mp-link" to="/settings/models">{{ t('idea.pick.download') }}</router-link>
  </div>
</template>
