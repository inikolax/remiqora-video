// «Own prompts»: the main screen's empty storyboard -> each scene's prompt by hand in the inspector -> shooting.
import { scenario, steps, step, go, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('manual', 'Own prompts: a storyboard by hand', `At the end you will have a video where every scene was shot from your own English prompt — without the writer or a language model.`,
  meta('15–30 minutes for the prompts plus shooting; any model. You need to be able to write a prompt in English — or take a preset.') +
  steps(
    step('Open an empty storyboard', `<p>On the home screen, in the switch above the form, choose «Own prompts». «Title» is optional. Choose «Length» (next to it you see how many scenes it makes: 5 s each on H3 and WAN, 10 s each on LTX), «Frame» and «Model». Click «Open storyboard» — it opens right away.</p>${go('/', 'Open the home screen')}`),
    step('Start the first scene', `<p>On the empty scene's card, click «Write prompt»: the scene is selected and the cursor goes to the «Prompt for the model, as is» field in the inspector. While the field is empty, there is a «Preset» above it — it inserts a sample prompt following the H3 formula, with «...» in place of the place, actions and sound.</p>`),
    step('Write the prompt', `<p>Rewrite the preset for your scene: the style, <code>Scene:</code> — the place, <code>Camera:</code>, <code>Timeline:</code> with actions by seconds (<code>[0s-2s]</code>), <code>Audio:</code>. The «What happens» field is a note for you; it doesn't go to the model.</p>`,
      'The preset\'s timeline is for 5 s: in a 10 s scene (LTX), stretch it to <code>[…-10s]</code>.'),
    step('Link the scenes', `<p>In the inspector, «Start»: «New scene — from the prompt only», or a continuation — «from the last frame of the previous one» or «from the last frame of scene N» (a cutaway: go back to the moment where scene N ended). Start a continuation's prompt with the line <code>Continue seamlessly from &lt;Picture 1&gt;.</code> — the continuation preset already has it. On the card such a scene is marked «from frame N».</p>`),
    step('Add scenes', `<p>«Add scene» above the cards inserts an empty continuation after the selected one; the writer doesn't fill it in. Cards are reordered by the dots on the left; the first scene is always new.</p>`),
    step('Shoot the video', `<p>In the shooting panel choose «Quality» («Draft» first) and click «Shoot video». H3 gets your prompt word for word. LTX and WAN get it reworked: without the <code>&lt;Picture 1&gt;</code> line, the timeline as one paragraph of sentences, without the tail about on-screen text; WAN also without lines and the <code>Audio:</code> line.</p>`),
  ) +
  tip(`One scene, one place. If a continuation says «she walks into a different room», the model makes a jump mid-scene: a new place is a new scene.`) +
  tip(`A prompt is hard to get right the first time: debug it in the Lab on a single scene, with the same seed, and only then paste it into the storyboard.`) +
  `<p class="note">Next: ${see('prompt', 'How to write a prompt')}, ${see('prompt-recipes', 'Presets')}, ${see('tut-lab', 'One scene in the Lab')}</p>`, GROUP_EN)
