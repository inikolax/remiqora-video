// «Снять ролик»: what the main button does and says - shoot what is left, only mix, only re-finish, or open the
// finished video - with the time it takes; and what to look at before a long shoot («Перед съёмкой», ShootConfirm):
// the model that won't do what the storyboard asks, LoRA of another model, edited text not in the prompt yet, scenes
// without their first frame, shots from before an edit. The shooting panel, the board's top bar and the video page share it.
import { computed } from 'vue'
import { S, banner } from './store'
import { P, dirtyScenes, flushSave, outLabel } from './project'
import { post } from './api'
import { staleShot } from './board'
import { mins } from './format'
import { t } from '../i18n'
import type { Plan } from './types'

export function useShoot(p: () => Plan) {
  const st = computed(() => P.proj!.settings)
  const q = computed(() => S.cfg!.qualities)
  const cur = computed(() => q.value.find((x) => x.id === st.value.quality) || q.value[0])
  const eta = (x: { id: string; per_scene: number }) => (P.est && P.est[x.id] ? P.est[x.id].seconds : x.per_scene * p().scenes.length + 40)
  const est = computed(() => P.est && P.est[cur.value.id])
  const saved = computed(() => (P.proj!.renders || {})[cur.value.id])
  // nothing left to do: the button opens the video
  const done = computed(() => (est.value && est.value.to_shoot === 0 && !est.value.remix && !est.value.refinish && saved.value && saved.value.complete && saved.value.video ? saved.value : null))
  const mainLabel = computed(() => {
    const e = est.value
    return e && e.remix ? t('board.shoot.mix') : e && e.refinish ? t('video.again.refinish', { out: outLabel(st.value) }) : e && e.to_shoot === 0 ? t('board.shoot.build') : t('video.again.shoot')
  })
  const mainIcon = computed(() => (est.value && est.value.remix ? 'music' : est.value && est.value.to_shoot === 0 ? 'film' : 'clapper'))
  const note = computed(() => {
    const e = est.value, n = p().scenes.length
    if (!e) return ''
    return (e.to_shoot === 0 ? (e.remix ? t('board.shoot.onlyMix') : e.refinish ? t('board.shoot.onlyOut') : t('board.shoot.onlyJoin'))
      : e.cached ? t('board.shoot.fromCache', { k: e.cached, n, x: e.to_shoot }) : t('board.shoot.toShoot', { x: t('board.scenesAcc', e.to_shoot) }))
      + ' · ' + (e.measured ? t('board.shoot.perSceneMeasured', { t: mins(e.per_scene), n: e.measured }) : t('board.shoot.perScene', { t: mins(e.per_scene) }))
  })

  // the model: what it won't do with this storyboard
  const model = computed(() => (S.cfg?.video_models || []).find((m) => m.id === (st.value.video_model || 'h3')) || null)
  const modelWarn = computed(() => {
    const m = model.value, pl = p(), out: string[] = []
    if (!m) return out
    const lines = pl.scenes.some((s) => (s.lines || []).some((l: any) => (l.text || '').trim()))
    const faces = !!pl.ref_photo && (pl.cast || []).some((c) => c.photo || c.from_photo)
    if (!m.voice && lines) out.push(t('board.shoot.mute', { m: m.name }))
    if (!m.refs && faces) out.push(t('board.shoot.noFaces', { m: m.name }))
    if (!m.sound && !st.value.track) out.push(t('board.shoot.noSound', { m: m.name }))
    return out
  })
  // a LoRA of another model in the video's list (the model changed): its model shoots without it
  const foreign = (id: string) => { const l = S.loras.find((x) => x.id === id); return !!l && l.model !== (st.value.video_model || 'h3').replace(/^rq_/, '') }
  const foreignLora = computed(() => ((st.value.loras || []) as { id: string }[]).some((u) => foreign(u.id)))
  const dirty = computed(() => dirtyScenes(p()))
  // a storyboard drawn for its frames (a hero with a portrait, some scenes with a drawn first frame): the new scenes
  // still without one are shot from the text alone and the face may differ there
  const noFrame = computed(() => {
    const pl = p()
    if (pl.mode === 'none' || !(pl.cast || []).some((c) => c.photo || c.from_photo)) return []
    const isNew = (s: Record<string, any>) => s.kind === 'new' && (s.raw === undefined || s.raw === null)
    if (!pl.scenes.some((s) => isNew(s) && (s.start_photo || '').startsWith('frame_'))) return []
    return pl.scenes.filter((s) => isNew(s) && !s.start_photo).map((s) => s.index as number)
  })
  const stale = computed(() => p().scenes.filter((s) => staleShot(s.index)).map((s) => s.index as number))
  // drawn frames whose face missed the hero's (app/frames.py: frame.ok false): the shot takes that face
  const unlike = computed(() => unlikeOf(p()))
  // only the assembly is left and no text waits for its prompt: no question before it
  const quick = computed(() => !!est.value && est.value.to_shoot === 0 && !dirty.value.length)
  return { st, q, cur, eta, est, done, mainLabel, mainIcon, note, model, modelWarn, foreign, foreignLora, dirty, noFrame, stale, unlike, quick }
}
// scene numbers for a line of text: «3, 5, 8» - the first eight, then «…»
export const sceneList = (ix: number[]) => ix.slice(0, 8).map((i) => i + 1).join(', ') + (ix.length > 8 ? '…' : '')
// «Перерисовать непохожие» (app/frames.py unlike): the scenes whose drawn frame is not like the hero, one job; a new
// frame stays only when its face is closer to the hero's
export const unlikeOf = (p: Plan) => p.scenes.filter((s) => s.kind === 'new' && (s.start_photo || '').startsWith('frame_') && s.frame?.ok === false)
  .map((s) => s.index as number)
export async function redrawUnlike() {
  await flushSave()
  try { S.jobs = [...S.jobs, await post(`/api/projects/${P.proj!.id}/frames`, { unlike: true })] } catch (e) { banner((e as Error).message) }
}
