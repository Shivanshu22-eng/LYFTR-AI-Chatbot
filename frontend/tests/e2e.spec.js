import { test, expect } from '@playwright/test';

/**
 * Install deterministic API route mocks for /health, /sessions, and /sessions/:id/messages.
 */
async function mockBackendBase(page, { sessions = [], delayChatMs = 0 } = {}) {
  let sessionCounter = 0;

  await page.route('**/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', keys_configured: 2, cache_enabled: true }),
    });
  });

  await page.route('**/sessions/*/messages', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    });
  });

  await page.route('**/sessions', async (route) => {
    if (route.request().method() === 'POST') {
      sessionCounter += 1;
      const now = new Date().toISOString();
      const created = {
        id: `e2e-session-${sessionCounter}`,
        title: 'New Chat',
        created_at: now,
        updated_at: now,
      };
      sessions.unshift(created);
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(created),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(sessions),
      });
    }
  });

  return { delayChatMs };
}

test.describe('LYFTR AI Chatbot E2E', () => {
  test('renders welcome screen, generates session on load, sends multi-turn messages, displays metadata & loading state', async ({ page }) => {
    const createdSessionIds = [];
    const chatRequests = [];
    const sessions = [];

    await mockBackendBase(page, { sessions });

    await page.route('**/chat', async (route) => {
      const body = route.request().postDataJSON();
      chatRequests.push(body);
      const turn = chatRequests.length;
      // Brief delay so loading indicator is observable
      await new Promise((r) => setTimeout(r, 150));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: body.session_id,
          reply: `Echo: ${body.message}`,
          metadata: {
            resolution_source: turn === 1 ? 'LIVE_INFERENCE' : 'LLM_CACHE',
            model: 'gemini/gemini-3.8-flash',
            latency_ms: turn === 1 ? 142.5 : 2.1,
            input_tokens: 12,
            output_tokens: 7,
            key_id: turn === 1 ? 'key-1' : null,
            fallback_attempts: 0,
          },
        }),
      });
    });

    page.on('response', async (res) => {
      if (res.url().endsWith('/sessions') && res.request().method() === 'POST' && res.status() === 201) {
        const data = await res.json().catch(() => null);
        if (data?.id) createdSessionIds.push(data.id);
      }
    });

    // 1. Open the actual React application
    await page.goto('/');

    // 2. Verify welcome screen renders & backend is connected
    await expect(page.getByRole('heading', { name: 'Welcome to LYFTR AI' })).toBeVisible();
    await expect(page.locator('.status-bar')).toContainText('Connected');

    // 3. Verify a new session ID is generated on page load
    await expect.poll(() => createdSessionIds.length).toBeGreaterThanOrEqual(1);

    // 4. Verify chat input & send button are visible
    const chatInput = page.getByTestId('chat-input');
    const sendButton = page.getByTestId('send-button');
    await expect(chatInput).toBeVisible();
    await expect(sendButton).toBeVisible();

    // 5. Enter a message and click Send (wait for loading indicator)
    await chatInput.fill('Hello E2E turn 1');
    await sendButton.click();

    // 6. Verify input clears after sending
    await expect(chatInput).toHaveValue('');

    // 7. Verify loading indicator appears
    await expect(page.locator('.typing-indicator')).toBeVisible();

    // 8. Verify assistant response appears
    const firstAssistant = page.getByTestId('assistant-message').first();
    await expect(firstAssistant).toBeVisible({ timeout: 10000 });
    await expect(firstAssistant).toContainText('Hello E2E turn 1');

    // 9. Verify all required metadata data-testid attributes appear
    await expect(firstAssistant.getByTestId('meta-source')).toBeVisible();
    await expect(firstAssistant.getByTestId('meta-model')).toBeVisible();
    await expect(firstAssistant.getByTestId('meta-latency')).toBeVisible();
    await expect(firstAssistant.getByTestId('meta-input-tokens')).toBeVisible();
    await expect(firstAssistant.getByTestId('meta-output-tokens')).toBeVisible();

    // 10 & 11. Send a second message and verify multi-turn conversation works in same session
    await chatInput.fill('Follow up turn 2');
    await sendButton.click();
    await expect(chatInput).toHaveValue('');

    const assistantMessages = page.getByTestId('assistant-message');
    await expect(assistantMessages).toHaveCount(2, { timeout: 10000 });
    await expect(assistantMessages.nth(1)).toContainText('turn 2');
    expect(chatRequests.length).toBe(2);
    expect(createdSessionIds).toContain(chatRequests[0].session_id);
    expect(chatRequests[1].session_id).toBe(chatRequests[0].session_id);

    // 12. Reload page and verify a new session ID is generated
    const countBeforeReload = createdSessionIds.length;
    await page.reload();
    await expect.poll(() => createdSessionIds.length).toBeGreaterThan(countBeforeReload);
    expect(createdSessionIds[createdSessionIds.length - 1]).not.toBe(chatRequests[0].session_id);
  });

  test('supports resolution_source field when backend returns resolution_source', async ({ page }) => {
    await mockBackendBase(page);

    await page.route('**/chat', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'e2e-session-1',
          reply: 'Reply with resolution_source',
          metadata: {
            resolution_source: 'LLM_CACHE',
            model: 'gemini/gemini-3.8-flash',
            latency_ms: 1.2,
            input_tokens: 14,
            output_tokens: 6,
            key_id: null,
            fallback_attempts: 0,
          },
        }),
      });
    });

    await page.goto('/');
    await page.getByTestId('chat-input').fill('Check resolution_source');
    await page.getByTestId('send-button').click();

    const msg = page.getByTestId('assistant-message').first();
    await expect(msg).toBeVisible();
    await expect(msg.getByTestId('meta-source')).toContainText('Cache');
    await expect(msg.getByTestId('meta-model')).toContainText('gemini/gemini-3.8-flash');
    await expect(msg.getByTestId('meta-latency')).toContainText('1.2ms');
    await expect(msg.getByTestId('meta-input-tokens')).toContainText('14');
    await expect(msg.getByTestId('meta-output-tokens')).toContainText('6');
  });

  test('displays error notification when backend is unavailable', async ({ page }) => {
    await page.route('**/health', (route) =>
      route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Unavailable' }) })
    );
    await page.route('**/sessions', (route) =>
      route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Unavailable' }) })
    );
    await page.route('**/chat', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'All AI providers unavailable (503)' }),
      })
    );

    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Welcome to LYFTR AI' })).toBeVisible();
    await expect(page.locator('.status-bar')).toContainText('Offline');
    await expect(page.getByTestId('chat-input')).toBeVisible();

    await page.getByTestId('chat-input').fill('Trigger backend error');
    await page.getByTestId('send-button').click();

    const alert = page.locator('[role="alert"]');
    await expect(alert).toBeVisible({ timeout: 5000 });
    await expect(alert).toContainText('All AI providers unavailable (503)');
  });

  test('is usable on mobile viewport (375x812)', async ({ page }) => {
    await mockBackendBase(page);
    await page.route('**/chat', async (route) => {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: body.session_id || 'e2e-session-1',
          reply: 'Mobile reply OK',
          metadata: {
            resolution_source: 'LIVE_INFERENCE',
            model: 'gemini/gemini-3.8-flash',
            latency_ms: 85.4,
            input_tokens: 9,
            output_tokens: 5,
            key_id: 'key-1',
            fallback_attempts: 0,
          },
        }),
      });
    });

    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/');

    // Close sidebar if open on mobile overlay so chat area and input are unobstructed
    const closeBtn = page.getByRole('button', { name: 'Close sidebar' });
    if (await closeBtn.isVisible()) {
      await closeBtn.click();
    }

    const chatInput = page.getByTestId('chat-input');
    const sendButton = page.getByTestId('send-button');
    await expect(chatInput).toBeVisible();
    await expect(sendButton).toBeVisible();

    // Verify no horizontal overflow on mobile
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth
    );
    expect(hasOverflow).toBe(false);

    await chatInput.fill('Mobile test message');
    await sendButton.click();

    const assistantMsg = page.getByTestId('assistant-message').first();
    await expect(assistantMsg).toBeVisible({ timeout: 10000 });
    await expect(assistantMsg).toContainText('Mobile reply OK');
    await expect(assistantMsg.getByTestId('meta-source')).toContainText('Live');
  });
});
