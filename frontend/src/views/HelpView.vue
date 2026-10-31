<script setup lang="ts">
// The help page: contents as a tree (groups that fold, the section you are reading open down to its entries), a
// search over every entry, the worked example on top.
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { help, helpHero } from '../lib/content'

const { t } = useI18n()
const props = defineProps<{ section?: string }>()
const HELP = computed(() => help())   // the interface's language (lib/content)
const groups = computed(() => [...new Set(HELP.value.map((x) => x.group))])
const body = ref<HTMLElement | null>(null)
const q = ref('')
const none = ref('')

// the tree's third level: a section's entries (its terms) or a scenario's steps, as the page shows them
const plain = (h: string) => h.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim()
const ENTRIES = computed<Record<string, string[]>>(() => Object.fromEntries(HELP.value.map((x) => [x.id, x.id.startsWith('tut-')
  ? [...x.html.matchAll(/<li><b>(.*?)<\/b>/g)].map((m) => plain(m[1]))
  : [...x.html.matchAll(/<dt[^>]*>(.*?)<\/dt>/gs)].map((m) => plain(m[1]))])))
const groupOf = (id: string) => HELP.value.find((x) => x.id === id)?.group || ''

// the section being read: the route's, then whichever is under the header while scrolling
const cur = ref(props.section || 'start')
const fold = reactive<Record<string, boolean>>({})   // a group folded or unfolded by hand
const curGroup = computed(() => groupOf(cur.value))
watch(curGroup, (g) => { delete fold[g] })   // reading on into another group opens it
const isOpen = (g: string) => !!q.value.trim() || (fold[g] ?? g === curGroup.value)
const hits = ref<Set<string> | null>(null)   // while searching: the sections with something found
const shownIn = (g: string) => HELP.value.filter((h) => h.group === g && (!hits.value || hits.value.has(h.id)))
const shownGroups = computed(() => groups.value.filter((g) => shownIn(g).length))

// the sticky header's bottom; on a narrow window it is not sticky and scrolls away (0 then)
const headBottom = () => Math.max(0, document.querySelector('.head')?.getBoundingClientRect().bottom ?? 0)
async function go() {
  await nextTick()
  const target = props.section && document.getElementById('help-' + props.section)
  // the section's title just under the sticky header, whose height changes when it wraps on a narrow window
  window.scrollTo(0, target ? target.getBoundingClientRect().top + window.scrollY - headBottom() - 16 : 0)
  cur.value = props.section || 'start'
}
watch(() => props.section, go)
// an entry of the section: its n-th term (or a scenario's n-th step) just under the header
function goEntry(id: string, n: number) {
  const sec = document.getElementById('help-' + id)
  const el = sec?.querySelectorAll<HTMLElement>(id.startsWith('tut-') ? '.flow > li' : 'dt')[n]
  if (el) window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - headBottom() - 16)
}
// the last section whose title has passed under the header (40 sections - cheap enough on every scroll event)
function spy() {
  if (q.value.trim()) return
  const line = headBottom() + 40
  let at = 'start'
  for (const s of body.value?.querySelectorAll<HTMLElement>('section[data-help-sec]') || []) {
    if (s.getBoundingClientRect().top > line) break
    at = s.id.slice(5)
  }
  cur.value = at
}
onMounted(() => { go(); window.addEventListener('scroll', spy, { passive: true }) })
onUnmounted(() => window.removeEventListener('scroll', spy))

// the search: entries (a term with its text), paragraphs and list items that mention the words stay, with the words marked
watch(q, (v) => {
  // the stem of a Russian word: «лицо» finds «лица» and «лицом» too
  const words = v.toLowerCase().split(/\s+/).filter((w) => w.length > 1).map((w) => (w.length > 3 ? w.slice(0, -1) : w))
  const box = body.value!
  box.querySelectorAll('mark').forEach((m) => m.replaceWith(document.createTextNode(m.textContent || '')))
  box.normalize()
  ;(document.getElementById('help-start') as HTMLElement).hidden = words.length > 0
  let found = 0
  box.querySelectorAll<HTMLElement>('[data-help-sec]').forEach((sec) => {
    // a term goes with its text: <dt> with its <dd> (in a plain list or a node card), a key with what it does
    const parts = [...sec.querySelectorAll<HTMLElement>(':scope > p, :scope > ul > li, :scope > ol > li, :scope > .tip, :scope dl dt, :scope .keys-grid > span:nth-child(odd)')]
    let any = false
    for (const el of parts) {
      const paired = el.tagName === 'DT' || el.parentElement?.classList.contains('keys-grid')
      const pair = (paired ? [el, el.nextElementSibling] : [el]).filter(Boolean) as HTMLElement[]
      const hit = !words.length || words.every((w) => pair.map((x) => (x.textContent || '').toLowerCase()).join(' ').includes(w))
      pair.forEach((x) => { x.hidden = !hit })
      if (hit && words.length) { any = true; found++; pair.forEach((x) => mark(x, words)) }
      const card = el.parentElement?.classList.contains('node-card') ? el.parentElement : null
      if (card) card.hidden = !hit
    }
    // the pictures and headings of a section stay only while nothing is searched
    sec.querySelectorAll<HTMLElement>(':scope > figure, :scope > h3, :scope > .legend-row, :scope > .note').forEach((x) => { x.hidden = words.length > 0 })
    sec.hidden = words.length > 0 && !any
  })
  hits.value = words.length ? new Set([...box.querySelectorAll<HTMLElement>('[data-help-sec]')].filter((s) => !s.hidden).map((s) => s.id.slice(5))) : null
  none.value = words.length && !found ? t('helpui.none', { q: v.trim() }) : ''
})
function mark(el: HTMLElement, words: string[]) {
  const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), nodes: Node[] = []
  while (walk.nextNode()) nodes.push(walk.currentNode)
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi')
  const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!))
  for (const n of nodes) {
    if (!re.test(n.textContent || '')) continue
    const span = document.createElement('span')
    span.innerHTML = esc(n.textContent || '').replace(re, '<mark>$1</mark>')
    ;(n as ChildNode).replaceWith(...span.childNodes)
  }
}
</script>

<template>
  <div class="screen help">
    <nav class="side help-toc" :aria-label="t('helpui.toc')"><span class="help-name">{{ t('helpui.name') }}</span>
      <input v-model="q" type="search" class="field-in" :placeholder="t('helpui.searchPh')" :aria-label="t('helpui.searchAria')">
      <router-link v-if="!hits" to="/help/start" :class="{ on: cur === 'start' }">{{ t('helpui.start') }}</router-link>
      <div v-for="g in shownGroups" :key="g" class="toc-group" :class="{ open: isOpen(g) }">
        <button type="button" class="toc-head" :aria-expanded="isOpen(g)" @click="fold[g] = !isOpen(g)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
          {{ g }}<small>{{ HELP.filter((h) => h.group === g).length }}</small></button>
        <template v-if="isOpen(g)">
          <template v-for="x in shownIn(g)" :key="x.id">
            <!-- a section with entries of its own shows it like a group does: a chevron, turned down while it is open -->
            <router-link :to="`/help/${x.id}`" :class="{ on: x.id === cur, branch: !hits && ENTRIES[x.id].length, open: x.id === cur && !hits }"
              :aria-expanded="!hits && ENTRIES[x.id].length ? x.id === cur : undefined">{{ x.title }}<svg v-if="!hits && ENTRIES[x.id].length" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg></router-link>
            <div v-if="x.id === cur && !hits && ENTRIES[x.id].length" class="toc-entries">
              <button v-for="(e, n) in ENTRIES[x.id]" :key="n" type="button" @click="goEntry(x.id, n)">{{ e }}</button></div>
          </template>
        </template></div>
    </nav>
    <main ref="body" class="main help-body">
      <section id="help-start" class="help-hero" v-html="helpHero()" />
      <p v-if="none" class="help-none">{{ none }}</p>
      <!-- the entries straight in the section: the search walks its own <p>, <li> and <dt> -->
      <section v-for="x in HELP" :id="`help-${x.id}`" :key="x.id" data-help-sec v-html="`<span class='help-eyebrow'>${x.group}</span><h2>${x.title}</h2>${x.html}`" />
    </main>
  </div>
</template>
