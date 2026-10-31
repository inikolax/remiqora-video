<script setup lang="ts">
// «Записать голос»: a few seconds of the user's own voice from the microphone, for a «Трек» that feeds a Scene's
// «голос» (ID-LoRA takes its voice from it). The browser records WebM/Opus; the server keeps it as WAV.
import { onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'

const { t } = useI18n()

const emit = defineEmits<{ done: [file: File] }>()
const MAX_S = 30
const rec = ref<MediaRecorder | null>(null)
const secs = ref(0)
const err = ref('')
let chunks: Blob[] = []
let timer = 0
let stream: MediaStream | null = null

async function start() {
  err.value = ''
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: true, autoGainControl: true } })
  } catch (e) {
    err.value = t('idea.voice.noMic')
    return
  }
  chunks = []
  const r = new MediaRecorder(stream)
  r.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
  r.onstop = () => {
    stream?.getTracks().forEach((t) => t.stop())
    stream = null
    clearInterval(timer)
    const blob = new Blob(chunks, { type: r.mimeType || 'audio/webm' })
    rec.value = null
    if (secs.value >= 1 && blob.size) emit('done', new File([blob], `${t('idea.voice.file')}.webm`, { type: blob.type }))
    else err.value = t('idea.voice.tooShort')
  }
  secs.value = 0
  r.start()
  rec.value = r
  timer = window.setInterval(() => { secs.value++; if (secs.value >= MAX_S) stop() }, 1000)
}
function stop() { if (rec.value && rec.value.state !== 'inactive') rec.value.stop() }
onBeforeUnmount(() => { if (rec.value) { rec.value.onstop = null; stop() } stream?.getTracks().forEach((t) => t.stop()); clearInterval(timer) })
</script>

<template>
  <button v-if="!rec" type="button" class="btn" :title="t('idea.voice.title')" @click="start"><Icon name="volume" />{{ t('idea.voice.record') }}</button>
  <button v-else type="button" class="btn rec-on" @click="stop"><Icon name="stop" />{{ t('idea.voice.stop', { s: secs }) }}</button>
  <span v-if="err" class="warn-line small"><Icon name="warn" :size="12" />{{ err }}</span>
</template>

<style scoped>
.rec-on { color: var(--bad, #e5484d); }
</style>
