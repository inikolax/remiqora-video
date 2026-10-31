// «One scene in the Lab»: #/lab - the prompt, the shooting block, takes and seeds, the comparison on all models.
import { scenario, steps, step, go, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('lab', 'One scene in the Lab', `At the end you will have one scene in several takes — and a prompt tested on the model you need, ready to move into the storyboard.`,
  meta('5–15 minutes for a take or two; any model. You only need a prompt, and optionally a start frame and a LoRA.') +
  steps(
    step('Open the Lab', `<p>The «Lab» link in the header. On the left, the prompt, LoRA and «Shoot»; on the right, the frame of the scene to shoot with its settings above and the timeline below, the takes under it; while there are no takes, it shows presets.</p>${go('/lab', 'Open the Lab')}`),
    step('Write the prompt', `<p>The easiest way is «Preset ▾»: 16 complete prompts for common scenes; the scene length adjusts to their timeline. You can write your own text in your language on the «Russian» tab and click «Translate to English» — the translation opens on «English», check it. What gets shot is always the English.</p>`,
      'Translation takes 10–30 s; the video model is unloaded for that time.'),
    step('Check the prompt\'s parts', `<p>The «Fields» view: style, place, camera, «What happens» by line, sound; the timeline is computed automatically. The «Text» view: the whole prompt. Under the prompt are part labels: a dashed one with a plus means the part is missing, a click inserts it. Yellow lines under the field say what to fix, each with its own button.</p>`),
    step('Set up the shoot', `<p>Above the frame on the right: model, format, quality («Draft» while searching for the prompt), seed. Under the frame: the length (no longer than the model's limit: LTX 10 s, WAN 5 s). Want to start from a picture? Drag it right into the frame and make the first line of the prompt <code>Continue seamlessly from &lt;Picture 1&gt;.</code></p>`),
    step('Add a LoRA', `<p>In «LoRA», click «Add» — a list from the selected model's folder. The slider is the strength, usually 0.6–1. If the LoRA shows «trigger: …», put that word into the prompt.</p>`),
    step('Shoot takes', `<p>The number left of the button is how many takes in a row; each take's seed is 1 higher. Click «Shoot scene» (<kbd>Ctrl</kbd> <kbd>Enter</kbd>). An empty «Seed» means a new one every time.</p>`),
    step('Compare the models', `<p>«Shoot on all models — compare»: the same prompt and seed, one take on each model whose weights are present. The models load one after another; it takes a few minutes. The takes are labeled with the model.</p>`),
    step('Review the result', `<p>On the right, in «Takes», the takes are grouped by prompt; hover to play, click for a large view. Under a take: «Repeat with seed» — change the prompt and see only its difference; «Continue from the last frame» — the next scene from its frame; «Download», «Delete».</p>`),
  ) +
  tip(`Search for the prompt on one seed: «Repeat with seed», an edit, then «Shoot scene» again. If the seed changes, the scene is different and you can't tell what the edit did. The seed you found gives the same scene in the final, only sharper.`) +
  `<p class="note">Next: ${see('lab', 'The Lab: reference')}, ${see('prompt-parts', 'Prompt parts in order')}, ${see('tut-loras', 'Your own LoRA and another model')}</p>`, GROUP_EN)
