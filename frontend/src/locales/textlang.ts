// The texts' language (app/i18n.py): the setting on «Модели и настройки» → «Сценарист», and the storyboard's
// «Перевести на …» button.
export default {
  ru: {
    label: 'Язык текстов',
    hint: 'На нём вы пишете идеи и читаете сцены; сценарист пишет тексты сцен на нём, переводчик переводит с него в английский промт. Реплики героев звучат на языке ролика — том, что был выбран, когда его написали. Промты для видеомоделей всегда английские.',
    saved: 'Язык текстов: {v}',
    translate: 'Перевести на {v}',
    translateTitle: 'Тексты сцен на другом языке — перевести их на {v} для чтения (промты и снятое не меняются)',
  },
  en: {
    label: 'Text language',
    hint: "The language you write ideas and read scenes in: the writer writes the scene texts in it, the translator turns it into the English prompt. The characters speak the video's language — the one chosen when it was written. Prompts for the video models are always English.",
    saved: 'Text language: {v}',
    translate: 'Translate to {v}',
    translateTitle: 'Scene texts in another language: translate them to {v} for reading (prompts and shots stay as they are)',
  },
}
