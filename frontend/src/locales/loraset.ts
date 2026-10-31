// components/LoraSet.vue: the LoRA of a new video and its pictures.
export default {
  ru: {
    title: 'LoRA', sub: 'для видео и картинок, всё меняется потом', picked: 'выбрано: {n}',
    video: 'Видео (модель ролика)', krea: 'Портреты и места (Krea 2)', flux2: 'Кадры сцен (FLUX.2 Klein)',
    pics: 'LoRA картинок', picsSub: 'с ними рисуются портреты, места и кадры сцен',
    lineTitle: 'LoRA, с которыми рисует {m}; это настройка проекта — те же видны в панели съёмки', strength: 'Сила', more: 'ещё', addShort: 'добавить', search: 'Найти LoRA', nothing: 'всё уже добавлено или не найдено',
    short: { krea: 'Krea 2', flux2: 'FLUX.2' }, none: 'нет', cardSub: 'стиль видео и картинок', dragTitle: 'Сила: тяните по фишке или стрелки ← →; × или Delete убирает',
    cardNote: 'Сила — заливка фишки: тяните по ней вбок. Всё это потом меняется в раскадровке: у героя, мест, кадра сцены и в панели съёмки.',
    row: { video: 'Видео', videoSub: '{m}, все сцены', krea: 'Портреты', kreaSub: 'Krea 2: герои, места', flux2: 'Кадры сцен', flux2Sub: 'FLUX.2 Klein', off: 'не рисуются: галка снята' },
    heroHint: 'стиль портрета: Krea 2 — новые лица и пробы, FLUX.2 — правка черт; те же LoRA у мест и кадров',
    placesHint: 'стиль картинок мест (Krea 2); те же LoRA у героя',
    add: '{x}: добавить LoRA', fromLibrary: '+ из библиотеки', empty: 'в папке нет LoRA', strengthOf: 'Сила {x}', remove: 'Убрать {x}',
  },
  en: {
    title: 'LoRA', sub: 'for the video and the pictures, all can change later', picked: '{n} picked',
    video: "Video (the video's model)", krea: 'Portraits and places (Krea 2)', flux2: 'Scene frames (FLUX.2 Klein)',
    pics: 'Picture LoRA', picsSub: 'the portraits, places and scene frames are drawn with them',
    lineTitle: "The LoRA {m} draws with; it is the project's setting - the same show in the shooting panel", strength: 'Strength', more: 'more', addShort: 'add', search: 'Find a LoRA', nothing: 'all added or none found',
    short: { krea: 'Krea 2', flux2: 'FLUX.2' }, none: 'none', cardSub: 'the style of the video and the pictures', dragTitle: 'Strength: drag along the chip or ← →; × or Delete removes it',
    cardNote: 'Strength is the chip\'s fill: drag along it. All of it changes later on the storyboard: at the hero, the places, a scene\'s frame and in the shooting panel.',
    row: { video: 'Video', videoSub: '{m}, every scene', krea: 'Portraits', kreaSub: 'Krea 2: heroes, places', flux2: 'Scene frames', flux2Sub: 'FLUX.2 Klein', off: 'not drawn: the tick is off' },
    heroHint: "the portrait's style: Krea 2 - new faces and tries, FLUX.2 - adjusted features; the same LoRA at the places and frames",
    placesHint: "the places' pictures' style (Krea 2); the same LoRA at the hero",
    add: '{x}: add a LoRA', fromLibrary: '+ from the library', empty: 'no LoRA in the folder', strengthOf: '{x} strength', remove: 'Remove {x}',
  },
}
