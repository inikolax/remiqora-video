// The «Reshoot a finished video» scenario: the «Video → video» node (app/v2v.py: IC-LoRA LTX 2.5 / 2.3, H3 Ref2VA, a mask with
// alpha) and «Scene from a sample» — a LoRA that reads a clip or a voice (ID-LoRA), «Scene sound», voice similarity.
import { scenario, steps, step, go, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('remake', 'Reshoot a finished video',
  'A shot clip redone through a LoRA that reads the clip itself: remove the background, another angle, photorealism, larger, another hero. And a scene with a face from a photo and a voice from a sample.',
  meta('5–10 minutes · a 5 s clip is redone in 1–1.5 min (RTX 4080) · LTX 2.5 or 2.3 with IC-LoRA, H3 with the Ref2VA LoRA, LTX 2.3 with ID-LoRA for the voice · you need a graph project with a shot scene') +
  steps(
    step('Put the LoRA into its folder',
      '<p>An IC-LoRA goes into the LoRA folder of its LTX version (LTX 2.3 also has <code>ltx\\ic-loras</code>), a Ref2VA LoRA into the H3 LoRA folder. The folders are in «Models and settings». The node recognizes by itself that the LoRA reads a clip; how to run it comes from its profile.</p>' + go('/models', 'Models and settings'),
      'No profile means default settings; your own go into a &lt;name&gt;.v2v.json file next to the LoRA.'),
    step('Add «Video → video» to a scene',
      '<p>Open the graph from the list on the home screen. Select a shot Scene, click «Add» → «Video → video»: the node appears next to it, and the scene\'s «scene» goes into its «scene» input.</p>',
      'Turn a storyboard into a graph: «Graph» → «Copy as a graph project». Shot scenes come from the cache.'),
    step('Choose the LoRA',
      '<p>In the node\'s panel, «LoRA», «Choose…»: the groups «LTX 2.5 · IC-LoRA» (Alpha-Gen — remove the background, Restore, Deblur), «LTX 2.3 · IC-LoRA» (3DREAL — 3D render to photorealism, CrossView — another camera position, upscalers) and «H3 · Ref2VA» (Character-Swap — another hero from the picture in the «picture» input). Under the list: «Engine», «Result», «Length». A prompt if the LoRA asks for one; «LoRA strength», and on LTX also «Clip strength».</p>'),
    step('Make the clip',
      '<p>«Make up to here» shoots what the input needs and rebuilds the clip; a long one goes in pieces. When done, «Download MP4». Alpha-Gen has «For editing (MOV)» (ProRes 4444), «For the web (WebM)» and «Mask (MP4)». The «scene» output goes into a Join, a Montage or the next «Video → video».</p>',
      'A regular player doesn\'t show transparency and plays the whole clip.'),
    step('Shoot a scene from a voice sample',
      '<p>The «LoRA» node → «Add LoRA…» → the group «From a sample — shot by their model» → ID-LoRA («voice · LTX 2.3»). Its output goes into the Scene\'s «LoRA» input. The hero\'s «Photo» goes into «start», a «Track» with 5–10 s of clean speech (a file or «Record voice») into the «voice» input. In the scene panel: «Voice from, s» and «Sample, s» (5 is best). Lines go into the Prompt\'s «Lines» section.</p>',
      'Such a scene is shot by the LoRA\'s model (LTX 2.3), even if the graph shoots on another one.'),
    step('Take the voice from a shot scene',
      '<p>The «Scene sound» node: the «scene» of a shot Scene goes into its input, «Voice only — no music or noise (Demucs)», and the «track» output goes into the «voice» input of the next Scene with ID-LoRA. The hero speaks in one voice throughout the video.</p>',
      'Separating the voice takes about a minute on the graphics card.'),
    step('Check the voice',
      '<p>«Shoot up to here». The scene panel shows a line: «Voice matches the sample» — from 0.6, «partly matches» — in between, «doesn\'t match» — below 0.4. Don\'t like it? «Another take».</p>',
      'A sample with music and a short line lower the score.'),
  ) +
  tip('<b>A clip in a scene.</b> IC-LoRA and Ref2VA can also go into a Scene — through the «LoRA» node, the «From a sample» group, with the clip in the «scene» input: the length and frame come from the clip, while takes and continuations work as for any scene. Such LoRAs don\'t go into regular scenes: there they give a flat picture.') +
  tip('In the storyboard the voice is set on the hero: «Voice» in their card — a file, a recording or «From a scene…». LTX 2.3 scenes where only that hero speaks are shot with ID-LoRA.') +
  `<p class="note">Next: ${see('graph-nodes', 'Graph nodes')} · ${see('tut-graph', 'A graph from a template')} · ${see('tut-loras', 'LoRA')}</p>`, GROUP_EN)
