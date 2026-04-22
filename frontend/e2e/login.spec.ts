import { expect, test } from '@playwright/test';

test('login redirects to chat', async ({ page }) => {
  await page.route('**/auth/login', async (route) => {
    await route.abort();
  });

  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.getByLabel('用户名').fill('admin');
  await page.getByLabel('密码').fill('admin123');
  await page.getByRole('button', { name: '登录' }).click();

  await expect(page).toHaveURL(/\/chat$/);
  await expect(
    page.getByPlaceholder(/请输入保单、理赔、服务等问题/),
  ).toBeVisible();
});
