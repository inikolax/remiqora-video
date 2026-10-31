<script setup lang="ts">
// The footer, one line about this machine (after Remiqora Video's AppFooter): who made it, the studio's promise
// (everything runs here), the writer - its model as chosen, or what keeps it from starting, a link to its settings
// (it is chosen there, not in the header) - and the way to the help and the scenarios, and the code's version.
// Remiqora's «Модели и лицензии» waits (lib/credits.ts): the user wants it out for now.
// Not on the one-screen-high pages (the lab, the graph, the montage).
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { S } from '../lib/store'

const { t } = useI18n()
const year = new Date().getFullYear()
const writer = computed(() => {
  const r = S.llms
  if (!r) return null
  const m = r.models.find((x) => x.id === S.llm)
  const problem = !r.server_ok ? t('header.noServer') : !m ? t('header.noGguf') : ''
  return { name: m ? m.name.replace(/-GGUF$|\.gguf$/i, '') : '', ok: !problem, problem }
})
</script>

<template>
  <footer class="foot">
    <div class="foot-in">
      <span class="foot-brand"><span class="foot-mark" aria-hidden="true"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="white" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6.5 7l5.5 11 5.5-11" /></svg></span>
        <span><b>Remiqora Video</b> · © {{ year }} {{ t('header.author') }}</span></span>
      <span class="foot-facts">
        <span :title="t('header.localTitle')">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3ZM9 12l2 2 4-4" /></svg>
          {{ t('header.local') }}</span>
        <router-link v-if="writer" to="/models/llm" class="foot-writer" :title="writer.ok ? t('header.writerOk') : writer.problem">
          <i class="foot-dot" :class="writer.ok ? 'ok' : 'bad'" />{{ t('header.writer') }}<b v-if="writer.name">{{ writer.name }}</b><em v-if="!writer.ok">{{ writer.problem }}</em></router-link>
      </span>
      <nav class="foot-links" :aria-label="t('header.help')">
        <router-link to="/help">{{ t('header.help') }}</router-link>
        <router-link to="/help/tut-first-run">{{ t('header.scenarios') }}</router-link>
        <span v-if="S.cfg?.version" class="foot-ver">{{ t('header.version', { v: S.cfg.version }) }}</span>
      </nav>
    </div>
  </footer>
</template>
