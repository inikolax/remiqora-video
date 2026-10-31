// «A video from an idea»: the main path by clicks - the idea, the storyboard, the draft, the final
import { scenario, steps, step, go, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('idea', 'A video from an idea',
  'A couple of sentences in your language turn into a storyboard, a draft video and a final. This is the studio\'s main path, step by step and button by button.',
  meta('For a 30 s video: the writer takes 20–30 s, a draft on H3 about 10 min, on LTX 3.5–4. You need the chosen model\'s weights and the writer.')
  + steps(
    step('Open the home screen',
      '<p>Click the logo in the header. Above the form on the left are four ways to start; choose «Writer» («from an idea»). On the right are your videos.</p>'
      + go('/', 'Open the home screen')),
    step('Write the idea',
      'The «Idea» field: who, where, what happens and how it ends. «A girl in a red coat walks along a night embankment in the rain, stops by a street lamp and smiles» is better than «a girl takes an evening walk»: place, light, weather, clothes and an ending give coherent scenes.'),
    step('Set the length, frame and model',
      '«Length» goes from 15 s to 10 min, and next to it you see right away how many scenes it makes: 5 s each on H3 and WAN, 10 s each on LTX. «Frame» is 16:9, 9:16 or 1:1. «Model» is who shoots: H3 and LTX with sound and lines, WAN without sound. You can change the model later.'),
    step('Choose the mood and the hero',
      '<p>«Mood»: Cinema, Clip, Commercial, Fantasy and effects, Documentary — the light, color, pace and camera of the whole video. «Who\'s in frame»: «One hero», «Several» or «No people». «Music and sound» is what the model composes by itself; empty means only the scene sounds.</p>'
      + '<p>«Photo» is optional: «First frame» makes the video start from this picture, «Look only» has the writer describe the hero from it.</p>'),
    step('Click «Write the scenes»',
      'The writer writes the storyboard; it opens right away and fills in when the writer is done. While it writes, the status bar shows a green dot.',
      'The estimate under the button: about 10 s plus 3 s per scene. A bit longer with a photo.'),
    step('Go through the storyboard',
      '<p>Clicking a card opens the inspector on the right. Edited «What happens»? Click «Update prompt from text». On the card, «Improve» and «Another version» have the writer rewrite the scene. Pin a good one with «Pin» in the inspector; the rest can be rewritten at once with «Rewrite unpinned» above the cards.</p>'
      + '<p>A yellow line on a card is a «check» mark: what the code considers a mistake. It is advice, not a ban.</p>'),
    step('Shoot a draft',
      'On the right, in the shooting panel: «Quality» → «Draft», then «Shoot video». The «Video» screen opens: at the bottom, a strip of scenes with «step 5/8», «from cache», «waiting for frame»; on the right, the stages and how much is left.',
      'You can close the page: shooting runs in the queue, and the video is saved into the project.'),
    step('Take the video or shoot the final',
      '«Download MP4» and «Open folder» give you the finished video. «Shoot final» shoots the same scenes with the same seeds, larger and sharper; «Back to storyboard» lets you keep editing.'),
  )
  + tip('Draft first, then edits, then «Shoot final»: an edited scene is reshot together with the continuations after it, the rest come from the cache.')
  + `<p class="note">Next: ${see('start', 'From idea to video')} — the same path on one example, with the prompt explained · ${see('tut-hero', 'Your own hero')} · ${see('tut-final', 'Final: 1080p, 4K, HDR, 48 fps')}</p>`, GROUP_EN)
