// A screenplay's size as the card and the panel show it (the server's app/screenplay.py parses it for real, with the
// heroes' names; here a line is «ИМЯ (как): слова» with the name in capitals - close enough to count).
// \b and \W are ASCII-only in JS even with /u: Cyrillic needs the Unicode letter class
const SCENE = /^\s*(?:СЦЕНА|SCENE)(?!\p{L})/iu
const LINE = /^\s*(\p{L}[^:()—–]{0,38}?)\s*(?:\([^)]*\))?\s*:\s*\S/u

export function screenplayStats(text: string) {
  let scenes = 0, lines = 0, actions = 0
  for (const raw of (text || '').split('\n')) {
    const row = raw.trim()
    if (!row) continue
    if (SCENE.test(row)) { scenes++; continue }
    const m = !/^[—–-]/.test(row) && LINE.exec(row)
    if (m && m[1].trim() === m[1].trim().toUpperCase()) lines++
    else actions++
  }
  return { scenes: Math.max(scenes, lines + actions ? 1 : 0), lines, actions, shots: lines + actions }
}
