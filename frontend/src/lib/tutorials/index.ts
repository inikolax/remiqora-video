// The scenarios of the help («Сценарии»): one file each, step by step from the first click to the result (kit.ts).
// The order here is the order in the contents.
import type { HelpSection } from '../help'
import firstRun from './firstRun'
import idea from './idea'
import fixScene from './fixScene'
import hero from './hero'
import photo from './photo'
import world from './world'
import clip from './clip'
import manual from './manual'
import lab from './lab'
import graph from './graph'
import edit from './edit'
import final from './final'
import remake from './remake'
import loras from './loras'
import disk from './disk'

export const TUTORIALS: HelpSection[] = [firstRun, idea, fixScene, hero, photo, world, clip, manual, lab, graph, edit, final, remake, loras, disk]
