// The «Montage and export to DaVinci Resolve» scenario: trim, split, copy, speed, takes, transitions, chains, sounds,
// track, color, «Build video»; then «For DaVinci Resolve…» (app/resolve.py) and what doesn't carry over.
import { scenario, steps, step, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('edit', 'Montage and export to DaVinci Resolve',
  'Shot scenes on a timeline: trimming, transitions, your own track and color, then a finished video or a timeline for DaVinci Resolve. Nothing is reshot.',
  meta('10 minutes · no video model: scenes come from the cache · you need a shot video; for the export, DaVinci Resolve') +
  steps(
    step('Open the montage',
      '<p>«Montage» is the fourth step in the header on «Storyboard», or the «Montage» button on the «Video» screen. At the top, the project bar with «Build video»; below it, the player above the timeline, and a panel on the side. Space plays, <kbd>←</kbd> <kbd>→</kbd> step a frame.</p>'),
    step('Trim and split clips',
      '<p>Drag a clip\'s left or right edge to trim its start or end; the scenes after it shift by themselves. For precision, «Start» and «End» in the clip panel, the ‹ › arrows step a frame. <kbd>S</kbd> («Split») splits the clip at the playhead, <kbd>Ctrl</kbd> <kbd>D</kbd> («Copy») places a copy right after it. «Speed» is 0.5–2×, picture and sound together. If there are other takes, «Take» shows thumbnails.</p>',
      'A clip is no shorter than 0.5 s. «Reset» restores the whole scene.'),
    step('Move chains and check the seams',
      '<p>Drag a clip and its continuations travel with it as a whole chain; a blue line shows where. Above every seam is an icon: a link means seamless, a yellow triangle means the picture jumps. Click a jumping seam for «Restore the seam» or «Hide with a dissolve».</p>'),
    step('Set transitions',
      '<p>Clicking a seam\'s icon opens its panel, section «Transition»: «Cut», «Flash» (a white flash for 4 frames, doesn\'t change the length), «Dissolve» or «Through black»; the last two have «Length» 0.2–2 s. «Play the seam» plays from a second and a half before it.</p>',
      'A dissolve shortens the video by its length: the scenes overlap.'),
    step('Add sound',
      '<p>A clip has the «Scene sound» slider (0–200 %). On the «Music» track, «Own track»; clicking the track opens its settings and «Ducks under scenes»: the track gets quieter under lines. With a track, «Magnet» (<kbd>M</kbd>, trimming snaps to beats) and «Cuts on beats» appear above the timeline. On the «Sounds» track, «+ Sound»: the file is placed at the playhead.</p>'),
    step('Set the color',
      '<p>Clear the selection (<kbd>Esc</kbd>) and the panel shows «Video color»: «Film», «Warm», «Cool», «Teal and orange», «Black and white» or «Load LUT (.cube)». «Match scenes\' color» pulls each clip toward the video\'s average, so scenes from different models stop jumping in color.</p>',
      'Color and «Ducks under scenes» are visible only in the built video.'),
    step('Build the video',
      '<p>«Build video» in the project bar: joins by the montage, the track, 1080p / 4K / HDR / 48 fps. If some scenes aren\'t shot yet, the button is «Shoot and build». <kbd>Ctrl</kbd> <kbd>Z</kbd> undoes any edit, even «As in the storyboard».</p>'),
    step('Export to DaVinci Resolve',
      '<p>In the panel (nothing selected), «For DaVinci Resolve…». Choose a folder: «&lt;name&gt; · Resolve» appears in it, with an FCPXML timeline and the files it plays. In Resolve: File → Import → Timeline. Exporting again recreates this folder.</p>'),
  ) +
  tip('<b>What arrives in Resolve.</b> Scenes with their own sound, trims, speed, dissolves and volume; the track and sounds on their own tracks, with fades. A flash becomes a «Flash» marker. An unshot scene becomes an empty gap of its length, «Scene N — not shot»: shoot it and export again. «Ducks under scenes» and the video color don\'t carry over — your own LUT is placed next to the timeline.') +
  tip('A graph node\'s montage («Open montage») is the same editor, but it doesn\'t export to Resolve yet.') +
  `<p class="note">Next: ${see('edit', 'Montage — reference')} · ${see('tut-final', 'Final')} · ${see('video', 'The «Video» screen')}</p>`, GROUP_EN)
