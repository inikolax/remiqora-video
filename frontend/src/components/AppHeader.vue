<script setup lang="ts">
// The header, one band: the brand; the rail - which video and its stages with their state (ProjectRail); what the
// video card is doing (StatusBar, a pill with its panel); the pages; the interface's language (RU | EN, as in
// Remiqora). The writer's model is chosen on «Модели и настройки» → «Сценарист» and shown in the footer.
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import ProjectRail from './ProjectRail.vue'
import StatusBar from './StatusBar.vue'
import { S, reloadWords } from '../lib/store'
import { setLocale, type LocaleCode } from '../i18n'

const route = useRoute()
const view = computed(() => String(route.name || ''))
const { t, locale } = useI18n()
function pickLocale(next: LocaleCode) {
  if (locale.value === next) return
  setLocale(next)
  locale.value = next
  reloadWords()   // the server's words (model cards, problems) in the new language
}
</script>

<template>
  <header class="top">
    <router-link class="brand" to="/" :aria-label="t('header.home')"><span class="mark" aria-hidden="true"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="white" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6.5 7l5.5 11 5.5-11" /></svg></span>
      <span class="brand-t"><b>Remiqora Video</b><small>{{ t('header.tagline') }}</small></span></router-link>
    <ProjectRail />
    <div class="status">
      <StatusBar />
      <nav class="pages" :aria-label="t('header.section')">
        <router-link v-if="view === 'lab'" to="/" class="nav-ic" :title="t('header.studioTitle')"><Icon name="film" /><span>{{ t('header.studio') }}</span></router-link>
        <router-link to="/models" class="gear nav-ic" :title="t('header.modelsTitle')"><Icon name="gear" /><span>{{ t('header.models') }}</span></router-link>
        <router-link v-if="view !== 'lab'" to="/lab" class="nav-ic" :title="t('header.labTitle')"><Icon name="flask" /><span>{{ t('header.lab') }}</span></router-link>
        <!-- the app's help window (Remiqora's way); the full reference is a button inside it and at #/help -->
        <button type="button" class="nav-ic" :title="t('header.helpTitle')" @click.stop="S.guide = 'app'"><Icon name="help" /><span>{{ t('header.help') }}</span></button>
      </nav>
      <div class="lang-seg" role="group" :aria-label="t('header.language')">
        <button type="button" :class="{ on: locale === 'ru' }" :aria-pressed="locale === 'ru'" :title="t('header.langRu')" lang="ru" @click="pickLocale('ru')">RU</button>
        <button type="button" :class="{ on: locale === 'en' }" :aria-pressed="locale === 'en'" :title="t('header.langEn')" lang="en" @click="pickLocale('en')">EN</button>
      </div>
    </div>
  </header>
</template>
