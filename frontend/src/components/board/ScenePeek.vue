<script setup lang="ts">
// A scene big, in a window over the board («Просмотр»): ⤢ on a card or Space on the board opens it. Its chosen take
// plays with sound (faces not fixed yet: the shot itself), else its frame; a scene with its own first frame shows it
// too («Первый кадр»). ← → step through the scenes (the selection follows), «Подробно» opens the scene on the whole
// page, Esc or a click beside it closes it.
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import { P } from '../../lib/project'
import { lenOf, peek, playKey, rawTake, shotPng } from '../../lib/board'
import { mmss } from '../../lib/format'

const { t } = useI18n()
const emit = defineEmits<{ open: [i: number] }>()
const scenes = computed(() => P.proj?.plan?.scenes || [])
const s = computed(() => (peek.value === null ? null : scenes.value[peek.value] || null))
const fileUrl = (f: string) => `/api/projects/${P.proj?.id}/files/${encodeURIComponent(f)}`
const take = computed(() => (s.value ? playKey(s.value) : null))
const still = computed(() => (s.value ? shotPng(s.value.index) : null))
const first = computed(() => (s.value?.start_photo ? fileUrl(s.value.start_photo) : null))
// what the window shows: the take (or the shot's frame), or the scene's first frame
const side = ref<'shot' | 'first'>('shot')
const shows = computed(() => (side.value === 'first' && first.value ? 'first' : take.value ? 'take' : still.value ? 'still' : first.value ? 'first' : 'none'))
const tall = computed(() => ['9:16', '4:5', '3:4'].includes(P.proj?.settings.aspect || ''))
const ar = computed(() => (P.proj?.settings.aspect || '16:9').replace(':', ' / '))
const secs = (x: number) => t('board.grid.secs', { s: String(Math.round(x * 10) / 10).replace('.', ',') })

const panel = ref<HTMLElement | null>(null)
const close = () => { peek.value = null }
function step(d: number) {
  const i = (peek.value ?? 0) + d
  if (i < 0 || i >= scenes.value.length) return
  peek.value = i
  P.sel = i
  P.picked = []
}
function onKey(e: KeyboardEvent) {
  if (peek.value === null) return
  if (e.key === 'Escape') close()
  else if (e.key === 'ArrowLeft') step(-1)
  else if (e.key === 'ArrowRight') step(1)
  else if (e.key === ' ' && !(e.target as HTMLElement).closest?.('video, button')) {
    const v = panel.value?.querySelector('video')
    if (v) { if (v.paused) v.play().catch(() => {}); else v.pause() } else close()
  } else return
  e.preventDefault()
  e.stopPropagation()
}
let before: HTMLElement | null = null
watch(() => peek.value !== null, async (on) => {
  if (on) {
    before = document.activeElement as HTMLElement | null
    document.addEventListener('keydown', onKey, true)
    document.body.classList.add('modal-open')
    await nextTick()
    panel.value?.focus()
  } else {
    document.removeEventListener('keydown', onKey, true)
    document.body.classList.remove('modal-open')
    before?.focus?.()
  }
}, { immediate: true })
watch(peek, () => { side.value = 'shot' })
onUnmounted(() => { document.removeEventListener('keydown', onKey, true); document.body.classList.remove('modal-open'); peek.value = null })
</script>

<template>
  <Teleport to="body">
    <Transition name="hm-fade">
      <div v-if="s" class="pk-back" @click.self="close">
        <div ref="panel" class="pk" :class="{ tall }" :style="{ '--ar': ar }" role="dialog" aria-modal="true" :aria-label="t('board.peek.title', { n: s.index + 1 })" tabindex="-1">
          <header class="pk-head">
            <b class="pk-n">{{ s.index + 1 }}</b>
            <span class="pk-t">{{ t('board.peek.title', { n: s.index + 1 }) }}<small>{{ mmss(Number(s.start) || 0) }} · {{ secs(lenOf(s)) }}</small></span>
            <span v-if="first && (take || still)" class="pk-sides" role="group">
              <button type="button" :class="{ on: shows !== 'first' }" @click="side = 'shot'">{{ t('board.peek.take') }}</button>
              <button type="button" :class="{ on: shows === 'first' }" @click="side = 'first'">{{ t('board.peek.first') }}</button></span>
            <span class="grow" />
            <button type="button" class="pk-btn" :disabled="s.index === 0" :title="t('board.insp.prev')" :aria-label="t('board.insp.prev')" @click="step(-1)"><Icon name="back" :size="15" /></button>
            <button type="button" class="pk-btn" :disabled="s.index >= scenes.length - 1" :title="t('board.insp.next')" :aria-label="t('board.insp.next')" @click="step(1)"><Icon name="forward" :size="15" /></button>
            <button type="button" class="btn pk-open" :title="t('board.peek.detailTitle')" @click="emit('open', s.index); close()"><Icon name="expand" :size="14" />{{ t('board.peek.detail') }}</button>
            <button type="button" class="hm-close" :aria-label="t('common.close')" :title="t('helpui.closeEsc')" @click="close"><Icon name="close" :size="15" /></button>
          </header>
          <div class="pk-pic">
            <video v-if="shows === 'take'" :key="take!" :src="fileUrl(`scenes/${take}.mp4`)" :poster="fileUrl(`scenes/${take}.png`)" controls autoplay playsinline />
            <img v-else-if="shows === 'still'" :src="still!" alt="">
            <img v-else-if="shows === 'first'" :src="first!" alt="">
            <div v-else class="sd-empty"><Icon name="film" :size="28" /><b>{{ t('board.detail.notShot') }}</b><span>{{ t('board.detail.notShotSub') }}</span></div>
            <span v-if="shows === 'first'" class="bg-tag">{{ t('board.grid.start') }}</span>
            <span v-else-if="shows === 'take' && rawTake(s)" class="bg-tag warn" :title="t('board.grid.facesTitle')">{{ t('board.grid.faces') }}</span>
          </div>
          <p v-if="s.ru" class="pk-text">{{ s.ru }}</p>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
