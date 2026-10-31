// Numbers and dates in the interface's language (Russian: comma decimals, «сегодня, 14:05»).
import { currentLocale, t } from '../i18n'

// Russian-only, kept for the screens not yet moved to t() plurals ('сцена | сцены | сцен' in a locale file)
export const plural = (n: number, one: string, few: string, many: string) =>
  n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? few : many
const tag = () => (currentLocale() === 'en' ? 'en-US' : 'ru-RU')
export const mins = (sec: number) =>
  sec < 90 ? `${Math.round(sec)} ${t('common.s')}` : `${(sec / 60).toLocaleString(tag(), { maximumFractionDigits: 0 })} ${t('common.min')}`
// the lab's: a tenth of a minute counts there (1,6 мин)
export const minsTenth = (sec: number) =>
  sec < 90 ? `${Math.round(sec)} ${t('common.s')}` : `${(sec / 60).toLocaleString(tag(), { maximumFractionDigits: 1 })} ${t('common.min')}`
export const mmss = (s: number) => { const r = Math.round(s); return `${Math.floor(r / 60)}:${String(r % 60).padStart(2, '0')}` }   // 119.8 -> 2:00, not 1:60
export const gb = (v: number) => v.toLocaleString(tag(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })
// frames at 24 fps -> seconds with one decimal
export const secs = (frames: number) => (frames / 24).toLocaleString(tag(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })
// a number with the interface's decimal mark (2,5 / 2.5)
export const dec = (x: number | string) => (currentLocale() === 'en' ? String(x) : String(x).replace('.', ','))
export function when(ts: number) {
  const d = new Date(ts * 1000), now = new Date(), hm = d.toLocaleTimeString(tag(), { hour: '2-digit', minute: '2-digit' })
  const days = Math.round((+new Date(now.toDateString()) - +new Date(d.toDateString())) / 864e5)
  return days === 0 ? t('shelf.today', { hm }) : days === 1 ? t('shelf.yesterday', { hm }) : d.toLocaleDateString(tag(), { day: 'numeric', month: 'long' })
}
