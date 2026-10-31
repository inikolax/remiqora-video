// The screens' help windows and keys sheets in English: the same shape, keys and ids as guides.ts.
import type { Guide } from './guides'

const WHO = { h3: 'var(--accent)', writer: 'var(--ok)', ffmpeg: '#378ADD', user: 'var(--faint)', krea: '#f59e0b', v2v: '#14b8a6', facefix: '#2dd4bf' }

export const GUIDES_EN: Record<string, Guide> = {
  app: {
    title: 'Remiqora Video help', icon: 'help',
    lead: 'A studio for videos and music clips on the MiniMax H3, LTX 2.3 and 2.5, and WAN 2.2 5B video models that runs entirely on this computer. You write an idea or give it a song, the writer breaks it into scenes, the chosen model shoots them (H3 and LTX with sound and spoken lines, WAN without sound), and the studio joins the video, lays the music and upscales it to 1080p or 4K.',
    steps: [
      { title: 'Idea', text: 'A couple of sentences or a song for a clip, a model, and optionally a photo of the hero or of the first frame.' },
      { title: 'Storyboard', text: 'Scenes of 5 s, 10 s on LTX: edit the text, the hero, the camera and the order.' },
      { title: 'Video', text: 'Scenes are shot as a chain, then the join, music and output; «Montage» is for trimming and transitions.' },
      { title: 'Graph', text: 'When you need branches: two endings, takes, a scene starting from the frame of any other.' },
    ],
    table: {
      title: 'Storyboard or graph',
      head: ['', 'Storyboard', 'Graph'],
      rows: [
        ['What for', 'A straight video, «idea → scenes»', 'Branches and versions of one video'],
        ['Scenes', 'In order; a continuation starts from the previous one', 'Start from the frame of any scene, a photo or a picture'],
        ['Versions', 'One video, scene seeds', 'Scene takes, branches, as many outputs as you like'],
        ['Writer', 'Writes and edits via the buttons on scenes', 'A «Writer» node that expands into nodes'],
        ['Cache', 'Its own', 'The same key: a graph made from a storyboard shoots only what is new'],
      ],
    },
    sections: [
      { title: 'Graphics card and queue', icon: 'clapper', items: [
        'The line under the header shows what the graphics card is doing: a <b>purple</b> dot means a video model is shooting, <b>green</b> means the writer is working, grey means it is free. A click opens the job, the queue and «Stop»; when free, «Unload model».',
        'The writer and a video model do not fit in video memory together, so jobs run one at a time. After the writer, the model loads again: up to half a minute, depending on the model.',
        '<b>RAM</b> on the right turns yellow from 80 % and red from 92 %; beyond that shooting slows down. <b>VRAM</b> is colored by who holds the memory.',
      ] },
      { title: 'Where things are stored', icon: 'folder', items: [
        'Videos are in the <code>projects</code> folder: the storyboard, the shot scenes, the finished files. You can close the page mid-work and the result is saved.',
        'Every shot scene sits in the cache under a key made of everything that defines it. Change nothing and the scene is taken instantly.',
        'Model weights, LoRA and tools are on the «Models and settings» page. The writer is a model from LM Studio\'s downloads, chosen in the header.',
      ] },
    ],
    tips: [
      'Shoot a draft first, fix the scenes and press «Shoot final»: with the same seeds the scenes stay the same, only sharper. The size depends on the model: H3 960×544 and 1344×768, LTX 1024×576 and 1280×704.',
      'Every screen has its own help: the «Help» button next to the title. The «?» by a field explains only that field.',
      'The panel with fields can be moved: drag the ⠿ handle at the top of the panel to the left, the right, or as a window over the screen; drag the panel\'s edge to make it wider.',
      'The full reference with every parameter and examples is the button at the bottom of this window.',
    ],
    limits: [
      'A scene is 5 s on H3 and WAN, 10 s on LTX; a video is up to 10 minutes. A 5 s draft scene takes about 1.5 min on H3, about half a minute on LTX, about 40 s on FastWan, about 2 min on WAN.',
      'Adult characters only: the storyboard code checks this.',
      'The model keeps a face from the text; long chains of continuations make the face drift. After three 5 s continuations or one 10 s one, a new scene is better.',
    ],
    more: [{ id: 'start', title: 'From idea to video' }, { id: 'tut-first-run', title: 'Scenarios step by step' }, { id: 'how', title: 'How it works' }, { id: 'header', title: 'Header and status line' }],
  },

  idea: {
    title: 'Help: the «Idea» screen', icon: 'spark',
    lead: 'Where a video begins: a couple of sentences, the length, the frame shape, the model and the mood. «Write the scenes» hands the idea to the writer: it breaks it into scenes (5 s on H3 and WAN, 10 s on LTX), and the storyboard opens.',
    steps: [
      { title: 'Describe the idea', text: 'Who, where, what happens and how it ends. The more concrete, the more connected the scenes.' },
      { title: 'Add a photo', text: 'Optional: the first frame of the video or only the hero\'s look.' },
      { title: 'Set up the video', text: 'Length, frame 16:9 / 9:16 / 1:1, model, mood, who is in the shot, music.' },
      { title: 'Write the scenes', text: 'The writer writes the storyboard: 20–30 s for a 30 s video.' },
    ],
    map: { cols: 'minmax(0, 1fr) minmax(0, 1.6fr)', areas: ['form how', 'form reels'], zones: [
      { area: 'form', title: 'The form on the left', text: 'How to start: Writer, Clip, Own prompts, Graph. Idea, photo, length, frame, model, mood, who is in the shot, music and «Write the scenes».', accent: true, deco: 'rows' },
      { area: 'how', title: 'How it works', text: 'Four steps: idea, storyboard, video, montage, shown while there are no videos yet.' },
      { area: 'reels', title: 'Your videos', text: 'Search and the «Storyboards / Graphs» filter; each card shows the kind and the state: «writing…», «shooting…», «check 2», «done».', deco: 'reels' },
    ] },
    sections: [
      { title: 'Photo', icon: 'image', items: [
        '<b>First frame</b>: the video starts with this picture. The model brings it to life, and the writer first describes what is in the photo and continues the action.',
        '<b>Look only</b>: the writer describes the hero in words, and the scenes are shot from the text.',
        'The picture is best in the same shape as the video\'s frame: a vertical photo in 16:9 gets cropped at the edges.',
      ] },
      { title: 'Who is in the shot', icon: 'user', items: [
        '<b>One hero</b>: one person in every scene.',
        '<b>Several</b>: 2–3 people, each scene with its own cast.',
        '<b>No people</b>: landscapes, objects, effects; each scene starts where the previous one ended.',
      ] },
      { title: 'Length, model and time', icon: 'film', items: [
        'From 15 seconds to 10 minutes. Scenes are 5 s on H3 and WAN (30 s is 6 scenes), 10 s on LTX (30 s is 3 scenes).',
        '<b>Model</b> is who shoots: H3 and LTX with sound and spoken lines in the video\'s language, WAN without sound; LTX 2.3 can shoot to your track. You can change it later, and give a scene its own.',
        'A 5 s draft scene: about 1.5 min on H3 (a 30 s video takes some 10 minutes), about half a minute on LTX, about 40 s on FastWan, about 2 min on WAN.',
      ] },
      { title: 'A clip from a song', icon: 'music', items: [
        'The «Clip» switch above the form: a song, lyrics (recognized automatically), «Singer\'s photo», who is in the shot, frame, model, and «Write the clip».',
        'Scenes are cut on the song\'s bars; where the voice sings, the hero sings their lines. LTX 2.3 can do this.',
      ] },
      { title: 'Without the writer', icon: 'pen', items: [
        'The «Own prompts» switch above the form: an empty storyboard of the length you need; you write each scene\'s prompt yourself, in English.',
        '«Graph» above the form: a graph project from a template or from an empty canvas.',
      ] },
    ],
    tips: [
      '«A girl in a red coat walks along a riverside at night in the rain, stops by a street lamp and smiles»: place, light, weather, clothes and an ending make connected scenes.',
      'The mood sets the style of the whole video: light, color, pace, camera.',
    ],
    limits: [
      'A model with sound composes its own music in every scene, and WAN has no sound at all: for one tune across the whole video, put your own track on the storyboard.',
      'The photo is described by a writer that can see pictures («sees photos» in the model list in the header).',
    ],
    more: [{ id: 'idea', title: 'The «Idea» screen' }, { id: 'clip', title: 'A clip from a song' }, { id: 'prompt', title: 'How to write a prompt' }],
  },

  board: {
    title: 'Help: the storyboard', icon: 'film',
    lead: 'The video scene by scene: 5 s on H3 and WAN, 10 s on LTX. Here you edit the scenes\' text, the hero, the camera and the order, and on the right choose the quality, LoRA, music and output. Every edit is saved at once; only what changed gets shot.',
    steps: [
      { title: 'Approve the hero', text: 'The «Heroes» tab: Krea draws tries, you approve one — the scenes hold the face by it.' },
      { title: 'Go through the scenes', text: '«Grid» shows every scene by episode; a click on a card opens the scene panel on the right.' },
      { title: 'Fix the «check» marks', text: 'Your own edit in «What happens», or «Improve» on «Scene in detail». The mark is advice, not a ban.' },
      { title: 'Shoot', text: 'The main button at the top right: «Shoot video». Quality, LoRA, music and output are on the «Shooting» tab.' },
    ],
    map: { cols: 'minmax(0, 1fr) minmax(8rem, 32%)', areas: ['bar bar', 'show insp', 'sheet insp', 'map map'], zones: [
      { area: 'bar', title: 'Tabs', text: 'Scenes, Heroes, Places, Song, Video — what is in each under its name; on the right «k of n shot» and the main button.', accent: true },
      { area: 'show', title: 'Show', text: 'Grid, Frame, Script, Graph — how the scenes are shown.' },
      { area: 'sheet', title: 'The sheet', text: 'An episode is a row: its number in the margin, what it is about, how much is shot; the cards beside it. In a clip an episode is one scene, so the sheet reads as a list.', deco: 'cards' },
      { area: 'insp', title: 'Scene panel', text: 'Number and time, «What happens»; tabs Start, Scene, Shooting, Lines, Takes; under the text, who wrote it; «Another take», «Pin» at the bottom.' },
      { area: 'map', title: 'The video\'s map', text: 'The episodes as a strip, the selected scene\'s episode framed; a click goes to a scene.', deco: 'chain' },
    ] },
    sections: [
      { title: 'Scenes and chains', icon: 'link', items: [
        'A <b>new scene</b> is shot from text, in its own place; a <b>continuation</b> starts from the last frame of the previous one.',
        'With people, no more than three 5 s continuations in a row (one of 10 s), then a new scene: otherwise the face drifts.',
        'In the inspector: <b>Model</b>: a new scene can have its own, for the whole chain; <b>Length</b>: up to the model\'s limit, H3 15 s, LTX 10, WAN 5; <b>Last frame</b> (LTX): a picture the scene arrives at.',
        'An episode is a chain: a new scene and the continuations after it. In a clip nearly every scene is new — episodes of one scene, the sheet reads as a list.',
        'Change the order in the «Script» by dragging a line. The lock means the writer leaves the scene alone.',
      ] },
      { title: 'The writer on buttons', icon: 'spark', items: [
        '<b>Improve</b>: more concrete and visual; <b>Another version</b>: a different action and angle.',
        'Changed the Russian text? «Update the prompt from the text» rewrites the English to match. Scenes only in English: «Translate to Russian» above the cards.',
        'A scene with a photo: press «Rewrite for the photo» so the writer sees the picture.',
      ] },
      { title: 'Hero, face and voice', icon: 'face', items: [
        'A detailed look changes less between scenes: age, hair, skin, distinctive features.',
        '«Heroes» is a casting: the look is edited right in the card; «Adjust features» keeps the face and changes a detail (FLUX.2 edits the portrait); «Another person» gives new faces from the look or your own photo. A click on a try compares it with the portrait, «Approve» is in the comparison. «In the scenes» says whether the face holds in the shot scenes.',
        '<b>Keep the face from the photo</b>: H3\'s new scenes are shot by the Ref2VA model with the hero\'s photo as the face sample; LTX and WAN don\'t have this.',
        '<b>Voice</b>: a 5–10 s sample of clean speech, from a file, the microphone or «From a scene…». LTX 2.3 scenes where only this hero speaks are shot in this voice (ID-LoRA).',
      ] },
      { title: 'Lines', icon: 'user', items: [
        'Under everyone in the scene: what they say in the video\'s language and how: quietly, in a whisper, shouting… Empty means silent.',
        'The code puts the line into the timeline on its own row, the speaker by the heroes\' descriptions, the voices into the sound. WAN does not speak: lines need H3 or LTX.',
        '<b>Suggest lines</b>: the writer proposes them on the button. About 2 words fit per second of the scene.',
      ] },
      { title: 'Own prompt', icon: 'pen', items: [
        '«Write the prompt myself» in the inspector: the prompt goes to the model word for word, and the writer no longer touches the scene.',
        'A continuation and a scene with a photo need the first line <code>Continue seamlessly from &lt;Picture 1&gt;.</code>',
      ] },
    ],
    cards: { title: 'What gets reshot', items: [
      { title: 'A scene edit', text: 'That scene and the continuations after it.', color: WHO.h3 },
      { title: 'Take', text: '«Another take»: only that scene, right now; choosing one reshoots its continuations.', color: WHO.h3 },
      { title: 'A scene\'s model, length, LoRA', text: 'The scene and the continuations after it.', color: WHO.h3 },
      { title: 'The video\'s model, quality, frame, LoRA', text: 'The whole video.', color: 'var(--warn)' },
      { title: 'Style, hero, Ref2VA', text: 'The whole video.', color: 'var(--warn)' },
      { title: 'Music', text: 'No reshoot: «Remix the music», seconds. With «Shoot to the track» (LTX 2.3), the scenes again.', color: WHO.ffmpeg },
      { title: 'Output', text: 'No reshoot: «Rebuild».', color: WHO.ffmpeg },
    ] },
    tips: [
      'Pin the scenes that worked and press «Rewrite unpinned»: the writer builds on the pinned ones.',
      'A static camera is kindest to the face; a close-up shows the face better, a wide shot the place.',
      'Actions on timeline rows: one per row, with the direction relative to the camera, or people walk backwards.',
    ],
    limits: [
      'A continuation cannot move to another place: that would be an abrupt cut in the middle of the scene.',
      'Models draw text and signs in the shot as gibberish, so the writer avoids them.',
    ],
    more: [{ id: 'look', title: 'Heroes: casting, style and Ref2VA' }, { id: 'timeline', title: 'Screen, episodes and chains' }, { id: 'inspector', title: 'Scene panel' },
      { id: 'check', title: 'The «check» mark' }, { id: 'shoot', title: 'Quality, LoRA, music, output' }],
  },

  video: {
    title: 'Help: the «Video» screen', icon: 'clapper',
    lead: 'Shooting and the result: scenes are shot as a chain, then joined with sound, your track and the output. The time is estimated from the latest shoots on this machine, counting the cache.',
    steps: [
      { title: 'Shoot video', text: 'Scenes in the cache are taken at once; only what is new gets shot. After edits the button reads «Shoot what changed», «Build from the montage» or «Remix the music».' },
      { title: 'Follow the scenes', text: 'At the bottom: «step 5/8», «from cache», «waiting for frame», how long it took.' },
      { title: 'Join and output', text: 'Stages on the right: model and encoder, scenes, join, music, 1080p / 4K.' },
      { title: 'Take the video', text: '«Download MP4», «Open folder», «Montage» or «Shoot final».' },
    ],
    map: { cols: 'minmax(0, 1fr) minmax(8rem, 30%)', areas: ['player side', 'shots side'], zones: [
      { area: 'player', title: 'Player', text: 'While shooting, the latest finished scene; afterwards, the whole video.', deco: 'player' },
      { area: 'shots', title: 'Scene strip', text: 'Click to watch a scene.', deco: 'shots' },
      { area: 'side', title: 'Time left and stages', text: 'Time to finish, stages with check marks, «Stop after the current scene», «Stop now», «Download MP4», «Montage», final.', accent: true },
    ] },
    cards: { title: 'Quality and output', items: [
      { title: 'Draft', text: 'By model: H3 960×544, ~1.5 min per 5 s; LTX 1024×576, ~0.5 min; WAN 960×544.', color: WHO.h3 },
      { title: 'Final', text: '«Shoot final», the same seeds: H3 1344×768, ~4.5 min per 5 s; LTX and WAN 1280×704.', color: WHO.h3 },
      { title: '1080p and 4K', text: 'NVIDIA RTX Video, ~10–15 s per 30 s of video.', color: WHO.ffmpeg },
      { title: 'HDR10', text: 'RTX TrueHDR, for an HDR screen.', color: WHO.ffmpeg },
      { title: '48 fps', text: 'RIFE draws the in-between frames and does not blend across cuts.', color: WHO.ffmpeg },
      { title: 'Your own track', text: 'Laid after the join. Only «Shoot to the track» (LTX 2.3) reshoots the scenes.', color: WHO.ffmpeg },
    ] },
    sections: [
      { title: 'Stop', icon: 'stop', items: [
        '<b>After the current scene</b>: it finishes and is saved, the rest wait for the next run.',
        '<b>Now</b>: shooting is interrupted and the current scene is lost.',
      ] },
      { title: 'What comes from the cache', icon: 'layers', items: [
        'Scenes where nothing changed: model, prompt, seed, size, LoRA, start frame.',
        'Music and output do not reshoot scenes, only the mix and processing, in seconds. The exception is «Shoot to the track»: editing the track reshoots the scenes.',
      ] },
    ],
    tips: [
      'Draft → edits → «Shoot final»: the final is shot with the same seeds, so the scenes are the same, only sharper.',
      'You can close the window: shooting runs in the queue and the video is saved to the project.',
    ],
    limits: [
      'The first scene takes longer while the model loads: up to half a minute, depending on the model; the same after the writer.',
      'HDR10 looks washed out on a regular screen.',
    ],
    more: [{ id: 'video', title: 'The «Video» screen' }, { id: 'cache', title: 'Cache and time' }, { id: 'shoot', title: 'Quality, LoRA, music, output' }],
  },

  edit: {
    title: 'Help: montage', icon: 'film',
    lead: 'The shot scenes on a timeline, like tracks in Remiqora\'s DAW: trim a scene\'s start and end, rearrange chains, add a dissolve, a flash or a transition through black, set the video color, lay your own track. Nothing is reshot: «Build video» cuts and joins the scenes from the cache in seconds.',
    steps: [
      { title: 'Shoot the video', text: 'Montage works with shot scenes; without edits it matches the storyboard.' },
      { title: 'Cut', text: 'Drag a clip\'s edge: the start or the end of the scene. The player shows the frame at the seam.' },
      { title: 'Watch the seams', text: 'The icon above a seam: a link means seamless, yellow means it jumps. A click gives the transition and «Restore the seam».' },
      { title: 'Build', text: '«Build video» in the top bar: the join by the montage, music, 1080p / 4K. Once built, «Open the video» takes its place.' },
    ],
    map: { cols: 'minmax(0, 1fr) minmax(8rem, 30%)', areas: ['bar bar', 'player side', 'shots side'], zones: [
      { area: 'bar', title: 'Project bar', text: 'Length, whether the video is built from the montage and one main button: «Build video» or «Open the video».', accent: true },
      { area: 'player', title: 'Player', text: 'The montage as it is: seams, dissolves, scene sound and the track. Click or Space to play.', deco: 'player' },
      { area: 'side', title: 'Panel', text: 'Four tabs, the selection opens its own. «Clip» — trim, take, speed; a seam — the transition, «Restore the seam». «Color» — the look and correction. «Sound» — the track and sounds. «Output» — whether the video is built, «For DaVinci Resolve…».' },
      { area: 'shots', title: 'Timeline', text: 'Tools above it, and with a track «Magnet» and «Cuts on beats». Seam icons above the clips, sound tracks; the top border can be dragged.', deco: 'shots' },
    ] },
    cards: { title: 'Transitions', items: [
      { title: 'Cut', text: 'Straight cut. A chain\'s continuation is seamless.', color: WHO.ffmpeg },
      { title: 'Dissolve', text: 'The scenes blend over 0.2–2 s, the sound too.', color: WHO.ffmpeg },
      { title: 'Through black', text: 'Fade to black and back out.', color: WHO.ffmpeg },
      { title: 'Flash', text: 'A cut with a white flash of 4 frames.', color: WHO.ffmpeg },
      { title: 'Split and copy', text: 'S splits a scene in two, Ctrl + D copies the clip.', color: WHO.user },
      { title: 'Speed', text: '0.5–2×: the scene\'s picture and sound together.', color: WHO.user },
      { title: 'Sounds', text: 'Your own files on the «Sounds» track, at the playhead.', color: WHO.user },
    ] },
    sections: [
      { title: 'Chains', icon: 'link', items: [
        'A continuation starts from the last frame of the previous scene, so a chain\'s scenes stay together: dragging a clip moves the whole chain.',
        'Trim a seam inside a chain and the picture jumps: a yellow triangle appears above the seam, and its panel says why and offers «Restore the seam».',
      ] },
      { title: 'Link to the storyboard', icon: 'pen', items: [
        'A reshot scene stays the same clip with its trims; a deleted one goes away; a new one lands after the scene before it.',
        '«As in the storyboard» removes all montage edits.',
      ] },
      { title: 'Video color', icon: 'image', items: [
        'One grade for all scenes: «Film», «Warm», «Cool», «Teal and orange», «Black and white» or «Own LUT (.cube)».',
        '<b>Match scenes\' color</b>: each clip is pulled toward the video\'s average, so scenes from different models and takes don\'t jump in color.',
      ] },
      { title: 'To a track', icon: 'music', items: [
        '<b>Magnet</b> (M): clip trims and sounds snap to the track\'s beats. <b>Cuts on beats</b>: each cut moves to the beat before it; seamless chains are left alone.',
      ] },
      { title: 'For DaVinci Resolve', icon: 'export', items: [
        '«For DaVinci Resolve…» asks for a folder and puts an FCPXML timeline with its files into «&lt;name&gt; · Resolve»: scenes with their own sound, the track, the sounds. In Resolve: File → Import → Timeline.',
        'Unshot scenes arrive as gaps of their length. Track ducking and the video color are not carried over; your own LUT is placed alongside.',
      ] },
    ],
    tips: [
      'Scene sound travels with the picture and no longer runs ahead at seams: lines stay on the lips.',
      'Space plays, arrows step a frame, Shift + arrows a second, Ctrl + wheel zooms; S splits, M is the magnet, Delete removes, Ctrl + Z undoes; ? shows all keys.',
      'Double-click a seam icon to play it from a second and a half before the seam.',
      '«Ducks under scenes» on the music makes the track quieter under spoken lines without manual curves.',
    ],
    limits: [
      'One video track: clips follow one another; picture over picture is not done here. Chains are moved as a whole.',
      'Track ducking and the video color are visible only in the built video; there are no volume curves yet.',
      'The browser preview may stutter slightly at a seam; in the built video the seams are exact.',
    ],
    more: [{ id: 'edit', title: 'Montage' }, { id: 'video', title: 'The «Video» screen' }],
  },

  'graph-view': {
    title: 'Help: the storyboard as a graph', icon: 'layers',
    lead: 'The same storyboard laid out by its links: what each scene is shot from and where it goes next. Links are edited right here: drag a scene\'s «frame» to the «start» of a later one, and it will begin from that frame; the scene\'s panel has «Start», takes and the scene\'s LoRA. Everything is saved to the storyboard at once. Text, people and camera are on the cards; «Copy as graph project» makes a separate graph project with branches and «Montage».',
    steps: [
      { title: 'Look over the graph', text: 'A long video opens on its first rows; the wheel zooms, dragging pans.' },
      { title: 'Click a node', text: 'Its links light up; on the right: the scene\'s video, start, who is in the shot, the prompt for the model, seed, key.' },
      { title: 'Drag a link', text: 'A scene\'s «frame» → the «start» of a later one: it will begin from that frame.' },
      { title: 'Open as a graph', text: 'A new graph project with the same scenes, taken from the cache.' },
    ],
    map: { cols: 'minmax(0, 1fr) minmax(8rem, 30%)', areas: ['canvas side'], zones: [
      { area: 'canvas', title: 'Canvas', text: 'Heroes, style and LoRA on the left; scenes in the middle, a chain per row; the join, music and output on the right.', deco: 'nodes' },
      { area: 'side', title: 'Panel', text: 'The selected node or the whole graph: legend, «Go to scene», «Copy as graph project».', accent: true },
    ] },
    sections: [
      { title: 'Links', icon: 'link', items: [
        'Last frame → the continuation\'s «start», in the chain\'s color.',
        'The hero\'s look → «who» of the scene that opens a chain; the photo for Ref2VA → «faces», as a yellow dashed line.',
        'Every scene → the join; style and LoRA apply to all scenes, so they have no links.',
      ] },
      { title: 'States', icon: 'clapper', items: [
        'The color of a node\'s header shows who works: «the model shoots», the writer, the join, you; the legend is in the panel.',
        'The same words as on the «Video» screen: «from cache», «93 s», «step 5/8», «waiting for frame».',
        '<b>will reshoot</b>: the scene changed after shooting; <b>in cache</b>: the frame is already shot, though there is no video yet.',
      ] },
    ],
    tips: ['«Go to scene» in the panel takes you to a scene by its number: handy in a video of 120 scenes.'],
    limits: ['Only what the storyboard has links for can be edited here: a scene\'s start, takes, LoRA. Branches, your own links and a montage node are in a graph project («Copy as graph project»).', 'A link only goes forward: a scene can start from the frame of an earlier one, not a later one.'],
    more: [{ id: 'graph', title: 'The storyboard graph' }, { id: 'graph-edit', title: 'Graph project' }],
  },

  'graph-edit': {
    title: 'Help: graph project', icon: 'layers',
    lead: 'A video made of nodes on a canvas: scenes, photos, LoRA, sound, joins, music and outputs, with any links. For branches and versions: two endings from shared scenes, a short and a long version, a scene starting from the frame of any other. Only what the outputs need gets shot.',
    steps: [
      { title: 'Add nodes', text: 'Select a node and a new one lands next to it and links itself. Or «Templates».' },
      { title: 'Watch «Next»', text: 'The node\'s panel shows its next step; what is missing shows as a badge on the card.' },
      { title: 'Link the ports', text: 'From an output on the right to an input on the left of the same color.' },
      { title: 'Shoot', text: '«Shoot all» on the right or «Shoot up to here» on a node.' },
      { title: 'Try variants', text: '«Another take», «Duplicate branch», several outputs.' },
    ],
    map: { cols: 'minmax(0, 1fr) minmax(8rem, 30%)', areas: ['tools side', 'canvas side'], zones: [
      { area: 'tools', title: 'Bar above the canvas', text: 'Videos, «Add», «Templates», «Whole graph», zoom, «Help», «Keys».' },
      { area: 'canvas', title: 'Canvas', text: 'Nodes and links. The header shows who works, a port what flows through it, the bottom the state.', deco: 'nodes' },
      { area: 'side', title: 'Panel on the right', text: 'The selected node: its fields and buttons. Nothing selected: the project: quality, «Shoot all», outputs, «Clear takes», «Build a storyboard».', accent: true },
    ] },
    cards: { title: 'Nodes', intro: 'The color is who works: purple is a video model, green the writer, blue the join and RTX, orange Krea 2, teal a clip remake, grey your data.', items: [
      { title: 'Idea', text: 'A couple of sentences for the writer.', color: WHO.user },
      { title: 'Hero', text: 'Look and photo; «Describe from photo».', color: WHO.writer },
      { title: 'Writer', text: '«Write», «Expand into scenes».', color: WHO.writer },
      { title: 'Prompt', text: 'Text or fields, as in the Lab; the heroes\' lines.', color: WHO.user },
      { title: 'Photo', text: 'A first frame or a face for Ref2VA.', color: WHO.user },
      { title: 'Picture', text: 'Krea 2 draws the first frame.', color: WHO.krea },
      { title: 'Scene', text: 'The graph\'s model: H3 up to 15 s, LTX up to 10, WAN up to 5; prompt, start, faces, LoRA.', color: WHO.h3 },
      { title: 'Video → video', text: 'A clip remade through a LoRA that reads the clip itself: remove the background, restore, replace the hero.', color: WHO.v2v },
      { title: 'Faces', text: 'Small, far faces in a shot scene made sharp and steady from frame to frame (Krea 2 + LTX 2.3).', color: WHO.facefix },
      { title: 'Frame', text: 'The last one or at any moment of the scene.', color: WHO.ffmpeg },
      { title: 'Scene sound', text: 'The sound of a shot scene: a voice for ID-LoRA or a track.', color: WHO.ffmpeg },
      { title: 'LoRA', text: 'A set with strengths, into the scenes.', color: WHO.user },
      { title: 'Join', text: 'Scenes in order, chain seams.', color: WHO.ffmpeg },
      { title: 'Montage', text: 'A join with an editor: trims, transitions, sounds.', color: WHO.ffmpeg },
      { title: 'Track and Music', text: 'Your own sound over the video; a track is also a voice sample.', color: WHO.ffmpeg },
      { title: 'Output', text: 'As shot, 1080p, 4K, HDR10, 48 fps.', color: WHO.ffmpeg },
      { title: 'Note and Group', text: 'Text on the canvas; a frame that carries nodes with it.', color: WHO.user },
    ] },
    keys: true,
    sections: [
      { title: 'Shooting', icon: 'clapper', items: [
        '<b>Shoot all</b> is one job: pictures, scenes (Ref2VA in a row), «Video → video», scene sound, frames, joins, music, outputs.',
        'An error stops only its own branch; the rest finish shooting.',
        'Edited a scene? It reshoots, along with everything that starts from its frame; neighboring branches don\'t.',
        'A scene has its own <b>Length</b>, from 3 s up to the model\'s limit: H3 15, LTX 10, WAN 5 (5 by default); the timeline of the prompt fields stretches to match.',
        'More than three continuations in a row with people and the scene shows «the face may drift»: start a new scene or connect the hero\'s photo to «faces».',
      ] },
      { title: 'Lines', icon: 'user', items: [
        'A «Prompt» has a «Lines» section: who (as named in the prompt: The heroine, Character 2, The man), how and what they say, in the video\'s language.',
        'A line goes into the timeline on its own row, the voice first in Audio; the scene\'s «Prompt with lines» shows what the model will get. WAN does not speak.',
        '<b>Suggest</b>: the writer reads the prompt and proposes lines. About 2 words per second of the scene.',
      ] },
      { title: 'Takes and branches', icon: 'shuffle', items: [
        '<b>Another take</b> shoots the scene with a different seed; the chosen take goes on, the others stay in the cache.',
        '<b>Duplicate branch</b>: a copy of the node and everything after it, with prompts: a second ending in one click.',
        '<b>Clear takes</b>: unchosen takes and leftover files go to the Windows Recycle Bin.',
      ] },
      { title: 'The writer in the graph', icon: 'spark', items: [
        'Works only on a button. When its inputs change, the node is marked «Rewrite».',
        '«Rewrite outdated» runs all such nodes in one job, so the model loads once.',
      ] },
      { title: 'Templates and JSON', icon: 'layers', items: [
        '«Templates» above the canvas: 16 built-in ones, from «Idea → writer → video» to «Trailer: five places», with a thumbnail of the graph and a note on what to do first; «Graph» among the ways to start on the home screen also comes from a template.',
        '«Save as template» and «Download as JSON»: the selected nodes or the whole graph; «Load from JSON»: the file becomes your template.',
        'Photos, tracks and the writer\'s output don\'t go into a template, only nodes, links and texts.',
      ] },
      { title: 'Storyboard ↔ graph', icon: 'film', items: [
        '«Copy as graph project» from a storyboard: the same keys, scenes from its cache.',
        '«Build a storyboard» from a straight graph: one output, one join, 5 s scenes. Ref2VA faces become heroes with photos, each scene with its own.',
      ] },
    ],
    tips: [
      'Start from a template: «Two endings», «Clip to your own track», «Dialogue of two». The links are already in place, and the template\'s note says what to change.',
      'Ctrl + Z undoes any edit, even deleting the whole graph.',
      'Until a scene\'s copy is changed, its key stays the same, so it is shot once.',
    ],
    limits: [
      'H3 was trained on 5–15 s scenes: 3–4 s will shoot, but that is outside what it knows.',
      'Describing the hero from a photo, writing, and suggesting lines happen only on a button.',
      'Only 5 s scenes carry over to a storyboard.',
    ],
    more: [{ id: 'graph-edit', title: 'Graph project' }, { id: 'graph-nodes', title: 'Graph nodes' }],
  },

  lab: {
    title: 'Help: the Lab', icon: 'flask',
    lead: 'One scene by hand, without a storyboard: try prompts, models, start frames, LoRA and length. Takes collect on the right by prompt, and a good one can be continued with the next scene.',
    steps: [
      { title: 'Write a prompt', text: '«Fields»: the scene in parts; «Text»: as a whole. «Preset ▾»: 16 ready prompts.' },
      { title: 'Translate', text: 'Writing in your own language? Use the «Русский» tab and «Translate to English».' },
      { title: 'Set up the shot', text: 'Model, start frame, length, format, quality, LoRA, seed.' },
      { title: 'Shoot takes', text: '«Shoot» or «Shoot on all models — compare»; takes on the right, «Continue from the last frame».' },
    ],
    map: { cols: 'minmax(0, 1fr) minmax(0, 1.25fr)', areas: ['sheet frame', 'sheet time', 'rack monitor'], zones: [
      { area: 'sheet', title: 'Scene prompt', text: 'English / Русский, Fields / Text, markup, parts, checks, «Expand».', accent: true },
      { area: 'frame', title: 'Frame', text: 'Model, format, quality, seed and start frame above it; a picture is dropped right into the frame.' },
      { area: 'time', title: 'Timeline and length', text: 'The timeline lines on the scene’s ruler; the length on the right.' },
      { area: 'rack', title: 'LoRA and «Shoot»', text: 'LoRA, how many takes, «Shoot» and the model comparison.' },
      { area: 'monitor', title: 'Takes', text: 'By prompt: hover to play, click to play in the frame; under a take: continue, repeat, download.', deco: 'takes' },
    ] },
    cards: { title: 'Preset ▾', intro: '16 whole prompts in groups, in the language of the open tab.', items: [
      { title: 'Basics', text: 'All parts empty, a hero, a continuation from a frame.' },
      { title: 'Speech', text: 'A line to the camera, a dialogue, a voiceover.' },
      { title: 'People and motion', text: 'Walking toward the camera, three in the shot, a dance.' },
      { title: 'Sounds and music', text: 'An explosion, a musician in the shot, background music.' },
      { title: 'No people', text: 'Nature, an object in close-up.' },
      { title: 'Style', text: '3D cartoon, old film.' },
    ] },
    sections: [
      { title: 'Prompt', icon: 'pen', items: [
        '<b>Fields</b>: style, place, camera, what happens second by second, sound; the timeline is counted for you.',
        'Yellow lines under a field say what to fix before shooting, each with its own button.',
        'A hero\'s line goes in quotes, with <code>in Russian:</code> (or your language) before it, and the hero says it in that language. H3 and LTX speak, WAN doesn\'t.',
      ] },
      { title: 'Model', icon: 'clapper', items: [
        '<b>Model</b> is who shoots; the prompt goes as written. Length is up to its limit: H3 15 s, LTX 10, WAN 5.',
        '<b>Shoot on all models — compare</b>: the same prompt and seed on every model whose weights are present, one take each, labeled with the model.',
      ] },
      { title: 'Takes and seed', icon: 'retake', items: [
        'The same prompt with the same seed gives the same take: keep the seed to see what an edit changes.',
        '«Repeat with seed»: edit the prompt and compare; «Continue from the last frame»: the next scene.',
      ] },
    ],
    tips: [
      'Shoot 2–3 takes of one prompt: the take changes noticeably with the seed.',
      'A start frame in the same shape as the frame: «Same as frame» in the format won\'t crop it.',
    ],
    limits: [
      'Translation takes the graphics card for the writer: the next take reloads the model, up to half a minute, depending on the model.',
      'H3 was trained on 5–15 second scenes; shorter can be shot, but it is outside what it knows.',
    ],
    more: [{ id: 'lab', title: 'Lab' }, { id: 'prompt', title: 'How to write a prompt' }, { id: 'prompt-parts', title: 'Prompt parts' }],
  },

  models: {
    title: 'Help: models and settings', icon: 'gear',
    lead: 'Weights of the video models (H3, LTX, WAN), Krea 2 and the writer, LoRA and tools. Everything is saved at once, no restart needed; a file you put in place by hand shows up on the page by itself.',
    steps: [
      { title: 'Open a model', text: 'What it can do, how long a scene takes here, the license and the weights by role; each shows where its file is.' },
      { title: 'Download what you need', text: 'In the background, one at a time; «Stop» and «Resume» from the same point.' },
      { title: 'Choose the writer', text: 'Default model, context, folders with GGUF.' },
      { title: 'Tools', text: 'The ComfyUI engine, Python, ffmpeg, RIFE, RTX Video: «Choose…» opens a Windows dialog, «As in .env» restores from the file.' },
    ],
    map: { cols: 'minmax(7rem, 26%) minmax(0, 1fr)', areas: ['nav card'], zones: [
      { area: 'nav', title: 'Sections', text: 'H3 video, Ref2VA, LTX 2.5, LTX 2.3, WAN 2.2 5B, Krea 2, writer, LoRA, tools.' },
      { area: 'card', title: 'The section\'s files', text: 'Name, size, where from (Hugging Face) and where to; «Download», «Use», «Remove» (to the Recycle Bin).', accent: true, deco: 'rows' },
    ] },
    sections: [
      { title: 'Downloading', icon: 'download', items: [
        'Files download one at a time; at the end the size is checked against Hugging Face.',
        '«Remove» sends the file to the Windows Recycle Bin rather than deleting it for good.',
        'The «Hugging Face token» in the «H3 video» section is only needed for gated models.',
      ] },
      { title: 'Video models', icon: 'film', items: [
        '«Unload» in a model\'s section frees video memory; the next shoot loads the model again.',
        'LoRA: for H3 the «LoRA» section, for LTX, WAN and Krea the folders in their sections. Put .safetensors files in the folder and they show up by themselves.',
        'FastWan is the same WAN 2.2 5B with the FastWan LoRA; its file is in the WAN section.',
      ] },
      { title: 'Writer', icon: 'spark', items: [
        'Models: every GGUF from LM Studio\'s downloads and from the folders on this page; the current one is chosen in the header.',
        '«sees photos»: the model can describe a hero from a picture.',
      ] },
    ],
    tips: ['The «where from» link on each file is its page on Hugging Face.'],
    limits: ['The H3 and Ref2VA files are 20 GB each: check your disk space before downloading.'],
    more: [{ id: 'models', title: 'Models and settings' }, { id: 'env', title: 'Settings in .env' }],
  },
}

// the montage's keys (views/EditView.vue), on the same sheet
export const EDIT_KEYS_EN: { title: string; icon: string; rows: [string, string][] }[] = [
  { title: 'Keyboard', icon: 'grip', rows: [
    ['Play / pause', 'Space'], ['Frame back / forward', '← / →'], ['Second back / forward', 'Shift + ← / →'], ['To start / to end', 'Home / End'],
    ['Split the clip at the playhead', 'S'], ['Copy a clip or sound', 'Ctrl + D'], ['Remove a clip, sound or seam transition', 'Delete'],
    ['Undo', 'Ctrl + Z'], ['Redo', 'Ctrl + Shift + Z'], ['Magnet to the track\'s beats', 'M'], ['Clear selection', 'Esc'], ['This sheet', '?'],
  ] },
  { title: 'Mouse', icon: 'expand', rows: [
    ['Trim the start or end', 'drag a clip\'s edge'], ['Move a chain', 'drag a clip'], ['Set up a seam', 'click the seam icon'],
    ['Play a seam', 'double-click the seam'], ['Playhead', 'click or drag on the ruler'], ['Time zoom', 'Ctrl + wheel'],
    ['Larger or smaller preview', 'drag the border above the timeline'],
  ] },
]
// the graph's keys sheet
export const GRAPH_KEYS_EN: { title: string; icon: string; rows: [string, string][] }[] = [
  { title: 'Keyboard', icon: 'grip', rows: [
    ['Select all', 'Ctrl + A'], ['Clear selection', 'Esc'], ['Delete selected', 'Delete'], ['Copy', 'Ctrl + C'],
    ['Paste', 'Ctrl + V'], ['Duplicate selected', 'Ctrl + D'], ['Undo', 'Ctrl + Z'], ['Redo', 'Ctrl + Shift + Z'],
    ['This sheet', '?'],
  ] },
  { title: 'Mouse', icon: 'expand', rows: [
    ['Zoom', 'wheel'], ['Pan the canvas', 'drag empty space'], ['Select several', 'Shift + box'],
    ['Add to selection', 'Ctrl + click'], ['Link ports', 'drag from an output to an input'], ['Move a group with its nodes', 'drag by the title'],
  ] },
]
