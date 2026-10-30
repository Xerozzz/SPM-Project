import { expect, type Page, test } from '@playwright/test'

// SCRUM-99 / SCRUM-29 / SCRUM-59: workspace links and safe form navigation.
async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill('password123')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible()
}
test('workspace navigation survives refresh and browser Back', async ({ page }) => {
  await signIn(page, 'organiser@example.com')
  await page.getByRole('button', { name: 'Event Calendar', exact: true }).click()
  await expect(page).toHaveURL(/view=event-calendar/)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Event Calendar', exact: true })).toBeVisible()
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await expect(page.getByRole('heading', { name: 'Notifications', exact: true })).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Event Calendar', exact: true })).toBeVisible()
})
test('cancelled navigation preserves an unfinished event and accepted navigation discards it', async ({
  page,
}) => {
  await signIn(page, 'organiser@example.com')
  await page.getByRole('button', { name: /Create event$/ }).click()
  await page.getByLabel('Name *', { exact: true }).fill('Unfinished browser draft')
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await expect(page.getByLabel('Name *', { exact: true })).toHaveValue('Unfinished browser draft')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await expect(page.getByRole('heading', { name: 'Notifications', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'My Events', exact: true }).click()
  await page.getByRole('button', { name: /Create event$/ }).click()
  await expect(page.getByLabel('Name *', { exact: true })).toHaveValue('')
})
test('leaving an unfinished venue can be cancelled without losing its values', async ({ page }) => {
  await signIn(page, 'venue-staff@example.com')
  await page.getByRole('button', { name: 'Venue Catalogue', exact: true }).click()
  await page.getByRole('button', { name: 'Add venue', exact: true }).click()
  await page.getByLabel('Name', { exact: true }).fill('Unfinished venue')
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.getByRole('button', { name: 'Booking Decisions', exact: true }).click()
  await expect(page.getByLabel('Name', { exact: true })).toHaveValue('Unfinished venue')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Booking Decisions', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Booking Decisions', exact: true })).toBeVisible()
})

test('browser Back can be cancelled while an event has unsaved changes', async ({ page }) => {
  await signIn(page, 'organiser@example.com')
  await page.getByRole('button', { name: /^Notifications/ }).click()
  await page.getByRole('button', { name: 'My Events', exact: true }).click()
  await page.getByRole('button', { name: /Create event$/ }).click()
  await page.getByLabel('Name *', { exact: true }).fill('Keep this draft')
  page.once('dialog', (dialog) => dialog.dismiss())
  await page.goBack()
  await expect(page).toHaveURL(/view=my-events/)
  await expect(page.getByLabel('Name *', { exact: true })).toHaveValue('Keep this draft')
  page.once('dialog', (dialog) => dialog.accept())
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Notifications', exact: true })).toBeVisible()
})
