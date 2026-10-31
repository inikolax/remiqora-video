// «Bring a photo to life»: the video starts from the user's photo (IdeaView.vue photoStarts -> plan scene 0 start_photo,
// writer.describe_starts), the crop to the frame (render: around the centre), the inspector's «First frame», the lab,
// and without a photo - the graph's «Picture» (Krea 2) into a scene's «start»
import { scenario, steps, step, go, see, tip, meta, GROUP_EN } from '../kit'

export default scenario('photo', 'Bring a photo to life',
  'A video that starts from your picture: the model brings the photo to life, and the writer continues the action from that moment. Works for a portrait, a landscape, an object.',
  meta('Like a regular video; the writer takes 10 s longer, since it looks at the photo first. Any video model can animate a start frame. You need a writer that «sees pictures».')
  + steps(
    step('Pick a picture',
      'A png, jpg or webp of the same shape as the video\'s frame. A photo of another shape is cropped at the edges around the center: a vertical phone shot in a 16:9 video loses its top and bottom, and the head may go out of frame.'),
    step('Upload the photo on the home screen',
      '<p>The «Writer» way, the «Photo» field: drag the picture in or click. Choose «First frame» («bring the photo to life»): the video starts exactly from this picture. «Look only» is different: the writer describes the hero from the photo in words, and the photo doesn\'t get into the frame.</p>'
      + go('/', 'Open the home screen'),
      'If the shape doesn\'t match, there is a yellow line «Photo of another shape: edges will be cropped to …» and a button «Use 9:16» (or another frame closer to the photo).'),
    step('Write what happens next',
      'In «Idea», what happens after this moment: «she turns toward the sea, the wind lifts her hair, she smiles». What is in the photo the writer sees by itself: the pose, the place, the light. «Who\'s in frame» as usual; with «No people» the photo is always the first frame.'),
    step('Choose the model and click «Write the scenes»',
      'Any model can animate a picture: H3 with a voice in the video\'s language, LTX faster, WAN without sound. The writer describes the photo and writes the first scene from it; then continuations and new scenes follow, as in any video.',
      'A writer without vision won\'t take the photo: «Model … doesn\'t see pictures» — choose another one in the header.'),
    step('Check the first scene',
      '<p>In the first scene\'s inspector, under «First frame»: «The scene will start from this photo» and the line «The writer sees: …». Changed the picture («Another photo»)? Click «Rewrite for the photo», otherwise the text drifts away from the photo and the face changes. «Remove» shoots the scene from the text only.</p>'
      + '<p>You can start any other new scene from a photo too: «Start from photo» or «From the hero\'s photo».</p>'),
    step('Keep the face further on',
      'Scenes after the first start from the video\'s frames, and the face slowly drifts. On H3, check «Keep the face from the photo (Ref2VA)» in the hero card: new scenes match the face against your picture. LTX and WAN don\'t keep the face from a photo — only through words and the start frame.',
      'For Ref2VA a frontal portrait on an even background is best: the model pulls the surroundings from the picture too.'),
    step('One scene in the Lab',
      '<p>Lab: «Start frame» — drag a picture in, and set the frame to «as the frame» so it isn\'t cropped. The first line of the prompt is <code>Continue seamlessly from &lt;Picture 1&gt;.</code>, then the movement and the camera. «Describe the person» gives the look in English for the prompt.</p>'
      + go('/lab', 'Open the Lab')),
    step('No photo? Draw one',
      'Graph: on the home screen «Graph» → «Choose a template» → «Picture → scene». The «Picture» node — Krea 2 draws from a prompt at the size of the video\'s frame, about 3.5 s; its «picture» output goes into the «start» input of a Scene. The «Bring a photo to life» template does the same with your own picture in the «Photo» node.',
      'The first picture after video takes about 10 s: the video model is unloaded. You need the Krea 2 weights.'),
  )
  + tip('The photo sets the first frame, the prompt sets what comes next. Don\'t describe another place or other clothes in the idea: the model will drift from the picture toward the text.')
  + `<p class="note">Next: ${see('idea', 'The «Idea» screen')} · ${see('inspector', 'Scene inspector')} · ${see('tut-hero', 'Your own hero')} · ${see('graph-nodes', 'Graph nodes')}</p>`, GROUP_EN)
