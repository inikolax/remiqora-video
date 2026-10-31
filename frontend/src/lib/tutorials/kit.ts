// The scenarios' building blocks (lib/tutorials): a scenario is a help section of the group «Сценарии» - a lead,
// numbered steps (the .flow of «От идеи до ролика»), a link that opens the screen a step is on, tips.
import type { HelpSection } from '../help'

export const GROUP = 'Сценарии'
export const GROUP_EN = 'Scenarios'   // tutorials/en: the English twins

// a step: its title, what to do (HTML), an optional line under it
export const step = (title: string, html: string, small = '') =>
  `<li><b>${title}</b>${html.startsWith('<') ? html : `<p>${html}</p>`}${small ? `<small>${small}</small>` : ''}</li>`
export const steps = (...items: string[]) => `<ol class="flow">${items.join('')}</ol>`
// a link to a screen of the app («Открыть главную», «Модели и настройки»): its hash route, e.g. '/', '/models', '/lab'
export const go = (to: string, label: string) => `<a class="tut-go" href="#${to}">${label} →</a>`
// a link to another help section or scenario
export const see = (id: string, label: string) => `<a href="#/help/${id}">${label}</a>`
export const tip = (html: string) => `<div class="tip">${html}</div>`
// what you get / how long, in a muted line under the lead
export const meta = (html: string) => `<p class="note">${html}</p>`

export const scenario = (id: string, title: string, lead: string, body: string, group = GROUP): HelpSection =>
  ({ id: `tut-${id}`, group, title, html: `<p class="lead">${lead}</p>${body}` })
