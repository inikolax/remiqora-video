<script setup lang="ts">
// «Сделать ролик» (app/autopilot.py) as one bar for every way, a song's clip or a story from text: the seven steps
// Слова → Сценарий → Герой → Места → Кадры → Съёмка → Монтаж (lib/home.ts maps the server's stages on them), the
// share of the whole done (the stages' estimates, the frames and the scenes counted where they are), the time left,
// «Остановить» and «Открыть и поправить». A stop of «Спрашивать меня» shows under it (AutoAsk.vue). Not running:
// where it failed or was stopped (project.autopilot) and «Продолжить» from there. On the home (the job before its
// project exists, and `compact` on a gallery card), on the board and on the video screen.
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import AutoAsk from './AutoAsk.vue'
import RouteSteps, { type RouteItem } from './RouteSteps.vue'
import WriterThinking from './WriterThinking.vue'
import { post } from '../lib/api'
import { S, banner, live, pollJobs } from '../lib/store'
import { P, liveAuto } from '../lib/project'
import { type AutoState, type BeatProgress, type Step, BEAT_ICON, BEAT_STEPS, STEP_ICON, beatCount, isBeatState, stageIdsOf, stepOf, stepSecs, stepsDone, stepsRun } from '../lib/home'
import { mins } from '../lib/format'
import type { Job } from '../lib/types'

const props = defineProps<{ jobId?: string; pid?: string; state?: AutoState | null; compact?: boolean }>()
const emit = defineEmits<{ again: [] }>()
const { t } = useI18n()
const router = useRouter()
const route = useRoute()

const j = computed<Job | undefined>(() => (props.jobId ? S.jobs.find((x) => x.id === props.jobId) : props.pid ? liveAuto(props.pid) : undefined))
const running = computed(() => !!j.value && live(j.value))
const auto = computed(() => (j.value as any)?.progress?.auto as { stages: { id: string; est: number; done: boolean }[]; stage: string | null; t?: number; what?: string } | undefined)
const stages = computed(() => auto.value?.stages || [])
const ask = computed(() => (running.value ? ((j.value as any)?.progress?.ask || null) : null) as Record<string, any> | null)
const project = computed(() => props.pid || (j.value?.params?.project as string | undefined) || '')

// «Бит-клип»: its own seven steps (lib/home.ts BEAT_STEPS), the server's stages one to one; the counters from progress.beat
const beat = computed(() => isBeatState(auto.value) || isBeatState(props.state) || (j.value?.params as any)?.what === 'beat' || stages.value.some((x) => x.id === 'pool' || x.id === 'pictures'))
const beatNow = computed(() => (running.value ? auto.value?.stage : props.state && !props.state.finished ? props.state.stage : null) || null)
const beatProg = computed(() => (j.value as any)?.progress?.beat as BeatProgress | undefined)
const beatNum = computed(() => (running.value ? beatCount(beatNow.value, beatProg.value) : { n: '', extra: 0 }))
// the seven steps: running - the job's own stages; not - the project's word on them
const clip = computed(() => stages.value.some((x) => x.id === 'words') || (auto.value?.what || props.state?.what || props.state?.req?.what
  || (j.value?.params?.song || props.state?.req?.song ? 'clip' : 'story')).startsWith('clip'))
const cur = computed<Step | null>(() => (beat.value ? (beatNow.value as Step | null) : running.value ? stepOf(auto.value?.stage, j.value) : props.state && !props.state.finished ? stepOf(props.state.stage) : null))
const done = computed(() => (running.value ? stages.value.filter((x) => x.done).map((x) => x.id) : props.state?.done || []))
const doneSteps = computed(() => stepsDone(done.value, clip.value, cur.value, !running.value && !!props.state?.finished))
const name = (s: Step) => t(beat.value ? `beat.step.${s}` : `home.step.${s}`)
// only the steps that run (the switches of the home's route «Как снимаем»)
const steps = computed(() => stepsRun(running.value ? stages.value.map((x) => x.id) : stageIdsOf(props.state?.req)))
// the row as the home's route draws it (RouteSteps.vue): done, now, still to come, each as wide as its estimate
const secsOf = computed(() => stepSecs(stages.value))
// a beat clip's row: every step the job runs (all seven when it is not running), done / now / still to come as the others
const beatItems = computed<RouteItem[]>(() => {
  const ids = (stages.value.length ? BEAT_STEPS.filter((s) => stages.value.some((x) => x.id === s)) : [...BEAT_STEPS]) as string[]
  const fin = !running.value && !!props.state?.finished
  const at = ids.indexOf(beatNow.value || '')
  return ids.map((s, k) => {
    const now = running.value && s === beatNow.value
    const dn = fin || done.value.includes(s) || (!running.value && at > k)
    const est = stages.value.find((x) => x.id === s)?.est
    const cnt = now && beatNum.value.n ? `${beatNum.value.n}${beatNum.value.extra ? ' · ' + t(s === 'pictures' ? 'beat.redraws' : 'beat.reshoots', { n: beatNum.value.extra }) : ''}` : ''
    // the bar draws its tiles by the home's Step type; a beat step's id only keys the tile
    return { id: s as Step, name: name(s as Step), icon: BEAT_ICON[s as keyof typeof BEAT_ICON], state: now ? 'now' : dn ? 'done' : 'on',
      time: now ? cnt || t('home.stepNow') : dn || est == null ? '' : t('home.stepTime', { t: mins(est) }), label: t(`beat.stepTitle.${s}`) } as RouteItem
  })
})
const items = computed<RouteItem[]>(() => beat.value ? beatItems.value : steps.value.map((s) => {
  const now = s === cur.value, done = doneSteps.value.has(s) && !now, sec = secsOf.value[s]
  return { id: s, name: name(s), icon: STEP_ICON[s], state: now ? 'now' : done ? 'done' : 'on', 
    time: now ? count.value || t('home.stepNow') : done || sec == null ? '' : t('home.stepTime', { t: mins(sec) }), label: t(`home.stepTitle.${s}`) }
}))

// the share of the whole: the stages done by their estimates, the current one by what it counts (frames, scenes) or
// by its time against its estimate (the job's own clock: elapsed from its start)
const pct = computed(() => {
  const jj = j.value as any, a = auto.value
  if (!jj || !a || !stages.value.length) return null
  const total = stages.value.reduce((s, x) => s + Math.max(1, x.est), 0)
  let sum = stages.value.filter((x) => x.done).reduce((s, x) => s + Math.max(1, x.est), 0)
  const st = stages.value.find((x) => x.id === a.stage)
  if (st) {
    const pr = jj.progress || {}
    let f = a.t && jj.started ? (jj.elapsed - (a.t - jj.started)) / Math.max(1, st.est) : 0
    if (a.stage === 'frames' && pr.total) f = pr.done / pr.total
    if (a.stage === 'pictures' && pr.beat?.pictures?.total) f = pr.beat.pictures.done / pr.beat.pictures.total
    if (a.stage === 'scenes' && pr.beat?.scenes?.total) f = pr.beat.scenes.done / pr.beat.scenes.total
    if (a.stage === 'render' && pr.scenes?.length) f = pr.scenes.filter((x: any) => ['done', 'cached'].includes(x.status)).length / pr.scenes.length
    sum += Math.max(1, st.est) * Math.min(0.97, Math.max(0, f))
  }
  return Math.min(99, Math.round((100 * sum) / total))
})
const left = computed(() => (j.value?.estimate && j.value.estimate > j.value.elapsed ? t('home.left', { t: mins(j.value.estimate - j.value.elapsed) }) : ''))
// a scene count while shooting: «Съёмка 12/29»
const count = computed(() => {
  const pr = (j.value as any)?.progress || {}
  if (beat.value) return beatNum.value.n ? `${beatNum.value.n}${beatNum.value.extra ? ' · ' + t(cur.value === 'pictures' as any ? 'beat.redraws' : 'beat.reshoots', { n: beatNum.value.extra }) : ''}` : ''
  if (cur.value === 'shoot' && pr.scenes?.length) return `${pr.scenes.filter((x: any) => ['done', 'cached'].includes(x.status)).length}/${pr.scenes.length}`
  if (cur.value === 'frames' && pr.total) return `${pr.done || 0}/${pr.total}`
  return ''
})

async function stop(question = t('home.stopAsk')) {
  if (!j.value || !confirm(question)) return false
  try { await post(`/api/jobs/${j.value.id}/cancel`); await pollJobs() } catch (e) { banner((e as Error).message); return false }
  return true
}
// «Открыть и поправить»: on its own project - the autopilot stopped and the place of the step opened (the hero's
// casting, the places, the scenes); elsewhere (the home) - the project opened, the autopilot going on
async function fix() {
  const pid = project.value
  if (!pid) return
  const here = route.params.id === pid
  if (!here) { router.push(`/p/${pid}`); return }
  if (running.value && !(await stop(t('home.fixAsk')))) return
  if (route.name !== 'board') router.push(`/p/${pid}`)
  P.tab = cur.value === 'hero' ? 'cast' : cur.value === 'places' ? 'places' : 'scenes'
}

// not running: the project's word on it (a failure, a stop), or the home's job that ended before its project
// a stage set with no job running and not finished: the studio was restarted mid-way - stopped there too
const stopped = computed(() => (!running.value && props.state && !props.state.finished && (props.state.error || props.state.stopped || props.state.stage) ? props.state : null))
const homeEnd = computed(() => (!running.value && props.jobId && j.value && !j.value.params?.project ? j.value : null))
const resuming = computed(() => !!project.value && !!liveAuto(project.value))
async function resume() {
  try { const r = await post(`/api/projects/${project.value}/autopilot`); S.jobs = [...S.jobs, r] } catch (e) { banner((e as Error).message) }
}
const stageName = (s?: string | null) => name((beat.value ? s || 'words' : stepOf(s || 'words') || 'words') as Step)
</script>

<template>
  <div v-if="running || stopped" class="sb" :class="{ compact }" role="status">
    <RouteSteps :items="items" :compact="compact" />
    <template v-if="running">
      <span class="bar big" role="progressbar" :aria-valuenow="pct || 0" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${pct || 0}%` }" /></span>
      <div class="sb-row">
        <span class="muted">{{ j!.status === 'queued' ? t('home.queued') : ask ? t('home.waiting') : cur ? `${name(cur)}${count ? ' ' + count : ''}` : '' }}</span>
        <span class="grow" /><span class="muted sb-num"><b v-if="pct != null">{{ pct }}%</b> {{ ask ? '' : left }}</span>
        <router-link v-if="compact && project" class="link-btn" :to="`/p/${project}`">{{ t('home.open') }}</router-link>
        <button v-else-if="project && !ask" type="button" class="btn" @click="fix"><Icon name="pen" :size="13" />{{ t('home.openFix') }}</button>
        <button v-if="compact || !ask" type="button" class="btn sb-stop" @click="stop()"><Icon name="stop" :size="13" />{{ t('home.stop') }}</button>
      </div>
      <WriterThinking v-if="!compact && !ask" :job="j" />
      <AutoAsk v-if="ask && !compact && project" :pid="project" :ask="ask" @stop="stop()" @fix="fix" />
    </template>
    <div v-else-if="stopped" class="sb-row warn-line">
      <Icon name="warn" :size="14" /><span class="sb-why">{{ stopped.error ? t('home.failedAt', { stage: stageName(stopped.stage), err: stopped.error }) : t('home.stoppedAt', { stage: stageName(stopped.stage) }) }}</span>
      <button type="button" class="primary" :disabled="resuming" @click="resume"><Icon name="play" :size="13" />{{ t('home.resume') }}</button>
    </div>
  </div>
  <div v-else-if="homeEnd && homeEnd.status === 'error'" class="sb sb-row warn-line">
    <Icon name="warn" :size="14" /><span class="sb-why">{{ homeEnd.error }}</span>
    <button type="button" class="primary" @click="emit('again')"><Icon name="play" :size="13" />{{ t('home.again') }}</button>
  </div>
</template>

<style scoped>
.sb { display: flex; flex-direction: column; gap: 10px; padding: 12px 14px; border: 1px solid var(--rule-2); border-radius: 12px; background: var(--panel); }
.sb.compact { padding: 0; border: 0; background: none; gap: 6px; }
.sb.compact .bar { display: none; }
.sb-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.sb-num { font-variant-numeric: tabular-nums; }
.sb-stop { color: var(--bad); }
.sb.compact .btn { min-height: 28px; padding: 0 8px; font-size: 12px; }
.sb-row.warn-line { flex-wrap: wrap; }
.sb-why { flex: 1; min-width: 200px; }
.sb .primary { flex: none; width: auto; min-height: 36px; padding: 0 16px; font-size: 14px; border-radius: 10px; }
</style>
