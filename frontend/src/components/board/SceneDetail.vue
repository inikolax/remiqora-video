<script setup lang="ts">
// One scene on the whole page («Сцена подробно»): on the left what is seen - the chosen take playing big, the scene's
// chain (where it goes on from and what goes on from it), its takes, side by side on demand; on the right the scene's
// panel without its head and takes (SceneInspector detail); the track under both moves to any scene. ‹ › and ← →
// step to the next scene, PgUp / PgDn to the next chain, Esc goes back to the storyboard.
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import SceneInspector from './SceneInspector.vue'
import ScenePlayer from './ScenePlayer.vue'
import BoardTrack from './BoardTrack.vue'
import { P, liveWriter, rewrite } from '../../lib/project'
import { fromOf, isRaw, moreTake, pickTake, shotPng, takesOf, taking } from '../../lib/board'
import { chainColor } from '../../lib/consts'
import { mmss } from '../../lib/format'
import type { Plan, Scene } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan; s: Scene }>()
const emit = defineEmits<{ close: [] }>()
const fileUrl = (path: string) => `/api/projects/${P.proj?.id}/files/${path}`
const go = (i: number) => { if (i >= 0 && i < props.p.scenes.length) P.sel = i }
const writer = computed(() => (P.proj ? liveWriter(P.proj.id) : undefined))
const shooting = computed(taking)

// the chain: the scenes shot as one piece with this one; where this one starts and what goes on from it
const chain = computed(() => props.p.scenes.filter((x) => x.chain === props.s.chain))
const from = computed(() => fromOf(props.p, props.s))
const next = computed(() => props.p.scenes.filter((x) => fromOf(props.p, x)?.index === props.s.index).map((x) => x.index + 1))
function chainStep(d: number) {
  const list = props.p.scenes, first = chain.value[0].index, last = chain.value[chain.value.length - 1].index
  if (d > 0) go(last + 1)
  else if (props.s.index > first) go(first)   // back to the start of this chain first, then to the one before
  else if (first > 0) go(list.findIndex((x) => x.chain === list[first - 1].chain))
}

// the takes: each shot one plays from the cache; the chosen one is the scene's seed
const takes = computed(() => takesOf(props.s))
const compare = ref(false)
const shot = computed(() => takes.value.filter((x) => x.cached && x.key))
watch(() => props.s.index, () => { compare.value = false })
const vids = ref<HTMLVideoElement[]>([])
function playAll() { for (const v of vids.value) { v.currentTime = 0; v.play().catch(() => {}) } }

function onKey(e: KeyboardEvent) {
  if ((e.target as HTMLElement).closest?.('input, textarea, select, [contenteditable]') || e.altKey || e.ctrlKey || e.metaKey) return
  const k = e.key
  if (k === 'Escape') emit('close')
  else if (k === 'ArrowLeft') go(props.s.index - 1)
  else if (k === 'ArrowRight') go(props.s.index + 1)
  else if (k === 'PageUp') chainStep(-1)
  else if (k === 'PageDown') chainStep(1)
  else return
  e.preventDefault()
}
onMounted(() => addEventListener('keydown', onKey))
onUnmounted(() => removeEventListener('keydown', onKey))
const top = ref<HTMLElement | null>(null)
watch(() => props.s.index, async () => { await nextTick(); top.value?.scrollTo({ top: 0 }) })
</script>

<template>
  <div class="sd">
    <header class="sd-head">
      <button type="button" class="btn" :title="t('board.detail.backTitle')" @click="emit('close')"><Icon name="back" />{{ t('board.detail.back') }}</button>
      <h1>{{ t('idea.sceneN', { n: s.index + 1 }) }}</h1>
      <span class="sd-kind" :style="{ '--c': chainColor(s.chain) }"><Icon :name="s.kind === 'new' ? 'clapper' : 'link'" :size="13" />{{ s.kind === 'new' ? t('board.card.new') : t('board.card.cont') }}</span>
      <span class="sd-crumb">{{ chain.length > 1 ? `${t('board.detail.chain')} ${chain[0].index + 1}–${chain[chain.length - 1].index + 1} · ${t('board.detail.chainN', { k: chain.indexOf(s) + 1, n: chain.length })}` : t('board.detail.chainOne') }}
        · {{ mmss(s.start) }}–{{ mmss(s.end) }}</span>
      <span class="grow" />
      <div class="sd-nav">
        <button type="button" class="btn" :disabled="s.index === 0" :title="t('board.detail.prev')" @click="go(s.index - 1)"><Icon name="back" :size="14" />{{ s.index > 0 ? s.index : '' }}</button>
        <button type="button" class="btn" :disabled="s.index === p.scenes.length - 1" :title="t('board.detail.next')" @click="go(s.index + 1)">{{ s.index < p.scenes.length - 1 ? s.index + 2 : '' }}<Icon name="forward" :size="14" /></button>
      </div>
      <button type="button" class="btn" :disabled="shooting" :title="t('board.takes.moreTitle')" @click="moreTake(s)"><Icon name="clapper" />{{ shooting ? t('board.takes.taking') : t('board.takes.more') }}</button>
      <template v-if="!p.manual && !isRaw(s) && !s.locked">
        <button type="button" class="btn" :disabled="!!writer" @click="rewrite('improve', [s.index])"><Icon name="spark" />{{ t('board.improve') }}</button>
        <button type="button" class="btn" :disabled="!!writer" @click="rewrite('variant', [s.index])"><Icon name="shuffle" />{{ t('board.variant') }}</button>
      </template>
    </header>

    <div class="sd-body">
      <section class="sd-left">
        <template v-if="!compare">
          <ScenePlayer :s="s" />
          <p v-if="s.ru" class="sd-what">{{ s.ru }}</p>
        </template>
        <div v-else class="sd-compare">
          <p v-if="shot.length < 2" class="muted">{{ t('board.detail.compareNone') }}</p>
          <div v-for="tk in shot" :key="tk.seed" class="sd-cmp" :class="{ on: tk.seed === s.seed }">
            <video ref="vids" :src="fileUrl(`scenes/${tk.key}.mp4`)" :poster="fileUrl(`scenes/${tk.key}.png`)" controls playsinline muted />
            <div class="sd-cmp-row"><b>{{ t('board.detail.take', { n: takes.indexOf(tk) + 1 }) }}</b><span class="muted">{{ t('board.detail.seed', { seed: tk.seed }) }}</span><span class="grow" />
              <span v-if="tk.seed === s.seed" class="sd-in">{{ t('board.detail.inVideo') }}</span>
              <button v-else type="button" class="btn" @click="pickTake(s, tk.seed)">{{ t('board.detail.pick') }}</button></div>
          </div>
        </div>

        <div class="sd-chain" :aria-label="t('board.detail.chainLabel')">
          <div class="sd-strip">
            <button v-for="x in chain" :key="x.index" type="button" class="sd-k" :class="{ on: x.index === s.index }" :style="{ '--c': chainColor(x.chain) }"
              :title="x.ru" @click="go(x.index)">
              <img v-if="shotPng(x.index)" :src="shotPng(x.index)!" alt=""><b>{{ x.index + 1 }}</b></button>
          </div>
          <span class="muted small">{{ from ? t('board.detail.startsFrom', { n: from.index + 1 }) : t('board.detail.startsNew') }}<template v-if="next.length">;
            {{ next.length === 1 ? t('board.detail.goesOn', { n: next[0] }) : t('board.detail.goesOnMany', { list: next.join(', ') }) }}</template></span>
        </div>

        <div class="sd-takes">
          <div class="sec-head"><span class="lbl">{{ t('board.detail.takes') }} <small>{{ t('board.takes.sub') }}</small></span>
            <button v-if="shot.length > 1" type="button" class="link-btn" @click="compare = !compare">{{ compare ? t('board.detail.compareOff') : t('board.detail.compare') }}</button>
            <button v-if="compare && shot.length > 1" type="button" class="link-btn" @click="playAll"><Icon name="play" :size="12" />{{ t('board.detail.playAll') }}</button></div>
          <div class="sd-take-list">
            <button v-for="(tk, i) in takes" :key="tk.seed" type="button" class="sd-take" :class="{ on: tk.seed === s.seed }" @click="pickTake(s, tk.seed)">
              <img v-if="tk.cached && tk.key" :src="fileUrl(`scenes/${tk.key}.png`)" alt=""><span v-else class="sd-take-none">{{ t('board.takes.notShot') }}</span>
              <span class="sd-take-t"><b>{{ t('board.detail.take', { n: i + 1 }) }}</b>{{ tk.seed === s.seed ? t('board.detail.inVideo') : t('board.detail.pick') }}<small>{{ t('board.detail.seed', { seed: tk.seed }) }}</small></span></button>
          </div>
          <p v-if="takes.length > 1 && next.length" class="muted small">{{ t('board.detail.pickNote') }}</p>
        </div>
      </section>

      <aside ref="top" class="sd-right">
        <SceneInspector :key="`${s.index}-${s.kind}-${'raw' in s}`" :p="p" :s="s" detail />
      </aside>
    </div>

    <BoardTrack :p="p" />
  </div>
</template>
