// The studio's words for the writer's choices. The words come from locales/board.ts and follow the interface's
// language: each label is a getter, read again wherever it is shown (a template or a computed tracks the switch).
import { t } from '../i18n'

// [id, label] with the label read through t() each time
const pair = (id: string, key: string): [string, string] => {
  const a = [id, ''] as [string, string]
  Object.defineProperty(a, 1, { get: () => t(key), enumerable: true })
  return a
}
// { id: label } with each label read through t() each time
const table = (prefix: string, ids: string[]): Record<string, string> => {
  const o: Record<string, string> = {}
  for (const id of ids) Object.defineProperty(o, id, { get: () => t(`${prefix}.${id}`), enumerable: true })
  return o
}

export const MODES: [string, string][] = [pair('one', 'board.mode.one'), pair('several', 'board.mode.several'), pair('none', 'board.mode.none')]
export const LENGTHS = [15, 30, 45, 60, 300, 600]   // seconds; past 3 min the writer works from an outline
export const ASPECTS: [string, number, number][] = [['16:9', 18, 10], ['9:16', 10, 18], ['1:1', 14, 14]]
export const CAMERAS: Record<string, string> = table('board.cam',
  ['static', 'push_in', 'pull_back', 'track_side', 'track_front', 'follow', 'orbit', 'pan', 'rise', 'handheld'])
export const FRAMINGS: Record<string, string> = table('board.framing', ['wide', 'medium', 'close'])
export const GENDERS: [string, string][] = [pair('female', 'board.gender.female'), pair('male', 'board.gender.male'), pair('other', 'board.gender.other')]
export const QL: Record<string, string> = table('board.quality', ['draft', 'final'])
// how a line is said (the server's prompts.HOW turns it into English: «шёпотом» -> "whispers")
export const HOW_RU: [string, string][] = ['', 'calm', 'soft', 'whisper', 'loud', 'shout', 'laugh', 'smile', 'angry', 'sad', 'scared',
  'thoughtful', 'tender', 'sing'].map((id) => pair(id, `board.how.${id || 'plain'}`))
export const LINE_WORDS = 10   // about what a 5 s scene holds; past it the server marks the scene «проверь»
const CHAIN_COLORS = ['#a855f7', '#ec4899']   // Remiqora's accent1 / accent2
export const chainColor = (c: number) => CHAIN_COLORS[c % 2]
export const modeName = (m: string) => (MODES.find((x) => x[0] === m) || [])[1] || ''
