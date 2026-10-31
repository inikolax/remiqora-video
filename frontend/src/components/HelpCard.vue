<script setup lang="ts">
// The card a "?" opens: the parameter's own entry from the help, near its button; a click outside, Escape or a page
// change closes it.
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { help } from '../lib/content'
import { S } from '../lib/store'

const { t } = useI18n()
const card = ref<HTMLElement | null>(null)
const pos = ref({ left: 0, top: 0 })

const entry = computed(() => {
  const h = S.help
  const sec = h && help().find((x) => x.id === h.section)
  if (!h || !sec) return null
  const box = document.createElement('div')
  box.innerHTML = sec.html
  let title = sec.title, body = ''
  if (h.term) {
    // the exact name first: «Сцена» is not «Сценарист»
    const term = h.term.toLowerCase().trim(), dts = [...box.querySelectorAll('dt')], name = (d: Element) => ((d as HTMLElement).dataset.term || d.textContent || '').toLowerCase().trim()   // the English help keeps the Russian term
    const dt = dts.find((d) => name(d) === term) || dts.find((d) => name(d).startsWith(term))
    if (dt) { title = dt.textContent || title; body = dt.nextElementSibling ? dt.nextElementSibling.innerHTML : '' }
  }
  return { id: sec.id, section: sec.title, title, body: body || box.innerHTML }
})

watch(() => S.help, async (h) => {
  if (!h) return
  await nextTick()
  const el = card.value
  if (!el) return
  const w = el.offsetWidth, ht = el.offsetHeight, top = h.y + 8
  pos.value = { left: Math.max(8, Math.min(innerWidth - w - 8, h.x - 12)), top: top + ht + 4 < innerHeight ? top : Math.max(8, h.y - ht - 40) }
})

const close = () => { S.help = null }
const outside = (e: MouseEvent) => { if (S.help && card.value && !card.value.contains(e.target as Node)) close() }
const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
onMounted(() => { document.addEventListener('click', outside); document.addEventListener('keydown', esc) })
onUnmounted(() => { document.removeEventListener('click', outside); document.removeEventListener('keydown', esc) })
const route = useRoute()
watch(() => route.fullPath, close)
</script>

<template>
  <div v-if="entry" ref="card" class="help-card" role="dialog" :aria-label="entry.title" :style="{ left: pos.left + 'px', top: pos.top + 'px' }">
    <div class="help-card-head"><b>{{ entry.title }}</b><button type="button" class="ghost" :aria-label="t('common.close')" @click="close">×</button></div>
    <div class="help-card-body" v-html="entry.body" />
    <router-link :to="`/help/${entry.id}`" class="help-card-more" @click="close">{{ t('helpui.openIn', { section: entry.section }) }}</router-link>
  </div>
</template>
