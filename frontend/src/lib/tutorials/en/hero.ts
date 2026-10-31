// «Your own hero»: the hero card of the storyboard (components/board/LookCard.vue) - photo, look, Ref2VA, voice, several heroes
import { scenario, steps, step, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('hero', 'Your own hero: photo, look, voice',
  'A hero with the same face, outfit and voice in every scene. Everything is set in the hero card above the storyboard timeline.',
  meta('5–10 minutes. The face from a photo (Ref2VA) works only for H3 scenes, the voice from a sample for LTX 2.3 scenes. You need a ready storyboard and a writer that «sees photos».')
  + steps(
    step('Open the hero card',
      'Open the video from the list on the home screen. The hero card is above the timeline: the look and outfit that go into every scene word for word. «EN» shows what goes to the model; «Edit» opens the fields.'),
    step('Add a photo',
      'In «Edit», in the hero\'s field, click «Photo» («Another photo» if there already is one) and choose a png, jpg or webp. Then «Describe from photo»: the writer describes the face, hair, gender and age; the outfit stays yours. The photo itself doesn\'t change the description until you click the button.',
      'Describing takes about 10 s on the graphics card.'),
    step('No photo? Draw the hero',
      'A hero without a photo has «Draw from description»: Krea 2 draws them from the look, outfit, the video\'s style and the place of the first scene, and the drawing becomes the hero\'s photo. Don\'t like it? «Draw again».',
      'About 10 s; you need the Krea 2 weights and an English description of the hero.'),
    step('Refine the look and outfit',
      'The fields «Look: face, hair, build, distinctive features» and «Outfit and accessories», «Gender», «Age» — in your language. Then «Update prompt from text»: the writer translates them into English. «Done» closes the fields.',
      'The look goes into every scene: after an edit, all scenes are reshot.'),
    step('Keep the face from the photo',
      'Under the card, check «Keep the face from the photo (Ref2VA)»: new H3 scenes are shot by the Ref2VA model with the hero\'s photo as the face sample. Continuations are shot as before, from the last frame; «on all scenes (experimental)» hands them to Ref2VA too.',
      'The checkbox shows when the video has a photo; the weights are in the «Ref2VA» section of the models page. LTX and WAN scenes don\'t keep the face from a photo.'),
    step('Give the hero a voice',
      '<p>In the «Voice» block: a sample of 5–10 s of clean speech — «File», «Record voice» from the microphone, or «From a scene…», the voice of a shot scene without music and noise. «Sample from, s» and «Length, s» set which piece to take.</p>'
      + '<p>LTX 2.3 scenes (not on a track) where only this hero speaks are shot with ID-LoRA in this voice; under the sample: «Scenes with this voice: N».</p>',
      '«From a scene…» separates the voice with Demucs — about a minute on the graphics card. Changing the sample reshoots these scenes.'),
    step('Several heroes',
      'A video in «Several» mode on the home screen: in «Edit», «Add hero» (up to three) and «Remove», each with their own photo and voice. In the scene inspector, the «Who\'s in the scene» checkboxes choose whose looks go into the prompt, and under each are their «Lines».'),
  )
  + tip('For Ref2VA take a frontal portrait, the face large, even light, a neutral background: the model pulls the surroundings from the picture too — a lavender field from the photo will end up in every scene.')
  + tip('The more distinctive features in the look, the less the face changes between scenes: «27 years old, dark chin-length bob, olive skin, a mole on the left cheek», not «a woman with brown hair».')
  + `<p class="note">Next: ${see('look', 'Hero, style and Ref2VA')} · ${see('inspector', 'Scene inspector')} · ${see('video-models', 'Video models')}</p>`, GROUP_EN)
