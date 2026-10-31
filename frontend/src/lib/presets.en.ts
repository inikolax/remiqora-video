// The lab's presets for the English interface: the same ids, order, seconds and prompts as presets.ts, with groups,
// names and hints in English. The English UI has no translation step, so `ru` (the prompt of the user's own language)
// is the English prompt too.
import { PRESETS, type Preset } from './presets'

const TEXT: Record<string, { group: string; name: string; hint: string }> = {
  parts: { group: 'Basics', name: 'All parts, empty', hint: 'a prompt skeleton: fill in the «...»' },
  hero: { group: 'Basics', name: 'Hero in the shot', hint: 'a new scene from text: a person, a place, three actions' },
  continue: { group: 'Basics', name: 'Continuation from a frame', hint: 'needs a start frame: the scene continues the picture' },
  animate: { group: 'Basics', name: 'Bring a photo to life', hint: 'needs a start frame: the same person and place, only living motion' },
  line: { group: 'Speech', name: 'A line to the camera', hint: "the hero speaks the video's language; tested in Remiqora Video" },
  dialog: { group: 'Speech', name: 'Dialogue of two', hint: 'two people take turns; each is named by a feature' },
  voiceover: { group: 'Speech', name: 'Voiceover', hint: 'a narrator speaks, the heroine\'s lips stay closed' },
  walk: { group: 'People and motion', name: 'Walking toward the camera', hint: 'the camera backs away in front of the hero; night, rain, neon' },
  three: { group: 'People and motion', name: 'Three in the shot', hint: 'each with their own features, place and action' },
  dance: { group: 'People and motion', name: 'Dance for a clip', hint: 'a stage, lights, haze, the camera circling, a beat' },
  boom: { group: 'Sounds and music', name: 'Explosion and effects', hint: 'each event\'s sound on its own row, no music' },
  musician: { group: 'Sounds and music', name: 'Musician in the shot', hint: 'the hero plays the music, everyone hears it' },
  score: { group: 'Sounds and music', name: 'Background music', hint: 'music by instruments and tempo, then the sounds of the place' },
  nature: { group: 'No people', name: 'Nature', hint: 'a landscape: fog, sunbeams, an animal in the distance' },
  product: { group: 'No people', name: 'Object in close-up', hint: 'an ad: studio light, an orbit, a drop' },
  cartoon: { group: 'Style', name: '3D cartoon', hint: 'animation instead of live action' },
  vintage: { group: 'Style', name: 'Old film', hint: 'the 1970s: faded colors, grain, flicker' },
}

export const PRESETS_EN: Preset[] = PRESETS.map(p => ({ ...p, ...(TEXT[p.id] ?? {}), ru: p.en }))
