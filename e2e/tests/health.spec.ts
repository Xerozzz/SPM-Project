import { expect, test } from '@playwright/test'

// Smoke test for the scaffold: prove the three containers are actually wired together
// by loading the page and waiting for the status the API reports about its database.
test('the home page reports that the API and database are healthy', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'ConnectSphere' })).toBeVisible()
  await expect(page.getByRole('status')).toHaveText(/API and database are ok/)
})
