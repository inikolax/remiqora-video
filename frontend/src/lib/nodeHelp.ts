// What each node of a graph project is for, in a line, and what to do with it next: «Дальше» is worked out from the
// node itself, its links and the server's state - a node just added says what it needs («Соедините Идею: …»),
// one that is ready says where it goes. The add menu, the node's card and its panel show them.
import { GE, WHO_NAME, inputsOf, nodeOf, refLoraOf, tOf } from './graphDoc'
import { videoModel } from './store'
import { t as tx } from '../i18n'

export interface NodeHelp { what: string; ports: string }   // the icon: graphDoc.ICON; {m} - the graph's model
const HELP_TYPES = ['idea', 'hero', 'writer', 'prompt', 'photo', 'picture', 'scene', 'v2v', 'facefix', 'frame', 'sound', 'lora', 'join', 'montage', 'track',
  'music', 'output', 'note', 'group']
const NO_PORTS = ['note', 'group']
// read through t() when read: the texts follow the interface's language (locales/nodes.ts what / ports)
export const NODE_HELP: Record<string, NodeHelp> = Object.fromEntries(HELP_TYPES.map((k) => [k, {
  get what() { return k === 'scene' ? '' : tx(`nodes.what.${k}`, { m: modelShort() }) },
  get ports() { return NO_PORTS.includes(k) ? '' : tx(`nodes.ports.${k}`) },
}]))

// the graph's model shoots every scene (H3, LTX, WAN): the lines about scenes name it
export const graphModel = () => videoModel(GE.proj?.settings.video_model || 'h3')
const modelShort = () => graphModel()?.short || 'H3'
const LORA_MODELS = ['h3', 'ltx23', 'ltx25', 'wan5b']   // the models with LoRA folders of their own (app/loras.py LIBRARIES)
export function nodeWhat(t: string): string {
  const m = graphModel()
  if (t === 'scene') {
    if (!m || m.id === 'h3') return tx('nodes.what.sceneH3')
    return tx(m.sound ? 'nodes.what.sceneSound' : 'nodes.what.sceneSilent', { m: m.short, s: m.max_seconds })
  }
  if (t === 'lora' && m && !LORA_MODELS.includes(m.id.replace(/^rq_/, '').replace(/^wan5b_fast$/, 'wan5b'))) return tx('nodes.what.loraNone', { m: m.short })
  return NODE_HELP[t]?.what || ''
}
// who does a node's work, in the panel's header: a scene - the graph's model
export const whoName = (who: string) => (who === 'h3' ? tx('nodes.shoots', { m: graphModel()?.name || 'H3' }) : WHO_NAME[who] || '')

// «Дальше»: the next thing to do with this node. setup - something is missing (shown on the card too); otherwise a
// hint where it goes / what makes it (only in the panel)
export interface Next { text: string; setup: boolean }
const outs = (id: string) => GE.edges.filter((e) => e.source === id)
const has = (id: string, port: string) => inputsOf(id, port).length > 0
const src = (id: string, port: string) => { const e = inputsOf(id, port)[0]; return e ? nodeOf(e.source) : null }

export function nextStep(id: string): Next | null {
  const n = nodeOf(id)
  if (!n) return null
  const t = tOf(n), d = n.data as Record<string, any>, st = GE.state?.nodes[id]
  const need = (text: string): Next => ({ text, setup: true })
  const tip = (text: string): Next => ({ text, setup: false })
  switch (t) {
    case 'idea':
      if (!(d.text || '').trim()) return need(tx('nodes.next.ideaText'))
      if (!outs(id).length) return need(tx('nodes.next.ideaLink'))
      if (outs(id).some((e) => ['scene', 'picture'].includes(tOf(nodeOf(e.target)!))))
        return need(tx('nodes.next.ideaScene'))
      return tip(tx('nodes.next.ideaOk'))
    case 'hero':
      if (!d.photo && !(d.en || '').trim()) return need(tx('nodes.next.heroNone'))
      if (!(d.en || '').trim()) return need(tx('nodes.next.heroDescribe'))
      if (!outs(id).length) return need(tx('nodes.next.heroLink'))
      return tip(tx('nodes.next.heroOk'))
    case 'writer': {
      const idea = src(id, 'idea')
      if (!idea && !(d.idea || '').trim()) return need(tx('nodes.next.writerIdea'))
      if (idea && !((idea.data as any).text || '').trim()) return need(tx('nodes.next.writerIdeaEmpty'))
      if (!d.plan) return need(tx('nodes.next.writerWrite'))
      if (st?.state === 'stale') return need(tx('nodes.next.writerStale'))
      if (!GE.nodes.some((x) => (x.data as any).from === id)) return need(tx('nodes.next.writerExpand'))
      return tip(tx('nodes.next.writerOk'))
    }
    case 'prompt':
      if (!(d.text || '').trim()) return need(tx('nodes.next.promptText'))
      if (!outs(id).length) return need(tx('nodes.next.promptLink'))
      return tip(tx('nodes.next.promptOk'))
    case 'photo':
      if (!d.file) return need(tx('nodes.next.photoFile'))
      if (!outs(id).length) return need(tx('nodes.next.photoLink'))
      return null
    case 'picture':
      if (!has(id, 'text') && !(d.prompt || '').trim()) return need(tx('nodes.next.pictureText'))
      if (d.model === 'flux2' && !has(id, 'ref')) return need(tx('nodes.next.pictureRef'))
      if (!outs(id).length) return need(tx('nodes.next.pictureLink', { m: modelShort() }))
      return st?.state === 'todo' ? tip(tx('nodes.next.pictureTodo')) : null
    case 'scene': {
      const ref = refLoraOf(id)?.v2v
      if (ref?.reads === 'clip' && !has(id, 'clip')) return need(tx('nodes.next.sceneClip'))
      if (ref?.reads === 'voice' && !has(id, 'start')) return need(tx('nodes.next.sceneStart'))
      if (ref?.reads === 'voice' && !has(id, 'voice')) return need(tx('nodes.next.sceneVoice'))
      if (!has(id, 'prompt') && !(ref?.reads === 'clip' && (ref.prompt !== 'required' || ref.template)))
        return need(tx('nodes.next.scenePrompt'))
      if (st?.state === 'error') return need(st.error || tx('nodes.next.error'))
      if (!outs(id).some((e) => e.sourceHandle === 'clip')) return need(tx('nodes.next.sceneLink'))
      if (st?.state === 'todo') return tip(tx('nodes.next.sceneTodo'))
      if (st?.state === 'wait') return tip(ref?.reads === 'clip' ? tx('nodes.next.sceneWaitClip') : tx('nodes.next.sceneWaitStart'))
      return null
    }
    case 'v2v':
      if (!has(id, 'clip')) return need(tx('nodes.next.v2vClip'))
      if (!d.lora) return need(tx('nodes.next.v2vLora'))
      if (st?.state === 'error') return need(st.error || tx('nodes.next.error'))
      if (st?.state === 'todo') return tip(tx('nodes.next.v2vTodo'))
      return st?.state === 'ready' && st.alpha ? tip(tx('nodes.next.v2vAlpha')) : null
    case 'facefix':
      if (!has(id, 'clip')) return need(tx('nodes.next.facefixClip'))
      if (st?.state === 'error') return need(st.error || tx('nodes.next.error'))
      if (!outs(id).length) return need(tx('nodes.next.facefixLink'))
      if (st?.state === 'todo') return tip(tx('nodes.next.facefixTodo'))
      if (st?.state === 'ready' && st.note && !st.note.faces) return tip(tx('nodes.next.facefixNone'))
      return null
    case 'sound':
      if (!has(id, 'clip')) return need(tx('nodes.next.soundClip'))
      if (!outs(id).length) return need(tx('nodes.next.soundLink'))
      return d.voice === false ? null : tip(tx('nodes.next.soundVoice'))
    case 'frame':
      if (!has(id, 'clip')) return need(tx('nodes.next.frameClip'))
      if (!outs(id).length) return need(tx('nodes.next.frameLink'))
      return null
    case 'lora':
      if (!(d.items || []).length) return need(tx('nodes.next.loraAdd'))
      if (!outs(id).length) return need(tx('nodes.next.loraLink'))
      return null
    case 'join': case 'montage':
      if (!has(id, 'clips')) return need(tx('nodes.next.joinClips'))
      if (!outs(id).length) return need(tx('nodes.next.joinLink'))
      return t === 'montage' ? tip(tx('nodes.next.montageOpen')) : tip(tx('nodes.next.joinMontage'))
    case 'track':
      if (!d.file) return need(tx('nodes.next.trackFile'))
      if (!outs(id).length) return need(tx('nodes.next.trackLink'))
      return null
    case 'music':
      if (!has(id, 'video') || !has(id, 'audio')) return need(tx('nodes.next.musicIn'))
      if (!outs(id).length) return need(tx('nodes.next.musicLink'))
      return null
    case 'output':
      if (!has(id, 'video')) return need(tx('nodes.next.outputIn'))
      return st?.state === 'ready' ? tip(tx('nodes.next.outputReady')) : tip(tx('nodes.next.outputTodo'))
  }
  return null
}

// a new node next to the selected one: the first ports that fit, either way (the selected one's output into the new
// one's input, or back) - so «Идея» then «Сценарист» comes linked
export function fitLink(selId: string, t: string): { source: string; sourceHandle: string; target: string; targetHandle: string; after: boolean } | null {
  const a = nodeOf(selId), spec = GE.types[t]
  if (!a || !spec) return null
  const as = GE.types[tOf(a)]
  // the new node's first input that takes one of the outputs (a Scene then «Видео → видео»: its clip, not its frame)
  for (const [ip, s] of Object.entries(spec.in)) {
    const op = Object.entries(as?.out || {}).find(([, ty]) => ty === s.type)
    if (op) return { source: selId, sourceHandle: op[0], target: '', targetHandle: ip, after: true }
  }
  for (const [op, ty] of Object.entries(spec.out)) {
    const ip = Object.entries(as?.in || {}).find(([p, s]) => s.type === ty && (s.multi || !inputsOf(selId, p).length))
    if (ip) return { source: '', sourceHandle: op, target: selId, targetHandle: ip[0], after: false }
  }
  return null
}
