// The English help, part one: the worked example and the sections how … check of help.ts (same ids and order).
// Every <dt> keeps its Russian text in data-term, so the "?" buttons (HelpCard.vue) still find the entry.
import type { HelpSection } from './help'

// a "how it reads / how it works better" pair inside an entry
const ex = (worse: string, better: string, why?: string) => `<div class="ex"><div class="ex-w"><span>Worse</span>${worse}</div>
  <div class="ex-b"><span>Better</span>${better}</div>${why ? `<p class="ex-why">${why}</p>` : ''}</div>`

// the worked example: one idea through the whole app, the prompt taken apart line by line
export const HERO_EN = `
<h1>From idea to video</h1>
<p class="hero-lead">You write a couple of sentences — the Writer splits them into scenes (5 s each; 10 s each on LTX), code builds an English prompt for every scene, and the video model shoots the scenes in chains. Here is one idea all the way through, on H3.</p>
<ol class="flow">
  <li><b>Idea</b><p class="ru">A young barista closes a cozy café late at night. Rain is falling outside; she switches off the lights and smiles at her reflection in the glass.</p>
    <small>30 seconds → 6 scenes. Mood «Cinema», one hero.</small></li>
  <li><b>Scene 1 of 6</b> <span class="kind">new scene · 0:00–0:05</span>
    <p class="ru">The barista wipes the counter in the empty café; streetlights glow behind the wet window.</p>
    <pre class="beats">She wipes the wooden counter in slow circles.
She glances at the rain-streaked window.
She smiles softly to herself.</pre>
    <small>The description is for you. The action lines are what will be on screen.</small></li>
  <li><b>The prompt for H3</b> <small>built by code, not by the Writer: every line comes from its own place. LTX and WAN get the same words as one paragraph, in their own order</small>
    <figure class="anatomy" aria-label="What a prompt is made of">
      <div class="an" style="--c:#a855f7"><span class="an-l">Style<small>from «Mood»; shared by the whole video</small></span>
        <code>Cinematic live-action film, warm tungsten light against cool blue rain, shallow depth of field, subtle film grain.</code></div>
      <div class="an" style="--c:#ec4899"><span class="an-l">Heroine<small>the hero card — word for word in every scene</small></span>
        <code>The heroine (the same person in every shot): a 27-year-old woman with a dark bob, olive skin, brown eyes and a small mole on her left cheek. Wearing a mustard apron over a white shirt.</code></div>
      <div class="an" style="--c:#378ADD"><span class="an-l">Place<small>on a new scene; a continuation stays in the same place</small></span>
        <code>Scene: a small cozy café at night, warm pendant lights, rain on the large front window.</code></div>
      <div class="an" style="--c:#7F77DD"><span class="an-l">Camera<small>«Shot» and «Camera» in the inspector</small></span>
        <code>Camera: medium shot, slow push-in.</code></div>
      <div class="an" style="--c:#1D9E75"><span class="an-l">Timeline<small>«Action lines», by the second</small></span>
        <code>Timeline:
[0s-2s] She wipes the wooden counter in slow circles.
[2s-4s] She glances at the rain-streaked window.
[4s-5s] She smiles softly to herself.</code></div>
      <div class="an" style="--c:#eab308"><span class="an-l">Sound<small>«Music and sound» + the scene's sounds</small></span>
        <code>Audio: soft lo-fi piano. Rain tapping on the glass, a cloth squeaking on wood.</code></div>
      <div class="an" style="--c:#888780"><span class="an-l">Tail<small>always: keep the face, no text</small></span>
        <code>Keep her face, hair and outfit exactly the same. No text, subtitles, logos or watermarks.</code></div>
    </figure></li>
  <li><b>Video</b><p>30 s — two chains of three scenes. Scene 1 is shot from text, scenes 2–3 continue it from its last frame, scene 4 opens a new chain, 5–6 continue it. In an H3 draft that is about 1.5 minutes per scene; then the join with sound and, if chosen, 1080p or 4K.</p></li>
</ol>`

export const PART_A: HelpSection[] = [
  { id: 'how', group: 'Getting started', title: 'How it works', html: `
<p>A video is made in four steps, the same as in the header: <b>Idea</b>, <b>Storyboard</b>, <b>Video</b>, <b>Montage</b>.</p>
<dl>
<dt data-term="Идея">Idea</dt><dd>A couple of sentences in your own words, a photo if you like. The Writer — a local language model — splits the idea into scenes as long as the video model's scene: 5 s, 10 s on LTX.</dd>
<dt data-term="Раскадровка">Storyboard</dt><dd>Scenes can be edited, reordered, pinned and rewritten. Every edit is saved at once.</dd>
<dt data-term="Ролик">Video</dt><dd>The scenes are shot in chains by the video model — H3, LTX 2.5, LTX 2.3, WAN 2.2 5B or FastWan (<a href="#/help/video-models">«Video models»</a>) — and joined with sound; optionally 1080p or 4K, HDR10, 48 frames per second.</dd>
<dt data-term="Монтаж">Montage</dt><dd>The shot scenes on a timeline: trimming, transitions, speed, track and sounds, color. Nothing is reshot.</dd>
</dl>
<p>H3 and LTX make picture and sound in one pass: a scene sounds the way its <code>Audio:</code> line says. WAN shoots without sound.</p>
<p>The Writer and the video model don't fit into video memory together, so jobs run in a queue, one at a time. The video model starts by itself on the first shoot and stays in memory between scenes; after the Writer has worked or the model has changed, it loads again — up to half a minute.</p>
<p>Videos live in the <code>projects</code> folder. You can close the page in the middle of work — the result is saved to the project.</p>` },

  { id: 'header', group: 'Getting started', title: 'Header and status bar', html: `
<dl>
<dt data-term="Шаги">Steps</dt><dd>Idea, Storyboard, Video, Montage. Storyboard opens once a video is chosen; Video and Montage once the storyboard is written. On the graph and in the Lab, the screen's name stands in place of the steps.</dd>
<dt data-term="Сценарист">Writer</dt><dd>The button on the right: the model that writes the storyboard and describes photos. The list has every GGUF from LM Studio's downloads folder and from <code>models\\llm</code> — a model downloaded in LM Studio shows up by itself. «sees photos» means the model can describe a hero from a picture.</dd>
<dt data-term="Что делает видеокарта">What the GPU is doing</dt><dd>The bar under the header: who is working (the video model — a purple dot, the Writer — a green one), which scene and step, the percentage and how much is left. A click opens the details: the job, the queue, «Stop» and memory. When the GPU is free, «Unload model» is there too — it frees video memory for other programs; the next shoot loads the model again.</dd>
<dt data-term="ОЗУ и Видео">RAM and VRAM</dt><dd>Memory in use. The «RAM» bar turns yellow from 80 % and red from 92 %. The «VRAM» bar is split by owner, each in its own color: «Video model», the Writer, Remiqora Video itself, other programs.</dd>
<dt data-term="Модели, Лаборатория, Справка">Models, Lab, Help</dt><dd>Weights and folders, one scene by hand, and the help window: screens, the queue, a quick start. If the window is narrower than 1500 pixels, only the icons show (gear, flask, question mark), the name in a tooltip; that way the header fits on one line. On a phone the header scrolls up with the page. Every screen has its own help window — the «Help» button next to the title; this page is the full reference, the «Full help» button in that window.</dd>
<dt data-term="Боковая панель">Side panel</dt><dd>On the «Storyboard» and «Video» screens and on the graph, the panel with the fields can be moved, as in the Remiqora DAW: drag the six-dot handle at the top of the panel — the places «Left», «Right» and «Window here» appear; a click on the handle opens the same menu. A docked panel gets wider or narrower when you drag its edge (or click the edge and press <kbd>←</kbd> <kbd>→</kbd>; a double click restores the default width). A window moves by its handle and resizes by its lower right corner; the cross puts it back on the right. Place and size are remembered for each screen in this browser. On a narrow screen the panel sits below the content, as before.</dd>
</dl>` },

  { id: 'prompt', group: 'Prompts', title: 'How to write a prompt', html: `
<p>A prompt is the text the model shoots a scene from: what is seen, what happens, what is heard. In the storyboard, code builds it from the scene's fields; you don't need to write it. You write the prompt yourself in the Lab and in «Own prompt» mode — this section is for those. Ready prompts to copy are in «Presets».</p>
<div class="tip"><b>The formula in the «Prompts» sections is for H3:</b> the labels <code>Scene:</code>, <code>Camera:</code>, <code>Audio:</code>, a timeline by the second, the tail. LTX and WAN get your prompt reworked: without the line <code>Continue seamlessly from &lt;Picture 1&gt;.</code> and the <code>&lt;Picture N&gt;</code> labels, the timeline as one paragraph of sentences in order, without the «No text, subtitles…» tail (it makes LTX draw subtitles); WAN also without spoken lines and the <code>Audio:</code> line. Storyboard scenes on LTX and WAN get their own prompt, built from the same fields (the «Video models» section).</div>
<dl>
<dt data-term="Язык">Language</dt><dd>English: models understand it best. If English isn't your first language, write the scene in your own, run it through a translator and check it against the examples below. Only the words a character says out loud stay in your language (the «Speech and dialogue» section).</dd>
<dt data-term="Что видно и слышно">What is seen and heard</dt><dd>The model doesn't know the plot, the thoughts or the hero's past — only the picture and the sound of these seconds. Instead of a feeling, describe what the face and hands do.
${ex('She feels lonely and remembers her past.', 'She sits alone on a bench, looks down at an old photo and slowly wipes away a tear.',
  "A memory can't be filmed; a downward glance, a photo in her hands and a tear can.")}</dd>
<dt data-term="Конкретные слова">Concrete words</dt><dd>Object, color, material, time of day, weather — the more precise, the less the model makes up on its own.
${ex('a woman in a nice dress in a city', 'a woman in a long emerald silk dress on a wet cobblestone street at night, neon reflections in the puddles')}</dd>
<dt data-term="Длина сцены">Scene length</dt><dd>In the Lab, from 1 second up to the model's limit (H3 — 15, LTX — 10, WAN — 5); in the storyboard, 5 or 10 s, depending on the model. 5 seconds hold 1–3 simple actions. A story of five events is several scenes, not one long prompt.</dd>
<dt data-term="Длина промта">Prompt length</dt><dd>Usually 60–150 words. Longer is fine if every word is about the shot; retelling the plot and repeating yourself don't help.</dd>
<dt data-term="Возраст">Age</dt><dd>Only adult characters appear in Remiqora Video. State the age directly: <code>an adult woman, about 30</code>.</dd>
<dt data-term="Сид">Seed</dt><dd>The number the shoot's randomness depends on. The same prompt with the same seed gives the same take. To see what an edit does, change a word or two and shoot with the same seed — in the Lab that's «Repeat with seed».</dd>
<dt data-term="Запреты">Negatives</dt><dd>H3 has no separate "what not to show" field. A short negative at the end helps, but not always; describing what should be there is more reliable.
${ex('Scene: a street, no people, no cars.', 'Scene: an empty quiet street at dawn, closed shutters, wet asphalt.')}</dd>
</dl>` },

  { id: 'prompt-parts', group: 'Prompts', title: 'The parts of a prompt, in order', html: `
<p>A prompt is easiest to write in parts, each as its own paragraph, in the same order as in the breakdown at the top of the help. In the Lab, the field shows which parts are already there, and a click on a missing one inserts its template.</p>
<dl>
<dt data-term="Начало с кадра">Starting from a frame</dt><dd>Only if the scene starts from a ready picture: a continuation from the last frame, or a photo. The first line is <code>Continue seamlessly from &lt;Picture 1&gt;.</code> Then what starts now. Don't describe the place, the people and the light again: the picture sets them, and a description that differs from it (another place, another framing) leads to another scene. The line <code>Everything stays as in the picture: the same people, place, light, colours and framing.</code> is enough instead. A new scene from text doesn't need the «Continue seamlessly» line.</dd>
<dt data-term="Стиль">Style</dt><dd>What kind of film it is: live action or animation, light, color, lens, film stock. The same paragraph in every scene of the video. Styles H3 knows: <code>live-action</code>, <code>cinematic</code>, <code>2D-animated</code>, <code>3D CG</code>, <code>claymation</code>, <code>watercolor</code>, <code>vintage film</code>.
${ex('beautiful, high quality, 8k, masterpiece', 'Realistic live-action cinematic look, warm evening lamp light, shallow depth of field, film grain.',
  'Words of praise tell the model almost nothing; light, lens and film stock do.')}</dd>
<dt data-term="Герой">Hero</dt><dd>Age, hair, face, clothes. Repeat the description word for word in every scene: describe the clothes differently and they will change.</dd>
<dt data-term="Место">Place</dt><dd><code>Scene:</code> — where and when: a room or a street, weather, time of day, the main objects.
<pre class="ex-code">Scene: a small kitchen at dawn, rain on the window, a kettle on the stove.</pre></dd>
<dt data-term="Камера">Camera</dt><dd><code>Camera:</code> — shot size and movement: <code>Camera: close-up, slow push-in.</code> All the words are in the «Camera and light» section.</dd>
<dt data-term="Таймлайн">Timeline</dt><dd><code>Timeline:</code> — what happens second by second, one action per line. The segments follow each other and together make up the scene's length.
<pre class="ex-code">Timeline:
[0s-2s] She lifts the cup to her lips.
[2s-4s] She looks out of the window.
[4s-5s] She smiles.</pre></dd>
<dt data-term="Звук">Sound</dt><dd><code>Audio:</code> — H3 makes the sound together with the video. List the sounds of the place and the actions; describe music by instruments and tempo, not by mood.
${ex('Audio: epic emotional music.', 'Audio: slow solo piano with soft strings. Rain on the glass, a spoon clinking in a cup.')}
No music: <code>Audio: no music, only the natural sound of rain and footsteps.</code></dd>
<dt data-term="Хвост">Tail</dt><dd><code>Keep her face, hair and outfit exactly the same. No text, subtitles, logos or watermarks.</code> The first sentence helps continuations keep the hero, the second works against lettering in the shot.</dd>
</dl>` },

  { id: 'prompt-speech', group: 'Prompts', title: 'Speech and dialogue', html: `
<p>H3 and LTX can talk: voice, lip movement and sound are made together with the video. Speech comes out intelligible, Russian included (tested in the Lab on H3, LTX 2.5 and LTX 2.3). WAN doesn't talk: its spoken lines won't be heard. In the storyboard, lines are written under each character in the scene (inspector, «Lines»): code puts them into the timeline in the format below and adds the voices to the sound. «Suggest lines», in the same place, has the Writer propose them at the press of a button. In the Lab and in «Own prompt», you write the line right in the prompt.</p>
<dl>
<dt data-term="Как написать реплику">How to write a line</dt><dd>In the timeline: who speaks, in what voice, in what language, and the words themselves in quotes — in the language they should be spoken in. In the sound line: that a voice is heard.
<pre class="ex-code">[1s-4s] She speaks in a calm, warm voice, in English: "I knew you'd come back."

Audio: her clear calm voice speaking English, quiet room tone, no music.</pre></dd>
<dt data-term="Длина реплики">Line length</dt><dd>Normal speech is about 2–3 words per second. A 5-second scene holds a sentence of 6–10 words if you leave a second for a look and a pause; a 10 s scene, twice that. A sentence that's too long may get cut off or rushed — then split it across two scenes.</dd>
<dt data-term="Голос">Voice</dt><dd>Describe how the voice sounds: low, hoarse, a whisper, fast, with a smile.
${ex('She says: "Hi."', 'She whispers softly with a smile, in English: "Hi."')}</dd>
<dt data-term="Двое говорят">Two people talking</dt><dd>In turns, each line on its own timeline line. Name the speaker by a feature — <code>The man in the grey coat says…</code>, <code>The woman answers…</code> — so the lips move on the right person.</dd>
<dt data-term="Голос за кадром">Voiceover</dt><dd>If a narrator speaks and the hero's lips must not move: <code>says in an off-screen voiceover: "…" while her lips remain completely closed.</code> This is what the MiniMax guide recommends; it hasn't been tested in Remiqora Video yet.</dd>
<dt data-term="Формат MiniMax">MiniMax format</dt><dd>In the official guide, a line is written with the speaker's number and the language: <code>The woman (S1) says: &lt;d&gt;[English] I knew it.&lt;/d&gt;</code> You can try it in the Lab; the quotes format is tested here, this one isn't yet.</dd>
<dt data-term="Голос между сценами">Voice across scenes</dt><dd>Every scene is shot separately, and in the next one the voice may sound different. The same voice description in every scene helps; how well the voice holds along a chain hasn't been tested yet.</dd>
</dl>` },

  { id: 'prompt-sound', group: 'Prompts', title: 'Sounds and music', html: `
<p>H3 and LTX make the sound in the same pass as the picture, so the sound matches the action (WAN shoots without sound): a step with its thud, an explosion with its flash. Sound is set in two places: in a timeline line — for an event; in the <code>Audio:</code> line — for the whole scene. Full examples are in «Presets».</p>
<dl>
<dt data-term="Звук события">Event sound</dt><dd>Write it in the same timeline line as the event itself — that way it sounds at the right second.
<pre class="ex-code">[2s-3s] The glass slips from her hand and shatters on the stone floor with a sharp crash.</pre></dd>
<dt data-term="Фон сцены">Scene background</dt><dd>The <code>Audio:</code> line: place, weather, small sounds, 1–3 phrases. <code>Audio: steady rain on the roof, distant thunder, a dog barking far away.</code></dd>
<dt data-term="Громкие события">Loud events</dt><dd>An explosion, thunder, a blow — name the strength and character of the sound: <code>deafening boom</code>, <code>low rumble</code>, <code>sharp crack</code>, <code>metallic clang</code>, <code>crackling fire</code>.
${ex('There is an explosion.', 'A fireball hits the castle wall and explodes with a deafening boom; stones and sparks fly.')}</dd>
<dt data-term="Музыка за кадром">Background score</dt><dd>Only the viewer hears it. Describe the instruments, the tempo and how the volume changes, not the mood.
${ex('Audio: sad music.', 'Audio: a slow solo cello with soft piano chords, growing quieter toward the end.')}</dd>
<dt data-term="Музыка в кадре">Music in the shot</dt><dd>The characters hear it: a street musician, a radio, an orchestra. Write it as a timeline event, with its source: <code>[0s-5s] A street musician plays a fast flamenco melody on an acoustic guitar.</code> The sound line then says <code>no background score</code>, so the model doesn't add a score on top.</dd>
<dt data-term="Без музыки">No music</dt><dd><code>Audio: no music, only …</code> and list the sounds. Needed if you'll lay your own track over the video later.</dd>
<dt data-term="Тихая сцена">Quiet scene</dt><dd>Describe the silence with sounds: <code>quiet room tone, only her soft breathing and a clock ticking</code>.</dd>
<dt data-term="Музыка между сценами">Music across scenes</dt><dd>Every scene composes its own music, so the melody changes from scene to scene. One piece of music for the whole video is your own track in the storyboard (the «Quality, LoRA, music, output» section), with «No music in scenes» for the scenes.</dd>
</dl>` },

  { id: 'prompt-cast', group: 'Prompts', title: 'Several characters', html: `
<p>The model draws everyone you mention and easily mixes up who does what. The easier the characters are to tell apart, the less confusion. Full examples — «Three in the shot» and «Two-person dialogue» in «Presets».</p>
<dl>
<dt data-term="Сколько">How many</dt><dd>Two or three. The more people with their own actions, the more often the model mixes up who does what. Describe a crowd as background, without features: <code>blurred passers-by in the background</code>.</dd>
<dt data-term="Разные приметы">Distinct features</dt><dd>Sex, age, hair, clothing color — so the characters can't be confused.
${ex('a man and a woman', 'a tall bald man in a black leather jacket and a young woman with a red bob in a yellow raincoat')}</dd>
<dt data-term="Где кто стоит">Who stands where</dt><dd>Place the characters: <code>on the left</code>, <code>on the right</code>, <code>in the middle</code>, <code>in the foreground</code>, <code>in the background</code>. That makes it easier for each to stay in place.</dd>
<dt data-term="Кто что делает">Who does what</dt><dd>Start every timeline line with whoever acts, and call them by a feature: <code>The man in the grey coat…</code>, <code>The red-haired woman…</code>. The pronouns he and she confuse the model when two people are of the same sex.</dd>
<dt data-term="Только они">Only them</dt><dd>Add to the scene's place: <code>Only these two people are in the scene, nobody else.</code> — otherwise the model may add someone else.</dd>
<dt data-term="Кто говорит">Who speaks</dt><dd>Lines in turns, each with its speaker's feature and a voice description (the «Speech and dialogue» section).</dd>
<dt data-term="В раскадровке">In the storyboard</dt><dd>The «Several» mode on the Idea screen does this for you: each scene has «Who's in the scene» checkboxes, and only the looks of the checked characters go into the prompt.</dd>
</dl>` },

  { id: 'prompt-camera', group: 'Prompts', title: 'Camera and light: the words', html: `
<p>English words H3 understands. A movement can be refined by amplitude and speed — and written as a plain sentence: <code>The camera pushes in with small amplitude at slow speed toward her face.</code></p>
<dl>
<dt data-term="План">Shot size</dt><dd><code>extreme close-up</code> — a detail, the eyes; <code>close-up</code> — the face; <code>medium close-up</code> — chest up; <code>medium shot</code> — waist up; <code>full shot</code> — head to toe; <code>wide shot</code> — the person and the place around them.</dd>
<dt data-term="Камера стоит">Camera holds still</dt><dd><code>static shot</code> — gentlest on the face; good for spoken lines.</dd>
<dt data-term="Камера едет">Camera moves</dt><dd><code>push in</code> — toward the hero; <code>pull out</code> — away from the hero; <code>truck left</code> / <code>truck right</code> — sideways; <code>pedestal up</code> / <code>pedestal down</code> — up and down; <code>tracking shot</code> — following someone walking; <code>arc shot</code> — in an arc around the hero.</dd>
<dt data-term="Камера поворачивается">Camera turns</dt><dd>It stays in place and turns the lens: <code>pan left</code> / <code>pan right</code> — left and right; <code>tilt up</code> / <code>tilt down</code> — up and down; <code>zoom in</code> / <code>zoom out</code> — closer by the lens, without moving the camera.</dd>
<dt data-term="Особые">Special</dt><dd><code>the camera shakes slightly</code> — like handheld; <code>POV</code> — through the hero's eyes.</dd>
<dt data-term="Размах и скорость">Amplitude and speed</dt><dd><code>with small amplitude</code> / <code>with large amplitude</code>, <code>at slow speed</code> / <code>at fast speed</code>. Slow, small movement is more reliable: fast movement smears.</dd>
<dt data-term="Свет">Light</dt><dd><code>soft natural daylight</code>, <code>golden hour sunlight</code>, <code>warm lamp light</code>, <code>cold blue moonlight</code>, <code>neon lights</code>, <code>candlelight</code>, <code>backlight, silhouette</code>.</dd>
<dt data-term="Картинка">Picture</dt><dd><code>shallow depth of field</code> — blurred background; <code>film grain</code> — film grain; <code>high contrast</code> — hard shadows; <code>muted colors</code> — subdued color.</dd>
</dl>` },

  { id: 'prompt-mistakes', group: 'Prompts', title: 'Common mistakes', html: `
<dl>
<dt data-term="Несколько действий в строке">Several actions on one line</dt><dd>H3 spreads actions over the seconds when each is on its own line.
${ex('<code>She turns, then smiles and waves.</code>', '<code>[0s-2s] She turns to the camera.</code><br><code>[2s-4s] She smiles.</code><br><code>[4s-5s] She waves.</code>')}</dd>
<dt data-term="Ходьба без направления">Walking with no direction</dt><dd>${ex('<code>She walks down the street.</code>', '<code>She walks toward the camera down the street.</code>',
  'Without a direction the model often turns the person to face us but moves them away from the camera — the result is walking backwards.')}</dd>
<dt data-term="Надписи">Lettering</dt><dd>Signs, screens, letters, books — models often write gibberish on them. If you don't need lettering, don't mention objects with text. If you do — keep it short, in quotes: <code>a neon sign reading "OPEN"</code>; it won't always work.</dd>
<dt data-term="Лишние люди">Extra people</dt><dd>Every person you mention will appear in the shot. If there is one hero, add <code>Only she is in this scene, nobody else.</code> Describe a crowd as background: <code>blurred passers-by in the background</code>.</dd>
<dt data-term="Другое место в продолжении">A different place in a continuation</dt><dd>A continuation starts from the last frame — so it is in the same room. «She walks into another room» gives an abrupt jump in the middle of the scene; a new place is a new scene.</dd>
<dt data-term="Одежда меняется">Clothes change</dt><dd>If the clothes are described differently across scenes, or not at all, the model invents new ones. Copy the hero's description word for word.</dd>
<dt data-term="Быстрое движение">Fast movement</dt><dd>Running, fighting, dancing, an abrupt camera get smeared, especially in a draft. Slow the action down, or shoot it closer and shorter.</dd>
<dt data-term="Пустые слова">Empty words</dt><dd><code>epic</code>, <code>amazing</code>, <code>emotional</code>, <code>masterpiece</code> don't tell the model what to shoot. Replace them with light, movement and sound.</dd>
<dt data-term="Русские слова в тексте">Non-English words in the text</dt><dd>Write everything except the spoken words in English: the model understands a word in another language in the middle of English text worse, and in the storyboard a non-English word gets the «check» mark.</dd>
</dl>` },

  { id: 'prompt-recipes', group: 'Prompts', title: 'Presets', html: `
<p>The same full prompts as in the Lab's «Preset ▾» menu (there they are inserted directly, in English or in your language): copy one and adapt it — the hero, the place, the actions. «Line to camera» is tested in Remiqora Video; the rest are written from the MiniMax guide and our experience, and results may vary — shoot 2–3 takes and pick one.</p>
<dl>
<dt data-term="Герой в кадре">Hero in the shot</dt><dd>A new scene from text: a person, a place, three actions.
<pre class="ex-code">Realistic live-action cinematic look, golden hour sunlight, shallow depth of field, film grain.

Scene: an adult woman, about 30, with long wavy red hair and freckles, wearing a white linen shirt, stands on a wooden pier by a calm lake at sunset.

Camera: medium shot, slow push-in.

Timeline:
[0s-2s] She looks out over the water.
[2s-4s] She turns her head toward the camera.
[4s-5s] She smiles softly.

Audio: gentle acoustic guitar at a slow tempo. Water lapping against the pier, distant birds.

Keep her face, hair and outfit exactly the same. No text, subtitles, logos or watermarks.</pre></dd>
<dt data-term="Реплика в камеру">Line to camera</dt><dd>The hero speaks; the words in quotes are in the language he should speak.
<pre class="ex-code">Realistic live-action cinematic look, warm evening lamp light, shallow depth of field, film grain.

Scene: an adult man, about 40, with short grey hair and a trimmed beard, wearing a dark wool sweater, sits at a kitchen table at night.

Camera: medium close-up, static shot, his face clearly visible.

Timeline:
[0s-1s] He looks up at the camera.
[1s-4s] He speaks in a low, tired voice, in English: "Sit down. We need to talk."
[4s-5s] He folds his hands on the table.

Audio: his low calm voice speaking English, quiet room tone, a clock ticking, no music.

No text, subtitles, logos or watermarks.</pre></dd>
<dt data-term="Диалог двоих">Two-person dialogue</dt><dd>Length 8 s. The characters differ by clothes and by place in the shot, the lines come in turns, each with the speaker's feature.
<pre class="ex-code">Realistic live-action cinematic look, soft window daylight, shallow depth of field, film grain.

Scene: a small café by a big window. On the left, an adult man, about 35, with short black hair and a grey wool coat. On the right, an adult woman, about 30, with a red bob and a yellow raincoat. They sit across a small table with two cups of coffee. Only these two people are in the scene, nobody else.

Camera: medium shot, static shot, both faces clearly visible.

Timeline:
[0s-3s] The man in the grey coat leans forward and says in a low calm voice, in English: "So you came after all."
[3s-4s] The red-haired woman looks at him and smiles.
[4s-7s] The red-haired woman answers in a soft amused voice, in English: "I promised, didn't I?"
[7s-8s] The man in the grey coat laughs quietly.

Audio: two voices speaking English, quiet café chatter in the background, cups clinking, no music.

No text, subtitles, logos or watermarks.</pre></dd>
<dt data-term="Трое в кадре">Three in the shot</dt><dd>No speech: each has their own features, place and action.
<pre class="ex-code">Realistic live-action cinematic look, golden hour sunlight, film grain.

Scene: a sunny park meadow. On the left, an adult woman, about 25, with long blond braids and a white sundress. In the middle, an adult man, about 30, tall, with a shaved head and a green T-shirt. On the right, an adult woman, about 40, with short curly grey hair and a denim jacket. Only these three people are in the scene, nobody else.

Camera: full shot, static shot.

Timeline:
[0s-2s] The man in the green T-shirt throws a red frisbee to the left.
[2s-4s] The blond woman in the white sundress jumps and catches it.
[4s-5s] The grey-haired woman in the denim jacket claps and laughs.

Audio: a light ukulele at a cheerful tempo. Birds, laughter, the whoosh of the frisbee.

No text, subtitles, logos or watermarks.</pre></dd>
<dt data-term="Взрыв и эффекты">Explosion and effects</dt><dd>Each event's sound in its own timeline line, no music.
<pre class="ex-code">Epic fantasy film look, dramatic dusk light, smoke and embers, high contrast.

Scene: a stone castle wall at dusk, burning torches along the battlements. An adult knight in dented steel armor and a helmet stands on the wall with a round shield.

Camera: wide shot, the camera shakes slightly.

Timeline:
[0s-2s] The knight raises his shield and looks up at the sky.
[2s-3s] A fireball hits the wall below him and explodes with a deafening boom.
[3s-5s] Stones and burning sparks fly through the smoke as the knight crouches behind his shield.

Audio: no music. A low rumble before the impact, a deafening explosion, falling stones, crackling fire and the clang of metal.

No text, subtitles, logos or watermarks.</pre></dd>
<dt data-term="Музыкант в кадре">Musician in the shot</dt><dd>Length 8 s. The hero plays the music, everyone in the scene hears it; there is no background score.
<pre class="ex-code">Realistic live-action cinematic look, warm streetlights at night, shallow depth of field, film grain.

Scene: a narrow old-town street at night, wet cobblestones. An adult man, about 50, with a grey beard and a black hat sits on a stool and plays an acoustic guitar. Passers-by walk past, blurred in the background.

Camera: medium shot, a slow arc shot around the musician.

Timeline:
[0s-5s] The musician plays a fast flamenco melody, his fingers moving quickly over the strings.
[5s-8s] He slaps the guitar body twice in rhythm and smiles.

Audio: the loud acoustic guitar of the street musician, footsteps on wet stones, distant voices, no background score.

No text, subtitles, logos or watermarks.</pre></dd>
<dt data-term="Музыка за кадром">Background score</dt><dd>Music by instruments, tempo and volume; the sounds of the place after it.
<pre class="ex-code">Realistic live-action cinematic look, sunrise light, warm haze, film grain.

Scene: an empty desert road at sunrise, a red vintage car drives toward the camera, dust rising behind it.

Camera: wide shot, a slow pull out as the car approaches.

Timeline:
[0s-3s] The red car drives along the road toward the camera.
[3s-5s] The car passes close by the camera and leaves a cloud of dust.

Audio: a slow synthesizer pad joined by a steady electronic drum beat that gradually gets louder. The car engine hums, gravel crunches under the tires, the wind whistles.

No text, subtitles, logos or watermarks.</pre></dd>
<dt data-term="Продолжение с кадра">Continuation from a frame</dt><dd>The start frame is the last frame of the previous take («Continue from the last frame» under the take).
<pre class="ex-code">Continue seamlessly from &lt;Picture 1&gt;.

Realistic live-action cinematic look, golden hour sunlight, shallow depth of field, film grain.

Scene: the same wooden pier at sunset, the same woman in the white linen shirt.

Camera: medium shot, static shot.

Timeline:
[0s-3s] She sits down on the edge of the pier.
[3s-5s] She dips her bare feet into the water.

Audio: gentle acoustic guitar at a slow tempo. Soft splashing, distant birds.

Keep her face, hair and outfit exactly the same. No text, subtitles, logos or watermarks.</pre></dd>
<dt data-term="Природа">Nature</dt><dd>A landscape without people: fog, sunbeams, an animal in the distance.
<pre class="ex-code">Cinematic nature documentary look, soft morning light, high detail.

Scene: an empty pine forest at dawn, thick fog between the trees, sunbeams breaking through the branches.

Camera: wide shot, a slow tracking shot forward between the trunks.

Timeline:
[0s-3s] The sunbeams slowly brighten through the fog.
[3s-5s] A deer steps out from behind a tree in the distance.

Audio: no music, only birdsong, a light breeze in the pines and a twig cracking.

No text, subtitles, logos or watermarks.</pre></dd>
</dl>
<p>Seven more presets — only in the Lab's «Preset ▾» menu:</p>
<dl>
<dt data-term="Все части, пустые">All parts, empty</dt><dd>A prompt skeleton: every part with «...» to fill in.</dd>
<dt data-term="Голос за кадром">Voiceover</dt><dd>8 s. A woman narrator speaks, the heroine's lips stay closed (the «Speech and dialogue» section).</dd>
<dt data-term="Идёт к камере">Walking to camera</dt><dd>The camera backs away in front of the hero; night, rain, neon.</dd>
<dt data-term="Танец для клипа">Dance for a clip</dt><dd>A stage, light, haze, the camera circling, a beat.</dd>
<dt data-term="Предмет крупно">Product close-up</dt><dd>An ad: studio light, the camera circling, a drop.</dd>
<dt data-term="3D-мультфильм">3D cartoon</dt><dd>Animation instead of live action.</dd>
<dt data-term="Старая плёнка">Old film</dt><dd>The 1970s: faded colors, grain, flicker.</dd>
</dl>` },

  { id: 'idea', group: 'Idea', title: 'The «Idea» screen', html: `
<dl>
<dt data-term="Идея">Idea</dt><dd>In your own words: who, where, what happens and how it ends. The Writer holds on to concrete details — the place, the time of day, the clothes, a gesture at the end.
${ex('A girl takes an evening walk.', 'A girl in a red coat walks along a riverside promenade at night in the rain, stops under a streetlight and smiles at the camera.',
  'In the second version the Writer has a place, light, weather, clothes and an ending — the scenes will hang together.')}</dd>
<dt data-term="Фото">Photo</dt><dd>Optional (png, jpg, webp). After uploading, choose what to do with it.
<br><b>First frame</b> — the video will start exactly from this picture: the video model brings it to life, and the Writer first describes what's in the photo (pose, place, light) and continues the action from that moment.
<br><b>Look only</b> — the Writer describes the hero in words, the scenes are shot from text, the photo doesn't get into the shot.
${ex('A vertical phone photo for a 16:9 video — the edges get cropped, the head may go out of frame.', 'A picture of the same shape as the video frame; if the shapes differ, press «Use 9:16» in the warning.')}</dd>
<dt data-term="Модель">Model</dt><dd>Who will shoot: H3 (speech in the video's language, faces from a photo), LTX 2.5 (fast, its own sound), LTX 2.3 (can shoot to your track — clips), WAN 2.2 5B or WAN 2.2 5B · FastWan (picture only). What each can do — the table in <a href="#/help/video-models">«Video models»</a>. You can change it later too, in the storyboard, and per scene.</dd>
<dt data-term="Длина">Length</dt><dd>From 15 seconds to 10 minutes. The video is split into 5 s scenes: 30 s is 6 scenes. On LTX the scenes are 10 s: 30 s is 3 scenes, 15 s is 10 + 5. Shooting time depends on the model: a 30 s draft takes about 10 minutes on H3, 3.5–4 on LTX, about 12 on WAN.</dd>
<dt data-term="Кадр">Frame</dt><dd>16:9 — horizontal, 9:16 — vertical for phones, 1:1 — square. The size in pixels differs by model: a 16:9 draft is 960×544 on H3, 1024×576 on LTX (the table in «Video models»).</dd>
<dt data-term="Настроение">Mood</dt><dd>Cinema, Clip, Ad, Fantasy and effects, Documentary. Sets the style of the whole video: light, color, pace, camera.</dd>
<dt data-term="Кто в кадре">Who's in the shot</dt><dd><b>One hero</b> — one person in every scene.
<br><b>Several</b> — 2–3 people, each scene with its own cast.
<br><b>No people</b> — landscapes, objects, effects. Instead of a hero the Writer describes a «world», and each scene starts where the previous one ended.</dd>
<dt data-term="Музыка и звук">Music and sound</dt><dd>What the model itself should compose, e.g. «warm ambient, soft piano» (WAN makes no sound). Empty — only the scene's sounds. Every scene has its own music, so the melody changes from scene to scene; one piece of music for the whole video is your own track (the <a href="#/help/shoot">«Quality, LoRA, music, output»</a> section).</dd>
<dt data-term="Расписать сцены">Write the scenes</dt><dd>Creates the video and starts the Writer: 20–30 s per 30 s of video, a little longer with a photo. The storyboard opens right away and fills in when the Writer is done.</dd>
<dt data-term="Без сценариста">Without the Writer</dt><dd>The «Own prompts» switch above the form: an empty storyboard of the length you need, with no language model. You write each scene's prompt yourself, in English; H3 gets it word for word, LTX and WAN without the H3 markup (the <a href="#/help/prompt">«How to write a prompt»</a> section).</dd>
<dt data-term="Как начать">How to start</dt><dd>Above the form — four ways: «Writer» (an idea in your words), «Clip» (from a song, the «Clip from a song» section), «Own prompts» (an empty storyboard) and «Graph» (a canvas of nodes; «Choose a template» opens the templates window, with an empty canvas there too).</dd>
<dt data-term="Ваши ролики">Your videos</dt><dd>All projects; on top — search by name and filters: kind (storyboards, clips, graphs), models (several allowed — a video matches if at least one of its scenes was shot by a chosen model), frame, state (done, not shot, check scenes, unfinished, in progress now) and order (modified, created, longest, by name). Each option shows how many videos it would leave; the choice is remembered, «Reset» brings everything back. On a phone the filters are behind the «Filters» button.
The card shows the kind's icon (film — storyboard, note — clip, layers — graph) and the state: «Writer is writing…», «shooting…», «check 2» — two scenes have remarks, «not shot», «done» with the size; for a graph — «building…», «done» or «not built». «In progress now» is a video with any work going on: the Writer writing, scenes or takes being shot, a graph being built. The strip under the frame shows the models that shot the video, each as long as its share of scenes (purple — H3, terracotta — LTX 2.5, ochre — LTX 2.3, green — WAN, light green — FastWan); a vertical video is shown whole, on its own blurred background. «from Remiqora» is a clip carried over with its shot scenes from the old Remiqora (the remiqora-video-old folder). The trash can in the corner deletes the whole video.</dd>
</dl>` },

  { id: 'clip', group: 'Idea', title: 'Clip from a song', html: `
<p>The second switch on the main screen is «Clip». Scenes are cut not by 5 s but by the song's bars, and the Writer writes along its parts.</p>
<dl>
<dt data-term="Песня">Song</dt><dd>An uploaded song is analyzed right away (about a second): tempo, bars, parts — quiet (intro, verse, break) and loud (drop, chorus). On the waveform the loud parts are highlighted, the chorus with a pink line on top, the sung lines with marks below. A click on the waveform starts the clip from the nearest bar. «Listen» next to the name plays the stretch the clip takes — a white mark runs along the waveform; while it plays, a click inside the frame seeks there, and outside it moves the clip start to that bar; «Stop» stops it. A song is stored once, however many clips you make from it.</dd>
<dt data-term="Слова">Lyrics</dt><dd>Recognized from the song itself: the voice is separated (Demucs), the words are transcribed with each word's timing (Whisper large-v3) — a GPU job, about 40 s; it runs by itself before the Writer, or in advance with the «Recognize lyrics» button. You can fix the recognized words in the field and press «Save my text»: it is laid onto the timing of the recognized words, even with different line breaks. The chorus is found by repeated lines.</dd>
<dt data-term="Сцены по тактам">Scenes by bars</dt><dd>Each part of the song is a cut. Within a part, scenes run for whole bars: about 3 s in a loud part, twice that in a quiet one; no shorter than 1.5 s and no longer than 8 s (and no longer than the model shoots: 5 s for WAN). A scene is shot a little longer — up to the model's frame-grid step — and in the montage is cut exactly to its bar. In clips made since 30.10.2026 a scene from a first frame is also shot 8 frames before its bar (to the track — from that same place of the song), and those frames are cut: the first frames of such a scene are an almost still picture, and every cut showed «a photo, then it moves».</dd>
<dt data-term="Типы сцен">Scene types</dt><dd><b>Singing</b> — the hero sings, face close-up; only where the voice is heard, and the line is the words sung in those seconds (delivery «sings»). <b>Performance</b> — movement to the music. <b>Insert</b> — a detail without a face: hands, light, smoke, fabric. In singing and performance the hands stay empty and below the shoulders: no waving, no arms above the head, nothing in the hands, no spinning — the video models smear the hands and what they hold. The movement is a sway, a turn of the head, the shoulders, the hair in the wind, a step toward the camera; a scene with such hands goes back to the writer to fix.</dd>
<dt data-term="Идея клипа">Clip idea</dt><dd>Optional. The Writer first writes a treatment — the format, the palette, a motif that grows toward the chorus, and what happens in each part — then the scenes. Key words of a line are taken literally.</dd>
<dt data-term="Длина клипа">Clip length</dt><dd>Buttons under the waveform: «30 s», «45 s», «1 min», «1.5 min», «Whole song». Next to them — the stretch of the song and roughly how many scenes it will make (about one per 4 s). If it doesn't fit before the end of the song, the start moves back.</dd>
<dt data-term="Кто в кадре">Who's in the shot</dt><dd>As on the Idea screen: one hero, several or no people.</dd>
<dt data-term="Что пишет сценарист">What the writer writes</dt><dd><b>The hero's look</b>: «Writer» invents it, «I'll describe it» is your text (and the hero's gender) that the Writer only translates for the model, «From a photo» — the Writer describes the look from the singer's photo, and the singing scenes start from that face. <b>The clip's story</b>: «Writer» invents a story over the song's parts, «My idea as it is» takes your idea with nothing invented (then the idea is needed). <b>Scene texts</b>: «All» — the Writer writes the whole clip at once; «Only the empty ones» and «None: a skeleton» — the Writer isn't started, the clip's skeleton opens. Everything written can be edited in each scene later.</dd>
<dt data-term="Каркас клипа">The clip's skeleton</dt><dd>On the storyboard, «Show» → «Skeleton» (a clip with no written scenes opens in it by itself): every scene along the song — its time, part, the words sung in it, its type and who wrote it («you», «writer», «empty»). Your own text makes a scene yours and pins it: the Writer won't rewrite it, only turns your words into the prompt. A type picked here stays yours too. «Write the rest» — the Writer writes the empty scenes leaning on yours, the first time also the story, the hero and the style.</dd>
<dt data-term="Кадр">Frame</dt><dd>16:9, 9:16 or 1:1 — as on the Idea screen.</dd>
<dt data-term="Расписать клип">Write the clip</dt><dd>Creates the clip and starts the Writer (or, with «Only the empty ones» and «None», opens the skeleton right away); the estimate goes by the Writer's speed on this computer, plus 40 s if the lyrics aren't recognized yet. The storyboard opens right away.</dd>
<dt data-term="Модель">Model</dt><dd>LTX 2.3 hears its piece of the track and syncs the lips to the voice — that's why it shoots clips by default. If you choose another (H3 — faces from a photo, LTX 2.5 — faster, WAN — no sound), the singing scenes are still shot by LTX 2.3 (the scene's «Model»); the form says so below. The video's sound is the song itself; the scenes' own sound is off.</dd>
</dl>` },

  { id: 'look', group: 'Storyboard', title: 'Heroes: casting, style and Ref2VA', html: `
<dl>
<dt data-term="Название">Title</dt><dd>On the «Shooting» tab, at the top; click it (there's a pencil next to it) to change it. Under it — a line like on a clapperboard: how many scenes, length, frame, mood, how many people and how long the Writer took to write the script.</dd>
<dt data-term="Переписать незакреплённые">Rewrite unpinned</dt><dd>In the «Script» view (above the scenes: «Show» → «Script»), above the list of scenes, with the Writer's icon and the number of scenes without a lock. The Writer rewrites every scene without a lock; pinned ones stay and serve it as anchors. With more than three scenes it asks first.</dd>
<dt data-term="Добавить сцену">Add scene</dt><dd>In the «Grid», at the end of every episode — the «+ Scene» tile: a continuation in this episode (it starts from the last frame of the scene before it), and under it «+ New episode after» — a scene with its own first frame and place. In the «Script» — «Add scene»: a continuation after the selected one. The Writer writes the new scene from its neighbours right away. In a clip the new scene takes the second half of the scene before it (on the nearest bar), and the song's words are shared between them — the other scenes keep their place in the song; a scene shorter than 3 s can't be split so, pick another.</dd>
<dt data-term="Кастинг">Casting</dt><dd>The «Heroes» tab: the heroes on the left (when there are several; «Add a hero» is there too, up to three), the approved portrait big in the middle, beside it the gender, age, look and outfit — all edited in place. The words of the look and the outfit go into every scene <b>word for word</b> — they are what holds the face from scene to scene. Edited the look after the portrait? The portrait gets a yellow mark and the line «the portrait shows another look» with «Draw from the look»: the writer translates the look, Krea draws four new faces. With no people, the «world» stands instead of the heroes.
${ex('a woman with brown hair', 'a 27-year-old woman with a dark chin-length bob, olive skin, brown eyes and a small mole on her left cheek',
  'The more features, the less the face changes between new scenes. The remark «described too briefly» is about the same thing.')}</dd>
<dt data-term="Поправить черты">Adjust features</dt><dd>Same face, one detail changes. Pick features — age, hair, smile, makeup, light — or write your own change («red shoulder-length hair»), then «Draw 2 tries». FLUX.2 Klein edits the approved portrait itself, so the face holds, an own photo included; without FLUX.2 Krea draws on the portrait's seed. Your own change goes into English by the writer first. The try you approve adds the change to the look (not the light: that is for the tries only). About 30–60 s.</dd>
<dt data-term="Другой человек">Another person</dt><dd>A new face — the hero's scenes will be reshot. «New faces from this look»: four Krea 2 tries from the look, the outfit, the video's style and the place of the hero's first scene (an edited look is translated by the writer first). «Describe anew»: edit the look above, then «Draw from the look». «Own photo»: your picture becomes the portrait; «Describe from photo» rewrites the look from it.</dd>
<dt data-term="Пробы">Tries</dt><dd>Every try stays in the project. A click on a try compares it with the approved portrait: before, after and what is added to the look; «Approve» makes it the portrait (the one before stays among the tries; a new face asks first), «Remove the try» or the cross drops it. A try where the detector found two people or no face is framed yellow: Krea sometimes draws a second figure behind the hero. On H3 Ref2VA holds the face by the portrait, in a clip the singing scenes start from it, FLUX.2 Klein draws the scenes' frames from it.</dd>
<dt data-term="В сценах">In the scenes</dt><dd>Under the tries — the shot scenes with the hero and how close the face on each one's last frame is to the portrait (SFace). Below the line — «another face» in a yellow frame: reshoot that scene or draw it a frame. «No face seen» — the hero has their back to us or is far away. A click opens the scene.</dd>
<dt data-term="Все поля и EN">All fields and EN</dt><dd>Under the look and in the «Voice» row («Set up») — the full form: the hero's voice, the photo, the look in English as it goes to the model, «Update the prompt from the text». In «Several» mode a hero is removed with «Remove» next to their name. After an edit of the look, the hero's scenes are reshot.</dd>
<dt data-term="Фото героя">Hero photo</dt><dd>Every hero can have their own photo. «Describe from photo» — the Writer describes the face, hair, sex and age in ~10 s; the outfit stays yours. The photo itself doesn't change the description until you press the button.</dd>
<dt data-term="Нарисовать кадры всем сценам">Draw frames for all scenes</dt><dd>For every new scene with a hero who has a photo, FLUX.2 Klein draws the first frame: their face from the photo in the scene's place, with the scene's framing and first action (about 5 s a frame, the model loaded once). The scenes start from these frames — the face and the place hold from the first frame instead of being invented by the video model anew. A frame already there is replaced, and those scenes are shot anew. The clip wizard draws the frames itself, right after the singer's portrait. FLUX.2 Klein's first reference is the face cut out of the portrait, the second the whole portrait, the third the place; the hero's outfit goes into the frame's prompt word for word. When the face on the frame doesn't look like the hero, more seeds are tried a step closer (wide → medium → close-up), the best frame stays and the scene takes its framing. A frame that never got alike is marked «the frame is not like the hero» on the card and in «Before shooting».</dd>
<dt data-term="Перерисовать непохожие">Redraw the unlike ones</dt><dd>A button on the hero's tab and in «Before shooting»: the scenes whose frame doesn't look like the hero are drawn again in one job. A new frame stays only when its face is closer to the hero's photo, otherwise the old one stays. The clip wizard does this step itself, after the frames.</dd>
<dt data-term="Места">Places</dt><dd>A picture of each place of the video: the flat, the street, the roof. A scene's frame is drawn with it as the second reference after the hero's photo, so the place stays the same from scene to scene while each scene has its own camera in it; without a picture FLUX.2 Klein draws the place from the words anew every time. «Gather places»: the writer sorts the new scenes into 2–6 places and describes each as an empty set (in English, for the model; edited under «Edit»). «Draw»: Krea 2 paints the place empty, with nobody in it (about 5 s); «Another one» draws another; «Own photo» puts your picture in place of the drawn one. A scene's place is picked in its panel («Place»). The places themselves change no shot; the frame drawn with them does: after a new picture of a place, draw its scenes' frames again. The clip wizard gathers and draws the places itself, before the frames (the «Places» box in the wizard). The «Draw the scenes' frames in the places' pictures» box turns them off: the frames are drawn from the words again, the places and pictures stay.</dd>
<dt data-term="Голос героя">Hero's voice</dt><dd>A sample of 5–10 s of clean speech: «File», «Record voice» from the microphone, or «From a scene…» — the voice of a shot scene without music and noise (Demucs, about a minute on the GPU). «Sample from» and «Length» set which piece to take. Scenes on LTX 2.3 (not to a track) where only this hero speaks are shot with ID-LoRA in this voice; under the sample you can see how many such scenes there are. Changing the sample reshoots them.</dd>
<dt data-term="Держать лицо по фото">Keep the face from the photo</dt><dd>Ref2VA: new scenes are shot by a separate model that uses the hero's photo as the face reference. Only for H3 scenes: LTX and WAN scenes don't keep a face from a photo. Visible if the video has a photo. The model also picks up the surroundings from the picture.
${ex('The heroine in profile against a lavender field — the face is hard to see, and the field will turn up in every scene.', 'A frontal portrait, the face large, even light, a neutral background.')}</dd>
<dt data-term="На всех сценах">In all scenes</dt><dd>An experiment, off by default. Ref2VA shoots continuations too: the last frame is pinned as the first, and the face is checked against the photo every time. The face holds longer, but the head may drift out of the frame. Switching it reshoots the whole video.</dd>
</dl>` },

  { id: 'timeline', group: 'Storyboard', title: 'Screen, episodes and chains', html: `
<p>On top — the tabs: «Scenes», «Heroes», «Places», «Song» (in a clip) and «Shooting»; under each name, what is in it: how many scenes and episodes, heroes, places, and for «Shooting» its length, frame and model. On the right — how many scenes are shot, as a bar, and the one main button: shoot what is left, or open the finished video. To the right of the scenes — the selected scene's panel (the «Scene panel» section). Any picture of the project — the hero's portrait, the tries, the places, a scene's first and last frame — opens big by a click (a try by the ⤢ button in its corner): in the window ← → go through all the project's pictures, a strip of them below, Esc closes it.</p>
<dl>
<dt data-term="Показать">Show</dt><dd>Above the scenes: «Grid» — all the scenes as cards by episode (opens first); «Frame» — the selected scene big, its take playing; «Script» — all the scenes as text, with search and filters; «Graph» — the same scenes as nodes on a canvas.</dd>
<dt data-term="Эпизод">Episode</dt><dd>A row of the grid is one chain: a new scene and the continuations after it, shot as one piece, frame after frame. In the margin — the episode's number, what it is about (from the Writer's plan), its time and how many of its scenes are shot; a click on the margin picks all its scenes.</dd>
<dt data-term="Почему в клипе сцены списком">Why a clip's scenes form a list</dt><dd>In a clip the Writer cuts the scenes on the song's beats, and nearly every one starts from a frame of its own: a new angle, a cut on the beat. Then every scene is a chain of its own, an episode of one scene, and the grid reads as a list: a number in the margin and one card beside it. In a storyboard with continuations, where a scene goes on from the last frame of the one before, a chain's scenes stand in a row. For example, a clip of 12 scenes is 12 episodes of one card, while the storyboard «A walk among blue flowers» of 6 scenes is 2 episodes of three. It is not a fault: this is how the grid shows the scenes are shot apart.</dd>
<dt data-term="Новая сцена">New scene</dt><dd>Shot from text, in its own place; opens a chain. Between chains — an ordinary edit cut.</dd>
<dt data-term="Продолжение">Continuation</dt><dd>Shot from the last frame of the previous scene: the same place, the same moment, as if the camera never stopped.
${ex('In a continuation: «She walks into a different room.» — the model will make an abrupt jump in the middle of the scene.', 'A new place is a new scene; in a continuation the action goes on in the same place.')}</dd>
<dt data-term="Правило цепочек">Chain rule</dt><dd>With people — no more than three continuations in a row, then a new scene: otherwise the face slowly drifts. 10 s scenes (LTX) — no more than one: the chain is also about 20 s. With no people the whole video is one chain.</dd>
<dt data-term="Полоса внизу">The strip at the bottom</dt><dd>With «Grid» — the video's map: the episodes as a strip, the selected scene's episode framed; a click or a drag goes to the scene at that point. With «Frame» and «Script» — the track: each scene as long as its time, a chain's scenes close together. A long video's track has two floors: on top the whole video with a frame round the part shown, below that part big; browse it with the wheel, the ← → arrows at its edges and by dragging the frame. A double click on a scene opens «Scene in detail».</dd>
<dt data-term="Точка на карточке">Dot on the card</dt><dd>A yellow dot — the scene has a remark (the «The «check» mark» section).</dd>
<dt data-term="Цвета">Colors</dt><dd>On the track and the map, purple and pink simply alternate so neighboring chains stand apart; the chain's number doesn't matter. The cards have no color: a purple frame is the selected scene.</dd>
</dl>` },

  { id: 'cards', group: 'Storyboard', title: 'Cards and what to do with scenes', html: `
<dl>
<dt data-term="Как устроена">How a card is built</dt><dd>The scene's frame — the last one of the latest shoot; a scene not shot yet shows its first frame tagged «start» if it has one, otherwise hatching. The «reshoot» tag — the scene changed after it was shot: you see the old frame, and it is shot again next time. Its number and length, under it two lines of what happens and who wrote them: «you» or «writer». ▶ in the middle of a shot card plays the chosen take right there, with sound; a click on the video pauses it. ⤢ in the card’s corner or Space opens the scene big in a window: the take with sound or the frame, «Take / First frame», ← → to the scenes beside it, «In detail» — the whole page, Esc closes it. The «faces not fixed» tag — the scene has its faces fixed after the shot, but the take came from «Another take»: you see and play the take itself, «Shoot the video» fixes the faces. A lock — the scene is pinned, a yellow dot — a remark. A click selects the scene, Ctrl adds it to the selected ones, Shift picks a run from the selected one; a double click or Enter opens «Scene in detail», ← → the scene next to it, Esc drops several picked ones.</dd>
<dt data-term="Несколько сцен">Several scenes</dt><dd>More than one picked (Ctrl, Shift or a click on an episode's margin) — a shared panel on the right: length, camera and model for all, «Improve» and «Another version» for all, pin, delete.</dd>
<dt data-term="Улучшить">Improve</dt><dd>On «Scene in detail» and in the shared panel of several scenes: the Writer makes the scene more concrete and more visual, keeping the meaning.</dd>
<dt data-term="Склейки внутри сцены">Cuts inside the scene</dt><dd>A checkbox on the scene panel's «Scene» tab (when it has 2–3 actions): each action a shot of its own with a hard cut, wide → medium → close-up, starting from the scene’s framing. H3 makes the cut itself from the shot markup in the prompt; in 5 s you usually get one cut and a push-in for the rest, in 10–15 s scenes more. H3 only, and only without spoken lines. The scene is shot again; the clip check doesn’t count such a cut as a fault.</dd>
<dt data-term="Ветка">Branch</dt><dd>A button on the «Shooting» tab, next to the title: a copy of the video to try another take, model or edit without losing this one. The shot scenes come as they are — nothing shot again, nearly no disk space; the built video doesn’t. Under the branch’s title: where it came from and what differs — which scenes, settings, its own montage.</dd>
<dt data-term="Граф для ComfyUI">Graph for ComfyUI</dt><dd>A folded block on the scene panel's «Shooting» tab: the graph a new shot sends to the worker, without shooting. For debugging recipes: which nodes, which input files and from where, the scene’s key, «Copy JSON».</dd>
<dt data-term="Другой вариант">Another version</dt><dd>In the same places: a different action and angle that still fit the video.</dd>
<dt data-term="Обновить сюжет от этой сцены">Update the story from this scene</dt><dd>On the scene panel's «Frame» tab, the «Story» block. You changed a scene: say the heroine now walks away, while later in the storyboard they embrace. The Writer reads the whole video, names the scenes that no longer agree with this one (people, place, an object, what came before or after) with a reason for each, and rewrites only them: at most 6, locked scenes and scenes with your own prompt are left alone. The rewritten ones get a «from scene N» tag (the reason in its tooltip) and will be shot again. «Put them back» restores their texts. The heroes’ spoken lines don’t change: check them yourself. About 30 s.</dd>
<dt data-term="Перетаскивание">Dragging</dt><dd>In the «Script»: drag a scene's line to another place to change the order. The first scene always becomes a new one.</dd>
<dt data-term="Замок">Lock</dt><dd>The Writer doesn't touch a pinned scene: not by the buttons, not by «Rewrite unpinned», not by auto-fixing. «Pin» is at the bottom of the scene panel; a pinned scene's card shows a lock. A scene with its own prompt is never rewritten by the Writer at all.</dd>
<dt data-term="Перевести на русский">Translate to Russian</dt><dd>A button in the «Script» when the storyboard has scenes in English (clips from Remiqora). The Writer translates what happens and the prompt itself into Russian — for reading: the model still gets the original, nothing shot is reshot. The scene panel shows the prompt in Russian, «Show original» shows what the model gets. Editing the prompt removes the translation.</dd>
<dt data-term="Подсказки в панели">Notes in the panel</dt><dd>«Text changed — prompt still old» — you edited «What happens» but the English prompt is the same: press «Update prompt from text» under it. A «check» remark — the «The «check» mark» section. «In the clip: frozen for 2.5 s» — the automatic check of the shot clip (below).</dd>
<dt data-term="Кадр на карточке">Frame on the card</dt><dd>The scene's last frame from the latest shoot. After an edit it may be stale until the scene is reshot.</dd>
</dl>` },

  { id: 'inspector', group: 'Storyboard', title: 'Scene panel', html: `
<p>On the right, for the selected scene. On top — its number big, its time and kind (new or a continuation), ← → to the scenes beside it and ⤢ — «Scene in detail» on the whole page. Under them «What happens» is always in sight. The rest is in tabs: «Start» — what the scene starts from, its first and last frame; «Scene» — camera, shot, length, cuts inside the scene and «Update the story»; «Shooting» — the model, faces after the shot, the scene's LoRA, the prompt for the model and the graph for ComfyUI; «Lines» — who is in the scene and what they say; «Takes». The open tab stays as you select another scene. At the bottom, always — «Another take», «Pin» and the bin. On «Scene in detail» the same fields go one under another, without tabs.</p>
<dl>
<dt data-term="Что происходит">What happens</dt><dd>The scene in your words. If you change it, «Update prompt from text» appears: the Writer rewrites the English to match your text and leaves your text as it is.</dd>
<dt data-term="Кто написал">Who wrote it</dt><dd>Under the text: «you» — the scene is yours, «writer» — the Writer's, «empty» — not written yet. Your scene pins itself: the Writer leaves it alone when it rewrites other scenes («Update the story», «Write the rest»). «In my own words» puts the cursor in the text — write it yourself. «Rewrite» hands the scene to the Writer: it writes it anew and the lock comes off.</dd>
<dt data-term="Камера">Camera</dt><dd>Static, push in, pull out, side tracking, camera backing away in front of the hero, following from behind, orbit, pan, rise, handheld close to the face. Calm movements are more reliable; a static camera is gentlest on the face. «Handheld» is for an LTX singing scene from its first frame: with a static camera it comes out almost a still. In new clips the singing scenes in close-up and medium shot get it themselves.</dd>
<dt data-term="План">Shot</dt><dd>Wide, medium, close-up. A close-up shows the face better, a wide shot shows the place.</dd>
<dt data-term="Начало">Start</dt><dd>A new scene (from text, its own place) or a continuation — from the last frame of the previous scene or of any earlier one («Continuation — from the last frame of scene N»). The latter is a cutaway: you showed something else and came back to the moment where scene N ended. Such a scene opens its own chain (with a change of shot before it), and face drift is counted by frames: «from the frame of scene 2» is the third continuation if scene 2 is itself the second. The card says «from frame N».</dd>
<dt data-term="Модель сцены">Scene model</dt><dd>Which model shoots the scene and its continuations: «same as the video» or its own. That way, in one video, story scenes with faces are shot by H3, landscapes and action by LTX 2.5 (three times faster), singing to a track by LTX 2.3. Frame sizes differ between models: in the video, a scene is fitted to the video's frame. Shooting goes model by model — each loads once. A continuation has no model of its own: it is shot by its chain's model, because it starts from that model's frame.</dd>
<dt data-term="Длина сцены">Scene length</dt><dd>5, 10 or 15 seconds — as much as the scene's model shoots: LTX up to 10 s, H3 up to 15 s, WAN only 5. A storyboard on LTX is written in 10 s scenes from the start: 30 s is 3 scenes, 15 s is 10 + 5. In such a scene the actions share all 10 seconds, and the lines can be twice as long — about 20 words. Length is part of the key: change it and the scene and the continuations after it are reshot, the scenes after it shift.</dd>
<dt data-term="Первый кадр">First frame</dt><dd>On a new scene. «Draw a frame» — FLUX.2 Klein draws the first frame itself: the hero from their photo (face, hair, clothes) in the scene's place, with the scene's framing and first action, about 5 s; the face on the frame is checked against the photo, a miss tries another seed, and when the third one fails too a warning sits under the frame — «Redraw the frame» draws again. The Writer already "sees" such a frame — no rewrite needed. «Start from photo» — the scene starts from your picture, the scene's model brings it to life; «From hero photo» — from the picture on the Idea screen. Then be sure to press <b>«Rewrite for photo»</b>: the Writer looks at the picture and writes the scene from it.
<dt data-term="Кто в кадре">Who is in the frame</dt><dd>Above the first frame, for drawing it. «As the scene says» — the ones the scene's text names, with the faces from their photos. You can pick the heroes yourself (several, by clicks) or «Nobody»: then only the place and what goes on in it is drawn, without people, faces or hands — leaves in the forest, say, even when the scene's English prompt still has the heroine. A drawn frame doesn't change — click «Another version».</dd>
${ex('Uploaded a photo of a lavender field and shot right away. The text had a meadow under clouds — the model drifted from the photo to the text, and the face changed.', 'Uploaded the photo → «Rewrite for photo» → the scene starts in the same field, in the same pose.')}</dd>
<dt data-term="Последний кадр">Last frame</dt><dd>LTX only: «End on frame» — the scene ends on your picture. Describe in the prompt how it gets there: camera movement, action. A model that can't do this shoots the scene without it — that's written under the picture. The frame is part of the key: change it and the scene is reshot.</dd>
<dt data-term="Кто в сцене">Who's in the scene</dt><dd>In «Several» mode: checkboxes for who is in the shot. Only the looks of the checked characters go into the prompt; otherwise the model draws everyone. A continuation without checks takes the cast of the scene that opened its chain.</dd>
<dt data-term="Реплики">Lines</dt><dd>Under everyone in the scene — what they say, in your language, and how: normally, quietly, in a whisper, shouting, with a smile, angrily… Empty — silent. Each line becomes its own timeline line: <code>[1s-4s] Character 2 whispers, in English: "I'm sorry."</code> — the speaker is named the same way as in the heroes' description («The heroine», «Character 2») so the lips move on the right face. The scene's actions and lines share its length: a line gets as much as its words need (about 2.5 words per second, at least 2 s), the actions get the rest. Voices are added to the sound, everything else is quieter under them. Lines are shown on the scene card too. The «12 / 10 words» counter above the lines is how many words everyone has and how many fit (about 10 per 5 s, 20 per 10 s); over that, the counter turns yellow. On WAN there's a warning above the lines, «… doesn't talk: lines won't be heard» — they need H3 or LTX.
${ex('«You\'re late. I waited for you all evening and you didn\'t even call»', '«You\'re late. I waited all evening»', 'A 5 s scene holds about 10 words for everyone together; longer, and the speech gets rushed or cut off, and the scene gets the «check» mark.')}
«Suggest lines» — the Writer proposes lines for those in the scene, from the story around it; yours are replaced, and you can edit them right away. Editing a line reshoots the scene and the continuations after it; scenes without lines don't change.</dd>
<dt data-term="Действия по строкам">Action lines</dt><dd>1–3 actions in English, one per line; on H3 they go onto the timeline <code>[0s-2s] [2s-4s] [4s-5s]</code>, LTX and WAN get them as sentences in order. Editing them pins the scene.
${ex('<code>She walks forward slowly.</code>', '<code>She walks toward the camera, the wind lifting her hair.</code>',
  'Without a direction toward the camera the model often turns people to face us but moves them away from the camera — the result is walking backwards.')}
${ex('<code>She turns, then smiles and waves.</code>', '<code>She turns to the camera.</code><br><code>She smiles.</code><br><code>She waves.</code>',
  'One action per line: the model spreads them over the seconds.')}</dd>
<dt data-term="Промт для модели">Prompt for the model</dt><dd>The collapsed «Prompt for the model, EN» block: what the scene's model will get. Code builds it from the scene's fields, differently for each model. H3 — by the formula: style, hero word for word, place, camera, timeline, sound and tail (taken apart line by line at the top of this page). LTX — one paragraph: style, place, who is there, the action from start to end, camera, sound with the lines. WAN — who, where, movement, camera, style, no sound; for a continuation and a scene from a photo, only movement and camera: the rest is already visible in the frame. For LTX and WAN the text is captioned «LTX 2.5 will get» (or another model): «on a new shoot; from the same fields, in its model's order». The storyboard stores the H3 prompt: switch back to H3 and what H3 shot is taken from the cache.</dd>
<dt data-term="Свой промт">Own prompt</dt><dd>«Write the prompt myself» moves the built prompt into the «Prompt for the model, as is» field, where you can rewrite it completely. H3 gets it word for word, LTX and WAN without the H3 markup (the «How to write a prompt» section); the Writer no longer touches the scene. «Preset» inserts a sample. «Restore the Writer's prompt» builds it from the fields again.
<pre class="ex-code">Continue seamlessly from &lt;Picture 1&gt;.

Realistic live-action cinematic look, soft natural light, film grain.

Scene: the same rooftop at dusk.

Camera: medium shot, static camera.

Timeline:
[0s-2s] She leans on the railing and looks at the city.
[2s-5s] She turns her head toward the camera and smiles.

Audio: distant traffic, a light wind.

No text, subtitles, logos or watermarks.</pre>
The first line is needed only by a continuation or a scene from a photo: that's how H3 knows it must start from a ready frame (LTX and WAN don't get it). How to write your own prompt, the hero's speech and the camera words — the <a href="#/help/prompt">«How to write a prompt»</a> section.</dd>
<dt data-term="Дубли">Takes</dt><dd>The «Takes» tab. «Another take» (at the bottom of the panel) shoots this scene again with a new seed — now, on its own (a separate job in the queue); earlier takes remain. The thumbnails are all the scene's takes: a click chooses which one goes into the video and into the continuations after it (their frame changes — they'll be reshot on «Shoot video»); × removes a take from the list, the file stays in the cache and comes back if that seed is chosen again. A continuation needs the shot frame of the scene it starts from to get a take. The card says «take 2/3». In the montage a clip can use another take without touching the storyboard.</dd>
<dt data-term="LoRA сцены">Scene LoRA</dt><dd>«Same as the video» — the set from the shooting panel; «Own» — a set and strength for this scene only, from the LoRAs of the model that shoots it; «No LoRA» — the scene is shot without them. LoRA is part of the cache key: change it and this scene is shot (and the continuations after it), the rest come from the cache. The card says «own LoRA» or «no LoRA».</dd>
<dt data-term="Закрепить, Удалить сцену">Pin, Delete scene</dt><dd>At the bottom of the panel, next to «Another take»: the lock and the bin; the other scenes' times are recalculated.</dd>
</dl>` },

  { id: 'check', group: 'Storyboard', title: 'The «check» mark', html: `
<p>After the script, code checks every scene. What fails, the Writer rewrites once by itself; if that doesn't work, the scene gets the mark, and the remark shows on the card. A scene with the mark can still be shot: it's a warning, not a ban.</p>
<ul>
<li>The English prompt contains Cyrillic letters.</li>
<li>Not 1–3 actions, an action too short or too long, or several actions joined by «then».</li>
<li>Walking without a direction toward the camera — people may walk backwards; toward and away from the camera in one scene.</li>
<li>The actions mention a character who isn't in the scene's cast — they won't be in the shot.</li>
<li>It isn't said how the scene ends — the next one has nothing to start from.</li>
<li>No description of the scene in your language.</li>
<li>Lines longer than fit in the scene; a line for a character who isn't in the scene.</li>
<li>The prompt is empty (a scene with its own prompt).</li>
<li>A continuation moves to another place — there'll be an abrupt cut.</li>
<li>A new scene doesn't describe the place; it isn't said who is in the scene.</li>
<li>There will be text, a sign or lettering in the shot.</li>
<li>The clothes change.</li>
<li>A person turned up in a video without people.</li>
<li>The scene starts from a photo, but the Writer hasn't seen it.</li>
<li>The style or the look is described too briefly; clothing got into the look description.</li>
<li>Adults only.</li>
</ul>
<p><b>In the clip: …</b> — after shooting, every new scene is also checked by the clip itself (about a second): black frames, «frozen», a jump inside the scene, a smear or a sharp change, the face not matching the start, in a clip from a song — «not singing» (the lips are still while the voice sounds). When the scene has one hero with a photo, the face is checked against their portrait: the median over five frames of the shot, below 0.3 in a close-up or medium shot is «the face is not the hero's» (a wide shot isn't judged: the face is small). «Almost still» is a scene with people whose picture barely changes. The serious ones — black, frozen, jump, long smear, «not singing», «the face is not the hero's» — are reshot once with another seed, and the take with fewer problems goes into the video, with equal ones the face closer to the hero. A singing scene of a new clip that is almost still is reshot once handheld, and the livelier take is kept. The rest is a line on the card, «In the clip: frozen for 2.5 s»: look at that spot yourself.</p>` },
]
