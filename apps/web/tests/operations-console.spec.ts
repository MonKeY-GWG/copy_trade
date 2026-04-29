import { expect, test, type Page, type Route } from "@playwright/test";

const API_BASE_URL = "http://localhost:8000";
const now = "2026-04-29T12:00:00.000Z";
const userId = "11111111-1111-4111-8111-111111111111";
const credentialId = "22222222-2222-4222-8222-222222222222";

const session = {
  authenticated: true,
  user_id: userId,
  email: "admin@example.test",
  display_name: "Admin User",
  roles: ["admin"],
  expires_at: "2026-04-29T18:00:00.000Z"
};

test("logs in and renders foundation panels", async ({ page }) => {
  await mockApi(page);

  await login(page);

  await expect(page.getByRole("heading", { name: "Admin Credentials" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Subscriptions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Exchange Accounts" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Copy Relationships" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Risk Settings" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dead Letter Queue" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Audit Logs" })).toBeVisible();
});

test("sends csrf header when creating an admin credential", async ({ page }) => {
  const requests: Array<{ csrf: string | null; payload: unknown }> = [];
  await mockApi(page, {
    async handleAdminCredentialCreate(route) {
      requests.push({
        csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null,
        payload: route.request().postDataJSON()
      });
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: "33333333-3333-4333-8333-333333333333",
          user_id: "44444444-4444-4444-8444-444444444444",
          email: "second-admin@example.test",
          display_name: "Second Admin",
          credential_type: "admin_api",
          token_prefix: "newtoken",
          active: true,
          created_at: now,
          last_used_at: null,
          token: "new-admin-token-" + "x".repeat(32)
        })
      });
    }
  });

  await login(page);

  const panel = page.locator("#admin-credentials");
  await panel.getByLabel("E-Mail").fill("second-admin@example.test");
  await panel.getByLabel("Anzeigename").fill("Second Admin");
  await panel.getByLabel("Login-Passwort").fill("another correct battery staple");
  await panel.getByRole("button", { name: "Credential erzeugen" }).click();

  await expect(panel.getByText("Token fuer second-admin@example.test")).toBeVisible();
  expect(requests).toEqual([
    {
      csrf: "csrf-from-login",
      payload: {
        email: "second-admin@example.test",
        display_name: "Second Admin",
        password: "another correct battery staple"
      }
    }
  ]);
});

test("sends csrf header for admin credential rotate and deactivate", async ({ page }) => {
  const requests: Array<{ action: string; csrf: string | null }> = [];
  await mockApi(page, {
    async handleAdminCredentialRotate(route) {
      requests.push({ action: "rotate", csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null });
      await json(route, {
        id: "33333333-3333-4333-8333-333333333333",
        user_id: userId,
        email: "admin@example.test",
        display_name: "Admin User",
        credential_type: "admin_api",
        token_prefix: "rotated1",
        active: true,
        created_at: now,
        last_used_at: null,
        token: "rotated-admin-token-" + "r".repeat(32)
      });
    },
    async handleAdminCredentialDeactivate(route) {
      requests.push({ action: "deactivate", csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null });
      await json(route, {
        id: credentialId,
        user_id: userId,
        email: "admin@example.test",
        display_name: "Admin User",
        credential_type: "admin_api",
        token_prefix: "abc12345",
        active: false,
        created_at: now,
        last_used_at: null
      });
    }
  });
  page.on("dialog", (dialog) => dialog.accept());

  await login(page);

  const panel = page.locator("#admin-credentials");
  await panel.getByRole("button", { name: "Rotieren" }).click();
  await expect(panel.getByText("Rotierter Token fuer admin@example.test")).toBeVisible();
  await panel.getByRole("button", { name: "Deaktivieren" }).click();

  await expect.poll(() => requests.length).toBe(2);
  expect(requests).toEqual([
    { action: "rotate", csrf: "csrf-from-login" },
    { action: "deactivate", csrf: "csrf-from-login" }
  ]);
});

test("sends csrf header when logging out", async ({ page }) => {
  const requests: Array<{ csrf: string | null }> = [];
  await mockApi(page, {
    async handleLogout(route) {
      requests.push({ csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null });
      await json(route, { ok: true });
    }
  });

  await login(page);
  await page.getByRole("button", { name: "Out" }).click();

  await expect(page.getByRole("button", { name: "Einloggen" })).toBeVisible();
  expect(requests).toEqual([{ csrf: "csrf-from-login" }]);
});

test("sends csrf header and payload for subscription upsert", async ({ page }) => {
  const requests: Array<{ csrf: string | null; userId: string; payload: unknown }> = [];
  await mockApi(page, {
    async handleSubscriptionUpsert(route) {
      requests.push({
        csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null,
        userId: new URL(route.request().url()).pathname.split("/")[4],
        payload: route.request().postDataJSON()
      });
      await json(route, {
        user_id: userId,
        status: "past_due",
        copy_trading_enabled: false,
        current_period_end: null,
        created_at: now,
        updated_at: now
      });
    }
  });

  await login(page);

  const panel = page.locator("#subscriptions");
  await panel.getByLabel("User-ID").fill(userId);
  await panel.getByLabel("Status").selectOption("past_due");
  await panel.getByLabel("Copy Trading enabled").uncheck();
  await panel.getByRole("button", { name: "Subscription speichern" }).click();

  await expect.poll(() => requests.length).toBe(1);
  expect(requests).toEqual([
    {
      csrf: "csrf-from-login",
      userId,
      payload: {
        status: "past_due",
        copy_trading_enabled: false,
        current_period_end: null
      }
    }
  ]);
});

test("sends csrf header and payload for exchange account status patch", async ({ page }) => {
  const requests: Array<{ csrf: string | null; payload: unknown }> = [];
  await mockApi(page, {
    async handleExchangeAccountPatch(route) {
      requests.push({
        csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null,
        payload: route.request().postDataJSON()
      });
      await json(route, exchangeAccount({ status: "disabled" }));
    }
  });

  await login(page);

  const panel = page.locator("#exchange");
  await panel.getByRole("button", { name: "Deaktivieren" }).click();

  await expect.poll(() => requests.length).toBe(1);
  expect(requests).toEqual([
    {
      csrf: "csrf-from-login",
      payload: { status: "disabled" }
    }
  ]);
});

test("sends csrf header and payload for exchange account create", async ({ page }) => {
  const requests: Array<{ csrf: string | null; payload: unknown }> = [];
  await mockApi(page, {
    async handleExchangeAccountCreate(route) {
      requests.push({
        csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null,
        payload: route.request().postDataJSON()
      });
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(
          exchangeAccount({
            id: "99999999-9999-4999-8999-999999999999",
            account_id: "new-account",
            label: "New Account",
            status: "active"
          })
        )
      });
    }
  });

  await login(page);

  const panel = page.locator("#exchange");
  await panel.getByLabel("User-ID").fill(userId);
  await panel.getByLabel("Account-ID").fill("new-account");
  await panel.getByLabel("Label").fill("New Account");
  await panel.getByLabel("Status").selectOption("active");
  await panel.getByLabel("Secret Reference").fill("secret://copy-trade/test/new-account");
  await panel.getByLabel("Secret Fingerprint").fill("a".repeat(64));
  await panel.getByRole("button", { name: "Exchange-Account erzeugen" }).click();

  await expect.poll(() => requests.length).toBe(1);
  expect(requests).toEqual([
    {
      csrf: "csrf-from-login",
      payload: {
        user_id: userId,
        exchange: "hyperliquid",
        account_id: "new-account",
        label: "New Account",
        status: "active",
        secret_reference: "secret://copy-trade/test/new-account",
        secret_fingerprint: "a".repeat(64)
      }
    }
  ]);
});

test("sends csrf header and payload when clearing exchange account secret metadata", async ({ page }) => {
  const requests: Array<{ csrf: string | null; payload: unknown }> = [];
  await mockApi(page, {
    async handleExchangeAccountPatch(route) {
      requests.push({
        csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null,
        payload: route.request().postDataJSON()
      });
      await json(route, exchangeAccount({ has_secret: false, secret_fingerprint_prefix: null }));
    }
  });
  page.on("dialog", (dialog) => dialog.accept());

  await login(page);

  const panel = page.locator("#exchange");
  await panel.getByRole("button", { name: "Secret leeren" }).click();

  await expect.poll(() => requests.length).toBe(1);
  expect(requests).toEqual([
    {
      csrf: "csrf-from-login",
      payload: {
        secret_reference: null,
        secret_fingerprint: null
      }
    }
  ]);
});

test("sends csrf header for copy relationship create and deactivate", async ({ page }) => {
  const requests: Array<{ action: string; csrf: string | null; payload: Record<string, unknown> }> = [];
  await mockApi(page, {
    async handleCopyRelationshipCreate(route) {
      requests.push({
        action: "create",
        csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null,
        payload: route.request().postDataJSON()
      });
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(copyRelationship({ id: "99999999-9999-4999-8999-999999999999" }))
      });
    },
    async handleCopyRelationshipPatch(route) {
      requests.push({
        action: "patch",
        csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null,
        payload: route.request().postDataJSON()
      });
      await json(route, copyRelationship({ active: false }));
    }
  });

  await login(page);

  const panel = page.locator("#copy-relationships");
  await panel.getByLabel("Source Account").fill("source-account");
  await panel.getByLabel("Source Symbol").fill("ETH");
  await panel.getByLabel("Follower Account").fill("follower-account");
  await panel.getByLabel("Target Symbol").fill("ETH");
  await panel.getByLabel("Max Slippage bps").fill("75");
  await panel.getByRole("button", { name: "Relationship erzeugen" }).click();
  await panel.getByRole("button", { name: "Deaktivieren" }).click();

  await expect.poll(() => requests.length).toBe(2);
  expect(requests[0]).toMatchObject({
    action: "create",
    csrf: "csrf-from-login",
    payload: {
      source_exchange: "hyperliquid",
      source_account_id: "source-account",
      source_symbol: "ETH",
      follower_account_id: "follower-account",
      target_exchange: "hyperliquid",
      target_symbol: "ETH",
      max_slippage_bps: 75,
      active: true
    }
  });
  expect(typeof requests[0].payload.effective_from).toBe("string");
  expect(requests[1]).toEqual({
    action: "patch",
    csrf: "csrf-from-login",
    payload: { active: false }
  });
});

test("sends csrf header when activating an inactive copy relationship", async ({ page }) => {
  const requests: Array<{ csrf: string | null; payload: unknown }> = [];
  await mockApi(page, {
    async handleCopyRelationshipsList(route) {
      await json(route, {
        items: [copyRelationship({ active: false })],
        limit: 100,
        offset: 0
      });
    },
    async handleCopyRelationshipPatch(route) {
      requests.push({
        csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null,
        payload: route.request().postDataJSON()
      });
      await json(route, copyRelationship({ active: true }));
    }
  });

  await login(page);

  const panel = page.locator("#copy-relationships");
  await panel.getByRole("button", { name: "Aktivieren", exact: true }).click();

  await expect.poll(() => requests.length).toBe(1);
  expect(requests).toEqual([
    {
      csrf: "csrf-from-login",
      payload: { active: true }
    }
  ]);
});

test("loads relationship risk settings and saves them with csrf header", async ({ page }) => {
  const requests: Array<{ csrf: string | null; payload: unknown }> = [];
  await mockApi(page, {
    async handleRiskSettingsUpsert(route) {
      requests.push({
        csrf: route.request().headers()["x-copy-trade-csrf-token"] ?? null,
        payload: route.request().postDataJSON()
      });
      await json(route, {
        copy_relationship_id: "66666666-6666-4666-8666-666666666666",
        enabled: false,
        max_order_quantity: "2.5",
        max_slippage_bps: 80,
        max_leverage: "3",
        created_at: now,
        updated_at: now
      });
    }
  });

  await login(page);

  await page.locator("#copy-relationships").getByRole("button", { name: "Risk laden" }).click();
  const panel = page.locator("#risk");
  await expect(panel.getByText("Risk Settings geladen")).toBeVisible();
  await panel.getByLabel("Risk Gate enabled").uncheck();
  await panel.getByLabel("Max Order Quantity").fill("2.5");
  await panel.getByLabel("Max Slippage bps").fill("80");
  await panel.getByLabel("Max Leverage").fill("3");
  await panel.getByRole("button", { name: "Risk Settings speichern" }).click();

  await expect(panel.getByText("Risk Settings gespeichert")).toBeVisible();
  expect(requests).toEqual([
    {
      csrf: "csrf-from-login",
      payload: {
        enabled: false,
        max_order_quantity: "2.5",
        max_slippage_bps: 80,
        max_leverage: "3"
      }
    }
  ]);
});

test("filters dead letter events and audit logs", async ({ page }) => {
  const deadLetterStatuses: Array<string | null> = [];
  const auditQueries: Array<{ entityType: string | null; action: string | null }> = [];
  await mockApi(page, {
    async handleDeadLettersList(route) {
      const status = new URL(route.request().url()).searchParams.get("status");
      deadLetterStatuses.push(status);
      await json(route, {
        items:
          status === "ignored"
            ? [
                {
                  id: "77777777-7777-4777-8777-777777777777",
                  idempotency_key: "dlq-test-key",
                  failed_subject: "exchange.trade_event.normalized",
                  delivery_attempt: 3,
                  max_delivery_attempts: 3,
                  error_type: "RuntimeError",
                  payload: { token: "[REDACTED]" },
                  status: "ignored",
                  created_at: now,
                  updated_at: now
                }
              ]
            : [],
        limit: 100,
        offset: 0
      });
    },
    async handleAuditLogsList(route) {
      const searchParams = new URL(route.request().url()).searchParams;
      auditQueries.push({
        entityType: searchParams.get("entity_type"),
        action: searchParams.get("action")
      });
      await json(route, {
        items: searchParams.get("entity_type")
          ? [
              {
                id: "88888888-8888-4888-8888-888888888888",
                occurred_at: now,
                actor_type: "user",
                actor_id: userId,
                action: "copy_relationship.created",
                entity_type: "copy_relationship",
                entity_id: "66666666-6666-4666-8666-666666666666",
                before_state: null,
                after_state: { active: true },
                metadata: {}
              }
            ]
          : [],
        limit: 100,
        offset: 0
      });
    }
  });

  await login(page);

  const dlqPanel = page.locator("#dlq");
  await dlqPanel.getByRole("button", { name: "ignored" }).click();
  await expect(dlqPanel.getByText("exchange.trade_event.normalized")).toBeVisible();

  const auditPanel = page.locator("#audit");
  await auditPanel.getByLabel("Entity Type").fill("copy_relationship");
  await auditPanel.getByLabel("Action").fill("copy_relationship.created");
  await auditPanel.getByRole("button", { name: "Audit laden" }).click();
  await expect(auditPanel.getByText("copy_relationship.created")).toBeVisible();

  expect(deadLetterStatuses).toContain("ignored");
  expect(auditQueries).toContainEqual({
    entityType: "copy_relationship",
    action: "copy_relationship.created"
  });
});

type MockApiOptions = {
  handleAdminCredentialCreate?: (route: Route) => Promise<void>;
  handleAdminCredentialRotate?: (route: Route) => Promise<void>;
  handleAdminCredentialDeactivate?: (route: Route) => Promise<void>;
  handleLogout?: (route: Route) => Promise<void>;
  handleSubscriptionUpsert?: (route: Route) => Promise<void>;
  handleExchangeAccountCreate?: (route: Route) => Promise<void>;
  handleExchangeAccountPatch?: (route: Route) => Promise<void>;
  handleCopyRelationshipCreate?: (route: Route) => Promise<void>;
  handleCopyRelationshipsList?: (route: Route) => Promise<void>;
  handleCopyRelationshipPatch?: (route: Route) => Promise<void>;
  handleRiskSettingsUpsert?: (route: Route) => Promise<void>;
  handleDeadLettersList?: (route: Route) => Promise<void>;
  handleAuditLogsList?: (route: Route) => Promise<void>;
};

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("E-Mail").fill("admin@example.test");
  await page.getByLabel("Passwort").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Einloggen" }).click();
}

async function mockApi(page: Page, options: MockApiOptions = {}) {
  await page.route(`${API_BASE_URL}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();

    if (url.pathname === "/auth/session" && method === "GET") {
      await route.fulfill({ status: 401, contentType: "application/json", body: "{}" });
      return;
    }

    if (url.pathname === "/auth/login" && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "Set-Cookie": "copy_trade_csrf=csrf-from-login; Path=/; SameSite=Lax" },
        body: JSON.stringify({ ...session, csrf_token: "csrf-from-login" })
      });
      return;
    }

    if (url.pathname === "/auth/logout" && method === "POST") {
      if (options.handleLogout) {
        await options.handleLogout(route);
        return;
      }
      await json(route, { ok: true });
      return;
    }

    if (url.pathname === "/admin/identity/admin-credentials" && method === "POST") {
      if (options.handleAdminCredentialCreate) {
        await options.handleAdminCredentialCreate(route);
        return;
      }
      await route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
      return;
    }

    if (url.pathname.endsWith("/rotate") && url.pathname.startsWith("/admin/identity/admin-credentials/") && method === "POST") {
      if (options.handleAdminCredentialRotate) {
        await options.handleAdminCredentialRotate(route);
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "33333333-3333-4333-8333-333333333333",
          user_id: userId,
          email: "admin@example.test",
          display_name: "Admin User",
          credential_type: "admin_api",
          token_prefix: "rotated1",
          active: true,
          created_at: now,
          last_used_at: null,
          token: "rotated-admin-token-" + "r".repeat(32)
        })
      });
      return;
    }

    if (
      url.pathname.endsWith("/deactivate") &&
      url.pathname.startsWith("/admin/identity/admin-credentials/") &&
      method === "POST"
    ) {
      if (options.handleAdminCredentialDeactivate) {
        await options.handleAdminCredentialDeactivate(route);
        return;
      }
      await json(route, {
        id: credentialId,
        user_id: userId,
        email: "admin@example.test",
        display_name: "Admin User",
        credential_type: "admin_api",
        token_prefix: "abc12345",
        active: false,
        created_at: now,
        last_used_at: null
      });
      return;
    }

    if (url.pathname === "/admin/identity/admin-credentials" && method === "GET") {
      await json(route, {
        items: [
          {
            id: credentialId,
            user_id: userId,
            email: "admin@example.test",
            display_name: "Admin User",
            credential_type: "admin_api",
            token_prefix: "abc12345",
            active: true,
            created_at: now,
            last_used_at: null
          }
        ],
        limit: 100,
        offset: 0
      });
      return;
    }

    if (
      url.pathname.startsWith("/admin/identity/users/") &&
      url.pathname.endsWith("/subscription") &&
      method === "PUT"
    ) {
      if (options.handleSubscriptionUpsert) {
        await options.handleSubscriptionUpsert(route);
        return;
      }
      await json(route, {
        user_id: userId,
        status: "active",
        copy_trading_enabled: true,
        current_period_end: null,
        created_at: now,
        updated_at: now
      });
      return;
    }

    if (url.pathname === "/admin/identity/subscriptions" && method === "GET") {
      await json(route, {
        items: [
          {
            user_id: userId,
            status: "active",
            copy_trading_enabled: true,
            current_period_end: null,
            created_at: now,
            updated_at: now
          }
        ],
        limit: 100,
        offset: 0
      });
      return;
    }

    if (url.pathname === "/admin/exchange-accounts" && method === "POST") {
      if (options.handleExchangeAccountCreate) {
        await options.handleExchangeAccountCreate(route);
        return;
      }
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(exchangeAccount())
      });
      return;
    }

    if (url.pathname === "/admin/exchange-accounts" && method === "GET") {
      await json(route, {
        items: [exchangeAccount()],
        limit: 100,
        offset: 0
      });
      return;
    }

    if (url.pathname.startsWith("/admin/exchange-accounts/") && method === "PATCH") {
      if (options.handleExchangeAccountPatch) {
        await options.handleExchangeAccountPatch(route);
        return;
      }
      await json(route, exchangeAccount());
      return;
    }

    if (url.pathname === "/admin/copy-relationships" && method === "POST") {
      if (options.handleCopyRelationshipCreate) {
        await options.handleCopyRelationshipCreate(route);
        return;
      }
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(copyRelationship())
      });
      return;
    }

    if (url.pathname === "/admin/copy-relationships" && method === "GET") {
      if (options.handleCopyRelationshipsList) {
        await options.handleCopyRelationshipsList(route);
        return;
      }
      await json(route, {
        items: [copyRelationship()],
        limit: 100,
        offset: 0
      });
      return;
    }

    if (url.pathname.startsWith("/admin/copy-relationships/") && method === "PATCH") {
      if (options.handleCopyRelationshipPatch) {
        await options.handleCopyRelationshipPatch(route);
        return;
      }
      await json(route, copyRelationship());
      return;
    }

    if (
      url.pathname === "/admin/copy-relationships/66666666-6666-4666-8666-666666666666/risk-settings" &&
      method === "GET"
    ) {
      await json(route, {
        copy_relationship_id: "66666666-6666-4666-8666-666666666666",
        enabled: true,
        max_order_quantity: null,
        max_slippage_bps: 100,
        max_leverage: null,
        created_at: now,
        updated_at: now
      });
      return;
    }

    if (
      url.pathname === "/admin/copy-relationships/66666666-6666-4666-8666-666666666666/risk-settings" &&
      method === "PUT"
    ) {
      if (options.handleRiskSettingsUpsert) {
        await options.handleRiskSettingsUpsert(route);
        return;
      }
      await json(route, {
        copy_relationship_id: "66666666-6666-4666-8666-666666666666",
        enabled: true,
        max_order_quantity: null,
        max_slippage_bps: 100,
        max_leverage: null,
        created_at: now,
        updated_at: now
      });
      return;
    }

    if (url.pathname === "/admin/operations/dead-letter-events" && method === "GET") {
      if (options.handleDeadLettersList) {
        await options.handleDeadLettersList(route);
        return;
      }
      await json(route, {
        items: [],
        limit: 100,
        offset: 0
      });
      return;
    }

    if (url.pathname === "/admin/audit-logs" && method === "GET") {
      if (options.handleAuditLogsList) {
        await options.handleAuditLogsList(route);
        return;
      }
      await json(route, {
        items: [],
        limit: 100,
        offset: 0
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unhandled mock route: ${method} ${url.pathname}` })
    });
  });
}

async function json(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body)
  });
}

function exchangeAccount(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "55555555-5555-4555-8555-555555555555",
    user_id: userId,
    exchange: "hyperliquid",
    account_id: "source-account",
    label: "Source",
    status: "active",
    has_secret: true,
    secret_fingerprint_prefix: "aaaaaaaa",
    created_at: now,
    updated_at: now,
    ...overrides
  };
}

function copyRelationship(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "66666666-6666-4666-8666-666666666666",
    source_exchange: "hyperliquid",
    source_account_id: "source-account",
    source_symbol: "BTC",
    follower_account_id: "follower-account",
    target_exchange: "hyperliquid",
    target_symbol: "BTC",
    max_slippage_bps: 100,
    active: true,
    effective_from: now,
    created_at: now,
    updated_at: now,
    ...overrides
  };
}
