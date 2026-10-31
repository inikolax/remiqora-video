<script setup lang="ts">
// A scene's chosen take, playing: its video from the cache (faces not fixed yet: the shot itself), else the last frame
// of the latest render, else «not shot yet». The board's «Кадр» and the scene's full page share it; «ended» lets the
// board go on to the next scene.
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import { P } from '../../lib/project'
import { playKey, shotPng } from '../../lib/board'
import type { Scene } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ s: Scene; autoplay?: boolean }>()
const emit = defineEmits<{ ended: [] }>()
const fileUrl = (path: string) => `/api/projects/${P.proj?.id}/files/${path}`
const chosen = computed(() => (playKey(props.s) ? { key: playKey(props.s) } : null))
const still = computed(() => shotPng(props.s.index))
const tall = computed(() => P.proj?.settings.aspect === '9:16')
const vid = ref<HTMLVideoElement | null>(null)
watch(() => chosen.value?.key, async () => { if (!props.autoplay) return; await nextTick(); vid.value?.play().catch(() => {}) })
</script>

<template>
  <div class="sd-player" :class="{ tall }">
    <video v-if="chosen" ref="vid" :key="chosen.key!" :src="fileUrl(`scenes/${chosen.key}.mp4`)" :poster="fileUrl(`scenes/${chosen.key}.png`)"
      controls playsinline :autoplay="autoplay" @ended="emit('ended')" />
    <img v-else-if="still" :src="still" alt="">
    <div v-else class="sd-empty"><Icon name="film" :size="28" /><b>{{ t('board.detail.notShot') }}</b><span>{{ t('board.detail.notShotSub') }}</span></div>
  </div>
</template>
