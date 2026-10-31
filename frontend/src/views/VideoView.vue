<script setup lang="ts">
// 3. The video: the chain being shot (scene by scene, from the live job), then the assembled video and what comes
// after it (the music, RTX), with the time left.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from '../components/Icon.vue'
import SidePanel from '../components/SidePanel.vue'
import ShootConfirm from '../components/board/ShootConfirm.vue'
import GuideButton from '../components/help/GuideButton.vue'
import { api, post } from '../lib/api'
import { banner, onJobEnd, pollJobs, videoModel } from '../lib/store'
import { P, file, openProject, outLabel, reloadProject, startRender } from '../lib/project'
import { useShots } from '../lib/shots'
import { useShoot } from '../lib/shoot'
import { QL } from '../lib/consts'
import { mins, mmss } from '../lib/format'

const { t } = useI18n()
const props = defineProps<{ id: string }>()
const router = useRouter()
const loaded = ref(false)
const player = ref<HTMLVideoElement | null>(null)
const p = computed(() => P.proj?.plan || null)
const { q, saved, job, run, last, rows, ready, curIdx, sceneLeft, shot } = useShots(() => props.id)
const est = computed(() => P.est && P.est[q.value])
const n = computed(() => p.value?.scenes.length || 0)

// the player: the assembled video when there is one, else the newest finished scene
const src = computed(() => {
  const sv = saved.value
  if (!run.value && sv && (sv.video_up || sv.video) && !(last.value && last.value.status === 'error')) return sv.video_up || sv.video
  return [...rows.value].reverse().find((r) => r.mp4)?.mp4 || null
})
const playerNote = computed(() => (src.value ? '' : run.value ? t('video.firstShooting') : t('video.notShot')))
const picked = ref<string | null>(null)
const shown = computed(() => picked.value || src.value)
watch(src, () => { picked.value = null })
function play(path: string) { picked.value = path; setTimeout(() => player.value?.play().catch(() => {}), 0) }

const left = computed(() => {
  const j = run.value
  if (!j) return 0
  return Math.max(0, rows.value.reduce((a, r) => a + (r.status === 'queued' ? r.estimate || 0 : 0), 0)
    + (curIdx.value >= 0 ? sceneLeft(rows.value[curIdx.value]) : 0)
    + (['assembling', 'upscaling'].includes(j.progress?.stage) ? 0 : 15))
})
const stage = computed(() => (run.value && run.value.progress ? run.value.progress.stage : saved.value ? 'done' : ''))
const width = computed(() => (saved.value ? saved.value.width : run.value?.progress?.width))
const out = computed(() => (P.proj ? outLabel(P.proj.settings) : ''))
const asShot = computed(() => out.value === t('video.asShot'))
// the other quality's button: its hint names the project's model and its frame (the cards' sizes are 16:9's)
const sizeTip = (q: string) => {
  const st = P.proj?.settings, m = videoModel(st?.video_model || 'h3'), s = m?.sizes[q]
  return !m ? undefined : s && (st?.aspect || '16:9') === '16:9' ? `${s.w}×${s.h}, ${m.name}` : m.name
}
// a shoot asks first («Перед съёмкой», the quality picked there); only the assembly left - straight away. The other
// quality sits behind «Ещё»: one click there was a half-hour job
const { quick } = useShoot(() => p.value!)
const ask = ref<string | null>(null)
const more = ref(false)
const shoot = (quality?: string) => { more.value = false; if (!quality && quick.value) startRender(); else ask.value = quality || q.value }
const other = computed(() => (q.value === 'draft' ? 'final' : 'draft'))
const mp4Name = computed(() => `${P.proj?.name || t('video.file')}${saved.value?.out_tag ? '_' + saved.value.out_tag : ''}.mp4`)
const allDone = computed(() => !!(est.value && est.value.to_shoot === 0 && !est.value.remix && !est.value.refinish && saved.value && saved.value.complete))
const againLabel = computed(() => (est.value && est.value.reedit ? t('video.again.reedit') : est.value && est.value.remix ? t('video.again.remix') : est.value && est.value.refinish ? t('video.again.refinish', { out: out.value })
  : allDone.value ? t('video.again.allDone') : saved.value ? t('video.again.changed') : t('video.again.shoot')))
const stages = computed(() => {
  const j = run.value, sv = saved.value, e = est.value, list: { state: string; text: string; note: string }[] = []
  list.push({ state: 'ok', text: t('video.stage.board'), note: t('video.scenesN', n.value) })
  if (j) list.push({ state: j.phase === 'starting' || j.phase === 'loading' ? 'now' : 'ok', text: t('video.stage.model'), note: j.phase === 'starting' ? t('video.stage.starting') : j.phase === 'loading' ? t('video.stage.loading') : t('video.stage.inMemory') })
  list.push({ state: ready.value === n.value ? 'ok' : j && stage.value === 'shooting' ? 'now' : '', text: t('video.stage.scenes', { n: n.value }), note: `${ready.value} / ${n.value}` })
  list.push({ state: stage.value === 'assembling' ? 'now' : !j && sv && sv.video && !(e && e.reedit) ? 'ok' : '', text: P.proj?.edit ? t('video.stage.joinMontage') : t('video.stage.join'),
    note: e && e.reedit && !j ? t('video.stage.montageChanged') : sv && sv.video && !j ? '' : `~5 ${t('common.s')}` })
  const track = P.proj?.settings.track
  if (track) list.push({ state: stage.value === 'mixing' ? 'now' : !j && sv && sv.track_sig && !(e && e.remix) ? 'ok' : '', text: t('video.stage.music', { name: track.name }),
    note: e && e.remix && !e.reedit && !j ? t('video.stage.trackChanged') : !j && sv && sv.track_sig ? '' : `~3 ${t('common.s')}` })
  if (!asShot.value) list.push({ state: stage.value === 'upscaling' || stage.value === 'interpolating' ? 'now' : sv && sv.video_up && !j && !(e && e.refinish) ? 'ok' : '',
    text: out.value, note: e && e.refinish && !j ? t('video.stage.changed') : sv && sv.up_size && !j ? `${sv.up_size}${sv.fps === 48 ? ' · 48 fps' : ''}${sv.hdr ? ' · HDR10' : ''}` : '' })
  return list
})
const stopAfter = () => post(`/api/jobs/${job.value!.id}/stop-after`).then(pollJobs).catch((e) => banner(e.message))
function stopNow() { if (confirm(t('video.stopNowAsk'))) post(`/api/jobs/${job.value!.id}/cancel`).then(pollJobs) }
const openDir = () => api(`/api/projects/${P.proj!.id}/open`, { method: 'POST' }).catch((e) => banner(e.message))

let off: () => void
onMounted(async () => {
  try { await openProject(props.id) } catch (e) { banner((e as Error).message); router.push('/'); return }
  if (!P.proj!.plan) { router.replace(`/p/${props.id}`); return }
  loaded.value = true
  // a render of this project ended: the video, the renders and the estimate are new
  off = onJobEnd((j) => { if (j.params?.project === props.id) reloadProject() })
})
onUnmounted(() => off?.())
</script>

<template>
  <div v-if="loaded && p" class="screen">
    <SidePanel id="video" class="side right" :label="t('video.title')" :width="380">
      <div class="stack" style="gap:10px">
        <span class="lbl title-row"><GuideButton guide="video" compact /> {{ run ? t('video.left') : job ? t('video.inQueue') : saved ? (saved.complete ? t('video.ready') : t('video.notAll')) : t('video.title') }}</span>
        <span class="big">{{ run ? `~${mins(left)}` : saved ? (saved.complete ? mmss(saved.duration || p.seconds || saved.shots.length * 5) : `${saved.shots.length} / ${n}`) : '—' }}</span>
        <div class="bar"><i :style="{ width: `${Math.round((ready / n) * 100)}%` }" /></div>
        <span class="muted" style="font-size:13px">{{ QL[q] || q }} {{ width || '' }}{{ !asShot ? ' → ' + out : '' }}</span></div>
      <ol class="stages">
        <li v-for="x in stages" :key="x.text" :class="x.state"><span>{{ x.state === 'ok' ? '✓' : x.state === 'now' ? '●' : '○' }}</span><span>{{ x.text }}</span><span>{{ x.note }}</span></li>
      </ol>
      <div v-if="last && last.status === 'error'" class="warn-line"><Icon name="warn" :size="14" /><span>{{ last.error }}</span></div>
      <div v-if="saved && saved.up_error && !run" class="warn-line"><Icon name="warn" :size="14" /><span>{{ saved.up_error }}</span></div>
      <div class="stack" style="gap:8px">
        <template v-if="job">
          <button type="button" class="btn" :disabled="job.stop_after" @click="stopAfter"><Icon name="stop" />{{ job.stop_after ? t('video.willStopAfter') : t('video.stopAfter') }}</button>
          <button type="button" class="btn danger" @click="stopNow"><Icon name="close" />{{ t('video.stopNow') }}</button></template>
        <!-- all shot: the next step is the file itself -->
        <a v-else-if="allDone && saved?.video" class="primary" :href="file(saved.video_up || saved.video)" :download="mp4Name"><Icon name="download" :size="18" /><span class="p-lbl"><b>{{ t('video.downloadMp4') }}</b><small>{{ QL[q] }}{{ !asShot ? ' · ' + out : '' }}</small></span></a>
        <button v-else type="button" class="primary" :disabled="allDone" @click="shoot()"><Icon name="play" :size="18" /><span class="p-lbl"><b>{{ againLabel }}</b><small>{{ QL[q] }}{{ est && !allDone ? ` · ~${mins(est.seconds)}` : '' }}</small></span></button>
        <router-link class="btn" :to="`/p/${P.proj!.id}`"><Icon name="back" />{{ t('video.backToBoard') }}</router-link></div>
      <section class="shoot">
        <span class="lbl">{{ !run && saved && saved.video ? t('video.done') : t('video.whenReady') }}</span>
        <div class="stack" style="gap:8px">
          <template v-if="!(allDone && saved?.video && !job)">
            <a v-if="saved && saved.video" class="btn" :href="file(saved.video_up || saved.video)" :download="mp4Name"><Icon name="download" />{{ t('video.downloadMp4') }}</a>
            <a v-else class="btn" aria-disabled="true" style="opacity:.45;pointer-events:none"><Icon name="download" />{{ t('video.downloadMp4') }}</a></template>
          <button type="button" class="btn" @click="openDir"><Icon name="folder" />{{ t('common.openFolder') }}</button>
          <router-link class="btn" :to="`/p/${P.proj!.id}/edit`" :title="t('video.montageTitle')"><Icon name="cut" />{{ t('video.montage') }}</router-link></div>
        <div class="vv-more"><button type="button" class="btn" :disabled="!!job" :aria-expanded="more" :title="t('video.moreTitle')" @click="more = !more">{{ t('video.more') }}{{ more ? '' : '…' }}</button>
          <button v-if="more" type="button" class="btn" :title="sizeTip(other)" @click="shoot(other)"><Icon name="clapper" :size="18" />{{ other === 'final' ? t('video.shootFinal') : t('video.shootDraft') }}{{ P.est && P.est[other] ? ` · ~${mins(P.est[other].seconds)}` : '' }}…</button></div>
        <span class="foot-note" style="text-align:left">{{ t('video.cacheNote') }}</span>
      </section>
    </SidePanel>
    <ShootConfirm :p="p" :open="!!ask" :quality="ask || undefined" @close="ask = null" />
    <main class="main">
      <div class="player" :style="{ aspectRatio: (P.proj!.settings.aspect || '16:9').replace(':', ' / ') }">
        <video ref="player" :src="shown ? file(shown) : undefined" controls playsinline /><div class="player-note">{{ playerNote }}</div></div>
      <div class="shots" :style="{ gridTemplateColumns: `repeat(${Math.min(n, 8)},minmax(0,1fr))` }">
        <figure v-for="(r, i) in rows" :key="i" class="shot" :class="{ now: r.status === 'running' }" :data-play="r.mp4 || undefined" @click="r.mp4 && play(r.mp4)">
          <div class="thumb"><img v-if="r.png" :src="file(r.png)" :alt="t('idea.sceneN', { n: i + 1 })"><span v-if="shot(r, i).pct !== null">{{ shot(r, i).pct }}%</span></div>
          <figcaption><b>{{ i + 1 }}</b><span :class="shot(r, i).tone">{{ shot(r, i).st }}</span><small v-if="shot(r, i).cap" :title="shot(r, i).cap">{{ shot(r, i).cap }}</small></figcaption></figure>
      </div>
    </main>
  </div>
</template>
