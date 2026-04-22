import { expect, test } from '@playwright/test';

test('knowledge page can retry a failed job', async ({ page }) => {
  const persistedState = JSON.stringify({
    state: {
      themeMode: 'light',
      lang: 'zh',
      user: { username: 'admin', token: 'mock-token-admin' },
    },
    version: 0,
  });

  await page.addInitScript((value) => {
    window.localStorage.setItem('aia-app-store', value);
  }, persistedState);

  let jobs = [
    {
      job_id: 'job-failed-1',
      type: 'url',
      source: 'https://example.com/data.json',
      collection: 'aia_knowledge_base',
      status: 'failed',
      created_at: '2026-04-22T13:00:00Z',
      started_at: null,
      finished_at: '2026-04-22T13:01:00Z',
      doc_count: 0,
      schema: '',
      skipped: 0,
      failed_items: 1,
      error: 'timeout',
    },
  ];
  let retryTriggered = false;

  await page.route('**/kb/jobs', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: jobs });
      return;
    }
    await route.continue();
  });
  await page.route('**/kb/jobs/job-failed-1/retry', async (route) => {
    retryTriggered = true;
    jobs = [
      {
        ...jobs[0],
        status: 'pending',
        error: "",
      },
    ];
    await route.fulfill({
      json: { job_id: 'job-failed-1', status: 'pending' },
    });
  });
  await page.route('**/kb/collections', async (route) => {
    await route.fulfill({
      json: { collections: [{ name: 'aia_knowledge_base', doc_count: 1 }] },
    });
  });
  await page.route('**/kb/docs**', async (route) => {
    await route.fulfill({
      json: {
        total: 1,
        offset: 0,
        limit: 10,
        collection: 'aia_knowledge_base',
        docs: [
          {
            id: 'doc-1',
            title: '示例文档',
            content: '示例内容',
            service_name: '',
            service_url: '',
            source_file: '',
            category: '',
            schema: '',
            score: null,
          },
        ],
      },
    });
  });
  await page.route('**/health**', async (route) => {
    await route.fulfill({
      json: {
        status: 'ok',
        doc_count: 1,
        collection: 'aia_knowledge_base',
        last_updated: '2026-04-22T13:00:00Z',
      },
    });
  });

  await page.goto('/knowledge', { waitUntil: 'domcontentloaded' });

  await expect(page.getByText('知识库管理')).toBeVisible();
  await page.getByRole('tab', { name: '导入知识' }).click();
  const retryButton = page.getByRole('button', { name: '重试任务' });
  await expect(retryButton).toBeVisible();
  await retryButton.click();

  await expect(page.getByText('已重新加入导入队列')).toBeVisible();
  await expect(page.getByText('等待中')).toBeVisible();
  expect(retryTriggered).toBeTruthy();
});
