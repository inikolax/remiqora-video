import { createRouter, createWebHashHistory } from 'vue-router'
import IdeaView from './views/IdeaView.vue'
import BoardView from './views/BoardView.vue'
import VideoView from './views/VideoView.vue'
import ModelsView from './views/ModelsView.vue'
import HelpView from './views/HelpView.vue'
import LabView from './views/LabView.vue'

// The hash URLs of the page before Vue, kept: #/ the idea and your videos, #/p/<id> the storyboard, #/p/<id>/video
// the shooting, #/p/<id>/graph the storyboard as a graph (phase 9), #/models, #/help/<section>; the lab moved from /lab to #/lab (the server redirects the old address).
const router = createRouter({
  history: createWebHashHistory(),
  // a new screen opens at its top; the help scrolls to its section itself
  // the help scrolls to its section itself (HelpView): going there from another screen, the top would undo it
  scrollBehavior: (to, from) => (to.name === 'help' && (from.name === 'help' || to.params.section) ? false : { top: 0 }),
  routes: [
    { path: '/', name: 'idea', component: IdeaView },
    { path: '/p/:id', name: 'board', component: BoardView, props: true },
    { path: '/p/:id/video', name: 'video', component: VideoView, props: true },
    { path: '/p/:id/edit', name: 'edit', component: () => import('./views/EditView.vue'), props: true },
    { path: '/g/:id/edit/:node', name: 'gmontage', component: () => import('./views/EditView.vue'), props: true },
    // the graph carries Vue Flow (~170 KB): loaded when it is opened
    { path: '/p/:id/graph', name: 'graph', component: () => import('./views/GraphView.vue'), props: true },
    // a graph project (phase 9): its own canvas, editable
    { path: '/g/:id', name: 'gedit', component: () => import('./views/GraphEditView.vue'), props: true },
    { path: '/models/:section?', name: 'models', component: ModelsView, props: true },
    { path: '/help/:section?', name: 'help', component: HelpView, props: true },
    { path: '/lab', name: 'lab', component: LabView },
    { path: '/:rest(.*)*', redirect: '/' },
  ],
})

// A screen loaded on demand (the montage, the graph) from a build that is gone: the page was open while the app was
// rebuilt and asks for chunks under their old names (the user: «Монтаж сломался»). Load that screen anew from the
// new build, once a minute at most - a chunk that is really missing must not reload the page forever.
function reloadInto(to: string) {
  let last = 0
  try { last = +(sessionStorage.getItem('chunk-reload') || 0) } catch { /* no storage: reload anyway */ }
  if (Date.now() - last < 60_000) return false
  try { sessionStorage.setItem('chunk-reload', String(Date.now())) } catch { /* ignore */ }
  location.assign(to)
  location.reload()
  return true
}
const STALE = /dynamically imported module|Importing a module script failed|error loading dynamically|Unable to preload CSS/i
router.onError((err, to) => {
  if (STALE.test(String(err?.message || err))) reloadInto(router.resolve(to).href)
})
window.addEventListener('vite:preloadError', (e) => {
  if (reloadInto(location.href)) e.preventDefault()
})

export default router
