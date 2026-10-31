<script setup lang="ts">
// The heroes tab as a casting, everything on one screen: the heroes on the left (more than one: added, up to three, and
// removed here), the chosen one's approved portrait big with their look beside it, edited in place - the gender, the
// age, the look and the outfit; a look edited after the portrait says so and draws from the look again. Under it «Что
// поменять», split by intent: «Поправить черты» keeps the face and changes a detail (features and the user's own words;
// FLUX.2 edits the portrait, hero.adjust), «Другой человек» gives a new face (new tries from the look, the look written
// anew, an own photo). Krea's and FLUX's tries in a strip: a click compares a try with the approved one - before, after
// and what approving it writes into the look - and approves it from there. «В сценах»: how close the face on each shot
// scene is to the portrait (SFace). The voice is a row of its own; «Настроить» opens the full form (LookCard).
import { computed, ref, watch } from 'vue'
import { openZoom, vZoom } from '../../lib/zoom'
import { useI18n } from 'vue-i18n'
import Icon from '../Icon.vue'
import PicLoraLine from '../PicLoraLine.vue'
import { api, post } from '../../lib/api'
import { S, banner } from '../../lib/store'
import { P, flushSave, projectCall, scheduleSave } from '../../lib/project'
import { shotPng } from '../../lib/board'
import { GENDERS } from '../../lib/consts'
import type { Plan } from '../../lib/types'

const { t } = useI18n()
const props = defineProps<{ p: Plan }>()
const emit = defineEmits<{ edit: []; open: [i: number] }>()
const proj = computed(() => P.proj!)
const cast = computed(() => (props.p.cast || []) as Record<string, any>[])
const several = computed(() => props.p.mode === 'several')
const cur = ref(0)
watch(() => cast.value.length, (n) => { if (cur.value >= n) cur.value = Math.max(0, n - 1) })
const c = computed(() => cast.value[cur.value] || {})
const file = (f: string) => `/api/projects/${proj.value.id}/files/${encodeURIComponent(f)}`
const photoOf = (x: Record<string, any>) => (x.photo ? file(x.photo) : x.from_photo && proj.value.settings.photo ? `/api/projects/${proj.value.id}/photo` : null)
const nameOf = (x: Record<string, any>, i: number) => x.name || (cast.value.length > 1 ? t('board.cast.heroN', { n: i + 1 }) : x.gender === 'female' ? t('board.look.heroine') : t('board.look.hero'))
// the scenes a hero is in: with several people their own «who», else all of them
const scenesOf = (i: number) => several.value ? props.p.scenes.filter((s) => (s.who || []).includes(i + 1)).length : props.p.scenes.length

// ---- the look, edited in place (the English follows by «Нарисовать по описанию») ----
const val = (e: Event) => (e.target as HTMLInputElement).value
function setCast(k: string, v: string) {
  const x = cast.value[cur.value]
  if (k === 'age') x.age = Math.max(21, +v || 21)
  else x[k] = v
  if (['ru', 'outfit_ru', 'gender', 'age'].includes(k)) {
    x.ru_dirty = true
    if (photoOf(x)) x.photo_stale = true   // the portrait shows the look before the edit
  }
  scheduleSave(); flushSave()
}
const stale = computed(() => !!c.value.photo_stale && !!photoOf(c.value))
const lookBox = ref<HTMLTextAreaElement>()
const toLook = () => { lookBox.value?.focus(); lookBox.value?.scrollIntoView({ block: 'center', behavior: 'smooth' }) }
function addHero() {
  props.p.cast!.push({ gender: 'female', age: 30, ru: '', outfit_ru: '', en: '', outfit_en: '', ru_dirty: true })
  scheduleSave(); flushSave()
  cur.value = props.p.cast!.length - 1
  banner(t('board.look.added', { n: props.p.cast!.length }), 'info')
}
function delHero() {
  const n = cur.value + 1
  if (!confirm(t('board.look.delAsk', { n }))) return
  props.p.cast!.splice(cur.value, 1)
  for (const sc of props.p.scenes) if (sc.who) sc.who = sc.who.filter((x: number) => x !== n).map((x: number) => (x > n ? x - 1 : x))
  scheduleSave(); flushSave()
}

// ---- the jobs: «Поправить черты», new faces from the look, a description from the photo ----
const job = computed(() => S.jobs.find((j) => (j.kind === 'cast_tries' || j.kind === 'draw') && (j.status === 'running' || j.status === 'queued') && j.params?.project === proj.value.id))
const busy = computed(() => !!job.value)
async function run(path: string, body?: unknown) {
  await flushSave()
  try { S.jobs = [...S.jobs, await post(`/api/projects/${proj.value.id}/cast/${cur.value}/${path}`, body)] } catch (e) { banner((e as Error).message) }
}
const redraw = (n = 4) => run('redraw', { n })
const describe = () => run('describe')
const GROUPS = [{ id: 'age', keys: ['younger', 'older'] }, { id: 'hair', keys: ['shorter', 'longer', 'lighter', 'curly'] },
  { id: 'face', keys: ['smile', 'makeup', 'softer'] }, { id: 'light', keys: ['warm', 'studio'] }]
const picked = ref<string[]>([])
const own = ref('')
const fixErr = ref('')
watch(cur, () => { picked.value = []; own.value = ''; fixErr.value = ''; sel.value = '' })
const changes = computed(() => picked.value.length + (own.value.trim() ? 1 : 0))
function toggle(k: string) {
  fixErr.value = ''
  picked.value = picked.value.includes(k) ? picked.value.filter((x) => x !== k) : [...picked.value, k]
}
async function adjust() {
  if (!changes.value) { fixErr.value = t('board.cast.fixPickErr'); return }
  await run('adjust', { tweaks: picked.value, text: own.value.trim() })
  picked.value = []; own.value = ''
}
async function upload(f?: File) {
  if (!f) return
  const fd = new FormData()
  fd.append('file', f)
  await projectCall('POST', `/cast/${cur.value}/photo`, fd)   // the description stays the user's call: «Описать по фото»
}

// ---- the tries: newest first; a click compares, «Утвердить» approves ----
const tries = computed(() => [...((c.value.tries || []) as Record<string, any>[])].reverse().filter((x) => x.file !== c.value.photo))
const sel = ref('')
watch(tries, (list) => { if (sel.value && !list.some((x) => x.file === sel.value)) sel.value = '' })
const selTry = computed(() => tries.value.find((x) => x.file === sel.value) || null)
const faultOf = (x: Record<string, any>) => (x.faces > 1 ? t('board.cast.twoFaces') : x.faces === 0 ? t('board.cast.noFace') : '')
const keysOf = (x: Record<string, any>) => (x.tweaks || (x.tweak ? [x.tweak] : [])) as string[]
// what approving a try writes into the look: its features but the light, and the user's own words (hero.change_of)
const changeOf = (x: Record<string, any>) => [...keysOf(x).filter((k) => k !== 'warm' && k !== 'studio').map((k) => t(`board.cast.tweak.${k}`)), ...(x.change_ru ? [x.change_ru] : [])].join(', ')
const isAdjust = (x: Record<string, any>) => keysOf(x).length > 0 || !!x.change_ru
const captionOf = (x: Record<string, any>) => faultOf(x) || (isAdjust(x) ? [...keysOf(x).map((k) => t(`board.cast.tweak.${k}`)), ...(x.change_ru ? [x.change_ru] : [])].join(', ') : t('board.cast.try'))
const diffOf = (x: Record<string, any>) => (!isAdjust(x) ? t('board.cast.newFace') : changeOf(x) ? `+ ${changeOf(x)}` : t('board.cast.lightOnly'))
async function approve(x: Record<string, any>) {
  if (!isAdjust(x) && photoOf(c.value) && scenesOf(cur.value) && !confirm(t('board.cast.approveAsk', { n: scenesOf(cur.value) }))) return
  await projectCall('PUT', `/cast/${cur.value}/pick`, { file: x.file })
  sel.value = ''
}
const drop = async (f: string) => { await projectCall('DELETE', `/cast/${cur.value}/tries/${encodeURIComponent(f)}`); if (sel.value === f) sel.value = '' }

// ---- «В сценах»: loaded when the hero or their photo changes, or a render ends ----
const faces = ref<{ index: number; sim: number | null }[]>([])
const fmin = ref(0.3)
const loadingFaces = ref(false)
async function loadFaces() {
  if (!c.value.photo) { faces.value = []; return }
  loadingFaces.value = true
  try { const r = await api<{ faces: { index: number; sim: number | null }[]; min: number }>(`/api/projects/${proj.value.id}/cast/${cur.value}/faces`); faces.value = r.faces; fmin.value = r.min }
  catch { faces.value = [] } finally { loadingFaces.value = false }
}
watch(() => [cur.value, c.value.photo, proj.value.renders?.[proj.value.settings.quality]?.shots?.length], loadFaces, { immediate: true })
const drift = computed(() => faces.value.filter((x) => x.sim !== null && x.sim < fmin.value).length)
const held = computed(() => faces.value.filter((x) => x.sim !== null && x.sim >= fmin.value).length)
const pct = (x: number) => `${Math.round(x * 100)}%`
</script>

<template>
  <div class="cc" :class="{ solo: cast.length < 2 && !several }" :style="{ '--ar': (proj.settings.aspect || '16:9').replace(':', ' / ') }">
    <!-- the heroes -->
    <aside v-if="cast.length > 1 || several" class="cc-who" :aria-label="t('board.bar.cast')">
      <button v-for="(x, i) in cast" :key="i" type="button" :class="{ on: i === cur }" @click="cur = i">
        <img v-if="photoOf(x)" :src="photoOf(x)!" alt=""><span v-else class="cc-nopic"><Icon name="user" :size="20" /></span>
        <span><b>{{ nameOf(x, i) }}</b><small>{{ t('board.cast.inScenes', scenesOf(i)) }}</small></span></button>
      <button v-if="several && cast.length < 3" type="button" class="cc-add" @click="addHero"><span class="cc-nopic"><Icon name="plus" :size="20" /></span>{{ t('board.look.addHero') }}</button>
    </aside>

    <div class="cc-main">
      <div class="cc-top">
        <!-- the approved portrait, or the invitation to draw one -->
        <div v-if="photoOf(c)" class="cc-shot"><img v-zoom :src="photoOf(c)!" :alt="t('board.look.photoAlt')">
          <span class="cc-seal" :class="{ stale }"><i><Icon :name="stale ? 'warn' : 'check'" :size="11" /></i>{{ c.drawn ? t('board.cast.approved') : t('board.cast.ownPhoto') }}<template v-if="faces.length">, {{ t('board.cast.holds', { k: held, n: faces.length }) }}</template></span></div>
        <div v-else class="cc-shot cc-empty"><Icon name="brush" :size="26" /><b>{{ t('board.cast.noPortrait') }}</b><span>{{ t('board.cast.noPortraitHint') }}</span>
          <button type="button" class="primary" :disabled="busy || !(c.ru || c.en)" @click="redraw()"><Icon name="spark" />{{ t('board.cast.draw4') }}</button></div>

        <div class="cc-info">
          <div class="cc-name"><h2>{{ nameOf(c, cur) }}</h2>
            <select class="cc-inl" :aria-label="t('board.look.gender')" :value="c.gender" @change="setCast('gender', val($event))"><option v-for="[k, v] in GENDERS" :key="k" :value="k">{{ v }}</option></select>
            <label class="cc-inl cc-age"><input type="number" min="21" max="99" :aria-label="t('board.look.ageLbl')" :value="c.age || 30" @change="setCast('age', val($event))">{{ t('board.cast.age', c.age || 30).replace(/^\d+\s*/, '') }}</label>
            <span class="grow" />
            <button v-if="several && cast.length > 1" type="button" class="ghost" :title="t('board.look.removeHeroTitle')" @click="delHero"><Icon name="trash" />{{ t('board.look.remove') }}</button></div>
          <label class="cc-field"><span>{{ t('board.cast.look') }}</span><textarea ref="lookBox" rows="3" :placeholder="t('board.cast.lookPh')" :value="c.ru || ''" @change="setCast('ru', val($event))" /></label>
          <label class="cc-field"><span>{{ t('board.cast.outfit') }}</span><textarea rows="2" :placeholder="t('board.cast.outfitPh')" :value="c.outfit_ru || ''" @change="setCast('outfit_ru', val($event))" /></label>
          <div v-if="stale" class="cc-stale"><Icon name="warn" :size="16" /><span>{{ t('board.cast.stale') }}</span>
            <button type="button" class="btn" :disabled="busy" @click="redraw()"><Icon name="spark" />{{ t('board.cast.staleGo') }}</button></div>
          <button type="button" class="ghost cc-all" @click="emit('edit')"><Icon name="pen" :size="14" />{{ t('board.cast.allFields') }}</button>
        </div>
      </div>

      <!-- what to change: the same face, or another person -->
      <section class="cc-change" :aria-label="t('board.cast.change')">
        <div class="cc-h"><b>{{ t('board.cast.change') }}</b><span class="grow" />
          <span v-if="job" class="cc-busy"><i class="spin" />{{ (job.progress as any)?.message || t('status.drawing') }}</span></div>
        <div class="cc-ways">
          <div class="cc-way fix">
            <b><Icon name="sliders" />{{ t('board.cast.fix') }}</b><span class="sub">{{ t('board.cast.fixSub') }}</span>
            <template v-if="photoOf(c)">
              <div v-for="g in GROUPS" :key="g.id" class="cc-grp"><span>{{ t(`board.cast.group.${g.id}`) }}</span>
                <div><button v-for="k in g.keys" :key="k" type="button" class="cc-chip" :aria-pressed="picked.includes(k)" @click="toggle(k)">{{ t(`board.cast.chip.${k}`) }}</button></div></div>
              <input v-model="own" class="field-in" maxlength="200" :placeholder="t('board.cast.ownPh')" @input="fixErr = ''">
              <p v-if="fixErr" class="cc-err" role="alert">{{ fixErr }}</p>
              <button type="button" class="btn cc-go" :disabled="busy" @click="adjust"><Icon name="brush" />{{ changes ? t('board.cast.fixGo', changes) : t('board.cast.fixPick') }}</button>
              <small>{{ t('board.cast.fixNote') }}</small>
            </template>
            <p v-else class="sub">{{ t('board.cast.fixNeedsPhoto') }}</p>
          </div>
          <div class="cc-way">
            <b><Icon name="users" />{{ t('board.cast.person') }}</b><span class="sub">{{ t('board.cast.personSub') }}</span>
            <div class="cc-row"><Icon name="shuffle" /><span>{{ t('board.cast.newFaces') }}</span>
              <button type="button" class="btn" :disabled="busy || !(c.ru || c.en)" @click="redraw()"><Icon name="spark" />{{ t('board.cast.newFacesGo') }}</button></div>
            <div class="cc-row"><Icon name="pen" /><span>{{ t('board.cast.rewrite') }}<small>{{ t('board.cast.rewriteSub') }}</small></span>
              <button type="button" class="btn" @click="toLook">{{ t('board.cast.rewriteGo') }}</button></div>
            <div class="cc-row"><Icon name="image" /><span>{{ t('board.cast.upload') }}<small>{{ t('board.cast.uploadSub') }}</small></span>
              <label class="btn" style="cursor:pointer">{{ t('board.cast.uploadGo') }}<input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="upload(($event.target as HTMLInputElement).files?.[0])"></label></div>
            <div v-if="c.photo || c.from_photo" class="cc-row"><Icon name="face" /><span>{{ t('board.look.describe') }}<small>{{ t('board.look.describeTitle') }}</small></span>
              <button type="button" class="btn" :disabled="busy" @click="describe"><Icon name="spark" />{{ t('board.look.describe') }}</button></div>
          </div>
        </div>
        <PicLoraLine :models="['krea', 'flux2']" :hint="t('loraset.heroHint')" />
      </section>

      <!-- the tries: a click compares, the approve is in the comparison -->
      <section v-if="photoOf(c) || tries.length" class="cc-strip">
        <div class="cc-h"><b>{{ t('board.cast.tries') }}</b><span>{{ t('board.cast.triesSel') }}</span></div>
        <div class="cc-tries">
          <figure v-if="photoOf(c)" class="cc-try on"><img v-zoom :src="photoOf(c)!" alt=""><figcaption>{{ t('board.cast.approvedShort') }}</figcaption></figure>
          <figure v-for="x in tries" :key="x.file" class="cc-try" :class="{ bad: faultOf(x), sel: x.file === sel }">
            <button type="button" class="cc-pick" :aria-pressed="x.file === sel" @click="sel = x.file === sel ? '' : x.file"><img :src="file(x.file)" alt="" loading="lazy"></button>
            <button type="button" class="cc-drop" :aria-label="t('board.cast.drop')" :title="t('board.cast.drop')" @click="drop(x.file)"><Icon name="close" :size="13" /></button>
            <button type="button" class="cc-zoom" :aria-label="t('zoom.open')" :title="t('zoom.open')" @click="openZoom(file(x.file))"><Icon name="expand" :size="12" /></button>
            <figcaption>{{ captionOf(x) }}</figcaption></figure>
        </div>
        <div v-if="selTry" class="cc-cmp">
          <figure><img v-if="photoOf(c)" v-zoom :src="photoOf(c)!" alt=""><span v-else class="cc-nopic"><Icon name="user" :size="22" /></span><figcaption>{{ t('board.cast.was') }}</figcaption></figure>
          <figure class="now"><img v-zoom :src="file(selTry.file)" alt=""><figcaption>{{ t('board.cast.now') }}</figcaption></figure>
          <div class="cc-cmp-t"><span class="lbl">{{ t('board.cast.inLook') }}</span><p :class="{ add: isAdjust(selTry) && changeOf(selTry) }">{{ diffOf(selTry) }}</p>
            <p v-if="faultOf(selTry)" class="cc-err">{{ faultOf(selTry) }}</p>
            <div class="acts"><button type="button" class="btn cc-ok" @click="approve(selTry)"><Icon name="check" />{{ t('board.cast.approve') }}</button>
              <button type="button" class="btn" @click="drop(selTry.file)">{{ t('board.cast.drop') }}</button></div></div>
        </div>
      </section>

      <!-- the face in the shot scenes -->
      <section v-if="c.photo" class="cc-strip">
        <div class="cc-h"><b>{{ t('board.cast.inShot') }}</b>
          <span>{{ loadingFaces ? t('board.cast.checking') : faces.length ? (drift ? t('board.cast.drift', drift) : t('board.cast.allHold')) : t('board.cast.noneShot') }}</span></div>
        <div v-if="faces.length" class="cc-scenes">
          <button v-for="x in faces" :key="x.index" type="button" class="cc-sc" :class="{ drift: x.sim !== null && x.sim < fmin }" :title="t('board.cast.toScene', { n: x.index + 1 })" @click="emit('open', x.index)">
            <img v-if="shotPng(x.index)" :src="shotPng(x.index)!" alt="" loading="lazy">
            <span><span>{{ t('idea.sceneN', { n: x.index + 1 }) }}</span><b>{{ x.sim === null ? t('board.cast.noFaceShort') : x.sim < fmin ? t('board.cast.other') : pct(x.sim) }}</b></span></button>
        </div>
      </section>

      <!-- the voice: a row of its own; the full form for it and the English -->
      <div class="cc-voice"><Icon name="music" /><b>{{ t('board.cast.voice') }}</b><span>{{ c.voice ? c.voice.name : t('board.cast.noVoice') }}</span><span class="grow" />
        <button type="button" class="btn" @click="emit('edit')">{{ t('board.cast.voiceSet') }}</button></div>
    </div>
  </div>
</template>
