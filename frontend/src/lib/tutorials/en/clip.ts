// «A clip from a song»: the main screen's «Clip» -> the storyboard cut on the song's bars -> shooting to the track -> the montage on beats.
import { scenario, steps, step, go, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('clip', 'A clip from a song', `At the end you will have a clip for your song: scenes cut on the bars, the hero singing their lines, and the song itself as the video's sound.`,
  meta('About 10 minutes of work plus shooting; the model is LTX 2.3 (it hears the track). You need a song: mp3, wav, m4a, flac or ogg.') +
  steps(
    step('Upload the song', `<p>On the home screen, in the switch above the form, choose «Clip». Drag the song into the «Song» field or click it. Within a second the tempo, bars and parts are found: loud parts are highlighted on the waveform, the chorus has a pink line on top. Click the waveform and the clip starts from that bar.</p>${go('/', 'Open the home screen')}`),
    step('Check the lyrics', `<p>Click «Recognize lyrics»: Demucs separates the voice, Whisper writes down the words with the time of each — about 40 s on the graphics card. If you don't click it, the lyrics are recognized automatically before the writer runs. Fix mistakes in the field and click «Save my text»: it is laid onto the timing of the recognized words.</p>`,
      'Without lyrics the clip is written without singing scenes.'),
    step('Choose the length and the hero', `<p>Under the waveform: «30 s», «45 s», «1 min», «1.5 min» or «Whole song»; next to it, the segment and how many scenes it makes. «Idea» is optional. In «Who's in frame»: «One hero», «Several» or «No people». You can put a picture into «Singer's photo»: the writer describes the look from it. Without a photo Krea 2 draws the singer from the description, and the singing scenes start from that face.</p>`),
    step('Set the frame and model', `<p>«Frame» is 16:9, 9:16 or 1:1. «Model» defaults to LTX 2.3: it hears its piece of the track and moves the lips to the voice. If you pick another one, the singing scenes are still shot by LTX 2.3; it says so under the field.</p>`),
    step('Click «Write the clip»', `<p>Next to the button is the estimate: 10 s plus 4 s per scene, plus 40 s if the lyrics aren't recognized yet. The storyboard opens right away and fills in when the writer is done.</p>`),
    step('Look at the storyboard', `<p>Above the timeline is «Song»: the segment, the tempo and how many scenes of each type. Each part of the song is a cut; inside a part, scenes span whole bars: about 3 s in a loud part, twice as long in a quiet one. A scene's inspector has «Scene type»: «Singing», «Performance» or «Insert». Singing is only available where a voice is heard.</p>`),
    step('Shoot the clip', `<p>In the shooting panel, «Shoot to the track — a clip, heroes sing» is checked: each scene gets the piece of the song from its own place. Click «Shoot video». The scenes' own sound is off; the video's sound is the song.</p>`,
      'Editing the track or its start reshoots the scenes.'),
    step('Fit the cuts in the montage', `<p>Step «4 Montage» in the header. «Magnet» (the <kbd>M</kbd> key) makes clip trimming snap to the track's beats. «Cuts on beats» puts every cut on the beat before it; seamless chain joins are left alone. In a loud part a clip enters with a flash by default. Then «Build video».</p>`),
  ) +
  tip(`Don't reorder or speed up scenes in the montage without need: the track pieces are counted from the storyboard, and the lips will drift off the song. Trimming the ends and cuts on beats are safe.`) +
  tip(`For «Singer's photo» the writer must see pictures: in «Models and settings» → «Writer» such a model is labeled «sees photos».`) +
  `<p class="note">Next: ${see('clip', 'A clip from a song: reference')}, ${see('tut-edit', 'Montage step by step')}, ${see('shoot', 'Shoot to the track')}</p>`, GROUP_EN)
