// The help: every parameter of Remiqora Video, what it does and what it costs, with examples. Shown at #/help (and
// #/help/<section>); the "?" next to a field shows its own entry (a <dt> of its section) in a card, examples included.
// Plain data: HelpView.vue renders it, HelpCard.vue shows one entry. `group` orders the contents; HELP_HERO is the worked example on top of the page.

import { icon } from "./icons";
import { TUTORIALS } from "./tutorials";

// a "how it reads / how it works better" pair inside an entry
const ex = (worse: string, better: string, why?: string) => `<div class="ex"><div class="ex-w"><span>Так хуже</span>${worse}</div>
  <div class="ex-b"><span>Так лучше</span>${better}</div>${why ? `<p class="ex-why">${why}</p>` : ""}</div>`;

// ---- the graph's pictures: who works (the header's colour) and what a port carries, as on the canvas (lib/graphDoc.ts)
const WHO: Record<string, [string, string]> = {
  h3: ["var(--accent)", "модель снимает"], writer: ["var(--ok)", "сценарист (LLM)"], ffmpeg: ["#378ADD", "склейка, ffmpeg и RTX"],
  krea: ["#f59e0b", "Krea 2 рисует"], v2v: ["#14b8a6", "пересборка клипа"], facefix: ["#2dd4bf", "Krea 2 и LTX 2.3 чинят лица"],
  user: ["var(--faint)", "ваши данные"], none: ["var(--rule-3)", "только холст"],
};
const PORT: Record<string, [string, string]> = {
  text: ["var(--soft)", "текст"], look: ["var(--ok)", "внешность"], image: ["#e879f9", "картинка"], clip: ["#378ADD", "сцена"],
  video: ["#378ADD", "ролик"], audio: ["#eab308", "звук"], lora: ["var(--accent-hi)", "LoRA"],
};
const pt = (name: string, type: string) => `<span class="pt" style="--p:${PORT[type][0]}"><i></i>${name}</span>`;
const WHO_CHIPS = Object.entries(WHO).filter(([k]) => k !== "none").map(([, [c, n]]) => `<span class="who-chip" style="--h:${c}"><i></i>${n}</span>`).join("");
const PORT_CHIPS = Object.entries(PORT).filter(([k]) => k !== "video").map(([k, [, n]]) => pt(k === "clip" ? "сцена, ролик" : n, k)).join("");
// a node as a card: the header in its worker's colour, its inputs left and outputs right; the <dt> is the node's
// name, so a "?" of the canvas finds it
// a port with what to plug into it / where it goes: a row of the card's list
type Port = [string, string, string];
const portRows = (ins: Port[], outs: Port[], inTitle: string, outTitle: string) => !ins.length && !outs.length ? "" : `<div class="nc-list">${
  ins.length ? `<span class="nc-h">${inTitle}</span>${ins.map(([n, t, h]) => `<div class="nc-row in">${pt(n, t)}<span class="nc-hint">${h}</span></div>`).join("")}` : ""}${
  outs.length ? `<span class="nc-h">${outTitle}</span>${outs.map(([n, t, h]) => `<div class="nc-row out">${pt(n, t)}<span class="nc-hint">${h}</span></div>`).join("")}` : ""}</div>`;
const nodeCard = (title: string, who: string, ic: string, ins: Port[], outs: Port[], text: string) =>
  `<div class="node-card" style="--h:${WHO[who][0]}"><dt>${icon(ic, 15)}${title}</dt><dd>${portRows(ins, outs, "Входы", "Выходы")}${text.startsWith("<") ? text : `<p>${text}</p>`}</dd></div>`;

// «Две концовки» as a picture: scenes 1-2 shared, two third scenes, two assemblies, two outputs
const GW = 118, GH = 56;
const gBox = (x: number, y: number, title: string, who: string, sub: string) => `<g transform="translate(${x} ${y})">
  <rect width="${GW}" height="${GH}" rx="9" class="gd-node"/><rect x="10" y="0" width="${GW - 20}" height="3" rx="1.5" fill="${WHO[who][0]}"/>
  <text x="11" y="23" class="gd-t">${title}</text><text x="11" y="41" class="gd-s">${sub}</text></g>`;
const gEdge = (x1: number, y1: number, x2: number, y2: number, type: string, faint = false) =>
  `<path d="M${x1} ${y1} C${x1 + 36} ${y1} ${x2 - 36} ${y2} ${x2} ${y2}" stroke="${PORT[type][0]}" class="gd-e${faint ? " faint" : ""}"/>
  <circle cx="${x1}" cy="${y1}" r="3.5" fill="${PORT[type][0]}"/><circle cx="${x2}" cy="${y2}" r="3.5" fill="${PORT[type][0]}"/>`;
const S1 = [16, 92], S2 = [176, 92], KA = [336, 24], KB = [336, 160], JA = [490, 24], JB = [490, 160], OA = [652, 24], OB = [652, 160];
const R = (b: number[], dy: number) => [b[0] + GW, b[1] + dy] as const, L = (b: number[], dy: number) => [b[0], b[1] + dy] as const;
const GRAPH_DIAGRAM = `<figure class="graph-pic" aria-label="Две концовки: общие сцены 1 и 2, две разные третьи, две склейки и два выхода">
<svg viewBox="0 0 786 236" role="img">
${[S1, S2, KA, KB].map((s) => [JA, JB].filter((j) => !(s === KA && j === JB) && !(s === KB && j === JA)).map((j) => gEdge(...R(s, 40), ...L(j, 38), "clip", true)).join("")).join("")}
${gEdge(...R(S1, 20), ...L(S2, 20), "image")}${gEdge(...R(S2, 20), ...L(KA, 20), "image")}${gEdge(...R(S2, 20), ...L(KB, 20), "image")}
${gEdge(...R(JA, 28), ...L(OA, 28), "video")}${gEdge(...R(JB, 28), ...L(OB, 28), "video")}
${gBox(S1[0], S1[1], "Сцена 1", "h3", "общая")}${gBox(S2[0], S2[1], "Сцена 2", "h3", "с кадра сцены 1")}
${gBox(KA[0], KA[1], "Концовка А", "h3", "с кадра сцены 2")}${gBox(KB[0], KB[1], "Концовка Б", "h3", "с кадра сцены 2")}
${gBox(JA[0], JA[1], "Склейка А", "ffmpeg", "1 · 2 · А")}${gBox(JB[0], JB[1], "Склейка Б", "ffmpeg", "1 · 2 · Б")}
${gBox(OA[0], OA[1], "Выход А", "ffmpeg", "1080p")}${gBox(OB[0], OB[1], "Выход Б", "ffmpeg", "1080p")}
<text x="16" y="178" class="gd-s">сцены 1–2 снимаются один раз</text><text x="16" y="194" class="gd-s">и идут в обе версии</text>
</svg>
<figcaption>Шаблон «Две концовки». <span style="color:#e879f9">Розовые</span> связи — последний кадр сцены идёт в старт следующей, <span style="color:#378ADD">синие</span> — снятые сцены идут в склейку, склейка — в выход.</figcaption>
</figure>`;

// the worked example: one idea through the whole app, the prompt taken apart line by line
export const HELP_HERO = `
<h1>От идеи до ролика</h1>
<p class="hero-lead">Вы пишете пару фраз на своём языке — сценарист раскладывает их на сцены (по 5 с; на LTX — по 10 с), код собирает для каждой сцены английский промт, модель ролика снимает сцены цепочкой. Вот одна идея целиком, на H3.</p>
<ol class="flow">
  <li><b>Идея</b><p class="ru">Девушка-бариста закрывает уютное кафе поздно вечером. За окном идёт дождь, она выключает свет и улыбается своему отражению в стекле.</p>
    <small>30 секунд → 6 сцен. Настроение «Кино», один герой.</small></li>
  <li><b>Сцена 1 из 6</b> <span class="kind">новая сцена · 0:00–0:05</span>
    <p class="ru">Бариста протирает стойку в пустом кафе, за мокрым окном горят фонари.</p>
    <pre class="beats">She wipes the wooden counter in slow circles.
She glances at the rain-streaked window.
She smiles softly to herself.</pre>
    <small>Текст на вашем языке — для вас. Действия по строкам — то, что будет в кадре.</small></li>
  <li><b>Промт для H3</b> <small>собирает код, не сценарист: каждая строка — из своего места. LTX и WAN получают те же слова одним абзацем, в своём порядке</small>
    <figure class="anatomy" aria-label="Из чего состоит промт">
      <div class="an" style="--c:#a855f7"><span class="an-l">Стиль<small>из «Настроения»; общий для ролика</small></span>
        <code>Cinematic live-action film, warm tungsten light against cool blue rain, shallow depth of field, subtle film grain.</code></div>
      <div class="an" style="--c:#ec4899"><span class="an-l">Героиня<small>карточка героя — дословно в каждой сцене</small></span>
        <code>The heroine (the same person in every shot): a 27-year-old woman with a dark bob, olive skin, brown eyes and a small mole on her left cheek. Wearing a mustard apron over a white shirt.</code></div>
      <div class="an" style="--c:#378ADD"><span class="an-l">Место<small>у новой сцены; продолжение остаётся там же</small></span>
        <code>Scene: a small cozy café at night, warm pendant lights, rain on the large front window.</code></div>
      <div class="an" style="--c:#7F77DD"><span class="an-l">Камера<small>«План» и «Камера» в инспекторе</small></span>
        <code>Camera: medium shot, slow push-in.</code></div>
      <div class="an" style="--c:#1D9E75"><span class="an-l">Таймлайн<small>«Действия по строкам», по секундам</small></span>
        <code>Timeline:
[0s-2s] She wipes the wooden counter in slow circles.
[2s-4s] She glances at the rain-streaked window.
[4s-5s] She smiles softly to herself.</code></div>
      <div class="an" style="--c:#eab308"><span class="an-l">Звук<small>«Музыка и звук» + звуки сцены</small></span>
        <code>Audio: soft lo-fi piano. Rain tapping on the glass, a cloth squeaking on wood.</code></div>
      <div class="an" style="--c:#888780"><span class="an-l">Хвост<small>всегда: держать лицо, без текста</small></span>
        <code>Keep her face, hair and outfit exactly the same. No text, subtitles, logos or watermarks.</code></div>
    </figure></li>
  <li><b>Ролик</b><p>30 с — две цепочки по три сцены. Сцена 1 снимается из текста, сцены 2–3 продолжают её с последнего кадра, сцена 4 открывает новую цепочку, 5–6 продолжают её. В черновике H3 это около 1,5 минуты на сцену; потом склейка со звуком и, если выбрано, 1080p или 4K.</p></li>
</ol>`;

export interface HelpSection { id: string; group: string; title: string; html: string }
const REFERENCE: HelpSection[] = [
  { id: "how", group: "Начало", title: "Как это устроено", html: `
<p>Ролик делается в четыре шага, они же в шапке: <b>Идея</b>, <b>Раскадровка</b>, <b>Ролик</b>, <b>Монтаж</b>.</p>
<dl>
<dt>Идея</dt><dd>Пара фраз на вашем языке (он задаётся в «Модели» → «Сценарист»), по желанию фото. Сценарист — локальная языковая модель — делит идею на сцены длиной в сцену модели ролика: 5 с, на LTX — 10 с.</dd>
<dt>Раскадровка</dt><dd>Сцены можно править, переставлять, закреплять и переписывать. Каждая правка сохраняется сразу.</dd>
<dt>Ролик</dt><dd>Сцены снимаются цепочкой моделью ролика — H3, LTX 2.5, LTX 2.3, WAN 2.2 5B или FastWan (<a href="#/help/video-models">«Модели видео»</a>) — и склеиваются со звуком; по желанию — 1080p или 4K, HDR10, 48 кадров в секунду.</dd>
<dt>Монтаж</dt><dd>Снятые сцены на таймлайне: обрезка, переходы, скорость, трек и звуки, цвет. Ничего не переснимается.</dd>
</dl>
<p>H3 и LTX делают видео и звук одним проходом: в сцене звучит то, что написано в её строке <code>Audio:</code>. WAN снимает без звука.</p>
<p>Сценарист и видеомодель не помещаются в видеопамять вместе, поэтому задачи идут по очереди, по одной. Видеомодель запускается сама при первой съёмке и остаётся в памяти между сценами; после сценария или смены модели она загружается заново — до полуминуты.</p>
<p>Ролики лежат в папке <code>projects</code>. Страницу можно закрыть посреди работы — результат сохранится в проект.</p>` },

  { id: "header", group: "Начало", title: "Шапка и строка состояния", html: `
<dl>
<dt>Шаги</dt><dd>Идея, Раскадровка, Ролик, Монтаж. Раскадровка открывается, когда выбран ролик; Ролик и Монтаж — когда раскадровка написана. На графе и в лаборатории вместо шагов — название экрана.</dd>
<dt>Сценарист</dt><dd>Кнопка справа: модель, которая пишет раскадровку и описывает фото. В списке все GGUF из папки загрузок LM Studio и из <code>models\\llm</code> — скачанная в LM Studio модель появится сама. «видит фото» — модель умеет описать героя по снимку.</dd>
<dt>Что делает видеокарта</dt><dd>Строка под шапкой: кто работает (видеомодель — фиолетовая точка, сценарист — зелёная), какая сцена и шаг, процент и сколько осталось. Щелчок открывает подробности: задачу, очередь, «Остановить» и память. Когда видеокарта свободна, там же «Выгрузить модель» — освободить видеопамять для других программ; следующая съёмка загрузит модель снова.</dd>
<dt>ОЗУ и Видео</dt><dd>Занятая память. Полоска «ОЗУ» желтеет от 80 % и краснеет от 92 %. Полоска «Видео» разбита по владельцам, у каждого свой цвет: «Видеомодель», сценарист, сама Remiqora Video, остальные программы.</dd>
<dt>Модели, Лаборатория, Справка</dt><dd>Веса и папки, одна сцена вручную и окно справки: экраны, очередь, быстрый старт. Если окно уже 1500 пикселей, видны только значки (шестерёнка, колба, вопрос), название — во всплывающей подсказке; так шапка помещается в одну строку. На телефоне шапка уезжает вверх вместе со страницей. У каждого экрана своё окно справки — кнопка «Справка» рядом с заголовком; эта страница — полный справочник, кнопка «Полная справка» в окне.</dd>
<dt>Боковая панель</dt><dd>На экранах «Раскадровка», «Ролик» и графа панель с полями переставляется, как в DAW Remiqora: потяните ручку из шести точек вверху панели — появятся места «Слева», «Справа» и «Окном здесь»; щелчок по ручке открывает то же меню. Прикреплённая панель становится шире или уже, если тянуть её край (или щёлкнуть по краю и нажимать <kbd>←</kbd> <kbd>→</kbd>; двойной щелчок — ширина по умолчанию). Окно двигается за ручку, размер — за правый нижний угол, крестик возвращает его направо. Место и размер запоминаются для каждого экрана в этом браузере. На узком экране панель стоит под содержимым, как раньше.</dd>
</dl>` },

  { id: "prompt", group: "Промты", title: "Как писать промт", html: `
<p>Промт — текст, по которому модель снимает сцену: что видно, что происходит, что слышно. В раскадровке его собирает код из полей сцены, писать его не нужно. Сами вы пишете промт в лаборатории и в режиме «Свой промт» — этот раздел для них. Готовые промты для копирования — в «Заготовках».</p>
<div class="tip"><b>Формула в разделах «Промты» — для H3:</b> метки <code>Scene:</code>, <code>Camera:</code>, <code>Audio:</code>, таймлайн по секундам, хвост. Ваш промт LTX и WAN получают переделанным: без строки <code>Continue seamlessly from &lt;Picture 1&gt;.</code> и меток <code>&lt;Picture N&gt;</code>, таймлайн — одним абзацем предложений по порядку, без хвоста «No text, subtitles…» (LTX от него рисует субтитры); WAN — ещё и без реплик и строки <code>Audio:</code>. Сцены раскадровки на LTX и WAN получают свой промт, собранный из тех же полей (раздел «Модели видео»).</div>
<dl>
<dt>Язык</dt><dd>Английский: его модели понимают лучше всего. Если английский не родной, напишите сцену на своём языке, переведите переводчиком и сверьте с примерами ниже. На языке ролика остаются только слова, которые герой произносит вслух (раздел «Речь и диалоги»).</dd>
<dt>Что видно и слышно</dt><dd>Модель не знает сюжета, мыслей и прошлого героя — только картинку и звук этих секунд. Вместо чувства опишите, что делают лицо и руки.
${ex("She feels lonely and remembers her past.", "She sits alone on a bench, looks down at an old photo and slowly wipes away a tear.",
  "Воспоминание снять нельзя, а взгляд вниз, фото в руках и слезу — можно.")}</dd>
<dt>Конкретные слова</dt><dd>Предмет, цвет, материал, время суток, погода — чем точнее, тем меньше модель придумывает сама.
${ex("a woman in a nice dress in a city", "a woman in a long emerald silk dress on a wet cobblestone street at night, neon reflections in the puddles")}</dd>
<dt>Длина сцены</dt><dd>В лаборатории от 1 секунды до предела модели (H3 — 15, LTX — 10, WAN — 5), в раскадровке — 5 или 10 с, по модели. За 5 секунд помещается 1–3 простых действия. История из пяти событий — это несколько сцен, а не один длинный промт.</dd>
<dt>Длина промта</dt><dd>Обычно 60–150 слов. Длиннее можно, если каждое слово — про кадр; пересказ сюжета и повторы не помогают.</dd>
<dt>Возраст</dt><dd>В Remiqora Video снимаются только взрослые персонажи. Пишите возраст прямо: <code>an adult woman, about 30</code>.</dd>
<dt>Сид</dt><dd>Число, от которого зависит случайность съёмки. Тот же промт с тем же сидом даёт тот же дубль. Чтобы понять, что даёт правка, меняйте одно-два слова и снимайте с тем же сидом — в лаборатории это «Повторить с сидом».</dd>
<dt>Запреты</dt><dd>Отдельного поля «чего не надо» у H3 нет. Короткий запрет в конце помогает, но не всегда; надёжнее описать, что должно быть.
${ex("Scene: a street, no people, no cars.", "Scene: an empty quiet street at dawn, closed shutters, wet asphalt.")}</dd>
</dl>` },

  { id: "prompt-parts", group: "Промты", title: "Части промта по порядку", html: `
<p>Промт удобно писать частями, каждую — отдельным абзацем, в том же порядке, что в разборе в начале справки. В лаборатории под полем видно, какие части уже есть, а щелчок по недостающей вставит её заготовку.</p>
<dl>
<dt>Начало с кадра</dt><dd>Только если сцена начинается с готовой картинки: продолжение с последнего кадра или фото. Первой строкой — <code>Continue seamlessly from &lt;Picture 1&gt;.</code> Дальше — что начинается теперь. Место, людей и свет заново не описывайте: их задаёт картинка, а описание, которое с ней расходится (другое место, другой план), уводит в другую сцену. Вместо него хватит строки <code>Everything stays as in the picture: the same people, place, light, colours and framing.</code> Новой сцене из текста строка «Continue seamlessly» не нужна.</dd>
<dt>Стиль</dt><dd>Какое это кино: живая съёмка или анимация, свет, цвет, оптика, плёнка. Один и тот же абзац во всех сценах ролика. Стили, которые знает H3: <code>live-action</code>, <code>cinematic</code>, <code>2D-animated</code>, <code>3D CG</code>, <code>claymation</code>, <code>watercolor</code>, <code>vintage film</code>.
${ex("beautiful, high quality, 8k, masterpiece", "Realistic live-action cinematic look, warm evening lamp light, shallow depth of field, film grain.",
  "Слова-похвалы почти ничего не говорят модели, а свет, оптика и плёнка — говорят.")}</dd>
<dt>Герой</dt><dd>Возраст, волосы, лицо, одежда. Описание повторяйте во всех сценах слово в слово: написали одежду иначе — она и сменится.</dd>
<dt>Место</dt><dd><code>Scene:</code> — где и когда: комната или улица, погода, время суток, главные предметы.
<pre class="ex-code">Scene: a small kitchen at dawn, rain on the window, a kettle on the stove.</pre></dd>
<dt>Камера</dt><dd><code>Camera:</code> — план и движение: <code>Camera: close-up, slow push-in.</code> Все слова — в разделе «Камера и свет».</dd>
<dt>Таймлайн</dt><dd><code>Timeline:</code> — что происходит по секундам, одно действие на строку. Отрезки идут подряд и вместе дают длину сцены.
<pre class="ex-code">Timeline:
[0s-2s] She lifts the cup to her lips.
[2s-4s] She looks out of the window.
[4s-5s] She smiles.</pre></dd>
<dt>Звук</dt><dd><code>Audio:</code> — H3 делает звук вместе с видео. Перечислите звуки места и действий; музыку описывайте инструментами и темпом, а не настроением.
${ex("Audio: epic emotional music.", "Audio: slow solo piano with soft strings. Rain on the glass, a spoon clinking in a cup.")}
Без музыки: <code>Audio: no music, only the natural sound of rain and footsteps.</code></dd>
<dt>Хвост</dt><dd><code>Keep her face, hair and outfit exactly the same. No text, subtitles, logos or watermarks.</code> Первая фраза помогает продолжениям держать героя, вторая — против надписей в кадре.</dd>
</dl>` },

  { id: "prompt-speech", group: "Промты", title: "Речь и диалоги", html: `
<p>H3 и LTX умеют говорить: голос, движение губ и звук делаются вместе с видео. Речь получается разборчивой, русская в том числе — проверено в лаборатории на H3, LTX 2.5 и LTX 2.3. WAN не говорит: реплики у него не прозвучат. На раскадровке реплики пишутся под каждым героем сцены (инспектор, «Реплики»): код сам ставит их в таймлайн в формате ниже и добавляет голоса в звук. «Придумать реплики» там же — сценарист предложит их по кнопке. В лаборатории и «Своём промте» реплику пишут прямо в промте.</p>
<dl>
<dt>Как написать реплику</dt><dd>В таймлайне: кто говорит, каким голосом, на каком языке, и сами слова в кавычках — на том языке, на котором их надо произнести. В строке звука — что звучит голос.
<pre class="ex-code">[1s-4s] She speaks in a calm, warm voice, in Russian: "Я знала, что ты вернёшься."

Audio: her clear calm voice speaking Russian, quiet room tone, no music.</pre></dd>
<dt>Длина реплики</dt><dd>Обычная речь — около 2–3 слов в секунду. В сцену 5 секунд помещается фраза из 6–10 слов, если оставить секунду на взгляд и паузу; в сцену 10 с — вдвое больше. Слишком длинная фраза может оборваться или пойти скороговоркой — тогда разделите её на две сцены.</dd>
<dt>Голос</dt><dd>Опишите, как звучит голос: низкий, хриплый, шёпотом, быстро, с улыбкой.
${ex('She says: "Привет."', 'She whispers softly with a smile, in Russian: "Привет."')}</dd>
<dt>Двое говорят</dt><dd>По очереди, каждая реплика — своя строка таймлайна. Называйте говорящего приметой — <code>The man in the grey coat says…</code>, <code>The woman answers…</code>, — чтобы губы двигались у нужного человека.</dd>
<dt>Голос за кадром</dt><dd>Если говорит рассказчик, а губы героя двигаться не должны: <code>says in an off-screen voiceover: "…" while her lips remain completely closed.</code> Так советует руководство MiniMax; в Remiqora Video это ещё не проверяли.</dd>
<dt>Формат MiniMax</dt><dd>В официальном руководстве реплика пишется с номером говорящего и языком: <code>The woman (S1) says: &lt;d&gt;[Russian] Я знала.&lt;/d&gt;</code> Его можно пробовать в лаборатории; формат с кавычками проверен у нас, этот — пока нет.</dd>
<dt>Голос между сценами</dt><dd>Каждая сцена снимается отдельно, и в следующей голос может звучать иначе. Одинаковое описание голоса во всех сценах помогает; насколько голос держится в цепочке, ещё не проверяли.</dd>
</dl>` },

  { id: "prompt-sound", group: "Промты", title: "Звуки и музыка", html: `
<p>H3 и LTX делают звук тем же проходом, что и картинку, поэтому звук совпадает с действием (WAN снимает без звука): шаг — со стуком, взрыв — со вспышкой. Звук задаётся в двух местах: в строке таймлайна — у события, в строке <code>Audio:</code> — для всей сцены. Целые примеры — в «Заготовках».</p>
<dl>
<dt>Звук события</dt><dd>Пишите его в той же строке таймлайна, что и само событие, — так он прозвучит в нужную секунду.
<pre class="ex-code">[2s-3s] The glass slips from her hand and shatters on the stone floor with a sharp crash.</pre></dd>
<dt>Фон сцены</dt><dd>Строка <code>Audio:</code>: место, погода, мелкие звуки, 1–3 фразы. <code>Audio: steady rain on the roof, distant thunder, a dog barking far away.</code></dd>
<dt>Громкие события</dt><dd>Взрыв, гром, удар — называйте силу и характер звука: <code>deafening boom</code>, <code>low rumble</code>, <code>sharp crack</code>, <code>metallic clang</code>, <code>crackling fire</code>.
${ex("There is an explosion.", "A fireball hits the castle wall and explodes with a deafening boom; stones and sparks fly.")}</dd>
<dt>Музыка за кадром</dt><dd>Её слышит только зритель. Описывайте инструменты, темп и как меняется громкость, а не настроение.
${ex("Audio: sad music.", "Audio: a slow solo cello with soft piano chords, growing quieter toward the end.")}</dd>
<dt>Музыка в кадре</dt><dd>Её слышат герои: уличный музыкант, радио, оркестр. Пишите её событием в таймлайне, с источником: <code>[0s-5s] A street musician plays a fast flamenco melody on an acoustic guitar.</code> В строке звука тогда — <code>no background score</code>, чтобы модель не добавила ещё и музыку за кадром.</dd>
<dt>Без музыки</dt><dd><code>Audio: no music, only …</code> и перечислите звуки. Нужно, если потом наложите на ролик свой трек.</dd>
<dt>Тихая сцена</dt><dd>Опишите тишину звуками: <code>quiet room tone, only her soft breathing and a clock ticking</code>.</dd>
<dt>Музыка между сценами</dt><dd>Каждая сцена сочиняет свою музыку, поэтому мелодия от сцены к сцене меняется. Одна музыка на весь ролик — свой трек в раскадровке (раздел «Качество, LoRA, музыка, выход»), а в сценах — «В сценах без музыки».</dd>
</dl>` },

  { id: "prompt-cast", group: "Промты", title: "Несколько персонажей", html: `
<p>Модель рисует каждого, кого вы упомянули, и легко путает, кто что делает. Чем проще различить героев, тем меньше путаницы. Целый пример — «Трое в кадре» и «Диалог двоих» в «Заготовках».</p>
<dl>
<dt>Сколько</dt><dd>Двое-трое. Чем больше людей с собственными действиями, тем чаще модель путает, кто что делает. Толпу описывайте фоном, без примет: <code>blurred passers-by in the background</code>.</dd>
<dt>Разные приметы</dt><dd>Пол, возраст, волосы, цвет одежды — так, чтобы героев нельзя было спутать.
${ex("a man and a woman", "a tall bald man in a black leather jacket and a young woman with a red bob in a yellow raincoat")}</dd>
<dt>Где кто стоит</dt><dd>Расставьте героев: <code>on the left</code>, <code>on the right</code>, <code>in the middle</code>, <code>in the foreground</code>, <code>in the background</code>. Так каждому проще остаться на своём месте.</dd>
<dt>Кто что делает</dt><dd>Каждую строку таймлайна начинайте с того, кто действует, и зовите его по примете: <code>The man in the grey coat…</code>, <code>The red-haired woman…</code>. Местоимения he и she при двух людях одного пола путают модель.</dd>
<dt>Только они</dt><dd>Допишите в место сцены: <code>Only these two people are in the scene, nobody else.</code> — иначе модель может добавить кого-нибудь ещё.</dd>
<dt>Кто говорит</dt><dd>Реплики — по очереди, каждая со своей приметой говорящего и описанием голоса (раздел «Речь и диалоги»).</dd>
<dt>В раскадровке</dt><dd>Режим «Несколько» на экране идеи делает это сам: у каждой сцены галки «Кто в сцене», и в промт идут внешности только отмеченных.</dd>
</dl>` },

  { id: "prompt-camera", group: "Промты", title: "Камера и свет: слова", html: `
<p>Английские слова, которые H3 понимает. Движение можно уточнить размахом и скоростью — и писать его обычной фразой: <code>The camera pushes in with small amplitude at slow speed toward her face.</code></p>
<dl>
<dt>План</dt><dd><code>extreme close-up</code> — деталь, глаза; <code>close-up</code> — лицо; <code>medium close-up</code> — по грудь; <code>medium shot</code> — по пояс; <code>full shot</code> — во весь рост; <code>wide shot</code> — человек и место вокруг.</dd>
<dt>Камера стоит</dt><dd><code>static shot</code> — бережнее всего к лицу; хорош для реплик.</dd>
<dt>Камера едет</dt><dd><code>push in</code> — к герою; <code>pull out</code> — от героя; <code>truck left</code> / <code>truck right</code> — вбок; <code>pedestal up</code> / <code>pedestal down</code> — вверх и вниз; <code>tracking shot</code> — следом за идущим; <code>arc shot</code> — по дуге вокруг героя.</dd>
<dt>Камера поворачивается</dt><dd>Стоит на месте и поворачивает объектив: <code>pan left</code> / <code>pan right</code> — влево и вправо; <code>tilt up</code> / <code>tilt down</code> — вверх и вниз; <code>zoom in</code> / <code>zoom out</code> — приближение объективом, без движения камеры.</dd>
<dt>Особые</dt><dd><code>the camera shakes slightly</code> — как с рук; <code>POV</code> — глазами героя.</dd>
<dt>Размах и скорость</dt><dd><code>with small amplitude</code> / <code>with large amplitude</code>, <code>at slow speed</code> / <code>at fast speed</code>. Медленное и небольшое движение надёжнее: на быстром — смаз.</dd>
<dt>Свет</dt><dd><code>soft natural daylight</code>, <code>golden hour sunlight</code>, <code>warm lamp light</code>, <code>cold blue moonlight</code>, <code>neon lights</code>, <code>candlelight</code>, <code>backlight, silhouette</code>.</dd>
<dt>Картинка</dt><dd><code>shallow depth of field</code> — фон размыт; <code>film grain</code> — плёночное зерно; <code>high contrast</code> — резкие тени; <code>muted colors</code> — приглушённый цвет.</dd>
</dl>` },

  { id: "prompt-mistakes", group: "Промты", title: "Частые ошибки", html: `
<dl>
<dt>Несколько действий в строке</dt><dd>H3 раскладывает действия по секундам, когда каждое на своей строке.
${ex("<code>She turns, then smiles and waves.</code>", "<code>[0s-2s] She turns to the camera.</code><br><code>[2s-4s] She smiles.</code><br><code>[4s-5s] She waves.</code>")}</dd>
<dt>Ходьба без направления</dt><dd>${ex("<code>She walks down the street.</code>", "<code>She walks toward the camera down the street.</code>",
  "Без направления модель часто разворачивает человека лицом к нам, а ведёт его от камеры — выходит ходьба задом наперёд.")}</dd>
<dt>Надписи</dt><dd>Вывески, экраны, письма, книги — модели часто пишут на них абракадабру. Если надпись не нужна, не упоминайте предметы с текстом. Если нужна — коротко, в кавычках: <code>a neon sign reading "OPEN"</code>; получится не всегда.</dd>
<dt>Лишние люди</dt><dd>Каждый упомянутый человек появится в кадре. Если герой один, допишите <code>Only she is in this scene, nobody else.</code> Толпу описывайте фоном: <code>blurred passers-by in the background</code>.</dd>
<dt>Другое место в продолжении</dt><dd>Продолжение начинается с последнего кадра — значит, в той же комнате. «She walks into another room» даст резкий скачок посреди сцены; новое место — это новая сцена.</dd>
<dt>Одежда меняется</dt><dd>Одежда описана в сценах по-разному или не описана вовсе — модель придумывает новую. Копируйте описание героя слово в слово.</dd>
<dt>Быстрое движение</dt><dd>Бег, драка, танец, резкая камера смазываются, особенно в черновике. Замедлите действие или снимите его крупнее и короче.</dd>
<dt>Пустые слова</dt><dd><code>epic</code>, <code>amazing</code>, <code>emotional</code>, <code>masterpiece</code> не говорят модели, что снимать. Замените их светом, движением и звуком.</dd>
<dt>Русские слова в тексте</dt><dd>Всё, кроме произносимых слов, пишите по-английски: слово на другом языке посреди английского текста модель понимает хуже, а в раскадровке оно даёт пометку «проверь».</dd>
</dl>` },

  { id: "prompt-recipes", group: "Промты", title: "Заготовки", html: `
<p>Те же целые промты, что в меню «Заготовка ▾» лаборатории (там они вставляются сразу, по-английски или на вашем языке): скопируйте и поменяйте под себя — героя, место, действия. В Remiqora Video проверена «Реплика в камеру»; остальные написаны по руководству MiniMax и нашему опыту, и результат может отличаться — снимайте по 2–3 дубля и выбирайте.</p>
<dl>
<dt>Герой в кадре</dt><dd>Новая сцена из текста: человек, место, три действия.
<pre class="ex-code">Realistic live-action cinematic look, golden hour sunlight, shallow depth of field, film grain.

Scene: an adult woman, about 30, with long wavy red hair and freckles, wearing a white linen shirt, stands on a wooden pier by a calm lake at sunset.

Camera: medium shot, slow push-in.

Timeline:
[0s-2s] She looks out over the water.
[2s-4s] She turns her head toward the camera.
[4s-5s] She smiles softly.

Audio: gentle acoustic guitar at a slow tempo. Water lapping against the pier, distant birds.

Keep her face, hair and outfit exactly the same. No text, subtitles, logos or watermarks.</pre></dd>
<dt>Реплика в камеру</dt><dd>Герой говорит на языке ролика.
<pre class="ex-code">Realistic live-action cinematic look, warm evening lamp light, shallow depth of field, film grain.

Scene: an adult man, about 40, with short grey hair and a trimmed beard, wearing a dark wool sweater, sits at a kitchen table at night.

Camera: medium close-up, static shot, his face clearly visible.

Timeline:
[0s-1s] He looks up at the camera.
[1s-4s] He speaks in a low, tired voice, in Russian: "Садись. Нам надо поговорить."
[4s-5s] He folds his hands on the table.

Audio: his low calm voice speaking Russian, quiet room tone, a clock ticking, no music.

No text, subtitles, logos or watermarks.</pre></dd>
<dt>Диалог двоих</dt><dd>Длина 8 с. Герои различаются одеждой и местом в кадре, реплики идут по очереди, у каждой — примета говорящего.
<pre class="ex-code">Realistic live-action cinematic look, soft window daylight, shallow depth of field, film grain.

Scene: a small café by a big window. On the left, an adult man, about 35, with short black hair and a grey wool coat. On the right, an adult woman, about 30, with a red bob and a yellow raincoat. They sit across a small table with two cups of coffee. Only these two people are in the scene, nobody else.

Camera: medium shot, static shot, both faces clearly visible.

Timeline:
[0s-3s] The man in the grey coat leans forward and says in a low calm voice, in Russian: "Ты всё-таки пришла."
[3s-4s] The red-haired woman looks at him and smiles.
[4s-7s] The red-haired woman answers in a soft amused voice, in Russian: "Я же обещала."
[7s-8s] The man in the grey coat laughs quietly.

Audio: two voices speaking Russian, quiet café chatter in the background, cups clinking, no music.

No text, subtitles, logos or watermarks.</pre></dd>
<dt>Трое в кадре</dt><dd>Без речи: у каждого свои приметы, своё место и своё действие.
<pre class="ex-code">Realistic live-action cinematic look, golden hour sunlight, film grain.

Scene: a sunny park meadow. On the left, an adult woman, about 25, with long blond braids and a white sundress. In the middle, an adult man, about 30, tall, with a shaved head and a green T-shirt. On the right, an adult woman, about 40, with short curly grey hair and a denim jacket. Only these three people are in the scene, nobody else.

Camera: full shot, static shot.

Timeline:
[0s-2s] The man in the green T-shirt throws a red frisbee to the left.
[2s-4s] The blond woman in the white sundress jumps and catches it.
[4s-5s] The grey-haired woman in the denim jacket claps and laughs.

Audio: a light ukulele at a cheerful tempo. Birds, laughter, the whoosh of the frisbee.

No text, subtitles, logos or watermarks.</pre></dd>
<dt>Взрыв и эффекты</dt><dd>Звук каждого события — в его строке таймлайна, без музыки.
<pre class="ex-code">Epic fantasy film look, dramatic dusk light, smoke and embers, high contrast.

Scene: a stone castle wall at dusk, burning torches along the battlements. An adult knight in dented steel armor and a helmet stands on the wall with a round shield.

Camera: wide shot, the camera shakes slightly.

Timeline:
[0s-2s] The knight raises his shield and looks up at the sky.
[2s-3s] A fireball hits the wall below him and explodes with a deafening boom.
[3s-5s] Stones and burning sparks fly through the smoke as the knight crouches behind his shield.

Audio: no music. A low rumble before the impact, a deafening explosion, falling stones, crackling fire and the clang of metal.

No text, subtitles, logos or watermarks.</pre></dd>
<dt>Музыкант в кадре</dt><dd>Длина 8 с. Музыку играет герой, её слышат все в сцене; музыки за кадром нет.
<pre class="ex-code">Realistic live-action cinematic look, warm streetlights at night, shallow depth of field, film grain.

Scene: a narrow old-town street at night, wet cobblestones. An adult man, about 50, with a grey beard and a black hat sits on a stool and plays an acoustic guitar. Passers-by walk past, blurred in the background.

Camera: medium shot, a slow arc shot around the musician.

Timeline:
[0s-5s] The musician plays a fast flamenco melody, his fingers moving quickly over the strings.
[5s-8s] He slaps the guitar body twice in rhythm and smiles.

Audio: the loud acoustic guitar of the street musician, footsteps on wet stones, distant voices, no background score.

No text, subtitles, logos or watermarks.</pre></dd>
<dt>Музыка за кадром</dt><dd>Музыка — инструментами, темпом и громкостью; звуки места — следом за ней.
<pre class="ex-code">Realistic live-action cinematic look, sunrise light, warm haze, film grain.

Scene: an empty desert road at sunrise, a red vintage car drives toward the camera, dust rising behind it.

Camera: wide shot, a slow pull out as the car approaches.

Timeline:
[0s-3s] The red car drives along the road toward the camera.
[3s-5s] The car passes close by the camera and leaves a cloud of dust.

Audio: a slow synthesizer pad joined by a steady electronic drum beat that gradually gets louder. The car engine hums, gravel crunches under the tires, the wind whistles.

No text, subtitles, logos or watermarks.</pre></dd>
<dt>Продолжение с кадра</dt><dd>Стартовый кадр — последний кадр предыдущего дубля («Продолжить с последнего кадра» под дублем).
<pre class="ex-code">Continue seamlessly from &lt;Picture 1&gt;.

Realistic live-action cinematic look, golden hour sunlight, shallow depth of field, film grain.

Scene: the same wooden pier at sunset, the same woman in the white linen shirt.

Camera: medium shot, static shot.

Timeline:
[0s-3s] She sits down on the edge of the pier.
[3s-5s] She dips her bare feet into the water.

Audio: gentle acoustic guitar at a slow tempo. Soft splashing, distant birds.

Keep her face, hair and outfit exactly the same. No text, subtitles, logos or watermarks.</pre></dd>
<dt>Природа</dt><dd>Пейзаж без людей: туман, лучи, зверь вдалеке.
<pre class="ex-code">Cinematic nature documentary look, soft morning light, high detail.

Scene: an empty pine forest at dawn, thick fog between the trees, sunbeams breaking through the branches.

Camera: wide shot, a slow tracking shot forward between the trunks.

Timeline:
[0s-3s] The sunbeams slowly brighten through the fog.
[3s-5s] A deer steps out from behind a tree in the distance.

Audio: no music, only birdsong, a light breeze in the pines and a twig cracking.

No text, subtitles, logos or watermarks.</pre></dd>
</dl>
<p>Ещё семь заготовок — только в меню «Заготовка ▾» лаборатории:</p>
<dl>
<dt>Все части, пустые</dt><dd>Каркас промта: все части с «...», которые надо заполнить.</dd>
<dt>Голос за кадром</dt><dd>8 с. Говорит рассказчица, губы героини сомкнуты (раздел «Речь и диалоги»).</dd>
<dt>Идёт к камере</dt><dd>Камера пятится перед героем; ночь, дождь, неон.</dd>
<dt>Танец для клипа</dt><dd>Сцена, свет, дымка, облёт камерой, бит.</dd>
<dt>Предмет крупно</dt><dd>Реклама: студийный свет, облёт, капля.</dd>
<dt>3D-мультфильм</dt><dd>Анимация вместо живой съёмки.</dd>
<dt>Старая плёнка</dt><dd>1970-е: выцветшие цвета, зерно, мерцание.</dd>
</dl>` },

  { id: "idea", group: "Идея", title: "Экран «Идея»", html: `
<dl>
<dt>Идея</dt><dd>Своими словами: кто, где, что происходит и чем кончается. Сценарист держится за конкретные детали — место, время суток, одежду, жест в конце.
${ex("Девушка гуляет вечером.", "Девушка в красном пальто идёт по ночной набережной под дождём, останавливается у фонаря и улыбается в камеру.",
  "Во втором варианте у сценариста есть место, свет, погода, одежда и финал — сцены выйдут связными.")}</dd>
<dt>Фото</dt><dd>Необязательно (png, jpg, webp). После загрузки выберите, что с ним сделать.
<br><b>Первый кадр</b> — ролик начнётся ровно с этого снимка: модель ролика его оживит, а сценарист сначала опишет, что на фото (поза, место, свет), и продолжит действие с этого момента.
<br><b>Только внешность</b> — сценарист опишет героя словами, сцены снимутся по тексту, фото в кадр не попадёт.
${ex("Вертикальное фото с телефона для ролика 16:9 — края обрежутся, голова может уйти за кадр.", "Снимок той же формы, что кадр ролика; если формы разные, нажмите «Взять 9:16» в предупреждении.")}</dd>
<dt>Модель</dt><dd>Кто будет снимать: H3 (голос на языке ролика, лица по фото), LTX 2.5 (быстро, свой звук), LTX 2.3 (может снимать под ваш трек — клипы), WAN 2.2 5B или WAN 2.2 5B · FastWan (только картинка). Что умеет каждая — таблица в <a href="#/help/video-models">«Модели видео»</a>. Сменить можно и потом, в раскадровке, и у каждой сцены.</dd>
<dt>Длина</dt><dd>От 15 секунд до 10 минут. Ролик делится на сцены по 5 с: 30 с — это 6 сцен. На LTX сцены по 10 с: 30 с — 3 сцены, 15 с — 10 + 5. Время съёмки зависит от модели: 30 с черновика на H3 — около 10 минут, на LTX — 3,5–4, на WAN — около 12.</dd>
<dt>Кадр</dt><dd>16:9 — горизонтальный, 9:16 — вертикальный для телефона, 1:1 — квадрат. Размер в пикселях у каждой модели свой: черновик 16:9 на H3 — 960×544, на LTX — 1024×576 (таблица в «Модели видео»).</dd>
<dt>Настроение</dt><dd>Кино, Клип, Реклама, Фэнтези и эффекты, Документальное. Задаёт стиль всего ролика: свет, цвет, темп, камеру.</dd>
<dt>Кто в кадре</dt><dd><b>Один герой</b> — один человек во всех сценах.
<br><b>Несколько</b> — 2–3 человека, у каждой сцены свой состав.
<br><b>Без людей</b> — пейзажи, предметы, эффекты. Вместо героя сценарист описывает «мир», а каждая сцена начинается тем, чем закончилась предыдущая.</dd>
<dt>Музыка и звук</dt><dd>Что должна сочинить сама модель, например «тёплый эмбиент, мягкое пианино» (WAN звука не делает). Пусто — только звуки сцены. Музыка в каждой сцене своя, поэтому мелодия от сцены к сцене меняется; одна музыка на весь ролик — это свой трек (раздел <a href="#/help/shoot">«Качество, LoRA, музыка, выход»</a>).</dd>
<dt>Расписать сцены</dt><dd>Создаёт ролик и запускает сценариста: 20–30 с на 30 с ролика, с фото чуть дольше. Раскадровка откроется сразу и заполнится, когда сценарист закончит.</dd>
<dt>Без сценариста</dt><dd>Переключатель «Свои промты» над формой: пустая раскадровка на нужную длину без языковой модели. Промт каждой сцены вы пишете сами по-английски; H3 получает его слово в слово, LTX и WAN — без пометок H3 (раздел <a href="#/help/prompt">«Как писать промт»</a>).</dd>
<dt>Как начать</dt><dd>Над формой — четыре способа: «Сценарист» (идея на вашем языке), «Клип» (из песни, раздел «Клип из песни»), «Свои промты» (пустая раскадровка) и «Граф» (холст из узлов; «Выбрать шаблон» открывает окно шаблонов, там же пустой холст).</dd>
<dt>Ваши ролики</dt><dd>Все проекты; сверху — поиск по названию и фильтры: вид (раскадровки, клипы, графы), модели (можно несколько — ролик подходит, если хоть одну его сцену сняла выбранная модель), кадр, состояние (готово, не снято, проверь сцены, не дописано, сейчас в работе) и порядок (изменены, созданы, длиннее, по названию). У каждого варианта — сколько роликов он оставит; выбор запоминается, «Сбросить» возвращает всё. На телефоне фильтры — под кнопкой «Фильтры».
На карточке значок вида (плёнка — раскадровка, нота — клип, слои — граф) и состояние: «сценарист пишет…», «снимается…», «проверь 2» — у двух сцен есть замечания, «не снято», «готово» с размером; у графа — «собирается…», «готово» или «не собран». «Сейчас в работе» — ролик, над которым идёт любая работа: пишет сценарист, снимаются сцены или дубли, собирается граф. Полоска под кадром — модели, снявшие ролик, каждая длиной в свою долю сцен (фиолетовая — H3, терракотовая — LTX 2.5, охра — LTX 2.3, зелёная — WAN, светло-зелёная — FastWan); вертикальный ролик показан целиком, на своём размытом фоне. «из Remiqora» — клип, перенесённый со снятыми сценами из старой Remiqora (папка remiqora-video-old). Корзина в углу удаляет ролик целиком.</dd>
</dl>` },

  { id: "clip", group: "Идея", title: "Клип из песни", html: `
<p>Второй переключатель на главной — «Клип». Сцены режутся не по 5 с, а по тактам песни, и сценарист пишет по её частям.</p>
<dl>
<dt>Песня</dt><dd>Загруженная песня сразу разбирается (около секунды): темп, такты, части — тихие (вступление, куплет, брейк) и громкие (дроп, припев). На волне громкие части подсвечены, припев — розовой чертой сверху, спетые строки — метками снизу. Щелчок по волне начинает клип с ближайшего такта. «Послушать» рядом с названием проигрывает кусок, который возьмёт клип, — по волне бежит белая отметка; пока играет, щелчок внутри рамки перематывает туда, а вне рамки переносит начало клипа на этот такт; «Стоп» — остановить. Песня хранится один раз, сколько бы клипов из неё ни делали.</dd>
<dt>Слова</dt><dd>Распознаются из самой песни: голос отделяется (Demucs), слова записываются со временем каждого (Whisper large-v3) — задача на видеокарте, около 40 с; сами — перед сценаристом, или кнопкой «Распознать слова» заранее. Распознанные слова можно поправить в поле и нажать «Сохранить свой текст»: он ляжет на время распознанных слов, даже с другой разбивкой на строки. Припев находится по повторяющимся строкам.</dd>
<dt>Сцены по тактам</dt><dd>Каждая часть песни — склейка. Внутри части сцены по целым тактам: в громкой около 3 с, в тихой вдвое дольше; не короче 1,5 с и не длиннее 8 с (и не длиннее, чем снимает модель: у WAN — 5 с). Сцена снимается чуть длиннее — до шага сетки кадров модели — и в монтаже режется ровно на свой такт. В клипах, сделанных с 30.10.2026, сцена со стартового кадра снимается ещё на 8 кадров раньше своего такта (под трек — с того же места песни), и эти кадры отрезаются: первые кадры такой сцены — почти неподвижная картинка, и на каждой склейке было видно «фото, потом поехало».</dd>
<dt>Типы сцен</dt><dd><b>Пение</b> — герой поёт, лицо крупно; только там, где звучит голос, и его реплика — слова, спетые в эти секунды (манера «поёт»). <b>Перформанс</b> — движение под музыку. <b>Вставка</b> — деталь без лица: руки, свет, дым, ткань. В пении и перформансе руки пустые и ниже плеч: без взмахов, без рук над головой, без предметов в руках, без кружения — у моделей видео руки и предмет в них «плывут». Движение — покачивание, поворот головы, плечи, волосы на ветру, шаг к камере; сценарий с такими руками отправляется сценаристу на правку.</dd>
<dt>Идея клипа</dt><dd>Необязательна. Сценарист сначала пишет тритмент — формат, палитру, мотив, который растёт к припеву, и что происходит в каждой части, — потом сцены. Ключевые слова строки берутся буквально.</dd>
<dt>Длина клипа</dt><dd>Кнопки под волной: «30 с», «45 с», «1 мин», «1,5 мин», «Вся песня». Рядом — отрезок песни и сколько примерно выйдет сцен (около одной на 4 с). Не помещается до конца песни — начало сдвигается назад.</dd>
<dt>Кто в кадре</dt><dd>Как на экране идеи: один герой, несколько или без людей.</dd>
<dt>Что пишет сценарист</dt><dd><b>Внешность героя</b>: «Сценарист» придумает её сам, «Опишу сам» — ваш текст (и пол героя), сценарист его только переведёт для модели, «По фото» — сценарист опишет внешность по фото певца, и поющие сцены начнутся с этого лица. <b>Сюжет клипа</b>: «Сценарист» придумает историю по частям песни, «Моя идея как есть» — возьмёт вашу идею без своих выдумок (идея тогда нужна). <b>Тексты сцен</b>: «Все» — сценарист пишет весь клип сразу; «Только пустые» и «Никакие: каркас» — сценарист не запускается, открывается каркас клипа. Всё написанное потом правится в каждой сцене.</dd>
<dt>Каркас клипа</dt><dd>На раскадровке «Показать» → «Каркас» (клип без написанных сцен открывается в нём сам): все сцены по песне — время, часть, слова, которые в ней звучат, тип и кто писал («вы», «сценарист», «пусто»). Свой текст в сцене делает её вашей и закрепляет: сценарист её не перепишет, только переведёт ваши слова в промт. Тип, выбранный здесь, тоже остаётся вашим. «Написать остальные» — сценарист пишет пустые сцены, опираясь на ваши, в первый раз ещё сюжет, героя и стиль.</dd>
<dt>Кадр</dt><dd>16:9, 9:16 или 1:1 — как на экране идеи.</dd>
<dt>Расписать клип</dt><dd>Создаёт клип и запускает сценариста (или, при «Только пустые» и «Никакие», сразу открывает каркас); оценка по скорости сценариста на этом компьютере, плюс 40 с, если слова ещё не распознаны. Раскадровка откроется сразу.</dd>
<dt>Модель</dt><dd>LTX 2.3 слышит свой кусок трека и делает губы под голос — поэтому по умолчанию клип снимает она. Если выбрать другую (H3 — лица по фото, LTX 2.5 — быстрее, WAN — без звука), поющие сцены всё равно снимет LTX 2.3 («Модель» у сцены), под формой это сказано. Звук ролика — сама песня; свой звук сцен выключен.</dd>
</dl>` },

  { id: "look", group: "Раскадровка", title: "Герои: кастинг, стиль и Ref2VA", html: `
<dl>
<dt>Название</dt><dd>Во вкладке «Съёмка», сверху; щёлкните по нему (рядом карандаш), чтобы исправить. Под ним — строка, как на хлопушке: сколько сцен, длина, кадр, настроение, сколько людей и за сколько сценарист написал сценарий.</dd>
<dt>Переписать незакреплённые</dt><dd>В виде «Сценарий» (над сценами: «Показать» → «Сценарий»), над списком сцен, со значком сценариста и числом сцен без замка. Сценарист заново пишет все сцены без замка; закреплённые остаются и служат ему опорой. Больше трёх сцен — сначала спросит.</dd>
<dt>Добавить сцену</dt><dd>В «Сетке» в конце каждого эпизода — плитка «+ Сцена»: продолжение в этот эпизод (начнётся с последнего кадра сцены перед ней), под ней «+ Новый эпизод после» — сцена со своим первым кадром и местом. В «Сценарии» — «Добавить сцену»: продолжение после выбранной. Сценарист сразу пишет новую сцену по соседним. В клипе новая сцена забирает вторую половину времени сцены перед ней (по ближайшему такту), и слова песни делятся между ними — остальные сцены остаются на своих местах в песне; сцену короче 3 с так не разделить, выберите другую.</dd>
<dt>Кастинг</dt><dd>Вкладка «Герои»: слева герои (когда их несколько; там же «Добавить героя», до трёх), в середине утверждённый портрет крупно, рядом пол, возраст, внешность и наряд — всё правится прямо на месте. Слова внешности и наряда вставляются в каждую сцену <b>дословно</b> — именно они держат лицо от сцены к сцене. Правили описание после портрета — у портрета жёлтый значок и строка «на портрете не та внешность» с кнопкой «Нарисовать по описанию»: сценарист переведёт описание, Krea нарисует четыре новых лица. Без людей вместо героев — «мир».
${ex("a woman with brown hair", "a 27-year-old woman with a dark chin-length bob, olive skin, brown eyes and a small mole on her left cheek",
  "Чем больше примет, тем меньше лицо меняется между новыми сценами. Замечание «описана слишком коротко» — о том же.")}</dd>
<dt>Поправить черты</dt><dd>Лицо то же, меняется деталь. Выберите черты — возраст, волосы, улыбку, макияж, свет — или напишите свою правку («рыжие волосы до плеч»), затем «Нарисовать 2 пробы». FLUX.2 Klein правит сам утверждённый портрет, поэтому лицо держится, и это работает и для своего фото; без FLUX.2 Krea рисует на зерне портрета. Свою правку сценарист сначала переведёт на английский. Утверждённая проба допишет правку во внешность (свет — нет: он только для проб). Около 30–60 с.</dd>
<dt>Другой человек</dt><dd>Новое лицо — сцены с героем переснимутся. «Новые лица по этому описанию» — четыре пробы Krea 2 по внешности, наряду, стилю ролика и месту первой сцены героя (описание правили — сначала его переведёт сценарист). «Описать заново» — правьте описание выше, потом «Нарисовать по описанию». «Своё фото» — ваша картинка становится портретом; «Описать по фото» перепишет по ней внешность.</dd>
<dt>Пробы</dt><dd>Все пробы остаются в проекте. Щелчок по пробе сравнивает её с утверждённым портретом: было, стало и что допишется во внешность; «Утвердить» делает её портретом (прежний остаётся среди проб, новое лицо перед этим спросит подтверждение), «Убрать пробу» — крестик. Проба, где детектор нашёл в кадре двоих или не нашёл лица, обведена жёлтым: Krea порой дорисовывает вторую фигуру за спиной. По портрету на H3 держит лицо Ref2VA, в клипе с него начинаются поющие сцены, с него FLUX.2 Klein рисует кадры сцен.</dd>
<dt>В сценах</dt><dd>Под пробами — снятые сцены с героем и сходство лица на последнем кадре каждой с портретом (SFace). Ниже порога — «другое лицо» в жёлтой рамке: такую сцену стоит переснять или нарисовать ей кадр. «Лица не видно» — герой спиной или далеко. Щелчок открывает сцену.</dd>
<dt>Все поля и EN</dt><dd>Под описанием и в строке «Голос» («Настроить») — полная форма: голос героя, фото, описание по-английски, как оно уходит в модель, «Обновить промт по тексту». В режиме «Несколько» героя можно убрать кнопкой «Убрать» рядом с его именем. После правки внешности переснимутся сцены с героем.</dd>
<dt>Фото героя</dt><dd>У каждого героя может быть своё фото. «Описать по фото» — сценарист опишет лицо, волосы, пол и возраст за ~10 с; одежда останется вашей. Само фото описание не меняет, пока не нажмёте кнопку.</dd>
<dt>Нарисовать кадры всем сценам</dt><dd>Каждой новой сцене с героем, у которого есть фото, FLUX.2 Klein рисует первый кадр: его лицо с фото в месте сцены, план и первое действие сцены (около 5 с на кадр, модель грузится один раз). Сцены стартуют с этих кадров — лицо и место держатся с первого кадра, а не придумываются моделью видео заново. Кадр, который уже был, заменяется, и эти сцены переснимаются. Мастер клипа рисует кадры сам, сразу после портрета певицы. Первая опора FLUX.2 Klein — лицо, вырезанное из портрета крупно, вторая — портрет целиком, третья — место; одежда героя вписывается в промт кадра дословно. Если лицо на кадре не похоже на героя, пробуются ещё сиды планом на ступень крупнее (общий → средний → крупный), лучший кадр остаётся, и план сцены становится его планом. Кадр, который так и не стал похож, помечается «кадр не похож на героя» на карточке и в «Перед съёмкой».</dd>
<dt>Перерисовать непохожие</dt><dd>Кнопка во вкладке героя и в «Перед съёмкой»: сцены, чей кадр не похож на героя, рисуются заново одной задачей. Новый кадр остаётся, только если его лицо ближе к фото героя, иначе остаётся старый. Мастер клипа делает этот шаг сам, после кадров.</dd>
<dt>Места</dt><dd>Картинка каждого места ролика — квартиры, улицы, крыши. Кадр сцены рисуется с ней второй опорой после фото героя, поэтому место остаётся тем же от сцены к сцене, а камера в нём своя у каждой сцены; без картинки FLUX.2 Klein рисует место по словам заново каждый раз. «Собрать места» — сценарист разложит новые сцены по 2–6 местам и опишет каждое как пустую декорацию (по-английски, для модели; правится в «Изменить»). «Нарисовать» — Krea 2 рисует место пустым, без людей (около 5 с), «Ещё вариант» — другой; «Своё фото» — ваша картинка вместо нарисованной. Место сцены выбирается в её панели («Место»). Сами места съёмку не меняют — меняется кадр, нарисованный с ними: после новой картинки места перерисуйте кадры его сцен. Мастер клипа собирает и рисует места сам, перед кадрами (галка «Места» в мастере). Галка «Рисовать кадры сцен в картинках мест» выключает их: кадры снова рисуются по словам, места и картинки остаются.</dd>
<dt>Голос героя</dt><dd>Образец 5–10 с чистой речи: «Файл», «Записать голос» с микрофона или «Из сцены…» — голос снятой сцены без музыки и шумов (Demucs, около минуты на видеокарте). «Образец с» и «Длина» — какой кусок взять. Сцены на LTX 2.3 (не под трек), где говорит только этот герой, снимаются с ID-LoRA этим голосом; под образцом видно, сколько таких сцен. Смена образца переснимает их.</dd>
<dt>Держать лицо по фото</dt><dd>Ref2VA: новые сцены снимает отдельная модель, которой фото героя служит образцом лица. Только для сцен H3: сцены LTX и WAN лицо по фото не держат. Видна, если у ролика есть фото. Модель тянет из снимка и обстановку.
${ex("Героиня в профиль на фоне лавандового поля — лицо видно плохо, а поле окажется в каждой сцене.", "Портрет анфас, лицо крупно, ровный свет, нейтральный фон.")}</dd>
<dt>На всех сценах</dt><dd>Эксперимент, выключен по умолчанию. Ref2VA снимает и продолжения: последний кадр закрепляется первым, а лицо каждый раз сверяется с фото. Лицо держится дольше, но голова может уходить за край кадра. Переключение переснимает весь ролик.</dd>
</dl>` },

  { id: "timeline", group: "Раскадровка", title: "Экран, эпизоды и цепочки", html: `
<p>Сверху — вкладки: «Сцены», «Героиня» (или «Герой», «Герои» — по героям ролика), «Места», «Песня» (у клипа) и «Съёмка»; под названием каждой — что внутри: сколько сцен и эпизодов, героев, мест, у «Съёмки» — длина, кадр и модель. Справа — сколько сцен снято, полоской, и одна главная кнопка: снять то, что осталось, или открыть готовый ролик. Справа от сцен — панель выбранной сцены (раздел «Панель сцены»). Любое фото проекта — портрет героя, пробы, места, первый и последний кадр сцены — открывается крупно по щелчку (у проб — кнопка ⤢ в углу): в окне ← → листают все фото проекта, внизу их лента, Esc закрывает.</p>
<dl>
<dt>Показать</dt><dd>Над сценами: «Сетка» — все сцены карточками по эпизодам (открывается сразу); «Кадр» — выбранная сцена крупно, её дубль играет; «Сценарий» — все сцены текстом, с поиском и фильтрами; «Граф» — те же сцены узлами на холсте.</dd>
<dt>Эпизод</dt><dd>Строка сетки — одна цепочка: новая сцена и продолжения после неё, снятые одним куском, кадр за кадром. На полях — номер эпизода, о чём он (из плана сценариста), время и сколько его сцен снято; щелчок по полям выбирает все сцены эпизода.</dd>
<dt>Почему в клипе сцены списком</dt><dd>В клипе сценарист режет сцены по тактам песни, и почти каждая начинается со своего кадра: новый ракурс, склейка на долю. Тогда каждая сцена — своя цепочка, эпизод из одной сцены, и сетка выглядит списком: номер на полях и одна карточка справа. В раскадровке с продолжениями, где сцена идёт с последнего кадра прошлой, сцены цепочки стоят в ряд. Например, клип из 12 сцен — 12 эпизодов по одной карточке, а раскадровка «Прогулка среди голубых цветов» из 6 сцен — 2 эпизода по три. Это не ошибка: так сетка показывает, что сцены сняты отдельно.</dd>
<dt>Новая сцена</dt><dd>Снимается из текста, в своём месте; открывает цепочку. Между цепочками — обычная монтажная склейка.</dd>
<dt>Продолжение</dt><dd>Снимается с последнего кадра предыдущей сцены: то же место, тот же момент, камера будто не выключалась.
${ex("В продолжении: «She walks into a different room.» — модель сделает резкий скачок посреди сцены.", "Новое место — это новая сцена; в продолжении действие идёт там же.")}</dd>
<dt>Правило цепочек</dt><dd>С людьми — не больше трёх продолжений подряд, потом новая сцена: иначе лицо постепенно уплывает. Сцены по 10 с (LTX) — не больше одного: цепочка так же около 20 с. Без людей весь ролик — одна цепочка.</dd>
<dt>Полоса внизу</dt><dd>При «Сетке» — карта ролика: эпизоды полосой, эпизод выбранной сцены в рамке; щелчок или протяжка — к сцене на этом месте ролика. При «Кадре» и «Сценарии» — дорожка: каждая сцена по своей длине, сцены цепочки вплотную. В длинном ролике дорожка в два этажа: сверху весь ролик с рамкой показанного куска, снизу этот кусок крупно; листается колесом, стрелками ← → по краям и протяжкой рамки. Двойной щелчок по сцене открывает «Сцену подробно».</dd>
<dt>Точка на карточке</dt><dd>Жёлтая точка — у сцены есть замечание (раздел «Пометка «проверь»»).</dd>
<dt>Цвета</dt><dd>На дорожке и карте фиолетовый и розовый просто чередуются, чтобы соседние цепочки различались; номер цепочки не важен. На карточках цвета нет: фиолетовая рамка — выбранная сцена.</dd>
</dl>` },

  { id: "cards", group: "Раскадровка", title: "Карточки и действия со сценами", html: `
<dl>
<dt>Как устроена</dt><dd>Кадр сцены — последний из последней съёмки; у ещё не снятой — её первый кадр с меткой «начало», если он есть, иначе штриховка. Метка «переснять» — сцену поменяли после съёмки: виден старый кадр, при съёмке она переснимется. Номер и длина, ниже две строки «что происходит» и кто их написал: «вы» или «сценарист». ▶ посередине снятой карточки играет выбранный дубль прямо здесь, со звуком; щелчок по видео — пауза. ⤢ в углу карточки или пробел открывают сцену крупно во всплывающем окне: дубль со звуком или кадр, «Дубль / Первый кадр», ← → к соседним сценам, «Подробно» — на всю страницу, Esc закрывает. Метка «лица не починены» — у сцены включена починка лиц, а дубль снят «Ещё дублем»: виден и играет сам дубль, лица починит «Снять ролик». Замок — сцена закреплена, жёлтая точка — замечание. Щелчок выбирает сцену, Ctrl добавляет к выбранным, Shift — подряд от выбранной; двойной щелчок или Enter открывает «Сцену подробно», ← → — соседняя сцена, Esc снимает выбор нескольких.</dd>
<dt>Несколько сцен</dt><dd>Выбрано больше одной (Ctrl, Shift или щелчок по полям эпизода) — справа общая панель: длина, камера и модель для всех, «Улучшить» и «Другой вариант» для всех, закрепить, удалить.</dd>
<dt>Ветка</dt><dd>Кнопка во вкладке «Съёмка», рядом с названием: копия ролика, чтобы попробовать другой дубль, модель или монтаж, не теряя этот. Снятые сцены берутся как есть — без пересъёмки и почти без места на диске; собранный ролик — нет. Под названием ветки — откуда она и чем отличается: какие сцены, настройки, свой монтаж.</dd>
<dt>Граф для ComfyUI</dt><dd>Свёрнутый блок на вкладке «Съёмка» панели сцены: граф, который уйдёт воркеру при новой съёмке, — без съёмки. Для отладки рецептов: какие узлы, какие входные файлы и откуда, ключ сцены, «Скопировать JSON».</dd>
<dt>Склейки внутри сцены</dt><dd>Галка на вкладке «Сцена» панели сцены (когда у неё 2–3 действия): каждое действие — свой план с жёсткой склейкой, общий → средний → крупный, начиная с плана сцены. H3 ставит склейку сам, по разметке шотов в промте; на 5 с обычно получается одна склейка, остальное — наездом, в сценах по 10–15 с — больше. Только H3 и только без реплик. Сцена переснимется; проверка клипа такую склейку браком не считает.</dd>
<dt>Улучшить</dt><dd>На странице «Сцена подробно» и в общей панели нескольких сцен: сценарист делает сцену конкретнее и нагляднее, сохраняя смысл.</dd>
<dt>Другой вариант</dt><dd>Там же: другое действие и ракурс, которые всё ещё вписываются в ролик.</dd>
<dt>Обновить сюжет от этой сцены</dt><dd>На вкладке «Сцена» панели сцены, блок «Сюжет». Вы поменяли сцену — например, героиня теперь уходит, а дальше по раскадровке они обнимаются. Сценарист читает весь ролик, называет сцены, которые с этой больше не сходятся (люди, место, предмет, что было до и после), с причиной для каждой, и переписывает только их: не больше 6, закреплённые и сцены со своим промтом не трогаются. Переписанные получают метку «от сцены N» (причина — в подсказке) и переснимутся. «Вернуть как было» возвращает их тексты. Реплики героев не меняются — проверьте их сами. Около 30 с.</dd>
<dt>Перетаскивание</dt><dd>В «Сценарии»: тяните строку сцены на другое место, чтобы поменять порядок. Первая сцена всегда становится новой.</dd>
<dt>Замок</dt><dd>Закреплённую сцену сценарист не трогает: ни кнопками, ни «Переписать незакреплённые», ни автоправкой. «Закрепить» — внизу панели сцены, на карточке закреплённой — замок. Сцену со своим промтом сценарист не переписывает вовсе.</dd>
<dt>Перевести на русский</dt><dd>Кнопка в «Сценарии», когда в раскадровке есть сцены на английском (клипы из Remiqora). Сценарист переводит, что происходит, и сам промт — для чтения: в модель по-прежнему уходит оригинал, снятое не переснимается. В панели сцены промт показан по-русски, «Показать оригинал» — то, что получает модель. Правка промта убирает перевод.</dd>
<dt>Подсказки в панели</dt><dd>«Текст изменён — промт ещё старый» — вы поправили «Что происходит», а английский промт прежний: нажмите «Обновить промт по тексту» под ним. Замечание «проверь» — раздел «Пометка «проверь»». «В клипе: замерло на 2,5 с» — автопроверка снятого клипа (ниже).</dd>
<dt>Кадр на карточке</dt><dd>Последний кадр сцены из последней съёмки. После правки он может быть старым, пока сцену не переснимут.</dd>
</dl>` },

  { id: "inspector", group: "Раскадровка", title: "Панель сцены", html: `
<p>Справа, у выбранной сцены. Сверху — её номер крупно, время и вид (новая или продолжение), ← → к соседним сценам и ⤢ — «Сцена подробно» на всю страницу. Под ними всегда на виду «Что происходит». Остальное — по вкладкам: «Начало» — с чего сцена начинается, её первый и последний кадр; «Сцена» — камера, план, длина, склейки внутри сцены и «Обновить сюжет»; «Съёмка» — модель, лица после съёмки, LoRA сцены, промт для модели и граф для ComfyUI; «Реплики» — кто в сцене и что говорит; «Дубли». Открытая вкладка остаётся, когда выбираете другую сцену. Внизу всегда — «Ещё дубль», «Закрепить» и корзина. На странице «Сцена подробно» те же поля идут подряд, без вкладок.</p>
<dl>
<dt>Что происходит</dt><dd>Сцена на вашем языке. Если текст изменить, появится «Обновить промт по тексту»: сценарист перепишет английский под него, а ваш текст оставит как есть.</dd>
<dt>Кто написал</dt><dd>Под текстом: «вы» — сцена ваша, «сценарист» — его, «пусто» — ещё не написана. Ваша сцена закрепляется сама: сценарист не тронет её, когда переписывает другие сцены («Обновить сюжет», «Написать остальные»). «Своими словами» ставит курсор в текст — пишите сами. «Переписать» отдаёт сцену сценаристу: он напишет её заново, замок снимется.</dd>
<dt>Камера</dt><dd>Статично, наезд, отъезд, сопровождение сбоку, камера пятится перед героем, следом сзади, облёт, панорама, подъём, с рук близко к лицу. Спокойные движения надёжнее; статичная камера бережнее всего к лицу. «С рук» — для поющей сцены LTX со стартового кадра: со статичной камерой она выходит почти стоп-кадром. В новых клипах поющие сцены крупным и средним планом получают её сами.</dd>
<dt>План</dt><dd>Общий, средний, крупный. Крупный лучше показывает лицо, общий — место.</dd>
<dt>Начало</dt><dd>Новая сцена (из текста, своё место) или продолжение — с последнего кадра предыдущей сцены или любой более ранней («Продолжение — с последнего кадра сцены N»). Второе — перебивка: показали другое и вернулись к моменту, где кончилась сцена N. Такая сцена открывает свою цепочку (перед ней — смена плана), а дрейф лица считается по кадрам: «с кадра сцены 2» — это третье продолжение, если сцена 2 сама второе. На карточке — «с кадра N».</dd>
<dt>Модель сцены</dt><dd>Какая модель снимает сцену и её продолжения: «как у ролика» или своя. Так в одном ролике сюжетные сцены с лицами снимает H3, пейзажи и действие — LTX 2.5 (втрое быстрее), пение под трек — LTX 2.3. Размер кадра у моделей разный: в ролике сцена приводится к кадру ролика. Снимается по моделям — каждая загружается один раз. У продолжения модели нет: оно снимается моделью своей цепочки, потому что начинается с её кадра.</dd>
<dt>Длина сцены</dt><dd>5, 10 или 15 секунд — сколько снимает модель сцены: LTX до 10 с, H3 до 15 с, WAN только 5. Раскадровка на LTX сразу пишется сценами по 10 с: 30 с — это 3 сцены, 15 с — 10 + 5. В такой сцене действия делят все 10 секунд, а реплики могут быть вдвое длиннее — около 20 слов. Длина входит в ключ: сменили — сцена и продолжения после неё переснимутся, сцены после неё сдвинутся.</dd>
<dt>Первый кадр</dt><dd>У новой сцены. «Нарисовать кадр» — FLUX.2 Klein рисует первый кадр сам: герой с его фото (лицо, волосы, одежда) в месте сцены, план и первое действие из сцены, около 5 с; лицо на кадре сверяется с фото, при промахе пробуется другой сид, а если не вышло и с третьего — под кадром предупреждение, «Перерисовать кадр» рисует снова. Сценарист такой кадр уже «видит» — переписывать не нужно. «Начать с фото» — сцена начнётся с вашего снимка, модель сцены его оживит; «С фото героя» — со снимка с экрана идеи. Затем обязательно нажмите <b>«Переписать под фото»</b>: сценарист посмотрит на снимок и напишет сцену из него.
<dt>Кто в кадре</dt><dd>Над первым кадром, для его рисования. «Как в сцене» — те, кого называет текст сцены, с лицами с их фото. Можно выбрать героев самому (несколько — щелчками) или «Никого»: тогда рисуется только место и то, что в нём происходит, без людей, лиц и рук — например, листья в лесу, даже если в английском промте сцены осталась героиня. Нарисованный кадр не меняется — нажмите «Ещё вариант».</dd>
${ex("Загрузили фото лавандового поля и сразу сняли. В тексте был луг под тучами — модель ушла от фото к тексту, и лицо стало другим.", "Загрузили фото → «Переписать под фото» → сцена начинается в том же поле, в той же позе.")}</dd>
<dt>Последний кадр</dt><dd>Только у LTX: «Прийти к кадру» — сцена закончится на вашей картинке. Опишите в промте, как она к ней приходит: движение камеры, действие. Модель, которая так не умеет, снимет сцену без него — это будет написано под картинкой. Кадр входит в ключ: сменили — сцена переснимется.</dd>
<dt>Кто в сцене</dt><dd>В режиме «Несколько»: галки — кто в кадре. В промт идут внешности только отмеченных, иначе модель рисует всех. У продолжения без галок — состав сцены, открывшей цепочку.</dd>
<dt>Реплики</dt><dd>Под каждым, кто в сцене, — что он говорит, на языке ролика, и как: обычно, тихо, шёпотом, кричит, с улыбкой, сердито… Пусто — молчит. Каждая реплика становится своей строкой таймлайна: <code>[1s-4s] Character 2 whispers, in Russian: "Прости."</code> — говорящий назван так же, как в описании героев («The heroine», «Character 2»), чтобы губы двигались у нужного лица. Действия сцены и реплики делят длину сцены: реплике — сколько нужно её словам (около 2,5 слова в секунду, не меньше 2 с), действиям — остальное. В звук добавляются голоса, остальное — тише них. Реплики видны и на карточке сцены. Счётчик «12 / 10 слов» над репликами — сколько слов у всех и сколько помещается (около 10 на 5 с, 20 на 10 с); больше — счётчик желтеет. На WAN над репликами предупреждение «… не говорит: реплики не прозвучат» — им нужен H3 или LTX.
${ex("«Ты опоздал. Я ждала тебя весь вечер, а ты даже не позвонил»", "«Ты опоздал. Я ждала весь вечер»", "В сцену 5 с помещается около 10 слов на всех; длиннее — речь пойдёт скороговоркой или оборвётся, сцена получит пометку «проверь».")}
«Придумать реплики» — сценарист предложит реплики тем, кто в сцене, по сюжету вокруг неё; ваши заменятся, править их можно сразу. Правка реплики переснимает сцену и продолжения после неё; сцены без реплик не меняются.</dd>
<dt>Действия по строкам</dt><dd>1–3 действия по-английски, по одному на строку; у H3 они ложатся на таймлайн <code>[0s-2s] [2s-4s] [4s-5s]</code>, LTX и WAN получают их предложениями по порядку. Правка закрепляет сцену.
${ex("<code>She walks forward slowly.</code>", "<code>She walks toward the camera, the wind lifting her hair.</code>",
  "Без направления к камере модель часто разворачивает людей лицом к нам, а ведёт от камеры — получается ходьба задом наперёд.")}
${ex("<code>She turns, then smiles and waves.</code>", "<code>She turns to the camera.</code><br><code>She smiles.</code><br><code>She waves.</code>",
  "Одно действие на строку: модель раскладывает их по секундам.")}</dd>
<dt>Промт для модели</dt><dd>Свёрнутый блок «Промт для модели, EN»: что получит модель сцены. Его собирает код из полей сцены, у каждой модели по-своему. H3 — по формуле: стиль, герой дословно, место, камера, таймлайн, звук и хвост (разбор по строкам в начале этой страницы). LTX — один абзац: стиль, место, кто там, действие от начала до конца, камера, звук с репликами. WAN — кто, где, движение, камера, стиль, без звука; у продолжения и сцены с фото — только движение и камера: остальное уже видно на кадре. Для LTX и WAN над текстом подпись «Получит LTX 2.5» (или другая модель): «при новой съёмке; из тех же полей, в порядке своей модели». Раскадровка хранит промт H3: вернёте H3 — снятое H3 возьмётся из кэша.</dd>
<dt>Свой промт</dt><dd>«Писать промт самому» переносит собранный промт в поле «Промт для модели, как есть», где его можно переписать целиком. H3 получает его слово в слово, LTX и WAN — без пометок H3 (раздел «Как писать промт»); сценарист сцену больше не трогает. «Заготовка» вставляет образец. «Вернуть промт сценариста» снова собирает его из полей.
<pre class="ex-code">Continue seamlessly from &lt;Picture 1&gt;.

Realistic live-action cinematic look, soft natural light, film grain.

Scene: the same rooftop at dusk.

Camera: medium shot, static camera.

Timeline:
[0s-2s] She leans on the railing and looks at the city.
[2s-5s] She turns her head toward the camera and smiles.

Audio: distant traffic, a light wind.

No text, subtitles, logos or watermarks.</pre>
Первая строка нужна только продолжению или сцене с фото: так H3 понимает, что начинать надо с готового кадра (LTX и WAN её не получают). Как писать свой промт, речь героя и слова для камеры — раздел <a href="#/help/prompt">«Как писать промт»</a>.</dd>
<dt>Дубли</dt><dd>Вкладка «Дубли». «Ещё дубль» (внизу панели) снимает эту сцену ещё раз с новым сидом — сейчас, одну (отдельная задача в очереди); прежние дубли остаются. Миниатюры — все дубли сцены: щелчок выбирает, какой пойдёт в ролик и в продолжения после неё (их кадр меняется — они переснимутся при «Снять ролик»); × убирает дубль из списка, файл остаётся в кэше и вернётся, если сид снова выберут. Продолжению для дубля нужен снятый кадр сцены, с которой оно идёт. На карточке — «дубль 2/3». В монтаже у клипа можно взять другой дубль, не трогая раскадровку.</dd>
<dt>LoRA сцены</dt><dd>«Как у ролика» — набор из панели съёмки; «Свои» — свой набор и сила только для этой сцены, из LoRA той модели, что её снимает; «Без LoRA» — сцена снимается без них. LoRA входит в ключ кэша: сменили — снимется эта сцена (и продолжения после неё), остальные — из кэша. На карточке — «своя LoRA» или «без LoRA».</dd>
<dt>Закрепить, Удалить сцену</dt><dd>Внизу панели, рядом с «Ещё дубль»: замок и корзина; время остальных сцен пересчитается.</dd>
</dl>` },

  { id: "check", group: "Раскадровка", title: "Пометка «проверь»", html: `
<p>После сценария каждую сцену проверяет код. Что не прошло, сценарист переписывает один раз сам; если не вышло — сцена получает пометку, а замечание видно на карточке. Сцену с пометкой можно снимать: это предупреждение, не запрет.</p>
<ul>
<li>В английском промте есть слова не по-английски.</li>
<li>Действий не 1–3, действие слишком короткое или длинное, или несколько действий через «then».</li>
<li>Ходьба без направления к камере — люди могут пойти задом наперёд; к камере и от камеры в одной сцене.</li>
<li>В действиях есть герой, которого нет в составе сцены, — его не будет в кадре.</li>
<li>Не сказано, чем заканчивается сцена — следующей не с чего начаться.</li>
<li>Нет описания сцены на вашем языке.</li>
<li>Реплики длиннее, чем помещается в сцену; реплика героя, которого нет в сцене.</li>
<li>Промт пуст (сцена со своим промтом).</li>
<li>Продолжение уходит в другое место — будет резкая склейка.</li>
<li>У новой сцены не описано место; не сказано, кто в сцене.</li>
<li>В кадре будет текст, вывеска или надпись.</li>
<li>Одежда меняется.</li>
<li>В ролике без людей появился человек.</li>
<li>Сцена начинается с фото, но сценарист его не видел.</li>
<li>Стиль или внешность описаны слишком коротко; одежда попала в описание внешности.</li>
<li>Только взрослые.</li>
</ul>
<p><b>В клипе: …</b> — после съёмки каждую новую сцену проверяет и сам клип (около секунды): чёрные кадры, «замерло», скачок внутри сцены, смаз или сильная перемена, лицо не похоже на старт, в клипе из песни — «не поёт» (губы стоят, а голос звучит). Когда в сцене один герой с фото, лицо сверяется с его портретом: медиана по пяти кадрам шота, на крупном и среднем плане ниже 0,3 — «лицо не как у героя» (общий план не судится: лицо мелкое). «Почти не движется» — сцена с людьми, где кадр едва меняется. Серьёзное — чёрное, замерло, скачок, долгий смаз, «не поёт», «лицо не как у героя» — переснимается один раз с другим сидом, в ролик идёт дубль с меньшими проблемами, а при равных — с лицом ближе к герою. Поющую сцену нового клипа, которая почти не движется, мастер переснимает один раз с камерой «с рук» и берёт более живой дубль. Остальное — строка «В клипе: замерло на 2,5 с» на карточке: посмотрите это место глазами.</p>` },

  { id: "graph", group: "Раскадровка", title: "Граф", html: `
<p>«Граф» в переключателе «Карточки / Граф» рядом с названием открывает ту же раскадровку на холсте: из чего снимается каждая сцена и куда она идёт дальше. Связи раскадровки правятся прямо на схеме: протяните «кадр» сцены к «старту» более поздней — она станет продолжением с этого кадра (перебивка и возврат); щелчок по связи выбирает сцену, в которую она ведёт; в панели сцены — «Начало», «Дубли» и «LoRA сцены». Всё сохраняется в раскадровку сразу. Текст, люди и камера — в карточках; отдельный граф с ветками и «Монтажом» — «Копия — проект-граф» вверху боковой панели, под названием (когда ничего не выбрано).</p>
<dl>
<dt>Узлы</dt><dd>Слева — герои (или мир в ролике без людей), стиль и LoRA. В середине — сцены: одна цепочка в строке, длинная цепочка переносится по 6 сцен. Справа — склейка, музыка и выход. Цвет шапки — кто работает: фиолетовый — модель снимает, зелёный — сценарист, синий — склейка и RTX, серый — ваши файлы.</dd>
<dt>Связи</dt><dd>Последний кадр сцены идёт в «старт» продолжения (цвет цепочки). Внешность героя идёт в «кто» той сцены, что открывает цепочку или меняет состав. Фото для Ref2VA идёт в «лица» — жёлтым пунктиром. Своё фото сцены — в её «старт». Каждая снятая сцена идёт в склейку. Стиль и LoRA действуют на все сцены, поэтому связей у них нет.</dd>
<dt>Состояние сцены</dt><dd>Те же слова, что на экране «Ролик»: «из кэша», «93 с», «шаг 5/8», «ждёт кадр». Ещё два слова есть только здесь: «переснимется» — сцена изменилась после съёмки, и «в кэше» — кадр с таким ключом уже снят, хотя готового ролика нет.</dd>
<dt>Щелчок по узлу</dt><dd>Подсвечивает его связи, остальное гаснет. Справа — видео сцены, откуда она стартует, кто в кадре, сид, ключ кадра и «Промт для модели». «Открыть в раскадровке» ведёт к этой сцене в карточках.</dd>
<dt>Холст</dt><dd>Колесо — масштаб, перетаскивание — сдвиг, как в ComfyUI. «Весь граф» показывает ролик целиком. Длинный ролик открывается на первых строках. «Перейти к сцене» справа приводит к сцене по номеру.</dd>
<dt>Копия — проект-граф</dt><dd>Делает из раскадровки новый проект-граф: каждая сцена — узел «Промт» с её промтом слово в слово и узел «Сцена» с её сидом. Ключи те же, поэтому снятые сцены берутся из кэша раскадровки, ничего не копируется и не переснимается. Сама раскадровка остаётся как была.</dd>
</dl>` },

  { id: "edit", group: "Съёмка и ролик", title: "Монтаж", html: `
<p class="lead">Четвёртый шаг: снятые сцены на таймлайне. Здесь режут начало и конец сцен, переставляют цепочки, ставят переходы и кладут свой трек. Ничего не переснимается — «Собрать ролик» склеивает сцены из кэша по монтажу.</p>
<dl>
<dt>Обрезка</dt><dd>Потяните левый край клипа — обрежется начало сцены, правый — конец; сцены после него сдвинутся сами, плеер покажет кадр на стыке. Точно — в панели клипа: «Начало» и «Конец» в секундах внутри шота, стрелки ‹ › — по кадру. Клип не короче 0,5 с. «Как было» возвращает сцену целиком.</dd>
<dt>Экран</dt><dd>Как в монтажной программе, весь в одном окне: сверху строка проекта — длина, сохранён ли монтаж и собран ли по нему ролик, одна главная кнопка: «Собрать ролик», а когда ролик собран по этому монтажу — «Открыть ролик»; под ней плеер над таймлайном, а сбоку панель — колонка во всю высоту, в четыре вкладки: «Клип», «Цвет», «Звук», «Вывод». Выделенное само открывает свою: клип, стык или кусок «Поверх» — «Клип», звук или трек — «Звук»; клип, выбранный при открытом «Цвете», остаётся на «Цвете» — красится он. Пустые дорожки «Поверх», «Музыка» и «Звуки» — тонкая строка со своим «+». Границу над таймлайном можно тянуть — плеер станет больше или меньше (двойной щелчок — как было). Панель двигается за ручку, как на других экранах: справа, слева или окном.</dd>
<dt>Стыки</dt><dd>Над каждым стыком двух клипов — значок того, что это за стык: <b>звено</b> цвета цепочки — без шва (продолжение с последнего кадра, картинка идёт дальше); <b>жёлтый треугольник</b> — скачок (стык цепочки обрезан, другой дубль перед продолжением или скорость не 1×); <b>черта</b> — склейка разных сцен; <b>искра</b> — вспышка; <b>два круга</b> — наплыв; <b>чёрная точка</b> — через чёрное. Щелчок по значку — стык в панели: два клипа по сторонам, почему он скачет, «Вернуть стык» (концы как сняты, тот же дубль, 1×) или «Спрятать наплывом», переход и его длина, «Проиграть стык» — с полутора секунд до него (двойной щелчок по значку — то же). <kbd>Delete</kbd> на стыке убирает переход. Ничего не выбрано — в панели список скачущих стыков.</dd>
<dt>Переходы</dt><dd>У каждого стыка: <b>склейка</b> (встык), <b>вспышка</b> (склейка с белой вспышкой на 4 кадра, длину не меняет; в клипе из песни так по умолчанию входят в громкую часть), <b>наплыв</b> (картинка и звук смешиваются) или <b>через чёрное</b>; длина перехода — 0,2–2 с. Наплыв укорачивает ролик на свою длину: сцены заходят друг на друга. У выбранного клипа в панели — строка «Стык перед клипом», щелчок ведёт к стыку.</dd>
<dt>Цепочки</dt><dd>Продолжение начинается с последнего кадра прошлой сцены, поэтому сцены цепочки всегда стоят вместе: потяните клип — переедет вся цепочка, синяя черта покажет куда. Стык внутри цепочки без обрезки — без шва (звено над стыком). Обрезали такой стык — картинка скакнёт: над стыком жёлтый треугольник, «Вернуть стык» в панели стыка вернёт как было.</dd>
<dt>Разрез, копия, убрать</dt><dd><kbd>S</kbd> (или «Разрезать») режет клип там, где стоит плейхед: две части одной сцены, вторая продолжает первую без шва — каждую можно обрезать, переставить внутри цепочки копией, замедлить. <kbd>Ctrl</kbd> <kbd>D</kbd> — копия клипа сразу после него (повтор момента, «стоп-кадр» из замедленной копии). <kbd>Delete</kbd> — убрать клип; если у сцены не осталось клипов, она уходит из ролика, но остаётся в раскадровке — в панели монтажа «Убраны из ролика» её вернут на место.</dd>
<dt>Дубли</dt><dd>Если у сцены несколько дублей («Ещё дубль» в раскадровке), в панели клипа — «Дубль» с миниатюрами: клип может взять любой, раскадровка не меняется (★ — дубль раскадровки, с его кадра начинаются продолжения). Другой дубль перед продолжением — стык скакнёт; две части одного дубля — без шва. На клипе — значок «д».</dd>
<dt>Скорость</dt><dd>0,5–2× у каждого клипа: картинка и звук сцены замедляются или ускоряются вместе (звук — без смены высоты). На клипе — значок «2×»; длина в ролике меняется, сцены после него сдвигаются. Стык с другой скоростью — не без шва: над стыком жёлтый треугольник.</dd>
<dt>Отмена</dt><dd><kbd>Ctrl</kbd> <kbd>Z</kbd> отменяет любую правку монтажа, даже «Как в раскадровке»; <kbd>Ctrl</kbd> <kbd>Shift</kbd> <kbd>Z</kbd> или <kbd>Ctrl</kbd> <kbd>Y</kbd> — повторить. Быстрые правки подряд (ползунок) — один шаг. Кнопки отмены и повтора — над таймлайном. <kbd>Esc</kbd> снимает выделение, <kbd>M</kbd> включает и выключает «Магнит». Все клавиши — «Клавиши» в строке проекта или <kbd>?</kbd>.</dd>
<dt>Звук сцен</dt><dd>Идёт с картинкой своей сцены. Громкость — своя у каждого клипа (0–200 %, ползунок «Звук сцены»): тише фон под репликой соседней сцены, громче тихая реплика. На дорожке — волна звука. Звук режется целыми кадрами вместе со своей картинкой и нигде не сдвигается — реплики остаются на губах. На склейке — короткое сглаживание 0,03 с против щелчков, на наплыве — смешивание.</dd>
<dt>Музыка</dt><dd>Ваш трек — тот же, что на экране «Ролик»: громкость, «звук сцен под ним», с какой секунды начать, нарастание и затухание. Щелчок по дорожке «Музыка» — эти настройки в панели. Нет трека — «Свой трек». <b>Уступает сценам</b> — ползунок 0–100 % («нет» — выключено): трек сам становится тише там, где сцены звучат громко (реплика, крик), и возвращается в паузах (компрессор по звуку сцен, на 100 % — 10:1); слышно в собранном ролике, в предпросмотре — нет.</dd>
<dt>Магнит</dt><dd>Кнопка над таймлайном, есть, когда в ролике свой трек; <kbd>M</kbd> — то же. Включён — обрезка клипа и звук прилипают к ближайшей доле трека, а на линейке времени видны доли и такты (когда масштаб позволяет). Выбор запоминается в этом браузере.</dd>
<dt>Склейки на доли</dt><dd>Там же: каждая склейка встаёт на долю трека перед ней — клип укорачивается меньше чем на долю. Стыки цепочек без шва не трогаются. Уже на долях — так и скажет.</dd>
<dt>Звуки</dt><dd>Дорожка «Звуки» — ваши файлы (mp3, wav, m4a, flac, ogg): «+ Звук» кладёт файл туда, где стоит плейхед. Звук тянется по дорожке, края обрезают его начало и конец; в панели — с какой секунды ролика, громкость, нарастание, затухание, копия. Звуки ложатся поверх звука сцен и трека; файлы хранятся в папке проекта <code>sounds</code>.</dd>
<dt>Поверх</dt><dd>Дорожка «Поверх» над видео: кусок шота любой сцены ролика (любой её снятый дубль) закрывает картинку на своём отрезке, а звук, длина ролика и склейки остаются как были — вставка, другой дубль поверх, перебивка без пересборки монтажа. «+ Поверх» кладёт к плейхеду кусок сцены под ним — другой её дубль, если он снят; в панели — сцена, дубль, с какой секунды ролика и какой кусок шота. Тянется по дорожке (магнит — к долям), края обрезают. Цвет ролика ложится и на него; в DaVinci уходит на дорожку V2 без звука.</dd>
<dt>Цвет ролика</dt><dd>Вкладка «Цвет» панели монтажа: сверху общий стиль — один цвет на все сцены: «Как снято», «Плёнка», «Тёплый», «Холодный», «Бирюза и оранж», «Чёрно-белый» или свой LUT — «Загрузить LUT (.cube)». <b>Выровнять сцены по цвету</b> — каждый клип подтягивается по цвету и контрасту на 60 % к среднему по ролику: сцены разных моделей и дублей перестают прыгать по цвету. Видно в собранном ролике, предпросмотр показывает как снято. Кадры не добавляются и не пропадают — склейки на месте. Ниже — <b>Сила LUT</b> (своя таблица не целиком, а частью: 50 % — наполовину), <b>Виньетка</b> (темнее к углам) и <b>Зерно плёнки</b> (новое в каждом кадре; в предпросмотре — неподвижное), на весь ролик. <b>До / после</b> — держите кнопку: плеер покажет ролик как снято, без всего цвета; отпустите — снова с цветом.</dd>
<dt>Плеер</dt><dd>Играет монтаж в браузере: два видео по очереди, наплыв и чёрное — прозрачностью, звук сцен и трек со своей громкостью. Пробел — играть / пауза, ← → — кадр, Shift + ← → — секунда, Home / End — начало и конец. На стыке может чуть запнуться — в собранном ролике всё точно.</dd>
<dt>Собрать ролик</dt><dd>Задача очереди, как «Снять ролик»: несняты сцены — снимутся, остальное из кэша; потом склейка по монтажу, трек, 1080p / 4K / HDR / 48 fps. Кнопка всегда в строке проекта, рядом — собран ли ролик по этому монтажу («Ролик собран по монтажу», «по прежнему монтажу», «не собран», «Есть неснятые сцены» — тогда «Снять и собрать»). На экране «Ролик» после правок монтажа — «Собрать по монтажу».</dd>
<dt>Связь с раскадровкой</dt><dd>Монтаж хранится в проекте, сцены в нём — по своему номеру, который не меняется. Переснятая сцена остаётся тем же клипом со своими обрезками; удалённая уходит; новая встаёт после сцены перед ней. «Как в раскадровке» стирает правки монтажа. Без правок ролик собирается так же, как всегда.</dd>
<dt>Для DaVinci Resolve</dt><dd>Кнопка в панели монтажа (ничего не выделено) спрашивает папку (в следующий раз окно откроется там же), создаёт в ней папку «Имя ролика · Resolve» с таймлайном FCPXML и файлами, которые он играет, и открывает её. Повторная выгрузка пересоздаёт эту папку. Если там уже есть чужая папка с таким именем, она не трогается: выгрузка ляжет в «… 2». В Resolve: File → Import → Timeline. Сцены идут на видеодорожку со своим звуком, с обрезками, скоростью, наплывами и громкостью. Трек и звуки ложатся на свои дорожки, с громкостью и фейдами. Вспышка становится маркером. Приглушение трека и цвет ролика не переносятся: в Resolve их делают по-своему, а свой LUT кладётся рядом с таймлайном. Неснятая сцена приходит пустым местом своей длины с подписью «Сцена N — не снята»: снимите её и выгрузите заново. Монтаж графа так пока не выгружается.</dd>
</dl>` },

  { id: "graph-edit", group: "Граф", title: "Проект-граф", html: `
<p class="lead">Ролик, собранный из узлов на холсте: сцены, фото, LoRA, склейки, музыка и выходы, а связи между ними любые. Граф нужен для веток и версий: две концовки из общих сцен, короткая и длинная версия, сцена, которая стартует с кадра любой другой. Для прямого ролика «идея → сцены» раскадровка проще.</p>
${GRAPH_DIAGRAM}
<div class="tip"><b>Как начать.</b> «Граф» среди способов начать на главной, затем «Выбрать шаблон» — шаблон или пустой холст с одной сценой. Первый раз проще всего с шаблона «Идея → сценарист → ролик»: идея и героиня уже вписаны и соединены со Сценаристом, заметка рядом говорит, что нажимать. «Копия — проект-граф» из раскадровки — та же раскадровка узлами, все снятые сцены берутся из её кэша.</div>
<ol class="flow steps">
  <li><b>Добавьте узлы</b><p>«Добавить» над холстом — у каждого узла значок и строка, для чего он. Если какой-то узел выделен, новый встанет рядом и сам свяжется с ним, когда порты подходят: выделите Идею и добавьте Сценариста — «текст» уйдёт в «идею». Ничего не выделено — узел встанет в середину экрана. «Шаблоны» — готовый кусок графа. Узлы двигаются мышью, панель справа правит выбранный.</p></li>
  <li><b>Смотрите «Дальше»</b><p>У выбранного узла в панели — «Дальше»: следующий шаг именно для него («Подключите Идею», «Нажмите «Написать»», «Развернуть в сцены», «Соедините «сцена» со Склейкой»). Чего узлу не хватает, видно и на самой карточке — пунктирной плашкой.</p></li>
  <li><b>Свяжите порты</b><p>Тяните от выхода справа к входу слева <b>того же цвета</b>: текст к тексту, картинка к картинке. Квадратный вход принимает несколько связей, круглый — одну: новая заменит старую.</p></li>
  <li><b>Снимите</b><p>«Снять всё» в панели проекта снимает то, что нужно выходам, остальное берёт из кэша. «Снять до сюда» у узла — только его и то, что ему нужно.</p></li>
  <li><b>Пробуйте варианты</b><p>«Ещё дубль» у сцены, «Дублировать ветку» для второй концовки, несколько выходов — несколько версий ролика.</p></li>
</ol>
<h3>Клавиши</h3>
<div class="keys-grid">
  <span><kbd>Shift</kbd> + рамка</span><span>выделить несколько узлов</span>
  <span><kbd>Ctrl</kbd> + щелчок</span><span>добавить узел к выделению</span>
  <span><kbd>Ctrl</kbd> <kbd>A</kbd></span><span>выделить всё</span>
  <span><kbd>Esc</kbd></span><span>снять выделение</span>
  <span><kbd>Delete</kbd> <kbd>Backspace</kbd></span><span>удалить выделенное</span>
  <span><kbd>Ctrl</kbd> <kbd>C</kbd> · <kbd>Ctrl</kbd> <kbd>V</kbd></span><span>копировать и вставить — со связями между узлами</span>
  <span><kbd>Ctrl</kbd> <kbd>D</kbd></span><span>дублировать выделенное</span>
  <span><kbd>Ctrl</kbd> <kbd>Z</kbd></span><span>отменить</span>
  <span><kbd>Ctrl</kbd> <kbd>Shift</kbd> <kbd>Z</kbd> · <kbd>Ctrl</kbd> <kbd>Y</kbd></span><span>повторить</span>
  <span><kbd>?</kbd></span><span>лист клавиш — тот же список в отдельном окне (кнопка «Клавиши» над холстом)</span>
</div>
<p class="note">Клавиши работают на любой раскладке. В поле ввода они остаются за полем: <kbd>Ctrl</kbd> <kbd>A</kbd> там выделяет текст. Шаг отмены — одно сохранение графа, пауза в наборе текста тоже шаг.</p>
<h3>Подробнее</h3>
<dl>
<dt>Снять всё</dt><dd>Одна задача в очереди. Порядок — картинки, потом сцены (сцены одной модели подряд и сцены с Ref2VA подряд, чтобы реже менять модель), «Видео → видео», «Звук сцены», кадры, склейки и монтажи, музыка, выходы. Ошибка останавливает только свою ветку, остальные доснимаются. «Остановить после текущего узла» — как на экране «Ролик».</dd>
<dt>Снять до сюда</dt><dd>У выбранного узла: снимает его и всё, что ему нужно, и ничего после.</dd>
<dt>Кэш и ключи</dt><dd>У каждой сцены ключ из промта (в том виде, в каком его получит модель), сида, размера, длины, модели, LoRA, стартового и последнего кадра, фото для Ref2VA и образца голоса — те же, что в раскадровке. Поправили сцену — меняется её ключ и ключи всех, кто стартует с её кадра; соседние ветки не трогаются. Узел с новым ключом показывает «к съёмке».</dd>
<dt>Сценарист и герой</dt><dd>Работают только по кнопке: «Написать», «Описать по фото». Если вход изменился, узел помечается «Переписать». «Переписать устаревшие» справа запускает все такие узлы одной задачей — модель сценариста загружается один раз.</dd>
<dt>Длина сцены</dt><dd>У каждой сцены своя: 3–15 с, но не дольше, чем снимает модель графа (LTX — 10 с, WAN — 5 с); по умолчанию 5 (ползунок и кнопки 3 · 5 · 8 · 10 · 15 в панели сцены). Длина входит в ключ: сменили — сцена переснимется. Таймлайн полей промта тянется под длину сцены, которую он кормит; «Кадр в момент» — в пределах её длины. H3 учили на 5–15 с: 3–4 с снимутся, но это вне её привычного.</dd>
<dt>Реплики</dt><dd>В панели «Промта» — раздел «Реплики»: кто говорит, как и что, на языке ролика. «Кто» — как герой назван в промте: <code>The heroine</code>, <code>Character 2</code>, <code>The man</code> (подсказки — из текста). Сервер вставляет реплику в таймлайн отдельной строкой (<code>[1s-3s] The man says with a smile, in Russian: "…"</code>), голос — первым в строку <code>Audio:</code>; у сцены «Промт с репликами» показывает, что получит модель. Около 2 слов на секунду сцены. «Придумать» — сценарист прочитает промт и предложит реплики тем, кто в нём есть (по кнопке). Реплики из раскадровки при «Копия — проект-граф» и из сценариста при «Развернуть в сцены» попадают сюда же, а ключи сцен не меняются.</dd>
<dt>Дрейф лица</dt><dd>С людьми лицо понемногу уплывает, если сцены снова и снова стартуют с кадра предыдущей. Как в раскадровке, после трёх продолжений подряд сцена показывает «лицо может уплыть»: начните новую сцену или подключите фото героя во вход «лица» — Ref2VA (только H3) сверяет лицо с фото, и счёт начинается заново. Без людей в промте предупреждения нет.</dd>
<dt>Дубли</dt><dd>«Ещё дубль» у сцены снимает её ещё раз с другим сидом. Все дубли лежат в кэше, выбранный идёт в склейку и в продолжения после неё. «Очистить дубли» убирает в корзину Windows невыбранные дубли и файлы, на которые больше не ссылается ни один узел.</dd>
<dt>Дублировать ветку</dt><dd>Копирует узел и всё, что после него, с промтами скопированных сцен и связями, которые входят в ветку снаружи. Так из сцены 3 получается вторая концовка: копия сцены, своя склейка и свой выход, а сцены 1–2 общие и снимаются один раз.</dd>
<dt>Упорядочить</dt><dd>Кнопка над холстом: узлы встают по потоку слева направо — идея и герои, промты, сцены, склейка и выход; то, что только кормит другой узел (трек, LoRA, фото), — прямо перед ним. Цепочки сцен раскладываются каждая своим рядом, много цепочек — в несколько столбцов, хвост ролика справа. Группа упорядочивается внутри и встаёт блоком, рамка подгоняется; заметки — строкой сверху. Выделено два узла или больше — только они. Ctrl+Z возвращает как было.</dd>
<dt>Шаблоны</dt><dd>Кнопка «Шаблоны» над холстом открывает окно: у каждого шаблона — граф в миниатюре, что в нём («4 сцены · 2 выхода · трек»), «Вставить» и «JSON». Встроенных 16, от простых к сложным: «Идея → сценарист → ролик» (первый), цепочка из трёх сцен, две концовки, короткая и длинная версия, оживить фото, картинка → сцена, одно лицо в разных местах (Ref2VA), диалог двоих, другой ракурс с середины, три дубля и лучший, свой стиль через LoRA, клип под свой трек, трейлер из пяти мест, пейзаж одной цепочкой, сценарист, сценарист и лицо по фото. В каждом — заметка, что сделать сначала. На главной «Граф» → «Выбрать шаблон» открывает то же окно: граф из шаблона или пустой.</dd>
<dt>Шаблоны в JSON</dt><dd>«Сохранить как шаблон» — выделенные узлы (или весь граф) становятся вашим шаблоном в <code>data\\graph_templates</code>. «Скачать как JSON» и «JSON» на карточке — файл, который можно поправить, отдать другому или хранить у себя. «Загрузить из JSON» — файл снова становится вашим шаблоном; занятое имя получает «(2)», узлы неизвестных типов и связи между портами разного цвета пропускаются, сообщение скажет, сколько. Принимается и <code>graph.json</code> проекта. Файлы проекта (фото, треки) и результат сценариста в шаблон не попадают — загрузите их в узлы заново.</dd>
<dt>Собрать раскадровку</dt><dd>Только из прямого графа: один выход, одна склейка, каждая сцена по 5 с стартует с ничего, с фото или с предыдущей сцены, LoRA у всех одинаковые. Лица Ref2VA становятся героями раскадровки с фото (у героя из узла «Герой» — его внешность), и каждая сцена помнит свои лица в своём порядке. Получается новая раскадровка со своими промтами, теми же сидами и ключами; снятые сцены в ней уже есть.</dd>
</dl>` },

  { id: "graph-nodes", group: "Граф", title: "Узлы графа", html: `
<p class="lead">Каждый узел делает одно дело. Цвет шапки — кто работает, цвет порта — что по нему идёт; связать можно только порты одного типа (у «сцены» и «ролика» цвет один, синий, но связать их нельзя).</p>
<div class="legend-row">${WHO_CHIPS}</div>
<div class="legend-row">${PORT_CHIPS}</div>
<h3>Сценарист</h3>
<dl class="node-cards">
${nodeCard("Идея", "user", "bulb", [], [["текст", "text", "пара фраз на вашем языке — во вход «идея» Сценариста"]], "О чём ролик, на вашем языке. «Перевести в промт» — когда идею хочется снять сразу, без сценариста: он переведёт её в английский промт модели графа, рядом встанет узел «Промт», а связи идеи со сценами и картинками перейдут на него.")}
${nodeCard("Герой", "writer", "user", [], [["внешность", "look", "описание героя — во вход «герои» Сценариста"], ["картинка", "image", "фото героя — во вход «лица» Сцены (Ref2VA)"]], "Фото, пол, возраст, внешность и одежда по-английски. «Описать по фото» заполняет их по кнопке. Можно описать героя на своём языке и нажать «Перевести на английский» — сценарист разложит описание на внешность и одежду.")}
${nodeCard("Сценарист", "writer", "quill", [["идея", "text", "о чём ролик — из узла «Идея»"], ["герои", "look", "кто в кадре — из узлов «Герой», можно несколько"]], [], "Пишет раскадровку по идее и героям («Написать»). «Развернуть в сцены» ставит справа промты и сцены, склейку и выход; после «Переписать» те же узлы получают новые тексты, сиды остаются.")}
</dl>
<h3>Сцены</h3>
<dl class="node-cards">
${nodeCard("Промт", "user", "text", [], [["текст", "text", "английский промт — во вход «промт» Сцены, Картинки или «Видео → видео»"]], "Что в кадре и что говорят герои — для модели графа (H3, LTX или WAN), текстом или по полям, как в лаборатории. Строка «Continue seamlessly from &lt;Picture 1&gt;.» добавляется сама, если сцена стартует с кадра. «Реплики» — что говорят герои, на языке ролика; встают в таймлайн и звук.")}
${nodeCard("Фото", "user", "image", [], [["картинка", "image", "во «старт» Сцены — первый кадр (обрежется под кадр); в «лица» — лицо для Ref2VA"]], "Ваша картинка с диска.")}
${nodeCard("Картинка", "krea", "brush", [["текст", "text", "что нарисовать — из «Промта» или «Идеи»"], ["образцы", "image", "только у FLUX.2 Klein: фото, герой или другая картинка (до трёх); у Krea 2 этого входа нет"]], [["картинка", "image", "нарисованный кадр — во «старт» Сцены"]], "<p>Рисует кадр для «старта» Сцены. Модель — в поле «Кто рисует».</p><ul class='nc-opts'><li><b>Krea 2</b>Только по промту, в размер финального кадра ролика (в черновике сцена берёт её уменьшенной). Около 3,5 с (первая картинка после видео — около 10 с). Можно добавить LoRA Krea с силой.</li><li><b>FLUX.2 Klein</b>По промту, по образцам со входа «образцы» или по тому и другому, около 4 с:<ul><li>без образцов — картинка по тексту;</li><li>с образцами — то же лицо, волосы и одежда в новом месте и ракурсе;</li><li>правка самой картинки: «замени фон на пляж, остальное то же» — переводчик оставит кадр образца;</li><li>без промта — новое фото человека с первого образца.</li></ul>В промте образцы зовутся «the first image», «the second image». Своя LoRA — из папки «Модели и настройки» → FLUX.2 Klein.</li></ul><p class='nc-note'>Промт, который питает и Сцену, и Картинку, переводится дважды: сцене — в форме видеомодели, картинке — как стоп-кадр для её модели (поле «Для картинки» у Промта).</p>")}
${nodeCard("Сцена", "h3", "clapper", [["промт", "text", "что в кадре и что говорят — из узла «Промт»"], ["старт", "image", "первый кадр: «Фото», «Картинка» или «Кадр» прошлой сцены"], ["конец", "image", "кадр, к которому сцена придёт — только LTX"], ["лица", "image", "фото героя: лицо держит Ref2VA — только H3"], ["LoRA", "lora", "наборы LoRA из узла «LoRA»; LoRA по образцу меняет и модель съёмки"], ["сцена", "clip", "клип-образец для IC-LoRA и Ref2VA-LoRA — длина и кадр берутся его"], ["голос", "audio", "образец голоса для ID-LoRA — из «Трека» или «Звука сцены»"]], [["кадр", "image", "последний кадр — во «старт» следующей сцены"], ["сцена", "clip", "снятый клип — в Склейку, Монтаж, Кадр, Звук сцены или «Видео → видео»"]], "<p>Снимает модель графа: H3 — 3–15 с, LTX — до 10 с, WAN — 5 с без звука; по умолчанию 5 с. Без «старта» — по промту с нуля, со «стартом» — с картинки, с «концом» — приходит к картинке.</p><p><b>По образцу.</b> LoRA, которая читает образец, ставится во вход «LoRA» (в узле «LoRA» — группа «По образцу»), и сцену снимает модель этой LoRA:</p><ul class='nc-opts'><li><b>IC-LoRA и Ref2VA-LoRA H3</b>Переделывают клип со входа «сцена»: Alpha-Gen, 3DREAL, CrossView, апскейл.</li><li><b>ID-LoRA LTX 2.3</b>Снимает говорящего героя: лицо со «старта», голос — кусок «Трека» во входе «голос» (с какой секунды и сколько — в панели сцены, лучше 5 с). Промт — из [VISUAL] / [SPEECH] / [SOUNDS] или обычный текст с репликами. Сходство голоса меряет WeSpeaker: «похож» — от 0,6, «не похож» — ниже 0,4, между ними «отчасти»; музыка в образце занижает оценку.</li></ul><p class='nc-note'>Снятый клип проверяется, как в раскадровке: «В клипе: …» в панели и плашка на узле. Дубли, продолжения и монтаж — как у любой сцены.</p>")}
${nodeCard("Видео → видео", "v2v", "film", [["сцена", "clip", "клип, который переделать — из Сцены или другого «Видео → видео»"], ["промт", "text", "если LoRA просит промт — из узла «Промт»"], ["картинка", "image", "персонаж для замены (Character-Swap) — из «Фото»"], ["LoRA", "lora", "LoRA с силой — из узла «LoRA»"]], [["сцена", "clip", "переделанный клип — в Склейку, Монтаж, Кадр или следующий «Видео → видео»"]], "<p>Клип заново через LoRA, которая читает сам клип. LoRA выбирается в узле:</p><ul class='nc-opts'><li><b>IC-LoRA для LTX 2.5</b>Alpha-Gen — убрать фон, Restore, Deblur…</li><li><b>IC-LoRA для LTX 2.3</b>3DREAL — 3D-рендер в фотореализм, CrossView — другая точка съёмки, апскейлеры — клип крупнее.</li><li><b>Ref2VA для H3</b>Character-Swap — заменить героя на персонажа с картинки.</li></ul><p><b>Прозрачный фон.</b> Alpha-Gen даёт маску и клип с прозрачным фоном. В панели узла он скачивается для монтажа (MOV ProRes 4444: DaVinci, Premiere) и для веба (WebM: браузеры, OBS). Обычный плеер прозрачность не показывает и играет клип целиком.</p><p class='nc-note'>Как запускать LoRA, говорит её профиль: нужен ли промт и с какого слова он начинается, одна или две стадии, сколько кадров за раз, во сколько раз итог больше клипа. Свой профиль — файл &lt;имя&gt;.v2v.json рядом с LoRA. Клип длиннее, чем LoRA берёт за раз, идёт кусками. В сцены такие LoRA не ставятся: там они дают плоскую картинку.</p>")}
${nodeCard("Лица", "facefix", "face", [["сцена", "clip", "снятый клип — из Сцены или «Видео → видео»"], ["промт", "text", "кто в кадре: внешность героя по-английски — из «Промта» или своим текстом в панели"]], [["сцена", "clip", "клип с починенными лицами — в Склейку, Монтаж или дальше"]], "<p>Мелкие далёкие лица в снятой сцене — резче и одинаковые от кадра к кадру. Около 2 мин на сцену 5 с вместе с загрузкой двух моделей. Если лиц в клипе нет — копия клипа и пометка.</p><ul class='nc-opts'><li><b>Какие лица</b>По ширине лица в кадре: «далёкие» (по умолчанию) чинятся целиком до 7 % ширины кадра и плавно перестают к 9 %; «очень далёкие» — 4–6 %, «и средние» — 10–12 %, «все». Крупное лицо не трогается: модель рисует его хуже, чем сняла.</li><li><b>Кто в кадре</b>Внешность героя, как у Сценариста. С ней модели дорисовывают именно героя, а не кого-то похожего: без описания и с сильной перерисовкой лицо становилось чужим.</li></ul><p class='nc-note'>Лицо ведётся по кадрам (YuNet), квадрат вокруг него — 512×512. Опорные кадры каждые 16 кадров улучшает Krea 2 (img2img, denoise 0,3), весь кроп проходит через LTX 2.3 с малым шумом (σ 0,72, 2 шага, опоры как guide) и вклеивается мягким овалом со сдвигом цвета под оригинал.</p>")}
${nodeCard("Кадр", "ffmpeg", "crop", [["сцена", "clip", "клип — из Сцены или «Видео → видео»"]], [["картинка", "image", "кадр из клипа — во «старт» другой Сцены"]], "Кадр из сцены: последний или в любой момент её длины. Продолжение не обязательно начинать с конца.")}
${nodeCard("Звук сцены", "ffmpeg", "volume", [["сцена", "clip", "снятая сцена, чей звук взять"]], [["трек", "audio", "голос сцены — в «голос» следующей Сцены (ID-LoRA) или в «трек» Музыки"]], "Звук снятой сцены — по умолчанию только голос (Demucs отделяет его от музыки и шумов, ~1 мин на видеокарте). Так герой говорит тем же голосом весь ролик.")}
${nodeCard("LoRA", "user", "sliders", [], [["LoRA", "lora", "набор с силой — во вход «LoRA» Сцены или «Видео → видео»"]], "Набор LoRA с силой. LoRA — модели графа (H3, LTX или WAN), из её папки. У сцены может быть несколько наборов, у разных сцен — разные.")}
</dl>
<h3>Ролик</h3>
<dl class="node-cards">
${nodeCard("Склейка", "ffmpeg", "merge", [["сцены", "clip", "клипы по порядку — из Сцен и «Видео → видео», сколько угодно"]], [["ролик", "video", "склеенный ролик — в Музыку или Выход"]], "Сцены по порядку (порядок — в панели справа). Продолжение со своего последнего кадра склеивается без повтора кадра. Звук режется целыми кадрами вместе с картинкой и не сдвигается, как в монтаже; на стыке — сглаживание 0,03 с против щелчков. «Сделать монтажом» — тот же узел с редактором монтажа.")}
${nodeCard("Монтаж", "ffmpeg", "cut", [["сцены", "clip", "клипы для монтажа — из Сцен и «Видео → видео», сколько угодно"]], [["ролик", "video", "смонтированный ролик — в Музыку или Выход"]], "Склейка с редактором — тем же, что у раскадровки: обрезка, разрез (S), копия, скорость, переходы, дубли сцен, звуки из файлов, отмена. «Открыть монтаж» в панели узла; монтаж хранится в узле, у каждой ветки свой. Клипы «Видео → видео» — каждый отдельным клипом, без дублей. Трек — узлом «Музыка» после него.")}
${nodeCard("Трек", "user", "music", [], [["трек", "audio", "звуковой файл — в «трек» Музыки или в «голос» Сцены (образец голоса, лучше 5–10 с чистой речи)"]], "Ваш звуковой файл: mp3, wav, m4a, flac или ogg — или «Записать голос» с микрофона.")}
${nodeCard("Музыка", "ffmpeg", "mix", [["ролик", "video", "из Склейки или Монтажа"], ["трек", "audio", "из «Трека» или «Звука сцены»"]], [["ролик", "video", "ролик с музыкой — в Выход"]], "Трек поверх ролика: громкость трека и звука сцен, с какой секунды трека, нарастание и затухание.")}
${nodeCard("Выход", "ffmpeg", "export", [["ролик", "video", "из Склейки, Монтажа или Музыки"]], [], "Готовый файл: как снято, 1080p или 4K через RTX, HDR10, 48 кадров в секунду. Выходов может быть несколько — каждый своя версия.")}
</dl>
<h3>На холсте</h3>
<dl class="node-cards">
${nodeCard("Заметка", "none", "note", [], [], "Текст на холсте, ничего не делает.")}
${nodeCard("Группа", "none", "box", [], [], "Рамка с названием за узлами. Перетащите её за заголовок — узлы внутри поедут вместе с ней.")}
</dl>` },

  { id: "video-models", group: "Съёмка и ролик", title: "Модели видео: H3, LTX, WAN", html: `
<p>Модель ролика выбирают при создании и меняют в панели раскадровки («Модель») или графа; у сцены может быть своя («Модель» в инспекторе сцены). Все модели работают на одном воркере: при первой сцене другой модели прежняя выгружается, новая загружается — до полуминуты сверху.</p>
<div style="overflow-x:auto;margin:6px 0 18px"><table style="border-collapse:collapse;font-size:13.5px;line-height:1.45;min-width:640px">
<thead><tr style="text-align:left;color:var(--text)"><th style="padding:6px 10px 6px 0">Модель</th><th style="padding:6px 10px">Хороша для</th><th style="padding:6px 10px">Звук и голос</th><th style="padding:6px 10px">Сцена до</th><th style="padding:6px 10px">Черновик / финал, 16:9</th><th style="padding:6px 10px">Сцена 5 с, черновик</th><th style="padding:6px 0 6px 10px">LoRA</th></tr></thead>
<tbody style="color:var(--soft)">
<tr style="border-top:1px solid var(--rule)"><td style="padding:6px 10px 6px 0"><b>MiniMax H3</b></td><td style="padding:6px 10px">лица и игра, лица по фото (Ref2VA)</td><td style="padding:6px 10px">свой звук, реплики на языке ролика</td><td style="padding:6px 10px">15 с</td><td style="padding:6px 10px">960×544 / 1344×768</td><td style="padding:6px 10px">≈ 95 с</td><td style="padding:6px 0 6px 10px"><code>loras\\h3</code></td></tr>
<tr style="border-top:1px solid var(--rule)"><td style="padding:6px 10px 6px 0"><b>LTX 2.5</b></td><td style="padding:6px 10px">быстрые сцены со звуком; «прийти к кадру»</td><td style="padding:6px 10px">свой звук, реплики</td><td style="padding:6px 10px">10 с</td><td style="padding:6px 10px">1024×576 / 1280×704</td><td style="padding:6px 10px">≈ 29 с</td><td style="padding:6px 0 6px 10px"><code>loras\\ltx25</code></td></tr>
<tr style="border-top:1px solid var(--rule)"><td style="padding:6px 10px 6px 0"><b>LTX 2.3</b></td><td style="padding:6px 10px">клипы: снимает под ваш трек, герои поют; голос героя по образцу (ID-LoRA); «прийти к кадру»</td><td style="padding:6px 10px">свой звук, реплики</td><td style="padding:6px 10px">10 с</td><td style="padding:6px 10px">1024×576 / 1280×704</td><td style="padding:6px 10px">≈ 32 с</td><td style="padding:6px 0 6px 10px"><code>ltx\\loras</code>, <code>ltx\\ic-loras</code></td></tr>
<tr style="border-top:1px solid var(--rule)"><td style="padding:6px 10px 6px 0"><b>WAN 2.2 5B</b></td><td style="padding:6px 10px">только картинка; лицензия Apache-2.0 — можно и для коммерции</td><td style="padding:6px 10px">нет</td><td style="padding:6px 10px">5 с</td><td style="padding:6px 10px">960×544 / 1280×704</td><td style="padding:6px 10px">≈ 120 с</td><td style="padding:6px 0 6px 10px"><code>loras\\wan5b</code></td></tr>
<tr style="border-top:1px solid var(--rule)"><td style="padding:6px 10px 6px 0"><b>WAN 2.2 5B · FastWan</b></td><td style="padding:6px 10px">то же, что WAN, в разы быстрее: 8 шагов вместо 20</td><td style="padding:6px 10px">нет</td><td style="padding:6px 10px">5 с</td><td style="padding:6px 10px">960×544 / 1280×704</td><td style="padding:6px 10px">≈ 40 с</td><td style="padding:6px 0 6px 10px">как у WAN</td></tr>
</tbody></table>
<p class="note">Время — замеры на RTX 4080, модель уже в памяти; «Модели и настройки» показывают замеры этой машины. Папки LoRA — в <code>models\\loras</code>, меняются там же. В раскадровке сцены по 5 с, на LTX — по 10 с.</p></div>
<dl>
<dt>LTX: две стадии</dt><dd>LTX 2.5 и 2.3 снимают в половину размера, потом увеличивают латент вдвое. Лиц по фото не держат: лицо держится словами и стартовым кадром.</dd>
<dt>WAN без звука</dt><dd>Реплики не прозвучат — звук ролика только ваш трек. В клипы без трека встаёт тишина, чтобы склейка и монтаж работали как обычно.</dd>
<dt>Промт под модель</dt><dd>Раскадровка хранит промт H3, а LTX и WAN получают свой, собранный из тех же полей сцены по руководству своей модели. LTX — один абзац в настоящем времени: стиль, место, кто там, действие от начала до конца, камера, звук с репликами. WAN — кто, где, движение, камера, стиль, без звука; у продолжения и сцены с фото — только движение и камера. В инспекторе это видно под «Промт для модели, EN»: «Получит LTX 2.5…». Свой промт сцены LTX и WAN получают переделанным: без пометок H3, таймлайн одним абзацем, без хвоста про надписи, у WAN — без реплик и звука. Смена модели не портит раскадровку: вернёте H3 — снятое H3 возьмётся из кэша.</dd>
<dt>Кэш</dt><dd>У каждой модели свои ключи сцен: снятое одной моделью не путается с другой. Ключи H3 — те же, что до появления других моделей.</dd>
<dt>Веса</dt><dd>«Модели и настройки» → раздел модели: какие файлы нужны, где лежат, откуда скачать. Без весов модель в списке помечена «нет весов».</dd>
</dl>` },

  { id: "shoot", group: "Съёмка и ролик", title: "Качество, LoRA, музыка, выход", html: `
<dl>
<dt>Модель</dt><dd>Кто снимает ролик: H3, LTX 2.5, LTX 2.3, WAN 2.2 5B или WAN 2.2 5B · FastWan. Под списком — чего модель не сделает с этой раскадровкой (реплики, лица по фото, звук). Смена модели переснимет сцены; снятое другой моделью остаётся в кэше. Подробно — раздел «Модели видео».</dd>
<dt>Снимать под трек</dt><dd>Только LTX 2.3, когда загружен свой трек. Каждая сцена получает кусок трека с того места, где она стоит в ролике, и снимается под него: движение — под музыку, губы — под голос песни. Звук ролика — сам трек. Правка трека или его начала переснимет сцены. Куски считаются по раскадровке: если в монтаже переставить, обрезать или ускорить сцены, картинка и песня разойдутся.</dd>
<dt>Качество</dt><dd><b>Черновик</b> — меньше и быстрее, <b>Финал</b> — крупнее и заметно детальнее. Размер и время у каждой модели свои (таблица в <a href="#/help/video-models">«Модели видео»</a>): на H3 черновик — 960×544, около 1,5 мин на сцену 5 с, финал — 1344×768, около 4,5 мин; на LTX финал 1280×704 — около минуты. Финал снимается с теми же сидами — сцены будут те же, только чётче. Удобно: сначала черновик, поправить, потом финал.</dd>
<dt>LoRA</dt><dd>Дообучения модели ролика, у каждой модели своя папка в папке моделей: H3 — <code>loras\\h3</code>, LTX 2.3 — <code>loras\\ltx23</code>, LTX 2.5 — <code>loras\\ltx25</code>, WAN и FastWan — общая <code>loras\\wan5b</code>, Krea 2 — <code>loras\\krea2</code> (папки меняются в «Модели и настройки»). Положили .safetensors в папку — LoRA появится в списке сама. «+ из библиотеки» показывает LoRA модели ролика, ползунок — сила, × — убрать. Обычно хватает 0,6–1; выше — стиль LoRA перебивает промт. Смена LoRA или силы переснимает весь ролик. Сменили модель ролика — LoRA другой модели остаются в списке, но не действуют (жёлтая строка), а сцены своей модели (клип) берут только свои.</dd>
<dt>LoRA картинок</dt><dd>Рядом с кнопками рисования — строка «LoRA»: выбранные LoRA фишками, заливка фишки — сила (тяните по ней вбок или стрелки ← →, × — убрать) и «+ добавить» со списком библиотеки: у героя (под «Что поменять»), у мест и у первого кадра сцены (вкладка «Начало»); те же LoRA — и в панели съёмки, под LoRA ролика. «Портреты и места (Krea 2)» — с ними Krea 2 рисует пробы и портрет героя и картинки мест; «Кадры сцен (FLUX.2 Klein)» — с ними FLUX.2 Klein рисует первые кадры сцен («Нарисовать кадр», «Перерисовать кадр», «Нарисовать кадры всем сценам») и правит черты героя. LoRA Krea лежат в <code>loras\\krea2</code>, LoRA FLUX.2 — в <code>loras\\flux2</code>. Уже нарисованное не меняется — нарисуйте заново. При создании ролика всё это — в карточке «LoRA» под «Моделью» («Клип из песни», «Сценарист»): свёрнутая показывает, что выбрано («Видео: нет», «Портреты: …», «Кадры сцен: …»), раскрытая — три строки: видео (LoRA модели ролика, все сцены), портреты (Krea 2: герои, места), кадры сцен (FLUX.2 Klein). Строка картинок, которые после сценария не рисуются, бледнеет; выбор остаётся.</dd>
<dt>Музыка</dt><dd>Свой трек на весь ролик: mp3, wav, m4a, flac или ogg ложится одной дорожкой после склейки.
<br><b>Громкость трека</b> — 0–150 %. <b>Звук сцен</b> — сколько оставить от звука сцен под музыкой (30 % — шаги и ветер слышны). <b>Начать трек с</b> — с какой секунды. <b>Затухание в конце</b> — плавный уход.
<br>Смена трека или уровней не переснимает сцены: кнопка станет «Свести музыку», это секунды. Исключение — «Снимать под трек»: там правка трека или его начала переснимет сцены.</dd>
<dt>В сценах без музыки</dt><dd>Модель перестаёт сочинять музыку в каждой сцене и делает только звуки, чтобы они не спорили с вашим треком. Меняет промты — сцены переснимутся.</dd>
<dt>Выход</dt><dd><b>Как снято</b> — без увеличения. <b>1080p</b> и <b>4K</b> — увеличение NVIDIA RTX Video после склейки, ~10–15 с на 30 с ролика.
<br><b>HDR10</b> — RTX TrueHDR: смотреть на HDR-экране, на обычном выглядит блёкло.
<br><b>48 кадров в секунду</b> — RIFE дорисовывает промежуточные кадры, движение плавнее; на стыках новых сцен кадры не смешиваются.
<br>Смена выхода не переснимает сцены: кнопка станет «Пересобрать».</dd>
<dt>Главная кнопка</dt><dd>Меняется по ситуации: «Снять ролик», «Собрать ролик» (всё снято), «Свести музыку», «Пересобрать», «Открыть ролик». Под ней — сколько сцен возьмётся из кэша и сколько придётся снять.</dd>
</dl>` },

  { id: "cache", group: "Съёмка и ролик", title: "Кэш и время", html: `
<p>Каждая снятая сцена хранится в <code>projects/&lt;ролик&gt;/scenes</code> под ключом из всего, что её определяет: промт (тот, что получит модель), сид, размер, длина, модель, LoRA, стартовый и последний кадр, фото для Ref2VA, образец голоса, кусок трека при «Снимать под трек». Ничего не изменилось — сцена берётся из кэша мгновенно.</p>
<dl>
<dt>Переснимается</dt><dd>Поправленная сцена и продолжения после неё (их стартовый кадр стал другим). Весь ролик — при смене модели, качества, кадра, LoRA, Ref2VA, стиля или внешности героя.</dd>
<dt>Не переснимается</dt><dd>Музыка и выход (1080p, 4K, HDR10, 48 fps) — только сведение и обработка, секунды. Кроме «Снимать под трек»: там правка трека переснимает сцены.</dd>
<dt>Оценка времени</dt><dd>По последним съёмкам на этой машине, с учётом кэша, загрузки модели, склейки, музыки и выхода.</dd>
</dl>` },

  { id: "video", group: "Съёмка и ролик", title: "Экран «Ролик»", html: `
<dl>
<dt>Плеер</dt><dd>Во время съёмки — последняя готовая сцена, потом весь ролик. Щелчок по сцене внизу — посмотреть её.</dd>
<dt>Полоса сцен</dt><dd>«из кэша», «87 с» — сколько снималась, «шаг 5/8» с процентом, «ждёт кадр» — продолжение ждёт предыдущую сцену, «отложена» — после остановки.</dd>
<dt>Остановить после текущей сцены</dt><dd>Текущая сцена доснимется и сохранится, остальные подождут следующего запуска.</dd>
<dt>Остановить сразу</dt><dd>Прерывает съёмку; текущая сцена пропадёт.</dd>
<dt>Скачать MP4, Открыть папку</dt><dd>Готовый ролик (в имени — формат, например <code>_4k_hdr_48fps</code>) и папка проекта.</dd>
<dt>Этапы</dt><dd>Список над кнопками: «Модель и энкодер» (запуск, загрузка или «в памяти»), «Сцены 1–N» со счётом снятых, «Склейка и звук» (или «Склейка по монтажу»), «Музыка: …», если есть трек, и выход, если не «как снято».</dd>
<dt>Главная кнопка</dt><dd>По ситуации: «Снять ролик», «Доснять изменённое» (часть сцен уже снята), «Собрать по монтажу» (монтаж изменён), «Свести музыку заново», «Пересобрать: …» (сменился выход) или «Всё снято». Под надписью — качество и оценка времени.</dd>
<dt>Монтаж</dt><dd>Кнопка рядом с «Открыть папку»: обрезать сцены, переставить, переходы, звуки — и собрать заново (раздел «Монтаж»).</dd>
<dt>Снять финал, Снять черновик</dt><dd>Те же сцены с теми же сидами в другом качестве; размер у каждой модели свой — он во всплывающей подсказке кнопки (на H3 финал — 1344×768). Рядом — оценка времени.</dd>
</dl>` },

  { id: "lab", group: "Инструменты", title: "Лаборатория", html: `
<p>Страница <code>/lab</code>: одна сцена вручную, без раскадровки. Удобно пробовать промты, стартовые кадры, LoRA и модели.</p>
<dl>
<dt>Модель</dt><dd>Кнопка с именем модели над кадром справа: кто снимает дубль — H3, LTX 2.5, LTX 2.3, WAN 2.2 5B или FastWan. Промт уходит как написан: H3 — слово в слово, LTX и WAN — без пометок H3 (раздел «Как писать промт»). От модели зависят размер, длина (не дольше её предела) и список LoRA. Модель подписана у дубля.</dd>
<dt>Снять на всех моделях — сравнить</dt><dd>Кнопка под «Снять»: тот же промт и сид — по дублю на каждой модели, чьи веса есть. Каждая модель грузится по очереди, так что это несколько минут.</dd>
<dt>Промт сцены</dt><dd>Два переключателя над промтом. Язык: <b>English</b> — промт, который уходит в модель; <b>Русский</b> (или ваш язык текстов) — та же сцена на вашем языке, для перевода. Снимается всегда английский. Вид: <b>Поля</b> — сцена по частям, промт собирается сам; <b>Текст</b> — промт целиком, своим текстом. «Заготовка ▾» заполняет поля или вставляет текст на языке открытой вкладки.</dd>
<dt>Поля и текст</dt><dd><b>Поля</b> — стиль, место, камера, что происходит по секундам, звук и две галочки хвоста; из них собирается промт в формате H3 (он виден в свёрнутом «Промт для …» под полями). Таймлайн считается сам, а действия и реплики идут по одному в строке — ошибкам таймлайна неоткуда взяться. <b>Текст</b> — один большой текст с разметкой, как раньше: для тех, кто пишет промт сам или правит собранный («Править текстом»). Переход из текста в поля разбирает текст по частям; абзац без метки попадает в «Место» — страница об этом скажет.</dd>
<dt>Стиль</dt><dd>Какое это кино: живая съёмка или анимация, свет, цвет, плёнка. Одна фраза, в английском промте — первый абзац без метки.</dd>
<dt>Место</dt><dd>Где и когда, кто там и как выглядит: комната или улица, время суток, погода, люди с возрастом, волосами и одеждой. Становится строкой <code>Scene:</code>.</dd>
<dt>Камера</dt><dd>План и движение из списков — те же слова, что в раскадровке; поле ниже — уточнение своими словами («лицо хорошо видно»). Всё вместе становится строкой <code>Camera:</code>.</dd>
<dt>Что происходит</dt><dd>Действия по одному в строке, до шести. Время слева считается само: действия делят длину сцены поровну, три действия на 5 с — 2, 2 и 1, как в раскадровке. Чтобы действие шло дольше, впишите секунды в поле справа; пустое — поровну с остальными. Реплика героя — в кавычках в той же строке, строка помечается розовым слева; на английском слое перед ней должно стоять <code>in Russian:</code> — перевод это делает сам.</dd>
<dt>Звук</dt><dd>Что слышно всю сцену: звуки места и действий, музыка инструментами и темпом или «без музыки». Становится строкой <code>Audio:</code>. Звук одного события лучше вписать в его строку действия.</dd>
<dt>Промт для модели</dt><dd>Свёрнутый блок под полями, назван по модели — «Промт для H3», «Промт для LTX 2.5»: текст, собранный из полей. LTX и WAN получат его без пометок H3. «Править текстом» переводит в режим «Текст», где его можно переписать целиком.</dd>
<dt>Проверка промта</dt><dd>Жёлтые строки под полем — что стоит поправить до съёмки, у каждой кнопка, которая это делает:
<br>«...» не заполнены — «Перейти»; таймлайн длиннее или короче сцены — «Сцена 8 с» или «Подогнать таймлайн» (время в скобках пересчитается); нет таймлайна — «Добавить»; слова не по-английски вне кавычек, несколько действий через then в одной строке, ходьба без направления к камере, надпись в кадре — «Показать»; есть стартовый кадр, а строки «Continue seamlessly from &lt;Picture 1&gt;.» нет — «Добавить строку», и наоборот.
<br>Это подсказки, а не запрет: снять можно и так. Только с незаполненными «...» программа переспросит.</dd>
<dt>Заготовка</dt><dd>Меню «Заготовка ▾»: 16 целых промтов для частых сцен — вставляются на языке открытой вкладки, а длина сцены ставится под их таймлайн:
<br><b>Основа</b> — все части пустыми, герой в кадре, продолжение с кадра (нужен стартовый кадр).
<br><b>Речь</b> — реплика в камеру, диалог двоих, голос за кадром.
<br><b>Люди и движение</b> — идёт к камере, трое в кадре, танец для клипа.
<br><b>Звуки и музыка</b> — взрыв и эффекты, музыкант в кадре, музыка за кадром.
<br><b>Без людей</b> — природа, предмет крупно.
<br><b>Стиль</b> — 3D-мультфильм, старая плёнка.
<br>Поменяйте героя, место и действия под себя. Проверена в Remiqora Video «Реплика в камеру»; остальные написаны по руководству MiniMax — снимайте по 2–3 дубля. Пока дублей нет, те же заготовки лежат справа, на месте монитора.</dd>
<dt>Перевести на английский</dt><dd>На вкладке «Русский». Сценарист, выбранный в шапке, переводит текст в английский промт по формуле H3: раскладывает его по частям, расставляет время <code>[0s-2s]</code> на длину сцены, а реплики в кавычках оставляет как есть и дописывает <code>in Russian:</code> (или ваш язык) — герой скажет их на нём. Перевод открывается на вкладке English: проверьте его перед съёмкой. Исходный текст остаётся; если вы его поменяли, на вкладке появится жёлтая точка — переведите заново.
<br>Перевод занимает 10–30 с и идёт в общей очереди видеокарты. Сценарист и видеомодель вместе в память не помещаются, поэтому видеомодель на это время выгружается, и следующий дубль загрузит её заново (до полуминуты сверху). Небольшая модель может ошибиться в переводе — для этого и нужна проверка.</dd>
<dt>Как писать промт</dt><dd>С примерами и готовыми промтами — раздел <a href="#/help/prompt">«Как писать промт»</a> и следующие за ним.</dd>
<dt>Развернуть</dt><dd>Кнопка со стрелками справа над промтом: промт раскрывается на всю лабораторию, ваш язык и английский — рядом, у каждого свои части и проверка. Там же «Снять сцену» и сводка, что снимется. «Свернуть» или Esc возвращают промт в панель.
<br>Панель слева можно и просто сделать шире: потяните её правый край (или щёлкните по краю и нажимайте <kbd>←</kbd> <kbd>→</kbd>), двойной щелчок по краю вернёт прежнюю ширину. Ширина запоминается.</dd>
<dt>Разметка</dt><dd>Галочка над промтом. Каждая часть подписана на языке интерфейса над своим абзацем («Место: где, когда, кто», «Таймлайн: что по секундам»), метки <code>Scene:</code>, <code>Camera:</code>, <code>Audio:</code> — в цветах частей, время <code>[0s-2s]</code> — зелёным, реплики в кавычках — розовым, <code>&lt;Picture 1&gt;</code> — синим, «...», которые ещё надо заполнить, — фиолетовым. Слова не по-английски вне кавычек подчёркнуты красной волной: модель понимает их хуже, их нужно перевести, а реплику героя — взять в кавычки. Подписи видны только вам, в модель уходит один промт. Снимите галочку — поле станет обычным.</dd>
<dt>Части промта</dt><dd>Строка под промтом — Стиль, Место, Камера, Таймлайн, Звук, Хвост, в тех же цветах, что в разборе промта в начале справки. С точкой — часть уже есть, щелчок выделит её. Пунктирная с плюсом — части нет, щелчок вставит её заготовку на своё место, а «...» в ней останется выделенным, чтобы сразу печатать.</dd>
<dt>Стартовый кадр</dt><dd>Картинка, с которой начнётся сцена: модель её оживит и продолжит. Перетащите файл (png, jpg, webp) в кадр справа или нажмите «Стартовый кадр» над ним; ещё проще — «Продолжить с последнего кадра» под готовым дублем. С кадром первой строкой промта пишите <code>Continue seamlessly from &lt;Picture 1&gt;.</code>
<br>«Описать человека» — сценарист посмотрит на кадр и опишет внешность по-английски (~10 с, видеокарта на это время занята); «Вставить в промт» поставит описание туда, где курсор. «Убрать кадр» — сцена снова снимется из текста.</dd>
<dt>Длина</dt><dd>Справа под кадром: 3, 5, 8 или 10 секунд; любая от 1 до 15 с шагом 0,5 — в поле «другая» рядом. Слева от длины — линейка сцены, на ней строки таймлайна промта: видно, что когда происходит и не выходит ли что-то за конец (такой отрезок красный); щелчок по отрезку выделяет его строку в промте. Не дольше, чем снимает модель: LTX — 10 с, WAN — 5 с (кнопки длиннее скрыты). H3 обучена на сценах от 5 до 15 секунд; короче снять можно, но это уже вне её привычного. Под длиной — сколько кадров выйдет: модели снимают 24 кадра в секунду и округляют длину вверх до своей сетки кадров. Чем длиннее сцена, тем дольше съёмка — оценка под кнопкой «Снять».</dd>
<dt>Формат</dt><dd>Над кадром — его форма: 16:9 — горизонтальный, 9:16 — для телефона, 1:1 — квадрат и другие. Рамка кадра сразу принимает эту форму, в её углу — размер в пикселях, у каждой модели свой. «Как у кадра» — форма стартового кадра, чтобы его не обрезать.</dd>
<dt>Качество</dt><dd><b>Черновик</b> — меньше и быстрее, чтобы искать промт. <b>Финал</b> — крупнее и детальнее, в 2–3 раза дольше. Наведите на кнопку — размер и время на 5 секунд у выбранной модели на этой машине. Тот же сид в финале даёт ту же сцену, только чётче.</dd>
<dt>LoRA</dt><dd>Дообучения модели, которой снимаете (H3, LTX или WAN; у FastWan — LoRA WAN): стиль, персонаж, движение. «Добавить» открывает список из папки этой модели, с поиском. Ползунок — сила (обычно 0,6–1; выше — LoRA перебивает промт), ↺ — вернуть 0,8, × — выключить. Жёлтая метка — может не подойти к модели (у LTX 2.3 так помечены LoRA от LTX-2 19B). Если у LoRA есть слово-триггер, впишите его в промт.</dd>
<dt>Сид</dt><dd>Поле над кадром. Число, от которого зависит случайность: тот же промт с тем же сидом даёт тот же дубль. Пусто — каждый раз новый. Чтобы увидеть, что даёт правка промта, держите сид прежним.</dd>
<dt>Сколько дублей</dt><dd>Число слева от «Снять»: сколько дублей снять подряд, сид у каждого на 1 больше. Удобно, чтобы выбрать лучший из нескольких.</dd>
<dt>Дубли</dt><dd>Справа под кадром, по промтам: у каждой группы — что происходит в сцене, под ней — дубли с сидом. Наведите — дубль играет без звука, щелчок — смотреть в кадре. Идущая съёмка видна в своей группе с шагом.</dd>
<dt>Под дублем</dt><dd>«Продолжить с последнего кадра» сделает его стартовым для следующей сцены; «Повторить настройки» (сид новый) или «Повторить с сидом» — чтобы менять промт и видеть только его разницу; «Скачать», «Удалить» — в корзину Windows.</dd>
<dt>Остановить</dt><dd>В строке состояния, пока снимается дубль: останавливает только дубли лаборатории, ролик студии продолжит сниматься.</dd>
</dl>` },

  { id: "models", group: "Инструменты", title: "Модели и настройки", html: `
<p>Страница «Модели» в шапке. Разделы слева: «Видео H3», «Ref2VA», «LTX 2.5», «LTX 2.3», «WAN 2.2 5B» (с LoRA FastWan), «Krea 2 — картинки», «Сценарист», «LoRA», «Инструменты»; точка — всё ли на месте, рядом — сколько занимает на диске. Сверху — все модели на диске одной полосой. Всё сохраняется сразу, перезапуск не нужен.</p>
<dl>
<dt>Карточка модели</dt><dd>У видеомодели: что умеет (звук, реплики, лица по фото, под трек), «Сцена 5 с» — сколько снимает черновик на этой машине (по замерам; пока не снимали — оценка), шагов, лицензия. Рядом — «в памяти» или «выгружен».</dd>
<dt>Выгрузить</dt><dd>Кнопка рядом с названием, пока модель в памяти: освобождает видеопамять, следующая съёмка загрузит модель снова. То же — «Выгрузить модель» в строке состояния.</dd>
<dt>Веса по ролям</dt><dd>Основная модель, энкодер текста, VAE видео и звука, апскейлер латента у LTX, LoRA FastWan, Ref2VA. У каждого файла видно, где он лежит или куда скачается и откуда — ссылка на Hugging Face. «Использовать» переключает модель, «Убрать» отправляет файл в корзину Windows.</dd>
<dt>Скачать</dt><dd>Файлы качаются в фоне по одному. «Остановить» сохраняет скачанное, «Продолжить» докачивает с того же места; в конце размер сверяется с Hugging Face. Файл, положенный в папку вручную, появится на странице сам.</dd>
<dt>Сценарист</dt><dd>Модель по умолчанию, контекст, папки с GGUF и скачивание по ссылке Hugging Face.</dd>
<dt>Krea 2 — картинки</dt><dd>Рисует узел «Картинка» в графе — на том же воркере, что видео (официальная сборка ComfyUI: Krea 2 Turbo int8, энкодер Qwen3-VL 4B fp8, VAE Qwen-Image; всё с Comfy-Org/Krea-2, в папках весов воркера). Перед картинкой видеомодель выгружается; Krea остаётся в памяти, следующие картинки — около 3,5 с. Свои папки для LoRA Krea: каждый файл проверяется по заголовку — LoRA и LoKr подходят, LoHa и DoRA помечены «может не примениться», полные веса заблокированы; рядом видны триггер-слова и превью (<code>имя.png</code>, <code>имя.civitai.info</code>). LoRA выбираются в узле «Картинка», сила от −30 до 30; если часть ключей LoRA не подошла к модели, это видно после картинки.</dd>
<dt>Папки LoRA</dt><dd>У каждой модели свои: «LoRA» — папки H3; в разделах LTX 2.5, LTX 2.3 и WAN 2.2 5B — их собственные (LoRA одной модели к другой не подходит), у Krea — свои. Положенный в папку .safetensors появится в списке сам.</dd>
<dt>Токен Hugging Face</dt><dd>В разделе «Видео H3»: нужен только для закрытых моделей, хранится в <code>data\\hf_token</code>. «Сохранить», «Убрать».</dd>
<dt>Инструменты</dt><dd>Пути к ядру ComfyUI, его Python, llama-server, ffmpeg и ffprobe, RIFE и RTX Video; у каждого видно, найден ли он. «Как в .env» возвращает значение из .env или умолчание; новое ядро или Python подхватятся со следующей съёмки.</dd>
<dt>Папки и пути</dt><dd>«Выбрать…» открывает окно Windows; «Как в .env» возвращает значение из файла настроек.</dd>
</dl>` },

  { id: "env", group: "Инструменты", title: "Настройки в .env", html: `
<p>Файл <code>.env</code> в папке программы (образец — <code>.env.example</code>). У всех значений есть умолчания для этой машины. Пути и папки проще задать на странице «Модели»: там они сохраняются в <code>data\\settings.json</code> поверх <code>.env</code> без перезапуска.</p>
<dl>
<dt>H3_MODEL_ROOTS</dt><dd>Папки с весами всех моделей воркера — H3, LTX, WAN, Krea (через ;): в них ищутся <code>diffusion_models</code>, <code>text_encoders</code>, <code>vae</code>, <code>loras</code>, <code>checkpoints</code>, <code>latent_upscale_models</code>. По умолчанию <code>models</code> в папке программы; установщик записывает в <code>.env</code> папку, выбранную при установке. Имя осталось от времён, когда модель была одна.</dd>
<dt>COMFY_DIR, COMFY_PYTHON</dt><dd>Где лежит ядро ComfyUI и его Python. По умолчанию — свои, <code>engine\\ComfyUI</code> и <code>engine\\.venv</code> (ставит <code>install.bat</code>: ядро на закреплённом коммите, torch с CUDA 13, Demucs и Whisper для слов песни); пока их нет — из Comfy Desktop. Сервера ComfyUI и порта нет: все модели снимает свой процесс с ядром как библиотекой.</dd>
<dt>COMFY_INPUT, COMFY_OUTPUT</dt><dd>Рабочие папки кадров и снятых сцен.</dd>
<dt>WORKER_LOG</dt><dd>Журнал воркера видеомоделей, по умолчанию <code>data\\h3worker.log</code>.</dd>
<dt>H3_UNET, H3_CLIP, H3_VAE, H3_AUDIO_VAE</dt><dd>Имена файлов модели H3, энкодера и VAE.</dd>
<dt>H3_TURBO_LORA</dt><dd>Turbo-LoRA официальной модели H3: 8 шагов без CFG. Модель с ускорением внутри (TURBO в имени) снимает без неё.</dd>
<dt>H3_REF_UNET, H3_REF_LORA, H3_REF_DIR</dt><dd>Модель Ref2VA, её turbo-LoRA и папка с ними.</dd>
<dt>LTX25_…, LTX23_…, WAN_…, KREA_…</dt><dd>Имена весов других моделей: <code>LTX25_UNET</code>, <code>LTX25_CLIP</code>, <code>LTX25_VAE</code>, <code>LTX25_AUDIO_VAE</code>, <code>LTX25_UPSCALER</code>; <code>LTX23_CKPT</code>, <code>LTX23_CLIP</code>, <code>LTX23_LORA</code>, <code>LTX23_UPSCALER</code>; <code>WAN_UNET</code>, <code>WAN_CLIP</code>, <code>WAN_VAE</code>, <code>WAN_FAST_LORA</code>; <code>KREA_UNET</code>, <code>KREA_CLIP</code>, <code>KREA_VAE</code>. Ищутся в папках <code>H3_MODEL_ROOTS</code>; умолчания — в <code>.env.example</code>.</dd>
<dt>LORA_DIRS</dt><dd>Папки с LoRA для H3 (через ;), по умолчанию <code>loras\\h3</code> в папке моделей.</dd>
<dt>LTX23_LORA_DIRS, LTX25_LORA_DIRS, WAN_LORA_DIRS, KREA_LORA_DIRS</dt><dd>Свои папки LoRA у каждой модели (через ;). По умолчанию в папке моделей: LTX 2.3 — <code>loras\\ltx23</code>, LTX 2.5 — <code>loras\\ltx25</code>, WAN и FastWan — <code>loras\\wan5b</code>, Krea — <code>loras\\krea2</code>.</dd>
<dt>LLAMA_SERVER_BIN, LLM_DIRS, LLM_MODEL, LLM_PORT, LLM_CTX</dt><dd>Сценарист: llama-server, папки с GGUF, модель по умолчанию (gemma-4-E4B), порт llama-server (8191), длина контекста (16384). llama-server ищется так: заданный путь, <code>tools\\llama</code>, движок установленной LM Studio. Если Windows его блокирует («Интеллектуальное управление приложениями»), нужна подписанная сборка — проще всего установить LM Studio.</dd>
<dt>FFMPEG, FFPROBE, RTX_VSR, RIFE_BIN, RIFE_MODEL</dt><dd>Склейка и звук, RTX Video (1080p, 4K, HDR10), RIFE (48 fps) и его модель — папка рядом с exe, по умолчанию <code>rife-v4.6</code>.</dd>
<dt>LYRICS_PYTHON, LYRICS_MODEL</dt><dd>Слова песни (Demucs + Whisper): Python с ними и модель Whisper (<code>large-v3</code>). Python ищется так: заданный (по умолчанию <code>tools\\lyrics\\.venv</code>), <code>engine\\.venv</code>, если в нём есть Demucs, окружение старой Remiqora.</dd>
<dt>HOST, PORT</dt><dd>Адрес и порт программы: <code>127.0.0.1</code> и 8810.</dd>
</dl>` },
];

// the contents: the start, then the scenarios step by step (lib/tutorials), then the reference by the steps of the work
const START = REFERENCE.filter((x) => x.group === "Начало");
export const HELP: HelpSection[] = [...START, ...TUTORIALS, ...REFERENCE.filter((x) => x.group !== "Начало")];
