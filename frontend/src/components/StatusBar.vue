<script setup lang="ts">
// What the video card does, as a pill in the header (after Remiqora's status strip): the worker's colour, the job in
// words, its share and time left; a click opens the details - the job, the queue, who holds the memory. The two
// meters stand beside it on a wide window (from 1600 px) and are always in the panel. A meter turns amber from 80 %
// and red from 92 %: there a render starts to swap or runs out of memory. The video memory is split by who holds it
// (the Windows counter per process). The job's progress is a line along the header's bottom edge.
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, post } from '../lib/api'
import { S, banner, jobKindName, pollJobs, pollSystem, projectName, stageKind } from '../lib/store'
import { gb } from '../lib/format'
import type { Job, Mem } from '../lib/types'

const { t } = useI18n()
// who holds the memory: its colour; the name is status.holder.<key>
const HOLDERS: Record<string, string> = { engine: '#7F77DD', llm: '#1D9E75', backend: '#378ADD', other: '#888780' }
const holderName = (k: string) => t(`status.holder.${k}`)
const pctOf = (m: Mem) => Math.min(100, Math.round((m.used / m.total) * 100))
const level = (m: Mem) => (m.used / m.total >= 0.92 ? 'bad' : m.used / m.total >= 0.8 ? 'warn' : '')
const holders = computed(() => (S.sys?.vram_by || []).filter((h) => h.gb >= 0.05).map((h) => ({ ...h, label: holderName(h.key), color: HOLDERS[h.key] })))
const ramRows = computed(() => Object.entries(S.sys?.procs || {}).filter(([, v]) => v) as [string, number][])

const run = computed(() => S.jobs.find((j) => j.status === 'running'))
const queued = computed(() => S.jobs.filter((j) => j.status === 'queued'))
const color = (j?: Job) => (!j ? 'var(--faint)' : ['render', 'scene', 'graph', 'take'].includes(j.kind) ? 'var(--accent)' : 'var(--ok)')
// a rough share of the job done: elapsed against its estimate (the estimate knows the cache and the cold start)
const pct = (j?: Job) => (!j ? null : j.kind === 'scene' && j.phase === 'sampling' && j.steps ? Math.round((100 * j.step) / j.steps)
  : j.estimate ? Math.min(99, Math.round((100 * j.elapsed) / j.estimate)) : null)
const left = (j: Job) => { const s = Math.max(0, Math.round(j.estimate - j.elapsed)); return s >= 60 ? t('status.leftMin', { n: Math.round(s / 60) }) : t('status.leftS', { n: s }) }

// the pill is HTML (the model's name bold): what comes from a job's params or the system - a model's or an LLM's
// name, a stage's message - is escaped, so a name with «<» shows as text and never becomes markup
const ENT: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
const h = (x: unknown) => String(x ?? '').replace(/[&<>"']/g, (c) => ENT[c])
// the same words as plain text (a title, the panel's row)
const plain = (x: string) => x.replace(/<[^>]+>/g, '').replace(/&(amp|lt|gt|quot|#39);/g, (e) => Object.keys(ENT).find((k) => ENT[k] === e) || e)
// what the card does, in words: the running job, or what still sits in memory
function actText(j: Job | undefined, nq: number) {
  if (!j) {
    const s = S.sys
    const held = s?.llm ? t('status.heldLlm', { name: h(s.llm) }) : s?.engine === 'ready' && (s.engine_ram || 0) > 2 ? t('status.heldEngine', { name: h(s.engine_model || 'H3'), gb: gb(s.engine_ram!) }) : ''
    return nq ? t('status.inQueue', { n: nq }) : `${t('status.gpuFree')}${held ? ' · ' + held : ''}`
  }
  const pr = j.progress || {}
  // phase 10: the model that shoots; phase 11: the scene being shot may have its own
  const who = h((pr.current != null && pr.scenes?.[pr.current]?.model) || j.params?.model || 'H3')
  const step = () => (j.phase === 'sampling' && j.steps ? ` · ${t('status.step', { step: j.step, steps: j.steps })}`
    : j.phase === 'loading' || j.phase === 'starting' ? ` · <span class="warn-t">${t('status.loadingModel')}</span>` : '')
  if (j.kind === 'render') {
    const stage = ['assembling', 'mixing', 'interpolating', 'upscaling'].includes(pr.stage) ? t(`status.stage.${pr.stage}`) : ''
    if (stage) return `<b>${who}</b> · ${stage}`
    const done = (pr.scenes || []).filter((x: any) => ['done', 'cached'].includes(x.status)).length
    return `<b>${who}</b> · ${t('status.sceneShot', { cur: pr.current != null ? pr.current + 1 : '…', done, all: h(j.params.scenes) })}` + step()
  }
  if (j.kind === 'graph') {
    const n = Object.values(pr.nodes || {}) as any[], done = n.filter((x) => ['done', 'cached'].includes(x.status)).length
    return `<b>${t('status.graph')}</b> · ${who} · ${t('status.nodesDone', { done, all: n.length })}` + step()
  }
  const secsOf = () => t('status.secs', { n: Math.round(j.elapsed) })
  const k = stageKind(j)   // a clip's writer job draws the places and the frames after the storyboard
  if (k === 'scene') return `<b>${h(j.params?.model_name || 'H3')}</b> · ${t('status.lab')} · ${j.phase === 'sampling' ? t('status.step', { step: j.step, steps: j.steps }) : t('status.preparing')}`
  if (k === 'take') return `<b>${who}</b> · ${t('status.takeOf', { n: h(Number(j.params?.scene ?? 0) + 1) })}` + step()
  if (k === 'voice') return `<b>Demucs</b> · ${t('status.voiceOf', { n: h(Number(j.params?.scene ?? 0) + 1) })} · ${secsOf()}`
  if (k === 'cast_tries') return `<b>Krea 2</b> · ${t('status.castTries')}${pr.message ? ` · ${h(pr.message)}` : ''}${j.phase === 'sampling' && j.steps ? ` · ${t('status.step', { step: j.step, steps: j.steps })}` : ''}`
  if (k === 'draw') return `<b>Krea 2</b> · ${t('status.drawing')}${j.phase === 'sampling' && j.steps ? ` · ${t('status.step', { step: j.step, steps: j.steps })}` : ''}`
  if (k === 'frame' || k === 'unlike') return `<b>FLUX.2 Klein</b> · ${t('status.frames', { cur: pr.scene != null ? pr.scene + 1 : '…', done: pr.done || 0, all: h(pr.total || j.params?.scenes || '…') })}` + step()
  if (k === 'place') return `<b>Krea 2</b> · ${t('status.places', { done: pr.done || 0, all: h(pr.total || j.params?.places || '…') })}` + step()
  if (k === 'lyrics') return `<b>Whisper</b> · ${t('status.lyrics')} · ${secsOf()}`
  const what = k === 'translate' ? (j.params?.what === 'look' ? t('status.trLook') : t('status.trPrompt')) : j.params?.how === 'ru' ? `${t('status.trScenes')}${j.steps ? ` · ${t('status.stepOf', { step: j.step, steps: j.steps })}` : ''}` : k === 'describe' || j.params?.how === 'describe' ? t('status.describing')
    : k === 'places' ? t('status.gathering') : k === 'write' ? t('status.writing') : k === 'graph-llm' ? t('status.graphLlm') : t('status.rewriting')
  return `<b>${t('status.writer')}</b> · ${what} · ${secsOf()}`
}
// the pill's words: the job, the queue, what sits in memory - or, idle and empty, the short «GPU свободна»
const pillText = computed(() => (!run.value && !queued.value.length && !S.sys?.llm && !(S.sys?.engine === 'ready' && (S.sys.engine_ram || 0) > 2)
  ? t('status.gpuIdle') : actText(run.value, queued.value.length)))
const kind = jobKindName
const proj = (j: Job) => j.params?.project as string | undefined

const panel = ref(false)
const away = () => { panel.value = false }
const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') panel.value = false }
onMounted(() => { document.addEventListener('click', away); document.addEventListener('keydown', esc) })
onUnmounted(() => { document.removeEventListener('click', away); document.removeEventListener('keydown', esc) })

function stop(j: Job) {
  if (!confirm(j.kind === 'render' ? t('status.confirmStopRender') : t('status.confirmStop'))) return
  post(`/api/jobs/${j.id}/cancel`).then(pollJobs).catch((e) => banner(e.message))
}
const unqueue = (j: Job) => post(`/api/jobs/${j.id}/cancel`).then(pollJobs).catch((e) => banner(e.message))
async function unload() {
  try { await api('/api/engine/free', { method: 'POST' }); await pollSystem() } catch (e) { banner((e as Error).message) }
}
</script>

<template>
  <div v-if="run" class="jobline" :style="{ '--c': color(run) }"><i :style="{ width: `${pct(run) || 0}%` }" /></div>
  <div class="statusbar">
    <div class="act" :class="{ on: !!run }" :style="{ '--c': color(run) }">
      <button type="button" class="act-btn" :aria-expanded="panel" aria-haspopup="dialog" :title="plain(actText(run, queued.length))" @click.stop="panel = !panel">
        <i class="act-dot" /><span class="act-text" v-html="pillText" />
        <span v-if="run" class="act-pct"><b v-if="pct(run) != null">{{ pct(run) }}%</b><span v-if="run.estimate > run.elapsed" class="act-left">{{ left(run) }}</span></span>
        <span v-if="queued.length" class="q">+{{ queued.length }}</span></button>
      <div v-if="panel" class="act-panel" role="dialog" :aria-label="t('status.panel')" @click.stop>
        <template v-if="run">
          <div class="ap-head"><i :style="{ background: color(run) }" /><b>{{ kind(run) }}</b><span v-if="proj(run)">«{{ projectName(proj(run)!) }}»</span></div>
          <div class="ap-row muted"><span>{{ plain(actText(run, 0)) }}</span><span>{{ pct(run) != null ? `${pct(run)}%` : '' }}{{ run.estimate > run.elapsed ? ` · ${left(run)}` : '' }}</span></div>
          <span class="bar big" role="progressbar" :aria-valuenow="pct(run) || 0" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${pct(run) || 0}%`, background: color(run) }" /></span>
          <div class="ap-acts"><router-link v-if="proj(run)" class="btn" :to="run.kind.startsWith('graph') ? `/g/${proj(run)}` : `/p/${proj(run)}${run.kind === 'render' ? '/video' : ''}`" @click="panel = false">{{ t('status.openVideo') }}</router-link>
            <router-link v-else-if="run.kind === 'scene'" class="btn" to="/lab" @click="panel = false">{{ t('status.openLab') }}</router-link>
            <button type="button" class="btn danger" @click="stop(run)">{{ t('common.stop') }}</button></div>
        </template>
        <template v-else>
          <p class="muted">{{ t('status.freeText') }}</p>
          <div v-if="S.sys?.engine === 'ready' && !queued.length" class="ap-acts"><button type="button" class="btn" :title="t('status.unloadTitle')" @click="unload">{{ t('status.unload') }}</button></div>
        </template>
        <div v-if="queued.length" class="ap-sec"><span class="lbl">{{ t('status.queue') }}</span>
          <div v-for="j in queued" :key="j.id" class="ap-row"><span>{{ kind(j) }}{{ proj(j) ? ` · ${projectName(proj(j)!)}` : "" }}</span>
            <button type="button" class="ghost" :aria-label="t('status.unqueue')" @click="unqueue(j)">×</button></div></div>
        <div class="ap-sec"><span class="lbl">{{ t('status.memory') }}</span>
          <div v-if="S.sys?.ram" class="ap-m"><div class="ap-row"><span class="muted">{{ t('status.ram') }}</span><span><b>{{ gb(S.sys.ram.used) }}</b> / {{ gb(S.sys.ram.total) }} {{ t('common.gb') }} · {{ pctOf(S.sys.ram) }}%</span></div>
            <span class="bar big"><i :class="level(S.sys.ram)" :style="{ width: `${pctOf(S.sys.ram)}%` }" /></span>
            <div v-for="[k, v] in ramRows" :key="k" class="ap-row muted"><span>{{ t('status.holds', { name: holderName(k) }) }}</span><span>{{ gb(v) }} {{ t('common.gb') }}</span></div></div>
          <div v-if="S.sys?.vram" class="ap-m"><div class="ap-row"><span class="muted">{{ S.sys.vram.name || t('status.vram') }}</span><span><b>{{ gb(S.sys.vram.used) }}</b> / {{ gb(S.sys.vram.total) }} {{ t('common.gb') }} · {{ pctOf(S.sys.vram) }}%</span></div>
            <span class="bar big"><i v-for="h in holders" :key="h.key" :style="{ width: `${Math.min(100, (h.gb / S.sys.vram.total) * 100)}%`, background: h.color }" /></span>
            <div v-for="h in holders" :key="h.key" class="ap-row"><span><i class="sw" :style="{ background: h.color }" />{{ h.label }}<small v-if="h.key === 'llm' && S.sys.llm">{{ S.sys.llm }}</small></span><span>{{ gb(h.gb) }} {{ t('common.gb') }}</span></div>
            <div v-if="S.sys.vram.load != null || S.sys.vram.temp != null" class="ap-row muted"><span>{{ S.sys.vram.load != null ? t('status.gpuLoad', { n: S.sys.vram.load }) : '' }}</span><span>{{ S.sys.vram.temp != null ? `${S.sys.vram.temp}°C` : '' }}</span></div></div>
          <div class="ap-row muted"><span><i class="sw" :style="{ background: S.sys?.llm ? 'var(--ok)' : '#5a5a68' }" />{{ S.sys?.llm ? t('status.llmLoaded', { name: S.sys.llm }) : t('status.llmUnloaded') }}</span></div></div>
      </div>
    </div>
    <div v-if="S.sys" class="meters" role="group" :aria-label="t('status.memory')">
      <span v-if="S.sys.ram" class="meter" :title="ramRows.map(([k, v]) => `${holderName(k)}: ${gb(v)} ${t('common.gb')}`).join(' · ')"><span>{{ t('status.ramShort') }}</span>
        <span class="bar" role="progressbar" :aria-valuenow="pctOf(S.sys.ram)" aria-valuemin="0" aria-valuemax="100"><i :class="level(S.sys.ram)" :style="{ width: `${pctOf(S.sys.ram)}%` }" /></span>
        <b>{{ gb(S.sys.ram.used) }}<small>/{{ Math.round(S.sys.ram.total) }} {{ t('common.gb') }}</small></b></span>
      <span v-if="S.sys.vram" class="meter" :title="holders.map((h) => `${h.label}: ${gb(h.gb)} ${t('common.gb')}`).join(' · ')"><span>{{ t('status.vramShort') }}</span>
        <span class="bar" role="progressbar" :aria-valuenow="pctOf(S.sys.vram)" aria-valuemin="0" aria-valuemax="100">
          <i v-for="h in holders" :key="h.key" :style="{ width: `${Math.min(100, (h.gb / S.sys.vram.total) * 100)}%`, background: h.color }" /><i v-if="!holders.length" :class="level(S.sys.vram)" :style="{ width: `${pctOf(S.sys.vram)}%` }" /></span>
        <b>{{ gb(S.sys.vram.used) }}<small>/{{ Math.round(S.sys.vram.total) }} {{ t('common.gb') }}</small></b></span>
    </div>
  </div>
</template>
