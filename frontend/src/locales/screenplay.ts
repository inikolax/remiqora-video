// A mini-series in the graph: the «Сериал» bible node and the «Сценарий» node - the panels
// (components/graph/NodeInspector.vue), the cards (EditNode.vue) and «Дальше» (lib/nodeHelp.ts).
export default {
  ru: {
    series: {
      title: 'Название', look: 'Вид', lookNone: 'Решит сценарист', style: 'Заметки о виде', world: 'Мир', characters: 'Персонажи', recap: 'Ранее',
      titlePh: 'Маша и Мурзик', stylePh: 'яркие тёплые цвета, мягкие формы', worldPh: 'где и когда это происходит', charactersPh: 'кто они, как говорят, что любят',
      recapPh: 'что было в прошлых сериях; «Добавить в "Ранее"» у Сценария дописывает сюда итог серии',
      hint: 'Библия сериала: её читает Сценарий. Вид из списка ставится каждому шоту серии. Один узел идёт во все серии — копируйте граф серии.',
      card: 'Вид: {look}',
    },
    play: {
      text: 'Сценарий', textPh: 'СЦЕНА 1. Кухня, утро.\nМАША (сердито): Ты опять съел весь сыр?\nКОТ (с улыбкой): Это был не я.\n— Кот прячет хвост за спину.',
      seconds: 'Длина серии, с', write: 'Написать сценарий', writeAgain: 'Написать заново', expand: 'Развернуть в шоты', srt: 'Экспорт .srt', recap: 'Добавить в "Ранее"',
      lines: 'реплик: {l}, действий: {a}, шотов: {n}', unknown: 'Нет героя с таким именем: {list}. Эти реплики пойдут без лица.',
      hintIntro: 'Формат сценария, по строке на реплику или действие:',
      hScene: '«СЦЕНА 1. Место, время.» — новое место',
      hLine: '«ИМЯ (как): реплика» — говорит герой; имя — как у узла Герой, ОН и ОНА — по полу',
      hAction: '«— действие» — шот без слов',
      hHow: '«как»: тихо, шёпотом, громко, кричит, сердито, с улыбкой, грустно… — незнакомое слово остаётся как есть',
      expandHint: '«Развернуть в шоты» ставит справа Промт и Сцену на каждую реплику и действие: говорит один, другой слушает; лица героев — во вход «лица» (первым — говорящий); длина шота — по словам. Место и действия по-русски сначала переведёт сценарист (перевод запоминается). Повторно — заменит свои узлы.',
      card: 'сцен: {s}, шотов: {n}', untranslated: 'Не удалось перевести место или действие на английский — проверьте промты шотов: {list}', cardNew: 'впишите сценарий или нажмите «Написать сценарий»',
    },
    next: {
      seriesTitle: 'Впишите название и опишите мир сериала — Сценарий прочтёт это.', seriesLink: 'Соедините «текст» со входом «сериал» узла Сценарий.',
      seriesOk: 'Готово: «Ранее» пополняется кнопкой у Сценария.',
      playCast: 'Подключите героев (узлы Герой) ко входу «герои» — по их именам разберутся реплики.',
      playText: 'Впишите сценарий по формату или нажмите «Написать сценарий» (нужна Идея; по кнопке, ~1 мин).',
      playExpand: 'Нажмите «Развернуть в шоты» — справа появятся Промты и Сцены, Монтаж и Выход.',
      playOk: 'Шоты справа — «Снять всё» в панели графа. «Экспорт .srt» — субтитры реплик.',
    },
  },
  en: {
    series: {
      title: 'Title', look: 'Look', lookNone: 'Writer decides', style: 'Notes on the look', world: 'World', characters: 'Characters', recap: 'Previously',
      titlePh: 'Masha and Murzik', stylePh: 'bright warm colours, soft shapes', worldPh: 'where and when it happens', charactersPh: 'who they are, how they talk, what they like',
      recapPh: 'what happened in earlier episodes; «Add to Previously» on the Screenplay appends the episode\'s summary here',
      hint: 'The series bible: the Screenplay reads it. A look from the list is set on every shot of the episode. One node goes into every episode: copy the episode\'s graph.',
      card: 'Look: {look}',
    },
    play: {
      text: 'Screenplay', textPh: 'SCENE 1. Kitchen, morning.\nMASHA (angry): Did you eat all the cheese again?\nCAT (smiling): It was not me.\n— The cat hides its tail behind its back.',
      seconds: 'Episode length, s', write: 'Write the screenplay', writeAgain: 'Write again', expand: 'Expand into shots', srt: 'Export .srt', recap: 'Add to Previously',
      lines: 'lines: {l}, actions: {a}, shots: {n}', unknown: 'No hero with this name: {list}. Those lines go without a face.',
      hintIntro: 'The screenplay format, a row per line or action:',
      hScene: '«SCENE 1. Place, time.» starts a new place (СЦЕНА works too)',
      hLine: '«NAME (how): line» a hero speaks; the name as on the Hero node, ОН and ОНА go by gender',
      hAction: '«— action» a shot without words',
      hHow: '«how»: quiet, whisper, loud, calm, smiling, gentle… (Russian words like тихо, сердито, грустно work too); an unknown word is kept as it is. The lines are spoken in Russian',
      expandHint: '«Expand into shots» puts a Prompt and a Scene on the right for every line and action: one speaks, the other listens; the heroes\' faces go into «faces» (the speaker first); a shot is as long as its words. Places and actions written in Russian are translated by the writer first (the translation is kept). Again: it replaces its own nodes.',
      card: 'scenes: {s}, shots: {n}', untranslated: 'Could not translate a place or an action into English - check the prompts of shots: {list}', cardNew: 'write the screenplay or press «Write the screenplay»',
    },
    next: {
      seriesTitle: 'Type the title and describe the series\' world: the Screenplay reads it.', seriesLink: 'Connect «text» to the Screenplay\'s «series» input.',
      seriesOk: 'Ready: «Previously» grows with the button on the Screenplay.',
      playCast: 'Connect the heroes (Hero nodes) to «cast»: the lines are told apart by their names.',
      playText: 'Type a screenplay in the format or press «Write the screenplay» (needs an Idea; by the button, ~1 min).',
      playExpand: 'Press «Expand into shots»: Prompts and Scenes, a Montage and an Output appear on the right.',
      playOk: 'The shots are on the right: «Shoot all» in the graph\'s panel. «Export .srt»: the lines\' subtitles.',
    },
  },
}
