// «Fix one scene»: after the draft - takes (SceneTakes.vue, main.new_take), the writer's buttons on the card,
// the inspector's fields, the pin, the checks, and what reshoots (render.preview: the scene and its continuations)
import { scenario, steps, step, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('fix-scene', 'Fix one scene',
  'The draft is shot, but one scene came out badly: the wrong face, odd movement, a line cut short. You can reshoot it, rewrite it or fix it by hand — the rest of the video stays as it is.',
  meta('A take of a 5 s draft scene: about 1.5 min on H3, about 30 s on LTX. Only this scene and the continuations after it are reshot. You need a shot draft.')
  + steps(
    step('Find the scene',
      'Open the video from the list on the home screen. On the storyboard every card shows the last frame of the shot scene; a click opens the inspector on the right. On the «Video» screen, clicking a scene in the strip at the bottom shows it in the player.'),
    step('Shoot another take',
      '<p>Often a scene is fine as text, it was just unlucky with randomness. In the inspector, in the «Takes» block: «Another take» shoots the scene again with a new seed, now and on its own, as a separate task in the queue. Earlier takes are kept.</p>'
      + '<p>The thumbnails are all of the scene\'s takes; a click chooses which one goes into the video and into the continuations after it. × removes a take from the list; the file stays in the cache. The card shows «take 2/3».</p>',
      'While the video is shooting, a take won\'t start. Continuations after a scene with a different take are reshot on «Shoot video»: their start frame has changed.'),
    step('Ask the writer',
      'On the card, «Improve» has the writer make the scene more concrete and visual while keeping its meaning; «Another version» gives a different action and angle that still fit the video. Several bad scenes? Pin the good ones and click «Rewrite unpinned» above the cards.'),
    step('Or fix it yourself',
      '<p>In the inspector: «What happens» in your language, then «Update prompt from text» — the writer rewrites the English to match your text. «Camera» and «Shot» are picked from lists: a static camera is gentlest on the face. «Actions by line» are in English, one action per line; editing them pins the scene. Keep «Lines» shorter — about 10 words per 5 s.</p>',
      'Until the prompt is updated, the card shows «Text changed — prompt is still old».'),
    step('Pin what works',
      '«Pin» at the bottom of the inspector: the writer won\'t touch such a scene — not with the buttons, not with «Rewrite unpinned», not with auto-fix. On the card, «Unpin» replaces «Improve» and «Another version».'),
    step('Look at the marks',
      '<p>A yellow line on a card is a «check» mark: what the code considers a mistake in the text (walking with no direction toward the camera, a long line, text in the frame). It is advice, not a ban.</p>'
      + '<p>«In the clip: frozen for 2.5 s» is a check of the shot clip. Serious ones — black frames, «frozen», a jump, a long blur — are reshot automatically once with a different seed; for the rest, look at that spot yourself.</p>'),
    step('Shoot what changed',
      'In the shooting panel, under the button, you see how many scenes come from the cache and how many will be shot. On the «Video» screen the button becomes «Shoot what changed»: the edited scene and the continuations after it are shot, the rest come from the cache, then everything is joined.',
      'A scene\'s cache key holds the prompt, seed, model, length, LoRA and start frame. If any of them changes, the scene is reshot.'),
    step('Or pick another take in the montage',
      'If a scene has several takes, the clip panel in the montage has «Take»: the clip can use any of them, the storyboard doesn\'t change. A different take before a continuation gives a jump at the seam — a yellow triangle marks it.'),
  )
  + tip('<b>Translate to Russian.</b> A button above the cards when the storyboard has scenes in English (clips from Remiqora): the writer translates what happens and the prompt, for reading only. The original goes to the model; nothing already shot is reshot.')
  + tip('Editing the hero\'s look, the style, the model, the quality or the video\'s LoRA reshoots the whole video, not one scene. To fix one scene, change the fields in its own inspector.')
  + `<p class="note">Next: ${see('inspector', 'Scene inspector')} · ${see('check', 'The «check» mark')} · ${see('cache', 'Cache and time')} · ${see('tut-edit', 'Montage')}</p>`, GROUP_EN)
