// The «Герой» node's actor panel (components/graph/ActorPanel.vue, app/actors.py).
export default {
  ru: {
    title: 'Актёр', fromLib: 'Из библиотеки', toLib: 'В библиотеку', toLibTitle: 'Сохранить этого героя в библиотеку актёров: внешность, одежда, фото',
    empty: 'В библиотеке пока никого: сохраните героя кнопкой «В библиотеку».', gone: 'Этого актёра больше нет в библиотеке: узел работает по своим полям.',
    unuse: 'Убрать актёра', hint: 'Внешность, одежда и картинка героя берутся у актёра (картинка — лицо с листа); свои поля ниже не используются.',
    face: 'Лицо', turn: 'В рост: анфас, сбоку, со спины', noSheet: 'Листа ещё нет: «Нарисовать лист».', lookIs: 'Нарисован в виде: {look}',
    sheet: 'Нарисовать лист', sheetTitle: 'FLUX.2 Klein рисует лицо крупно и героя в рост на чёрном фоне по фото актёра; без фото — сначала по описанию (Krea 2)',
    photo: 'Фото', tries: 'Пробы', triesHint: 'Выберите до четырёх видов: лицо актёра перерисуется в каждом по два раза. Щелчок по пробе делает её видом актёра, лист перерисуется в нём.',
    makeTries: 'Сделать пробы ({n})', pickTitle: 'Сделать этот вид видом актёра', pickAsk: 'Сделать этот вид видом актёра и перерисовать лист в нём?', clear: 'Убрать пробы',
    drawing: 'рисует лист', trying: 'рисует пробы', queue: 'Ждёт очереди…', working: '{what}… {s} с', failed: 'Не получилось нарисовать',
    namePrompt: 'Имя актёра', saved: 'Актёр «{name}» в библиотеке: выберите его кнопкой «Из библиотеки»',
  },
  en: {
    title: 'Actor', fromLib: 'From the library', toLib: 'To the library', toLibTitle: 'Save this hero into the actor library: look, outfit, photo',
    empty: 'Nobody in the library yet: save a hero with «To the library».', gone: 'This actor is no longer in the library: the node works from its own fields.',
    unuse: 'Remove the actor', hint: "The hero's look, outfit and picture come from the actor (the picture is the sheet's face); the fields below are not used.",
    face: 'Face', turn: 'Full body: front, side, back', noSheet: 'No sheet yet: «Draw the sheet».', lookIs: 'Drawn in the look: {look}',
    sheet: 'Draw the sheet', sheetTitle: "FLUX.2 Klein draws the face close-up and the full-body turnaround on black from the actor's photo; with no photo, Krea 2 draws the figure from the look first",
    photo: 'Photo', tries: 'Tries', triesHint: "Pick up to four looks: the actor's face is redrawn in each, twice. Click a try to make it the actor's look; the sheet is redrawn in it.",
    makeTries: 'Make tries ({n})', pickTitle: "Make this the actor's look", pickAsk: "Make this the actor's look and redraw the sheet in it?", clear: 'Clear the tries',
    drawing: 'drawing the sheet', trying: 'drawing the tries', queue: 'Waiting in the queue…', working: '{what}… {s} s', failed: 'The drawing failed',
    namePrompt: "The actor's name", saved: 'Actor «{name}» is in the library: pick it with «From the library»',
  },
}
