<script setup lang="ts">
// A picture of the project big (lib/zoom.ts): its name and place among the project's pictures on top, ← → (keys or
// buttons) to the others, a strip of them all below; Esc or a click beside it closes it.
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import { zoom } from '../lib/zoom'

const { t } = useI18n()
const pic = computed(() => (zoom.i >= 0 ? zoom.list[zoom.i] || null : null))
const close = () => { zoom.i = -1 }
const step = (d: number) => { const i = zoom.i + d; if (i >= 0 && i < zoom.list.length) zoom.i = i }
const panel = ref<HTMLElement | null>(null)
const strip = ref<HTMLElement | null>(null)
function onKey(e: KeyboardEvent) {
  if (zoom.i < 0) return
  if (e.key === 'Escape') close()
  else if (e.key === 'ArrowLeft') step(-1)
  else if (e.key === 'ArrowRight') step(1)
  else return
  e.preventDefault()
  e.stopPropagation()
}
let before: HTMLElement | null = null
watch(() => zoom.i >= 0, async (on) => {
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
})
// the current one in sight in the strip
watch(() => zoom.i, () => nextTick(() => strip.value?.querySelector<HTMLElement>('.on')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })))
</script>

<template>
  <Teleport to="body">
    <Transition name="hm-fade">
      <div v-if="pic" class="iz-back" @click.self="close">
        <div ref="panel" class="iz" role="dialog" aria-modal="true" :aria-label="pic.label || t('zoom.title')" tabindex="-1">
          <header class="iz-head">
            <b>{{ pic.label || t('zoom.title') }}</b><span v-if="zoom.list.length > 1" class="muted">{{ t('zoom.of', { k: zoom.i + 1, n: zoom.list.length }) }}</span>
            <span class="grow" />
            <a class="iz-btn" :href="pic.src" target="_blank" rel="noopener" :title="t('zoom.newTab')" :aria-label="t('zoom.newTab')"><Icon name="expand" :size="14" /></a>
            <button type="button" class="hm-close" :aria-label="t('common.close')" :title="t('helpui.closeEsc')" @click="close"><Icon name="close" :size="15" /></button>
          </header>
          <div class="iz-pic">
            <button v-if="zoom.list.length > 1" type="button" class="iz-nav prev" :disabled="zoom.i === 0" :aria-label="t('zoom.prev')" @click="step(-1)"><Icon name="back" :size="18" /></button>
            <img :key="pic.src" :src="pic.src" :alt="pic.label">
            <button v-if="zoom.list.length > 1" type="button" class="iz-nav next" :disabled="zoom.i >= zoom.list.length - 1" :aria-label="t('zoom.next')" @click="step(1)"><Icon name="forward" :size="18" /></button>
          </div>
          <div v-if="zoom.list.length > 1" ref="strip" class="iz-strip">
            <button v-for="(x, k) in zoom.list" :key="x.src" type="button" :class="{ on: k === zoom.i }" :title="x.label" @click="zoom.i = k"><img :src="x.src" alt="" loading="lazy"></button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
