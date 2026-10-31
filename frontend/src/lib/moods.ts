// A mood's name in the interface's language; the mood itself (a key of app/main.py MOODS) stays as it is stored.
import { t } from '../i18n'

const KEY: Record<string, string> = { 'Кино': 'cinema', 'Клип': 'clip', 'Реклама': 'ad', 'Фэнтези и эффекты': 'fantasy', 'Документальное': 'docu' }
export const moodName = (m: string) => (KEY[m] ? t(`mood.${KEY[m]}`) : m)
