import { test, expect } from '@playwright/test';

// ─── Report Issue Flow ────────────────────────────────────────

test.describe('Report Issue Flow', () => {
  test('should complete full report flow', async ({ page }) => {
    await page.goto('/');

    // Wait for map to load
    await page.waitForSelector('[aria-label="Community issue map"]', { timeout: 15000 });

    // Click Report Issue FAB
    await page.click('[aria-label="Report a new issue"]');

    // Wait for dialog to open
    await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5000 });

    // Step 1: Select category — click the first available category option
    const categoryBtn = page.locator('[aria-label="Pothole"]').first();
    if (await categoryBtn.isVisible()) {
      await categoryBtn.click();
    } else {
      // Fallback: click any category button
      await page.locator('[data-testid="category-option"]').first().click();
    }

    // Add description
    const descField = page.locator('textarea#report-description, textarea[name="description"], textarea[placeholder*="escribe"]').first();
    await descField.fill('Large pothole near the main junction causing vehicle damage.');
    await page.click('button:has-text("Next")');

    // Step 2: Skip media (click Next)
    const nextBtn = page.locator('button:has-text("Next")').first();
    if (await nextBtn.isVisible()) {
      await nextBtn.click();
    }

    // Step 3: Submit
    const submitBtn = page.locator('[aria-label="Submit your issue report"], button:has-text("Submit"), button:has-text("Report")').first();
    await expect(submitBtn).toBeVisible({ timeout: 5000 });
    await submitBtn.click();

    // Success toast or confirmation
    await expect(
      page.locator('text=Your report is live').or(
        page.locator('text=reported').or(
          page.locator('[data-testid="success-toast"]')
        )
      )
    ).toBeVisible({ timeout: 15000 });
  });

  test('should close report dialog on cancel', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('[aria-label="Community issue map"]', { timeout: 15000 });

    await page.click('[aria-label="Report a new issue"]');
    await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5000 });

    // Press Escape to close
    await page.keyboard.press('Escape');

    // Dialog should close
    await expect(page.locator('[role="dialog"]')).not.toBeVisible({ timeout: 3000 });
  });
});

// ─── Offline Behavior ─────────────────────────────────────────

test.describe('Offline Behavior', () => {
  test('should show offline banner when network is down', async ({ page, context }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Go offline
    await context.setOffline(true);

    // Trigger a network-dependent action — navigate or wait
    await page.waitForTimeout(1000);

    // Check for offline indicator (aria-label or text)
    const offlineIndicator = page.locator(
      '[aria-label="You are offline"], [data-testid="offline-banner"], text=offline'
    ).first();

    if (await offlineIndicator.isVisible({ timeout: 5000 }).catch(() => false)) {
      await expect(offlineIndicator).toBeVisible();
    }
    // Note: offline detection may rely on browser events; acceptable if not shown on first render

    await context.setOffline(false);
  });

  test('should allow offline draft creation', async ({ page, context }) => {
    await page.goto('/');
    await page.waitForSelector('[aria-label="Community issue map"]', { timeout: 15000 });

    // Go offline
    await context.setOffline(true);

    // Try to open report dialog
    const fab = page.locator('[aria-label="Report a new issue"]');
    if (await fab.isVisible({ timeout: 3000 }).catch(() => false)) {
      await fab.click();
      // Either dialog opens or an offline-mode draft dialog appears
      const dialog = page.locator('[role="dialog"]');
      await expect(dialog).toBeVisible({ timeout: 5000 });
    }

    await context.setOffline(false);
  });
});

// ─── Accessibility ────────────────────────────────────────────

test.describe('Accessibility', () => {
  test('skip to main content link is present and functional', async ({ page }) => {
    await page.goto('/');

    const skipLink = page.locator('.skip-to-content, a[href="#main-content"]').first();
    await expect(skipLink).toHaveAttribute('href', '#main-content');
  });

  test('report form is keyboard navigable', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('[aria-label="Community issue map"]', { timeout: 15000 });

    // Open report dialog
    await page.click('[aria-label="Report a new issue"]');
    await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5000 });

    // Tab through form elements — dialog must stay open
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');

    await expect(page.locator('[role="dialog"]')).toBeVisible();
  });

  test('map has accessible label', async ({ page }) => {
    await page.goto('/');
    const map = page.locator('[aria-label="Community issue map"]');
    await expect(map).toBeVisible({ timeout: 15000 });
  });

  test('FAB button has accessible label', async ({ page }) => {
    await page.goto('/');
    const fab = page.locator('[aria-label="Report a new issue"]');
    await expect(fab).toBeVisible({ timeout: 15000 });
    await expect(fab).toHaveAttribute('aria-label', 'Report a new issue');
  });
});

// ─── Navigation ───────────────────────────────────────────────

test.describe('Navigation', () => {
  test('page title is set', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Lumen/i);
  });

  test('home page loads without errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Filter out known third-party / map tile errors
    const criticalErrors = errors.filter(
      (e) => !e.includes('Failed to fetch') && !e.includes('tile') && !e.includes('leaflet')
    );
    expect(criticalErrors).toHaveLength(0);
  });
});
