<script setup lang="ts">
// The help window of a screen (S.guide = its id, lib/guides.ts), laid out like Remiqora's DAW guide: the lead, the
// quick start as numbered cards, a map of the screen in the screen's own layout, sections in two columns, small
// cards, the keys sheet's card (the graph), tips and limits, and the way into the full reference.
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import HelpModal from './HelpModal.vue'
import { guides } from '../../lib/content'
import { S } from '../../lib/store'
import { P } from '../../lib/project'

const router = useRouter()
const { t } = useI18n()
const g = computed(() => (S.guide ? guides()[S.guide] : null))
const close = () => { S.guide = null }
function full(id: string) { close(); router.push(`/help/${id}`) }
function keys() { S.guide = null; S.keys = true }

// the app's window: the screens, with the way to each and its own window
const project = computed(() => P.proj)
const SCREENS = computed(() => [
  { guide: 'idea', icon: 'spark', title: t('helpui.scr.idea.title'), text: t('helpui.scr.idea.text'), to: '/' },
  { guide: 'board', icon: 'film', title: t('helpui.scr.board.title'), text: t('helpui.scr.board.text'),
    to: project.value?.plan && project.value.type !== 'graph' ? `/p/${project.value.id}` : null },
  { guide: 'video', icon: 'clapper', title: t('helpui.scr.video.title'), text: t('helpui.scr.video.text'),
    to: project.value?.plan && project.value.type !== 'graph' ? `/p/${project.value.id}/video` : null },
  { guide: 'graph-edit', icon: 'layers', title: t('helpui.scr.graph.title'), text: t('helpui.scr.graph.text'), to: null },
  { guide: 'lab', icon: 'flask', title: t('helpui.scr.lab.title'), text: t('helpui.scr.lab.text'), to: '/lab' },
  { guide: 'models', icon: 'gear', title: t('helpui.scr.models.title'), text: t('helpui.scr.models.text'), to: '/models' },
])
function go(to: string) { close(); router.push(to) }
</script>

<template>
  <HelpModal :open="!!g" :title="g?.title || ''" :icon="g?.icon" wide @close="close">
    <div v-if="g" class="gm">
      <p class="gm-lead">{{ g.lead }}</p>

      <!-- the app's window: the screens -->
      <section v-if="S.guide === 'app'">
        <h3>{{ t('helpui.screens') }}</h3>
        <div class="gm-screens">
          <div v-for="s in SCREENS" :key="s.guide" class="gm-screen">
            <span class="gm-screen-ic"><Icon :name="s.icon" :size="18" /></span>
            <div class="gm-screen-t"><b>{{ s.title }}</b><p>{{ s.text }}</p>
              <div class="gm-screen-acts">
                <button type="button" class="gm-link" @click="S.guide = s.guide"><Icon name="help" :size="13" />{{ t('helpui.screenHelpLink') }}</button>
                <button v-if="s.to" type="button" class="gm-link" @click="go(s.to)"><Icon name="forward" :size="13" />{{ t('helpui.go') }}</button></div></div>
          </div>
        </div>
      </section>

      <!-- a quick start: a real sequence, so the steps are numbered -->
      <section v-if="g.steps">
        <h3>{{ S.guide === 'app' ? t('helpui.howVideo') : t('helpui.quickStart') }}</h3>
        <ol class="gm-steps">
          <li v-for="(s, i) in g.steps" :key="i"><span class="gm-num">{{ i + 1 }}</span><div><b>{{ s.title }}</b><p>{{ s.text }}</p></div></li>
        </ol>
      </section>

      <!-- a map of the screen, laid out like the screen itself -->
      <section v-if="g.map">
        <h3>{{ g.map.title || t('helpui.map') }}</h3>
        <div class="gm-map" :style="{ gridTemplateColumns: g.map.cols, gridTemplateAreas: g.map.areas.map((a) => `'${a}'`).join(' ') }">
          <div v-for="z in g.map.zones" :key="z.area" class="gm-zone" :class="{ accent: z.accent }" :style="{ gridArea: z.area }">
            <b>{{ z.title }}</b><p>{{ z.text }}</p>
            <div v-if="z.deco === 'chain'" class="deco-chain" aria-hidden="true"><i v-for="(c, i) in ['a', 'a', 'a', 'b', 'b', 'a', 'a']" :key="i" :class="c" /></div>
            <div v-else-if="z.deco === 'cards'" class="deco-cards" aria-hidden="true"><i v-for="i in 3" :key="i"><s /><s /></i></div>
            <div v-else-if="z.deco === 'player'" class="deco-player" aria-hidden="true"><Icon name="play" :size="20" /></div>
            <div v-else-if="z.deco === 'shots'" class="deco-shots" aria-hidden="true"><i v-for="i in 6" :key="i" :class="{ now: i === 4, done: i < 4 }" /></div>
            <div v-else-if="z.deco === 'takes'" class="deco-takes" aria-hidden="true"><i v-for="i in 6" :key="i" /></div>
            <div v-else-if="z.deco === 'reels'" class="deco-takes reels" aria-hidden="true"><i v-for="i in 3" :key="i" /></div>
            <div v-else-if="z.deco === 'rows'" class="deco-rows" aria-hidden="true"><i v-for="i in 4" :key="i" /></div>
            <svg v-else-if="z.deco === 'nodes'" class="deco-nodes" viewBox="0 0 240 70" aria-hidden="true">
              <path d="M52 22 C70 22 70 22 88 22" stroke="#e879f9" /><path d="M140 22 C160 22 160 14 178 14" stroke="#e879f9" />
              <path d="M140 30 C160 30 160 52 178 52" stroke="#378ADD" /><path d="M52 30 C110 60 150 56 178 56" stroke="#378ADD" opacity=".4" />
              <rect x="4" y="10" width="48" height="28" rx="5" /><rect x="88" y="10" width="52" height="28" rx="5" />
              <rect x="178" y="2" width="56" height="24" rx="5" /><rect x="178" y="40" width="56" height="24" rx="5" />
              <rect x="4" y="10" width="48" height="4" rx="2" class="h3" /><rect x="88" y="10" width="52" height="4" rx="2" class="h3" />
              <rect x="178" y="2" width="56" height="4" rx="2" class="h3" /><rect x="178" y="40" width="56" height="4" rx="2" class="ff" />
            </svg>
          </div>
        </div>
      </section>

      <section v-if="g.cards">
        <h3>{{ g.cards.title }}</h3>
        <p v-if="g.cards.intro" class="gm-intro">{{ g.cards.intro }}</p>
        <div class="gm-cards">
          <div v-for="c in g.cards.items" :key="c.title" class="gm-card" :style="c.color ? { '--c': c.color } : {}"><b>{{ c.title }}</b><p>{{ c.text }}</p></div>
        </div>
      </section>

      <section v-if="g.table">
        <h3>{{ g.table.title }}</h3>
        <div class="gm-table-wrap"><table class="gm-table">
          <thead><tr><th v-for="(h, i) in g.table.head" :key="i" scope="col">{{ h }}</th></tr></thead>
          <tbody><tr v-for="(r, i) in g.table.rows" :key="i"><th scope="row">{{ r[0] }}</th><td v-for="(c, j) in r.slice(1)" :key="j">{{ c }}</td></tr></tbody>
        </table></div>
      </section>

      <div v-if="g.sections" class="gm-cols">
        <section v-for="s in g.sections" :key="s.title">
          <h3><Icon v-if="s.icon" :name="s.icon" :size="15" />{{ s.title }}</h3>
          <ul class="gm-list"><li v-for="(x, i) in s.items" :key="i" v-html="x" /></ul>
        </section>
      </div>

      <!-- the keys live on their own sheet -->
      <section v-if="g.keys" class="gm-keys-cta">
        <span class="gm-screen-ic"><Icon name="grip" :size="18" /></span>
        <div><b>{{ t('helpui.keys') }}</b><p>{{ t('helpui.keysText') }} <kbd>?</kbd>.</p></div>
        <button type="button" class="btn" @click="keys">{{ t('helpui.openKeys') }}</button>
      </section>

      <div v-if="g.tips || g.limits" class="gm-boxes">
        <section v-if="g.tips" class="gm-box tips"><h3><Icon name="spark" :size="15" />{{ t('helpui.tips') }}</h3><ul class="gm-list"><li v-for="(x, i) in g.tips" :key="i" v-html="x" /></ul></section>
        <section v-if="g.limits" class="gm-box limits"><h3><Icon name="warn" :size="15" />{{ t('helpui.limits') }}</h3><ul class="gm-list"><li v-for="(x, i) in g.limits" :key="i" v-html="x" /></ul></section>
      </div>
    </div>
    <template #foot>
      <span class="muted">{{ t('helpui.more') }}</span>
      <button v-for="m in g?.more || []" :key="m.id" type="button" class="gm-link" @click="full(m.id)">{{ m.title }}</button>
      <span class="grow" />
      <button type="button" class="btn gm-full" @click="full(S.guide === 'app' ? 'start' : g!.more[0].id)"><Icon name="help" />{{ t('helpui.full') }}<Icon name="forward" :size="15" /></button>
    </template>
  </HelpModal>
</template>
