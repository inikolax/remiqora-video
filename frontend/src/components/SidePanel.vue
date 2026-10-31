<script setup lang="ts">
// A screen's side panel that moves and changes size, after Remiqora's DAW (components/editor/DockHandle.vue there):
// the grip at its top - dragged, it shows the places to drop it (left, right, a window over the screen); a plain
// click, or Enter / Space, opens a menu with the same places. Docked, its inner edge is dragged for the width (the
// arrow keys on it, a double click - back to the default); as a window it is moved by its bar and sized by its
// corner. The place and the sizes are remembered per screen in this browser; on a narrow screen it stays as it was.
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'

defineOptions({ inheritAttrs: false })   // the screen's classes go to the panel itself, not to the drop zones
type Place = 'right' | 'left' | 'float'
const props = withDefaults(defineProps<{ id: string; width?: number; label?: string }>(), { width: 380, label: '' })
const { t } = useI18n()
const panelName = computed(() => props.label || t('misc.panel'))
const PLACES = computed<[Place, string][]>(() => [['left', t('misc.left')], ['right', t('misc.right')], ['float', t('misc.float')]])
const MIN_W = 300, KEY = `h3_panel_${props.id}`

const saved = (() => { try { return JSON.parse(localStorage.getItem(KEY) || '{}') } catch { return {} } })()
const st = reactive({
  place: (['left', 'right', 'float'].includes(saved.place) ? saved.place : 'right') as Place,
  w: +saved.w || props.width, x: +saved.x || 0, y: +saved.y || 0, h: +saved.h || 0,
})
watch(st, (s) => { try { localStorage.setItem(KEY, JSON.stringify(s)) } catch { /* not remembered */ } }, { deep: true })

// a narrow screen: the panel stays under the content, as the screen's own styles put it
const narrow = ref(false)
let mq: MediaQueryList | null = null
const onMq = () => { narrow.value = !!mq?.matches }
const maxW = () => Math.max(MIN_W, innerWidth - 420)
const clampW = (w: number) => Math.round(Math.max(MIN_W, Math.min(maxW(), w)))
function keepInside() {   // a window never lies outside the screen (the browser window got smaller since)
  st.w = clampW(st.w)
  st.h = Math.round(Math.max(240, Math.min(innerHeight - 72, st.h || innerHeight - 160)))
  st.x = Math.round(Math.max(8, Math.min(innerWidth - st.w - 8, st.x)))
  st.y = Math.round(Math.max(64, Math.min(innerHeight - st.h - 8, st.y)))
}
onMounted(() => {
  mq = matchMedia('(max-width: 900px)')
  onMq()
  mq.addEventListener('change', onMq)
  if (st.place === 'float') keepInside()
  addEventListener('resize', onWin)
})
// a narrow window (a phone) has no dock: the remembered width stays as it was, not clamped to the minimum for good
const onWin = () => { if (mq?.matches) return; if (st.place === 'float') keepInside(); else st.w = clampW(st.w) }

const place = computed<Place | null>(() => (narrow.value ? null : st.place))
const style = computed(() => {
  if (place.value === 'float') return { position: 'fixed' as const, left: `${st.x}px`, top: `${st.y}px`, width: `${st.w}px`, height: `${st.h}px` }
  if (place.value) return { flex: `0 0 ${st.w}px`, width: `${st.w}px`, maxWidth: 'none', order: place.value === 'left' ? -1 : 2 }
  return {}
})

// a window's own corner: its size, as the user leaves it
const el = ref<HTMLElement | null>(null)
let ro: ResizeObserver | null = null
watch([place, el], ([p, e]) => {
  ro?.disconnect()
  if (p === 'float' && e) {
    ro = new ResizeObserver(() => { if (st.place === 'float' && !drag.value) { st.w = Math.round(e.offsetWidth); st.h = Math.round(e.offsetHeight) } })
    ro.observe(e)
  }
})

// ---- the grip: a click opens the menu, a drag shows the places ----
const menu = ref(false)
const drag = ref(false)
const zone = ref<Place | null>(null)
let x0 = 0, y0 = 0, dx = 0, dy = 0
const zoneAt = (x: number) => (x < innerWidth * 0.22 ? 'left' : x > innerWidth * 0.78 ? 'right' : 'float')
function gripDown(e: PointerEvent) {
  if (e.button !== 0) return
  e.preventDefault()
  x0 = e.clientX; y0 = e.clientY
  const r = el.value!.getBoundingClientRect()
  dx = e.clientX - r.left; dy = e.clientY - r.top
  addEventListener('pointermove', gripMove)
  addEventListener('pointerup', gripUp, { once: true })
}
function gripMove(e: PointerEvent) {
  if (!drag.value) {
    if (Math.hypot(e.clientX - x0, e.clientY - y0) < 5) return
    drag.value = true
    menu.value = false
    document.body.style.cursor = 'grabbing'
  }
  zone.value = zoneAt(e.clientX)
  if (st.place === 'float') { st.x = e.clientX - dx; st.y = e.clientY - dy }   // a window follows the pointer
}
function gripUp(e: PointerEvent) {
  removeEventListener('pointermove', gripMove)
  document.body.style.cursor = ''
  if (!drag.value) { menu.value = !menu.value; return }
  drag.value = false
  const z = zoneAt(e.clientX)
  zone.value = null
  if (z === 'float') {
    if (st.place !== 'float') { st.x = e.clientX - 24; st.y = e.clientY - 14; st.h = st.h || innerHeight - 160 }
    st.place = 'float'
    keepInside()
  } else st.place = z
}
function gripKey(e: MouseEvent) { if (e.detail === 0) menu.value = !menu.value }   // Enter / Space
function choose(p: Place) {
  if (p === 'float' && st.place !== 'float') { st.x = innerWidth - st.w - 40; st.y = 90; st.h = st.h || innerHeight - 160 }
  st.place = p
  if (p === 'float') keepInside()
  menu.value = false
}
const away = (e: Event) => { if (menu.value && !el.value?.querySelector('.dock-bar')?.contains(e.target as Node)) menu.value = false }
onMounted(() => document.addEventListener('pointerdown', away, true))

// ---- the inner edge of a docked panel: its width ----
function splitDown(e: PointerEvent) {
  const bar = e.currentTarget as HTMLElement, sx = e.clientX, w0 = st.w, sign = st.place === 'left' ? 1 : -1
  bar.setPointerCapture(e.pointerId)
  const move = (ev: PointerEvent) => { st.w = clampW(w0 + sign * (ev.clientX - sx)) }
  const up = () => { bar.removeEventListener('pointermove', move); bar.removeEventListener('pointerup', up) }
  bar.addEventListener('pointermove', move)
  bar.addEventListener('pointerup', up)
}
const grow = (by: number) => { st.w = clampW(st.w + (st.place === 'left' ? by : -by)) }
// the edge is the panel's neighbour in the screen's row (inside the panel it would scroll away with its content)
const split = computed(() => ({
  class: 'dock-split', role: 'separator', 'aria-orientation': 'vertical' as const, tabindex: 0, 'aria-valuenow': st.w,
  'aria-label': t('misc.widthAria', { w: st.w }), title: t('misc.widthTitle'),
  onPointerdown: (e: PointerEvent) => { e.preventDefault(); splitDown(e) }, onDblclick: () => { st.w = props.width },
  onKeydown: (e: KeyboardEvent) => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); grow(e.key === 'ArrowLeft' ? -24 : 24) } },
}))

onBeforeUnmount(() => {
  mq?.removeEventListener('change', onMq)
  removeEventListener('resize', onWin)
  removeEventListener('pointermove', gripMove)
  document.removeEventListener('pointerdown', away, true)
  ro?.disconnect()
  document.body.style.cursor = ''
})
</script>

<template>
  <div v-if="place === 'right'" v-bind="split" :style="{ order: 2 }" />
  <aside ref="el" v-bind="$attrs" class="dock" :class="place ? `dock-${place}` : 'dock-off'" :style="style">
    <div v-if="place" class="dock-bar">
      <button type="button" class="dock-grip" :aria-label="t('misc.move', { label: panelName })" :title="t('misc.gripTitle')"
        aria-haspopup="menu" :aria-expanded="menu" @pointerdown="gripDown" @click="gripKey" @keydown.escape="menu = false"><Icon name="grip" :size="16" /></button>
      <span class="dock-name">{{ panelName }}</span>
      <button v-if="place === 'float'" type="button" class="ghost dock-back" :title="t('misc.back')" :aria-label="t('misc.back')" @click="choose('right')"><Icon name="close" :size="14" /></button>
      <div v-if="menu" class="dock-menu" role="menu" :aria-label="panelName">
        <button v-for="[p, name] in PLACES" :key="p" type="button" role="menuitemradio" :aria-checked="st.place === p" :class="{ on: st.place === p }" @click="choose(p)">{{ name }}</button>
      </div>
    </div>
    <slot />
  </aside>
  <div v-if="place === 'left'" v-bind="split" :style="{ order: -1 }" />
  <Teleport to="body">
    <div v-if="drag" class="dock-zones" aria-hidden="true">
      <div v-for="[p, name] in PLACES" :key="p" :class="[`z-${p}`, { on: zone === p }]">{{ p === 'float' ? t('misc.floatHere') : name }}</div>
    </div>
  </Teleport>
</template>
