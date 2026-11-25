<script setup lang="ts">
// «Как снимаем» on the home: what «Сделать ролик» will do, as the steps Слова → Сценарий →
// Герой → Места → Кадры → Съёмка → Монтаж (RouteSteps.vue, the same row the bar shows once it runs). A step's tile
// keeps its width (equal columns, the shooting one and a half); its time «~2 мин» is the server's own estimate
// (POST /api/autopilot/estimate, the figures the job starts with). The header says the whole
// «≈ 14 мин · 6 сцен · 16:9 · MiniMax H3» and holds «Спрашивать меня ↔ Решать самому» (its stops are the flags on «Герой» and «Съёмка»), a line under it what the clicks do. «Герой»,
// «Места», «Кадры» have a switch (the autopilot's hero / places / frames); «Сценарий» and «Съёмка» a select - the writer
// or «пишу сам» (the route ends there, the storyboard opens), the model; «Слова» and «Монтаж» always run. A look that
// draws every frame locks «Кадры» on. `idle`: nothing given yet - the names only.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import RouteSteps, { type RouteItem } from './RouteSteps.vue'
import RouteLora from './RouteLora.vue'
import type { PicLoras, Pick } from './LoraSet.vue'
import { S, loadKreaLoras, loadLoras, lorasFor } from '../lib/store'
import { type RouteEstimate, type Step, STEP_ICON } from '../lib/home'
import { mins } from '../lib/format'
import type { VideoModel } from '../lib/types'

const props = defineProps<{
  idle: boolean; clip: boolean; est: RouteEstimate | null; ask: boolean
  own: boolean; hero: boolean; frames: boolean; places: boolean; forced: boolean
  photo: string | null; model: string; aspect: string; loras: Pick[]; pics: PicLoras
}>()
const emit = defineEmits<{ toggle: [s: Step]; 'update:ask': [v: boolean]; 'update:model': [id: string]; 'update:loras': [v: Pick[]]; 'update:pics': [v: PicLoras] }>()
const { t } = useI18n()

const modelCard = computed(() => (S.cfg?.video_models || []).find((m) => m.id === props.model))
const modelName = computed(() => props.est?.model || modelCard.value?.name || props.model)
const secs = (s: Step) => props.est?.steps?.[s]
const time = (s: Step) => (secs(s) != null ? t('home.stepTime', { t: mins(secs(s)!) }) : '')
const pop = ref<'' | 'write' | 'shoot'>('')

const items = computed<RouteItem[]>(() => {
  const name = (s: Step) => t(`home.step.${s}`)
  const ids: Step[] = [...(props.clip ? ['words' as Step] : []), 'write', 'hero', 'places', 'frames', 'shoot', 'montage']
  if (props.idle) return ids.map((id) => ({ id, name: name(id), icon: STEP_ICON[id], state: 'idle' }))
  const flag = props.ask && !props.own
  return ids.map((id): RouteItem => itemOf(id)).map((x) => ({ ...x, lora: !!loraOf(x.id) }))
  function itemOf(id: Step): RouteItem {
    const base = { id, name: name(id), icon: STEP_ICON[id], lora: false }
    const grey = props.own && !['words', 'write'].includes(id)
    if (grey) {
      const who = id === 'hero' ? t('home.stepWho.hero') : id === 'places' ? t('home.stepWho.places') : id === 'frames' ? t('home.stepWho.frames')
        : id === 'shoot' ? modelName.value : t('home.stepWho.montage')
      return { ...base, who, state: 'grey' }
    }
    switch (id) {
      case 'words': {
        const done = !!props.est?.words_done
        return { ...base, who: t('home.stepWho.words'), state: done ? 'done' : 'on', time: done ? t('home.stepDone') : time(id) }
      }
      case 'write':
        return { ...base, icon: props.own ? 'pen' : 'quill', who: t(props.own ? 'home.writeOwn' : 'home.writeWriter'), pick: true, state: 'on', time: time(id), press: 'menu',
          open: pop.value === 'write', hint: t('home.stepHint.pick'), label: t('home.stepAria.write', { who: t(props.own ? 'home.writeOwn' : 'home.writeWriter') }) }
      case 'hero': {
        const on = props.hero
        const who = props.photo ? t(on ? 'home.stepWho.heroPhoto' : 'home.stepWho.heroPhotoOff') : t('home.stepWho.hero')
        return { ...base, who, photo: props.photo || undefined, state: on ? 'on' : 'off', time: on ? time(id) : t('home.stepSkip'), press: 'toggle', hint: t(on ? 'home.stepHint.skip' : 'home.stepHint.back'),
          flag: on && flag ? t('home.flagStop') : undefined, label: t(`home.stepAria.${on ? 'on' : 'off'}`, { s: base.name }) }
      }
      case 'places': {
        const on = props.places && props.frames
        return { ...base, who: t('home.stepWho.places'), state: on ? 'on' : 'off', time: on ? time(id) : t('home.stepSkip'), press: 'toggle', hint: t(on ? 'home.stepHint.skip' : 'home.stepHint.back'),
          label: t(`home.stepAria.${on ? 'on' : 'off'}`, { s: base.name }) }
      }
      case 'frames': {
        const on = props.frames
        if (props.forced) return { ...base, who: t('home.framesForced'), state: 'on', time: time(id), press: 'toggle', locked: true, hint: t('home.stepHint.locked'), label: t('home.stepAria.locked', { s: base.name, why: t('home.framesForced') }) }
        return { ...base, who: t('home.stepWho.frames'), state: on ? 'on' : 'off', time: on ? time(id) : t('home.stepSkip'), press: 'toggle', hint: t(on ? 'home.stepHint.skip' : 'home.stepHint.back'),
          label: t(`home.stepAria.${on ? 'on' : 'off'}`, { s: base.name }) }
      }
      case 'shoot':
        return { ...base, who: modelName.value, pick: true, state: 'on', time: time(id), press: 'menu', open: pop.value === 'shoot', hint: t('home.stepHint.model'),
          flag: flag ? t('home.flagTrial') : undefined, flagShort: t('home.flagTrialShort'), label: t('home.stepAria.shoot', { who: modelName.value }) }
      default:
        return { ...base, who: t('home.stepWho.montage'), state: 'on', time: time(id) }
    }
  }
})
// the model list opens under «Съёмка» (kept inside the route's width)
const bodyEl = ref<HTMLElement | null>(null)
const popLeft = ref(0)
function press(s: Step, el?: HTMLElement) {
  if (s !== 'shoot' && s !== 'write') { emit('toggle', s); return }
  pop.value = pop.value === s ? '' : s
  const body = bodyEl.value
  if (body && el) popLeft.value = Math.max(0, Math.min(el.getBoundingClientRect().left - body.getBoundingClientRect().left, body.clientWidth - 360))
}
const setScript = (own: boolean) => { if (own !== props.own) emit('toggle', 'write'); pop.value = '' }

// the LoRA in their steps (a chip in the tile): the video's in «Съёмка» (its model's only), Krea 2's in «Герой» (or
// «Места» when the hero is off), FLUX.2 Klein's in «Кадры» - only while that step runs
function loraOf(id: Step): 'video' | 'krea' | 'flux2' | null {
  if (props.idle || props.own) return null
  if (id === 'shoot') return 'video'
  if (id === 'hero' && props.hero) return 'krea'
  if (id === 'places' && !props.hero && props.places && props.frames) return 'krea'
  if (id === 'frames' && props.frames) return 'flux2'
  return null
}
const listOf = (k: 'video' | 'krea' | 'flux2') => (k === 'video' ? props.loras : props.pics[k] || [])
function setList(k: 'video' | 'krea' | 'flux2', v: Pick[]) {
  if (k === 'video') emit('update:loras', v)
  else emit('update:pics', { ...props.pics, [k]: v })
}
const loraLabel = (k: 'video' | 'krea' | 'flux2') => (k === 'video' ? t('home.loraFor', { model: modelName.value }) : t(`loraset.${k}`))
// a new model: the video LoRA of another model's library go, and a line says which
const dropped = ref('')
watch(() => props.model, (m, was) => {
  if (!was || m === was || !S.loras.length || !props.loras.length) return
  const fit = new Set(lorasFor(m).map((l) => l.id))
  const gone = props.loras.filter((u) => !fit.has(u.id))
  if (!gone.length) return
  emit('update:loras', props.loras.filter((u) => fit.has(u.id)))
  dropped.value = t('home.loraDropped', { list: gone.map((u) => u.name).join(', '), model: modelName.value })
})

// the header's estimate: «≈ 14 мин · 6 сцен · 16:9 · MiniMax H3» (a clip: «· финал 1080p»)
const total = computed(() => (props.est ? `≈ ${mins(props.est.total)}` : ''))
// the line under the steps: what a step off costs (and «Вернуть»), «пишу сам», else what the flags and the widths mean
const offs = computed(() => {
  if (props.idle || props.own) return [] as { s: Step; text: string }[]
  const out: { s: Step; text: string }[] = []
  if (!props.hero) out.push({ s: 'hero', text: t(props.photo ? 'home.off.heroPhoto' : 'home.off.hero') })
  if (!props.frames) out.push({ s: 'frames', text: t('home.off.frames') })
  else if (!props.places) out.push({ s: 'places', text: t('home.off.places') })
  return out
})
const hint = computed(() => (!props.ask ? t('home.selfNote') : props.est?.gpu ? t('home.routeHint', { gpu: props.est.gpu }) : t('home.routeHintNoGpu')))

// «Съёмка»'s list: the offered models (installed first, as /api/config sorts them), each with its time a scene
const cards = computed<VideoModel[]>(() => (S.cfg?.video_models || []).filter((m) => !m.imported))
const perScene = (id: string) => (props.est?.models?.[id] != null ? t('home.perScene', { t: mins(props.est.models[id]) }) : '')
const choose = (m: VideoModel) => { if (m.missing.length) return; emit('update:model', m.id); pop.value = '' }
const rootEl = ref<HTMLElement | null>(null)
const outside = (e: Event) => { if (pop.value && rootEl.value && !rootEl.value.contains(e.target as Node)) pop.value = '' }
const esc = (e: KeyboardEvent) => { if (e.key === 'Escape' && pop.value) pop.value = '' }
onMounted(() => { document.addEventListener('pointerdown', outside); document.addEventListener('keydown', esc); if (!S.loras.length) loadLoras(); loadKreaLoras() })
onUnmounted(() => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', esc) })
</script>

<template>
  <section ref="rootEl" class="route" :class="{ idle }" :aria-label="t('home.route')">
    <div class="rt-head">
      <span class="rt-ttl"><Icon name="clapper" :size="16" />{{ t('home.route') }}</span>
      <span v-if="idle" class="rt-idle">{{ t('home.routeIdle') }}</span>
      <template v-else>
        <span class="rt-est" aria-live="polite"><b v-if="total">{{ total }}</b>
          <span v-if="est">· {{ t('home.estimateRest', { n: est.scenes, aspect, model: modelName }) }}<template v-if="clip"> · {{ t('home.final') }}</template></span>
          <span v-else class="muted">{{ aspect }} · {{ modelName }}</span></span>
        <span class="rt-sp" />
        <div v-if="!own" class="rt-ask" role="radiogroup" :aria-label="t('home.askTitle')">
          <button type="button" role="radio" :aria-checked="ask" :class="{ on: ask }" @click="emit('update:ask', true)"><Icon name="flag" :size="14" /><span class="rt-full">{{ t('home.ask') }}</span><span class="rt-short">{{ t('home.short.ask') }}</span></button>
          <button type="button" role="radio" :aria-checked="!ask" :class="{ on: !ask }" @click="emit('update:ask', false)"><Icon name="wand" :size="14" />{{ t('home.self') }}</button></div>
      </template>
    </div>
    <p v-if="!idle" class="rt-how">{{ t(own ? 'home.routeHowOwn' : 'home.routeHow') }}</p>
    <div ref="bodyEl" class="rt-body">
      <RouteSteps :items="items" @press="press">
        <template #lora="{ s }"><RouteLora v-if="loraOf(s.id)" :kind="loraOf(s.id)!" :model="model" :list="listOf(loraOf(s.id)!)" :label="loraLabel(loraOf(s.id)!)"
          @update:list="setList(loraOf(s.id)!, $event)" /></template>
      </RouteSteps>
      <div v-if="pop === 'write' && !idle" class="rt-pop" :style="{ left: `${popLeft}px` }" role="dialog" :aria-label="t('home.writeTitle')">
        <div class="rt-pop-ttl">{{ t('home.writeTitle') }}</div>
        <div role="radiogroup" :aria-label="t('home.writeTitle')">
          <button type="button" role="radio" :aria-checked="!own" class="rt-opt" :class="{ on: !own }" @click="setScript(false)">
            <Icon name="quill" :size="16" /><span class="rt-opt-t"><b>{{ t('home.writeWriter') }}</b><small>{{ t('home.writeWriterSub') }}</small></span></button>
          <button type="button" role="radio" :aria-checked="own" class="rt-opt" :class="{ on: own }" @click="setScript(true)">
            <Icon name="pen" :size="16" /><span class="rt-opt-t"><b>{{ t('home.writeOwn') }}</b><small>{{ t('home.writeOwnSub') }}</small></span></button>
        </div>
      </div>
      <div v-if="pop === 'shoot' && !idle" class="rt-pop" :style="{ left: `${popLeft}px` }" role="dialog" :aria-label="t('home.modelTitle')">
        <div class="rt-pop-ttl">{{ t('home.modelTitle') }}</div>
        <div role="radiogroup" :aria-label="t('home.modelTitle')">
          <button v-for="m in cards" :key="m.id" type="button" role="radio" :aria-checked="m.id === model" class="rt-opt" :class="{ on: m.id === model, miss: m.missing.length }"
            :aria-disabled="m.missing.length > 0 || undefined" @click="choose(m)">
            <Icon name="chip" :size="16" /><span class="rt-opt-t"><b>{{ m.name }}</b><small>{{ m.missing.length ? t('idea.pick.noWeights') : m.text }}</small></span>
            <span class="rt-opt-r">{{ perScene(m.id) }}</span></button>
        </div>
        <router-link v-if="cards.some((m) => m.missing.length)" class="link-btn rt-pop-link" to="/settings/models">{{ t('idea.pick.download') }}</router-link>
        <p class="rt-pop-lora"><Icon name="plug" :size="14" />{{ t('home.loraUnder') }}</p>
      </div>
    </div>
    <p v-if="dropped && !idle" class="rt-drop" role="status"><Icon name="warn" :size="14" />{{ dropped }} <button type="button" class="link-btn" @click="dropped = ''">{{ t('home.got') }}</button></p>
    <div v-if="!idle" class="rt-foot">
      <template v-if="offs.length"><span v-for="o in offs" :key="o.s" class="rt-off">{{ o.text }} <button type="button" class="link-btn" @click="emit('toggle', o.s)">{{ t('home.restore') }}</button></span></template>
      <span v-else-if="own">{{ t('home.scriptOwnNote') }}</span>
      <span v-else>{{ hint }}</span>
    </div>
  </section>
</template>

<style scoped>
.route { container-type: inline-size; display: flex; flex-direction: column; gap: 10px; padding-top: 14px; border-top: 1px solid var(--rule); }
.rt-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
.rt-ttl { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 14.5px; }
.rt-idle { color: var(--muted); font-size: 13px; }
.rt-how { margin: -4px 0 0; color: var(--muted); font-size: 12.5px; }
.rt-drop { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0; color: var(--warn); font-size: 12.5px; }
.rt-est { display: block; color: var(--soft); font-size: 13.5px; font-variant-numeric: tabular-nums; }
.rt-est b { margin-right: 4px; }
.rt-est b { color: var(--text); font-weight: 600; }
.rt-sp { flex: 1; }
.rt-ask { display: inline-flex; padding: 3px; border-radius: 99px; background: var(--field); border: 1px solid var(--rule-input); }
.rt-ask button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 36px; border: 0; border-radius: 99px; padding: 0 14px 0 11px;
  background: none; color: var(--muted); font: 500 13px/1.2 var(--ui); cursor: pointer; }
.rt-ask button:hover:not(.on) { color: var(--text); }
.rt-ask button.on { background: var(--grad); color: #fff; }
.rt-ask button.on:focus-visible { outline: none; box-shadow: 0 0 0 2px #fff; }
.rt-short { display: none; }
.rt-body { position: relative; padding-top: 4px; }
.rt-pop { position: absolute; z-index: 20; top: calc(100% + 8px); width: 360px; max-width: 100%; padding: 10px; border-radius: 12px; border: 1px solid var(--rule-2);
  background: var(--panel); box-shadow: 0 12px 34px rgba(0, 0, 0, .45); }
.rt-pop-ttl { font-weight: 600; font-size: 13.5px; margin: 2px 2px 8px; }
.rt-opt { display: flex; align-items: center; gap: 10px; width: 100%; min-height: 44px; padding: 8px 10px; border: 0; border-radius: 8px; background: none; color: var(--text); text-align: left; cursor: pointer; font: inherit; }
.rt-opt:hover { background: var(--hover); }
.rt-opt.on { background: var(--accent-bg); }
.rt-opt.miss { opacity: .6; cursor: default; }
.rt-opt :deep(svg) { flex: none; color: var(--accent-hi); }
.rt-opt-t { display: flex; flex-direction: column; min-width: 0; }
.rt-opt-t b { font-weight: 500; font-size: 13.5px; }
.rt-opt-t small { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.rt-opt-r { margin-left: auto; flex: none; color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.rt-pop-link { display: inline-block; margin: 6px 10px 0; font-size: 12.5px; }
.rt-pop-lora { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 8px 2px 2px; padding-top: 8px; border-top: 1px solid var(--rule); color: var(--soft); font-size: 13px; }
.rt-pop-lora :deep(svg) { color: var(--accent-hi); }
.rt-foot { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; color: var(--muted); font-size: 12.5px; }
.rt-off .link-btn, .rt-pop-lora .link-btn { min-height: 32px; font-size: 12.5px; margin-left: 6px; }
@container (max-width: 480px) {
  .rt-est { flex: 1 1 100%; }
  .rt-sp, .rt-idle { display: none; }
  .rt-ask { width: 100%; }
  .rt-ask button { flex: 1; }
  .rt-full { display: none; }
  .rt-short { display: inline; }
  /* the model list opens under the steps, not over them */
  .rt-pop { position: static; width: auto; margin-top: 8px; box-shadow: none; }
}
</style>
