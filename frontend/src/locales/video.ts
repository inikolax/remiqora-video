// The video screen (VideoView.vue) and the shots' state (lib/shots.ts, shared with the graph), lib/project.ts's output.
export default {
  ru: {
    asShot: 'как снято',
    shot: {
      cached: 'из кэша', step: 'шаг {step}/{steps}', loading: 'загрузка модели', preparing: 'готовится',
      waitsFrame: 'ждёт кадр {i}-й', queued: 'в очереди', skipped: 'отложена', done: 'готово', none: 'не снята',
    },
    title: 'Ролик', firstShooting: 'Первая сцена снимается…', notShot: 'Ролик ещё не снят',
    again: {
      reedit: 'Собрать по монтажу', remix: 'Свести музыку заново', refinish: 'Пересобрать: {out}',
      allDone: 'Всё снято', changed: 'Доснять изменённое', shoot: 'Снять ролик',
    },
    scenesN: '{n} сцена | {n} сцены | {n} сцен',
    stage: {
      board: 'Раскадровка готова', model: 'Модель и энкодер', starting: 'запуск', loading: 'загрузка', inMemory: 'в памяти',
      scenes: 'Сцены 1–{n}', joinMontage: 'Склейка по монтажу', join: 'Склейка и звук', montageChanged: 'монтаж изменён',
      music: 'Музыка: {name}', trackChanged: 'трек изменён', changed: 'изменено',
    },
    stopNowAsk: 'Остановить съёмку сразу? Текущая сцена пропадёт.',
    left: 'Осталось', inQueue: 'В очереди', ready: 'Готово', notAll: 'Снято не всё',
    willStopAfter: 'Остановится после текущей сцены', stopAfter: 'Остановить после текущей сцены', stopNow: 'Остановить сразу',
    backToBoard: 'Вернуться к раскадровке', done: 'Ролик готов', whenReady: 'Когда будет готово', file: 'ролик',
    downloadMp4: 'Скачать MP4', montage: 'Монтаж', montageTitle: 'Обрезать сцены, переставить, переходы, звуки — и собрать заново',
    shootFinal: 'Снять финал', shootDraft: 'Снять черновик', more: 'Ещё', moreTitle: 'Снять ролик в другом качестве',
    cacheNote: 'Готовые сцены лежат в кэше: поправите одну — переснимутся только она и продолжения после неё. Финал снимается с теми же сидами.',
  },
  en: {
    asShot: 'as shot',
    shot: {
      cached: 'from the cache', step: 'step {step}/{steps}', loading: 'loading the model', preparing: 'getting ready',
      waitsFrame: "waits for scene {i}'s frame", queued: 'queued', skipped: 'put off', done: 'ready', none: 'not shot',
    },
    title: 'Video', firstShooting: 'Shooting the first scene…', notShot: 'The video is not shot yet',
    again: {
      reedit: 'Build from the montage', remix: 'Remix the music', refinish: 'Rebuild: {out}',
      allDone: 'All shot', changed: 'Shoot what changed', shoot: 'Shoot video',
    },
    scenesN: '{n} scene | {n} scenes',
    stage: {
      board: 'Storyboard ready', model: 'Model and encoder', starting: 'starting', loading: 'loading', inMemory: 'in memory',
      scenes: 'Scenes 1–{n}', joinMontage: 'Joining by the montage', join: 'Joining and sound', montageChanged: 'montage changed',
      music: 'Music: {name}', trackChanged: 'track changed', changed: 'changed',
    },
    stopNowAsk: 'Stop shooting right now? The current scene will be lost.',
    left: 'Left', inQueue: 'Queued', ready: 'Ready', notAll: 'Not all shot',
    willStopAfter: 'Will stop after the current scene', stopAfter: 'Stop after the current scene', stopNow: 'Stop now',
    backToBoard: 'Back to the storyboard', done: 'The video is ready', whenReady: 'When it is ready', file: 'video',
    downloadMp4: 'Download MP4', montage: 'Montage', montageTitle: 'Trim scenes, reorder, transitions, sounds — and build again',
    shootFinal: 'Shoot final', shootDraft: 'Shoot draft', more: 'More', moreTitle: 'Shoot the video in the other quality',
    cacheNote: 'Finished scenes are kept in the cache: fix one and only it and the continuations after it get reshot. The final is shot with the same seeds.',
  },
}
