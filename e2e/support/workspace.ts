import { expect, type Page } from '@playwright/test'

/** Follow the same workspace navigation as a user, including the sidebar's unread badge. */
export async function openWorkspace(page: Page, name: string) {
  await page
    .getByRole('button', {
      name: name === 'Notifications' ? /^Notifications/ : name,
      exact: name !== 'Notifications',
    })
    .click()
  await expect(page.getByRole('heading', { name, exact: true, level: 1 })).toBeVisible()
}

/** Scope to the active screen: other role screens remain mounted but hidden. */
export function eventRow(page: Page, name: string) {
  return page
    .locator('main > section:not([hidden])')
    .getByRole('listitem')
    .filter({
      has: page.getByRole('heading', { name, exact: true }),
    })
}

/** Notes, decisions and history live in details rather than in a summary card. */
export async function openEvent(page: Page, name: string, workspace: string) {
  await openWorkspace(page, workspace)
  const back = page.getByRole('button', { name: `← Back to ${workspace}`, exact: true })
  if (await back.isVisible()) await back.click()
  await page.getByRole('button', { name: `View details for ${name}`, exact: true }).click()
  return eventRow(page, name)
}

/** Identity matching uses the retained record, even when its details are collapsed. */
export function notificationEntries(page: Page, action: string | RegExp, eventId: string) {
  return page
    .getByRole('region', { name: 'Notifications', exact: true })
    .getByRole('listitem')
    .filter({ hasText: eventId })
    .filter({ hasText: action })
}
