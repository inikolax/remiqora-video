// What each scene's shot is now, for the video screen and the graph alike: from the live render job, else from the
// last finished render of this quality. One place, so the graph's nodes say exactly what the video screen says.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { P, lastRender, liveRender } from './project'
import { mins } from './format'
import { t } from '../i18n'

export interface ShotRow { index: number; status: string; key?: string; seconds?: number; estimate?: number; png: string | null; mp4: string | null }
export interface ShotText { cap: string; tone: string; pct: number | null; st: string }

export function useShots(id: () => string) {
  const now = ref(Date.now())
  const q = computed(() => P.proj?.settings.quality || 'draft')
  const saved = computed(() => (P.proj?.renders || {})[q.value])
  const job = computed(() => liveRender(id()))
  const run = computed(() => (job.value && job.value.status === 'running' ? job.value : null))
  const last = computed(() => lastRender(id()))

  const rows = computed<ShotRow[]>(() => {
    const pl = P.proj?.plan, j = job.value || last.value, sv = saved.value
    if (!pl) return []   // the project is still loading
    if (j && j.progress?.scenes && (j.status === 'running' || j.status === 'queued' || !sv || (j.finished || 0) > sv.finished)) {
      return (j.progress.scenes as any[]).map((r) => ({ ...r, png: r.key && r.status !== 'running' && r.status !== 'queued' ? `scenes/${r.key}.png` : null,
        mp4: r.key && (r.status === 'done' || r.status === 'cached') ? `scenes/${r.key}.mp4` : null }))
    }
    // the last render's shots by the scene's id (a render before the ids: by its place)
    if (sv) return pl.scenes.map((s, i) => { const x = sv.shots.find((y: any) => (y.id ? y.id === s.id : y.index === i)); return x ? { index: i, status: x.cached ? 'cached' : 'done', key: x.key, seconds: x.seconds, png: x.png, mp4: x.file } : { index: i, status: 'none', png: null, mp4: null } })
    return pl.scenes.map((s) => ({ index: s.index, status: 'none', png: null, mp4: null }))
  })
  const ready = computed(() => rows.value.filter((r) => r.status === 'done' || r.status === 'cached').length)
  // when the current scene started, for its own countdown
  const curIdx = computed(() => rows.value.findIndex((r) => r.status === 'running'))
  const sceneStart = ref(Date.now())
  watch(curIdx, () => { sceneStart.value = Date.now() })
  const sceneLeft = (r: ShotRow) => Math.max(5, (r.estimate || 0) - (now.value - sceneStart.value) / 1000)

  function shot(r: ShotRow, i: number): ShotText {
    const j = run.value
    let cap = '', tone = ''
    if (r.status === 'done') { cap = `${Math.round(r.seconds || 0)} ${t('common.s')}`; tone = 'ok' }
    else if (r.status === 'cached') { cap = t('video.shot.cached'); tone = 'ok' }
    else if (r.status === 'running') cap = j && j.phase === 'sampling' && j.steps ? t('video.shot.step', { step: j.step, steps: j.steps }) : j && j.phase === 'loading' ? t('video.shot.loading') : j ? t('video.shot.preparing') : ''
    else if (r.status === 'queued') cap = P.proj?.plan?.scenes[i]?.kind === 'continue' ? t('video.shot.waitsFrame', { i }) : t('video.shot.queued')
    else if (r.status === 'skipped') cap = t('video.shot.skipped')
    const pct = r.status === 'running' && j ? Math.round(j.phase === 'sampling' ? 8 + (j.steps ? 84 * j.step / j.steps : 0) : ['decoding', 'saving'].includes(j.phase) ? 95 : 4) : null
    const st = r.status === 'done' || r.status === 'cached' ? t('video.shot.done') : r.status === 'running' ? `~${mins(sceneLeft(r))}` : r.status === 'queued' ? t('video.shot.queued') : r.status === 'skipped' ? '' : t('video.shot.none')
    return { cap, tone, pct, st }
  }

  let tick: ReturnType<typeof setInterval>
  onMounted(() => { tick = setInterval(() => { now.value = Date.now() }, 1000) })
  onUnmounted(() => clearInterval(tick))
  return { now, q, saved, job, run, last, rows, ready, curIdx, sceneLeft, shot }
}
