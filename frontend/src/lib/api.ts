// The server's API: JSON in and out (a FormData body goes as it is). An error comes back as an Error with the
// server's words; FastAPI's validation errors (a list of {loc, msg, ctx}) are said in words.
import { currentLocale, t } from '../i18n'
const FIELDS = ['prompt', 'seconds', 'count', 'strength', 'seed']
const field = (x: string | number) => (FIELDS.includes(String(x)) ? t(`misc.field.${x}`) : x)

interface Detail { loc?: (string | number)[]; msg: string; type?: string; ctx?: Record<string, unknown> }

function humanize(detail: unknown): string {
  if (!Array.isArray(detail)) return JSON.stringify(detail)
  return (detail as Detail[]).map((d) => {
    const f = d.loc?.filter((x) => x !== 'body').map(field).join(' → ') || t('misc.field.any')
    if (d.type === 'string_too_long') return t('misc.tooLong', { f, n: String(d.ctx?.max_length) })
    if (d.type === 'string_too_short') return t('misc.tooShort', { f })
    if (d.type === 'less_than_equal') return t('misc.maxN', { f, n: String(d.ctx?.le) })
    if (d.type === 'greater_than_equal') return t('misc.minN', { f, n: String(d.ctx?.ge) })
    return `${f}: ${d.msg}`
  }).join('\n')
}

export async function api<T = any>(url: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const isForm = opts.body instanceof FormData
  const r = await fetch(url, {
    method: opts.method,
    // the server answers in the page's language (app/i18n.py)
    headers: { 'X-Lang': currentLocale(), ...(isForm ? {} : { 'Content-Type': 'application/json' }) },
    body: opts.body ? (isForm ? (opts.body as FormData) : JSON.stringify(opts.body)) : undefined,
  })
  if (!r.ok) {
    let msg = r.statusText, detail: unknown
    try {
      const j = await r.json()
      detail = j.detail
      msg = typeof j.detail === 'string' ? j.detail : j.detail && typeof j.detail === 'object' && 'message' in j.detail ? String(j.detail.message) : humanize(j.detail)
    } catch { /* not JSON */ }
    // the status and the server's answer ride along: the graph takes the server's document from a 409
    throw Object.assign(new Error(msg), { status: r.status, detail })
  }
  return r.json()
}

export const post = <T = any>(url: string, body?: unknown) => api<T>(url, { method: 'POST', body })
