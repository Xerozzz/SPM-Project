import { expect, test } from '@playwright/test'

// SCRUM-27 (F1): unauthenticated users see sign-in; the scaffold health check
// moves behind the session, so the public expectation is the sign-in page.
test('unauthenticated users are shown the sign-in page', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
})
