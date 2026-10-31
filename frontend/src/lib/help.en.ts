// The help in English: help.en.a.ts and help.en.b.ts are the twins of help.ts's sections (same ids and order; a "?"
// finds its entry by the Russian term kept in <dt data-term="…">), tutorials/en the scenarios'.
import type { HelpSection } from './help'
import { HERO_EN, PART_A } from './help.en.a'
import { PART_B } from './help.en.b'
import { TUTORIALS_EN } from './tutorials/en'

const REFERENCE_EN = [...PART_A, ...PART_B]
const START = 'Getting started'
export const HELP_HERO_EN = HERO_EN
export const HELP_EN: HelpSection[] = [...REFERENCE_EN.filter((x) => x.group === START), ...TUTORIALS_EN,
  ...REFERENCE_EN.filter((x) => x.group !== START)]
