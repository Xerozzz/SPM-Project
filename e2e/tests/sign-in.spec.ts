import { expect, test } from '@playwright/test'

// SCRUM-27 (F1): sign in with a seeded account, see the session, sign out.
// Relies on the dev seed the api container runs on start (see README, "Seeded accounts").

test('a seeded user can sign in, sees their roles, and can sign out', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()

  await page.getByLabel('Email').fill('coordinator@example.com')
  await page.getByLabel('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByText('Signed in as: coordinator')).toBeVisible()

  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
})

test('wrong credentials show a generic error and stay on sign-in', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Email').fill('coordinator@example.com')
  await page.getByLabel('Password').fill('not-the-password')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByRole('alert')).toHaveText('Invalid email or password')
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
})
