<script setup lang="ts">
// The header's rail: which video this is (a switch to the recent ones) and its stages with their state - the
// storyboard's scenes and «проверь», how much of the video is shot, whether the montage is the user's own. On the
// home screen it is «Новый ролик»; in the lab and on a graph the same place says so, so the header keeps its shape.
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import GuideButton from './help/GuideButton.vue'
import { S } from '../lib/store'
import { P } from '../lib/project'

const { t } = useI18n()
const route = useRoute()
const view = computed(() => String(route.name || ''))
const routeId = computed(() => String(route.params.id || ''))

// the video this screen is about: a storyboard (P.proj) or a graph (by the route's id in the shelf's list)
const board = computed(() => (['board', 'video', 'graph', 'edit'].includes(view.value) && P.proj && P.proj.id === routeId.value ? P.proj : null))
const graphProj = computed(() => (['gedit', 'gmontage'].includes(view.value) ? S.projects.find((p) => p.id === routeId.value) || null : null))
const title = computed(() => board.value?.name || graphProj.value?.name || '')
const kindIcon = (k?: string) => (k === 'graph' ? 'layers' : k === 'clip' ? 'music' : 'film')

// a stage's state, in words: the storyboard's size and marks, the shot share, the montage
const est = computed(() => (board.value && P.est ? P.est[board.value.settings?.quality || 'draft'] : null))
const scenes = computed(() => board.value?.plan?.scenes || [])
const checks = computed(() => scenes.value.filter((s: any) => s.status === 'check').length)
const shot = computed(() => {
  const n = scenes.value.length, left = est.value?.to_shoot
  return n && left != null ? { done: n - left, all: n } : null
})
const stages = computed(() => {
  const p = board.value
  if (!p) return []
  const id = p.id, written = !!p.plan
  const s = shot.value
  return [
    { key: 'idea', label: t('header.step.idea'), to: '/', on: false, done: true, sub: '' },
    { key: 'board', label: t('header.step.board'), to: `/p/${id}`, on: view.value === 'board' || view.value === 'graph', done: written,
      sub: written ? t('header.scenes', scenes.value.length) : '', warn: checks.value ? t('header.checks', { n: checks.value }) : '' },
    { key: 'video', label: t('header.step.video'), to: written ? `/p/${id}/video` : null, on: view.value === 'video', done: !!s && s.done === s.all,
      sub: !written ? '' : !s ? '' : s.done === s.all ? t('header.shotAll') : s.done ? t('header.shot', s) : t('header.notShot'),
      fill: s && s.all ? s.done / s.all : 0 },
    { key: 'edit', label: t('header.step.edit'), to: written ? `/p/${id}/edit` : null, on: view.value === 'edit', done: false,
      sub: !written ? '' : est.value?.reedit ? t('header.editChanged') : p.edit ? t('header.editOwn') : '' },
  ]
})

// the switch: the recent videos, newest first
const open = ref(false)
const menu = ref<HTMLElement | null>(null)
const recent = computed(() => [...S.projects].sort((a, b) => (b.updated || 0) - (a.updated || 0)).slice(0, 8))
const linkOf = (p: Record<string, any>) => (p.kind === 'graph' ? `/g/${p.id}` : `/p/${p.id}`)
async function toggle() {
  open.value = !open.value
  if (open.value) { await nextTick(); (menu.value?.querySelector('a') as HTMLElement | null)?.focus() }
}
const away = () => { open.value = false }
const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') open.value = false }
onMounted(() => { document.addEventListener('click', away); document.addEventListener('keydown', esc) })
onUnmounted(() => { document.removeEventListener('click', away); document.removeEventListener('keydown', esc) })
</script>

<template>
  <div class="rail">
    <div class="rail-who" @click.stop>
      <button type="button" class="rail-name" :title="t('header.switchTitle')" aria-haspopup="menu" :aria-expanded="open" @click="toggle">
        <template v-if="view === 'lab'"><Icon name="flask" :size="16" /><b>{{ t('header.lab') }}</b></template>
        <template v-else-if="title"><Icon :name="kindIcon(graphProj ? 'graph' : board?.plan?.clip ? 'clip' : 'board')" :size="16" /><b>{{ title }}</b></template>
        <template v-else><Icon name="plus" :size="16" /><b>{{ t('header.newVideo') }}</b></template>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
      </button>
      <div v-if="open" ref="menu" class="rail-menu" role="menu">
        <span class="rail-menu-h">{{ t('header.recent') }}</span>
        <router-link v-for="p in recent" :key="p.id" :to="linkOf(p)" role="menuitem" :class="{ on: p.id === routeId }" @click="open = false">
          <Icon :name="kindIcon(p.kind)" :size="15" /><span>{{ p.name || t('header.untitled') }}</span></router-link>
        <router-link to="/" class="rail-all" role="menuitem" @click="open = false"><Icon name="arrange" :size="15" /><span>{{ t('header.allVideos') }}</span></router-link>
      </div>
    </div>

    <!-- a storyboard's stages, each with its state -->
    <nav v-if="stages.length" class="rail-stages" :aria-label="t('header.rail')">
      <template v-for="s in stages" :key="s.key">
        <span v-if="s.on" class="stage on" aria-current="page"><b>{{ s.label }}</b><small v-if="s.sub || s.warn">{{ s.sub }}<em v-if="s.warn" :class="{ after: !!s.sub }">{{ s.warn }}</em></small>
          <i v-if="s.fill" class="stage-fill" :style="{ width: `${s.fill * 100}%` }" /></span>
        <router-link v-else-if="s.to" :to="s.to" class="stage" :class="{ done: s.done, idea: s.key === 'idea' }">
          <b><Icon v-if="s.key === 'idea'" name="check" :size="13" />{{ s.label }}</b>
          <small v-if="s.sub || s.warn">{{ s.sub }}<em v-if="s.warn" :class="{ after: !!s.sub }">{{ s.warn }}</em></small>
          <i v-if="s.fill" class="stage-fill" :style="{ width: `${s.fill * 100}%` }" /></router-link>
        <span v-else class="stage off"><b>{{ s.label }}</b></span>
      </template>
    </nav>
    <!-- a graph: the canvas, and a node's montage when that is open -->
    <nav v-else-if="graphProj" class="rail-stages" :aria-label="t('header.rail')">
      <router-link v-if="view === 'gmontage'" :to="`/g/${routeId}`" class="stage"><b>{{ t('header.graph') }}</b><small>{{ t('header.graphSub') }}</small></router-link>
      <span v-else class="stage on" aria-current="page"><b>{{ t('header.graph') }}</b><small>{{ t('header.graphSub') }}</small></span>
      <span v-if="view === 'gmontage'" class="stage on" aria-current="page"><b>{{ t('header.montage') }}</b><small>{{ t('header.nodeMontage') }}</small></span>
    </nav>
    <span v-else-if="view === 'lab'" class="rail-note">{{ t('header.labSub') }}<GuideButton guide="lab" /></span>
  </div>
</template>
