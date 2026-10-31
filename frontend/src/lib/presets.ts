// The lab's «Заготовка» menu: whole prompts for the common kinds of scene, each in English (the prompt H3 gets) and in
// Russian (for the «Русский» tab, to translate). Spoken lines stay Russian in both. Only «Реплика в камеру» has been
// shot in H3 Studio (2026-10-22); the rest follow MiniMax's prompt guide and what the storyboard taught us.
import { template } from './promptParts'

export interface Preset { id: string; group: string; name: string; hint: string; seconds: number; frame?: boolean; en: string; ru: string }

const TAIL_EN = 'No text, subtitles, logos or watermarks.'
const TAIL_RU = 'Без текста, субтитров, логотипов и водяных знаков.'
const KEEP_EN = (who: 'her' | 'his') => `Keep ${who} face, hair and outfit exactly the same. ${TAIL_EN}`
const KEEP_RU = `Лицо, волосы и одежда не меняются. ${TAIL_RU}`

export const PRESETS: Preset[] = [
  { id: 'parts', group: 'Основа', name: 'Все части, пустые', hint: 'каркас промта: заполните «...»', seconds: 5,
    en: template('en'), ru: template('ru') },

  { id: 'hero', group: 'Основа', name: 'Герой в кадре', hint: 'новая сцена из текста: человек, место, три действия', seconds: 5,
    en: `Realistic live-action cinematic look, golden hour sunlight, shallow depth of field, film grain.

Scene: an adult woman, about 30, with long wavy red hair and freckles, wearing a white linen shirt, stands on a wooden pier by a calm lake at sunset.

Camera: medium shot, slow push-in.

Timeline:
[0s-2s] She looks out over the water.
[2s-4s] She turns her head toward the camera.
[4s-5s] She smiles softly.

Audio: gentle acoustic guitar at a slow tempo. Water lapping against the pier, distant birds.

${KEEP_EN('her')}`,
    ru: `Стиль: реалистичное кино, золотой закатный свет, малая глубина резкости, плёночное зерно.

Место: взрослая женщина около 30 лет, длинные волнистые рыжие волосы, веснушки, белая льняная рубашка. Стоит на деревянном причале у тихого озера на закате.

Камера: средний план, медленный наезд.

Таймлайн:
[0s-2s] Она смотрит на воду.
[2s-4s] Она поворачивает голову к камере.
[4s-5s] Она мягко улыбается.

Звук: тихая акустическая гитара в медленном темпе. Плеск воды о причал, далёкие птицы.

${KEEP_RU}` },

  { id: 'continue', group: 'Основа', name: 'Продолжение с кадра', hint: 'нужен стартовый кадр: сцена продолжит картинку', seconds: 5, frame: true,
    en: `Continue seamlessly from <Picture 1>.

Realistic live-action cinematic look, soft natural light, shallow depth of field, film grain.

Scene: the same place and the same person as in the picture.

Camera: medium shot, static shot.

Timeline:
[0s-3s] ...
[3s-5s] ...

Audio: ...

${KEEP_EN('her')}`,
    ru: `Продолжить с кадра <Picture 1>.

Стиль: реалистичное кино, мягкий естественный свет, малая глубина резкости, плёночное зерно.

Место: то же место и тот же человек, что на картинке.

Камера: средний план, камера стоит.

Таймлайн:
[0s-3s] ...
[3s-5s] ...

Звук: ...

${KEEP_RU}` },

  // the photo itself comes alive: the text names no one and nothing new - H3 follows a text that describes another
  // person or place and leaves the photo (a lab take of 2026-10-24: a man on a bridge became a cook in a kitchen)
  { id: 'animate', group: 'Основа', name: 'Оживить фото', hint: 'нужен стартовый кадр: тот же человек и место, только живое движение', seconds: 5, frame: true,
    en: `Continue seamlessly from <Picture 1>.

Realistic live-action look, exactly the light, colours and lens of the picture.

Scene: the same place and the same person as in the picture, in the same pose and clothes; nothing new appears in the frame.

Camera: the same framing as the picture, very slow push-in.

Timeline:
[0s-2s] The person breathes calmly and blinks; a light breeze moves their hair and the things around them.
[2s-4s] The person turns their head slightly, their gaze softens.
[4s-5s] A faint smile; the background keeps moving softly.

Audio: the quiet sounds of the place in the picture, a light breeze.

Keep the face, hair and outfit exactly the same. ${TAIL_EN}`,
    ru: `Продолжить с кадра <Picture 1>.

Стиль: реалистичное кино, свет, цвета и оптика как на картинке.

Место: то же место и тот же человек, что на картинке, в той же позе и одежде; ничего нового в кадре не появляется.

Камера: тот же план, что на картинке, очень медленный наезд.

Таймлайн:
[0s-2s] Человек спокойно дышит и моргает, лёгкий ветер шевелит волосы и всё вокруг.
[2s-4s] Человек чуть поворачивает голову, взгляд смягчается.
[4s-5s] Лёгкая улыбка, фон продолжает мягко двигаться.

Звук: тихие звуки места с картинки, лёгкий ветер.

${KEEP_RU}` },

  { id: 'line', group: 'Речь', name: 'Реплика в камеру', hint: 'герой говорит на языке ролика; проверено в Remiqora Video', seconds: 5,
    en: `Realistic live-action cinematic look, warm evening lamp light, shallow depth of field, film grain.

Scene: an adult man, about 40, with short grey hair and a trimmed beard, wearing a dark wool sweater, sits at a kitchen table at night.

Camera: medium close-up, static shot, his face clearly visible.

Timeline:
[0s-1s] He looks up at the camera.
[1s-4s] He speaks in a low, tired voice, in Russian: "Садись. Нам надо поговорить."
[4s-5s] He folds his hands on the table.

Audio: his low calm voice speaking Russian, quiet room tone, a clock ticking, no music.

${TAIL_EN}`,
    ru: `Стиль: реалистичное кино, тёплый вечерний свет лампы, малая глубина резкости, плёночное зерно.

Место: кухня ночью. Взрослый мужчина около 40 лет, короткие седые волосы, аккуратная борода, тёмный шерстяной свитер, сидит за столом.

Камера: средний крупный план, камера стоит, лицо хорошо видно.

Таймлайн:
[0s-1s] Он поднимает глаза на камеру.
[1s-4s] Он говорит низким усталым голосом: «Садись. Нам надо поговорить.»
[4s-5s] Он складывает руки на столе.

Звук: его низкий спокойный голос по-русски, тишина кухни, тикают часы, без музыки.

${TAIL_RU}` },

  { id: 'dialog', group: 'Речь', name: 'Диалог двоих', hint: 'двое по очереди; каждого зовут по примете', seconds: 8,
    en: `Realistic live-action cinematic look, soft window daylight, shallow depth of field, film grain.

Scene: a small café by a big window. On the left, an adult man, about 35, with short black hair and a grey wool coat. On the right, an adult woman, about 30, with a red bob and a yellow raincoat. They sit across a small table with two cups of coffee. Only these two people are in the scene, nobody else.

Camera: medium shot, static shot, both faces clearly visible.

Timeline:
[0s-3s] The man in the grey coat leans forward and says in a low calm voice, in Russian: "Ты всё-таки пришла."
[3s-4s] The red-haired woman looks at him and smiles.
[4s-7s] The red-haired woman answers in a soft amused voice, in Russian: "Я же обещала."
[7s-8s] The man in the grey coat laughs quietly.

Audio: two voices speaking Russian, quiet café chatter in the background, cups clinking, no music.

${TAIL_EN}`,
    ru: `Стиль: реалистичное кино, мягкий дневной свет из окна, малая глубина резкости, плёночное зерно.

Место: маленькое кафе у большого окна. Слева взрослый мужчина около 35 лет, короткие чёрные волосы, серое шерстяное пальто. Справа взрослая женщина около 30 лет, рыжее каре, жёлтый дождевик. Они сидят друг напротив друга за столиком с двумя чашками кофе. В кадре только они двое, больше никого.

Камера: средний план, камера стоит, оба лица хорошо видны.

Таймлайн:
[0s-3s] Мужчина в сером пальто наклоняется вперёд и говорит низким спокойным голосом: «Ты всё-таки пришла.»
[3s-4s] Рыжая женщина смотрит на него и улыбается.
[4s-7s] Рыжая женщина отвечает мягким насмешливым голосом: «Я же обещала.»
[7s-8s] Мужчина в сером пальто тихо смеётся.

Звук: два голоса по-русски, тихий гул кафе на фоне, звон чашек, без музыки.

${TAIL_RU}` },

  { id: 'voiceover', group: 'Речь', name: 'Голос за кадром', hint: 'говорит рассказчик, губы героини сомкнуты', seconds: 8,
    en: `Realistic live-action cinematic look, soft overcast daylight, muted colors, film grain.

Scene: an adult woman, about 35, with a dark ponytail and a beige trench coat, walks slowly along an empty autumn alley covered with yellow leaves.

Camera: wide shot, a slow tracking shot beside her.

Timeline:
[0s-4s] She walks toward the camera along the alley, her lips closed. A calm female narrator says in an off-screen voiceover, in Russian: "В тот год осень пришла рано."
[4s-8s] She stops and looks up at the trees while her lips remain completely closed. The narrator continues in an off-screen voiceover, in Russian: "И я впервые никуда не спешила."

Audio: the narrator's calm voice speaking Russian, leaves rustling under her feet, a light wind, a soft piano at a slow tempo.

${TAIL_EN}`,
    ru: `Стиль: реалистичное кино, мягкий рассеянный дневной свет, приглушённые цвета, плёночное зерно.

Место: взрослая женщина около 35 лет, тёмные волосы в хвосте, бежевый тренч. Медленно идёт по пустой осенней аллее, засыпанной жёлтыми листьями.

Камера: общий план, камера медленно едет рядом с ней.

Таймлайн:
[0s-4s] Она идёт к камере по аллее, губы сомкнуты. Спокойный женский голос рассказчицы за кадром: «В тот год осень пришла рано.»
[4s-8s] Она останавливается и смотрит на деревья, губы по-прежнему сомкнуты. Рассказчица продолжает за кадром: «И я впервые никуда не спешила.»

Звук: спокойный голос рассказчицы по-русски, шорох листьев под ногами, лёгкий ветер, тихое пианино в медленном темпе.

${TAIL_RU}` },

  { id: 'walk', group: 'Люди и движение', name: 'Идёт к камере', hint: 'камера пятится перед героем; ночь, дождь, неон', seconds: 5,
    en: `Realistic live-action cinematic look, wet night streets, colored neon light reflections, shallow depth of field, film grain.

Scene: an adult man, about 30, with short dark hair and a black leather jacket, on a rainy city street at night, colored neon lights blurred in the background.

Camera: medium shot, the camera moves backward in front of him as he walks.

Timeline:
[0s-3s] He walks toward the camera through the rain.
[3s-5s] He stops and looks straight into the lens.

Audio: heavy rain on the asphalt, footsteps in puddles, distant traffic, a low synthesizer drone.

${KEEP_EN('his')}`,
    ru: `Стиль: реалистичное кино, мокрые ночные улицы, цветные неоновые отражения, малая глубина резкости, плёночное зерно.

Место: взрослый мужчина около 30 лет, короткие тёмные волосы, чёрная кожаная куртка. Дождливая городская улица ночью, размытые цветные неоновые огни на фоне.

Камера: средний план, камера отъезжает назад перед ним, пока он идёт.

Таймлайн:
[0s-3s] Он идёт к камере сквозь дождь.
[3s-5s] Он останавливается и смотрит прямо в объектив.

Звук: сильный дождь по асфальту, шаги по лужам, далёкий шум машин, низкий гул синтезатора.

${KEEP_RU}` },

  { id: 'three', group: 'Люди и движение', name: 'Трое в кадре', hint: 'у каждого свои приметы, место и действие', seconds: 5,
    en: `Realistic live-action cinematic look, golden hour sunlight, film grain.

Scene: a sunny park meadow. On the left, an adult woman, about 25, with long blond braids and a white sundress. In the middle, an adult man, about 30, tall, with a shaved head and a green T-shirt. On the right, an adult woman, about 40, with short curly grey hair and a denim jacket. Only these three people are in the scene, nobody else.

Camera: full shot, static shot.

Timeline:
[0s-2s] The man in the green T-shirt throws a red frisbee to the left.
[2s-4s] The blond woman in the white sundress jumps and catches it.
[4s-5s] The grey-haired woman in the denim jacket claps and laughs.

Audio: a light ukulele at a cheerful tempo. Birds, laughter, the whoosh of the frisbee.

${TAIL_EN}`,
    ru: `Стиль: реалистичное кино, золотой закатный свет, плёночное зерно.

Место: солнечная поляна в парке. Слева взрослая женщина около 25 лет, длинные светлые косы, белый сарафан. Посередине взрослый мужчина около 30 лет, высокий, бритая голова, зелёная футболка. Справа взрослая женщина около 40 лет, короткие кудрявые седые волосы, джинсовая куртка. В кадре только эти трое, больше никого.

Камера: общий план во весь рост, камера стоит.

Таймлайн:
[0s-2s] Мужчина в зелёной футболке бросает красную летающую тарелку влево.
[2s-4s] Светловолосая женщина в белом сарафане подпрыгивает и ловит её.
[4s-5s] Седая женщина в джинсовой куртке хлопает в ладоши и смеётся.

Звук: лёгкое укулеле в весёлом темпе. Птицы, смех, свист летящей тарелки.

${TAIL_RU}` },

  { id: 'dance', group: 'Люди и движение', name: 'Танец для клипа', hint: 'сцена, свет, дымка, облёт камерой, бит', seconds: 5,
    en: `Stylish music video look, colorful stage lights, light haze, high contrast.

Scene: an adult woman, about 25, with a sleek black bob and a silver sequin dress, dances alone on an empty stage filled with light haze.

Camera: full shot, a slow arc shot around her.

Timeline:
[0s-2s] She raises her arms and turns slowly.
[2s-4s] She steps to the side in rhythm with the beat.
[4s-5s] She freezes in a pose and looks at the camera.

Audio: a punchy electronic beat at a fast tempo with a deep bass line.

${KEEP_EN('her')}`,
    ru: `Стиль: стильный музыкальный клип, цветной сценический свет, лёгкая дымка, высокий контраст.

Место: взрослая женщина около 25 лет, гладкое чёрное каре, серебристое платье с пайетками. Танцует одна на пустой сцене в лёгкой дымке.

Камера: общий план во весь рост, камера медленно облетает её по дуге.

Таймлайн:
[0s-2s] Она поднимает руки и медленно поворачивается.
[2s-4s] Она делает шаг в сторону в ритм бита.
[4s-5s] Она замирает в позе и смотрит в камеру.

Звук: упругий электронный бит в быстром темпе с глубоким басом.

${KEEP_RU}` },

  { id: 'boom', group: 'Звуки и музыка', name: 'Взрыв и эффекты', hint: 'звук каждого события — в его строке, без музыки', seconds: 5,
    en: `Epic fantasy film look, dramatic dusk light, smoke and embers, high contrast.

Scene: a stone castle wall at dusk, burning torches along the battlements. An adult knight in dented steel armor and a helmet stands on the wall with a round shield.

Camera: wide shot, the camera shakes slightly.

Timeline:
[0s-2s] The knight raises his shield and looks up at the sky.
[2s-3s] A fireball hits the wall below him and explodes with a deafening boom.
[3s-5s] Stones and burning sparks fly through the smoke as the knight crouches behind his shield.

Audio: no music. A low rumble before the impact, a deafening explosion, falling stones, crackling fire and the clang of metal.

${TAIL_EN}`,
    ru: `Стиль: эпическое фэнтези, драматичный сумеречный свет, дым и искры, высокий контраст.

Место: каменная стена замка в сумерках, вдоль зубцов горят факелы. На стене стоит взрослый рыцарь в помятых стальных доспехах и шлеме, с круглым щитом.

Камера: общий план, камера слегка трясётся.

Таймлайн:
[0s-2s] Рыцарь поднимает щит и смотрит в небо.
[2s-3s] Огненный шар бьёт в стену под ним и взрывается с оглушительным грохотом.
[3s-5s] Сквозь дым летят камни и горящие искры, рыцарь приседает за щитом.

Звук: без музыки. Низкий гул перед ударом, оглушительный взрыв, падающие камни, треск огня и звон металла.

${TAIL_RU}` },

  { id: 'musician', group: 'Звуки и музыка', name: 'Музыкант в кадре', hint: 'музыку играет герой, её слышат все', seconds: 8,
    en: `Realistic live-action cinematic look, warm streetlights at night, shallow depth of field, film grain.

Scene: a narrow old-town street at night, wet cobblestones. An adult man, about 50, with a grey beard and a black hat sits on a stool and plays an acoustic guitar. Passers-by walk past, blurred in the background.

Camera: medium shot, a slow arc shot around the musician.

Timeline:
[0s-5s] The musician plays a fast flamenco melody, his fingers moving quickly over the strings.
[5s-8s] He slaps the guitar body twice in rhythm and smiles.

Audio: the loud acoustic guitar of the street musician, footsteps on wet stones, distant voices, no background score.

${TAIL_EN}`,
    ru: `Стиль: реалистичное кино, тёплые уличные фонари ночью, малая глубина резкости, плёночное зерно.

Место: узкая улочка старого города ночью, мокрая брусчатка. Взрослый мужчина около 50 лет, седая борода, чёрная шляпа, сидит на табурете и играет на акустической гитаре. Мимо идут прохожие, размытые на фоне.

Камера: средний план, камера медленно облетает музыканта по дуге.

Таймлайн:
[0s-5s] Музыкант играет быструю мелодию фламенко, пальцы быстро бегают по струнам.
[5s-8s] Он дважды в ритм хлопает по корпусу гитары и улыбается.

Звук: громкая акустическая гитара уличного музыканта, шаги по мокрым камням, далёкие голоса, без закадровой музыки.

${TAIL_RU}` },

  { id: 'score', group: 'Звуки и музыка', name: 'Музыка за кадром', hint: 'музыка инструментами и темпом, звуки места следом', seconds: 5,
    en: `Realistic live-action cinematic look, sunrise light, warm haze, film grain.

Scene: an empty desert road at sunrise, a red vintage car drives toward the camera, dust rising behind it.

Camera: wide shot, a slow pull out as the car approaches.

Timeline:
[0s-3s] The red car drives along the road toward the camera.
[3s-5s] The car passes close by the camera and leaves a cloud of dust.

Audio: a slow synthesizer pad joined by a steady electronic drum beat that gradually gets louder. The car engine hums, gravel crunches under the tires, the wind whistles.

${TAIL_EN}`,
    ru: `Стиль: реалистичное кино, рассветный свет, тёплая дымка, плёночное зерно.

Место: пустая пустынная дорога на рассвете, красная старинная машина едет к камере, за ней поднимается пыль.

Камера: общий план, камера медленно отъезжает, пока машина приближается.

Таймлайн:
[0s-3s] Красная машина едет по дороге к камере.
[3s-5s] Машина проносится совсем рядом с камерой и оставляет облако пыли.

Звук: медленный синтезаторный пэд, к нему добавляется ровный электронный бит, музыка постепенно громче. Гудит мотор, хрустит гравий под колёсами, свистит ветер.

${TAIL_RU}` },

  { id: 'nature', group: 'Без людей', name: 'Природа', hint: 'пейзаж: туман, лучи, зверь вдалеке', seconds: 5,
    en: `Cinematic nature documentary look, soft morning light, high detail.

Scene: an empty pine forest at dawn, thick fog between the trees, sunbeams breaking through the branches.

Camera: wide shot, a slow tracking shot forward between the trunks.

Timeline:
[0s-3s] The sunbeams slowly brighten through the fog.
[3s-5s] A deer steps out from behind a tree in the distance.

Audio: no music, only birdsong, a light breeze in the pines and a twig cracking.

${TAIL_EN}`,
    ru: `Стиль: кино о природе, мягкий утренний свет, высокая детализация.

Место: пустой сосновый лес на рассвете, густой туман между деревьями, сквозь ветви пробиваются солнечные лучи.

Камера: общий план, камера медленно едет вперёд между стволами.

Таймлайн:
[0s-3s] Лучи медленно становятся ярче сквозь туман.
[3s-5s] Вдалеке из-за дерева выходит олень.

Звук: без музыки, только пение птиц, лёгкий ветер в соснах и треск ветки.

${TAIL_RU}` },

  { id: 'product', group: 'Без людей', name: 'Предмет крупно', hint: 'реклама: студийный свет, облёт, капля', seconds: 5,
    en: `Polished commercial look, clean soft studio light, glossy reflections, high detail.

Scene: a glass bottle of perfume with a gold cap stands on a black reflective surface, drops of water on the glass, a dark background.

Camera: extreme close-up, a slow arc shot around the bottle.

Timeline:
[0s-3s] Light glides slowly across the glass.
[3s-5s] A single drop of water runs down the bottle.

Audio: a soft airy synthesizer pad at a slow tempo, a gentle shimmer, no voices.

${TAIL_EN}`,
    ru: `Стиль: дорогая реклама, чистый мягкий студийный свет, глянцевые отражения, высокая детализация.

Место: стеклянный флакон духов с золотой крышкой стоит на чёрной зеркальной поверхности, на стекле капли воды, тёмный фон.

Камера: деталь крупно, камера медленно облетает флакон по дуге.

Таймлайн:
[0s-3s] Свет медленно скользит по стеклу.
[3s-5s] По флакону стекает одна капля воды.

Звук: мягкий воздушный синтезатор в медленном темпе, лёгкий звон, без голосов.

${TAIL_RU}` },

  { id: 'cartoon', group: 'Стиль', name: '3D-мультфильм', hint: 'анимация вместо живой съёмки', seconds: 5,
    en: `3D CG animated film look, soft colorful lighting, rounded stylized shapes.

Scene: a small orange fox with big green eyes sits in a cozy forest clearing among giant mushrooms at sunrise.

Camera: medium shot, slow push-in.

Timeline:
[0s-2s] The fox sniffs a glowing blue flower.
[2s-4s] The flower sparkles and the fox jumps back in surprise.
[4s-5s] The fox laughs and wags its tail.

Audio: playful pizzicato strings at a lively tempo, birds chirping, a soft magical chime.

${TAIL_EN}`,
    ru: `Стиль: 3D-мультфильм, мягкий разноцветный свет, округлые стилизованные формы.

Место: маленький рыжий лисёнок с большими зелёными глазами сидит на уютной лесной поляне среди огромных грибов на рассвете.

Камера: средний план, медленный наезд.

Таймлайн:
[0s-2s] Лисёнок нюхает светящийся синий цветок.
[2s-4s] Цветок вспыхивает искрами, и лисёнок отпрыгивает от удивления.
[4s-5s] Лисёнок смеётся и виляет хвостом.

Звук: игривое пиццикато струнных в живом темпе, щебет птиц, мягкий волшебный перезвон.

${TAIL_RU}` },

  { id: 'vintage', group: 'Стиль', name: 'Старая плёнка', hint: '1970-е: выцветшие цвета, зерно, мерцание', seconds: 5,
    en: `Vintage film look from the 1970s, warm faded colors, heavy film grain, soft flicker.

Scene: an adult man, about 45, with a mustache and a brown suede jacket, leans on an old red car by a desert gas station at noon.

Camera: wide shot, static shot.

Timeline:
[0s-2s] He takes off his sunglasses.
[2s-5s] He looks at the empty road and squints in the sun.

Audio: hot wind, a creaking metal gate, distant cicadas, a slow twangy electric guitar.

${KEEP_EN('his')}`,
    ru: `Стиль: старая плёнка 1970-х, тёплые выцветшие цвета, крупное плёночное зерно, лёгкое мерцание.

Место: взрослый мужчина около 45 лет, усы, коричневая замшевая куртка, опирается на старую красную машину у заправки в пустыне в полдень.

Камера: общий план, камера стоит.

Таймлайн:
[0s-2s] Он снимает солнечные очки.
[2s-5s] Он смотрит на пустую дорогу и щурится от солнца.

Звук: горячий ветер, скрип железной калитки, далёкие цикады, медленная звенящая электрогитара.

${KEEP_RU}` },
]
