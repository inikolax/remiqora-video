// The long texts in the interface's language: the help (sections, the worked example, the scenarios), the screens'
// help windows and keys sheets, the lab's presets. Russian in help.ts, guides.ts, presets.ts, tutorials/*.ts; English
// in their .en twins, with the same ids and order. Read inside a computed or a template, they follow the switch.
import { currentLocale } from '../i18n'
import { HELP, HELP_HERO } from './help'
import { HELP_EN, HELP_HERO_EN } from './help.en'
import { EDIT_KEYS, GRAPH_KEYS, GUIDES } from './guides'
import { EDIT_KEYS_EN, GRAPH_KEYS_EN, GUIDES_EN } from './guides.en'
import { PRESETS } from './presets'
import { PRESETS_EN } from './presets.en'

const en = () => currentLocale() === 'en'
export const help = () => (en() ? HELP_EN : HELP)
export const helpHero = () => (en() ? HELP_HERO_EN : HELP_HERO)
export const guides = () => (en() ? GUIDES_EN : GUIDES)
export const editKeys = () => (en() ? EDIT_KEYS_EN : EDIT_KEYS)
export const graphKeys = () => (en() ? GRAPH_KEYS_EN : GRAPH_KEYS)
export const presets = () => (en() ? PRESETS_EN : PRESETS)
