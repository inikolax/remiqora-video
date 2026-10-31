<script setup lang="ts">
// The board's «Сценарий»: every scene as a line of text, grouped by episode (a chain - the scenes shot as one piece),
// each episode with what it is about from the writer's plan. A long video opens with its episodes folded but the one
// being worked on; a search over the text and the lines and filters (not shot, with lines, with notes, pinned) show
// the matching scenes in a flat list. A click selects (Ctrl / Shift pick several, the episode's number picks all of
// it), a double click opens the scene on the whole page, a line dragged moves the scene.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import { P } from '../../lib/project'
import { episodes, isPicked, isRaw, pickScene, shotPng } from '../../lib/board'
import { chainColor } from '../../lib/consts'
import { TL } from '../../lib/textLang'
import { mmss } from '../../lib/format'
import type { Plan, Scene } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan; busy: boolean; english: number; unlocked: number }>()
const emit = defineEmits<{ open: [i: number]; add: []; rewrite: []; translate: []; move: [from: number, to: number] }>()

const eps = computed(() => episodes(props.p))
const epOf = (i: number) => eps.value.find((e) => e.scenes.some((s) => s.index === i))
// which episodes are open: a short video - all; a long one - the one with the selected scene, and whatever is opened
const LONG = 16
const opened = ref(new Set<number>())
const allOpen = ref(props.p.scenes.length <= LONG)
watch(() => P.sel, (i) => { const e = epOf(i); if (e) opened.value.add(e.n) }, { immediate: true })
const isOpen = (n: number) => allOpen.value || opened.value.has(n)
function toggle(n: number) { if (allOpen.value) { allOpen.value = false; opened.value = new Set(eps.value.map((e) => e.n).filter((x) => x !== n)) } else if (opened.value.has(n)) opened.value.delete(n); else opened.value.add(n) }
function setAll(on: boolean) { allOpen.value = on; if (!on) opened.value = new Set([epOf(P.sel)?.n || 1]) }
const pickEpisode = (n: number) => { const e = eps.value.find((x) => x.n === n)!; P.picked = e.scenes.length > 1 ? e.scenes.map((s) => s.index) : []; P.sel = e.scenes[0].index }

// the search and the filters
const q = ref('')
type F = 'all' | 'notShot' | 'lines' | 'notes' | 'pinned'
const f = ref<F>('all')
const hasLines = (s: Scene) => (s.lines || []).some((l: any) => (l.text || '').trim())
const tests: Record<F, (s: Scene) => boolean> = {
  all: () => true, notShot: (s) => !shotPng(s.index), lines: hasLines,
  notes: (s) => s.status === 'check', pinned: (s) => !!s.locked,
}
const counts = computed(() => Object.fromEntries((Object.keys(tests) as F[]).map((k) => [k, props.p.scenes.filter(tests[k]).length])) as Record<F, number>)
const words = (s: Scene) => [s.ru, s.raw_ru, s.raw, ...(s.lines || []).map((l: any) => l.text)].filter(Boolean).join(' ').toLowerCase()
const filtering = computed(() => !!q.value.trim() || f.value !== 'all')
const found = computed(() => props.p.scenes.filter((s) => tests[f.value](s) && (!q.value.trim() || words(s).includes(q.value.trim().toLowerCase()))))
const FILTERS = computed(() => [['all', t('board.script.all')], ['notShot', t('board.script.notShot')], ['lines', t('board.script.withLines')],
  ['notes', t('board.script.withNotes')], ['pinned', t('board.script.pinned')]] as [F, string][])

const text = (s: Scene) => (isRaw(s) ? s.raw_ru || s.raw || '' : s.ru || '')
const lineOf = (s: Scene) => (s.lines || []).filter((l: any) => (l.text || '').trim()).map((l: any) => `«${l.text}»`).join(' ')

// a line dragged onto another moves the scene there
const from = ref<number | null>(null)
const over = ref<number | null>(null)
function drop(to: number) { const a = from.value; from.value = null; over.value = null; if (a !== null && a !== to) emit('move', a, to) }
</script>

<template>
  <section class="bs">
    <div class="bs-bar">
      <label class="shelf-find bs-find"><Icon name="search" :size="15" /><input v-model="q" type="search" :placeholder="t('board.script.find')" :aria-label="t('board.script.findLabel')"></label>
      <div class="bs-filters">
        <button v-for="[k, name] in FILTERS" :key="k" type="button" :class="{ on: f === k }" :disabled="k !== 'all' && !counts[k]" @click="f = k">{{ name }}<small>{{ counts[k] }}</small></button>
      </div>
      <span class="grow" />
      <button v-if="!filtering && eps.length > 1" type="button" class="link-btn" @click="setAll(!allOpen)">{{ allOpen ? t('board.script.foldAll') : t('board.script.expandAll') }}</button>
    </div>
    <div class="bs-acts">
      <button type="button" class="btn" :disabled="busy" :title="t('board.addSceneTitle')" @click="emit('add')"><Icon name="plus" />{{ t('board.addScene') }}</button>
      <button v-if="!p.manual" type="button" class="btn" :disabled="!unlocked || busy" :title="unlocked ? t('board.rewriteTitle', { scenes: t('board.scenesAcc', unlocked) }) : t('board.allPinned')"
        @click="emit('rewrite')"><Icon name="spark" />{{ t('board.rewriteUnpinned') }}<b class="bh-n">{{ unlocked }}</b></button>
      <button v-if="english" type="button" class="btn" :disabled="busy" @click="emit('translate')"><Icon name="spark" />{{ t('textlang.translate', { v: TL.name }) }}<b class="bh-n">{{ english }}</b></button>
      <span class="grow" /><span class="muted small">{{ t('board.script.pickHint') }}</span>
    </div>

    <div class="bs-list" role="list">
      <template v-if="filtering">
        <p v-if="!found.length" class="muted bs-none">{{ t('board.script.none') }}</p>
        <div v-for="s in found" :key="s.index" role="listitem" class="bs-line" :class="{ on: s.index === P.sel && !P.picked.length, pick: isPicked(s.index) }"
          @click="pickScene(s.index, $event)" @dblclick="emit('open', s.index)">
          <span class="bs-n" :style="{ '--c': chainColor(s.chain) }">{{ s.index + 1 }}</span><span class="bs-t">{{ mmss(s.start) }}</span>
          <span class="bs-x">{{ text(s) }}<i v-if="lineOf(s)">{{ lineOf(s) }}</i></span>
          <span class="bs-st"><small>{{ t('board.script.episode', { n: epOf(s.index)?.n }) }}</small></span>
        </div>
      </template>
      <template v-else>
        <template v-for="e in eps" :key="e.n">
          <div class="bs-ep" :class="{ open: isOpen(e.n) }" :style="{ '--c': chainColor(e.chain) }">
            <button type="button" class="bs-tw" :aria-expanded="isOpen(e.n)" @click="toggle(e.n)"><Icon :name="isOpen(e.n) ? 'collapse' : 'expand'" :size="12" /></button>
            <button type="button" class="bs-epn" :title="t('board.script.episodeTitle')" @click="pickEpisode(e.n)">{{ t('board.script.episode', { n: e.n }) }}</button>
            <span class="bs-t">{{ mmss(e.start) }}–{{ mmss(e.end) }}</span>
            <span class="bs-about" :title="t('board.script.chainNote')" @click="toggle(e.n)">{{ e.about }}</span>
            <small class="bs-cnt">{{ t('board.script.scenes', e.scenes.length) }}</small>
          </div>
          <template v-if="isOpen(e.n)">
            <div v-for="s in e.scenes" :key="s.index" role="listitem" class="bs-line" draggable="true" :title="t('board.script.drag')"
              :class="{ on: s.index === P.sel && !P.picked.length, pick: isPicked(s.index), drag: from === s.index, over: over === s.index }"
              @click="pickScene(s.index, $event)" @dblclick="emit('open', s.index)"
              @dragstart="from = s.index" @dragend="from = null; over = null" @dragover.prevent="from !== null && (over = s.index)" @dragleave="over = null" @drop.prevent="drop(s.index)">
              <span class="bs-n">{{ s.index + 1 }}</span><span class="bs-t">{{ mmss(s.start) }}–{{ mmss(s.end) }}</span>
              <span class="bs-x">{{ text(s) || t('board.card.notWritten') }}<i v-if="lineOf(s)">{{ lineOf(s) }}</i></span>
              <span class="bs-st">
                <Icon v-if="s.status === 'check'" name="warn" :size="13" class="bs-warn" />
                <Icon v-if="s.locked && !p.manual" name="lock" :size="13" :title="t('board.script.pinnedOne')" />
                <i class="bs-dot" :class="{ ok: !!shotPng(s.index) }" :title="shotPng(s.index) ? t('board.script.shot') : t('board.script.notShotOne')" />
                <small>{{ s.kind === 'new' ? t('board.card.new') : t('board.card.cont') }}</small></span>
            </div>
          </template>
        </template>
      </template>
    </div>
  </section>
</template>
