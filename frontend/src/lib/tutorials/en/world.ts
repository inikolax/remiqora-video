// «A video without people»: mode "none" (IdeaView.vue «Who's in frame», planner/grid.py - one chain), the world instead of a
// hero (LookCard.vue «World», prompts.lock_text, TAIL_NONE), the lab's «Nature», WAN without sound and a track
import { scenario, steps, step, go, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('world', 'A video without people',
  'Landscapes, nature, a city, objects, effects. Instead of a hero the writer describes a «world», and the whole video runs as one continuous camera move.',
  meta('For a 30 s video: a draft on LTX takes 3.5–4 min, on FastWan about 4 min without sound. No face needs keeping, so any model will do.')
  + steps(
    step('Choose «No people»',
      '<p>On the home screen, the «Writer» way: «Who\'s in frame» → «No people». In «Idea», the place, time of day, weather and what changes: «a misty pine forest at dawn, rays break through the branches, the fog thins, a deer steps out in the distance». «Mood»: «Documentary» for nature, «Fantasy and effects» for magic and the elements.</p>'
      + go('/', 'Open the home screen')),
    step('Click «Write the scenes»',
      'The writer writes the «world» — a description of the place that goes into every scene word for word — and the scenes. The whole video is one chain: the first scene is new, and each next one starts where the previous one ended.',
      'With people, a chain breaks after three continuations, otherwise the face drifts. A landscape doesn\'t drift like that, and a cut would break the movement.'),
    step('Adjust the world',
      'The card above the timeline is called «World»; «at the end of the prompt: «No people»» — the model is told not to show people. «Edit» → «World» in your language, then «Update prompt from text». «EN, as sent to the model» can also be edited directly.',
      'The world goes into every scene: after an edit, all scenes are reshot.'),
    step('Check the scenes',
      'What matters in each scene is how it ends: the next one starts from that frame. The «check» marks here are their own: «A person appeared in a video without people», «It isn\'t said how the scene ends». A stray person in the action? Remove them from «What happens» or click «Improve».'),
    step('Choose the model',
      '<p>In the shooting panel, «Model»: LTX 2.5 is fast and has the sounds of the place; H3 has sound too, but takes three times as long. WAN 2.2 5B and FastWan give picture only, but FastWan shoots a 5 s scene in 40 s; the Apache-2.0 license allows commercial use too.</p>',
      'Changing the model reshoots the whole video; what the previous model shot stays in the cache.'),
    step('Add a track',
      '«Own track for the whole video» is one piece of music over all scenes: the models compose their own music in every scene, and it changes at the cuts. Check «Scenes without music, sounds only» to keep wind, water and birds. On WAN the track is the video\'s only sound.',
      'A track and its levels don\'t reshoot scenes — «Remix the music» takes seconds. The «Scenes without music» checkbox changes the prompts and reshoots the scenes.'),
    step('Shoot and build',
      '«Quality» → «Draft», «Shoot video». Like it? «Shoot final» with the same seeds, «Output» 1080p or 4K, «48 frames per second» for smooth camera fly-throughs.'),
  )
  + tip('<b>One scene in the Lab.</b> «Preset ▾» → the «No people» group → «Nature» (fog, rays, an animal in the distance) or «Object close-up». In the Graph, the «Landscape in one chain» template.')
  + tip('In a landscape the camera is the main movement: «a slow fly-forward between the trunks», «rising above the forest». In the inspector, «Camera»: «Orbit», «Pan», «Camera rise».')
  + `<p class="note">Next: ${see('timeline', 'Timeline and chains')} · ${see('look', 'Hero, style and Ref2VA')} · ${see('video-models', 'Video models')} · ${see('tut-final', 'Final')}</p>`, GROUP_EN)
