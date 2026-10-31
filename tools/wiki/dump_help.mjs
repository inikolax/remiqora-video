// node tools/wiki/dump_help.mjs <out.json>: bundles help_entry.ts with the frontend's own rolldown and writes the help
// of both languages as JSON: { ru: { hero, sections: [{id, group, title, html}] }, en: {...} }
import { createRequire } from 'node:module'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontend = path.resolve(here, '..', '..', 'frontend')
const require = createRequire(path.join(frontend, 'package.json'))
const { build } = await import(pathToFileURL(require.resolve('rolldown')).href)

const tmp = mkdtempSync(path.join(tmpdir(), 'rv-wiki-'))
try {
  await build({ input: path.join(here, 'help_entry.ts'), platform: 'node', output: { dir: tmp, format: 'esm', entryFileNames: 'help.mjs' }, logLevel: 'warn' })
  const m = await import(pathToFileURL(path.join(tmp, 'help.mjs')).href)
  const out = { ru: { hero: m.HELP_HERO, sections: m.HELP }, en: { hero: m.HELP_HERO_EN, sections: m.HELP_EN } }
  writeFileSync(process.argv[2], JSON.stringify(out), 'utf8')
  console.log(`help: ${out.ru.sections.length} sections (ru), ${out.en.sections.length} (en)`)
} finally {
  rmSync(tmp, { recursive: true, force: true })
}
