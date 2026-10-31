// «Disk space»: where things live (projects.py, render.py scenes/ cache, graph.py out/ frames/ pictures/,
// resolve.py, config.py weights), what can go (graph_io.cleanup, Shelf.vue delete - rmtree, models «Remove» - the
// Recycle Bin), and VRAM vs disk («Unload model»)
import { scenario, steps, step, go, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('disk', 'Disk space',
  'Where videos, shot scenes, takes and model weights live, what you can delete without losing anything, and what gets reshot afterwards.',
  meta('A 5 s draft scene is about 2 MB, but every scene piles up takes, a draft and a final. Model weights take the most space — tens of gigabytes.')
  + steps(
    step('See what takes up space',
      '<p>«Models and settings»: at the top, «Models on disk» — all weights in one bar with each model\'s color; on the left, next to each section, how much it takes.</p>'
      + go('/models', 'Models and settings')),
    step('Open the video\'s folder',
      `<p>The «Video» screen → «Open folder». Each video is a folder <code>projects\\&lt;date-time-code&gt;</code> in the program folder:</p>`
      + '<ul><li><code>project.json</code> — the video itself: storyboard, montage, settings;</li>'
      + '<li><code>scenes</code> — the cache of shot scenes: every scene, every take and every quality has its own <code>.mp4</code> and last frame <code>.png</code>;</li>'
      + '<li><code>video_draft.mp4</code>, <code>video_final.mp4</code> and the same with an output suffix (<code>_1080p</code>, <code>_music</code>…) — the joined videos;</li>'
      + '<li>photos, <code>track.*</code> — your track, <code>sounds</code> — montage sounds, <code>luts</code> — your LUTs, <code>resolve</code> — the DaVinci export if no folder was chosen;</li>'
      + '<li>a graph also has <code>graph.json</code>, <code>out</code> (joins, montages, outputs), <code>frames</code> and <code>pictures</code>.</li></ul>'),
    step('Decide what to delete',
      '<p>Safe: a scene from <code>scenes</code> — on «Shoot video» it is shot again, while the storyboard and montage in <code>project.json</code> stay. A joined <code>video_…mp4</code> — «Build video» in the montage joins it from the cache in seconds. The <code>resolve</code> folder is recreated by a new export.</p>'
      + '<p>Not safe: <code>project.json</code> — that is the video itself; photos, the track and sounds — there is nothing to restore them from.</p>',
      'A deleted scene means minutes of shooting: the continuations after it are reshot too if the new take comes out different.'),
    step('Remove extra takes',
      '<p>In the storyboard, × on a take only removes it from the list: the file stays in <code>scenes</code> and comes back if that seed is chosen again.</p>'
      + '<p>In a graph project, with nothing selected, the panel on the right has «Clean up takes». It first says how many files and megabytes: unselected takes and files no node refers to. Everything goes to the Windows Recycle Bin; service files starting with «_» (montage) are left alone.</p>',
      'Until all of the graph\'s scenes are shot, only unselected takes are removed — extra files are checked later.'),
    step('Delete a whole video',
      'On the home screen, the trash can in the card\'s corner. A dialog asks: «Delete the video «…» with its whole storyboard, shot scenes and finished video?» The folder is deleted for good, not to the Windows Recycle Bin. A video in progress can\'t be deleted — wait for shooting to finish first.',
      'A graph made with «Copy as a graph project» takes shot scenes from the storyboard\'s cache: delete the storyboard and its scenes will have to be shot again.'),
    step('Clean up the Lab',
      '<p>Lab takes live in the program\'s <code>outputs</code> folder, separate from videos. Under a take, «Delete»: the video, the frame and the settings go to the Windows Recycle Bin.</p>'
      + go('/lab', 'Open the Lab')),
    step('Remove unneeded weights',
      `<p>Video model and Krea weights live in the <code>H3_MODEL_ROOTS</code> folders (by default <code>models</code> in the app's folder), Ref2VA there too, LoRAs in each model's folders, the writer (GGUF) in the <code>LLM_DIRS</code> folders. In a model's section, a file has «Remove»: it goes to the Windows Recycle Bin. The model selected in the settings can't be removed, nor can anything during shooting.</p>`,
      'Without weights a model is marked «no weights»; «Download» brings the file back from Hugging Face.'),
    step('VRAM is not disk',
      '«Unload model» in the status bar or «Unload» on the models page frees VRAM for other programs. The files stay where they are; the next shoot loads the model again, adding up to half a minute.'),
  )
  + tip(`The program's <code>data</code> folder holds the settings (<code>settings.json</code>), speed measurements, your graph templates, logs and <code>songs</code> — the songs of clips, one per song for all clips made from it. Don't delete songs while clips made from them still exist.`)
  + tip('The DaVinci export and «Build storyboard» from a graph don\'t copy scenes; they create a hard link to the same file (on the same drive): it takes no extra space, but the space is freed only when all links are deleted. Empty the Windows Recycle Bin yourself — until then the space isn\'t freed either.')
  + `<p class="note">Next: ${see('cache', 'Cache and time')} · ${see('models', 'Models and settings')} · ${see('env', 'Settings in .env')} · ${see('tut-fix-scene', 'Fix one scene')}</p>`, GROUP_EN)
