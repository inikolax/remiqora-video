<script setup lang="ts">
// «Перед съёмкой»: «Снять ролик» is one click for minutes to half an hour of the GPU, so first what will be shot (how
// many scenes, the time), in which quality, by which model to which output, and what to look at - the model's
// limits, LoRA of another model, edited text not in the prompt yet (put in first by default), new scenes without
// their first frame, frames not like the hero, shots from before an edit - each with the way to its fix. One button shoots.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import HelpModal from '../help/HelpModal.vue'
import { P, outLabel, startRender } from '../../lib/project'
import { S } from '../../lib/store'
import { redrawUnlike, sceneList, useShoot } from '../../lib/shoot'
import { mins } from '../../lib/format'
import type { Plan } from '../../lib/types'

const { t } = useI18n()
const router = useRouter()
const props = defineProps<{ p: Plan; open: boolean; quality?: string }>()
const emit = defineEmits<{ close: [] }>()
const { st, q, cur, eta, model, modelWarn, foreignLora, dirty, noFrame, stale, unlike } = useShoot(() => props.p)
const framing = computed(() => S.jobs.some((j) => j.kind === 'frame' && (j.status === 'running' || j.status === 'queued') && j.params?.project === P.proj?.id))

const qid = ref(cur.value.id)
const sync = ref(true)
watch(() => props.open, (on) => { if (on) { qid.value = props.quality || cur.value.id; sync.value = true } })
const qx = computed(() => q.value.find((x) => x.id === qid.value) || cur.value)
const e = computed(() => P.est && P.est[qid.value])
const n = computed(() => props.p.scenes.length)
const sizeOf = (id: string) => model.value?.sizes[id]?.w || q.value.find((x) => x.id === id)?.w
const what = computed(() => {
  const x = e.value
  if (!x) return t('board.shoot.toShoot', { x: t('board.scenesAcc', n.value) })
  if (x.to_shoot === 0) return x.remix ? t('board.shoot.onlyMix') : x.refinish ? t('board.shoot.onlyOut') : t('board.shoot.onlyJoin')
  return t('board.pre.shoot', { x: t('board.scenesAcc', x.to_shoot), n: n.value }) + (x.cached ? ` · ${t('board.pre.ready', { k: x.cached })}` : '')
})

// the way to a fix: a scene on the board, or the video's shooting settings
function toScene(i: number) {
  emit('close')
  P.tab = 'scenes'
  P.sel = i
  P.picked = []
  router.push(`/p/${P.proj!.id}`)
}
function toSettings() { emit('close'); P.tab = 'video'; router.push(`/p/${P.proj!.id}`) }

function go() {
  emit('close')
  startRender(qid.value === st.value.quality ? undefined : qid.value, sync.value)
}
</script>

<template>
  <HelpModal :open="open" :title="t('board.pre.title')" icon="clapper" narrow @close="emit('close')">
    <div class="pre">
      <dl class="pre-facts">
        <div><dt>{{ t('board.pre.what') }}</dt><dd><b>{{ what }}</b><small>~{{ mins(eta(qx)) }}</small></dd></div>
        <div><dt>{{ t('idea.model') }}</dt><dd>{{ model?.name || 'MiniMax H3' }}</dd></div>
        <div><dt>{{ t('board.shoot.output') }}</dt><dd>{{ outLabel(st) }}</dd></div>
      </dl>
      <div class="stack" style="gap:8px"><span class="lbl">{{ t('board.shoot.quality') }}</span>
        <div class="seg"><button v-for="x in q" :key="x.id" type="button" :class="{ on: x.id === qid }" :aria-pressed="x.id === qid" @click="qid = x.id">{{ x.id === 'final' ? t('board.quality.final') : t('board.quality.draft') }}<small>{{ sizeOf(x.id) }} · ~{{ mins(eta(x)) }}</small></button></div></div>

      <div class="stack pre-checks" style="gap:10px"><span class="lbl">{{ t('board.pre.check') }}</span>
        <div v-if="dirty.length" class="pre-dirty">
          <div class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('board.pre.dirty', { list: sceneList(dirty) }, dirty.length) }}</span></div>
          <label class="check-row"><input v-model="sync" type="checkbox">{{ t('board.pre.sync') }}</label>
          <span v-if="!sync" class="muted small">{{ t('board.pre.syncOff') }}</span></div>
        <div v-for="x in modelWarn" :key="x" class="warn-line"><Icon name="warn" :size="14" /><span>{{ x }}
          <button type="button" class="link-btn" @click="toSettings">{{ t('board.pre.toSettings') }}</button></span></div>
        <div v-if="foreignLora && model" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('board.shoot.foreignLora', { m: model.name }) }}
          <button type="button" class="link-btn" @click="toSettings">{{ t('board.pre.toSettings') }}</button></span></div>
        <div v-if="noFrame.length" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('board.pre.noFrame', { list: sceneList(noFrame) }, noFrame.length) }}
          <button type="button" class="link-btn" @click="toScene(noFrame[0])">{{ t('board.pre.toScene', { n: noFrame[0] + 1 }) }}</button></span></div>
        <div v-if="unlike.length" class="warn-line"><Icon name="warn" :size="14" /><span>{{ t('board.pre.unlike', { list: sceneList(unlike) }, unlike.length) }}
          <button type="button" class="link-btn" :disabled="framing" @click="redrawUnlike">{{ t('board.pre.redrawUnlike') }}</button>
          <button type="button" class="link-btn" @click="toScene(unlike[0])">{{ t('board.pre.toScene', { n: unlike[0] + 1 }) }}</button></span></div>
        <div v-if="stale.length" class="warn-line pre-info"><Icon name="retake" :size="14" /><span>{{ t('board.pre.stale', { list: sceneList(stale) }, stale.length) }}</span></div>
        <span v-if="!dirty.length && !modelWarn.length && !(foreignLora && model) && !noFrame.length && !unlike.length && !stale.length" class="muted small">{{ t('board.pre.allGood') }}</span>
      </div>
    </div>
    <template #foot>
      <span class="grow" />
      <button type="button" class="btn" @click="emit('close')">{{ t('common.cancel') }}</button>
      <button type="button" class="primary pre-go" @click="go"><Icon name="clapper" :size="16" />{{ dirty.length && sync ? t('board.pre.goSync') : t('board.pre.go') }} · ~{{ mins(eta(qx)) }}</button>
    </template>
  </HelpModal>
</template>
