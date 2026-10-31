// «Final»: draft -> final with the same seeds, the output (RTX Video, HDR10, RIFE), the track, the file
import { scenario, steps, step, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('final', 'Final: 1080p, 4K, HDR, 48 fps',
  'From a checked draft to a finished video: larger and sharper, upscaled to 1080p or 4K, optionally with HDR10, 48 frames per second and your own track.',
  meta('An H3 final takes about 4.5 min per 5 s scene, LTX about a minute; upscaling takes 10–15 s per 30 s of video. You need a shot draft; for the output, RTX Video and RIFE in «Tools».')
  + steps(
    step('Polish the draft',
      'Open the video from the list on the home screen and fix scenes while shooting is cheap. Shot scenes sit in the cache: an edit reshoots only that scene and the continuations after it.'),
    step('Choose the output',
      '<p>On the storyboard, in the panel on the right, «Output»: «As shot» — no upscaling, «1080p» or «4K» — NVIDIA RTX Video after joining. «HDR10» (RTX TrueHDR) is available only with 1080p or 4K. «48 frames per second» — RIFE draws a frame between every two, without blending at the cuts between new scenes.</p>',
      'The output doesn\'t reshoot scenes: the button becomes «Rebuild: …».'),
    step('Add your own track',
      '<p>«Own track for the whole video» — an mp3, wav, m4a, flac or ogg laid as one track after joining. Sliders: «Track volume», «Scene sound», «Start track at», «Fade out at the end»; after an edit, «Remix the music» takes seconds.</p>'
      + '<p>Two checkboxes reshoot scenes: «Scenes without music, sounds only» (changes the prompts) and, on LTX 2.3, «Shoot to the track — a clip, heroes sing».</p>'),
    step('Shoot the final',
      'On the «Video» screen click «Shoot final» — the time estimate is next to it, the size is in the button\'s tooltip. Or on the storyboard, «Quality» → «Final» and «Shoot video». The seeds are the same, so the scenes are the same, only sharper: H3 at 1344×768, LTX and WAN at 1280×704.',
      'The size is part of the cache key, so the final shoots all scenes again. The draft stays in the cache: «Shoot draft» brings it back without shooting.'),
    step('Watch the stages',
      'On the right, a list: «Model and encoder», «Scenes 1–N» with a count, «Joining and sound», «Music: …» if there is a track, and the output. «Stop after the current scene» finishes and saves it; «Stop now» loses the current scene.'),
    step('Take the file',
      '«Download MP4» gives the video named after its title with the output suffix: <code>…_4k_hdr_48fps.mp4</code>. «Open folder» opens the project folder: the draft and the final sit side by side, <code>video_draft</code> and <code>video_final</code>, the upscaled ones with the same suffix.',
      'If upscaling fails, the video without it is still ready — the reason is in the yellow line.'),
  )
  + tip('These don\'t reshoot scenes: the track and its levels («Remix the music» on the «Video» screen), the output («Rebuild: …»), the montage («Build from the montage»). These reshoot: quality, model, frame, the video\'s LoRA, style and hero — the whole video; a scene edit — that scene and its continuations.')
  + tip('Watch HDR10 on an HDR screen: on a regular one it looks washed out.')
  + `<p class="note">Next: ${see('shoot', 'Quality, LoRA, music, output')} · ${see('video', 'The «Video» screen')} · ${see('tut-edit', 'Montage')}</p>`, GROUP_EN)
