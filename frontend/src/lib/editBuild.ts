// The montage's «Собрать ролик» and where the built video stands, for the screen's bar and its panel: built by this
// montage, built by an earlier one, not built, scenes still to shoot, being built now.
import { computed } from 'vue'
import { ED, flushEdit } from './edit'
import { P, startRender } from './project'
import { S, banner } from './store'
import { post } from './api'
import { t } from '../i18n'

export const graphEdit = computed(() => ED.view?.kind === 'graph')
const quality = computed(() => ED.view?.quality || 'draft')
export const buildEst = computed(() => (P.est ? P.est[quality.value] : null))
// the video on disk is the one this montage makes (a video built before the montage existed is the storyboard's)
export const builtSame = computed(() => { const v = ED.view; return !!v?.built && (v.built_sig ? v.built_sig === v.sig : !v.changed) && !buildEst.value?.remix && !buildEst.value?.refinish })
export const building = computed(() => S.jobs.some((j) => (j.status === 'running' || j.status === 'queued') && j.params?.project === ED.id && j.kind !== 'write' && j.kind !== 'rewrite'))

export type BuildState = 'building' | 'error' | 'shoot' | 'same' | 'old' | 'none'
export const buildState = computed<BuildState>(() => {
  const v = ED.view
  if (building.value) return 'building'
  if (graphEdit.value && v?.state === 'error' && v.error) return 'error'
  if (v?.to_shoot) return 'shoot'
  if (builtSame.value) return 'same'
  return v?.built ? 'old' : 'none'
})
// read through t() when read: follows the interface's language
export const BUILD_SAY = {} as Record<BuildState, string>
for (const k of ['building', 'error', 'shoot', 'same', 'old', 'none'] as const) Object.defineProperty(BUILD_SAY, k, { get: () => t(`edit.build.${k}`), enumerable: true })

export async function build() {
  await flushEdit()
  if (!graphEdit.value) { await startRender(); return }
  // a graph's «Монтаж»: «Сделать до сюда» - the node and what it needs (scenes not shot yet are shot too)
  try { S.jobs = [...S.jobs, await post(`/api/projects/${ED.id}/nodes/run`, { targets: [ED.node] })]; banner(t('edit.queued'), 'info') }
  catch (e) { banner((e as Error).message) }
}
