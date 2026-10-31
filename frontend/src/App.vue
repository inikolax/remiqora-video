<script setup lang="ts">
// The page: the header (with the video card's state in it) on every screen, the screen of the route under them, and the help
// windows over all of it (the header's and each screen's, the graph's keys).
// The lab and the graph are one screen high with its own scrolling columns (lab.css), so the body knows when it is on.
import { computed, onMounted, ref, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './components/AppHeader.vue'
import AppFooter from './components/AppFooter.vue'
import Banners from './components/Banners.vue'
import ImageZoom from './components/ImageZoom.vue'
import HelpCard from './components/HelpCard.vue'
import GuideModal from './components/help/GuideModal.vue'
import KeysModal from './components/help/KeysModal.vue'
import { S, banner, start } from './lib/store'
import { t } from './i18n'
import { loadTextLang } from './lib/textLang'

const route = useRoute()
const ready = ref(false)
// the footer under the scrolling pages; the lab, the graph, the storyboard and the montage are one window high
const footed = computed(() => ready.value && !['lab', 'graph', 'gedit', 'board', 'edit', 'gmontage'].includes(String(route.name)))
watchEffect(() => {
  document.body.classList.toggle('lab', route.name === 'lab')
  document.body.classList.toggle('graph', route.name === 'graph' || route.name === 'gedit')
  document.body.classList.toggle('edit', route.name === 'edit' || route.name === 'gmontage')   // the montage: one window high
  document.body.classList.toggle('board', route.name === 'board')   // the storyboard: one window high, its track at the bottom
})
onMounted(() => start().then(() => loadTextLang()).then(() => { ready.value = true }).catch((e) => banner(t('misc.loadFailed', { msg: e.message }))))
</script>

<template>
  <div class="head">
    <AppHeader />
  </div>
  <div v-if="S.cfg?.problems.length && route.name === 'lab'" class="problems">{{ S.cfg.problems.join(' · ') }}</div>
  <router-view v-if="ready" :key="route.name === 'board' || route.name === 'video' || route.name === 'graph' || route.name === 'gedit' ? String(route.params.id) + String(route.name) : String(route.name)" />
  <AppFooter v-if="footed" />
  <Banners />
  <ImageZoom />
  <HelpCard />
  <GuideModal />
  <KeysModal />
</template>
