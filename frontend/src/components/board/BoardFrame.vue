<script setup lang="ts">
// The board's «Кадр»: the selected scene's chosen take big, what happens in it and who says what under it, ‹ › to the
// neighbours. «Подряд» plays on: a scene ends - the next one is selected and plays. «Подробно» opens the scene on the
// whole page.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import ScenePlayer from './ScenePlayer.vue'
import { P } from '../../lib/project'
import { castName, fromOf, isRaw } from '../../lib/board'
import { chainColor } from '../../lib/consts'
import { mmss } from '../../lib/format'
import type { Plan, Scene } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan; s: Scene }>()
const emit = defineEmits<{ open: [] }>()
const through = ref(false)
const go = (i: number) => { if (i >= 0 && i < props.p.scenes.length) { P.picked = []; P.sel = i } }
const onEnded = () => { if (through.value && props.s.index < props.p.scenes.length - 1) go(props.s.index + 1) }
const from = computed(() => fromOf(props.p, props.s))
const lines = computed(() => (props.p.mode === 'none' ? [] : (props.s.lines || []).filter((l: any) => (l.text || '').trim())))
const who = (n: number) => ((props.p.cast?.length || 0) > 1 ? castName(props.p.cast![n - 1] || {}, n - 1).replace(/^\d+\.\s*/, '') : t('board.look.hero'))
const problems = computed(() => (props.s.status === 'check' ? (props.s.problems_ru || props.s.problems || []).join('; ') : ''))
</script>

<template>
  <section class="bf">
    <ScenePlayer :s="s" :autoplay="through" @ended="onEnded" />
    <div class="bf-row">
      <button type="button" class="btn" :disabled="s.index === 0" :title="t('board.detail.prev')" @click="go(s.index - 1)"><Icon name="back" :size="14" /></button>
      <b class="bf-n">{{ t('idea.sceneN', { n: s.index + 1 }) }}</b>
      <span class="sd-kind" :style="{ '--c': chainColor(s.chain) }"><Icon :name="s.kind === 'new' ? 'clapper' : 'link'" :size="13" />{{ s.kind === 'new' ? t('board.card.new') : t('board.card.cont') }}</span>
      <span class="muted">{{ mmss(s.start) }}–{{ mmss(s.end) }}<template v-if="from"> · {{ t('board.detail.startsFrom', { n: from.index + 1 }) }}</template></span>
      <button type="button" class="btn" :disabled="s.index === p.scenes.length - 1" :title="t('board.detail.next')" @click="go(s.index + 1)"><Icon name="forward" :size="14" /></button>
      <span class="grow" />
      <label class="check-row" :title="t('board.frame.playThroughTitle')"><input v-model="through" type="checkbox">{{ t('board.frame.playThrough') }}</label>
      <button type="button" class="btn" :title="t('board.frame.fullTitle')" @click="emit('open')"><Icon name="expand" :size="14" />{{ t('board.frame.full') }}</button>
    </div>
    <p v-if="!isRaw(s) && s.ru" class="bf-what">{{ s.ru }}</p>
    <p v-else-if="isRaw(s)" class="bf-what bf-raw muted" :title="s.raw_ru || s.raw">{{ s.raw_ru || s.raw }}</p>
    <p v-if="lines.length" class="card-lines bf-lines"><span v-for="l in lines" :key="l.who"><b>{{ l.how === 'sing' ? '♪' : who(l.who) + ':' }}</b> «{{ l.text }}»</span></p>
    <div v-if="problems" class="warn-line"><Icon name="warn" :size="14" /><span>{{ problems }}</span></div>
  </section>
</template>
