// «Фото проекта»: a picture of the project big, in a window over the page (ImageZoom.vue, mounted once in App.vue).
// v-zoom on an <img> opens it by a click; ← → go through all the project's pictures - the heroes' portraits and tries,
// the places, the scenes' first and last frames - so any of them can be looked at from any one.
import { reactive, type Directive } from 'vue'
import { P } from './project'
import { t } from '../i18n'

export type Pic = { src: string; label: string }
export const zoom = reactive<{ list: Pic[]; i: number }>({ list: [], i: -1 })

// every picture the project has, in the order of the screens: heroes, places, scenes
export function projectPics(): Pic[] {
  const proj = P.proj, plan = proj?.plan
  if (!proj || !plan) return []
  const f = (x: string) => `/api/projects/${proj.id}/files/${encodeURIComponent(x)}`
  const out: Pic[] = []
  const cast = plan.mode === 'none' ? [] : (plan.cast || [])
  cast.forEach((c: Record<string, any>, i: number) => {
    const who = c.name || (cast.length > 1 ? t('board.cast.heroN', { n: i + 1 }) : c.gender === 'female' ? t('board.look.heroine') : t('board.look.hero'))
    if (c.photo) out.push({ src: f(c.photo), label: who })
    else if (c.from_photo && proj.settings.photo) out.push({ src: `/api/projects/${proj.id}/photo`, label: who })
    for (const x of [...(c.tries || [])].reverse()) if (x.file && x.file !== c.photo) out.push({ src: f(x.file), label: t('zoom.try', { who }) })
  })
  for (const x of plan.places || []) if (x.photo) out.push({ src: f(x.photo), label: x.name_ru || x.name || t('zoom.place') })
  for (const s of plan.scenes || []) {
    if (s.start_photo) out.push({ src: f(s.start_photo), label: t('zoom.first', { n: s.index + 1 }) })
    if (s.end_photo) out.push({ src: f(s.end_photo), label: t('zoom.last', { n: s.index + 1 }) })
  }
  return out.filter((x, k) => out.findIndex((y) => y.src === x.src) === k)
}

// a picture big: among the project's pictures when it is one of them, else alone
export function openZoom(src: string, label = '') {
  const path = (u: string) => { try { return new URL(u, location.href).pathname } catch { return u } }
  const list = projectPics()
  const k = list.findIndex((x) => path(x.src) === path(src))
  zoom.list = k >= 0 ? list : [{ src, label }, ...list]
  zoom.i = k >= 0 ? k : 0
}

// <img v-zoom>: a click opens it big (and does nothing else); the cursor says so
export const vZoom: Directive<HTMLImageElement, string | undefined> = {
  mounted(el, b) {
    el.classList.add('zoomable')
    el.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      openZoom(el.getAttribute('src') || el.currentSrc, b.value || el.alt || '')
    })
  },
}
