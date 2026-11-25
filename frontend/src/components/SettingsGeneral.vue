<script setup lang="ts">
// #/settings/general «Общие» card of the settings page (views/SettingsView.vue): the engine's switch, the folders and tools, the writer's
// defaults, the interface language. Every value is a key of app/settings.py (data/settings.json), the same ones the model
// cards save; this card only gathers the ones that belong to no single model. Saved at once; the page re-reads every 10 s
// unless a field is being typed in.
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from './Icon.vue'
import FolderList from './FolderList.vue'
import HelpQ from './HelpQ.vue'
import { api, post } from '../lib/api'
import { S, banner, keep, loadLlms, reloadWords } from '../lib/store'
import { currentLocale, setLocale, type LocaleCode } from '../i18n'
import { setTextLang as setTL } from '../lib/textLang'

const { t, locale } = useI18n()
const snap = ref<Record<string, any> | null>(null)
const err = ref('')
const page = ref<HTMLElement | null>(null)
const val = (e: Event) => (e.target as HTMLInputElement).value

async function load() { try { snap.value = await api('/api/app-settings'); err.value = '' } catch (e) { err.value = (e as Error).message } }
// one place saves: the server answers with the page's view again
async function setting(values: Record<string, unknown>) {
  try { snap.value = await post('/api/app-settings', { values }); err.value = '' } catch (e) { err.value = (e as Error).message }
}
const open = (path: string) => post('/api/models/open', { path }).catch((e) => banner(e.message))
async function pickPath(kind: string, start?: string) {
  try { return (await post('/api/models/pick', { kind: kind === 'folder' ? 'folder' : 'file', start })).path as string | null }
  catch (e) { banner((e as Error).message); return null }
}
async function addFolder(f: Record<string, any>) {
  const got = await pickPath('folder', f.dirs[f.dirs.length - 1]?.dir)
  if (got && !f.dirs.some((d: any) => d.dir.toLowerCase() === got.toLowerCase())) setting({ [f.key]: [...f.dirs.map((d: any) => d.dir), got] })
}
async function pick(tl: Record<string, any>) {
  const got = await pickPath(tl.kind, tl.path)
  if (got) setting({ [tl.key]: got })
}
// the writer's model: the default for every job, and the one the app uses now
const llmDefault = (name: string) => setting({ LLM_MODEL: name }).then(loadLlms).then(() => { if (S.llms?.default) { S.llm = S.llms.default; keep() } })
const attention = computed(() => (snap.value?.engine.params || []).find((p: any) => p.key === 'COMFY_ATTENTION'))
const away = computed(() => snap.value?.engine.mode && snap.value.engine.mode !== 'local')
const gbs = (v?: number | null) => (v ? `${v.toFixed(1)} ${t('common.gb')}` : '')

// the texts' language (app/i18n.py): ideas, scene texts, the translator's both ways
const textLang = ref<{ text: string; langs: { code: string; name: string; en?: string }[] } | null>(null)
async function loadLang() { try { textLang.value = await api('/api/lang') } catch { /* the page works without it */ } }
async function setTextLang(code: string) {
  try { textLang.value = await api('/api/lang', { method: 'PUT', body: { text: code } }); setTL(code); banner(t('textlang.saved', { v: textLang.value!.langs.find((x) => x.code === code)?.name || code }), 'info') }
  catch (e) { banner((e as Error).message) }
}
// the interface language: the same switch as the header's (kept in this browser)
function pickLocale(next: LocaleCode) {
  if (locale.value === next) return
  setLocale(next)
  locale.value = next
  reloadWords()
  load()
}

const typing = () => { const a = document.activeElement as HTMLInputElement | null; return !!(a && page.value?.contains(a) && /^(INPUT|TEXTAREA)$/.test(a.tagName)) }
let timer: ReturnType<typeof setTimeout> | undefined
function schedule() { clearTimeout(timer); timer = setTimeout(async () => { if (!typing()) await load(); schedule() }, 10000) }
onMounted(async () => { loadLang(); await load(); schedule() })
onUnmounted(() => clearTimeout(timer))
</script>

<template>
  <div ref="page" class="settings-general">
    <p v-if="!snap && !err" class="muted">{{ t('settings.loading') }}</p>
    <div v-if="err" class="warn-line" role="alert"><Icon name="warn" :size="14" />{{ err || t('settings.readFailed') }}</div>
    <template v-if="snap">
      <!-- Движок -->
      <section class="m-card" aria-labelledby="set-engine">
        <div class="m-title"><h2 id="set-engine">{{ t('settings.engine') }}</h2></div>
        <p class="muted">{{ t('settings.engineSub') }}</p>
        <div v-if="attention" class="m-sec">
          <label class="set-field"><span class="lbl">{{ attention.title }} <HelpQ id="settings" term="Быстрое внимание" :title="attention.title" /></span>
            <span class="row-inline"><input type="checkbox" :aria-label="attention.title" :checked="attention.value" @change="setting({ [attention.key]: ($event.target as HTMLInputElement).checked })">
              <span class="muted small">{{ attention.value ? t('models.switchOn') : t('models.switchOff') }}</span>
              <button v-if="attention.own" type="button" class="ghost" :title="t('models.switchDefault', { v: attention.default ? t('models.switchOn') : t('models.switchOff') })" @click="setting({ [attention.key]: '' })">{{ t('models.reset') }}</button></span>
            <span class="muted small">{{ attention.text }}</span></label>
          <p class="muted small">{{ t('settings.attentionNote') }}</p>
          <p v-if="away" class="warn-line"><Icon name="cloud" :size="14" />{{ t('settings.cloudNow') }}</p>
        </div>
        <div class="set-field"><span class="lbl">{{ t('settings.extraArgs') }} <HelpQ id="settings" term="Свои параметры ComfyUI" :title="t('settings.extraArgs')" /></span>
          <code class="mono">{{ snap.engine.extra_args || t('settings.extraArgsNone') }}</code>
          <span class="muted small">{{ t('settings.extraArgsNote') }}</span></div>
      </section>

      <!-- Папки и инструменты -->
      <section class="m-card" aria-labelledby="set-folders">
        <div class="m-title"><h2 id="set-folders">{{ t('settings.folders') }}</h2></div>
        <p class="muted">{{ t('settings.foldersSub') }}</p>
        <h3 class="set-h">{{ t('settings.toolsTitle') }}</h3>
        <div v-for="tl in snap.tools" :key="tl.key" class="w-row path-row">
          <div class="w-main"><b><i class="m-dot" :class="tl.ok ? 'ok' : 'bad'" :title="tl.ok ? t('models.found') : t('models.notFound')" /> {{ tl.name }}
              <HelpQ id="settings" term="Инструменты" :title="tl.name" :text="tl.text" /></b>
            <span v-if="!tl.ok" class="w-meta">{{ t('models.notFound') }}</span>
            <input class="field-in mono" :value="tl.path" spellcheck="false" :aria-label="t('models.pathAria', { name: tl.name })" @change="setting({ [tl.key]: val($event) })">
            <span v-if="tl.own" class="w-meta">{{ t('models.ownHere', { v: tl.default }) }}</span></div>
          <div class="w-acts"><button type="button" class="btn" @click="pick(tl)">{{ t('models.choose') }}</button>
            <button v-if="tl.own" type="button" class="ghost" :title="t('models.asEnvTitle')" @click="setting({ [tl.key]: '' })">{{ t('models.asEnv') }}</button>
            <button v-if="!(tl.kind === 'command' && !/[\\/]/.test(tl.path))" type="button" class="ghost" :title="t('common.openFolder')" :aria-label="t('common.openFolder')" @click="open(tl.path)"><Icon name="folder" /></button></div></div>
        <h3 class="set-h">{{ t('settings.foldersTitle') }}</h3>
        <details v-for="f in snap.folders" :key="f.key" class="m-fold">
          <summary>{{ f.title }} · {{ t('settings.dirsCount', { n: f.dirs.length }, f.dirs.length) }}
            <HelpQ id="settings" term="Папки" :title="f.title" :text="f.text || undefined" /></summary>
          <FolderList :rows="f.dirs.map((d: any) => ({ dir: d.dir, missing: !d.exists, meta: d.exists ? '' : t('models.noFolder') }))" :label="f.title"
            @save="(l) => setting({ [f.key]: l })" @add="addFolder(f)" @open="open" />
          <span v-if="f.own" class="w-meta">{{ t('models.ownHere', { v: '.env' }) }}
            <button type="button" class="ghost" :title="t('models.asEnvTitle')" @click="setting({ [f.key]: '' })">{{ t('models.asEnv') }}</button></span>
        </details>
      </section>

      <!-- Сценарист -->
      <section class="m-card" aria-labelledby="set-writer">
        <div class="m-title"><h2 id="set-writer">{{ t('settings.writer') }}</h2></div>
        <p class="muted">{{ t('settings.writerSub') }}</p>
        <div class="row2">
          <label class="stack"><span class="lbl">{{ t('settings.model') }} <HelpQ id="settings" term="Модель по умолчанию" :title="t('settings.model')" /></span>
            <select class="field-in" :value="snap.writer.default || ''" :disabled="!snap.writer.models.length" @change="llmDefault(val($event))">
              <option v-if="!snap.writer.models.length" value="">{{ t('settings.noModels') }}</option>
              <option v-for="m in snap.writer.models" :key="m.name" :value="m.name">{{ m.name.replace(/-GGUF$|\.gguf$/i, '') }}{{ m.gb ? ` · ${gbs(m.gb)}` : '' }}</option></select></label>
          <label class="stack"><span class="lbl">{{ t('settings.context') }} <HelpQ id="settings" term="Контекст" :title="t('settings.context')" /></span>
            <select class="field-in" :value="snap.writer.ctx" @change="setting({ LLM_CTX: +val($event) })">
              <option v-for="c in snap.writer.contexts" :key="c" :value="c">{{ t('models.tokens', { n: c.toLocaleString(currentLocale() === 'ru' ? 'ru-RU' : 'en-US') }) }}</option></select></label>
          <label v-if="textLang" class="stack"><span class="lbl">{{ t('settings.textLang') }} <HelpQ id="settings" term="Язык текстов" :title="t('settings.textLang')" /></span>
            <select class="field-in" :value="textLang.text" @change="setTextLang(val($event))">
              <option v-for="l in textLang.langs" :key="l.code" :value="l.code">{{ currentLocale() === 'en' ? l.en || l.name : l.name }}</option></select></label>
        </div>
      </section>

      <!-- Интерфейс -->
      <section class="m-card" aria-labelledby="set-ui">
        <div class="m-title"><h2 id="set-ui">{{ t('settings.ui') }}</h2></div>
        <p class="muted">{{ t('settings.uiSub') }}</p>
        <div class="set-field"><span class="lbl">{{ t('settings.uiLang') }} <HelpQ id="settings" term="Язык интерфейса" :title="t('settings.uiLang')" /></span>
          <div class="lang-seg" role="group" :aria-label="t('header.language')">
            <button type="button" :class="{ on: locale === 'ru' }" :aria-pressed="locale === 'ru'" lang="ru" @click="pickLocale('ru')">RU</button>
            <button type="button" :class="{ on: locale === 'en' }" :aria-pressed="locale === 'en'" lang="en" @click="pickLocale('en')">EN</button></div></div>
      </section>
    </template>
  </div>
</template>
