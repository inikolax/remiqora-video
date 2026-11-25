<script setup lang="ts">
// «Сценарист пула» (pool_writer): the beat clip's writer. The song, the idea and the cast come in by the ports; here the
// genre, the look and the number of shots, «Написать» (the LLM, only by the button) and «Развернуть» (the pool's shots
// become Picture → Scene chains), and the pool itself - every shot the writer made, editable by hand: title, framing, role,
// the picture's text and the motion's, a shot added or removed. A shot that should not be cut is removed on the canvas
// by cutting its link into the beat montage's «сцены».
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import BeatHelp from '../BeatHelp.vue'
import LookPick from '../LookPick.vue'
import { GE, expand, inputsOf, live, nodeOf, runLlm, touch } from '../../lib/graphDoc'
import { AUTO, type LookChoice } from '../../lib/looks'
import { FRAMINGS, GENRES, ROLES, type PoolShot } from '../../lib/beat'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const d = computed(() => (nodeOf(props.id)?.data || {}) as Record<string, any>)
const set = (k: string, v: unknown) => { d.value[k] = v; touch() }
const st = computed(() => GE.state?.nodes[props.id])
const busy = computed(() => !!live())
const pool = computed<PoolShot[]>(() => (d.value.pool || []) as PoolShot[])
const stale = computed(() => st.value?.state === 'stale' || st.value?.state === 'empty')
const hasSong = computed(() => inputsOf(props.id, 'song').length > 0)
const choice = computed<LookChoice>(() => ({ delivery: AUTO, look: d.value.look || AUTO, look_own: '' }))

// the pool's shots, edited in place: a new array each time, so the graph sees the change and saves it
function setShot(i: number, k: keyof PoolShot, v: string) { set('pool', pool.value.map((x, j) => (j === i ? { ...x, [k]: v } : x))) }
const addShot = () => set('pool', [...pool.value, { title: '', framing: 'medium', role: 'atmos', picture_en: '', motion_en: '' }])
const dropShot = (i: number) => set('pool', pool.value.filter((_, j) => j !== i))
const palette = computed(() => (Array.isArray(d.value.palette) ? (d.value.palette as unknown[]).filter((c): c is string => typeof c === 'string' && /^#[0-9a-f]{3,8}$/i.test(c)) : []))
</script>

<template>
  <div class="pp">
    <label class="stack"><span class="lbl">{{ t('beat.genre.lbl') }} <BeatHelp k="genre" /></span>
      <div class="chips"><button v-for="g in GENRES" :key="g" type="button" class="chip" :class="{ on: (d.genre || 'auto') === g }" @click="set('genre', g)">{{ t(`beat.genre.${g}`) }}</button></div></label>
    <div class="stack"><span class="lbl">{{ t('looks.look') }} <BeatHelp k="poolLook" /></span>
      <LookPick :model-value="choice" @update:model-value="set('look', $event.look)" /></div>
    <label class="stack"><span class="lbl">{{ t('beat.pool.n') }} <BeatHelp k="poolN" /> <small>{{ d.n || 16 }}</small></span>
      <input type="range" min="4" max="24" step="1" :value="d.n || 16" @input="set('n', +($event.target as HTMLInputElement).value)"></label>
    <button type="button" class="primary" :disabled="busy || !hasSong" :title="hasSong ? '' : t('beat.pool.needSong')" @click="runLlm([id])">
      <Icon name="spark" :size="18" />{{ pool.length ? (stale ? t('nodesPanel.rewrite') : t('nodesPanel.writeAgain')) : t('nodesPanel.write') }}</button>
    <button type="button" class="btn" :disabled="!pool.length || busy" :title="t('beat.pool.expandTitle')" @click="expand(id)"><Icon name="layers" />{{ t('nodesPanel.expand') }}</button>
    <p class="muted small">{{ t('beat.pool.hint') }}</p>
    <div v-if="d.hero_used" class="stack pp-hero"><span class="lbl">{{ t('beat.hero.writes') }} <BeatHelp k="heroText" /></span>
      <textarea class="field-in mono" rows="3" spellcheck="false" :value="d.hero_en" :aria-label="t('beat.hero.writes')" @input="set('hero_en', ($event.target as HTMLTextAreaElement).value)" />
      <span class="lbl">{{ t('beat.hero.writesHead') }}</span>
      <textarea class="field-in mono" rows="2" spellcheck="false" :value="d.head_en || ''" :aria-label="t('beat.hero.writesHead')" @input="set('head_en', ($event.target as HTMLTextAreaElement).value)" />
      <p v-if="d.hero_fallback" class="muted small warn">{{ t('beat.hero.fallback') }}</p>
      <p class="muted small">{{ t('beat.hero.writesHint') }}</p></div>
    <div v-if="palette.length" class="pp-pal"><span class="lbl">{{ t('beat.pool.palette') }}</span><i v-for="c in palette" :key="c" :style="{ background: c }" :title="c" /></div>

    <div class="sec-head"><span class="lbl">{{ t('beat.pool.shots', pool.length) }} <BeatHelp k="pool" /></span></div>
    <p v-if="!pool.length" class="muted small">{{ t('beat.pool.empty') }}</p>
    <div v-for="(s, i) in pool" :key="i" class="pp-shot">
      <div class="pp-head"><b>{{ i + 1 }}</b>
        <input class="field-in grow" :value="s.title" :placeholder="t('beat.pool.title')" :aria-label="t('beat.pool.title')" @input="setShot(i, 'title', ($event.target as HTMLInputElement).value)">
        <button type="button" class="ghost" :aria-label="t('beat.pool.drop')" :title="t('beat.pool.drop')" @click="dropShot(i)"><Icon name="close" /></button></div>
      <div class="pp-row">
        <select class="field-in" :value="s.role" :aria-label="t('beat.role.lbl')" @change="setShot(i, 'role', ($event.target as HTMLSelectElement).value)"><option v-for="r in ROLES" :key="r" :value="r">{{ t(`beat.role.${r}`) }}</option></select>
        <select class="field-in" :value="s.framing" :aria-label="t('beat.framing.lbl')" @change="setShot(i, 'framing', ($event.target as HTMLSelectElement).value)"><option v-for="f in FRAMINGS" :key="f" :value="f">{{ t(`beat.framing.${f}`) }}</option></select></div>
      <textarea class="field-in mono" rows="3" :value="s.picture_en" spellcheck="false" :placeholder="t('beat.pool.picture')" :aria-label="t('beat.pool.picture')" @input="setShot(i, 'picture_en', ($event.target as HTMLTextAreaElement).value)" />
      <textarea class="field-in mono" rows="2" :value="s.motion_en" spellcheck="false" :placeholder="t('beat.pool.motion')" :aria-label="t('beat.pool.motion')" @input="setShot(i, 'motion_en', ($event.target as HTMLTextAreaElement).value)" />
    </div>
    <button type="button" class="btn" @click="addShot"><Icon name="plus" />{{ t('beat.pool.add') }}</button>
    <p class="muted small">{{ t('beat.pool.removeHint') }} <BeatHelp k="removeShot" /></p>
  </div>
</template>

<style scoped>
.pp { display: flex; flex-direction: column; gap: 10px; }
.pp-hero { gap: 6px; }
.pp-pal { display: flex; align-items: center; gap: 6px; }
.pp-pal i { width: 22px; height: 22px; border-radius: 6px; border: 1px solid var(--rule-2); }
.pp-shot { display: flex; flex-direction: column; gap: 6px; padding: 8px; border-radius: 10px; border: 1px solid var(--rule-2); background: var(--panel); }
.pp-head { display: flex; align-items: center; gap: 6px; }
.pp-head b { min-width: 20px; color: var(--muted); font-variant-numeric: tabular-nums; }
.pp-row { display: flex; gap: 6px; }
.pp-row select { flex: 1; min-width: 0; }
</style>
