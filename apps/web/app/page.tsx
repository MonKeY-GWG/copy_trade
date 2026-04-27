"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type SessionState = {
  authenticated: boolean;
  user_id: string;
  email: string;
  display_name: string | null;
  roles: string[];
  expires_at: string;
};

type AdminCredential = {
  id: string;
  user_id: string;
  email: string;
  display_name: string | null;
  credential_type: string;
  token_prefix: string | null;
  active: boolean;
  created_at: string;
  last_used_at: string | null;
};

type AdminCredentialListResponse = {
  items: AdminCredential[];
  limit: number;
  offset: number;
};

type CreatedAdminCredential = AdminCredential & {
  token: string;
};

const SUBSCRIPTION_STATUSES = ["trialing", "active", "past_due", "canceled", "disabled"] as const;
const EXCHANGES = ["hyperliquid", "aster", "blofin"] as const;
const EXCHANGE_ACCOUNT_STATUSES = ["pending", "active", "disabled", "revoked", "error"] as const;
const DEAD_LETTER_STATUSES = ["open", "acknowledged", "reprocessed", "ignored"] as const;

type SubscriptionStatus = (typeof SUBSCRIPTION_STATUSES)[number];
type Exchange = (typeof EXCHANGES)[number];
type ExchangeAccountStatus = (typeof EXCHANGE_ACCOUNT_STATUSES)[number];
type DeadLetterStatus = (typeof DEAD_LETTER_STATUSES)[number];

type Subscription = {
  user_id: string;
  status: SubscriptionStatus;
  copy_trading_enabled: boolean;
  current_period_end: string | null;
  created_at: string;
  updated_at: string;
};

type SubscriptionListResponse = {
  items: Subscription[];
  limit: number;
  offset: number;
};

type ExchangeAccount = {
  id: string;
  user_id: string;
  exchange: Exchange;
  account_id: string;
  label: string | null;
  status: ExchangeAccountStatus;
  has_secret: boolean;
  secret_fingerprint_prefix: string | null;
  created_at: string;
  updated_at: string;
};

type ExchangeAccountListResponse = {
  items: ExchangeAccount[];
  limit: number;
  offset: number;
};

type CopyRelationship = {
  id: string;
  source_exchange: Exchange;
  source_account_id: string;
  source_symbol: string | null;
  follower_account_id: string;
  target_exchange: Exchange;
  target_symbol: string;
  max_slippage_bps: number;
  active: boolean;
  effective_from: string;
  created_at: string;
  updated_at: string;
};

type CopyRelationshipListResponse = {
  items: CopyRelationship[];
  limit: number;
  offset: number;
};

type RiskSettings = {
  copy_relationship_id: string;
  enabled: boolean;
  max_order_quantity: string | null;
  max_slippage_bps: number;
  max_leverage: string | null;
  created_at: string;
  updated_at: string;
};

type DeadLetterEvent = {
  id: string;
  idempotency_key: string;
  failed_subject: string;
  delivery_attempt: number;
  max_delivery_attempts: number;
  error_type: string;
  payload: Record<string, unknown> | null;
  status: DeadLetterStatus;
  created_at: string;
  updated_at: string;
};

type DeadLetterEventListResponse = {
  items: DeadLetterEvent[];
  limit: number;
  offset: number;
};

type AuditLog = {
  id: string;
  occurred_at: string;
  actor_type: string;
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
};

type AuditLogListResponse = {
  items: AuditLog[];
  limit: number;
  offset: number;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_COPY_TRADE_API_URL ?? "http://localhost:8000";
const CSRF_COOKIE_NAME = "copy_trade_csrf";

export default function ConsolePage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [csrfToken, setCsrfToken] = useState("");
  const [session, setSession] = useState<SessionState | null>(null);
  const [status, setStatus] = useState("Bereit");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [credentials, setCredentials] = useState<AdminCredential[]>([]);
  const [credentialFilter, setCredentialFilter] = useState<"active" | "all">("active");
  const [credentialsLoading, setCredentialsLoading] = useState(false);
  const [credentialsError, setCredentialsError] = useState("");
  const [credentialStatus, setCredentialStatus] = useState("");
  const [credentialActionId, setCredentialActionId] = useState<string | null>(null);
  const [createEmail, setCreateEmail] = useState("");
  const [createDisplayName, setCreateDisplayName] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createdToken, setCreatedToken] = useState<{ label: string; value: string } | null>(null);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [subscriptionFilter, setSubscriptionFilter] = useState<SubscriptionStatus | "all">("all");
  const [subscriptionsLoading, setSubscriptionsLoading] = useState(false);
  const [subscriptionsError, setSubscriptionsError] = useState("");
  const [subscriptionStatus, setSubscriptionStatus] = useState("");
  const [subscriptionActionUserId, setSubscriptionActionUserId] = useState<string | null>(null);
  const [subscriptionUserId, setSubscriptionUserId] = useState("");
  const [subscriptionState, setSubscriptionState] = useState<SubscriptionStatus>("active");
  const [copyTradingEnabled, setCopyTradingEnabled] = useState(true);
  const [currentPeriodEnd, setCurrentPeriodEnd] = useState("");
  const [exchangeAccounts, setExchangeAccounts] = useState<ExchangeAccount[]>([]);
  const [exchangeAccountFilter, setExchangeAccountFilter] = useState<ExchangeAccountStatus | "all">("all");
  const [exchangeAccountsLoading, setExchangeAccountsLoading] = useState(false);
  const [exchangeAccountsError, setExchangeAccountsError] = useState("");
  const [exchangeAccountStatus, setExchangeAccountStatus] = useState("");
  const [exchangeAccountActionId, setExchangeAccountActionId] = useState<string | null>(null);
  const [exchangeAccountUserId, setExchangeAccountUserId] = useState("");
  const [exchange, setExchange] = useState<Exchange>("hyperliquid");
  const [exchangeAccountId, setExchangeAccountId] = useState("");
  const [exchangeAccountLabel, setExchangeAccountLabel] = useState("");
  const [exchangeAccountState, setExchangeAccountState] = useState<ExchangeAccountStatus>("pending");
  const [secretReference, setSecretReference] = useState("");
  const [secretFingerprint, setSecretFingerprint] = useState("");
  const [copyRelationships, setCopyRelationships] = useState<CopyRelationship[]>([]);
  const [relationshipFilter, setRelationshipFilter] = useState<"active" | "all">("active");
  const [relationshipsLoading, setRelationshipsLoading] = useState(false);
  const [relationshipsError, setRelationshipsError] = useState("");
  const [relationshipStatus, setRelationshipStatus] = useState("");
  const [relationshipActionId, setRelationshipActionId] = useState<string | null>(null);
  const [relationshipSourceExchange, setRelationshipSourceExchange] = useState<Exchange>("hyperliquid");
  const [relationshipSourceAccountId, setRelationshipSourceAccountId] = useState("");
  const [relationshipSourceSymbol, setRelationshipSourceSymbol] = useState("");
  const [relationshipFollowerAccountId, setRelationshipFollowerAccountId] = useState("");
  const [relationshipTargetExchange, setRelationshipTargetExchange] = useState<Exchange>("hyperliquid");
  const [relationshipTargetSymbol, setRelationshipTargetSymbol] = useState("");
  const [relationshipMaxSlippageBps, setRelationshipMaxSlippageBps] = useState("100");
  const [relationshipActive, setRelationshipActive] = useState(true);
  const [relationshipEffectiveFrom, setRelationshipEffectiveFrom] = useState(() => toDateTimeLocal(new Date().toISOString()));
  const [riskSettings, setRiskSettings] = useState<RiskSettings | null>(null);
  const [riskRelationshipId, setRiskRelationshipId] = useState("");
  const [riskEnabled, setRiskEnabled] = useState(true);
  const [riskMaxOrderQuantity, setRiskMaxOrderQuantity] = useState("");
  const [riskMaxSlippageBps, setRiskMaxSlippageBps] = useState("100");
  const [riskMaxLeverage, setRiskMaxLeverage] = useState("");
  const [riskLoading, setRiskLoading] = useState(false);
  const [riskError, setRiskError] = useState("");
  const [riskStatus, setRiskStatus] = useState("");
  const [deadLetterEvents, setDeadLetterEvents] = useState<DeadLetterEvent[]>([]);
  const [deadLetterFilter, setDeadLetterFilter] = useState<DeadLetterStatus | "all">("open");
  const [deadLettersLoading, setDeadLettersLoading] = useState(false);
  const [deadLettersError, setDeadLettersError] = useState("");
  const [deadLettersStatus, setDeadLettersStatus] = useState("");
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState("");
  const [auditStatus, setAuditStatus] = useState("");
  const [auditEntityType, setAuditEntityType] = useState("");
  const [auditEntityId, setAuditEntityId] = useState("");
  const [auditAction, setAuditAction] = useState("");

  const roleText = useMemo(() => session?.roles.join(", ") ?? "keine Session", [session]);
  const activeCredentialCount = useMemo(
    () => credentials.filter((credential) => credential.active).length,
    [credentials]
  );
  const credentialUsers = useMemo(() => {
    const users = new Map<string, { user_id: string; label: string; email: string }>();
    for (const credential of credentials) {
      if (users.has(credential.user_id)) {
        continue;
      }
      users.set(credential.user_id, {
        user_id: credential.user_id,
        label: credential.display_name ?? credential.email,
        email: credential.email
      });
    }
    return [...users.values()];
  }, [credentials]);
  const enabledSubscriptionCount = useMemo(
    () =>
      subscriptions.filter(
        (subscription) =>
          subscription.copy_trading_enabled &&
          (subscription.status === "active" || subscription.status === "trialing")
      ).length,
    [subscriptions]
  );
  const activeExchangeAccountCount = useMemo(
    () => exchangeAccounts.filter((account) => account.status === "active").length,
    [exchangeAccounts]
  );
  const exchangeAccountIds = useMemo(
    () => [...new Set(exchangeAccounts.map((account) => account.account_id))],
    [exchangeAccounts]
  );
  const activeRelationshipCount = useMemo(
    () => copyRelationships.filter((relationship) => relationship.active).length,
    [copyRelationships]
  );
  const openDeadLetterCount = useMemo(
    () => deadLetterEvents.filter((event) => event.status === "open").length,
    [deadLetterEvents]
  );

  useEffect(() => {
    void refreshSession();
  }, []);

  async function refreshSession() {
    try {
      const response = await fetch(`${API_BASE_URL}/auth/session`, {
        credentials: "include"
      });
      if (!response.ok) {
        setSession(null);
        setCredentials([]);
        return;
      }
      const body = (await response.json()) as SessionState;
      setSession(body);
      setStatus("Session aktiv");
      setCsrfToken(readCookie(CSRF_COOKIE_NAME));
      await Promise.all([
        loadAdminCredentials(credentialFilter),
        loadSubscriptions(subscriptionFilter),
        loadExchangeAccounts(exchangeAccountFilter),
        loadCopyRelationships(relationshipFilter),
        loadDeadLetterEvents(deadLetterFilter),
        loadAuditLogs()
      ]);
    } catch {
      setSession(null);
      setCredentials([]);
      setSubscriptions([]);
      setExchangeAccounts([]);
      setCopyRelationships([]);
      setDeadLetterEvents([]);
      setAuditLogs([]);
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setStatus("Login wird geprueft");
    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      });
      if (!response.ok) {
        throw new Error("Login fehlgeschlagen");
      }
      const body = (await response.json()) as SessionState & { csrf_token: string };
      setCsrfToken(body.csrf_token);
      setSession(body);
      setPassword("");
      setStatus("Session aktiv");
      await Promise.all([
        loadAdminCredentials(credentialFilter),
        loadSubscriptions(subscriptionFilter),
        loadExchangeAccounts(exchangeAccountFilter),
        loadCopyRelationships(relationshipFilter),
        loadDeadLetterEvents(deadLetterFilter),
        loadAuditLogs()
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Login fehlgeschlagen");
      setStatus("Nicht angemeldet");
    } finally {
      setLoading(false);
    }
  }

  async function handleLogout() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE_URL}/auth/logout`, {
        method: "POST",
        credentials: "include",
        headers: csrfToken ? { "X-Copy-Trade-CSRF-Token": csrfToken } : {}
      });
      if (!response.ok) {
        throw new Error("Logout fehlgeschlagen");
      }
      setSession(null);
      setCsrfToken("");
      setCredentials([]);
      setSubscriptions([]);
      setExchangeAccounts([]);
      setCopyRelationships([]);
      setRiskSettings(null);
      setDeadLetterEvents([]);
      setAuditLogs([]);
      setCreatedToken(null);
      setStatus("Abgemeldet");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Logout fehlgeschlagen");
    } finally {
      setLoading(false);
    }
  }

  async function loadSubscriptions(filter: SubscriptionStatus | "all" = subscriptionFilter) {
    setSubscriptionsLoading(true);
    setSubscriptionsError("");
    try {
      const query = new URLSearchParams({ limit: "100", offset: "0" });
      if (filter !== "all") {
        query.set("status", filter);
      }
      const response = await fetch(`${API_BASE_URL}/admin/identity/subscriptions?${query}`, {
        credentials: "include"
      });
      if (!response.ok) {
        if (response.status === 401) {
          setSession(null);
          setStatus("Nicht angemeldet");
        }
        throw new Error(await apiError(response));
      }
      const body = (await response.json()) as SubscriptionListResponse;
      setSubscriptions(body.items);
      setSubscriptionStatus(`${body.items.length} Subscriptions geladen`);
    } catch (caught) {
      setSubscriptionsError(
        caught instanceof Error ? caught.message : "Subscriptions konnten nicht geladen werden"
      );
    } finally {
      setSubscriptionsLoading(false);
    }
  }

  async function handleSubscriptionFilterChange(nextFilter: SubscriptionStatus | "all") {
    setSubscriptionFilter(nextFilter);
    await loadSubscriptions(nextFilter);
  }

  async function handleUpsertSubscription(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubscriptionsError("");
    setSubscriptionStatus("Subscription wird gespeichert");
    setSubscriptionActionUserId(subscriptionUserId);
    try {
      const payload: {
        status: SubscriptionStatus;
        copy_trading_enabled: boolean;
        current_period_end?: string | null;
      } = {
        status: subscriptionState,
        copy_trading_enabled: copyTradingEnabled,
        current_period_end: currentPeriodEnd ? new Date(currentPeriodEnd).toISOString() : null
      };
      const response = await fetch(
        `${API_BASE_URL}/admin/identity/users/${subscriptionUserId}/subscription`,
        {
          method: "PUT",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            ...csrfHeaders()
          },
          body: JSON.stringify(payload)
        }
      );
      if (!response.ok) {
        throw new Error(await apiError(response));
      }
      setSubscriptionStatus("Subscription gespeichert");
      await loadSubscriptions(subscriptionFilter);
    } catch (caught) {
      setSubscriptionsError(caught instanceof Error ? caught.message : "Subscription konnte nicht gespeichert werden");
      setSubscriptionStatus("");
    } finally {
      setSubscriptionActionUserId(null);
    }
  }

  function editSubscription(subscription: Subscription) {
    setSubscriptionUserId(subscription.user_id);
    setSubscriptionState(subscription.status);
    setCopyTradingEnabled(subscription.copy_trading_enabled);
    setCurrentPeriodEnd(toDateTimeLocal(subscription.current_period_end));
    setSubscriptionStatus("Subscription zum Bearbeiten geladen");
  }

  async function loadExchangeAccounts(filter: ExchangeAccountStatus | "all" = exchangeAccountFilter) {
    setExchangeAccountsLoading(true);
    setExchangeAccountsError("");
    try {
      const query = new URLSearchParams({ limit: "100", offset: "0" });
      if (filter !== "all") {
        query.set("status", filter);
      }
      const response = await fetch(`${API_BASE_URL}/admin/exchange-accounts?${query}`, {
        credentials: "include"
      });
      if (!response.ok) {
        if (response.status === 401) {
          setSession(null);
          setStatus("Nicht angemeldet");
        }
        throw new Error(await apiError(response));
      }
      const body = (await response.json()) as ExchangeAccountListResponse;
      setExchangeAccounts(body.items);
      setExchangeAccountStatus(`${body.items.length} Exchange-Accounts geladen`);
    } catch (caught) {
      setExchangeAccountsError(
        caught instanceof Error ? caught.message : "Exchange-Accounts konnten nicht geladen werden"
      );
    } finally {
      setExchangeAccountsLoading(false);
    }
  }

  async function handleExchangeAccountFilterChange(nextFilter: ExchangeAccountStatus | "all") {
    setExchangeAccountFilter(nextFilter);
    await loadExchangeAccounts(nextFilter);
  }

  async function handleCreateExchangeAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setExchangeAccountsError("");
    setExchangeAccountStatus("Exchange-Account wird erzeugt");
    setExchangeAccountActionId("create");
    try {
      const payload: {
        user_id: string;
        exchange: Exchange;
        account_id: string;
        label?: string;
        status: ExchangeAccountStatus;
        secret_reference?: string;
        secret_fingerprint?: string;
      } = {
        user_id: exchangeAccountUserId,
        exchange,
        account_id: exchangeAccountId,
        status: exchangeAccountState
      };
      if (exchangeAccountLabel.trim()) {
        payload.label = exchangeAccountLabel.trim();
      }
      if (secretReference.trim()) {
        payload.secret_reference = secretReference.trim();
      }
      if (secretFingerprint.trim()) {
        payload.secret_fingerprint = secretFingerprint.trim();
      }
      const response = await fetch(`${API_BASE_URL}/admin/exchange-accounts`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...csrfHeaders()
        },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        throw new Error(await apiError(response));
      }
      setExchangeAccountId("");
      setExchangeAccountLabel("");
      setSecretReference("");
      setSecretFingerprint("");
      setExchangeAccountStatus("Exchange-Account erzeugt");
      await loadExchangeAccounts(exchangeAccountFilter);
    } catch (caught) {
      setExchangeAccountsError(
        caught instanceof Error ? caught.message : "Exchange-Account konnte nicht erzeugt werden"
      );
      setExchangeAccountStatus("");
    } finally {
      setExchangeAccountActionId(null);
    }
  }

  async function updateExchangeAccountStatus(account: ExchangeAccount, nextStatus: ExchangeAccountStatus) {
    setExchangeAccountsError("");
    setExchangeAccountStatus("Exchange-Account wird aktualisiert");
    setExchangeAccountActionId(account.id);
    try {
      const response = await fetch(`${API_BASE_URL}/admin/exchange-accounts/${account.id}`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...csrfHeaders()
        },
        body: JSON.stringify({ status: nextStatus })
      });
      if (!response.ok) {
        throw new Error(await apiError(response));
      }
      setExchangeAccountStatus(`Exchange-Account auf ${nextStatus} gesetzt`);
      await loadExchangeAccounts(exchangeAccountFilter);
    } catch (caught) {
      setExchangeAccountsError(
        caught instanceof Error ? caught.message : "Exchange-Account konnte nicht aktualisiert werden"
      );
      setExchangeAccountStatus("");
    } finally {
      setExchangeAccountActionId(null);
    }
  }

  async function clearExchangeAccountSecret(account: ExchangeAccount) {
    if (!window.confirm(`Secret-Metadaten fuer ${account.account_id} entfernen?`)) {
      return;
    }
    setExchangeAccountsError("");
    setExchangeAccountStatus("Secret-Metadaten werden entfernt");
    setExchangeAccountActionId(account.id);
    try {
      const response = await fetch(`${API_BASE_URL}/admin/exchange-accounts/${account.id}`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...csrfHeaders()
        },
        body: JSON.stringify({ secret_reference: null, secret_fingerprint: null })
      });
      if (!response.ok) {
        throw new Error(await apiError(response));
      }
      setExchangeAccountStatus("Secret-Metadaten entfernt");
      await loadExchangeAccounts(exchangeAccountFilter);
    } catch (caught) {
      setExchangeAccountsError(
        caught instanceof Error ? caught.message : "Secret-Metadaten konnten nicht entfernt werden"
      );
      setExchangeAccountStatus("");
    } finally {
      setExchangeAccountActionId(null);
    }
  }

  async function loadCopyRelationships(filter: "active" | "all" = relationshipFilter) {
    setRelationshipsLoading(true);
    setRelationshipsError("");
    try {
      const query = new URLSearchParams({ limit: "100", offset: "0" });
      if (filter === "active") {
        query.set("active", "true");
      }
      const response = await fetch(`${API_BASE_URL}/admin/copy-relationships?${query}`, {
        credentials: "include"
      });
      if (!response.ok) {
        if (response.status === 401) {
          setSession(null);
          setStatus("Nicht angemeldet");
        }
        throw new Error(await apiError(response));
      }
      const body = (await response.json()) as CopyRelationshipListResponse;
      setCopyRelationships(body.items);
      setRelationshipStatus(`${body.items.length} Copy-Relationships geladen`);
    } catch (caught) {
      setRelationshipsError(
        caught instanceof Error ? caught.message : "Copy-Relationships konnten nicht geladen werden"
      );
    } finally {
      setRelationshipsLoading(false);
    }
  }

  async function handleRelationshipFilterChange(nextFilter: "active" | "all") {
    setRelationshipFilter(nextFilter);
    await loadCopyRelationships(nextFilter);
  }

  async function handleCreateCopyRelationship(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRelationshipsError("");
    setRelationshipStatus("Copy-Relationship wird erzeugt");
    setRelationshipActionId("create");
    try {
      const payload: {
        source_exchange: Exchange;
        source_account_id: string;
        source_symbol?: string;
        follower_account_id: string;
        target_exchange: Exchange;
        target_symbol: string;
        max_slippage_bps: number;
        active: boolean;
        effective_from: string;
      } = {
        source_exchange: relationshipSourceExchange,
        source_account_id: relationshipSourceAccountId,
        follower_account_id: relationshipFollowerAccountId,
        target_exchange: relationshipTargetExchange,
        target_symbol: relationshipTargetSymbol,
        max_slippage_bps: Number(relationshipMaxSlippageBps),
        active: relationshipActive,
        effective_from: new Date(relationshipEffectiveFrom).toISOString()
      };
      if (relationshipSourceSymbol.trim()) {
        payload.source_symbol = relationshipSourceSymbol.trim();
      }
      const response = await fetch(`${API_BASE_URL}/admin/copy-relationships`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...csrfHeaders()
        },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        throw new Error(await apiError(response));
      }
      const created = (await response.json()) as CopyRelationship;
      setRiskRelationshipId(created.id);
      setRelationshipSourceSymbol("");
      setRelationshipFollowerAccountId("");
      setRelationshipTargetSymbol("");
      setRelationshipStatus("Copy-Relationship erzeugt");
      await loadCopyRelationships(relationshipFilter);
    } catch (caught) {
      setRelationshipsError(
        caught instanceof Error ? caught.message : "Copy-Relationship konnte nicht erzeugt werden"
      );
      setRelationshipStatus("");
    } finally {
      setRelationshipActionId(null);
    }
  }

  async function updateCopyRelationshipActive(relationship: CopyRelationship, active: boolean) {
    setRelationshipsError("");
    setRelationshipStatus("Copy-Relationship wird aktualisiert");
    setRelationshipActionId(relationship.id);
    try {
      const response = await fetch(`${API_BASE_URL}/admin/copy-relationships/${relationship.id}`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...csrfHeaders()
        },
        body: JSON.stringify({ active })
      });
      if (!response.ok) {
        throw new Error(await apiError(response));
      }
      setRelationshipStatus(active ? "Copy-Relationship aktiviert" : "Copy-Relationship deaktiviert");
      await loadCopyRelationships(relationshipFilter);
    } catch (caught) {
      setRelationshipsError(
        caught instanceof Error ? caught.message : "Copy-Relationship konnte nicht aktualisiert werden"
      );
      setRelationshipStatus("");
    } finally {
      setRelationshipActionId(null);
    }
  }

  async function loadRiskSettingsForRelationship(relationshipId: string) {
    if (!relationshipId) {
      return;
    }
    setRiskLoading(true);
    setRiskError("");
    setRiskStatus("Risk Settings werden geladen");
    try {
      const response = await fetch(`${API_BASE_URL}/admin/copy-relationships/${relationshipId}/risk-settings`, {
        credentials: "include"
      });
      if (response.status === 404) {
        setRiskSettings(null);
        setRiskRelationshipId(relationshipId);
        setRiskEnabled(true);
        setRiskMaxOrderQuantity("");
        setRiskMaxSlippageBps("100");
        setRiskMaxLeverage("");
        setRiskStatus("Noch keine Risk Settings fuer diese Relationship");
        return;
      }
      if (!response.ok) {
        throw new Error(await apiError(response));
      }
      const body = (await response.json()) as RiskSettings;
      applyRiskSettings(body);
      setRiskStatus("Risk Settings geladen");
    } catch (caught) {
      setRiskError(caught instanceof Error ? caught.message : "Risk Settings konnten nicht geladen werden");
      setRiskStatus("");
    } finally {
      setRiskLoading(false);
    }
  }

  async function handleUpsertRiskSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRiskLoading(true);
    setRiskError("");
    setRiskStatus("Risk Settings werden gespeichert");
    try {
      const payload: {
        enabled: boolean;
        max_order_quantity?: string;
        max_slippage_bps: number;
        max_leverage?: string;
      } = {
        enabled: riskEnabled,
        max_slippage_bps: Number(riskMaxSlippageBps)
      };
      if (riskMaxOrderQuantity) {
        payload.max_order_quantity = riskMaxOrderQuantity;
      }
      if (riskMaxLeverage) {
        payload.max_leverage = riskMaxLeverage;
      }
      const response = await fetch(`${API_BASE_URL}/admin/copy-relationships/${riskRelationshipId}/risk-settings`, {
        method: "PUT",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...csrfHeaders()
        },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        throw new Error(await apiError(response));
      }
      const body = (await response.json()) as RiskSettings;
      applyRiskSettings(body);
      setRiskStatus("Risk Settings gespeichert");
    } catch (caught) {
      setRiskError(caught instanceof Error ? caught.message : "Risk Settings konnten nicht gespeichert werden");
      setRiskStatus("");
    } finally {
      setRiskLoading(false);
    }
  }

  function applyRiskSettings(settings: RiskSettings) {
    setRiskSettings(settings);
    setRiskRelationshipId(settings.copy_relationship_id);
    setRiskEnabled(settings.enabled);
    setRiskMaxOrderQuantity(settings.max_order_quantity ?? "");
    setRiskMaxSlippageBps(String(settings.max_slippage_bps));
    setRiskMaxLeverage(settings.max_leverage ?? "");
  }

  async function loadDeadLetterEvents(filter: DeadLetterStatus | "all" = deadLetterFilter) {
    setDeadLettersLoading(true);
    setDeadLettersError("");
    try {
      const query = new URLSearchParams({ limit: "100", offset: "0" });
      if (filter !== "all") {
        query.set("status", filter);
      }
      const response = await fetch(`${API_BASE_URL}/admin/operations/dead-letter-events?${query}`, {
        credentials: "include"
      });
      if (!response.ok) {
        if (response.status === 401) {
          setSession(null);
          setStatus("Nicht angemeldet");
        }
        throw new Error(await apiError(response));
      }
      const body = (await response.json()) as DeadLetterEventListResponse;
      setDeadLetterEvents(body.items);
      setDeadLettersStatus(`${body.items.length} DLQ-Events geladen`);
    } catch (caught) {
      setDeadLettersError(caught instanceof Error ? caught.message : "DLQ-Events konnten nicht geladen werden");
    } finally {
      setDeadLettersLoading(false);
    }
  }

  async function handleDeadLetterFilterChange(nextFilter: DeadLetterStatus | "all") {
    setDeadLetterFilter(nextFilter);
    await loadDeadLetterEvents(nextFilter);
  }

  async function loadAuditLogs() {
    setAuditLoading(true);
    setAuditError("");
    try {
      const query = new URLSearchParams({ limit: "100", offset: "0" });
      if (auditEntityType.trim()) {
        query.set("entity_type", auditEntityType.trim());
      }
      if (auditEntityId.trim()) {
        query.set("entity_id", auditEntityId.trim());
      }
      if (auditAction.trim()) {
        query.set("action", auditAction.trim());
      }
      const response = await fetch(`${API_BASE_URL}/admin/audit-logs?${query}`, {
        credentials: "include"
      });
      if (!response.ok) {
        if (response.status === 401) {
          setSession(null);
          setStatus("Nicht angemeldet");
        }
        throw new Error(await apiError(response));
      }
      const body = (await response.json()) as AuditLogListResponse;
      setAuditLogs(body.items);
      setAuditStatus(`${body.items.length} Audit-Logs geladen`);
    } catch (caught) {
      setAuditError(caught instanceof Error ? caught.message : "Audit-Logs konnten nicht geladen werden");
    } finally {
      setAuditLoading(false);
    }
  }

  function applyAuditEntity(entityType: string, entityId: string | null) {
    setAuditEntityType(entityType);
    setAuditEntityId(entityId ?? "");
    setAuditAction("");
    setAuditStatus("Audit-Filter uebernommen");
  }

  async function loadAdminCredentials(filter: "active" | "all" = credentialFilter) {
    setCredentialsLoading(true);
    setCredentialsError("");
    try {
      const query = new URLSearchParams({ limit: "100", offset: "0" });
      if (filter === "active") {
        query.set("active", "true");
      }
      const response = await fetch(`${API_BASE_URL}/admin/identity/admin-credentials?${query}`, {
        credentials: "include"
      });
      if (!response.ok) {
        if (response.status === 401) {
          setSession(null);
          setStatus("Nicht angemeldet");
        }
        throw new Error(await apiError(response));
      }
      const body = (await response.json()) as AdminCredentialListResponse;
      setCredentials(body.items);
      setCredentialStatus(`${body.items.length} Credentials geladen`);
    } catch (caught) {
      setCredentialsError(
        caught instanceof Error ? caught.message : "Admin-Credentials konnten nicht geladen werden"
      );
    } finally {
      setCredentialsLoading(false);
    }
  }

  async function handleFilterChange(nextFilter: "active" | "all") {
    setCredentialFilter(nextFilter);
    await loadAdminCredentials(nextFilter);
  }

  async function handleCreateCredential(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCredentialsError("");
    setCredentialStatus("Credential wird erzeugt");
    setCredentialActionId("create");
    try {
      const payload: {
        email: string;
        display_name?: string;
        password?: string;
      } = { email: createEmail };
      if (createDisplayName.trim()) {
        payload.display_name = createDisplayName.trim();
      }
      if (createPassword) {
        payload.password = createPassword;
      }

      const response = await fetch(`${API_BASE_URL}/admin/identity/admin-credentials`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...csrfHeaders()
        },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        throw new Error(await apiError(response));
      }
      const body = (await response.json()) as CreatedAdminCredential;
      setCreatedToken({ label: `Token fuer ${body.email}`, value: body.token });
      setCreateEmail("");
      setCreateDisplayName("");
      setCreatePassword("");
      setCredentialStatus("Credential erzeugt");
      await loadAdminCredentials(credentialFilter);
    } catch (caught) {
      setCredentialsError(caught instanceof Error ? caught.message : "Credential konnte nicht erzeugt werden");
      setCredentialStatus("");
    } finally {
      setCredentialActionId(null);
    }
  }

  async function handleDeactivateCredential(credential: AdminCredential) {
    if (!window.confirm(`Admin-Credential fuer ${credential.email} deaktivieren?`)) {
      return;
    }
    setCredentialsError("");
    setCredentialStatus("Credential wird deaktiviert");
    setCredentialActionId(credential.id);
    try {
      const response = await fetch(
        `${API_BASE_URL}/admin/identity/admin-credentials/${credential.id}/deactivate`,
        {
          method: "POST",
          credentials: "include",
          headers: csrfHeaders()
        }
      );
      if (!response.ok) {
        throw new Error(await apiError(response));
      }
      setCredentialStatus("Credential deaktiviert");
      await loadAdminCredentials(credentialFilter);
    } catch (caught) {
      setCredentialsError(caught instanceof Error ? caught.message : "Credential konnte nicht deaktiviert werden");
      setCredentialStatus("");
    } finally {
      setCredentialActionId(null);
    }
  }

  async function handleRotateCredential(credential: AdminCredential) {
    if (!window.confirm(`Admin-Credential fuer ${credential.email} rotieren?`)) {
      return;
    }
    setCredentialsError("");
    setCreatedToken(null);
    setCredentialStatus("Credential wird rotiert");
    setCredentialActionId(credential.id);
    try {
      const response = await fetch(
        `${API_BASE_URL}/admin/identity/admin-credentials/${credential.id}/rotate`,
        {
          method: "POST",
          credentials: "include",
          headers: csrfHeaders()
        }
      );
      if (!response.ok) {
        throw new Error(await apiError(response));
      }
      const body = (await response.json()) as CreatedAdminCredential;
      setCreatedToken({ label: `Rotierter Token fuer ${body.email}`, value: body.token });
      setCredentialStatus("Credential rotiert");
      await loadAdminCredentials(credentialFilter);
    } catch (caught) {
      setCredentialsError(caught instanceof Error ? caught.message : "Credential konnte nicht rotiert werden");
      setCredentialStatus("");
    } finally {
      setCredentialActionId(null);
    }
  }

  async function handleCopyToken() {
    if (!createdToken) {
      return;
    }
    try {
      await navigator.clipboard.writeText(createdToken.value);
      setCredentialStatus("Token in Zwischenablage kopiert");
    } catch {
      setCredentialStatus("Token konnte nicht automatisch kopiert werden");
    }
  }

  function csrfHeaders(): Record<string, string> {
    const token = csrfToken || readCookie(CSRF_COOKIE_NAME);
    return token ? { "X-Copy-Trade-CSRF-Token": token } : {};
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Copy Trade</p>
          <h1>Operations Console</h1>
        </div>
        <div className="session-strip">
          <span className={session ? "status is-live" : "status"}>{status}</span>
          {session ? (
            <button className="icon-button" onClick={handleLogout} disabled={loading} title="Logout">
              Out
            </button>
          ) : null}
        </div>
      </header>

      <section className="workspace">
        <aside className="side-panel">
          <nav aria-label="Foundation Controls">
            <a className="nav-item is-active" href="#session">
              Session
            </a>
            <a className="nav-item" href="#admin-credentials">
              Admin Credentials
            </a>
            <a className="nav-item" href="#subscriptions">
              Subscriptions
            </a>
            <a className="nav-item" href="#exchange">
              Exchange Accounts
            </a>
            <a className="nav-item" href="#copy-relationships">
              Relationships
            </a>
            <a className="nav-item" href="#risk">
              Risk Settings
            </a>
            <a className="nav-item" href="#dlq">
              DLQ
            </a>
            <a className="nav-item" href="#audit">
              Audit
            </a>
          </nav>
        </aside>

        <section className="content-grid">
          <section className="panel" id="session">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Auth</p>
                <h2>Session</h2>
              </div>
              <span className={session ? "pill ok" : "pill"}>{session ? "aktiv" : "offen"}</span>
            </div>

            {session ? (
              <div className="session-summary">
                <dl>
                  <div>
                    <dt>User</dt>
                    <dd>{session.display_name ?? session.email}</dd>
                  </div>
                  <div>
                    <dt>E-Mail</dt>
                    <dd>{session.email}</dd>
                  </div>
                  <div>
                    <dt>Rollen</dt>
                    <dd>{roleText}</dd>
                  </div>
                  <div>
                    <dt>Ablauf</dt>
                    <dd>{new Date(session.expires_at).toLocaleString("de-DE")}</dd>
                  </div>
                </dl>
              </div>
            ) : (
              <form className="login-form" onSubmit={handleLogin}>
                <label>
                  E-Mail
                  <input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    autoComplete="username"
                    required
                  />
                </label>
                <label>
                  Passwort
                  <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete="current-password"
                    required
                  />
                </label>
                <button className="primary-action" type="submit" disabled={loading}>
                  {loading ? "Pruefen" : "Einloggen"}
                </button>
              </form>
            )}
            {error ? <p className="error-line">{error}</p> : null}
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">System</p>
                <h2>API</h2>
              </div>
              <span className="pill ok">lokal</span>
            </div>
            <div className="metric-list">
              <a href={`${API_BASE_URL}/health`} target="_blank" rel="noreferrer">
                Health
              </a>
              <a href={`${API_BASE_URL}/ready`} target="_blank" rel="noreferrer">
                Readiness
              </a>
              <a href={`${API_BASE_URL}/version`} target="_blank" rel="noreferrer">
                Version
              </a>
            </div>
          </section>

          {session ? (
            <section className="panel wide" id="admin-credentials">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Identity</p>
                  <h2>Admin Credentials</h2>
                </div>
                <span className={activeCredentialCount > 0 ? "pill ok" : "pill"}>
                  {activeCredentialCount} aktiv
                </span>
              </div>

              <div className="admin-credential-layout">
                <form className="credential-form" onSubmit={handleCreateCredential}>
                  <div className="form-grid">
                    <label>
                      E-Mail
                      <input
                        type="email"
                        value={createEmail}
                        onChange={(event) => setCreateEmail(event.target.value)}
                        autoComplete="off"
                        required
                      />
                    </label>
                    <label>
                      Anzeigename
                      <input
                        type="text"
                        value={createDisplayName}
                        onChange={(event) => setCreateDisplayName(event.target.value)}
                        autoComplete="off"
                      />
                    </label>
                    <label>
                      Login-Passwort
                      <input
                        type="password"
                        value={createPassword}
                        onChange={(event) => setCreatePassword(event.target.value)}
                        autoComplete="new-password"
                        minLength={12}
                      />
                    </label>
                  </div>
                  <div className="action-row">
                    <button className="primary-action" type="submit" disabled={credentialActionId === "create"}>
                      {credentialActionId === "create" ? "Erzeuge" : "Credential erzeugen"}
                    </button>
                    <span className="muted-line">{credentialStatus}</span>
                  </div>
                </form>

                {createdToken ? (
                  <div className="token-panel" role="status">
                    <div>
                      <p className="eyebrow">Einmaliger Token</p>
                      <h3>{createdToken.label}</h3>
                    </div>
                    <code className="token-output">{createdToken.value}</code>
                    <div className="action-row">
                      <button className="secondary-action" type="button" onClick={handleCopyToken}>
                        Kopieren
                      </button>
                      <button className="secondary-action" type="button" onClick={() => setCreatedToken(null)}>
                        Ausblenden
                      </button>
                    </div>
                  </div>
                ) : null}

                <div className="credential-toolbar">
                  <div className="filter-group" aria-label="Credential-Filter">
                    <button
                      className={credentialFilter === "active" ? "filter-button is-selected" : "filter-button"}
                      type="button"
                      onClick={() => void handleFilterChange("active")}
                    >
                      Aktiv
                    </button>
                    <button
                      className={credentialFilter === "all" ? "filter-button is-selected" : "filter-button"}
                      type="button"
                      onClick={() => void handleFilterChange("all")}
                    >
                      Alle
                    </button>
                  </div>
                  <button
                    className="secondary-action"
                    type="button"
                    onClick={() => void loadAdminCredentials(credentialFilter)}
                    disabled={credentialsLoading}
                  >
                    {credentialsLoading ? "Laedt" : "Aktualisieren"}
                  </button>
                </div>

                {credentialsError ? <p className="error-line">{credentialsError}</p> : null}

                <div className="table-wrap">
                  <table className="credential-table">
                    <thead>
                      <tr>
                        <th scope="col">User</th>
                        <th scope="col">Prefix</th>
                        <th scope="col">Status</th>
                        <th scope="col">Erstellt</th>
                        <th scope="col">Zuletzt genutzt</th>
                        <th scope="col">Aktionen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {credentials.map((credential) => (
                        <tr key={credential.id}>
                          <td>
                            <strong>{credential.display_name ?? credential.email}</strong>
                            <span>{credential.email}</span>
                          </td>
                          <td>
                            <code>{credential.token_prefix ?? "ohne"}</code>
                          </td>
                          <td>
                            <span className={credential.active ? "state-label is-active" : "state-label"}>
                              {credential.active ? "aktiv" : "inaktiv"}
                            </span>
                          </td>
                          <td>{formatDate(credential.created_at)}</td>
                          <td>{credential.last_used_at ? formatDate(credential.last_used_at) : "nie"}</td>
                          <td>
                            <div className="row-actions">
                              <button
                                className="secondary-action compact"
                                type="button"
                                disabled={!credential.active || credentialActionId === credential.id}
                                onClick={() => void handleRotateCredential(credential)}
                              >
                                Rotieren
                              </button>
                              <button
                                className="danger-action compact"
                                type="button"
                                disabled={!credential.active || credentialActionId === credential.id}
                                onClick={() => void handleDeactivateCredential(credential)}
                              >
                                Deaktivieren
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                      {credentials.length === 0 ? (
                        <tr>
                          <td colSpan={6}>Keine Admin-Credentials fuer den aktuellen Filter.</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          ) : null}

          {session ? (
            <section className="panel wide" id="subscriptions">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Access</p>
                  <h2>Subscriptions</h2>
                </div>
                <span className={enabledSubscriptionCount > 0 ? "pill ok" : "pill"}>
                  {enabledSubscriptionCount} copy-ready
                </span>
              </div>

              <div className="admin-credential-layout">
                <form className="credential-form" onSubmit={handleUpsertSubscription}>
                  <datalist id="admin-credential-users">
                    {credentialUsers.map((user) => (
                      <option key={user.user_id} value={user.user_id}>
                        {user.label} ({user.email})
                      </option>
                    ))}
                  </datalist>
                  <div className="form-grid subscription-grid">
                    <label>
                      User-ID
                      <input
                        list="admin-credential-users"
                        type="text"
                        value={subscriptionUserId}
                        onChange={(event) => setSubscriptionUserId(event.target.value)}
                        required
                      />
                    </label>
                    <label>
                      Status
                      <select
                        value={subscriptionState}
                        onChange={(event) => setSubscriptionState(event.target.value as SubscriptionStatus)}
                      >
                        {SUBSCRIPTION_STATUSES.map((item) => (
                          <option key={item} value={item}>
                            {item}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Period End
                      <input
                        type="datetime-local"
                        value={currentPeriodEnd}
                        onChange={(event) => setCurrentPeriodEnd(event.target.value)}
                      />
                    </label>
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={copyTradingEnabled}
                        onChange={(event) => setCopyTradingEnabled(event.target.checked)}
                      />
                      Copy Trading enabled
                    </label>
                  </div>
                  <div className="action-row">
                    <button
                      className="primary-action"
                      type="submit"
                      disabled={subscriptionActionUserId === subscriptionUserId}
                    >
                      {subscriptionActionUserId === subscriptionUserId ? "Speichert" : "Subscription speichern"}
                    </button>
                    <span className="muted-line">{subscriptionStatus}</span>
                  </div>
                </form>

                <div className="credential-toolbar">
                  <div className="filter-group" aria-label="Subscription-Filter">
                    <button
                      className={subscriptionFilter === "all" ? "filter-button is-selected" : "filter-button"}
                      type="button"
                      onClick={() => void handleSubscriptionFilterChange("all")}
                    >
                      Alle
                    </button>
                    {SUBSCRIPTION_STATUSES.map((item) => (
                      <button
                        className={subscriptionFilter === item ? "filter-button is-selected" : "filter-button"}
                        key={item}
                        type="button"
                        onClick={() => void handleSubscriptionFilterChange(item)}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                  <button
                    className="secondary-action"
                    type="button"
                    onClick={() => void loadSubscriptions(subscriptionFilter)}
                    disabled={subscriptionsLoading}
                  >
                    {subscriptionsLoading ? "Laedt" : "Aktualisieren"}
                  </button>
                </div>

                {subscriptionsError ? <p className="error-line">{subscriptionsError}</p> : null}

                <div className="table-wrap">
                  <table className="credential-table">
                    <thead>
                      <tr>
                        <th scope="col">User-ID</th>
                        <th scope="col">Status</th>
                        <th scope="col">Copy Trading</th>
                        <th scope="col">Period End</th>
                        <th scope="col">Aktualisiert</th>
                        <th scope="col">Aktionen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {subscriptions.map((subscription) => (
                        <tr key={subscription.user_id}>
                          <td>
                            <code>{subscription.user_id}</code>
                          </td>
                          <td>
                            <span className={subscription.status === "active" ? "state-label is-active" : "state-label"}>
                              {subscription.status}
                            </span>
                          </td>
                          <td>{subscription.copy_trading_enabled ? "enabled" : "disabled"}</td>
                          <td>
                            {subscription.current_period_end
                              ? formatDate(subscription.current_period_end)
                              : "kein Ende"}
                          </td>
                          <td>{formatDate(subscription.updated_at)}</td>
                          <td>
                            <button
                              className="secondary-action compact"
                              type="button"
                              onClick={() => editSubscription(subscription)}
                            >
                              Bearbeiten
                            </button>
                          </td>
                        </tr>
                      ))}
                      {subscriptions.length === 0 ? (
                        <tr>
                          <td colSpan={6}>Keine Subscriptions fuer den aktuellen Filter.</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          ) : null}

          {session ? (
            <section className="panel wide" id="exchange">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Exchange</p>
                  <h2>Exchange Accounts</h2>
                </div>
                <span className={activeExchangeAccountCount > 0 ? "pill ok" : "pill"}>
                  {activeExchangeAccountCount} aktiv
                </span>
              </div>

              <div className="admin-credential-layout">
                <form className="credential-form" onSubmit={handleCreateExchangeAccount}>
                  <div className="form-grid exchange-grid">
                    <label>
                      User-ID
                      <input
                        list="admin-credential-users"
                        type="text"
                        value={exchangeAccountUserId}
                        onChange={(event) => setExchangeAccountUserId(event.target.value)}
                        required
                      />
                    </label>
                    <label>
                      Exchange
                      <select value={exchange} onChange={(event) => setExchange(event.target.value as Exchange)}>
                        {EXCHANGES.map((item) => (
                          <option key={item} value={item}>
                            {item}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Account-ID
                      <input
                        type="text"
                        value={exchangeAccountId}
                        onChange={(event) => setExchangeAccountId(event.target.value)}
                        required
                      />
                    </label>
                    <label>
                      Label
                      <input
                        type="text"
                        value={exchangeAccountLabel}
                        onChange={(event) => setExchangeAccountLabel(event.target.value)}
                      />
                    </label>
                    <label>
                      Status
                      <select
                        value={exchangeAccountState}
                        onChange={(event) => setExchangeAccountState(event.target.value as ExchangeAccountStatus)}
                      >
                        {EXCHANGE_ACCOUNT_STATUSES.map((item) => (
                          <option key={item} value={item}>
                            {item}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Secret Reference
                      <input
                        type="text"
                        value={secretReference}
                        onChange={(event) => setSecretReference(event.target.value)}
                        autoComplete="off"
                      />
                    </label>
                    <label>
                      Secret Fingerprint
                      <input
                        type="text"
                        value={secretFingerprint}
                        onChange={(event) => setSecretFingerprint(event.target.value)}
                        autoComplete="off"
                        minLength={64}
                        maxLength={64}
                      />
                    </label>
                  </div>
                  <div className="action-row">
                    <button className="primary-action" type="submit" disabled={exchangeAccountActionId === "create"}>
                      {exchangeAccountActionId === "create" ? "Erzeugt" : "Exchange-Account erzeugen"}
                    </button>
                    <span className="muted-line">{exchangeAccountStatus}</span>
                  </div>
                </form>

                <div className="credential-toolbar">
                  <div className="filter-group" aria-label="Exchange-Account-Filter">
                    <button
                      className={exchangeAccountFilter === "all" ? "filter-button is-selected" : "filter-button"}
                      type="button"
                      onClick={() => void handleExchangeAccountFilterChange("all")}
                    >
                      Alle
                    </button>
                    {EXCHANGE_ACCOUNT_STATUSES.map((item) => (
                      <button
                        className={exchangeAccountFilter === item ? "filter-button is-selected" : "filter-button"}
                        key={item}
                        type="button"
                        onClick={() => void handleExchangeAccountFilterChange(item)}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                  <button
                    className="secondary-action"
                    type="button"
                    onClick={() => void loadExchangeAccounts(exchangeAccountFilter)}
                    disabled={exchangeAccountsLoading}
                  >
                    {exchangeAccountsLoading ? "Laedt" : "Aktualisieren"}
                  </button>
                </div>

                {exchangeAccountsError ? <p className="error-line">{exchangeAccountsError}</p> : null}

                <div className="table-wrap">
                  <table className="credential-table">
                    <thead>
                      <tr>
                        <th scope="col">Account</th>
                        <th scope="col">User-ID</th>
                        <th scope="col">Exchange</th>
                        <th scope="col">Status</th>
                        <th scope="col">Secret</th>
                        <th scope="col">Aktualisiert</th>
                        <th scope="col">Aktionen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {exchangeAccounts.map((account) => (
                        <tr key={account.id}>
                          <td>
                            <strong>{account.label ?? account.account_id}</strong>
                            <span>{account.account_id}</span>
                          </td>
                          <td>
                            <code>{account.user_id}</code>
                          </td>
                          <td>{account.exchange}</td>
                          <td>
                            <span className={account.status === "active" ? "state-label is-active" : "state-label"}>
                              {account.status}
                            </span>
                          </td>
                          <td>
                            {account.has_secret ? (
                              <span className="secret-state">
                                yes {account.secret_fingerprint_prefix ? `(${account.secret_fingerprint_prefix})` : ""}
                              </span>
                            ) : (
                              "no"
                            )}
                          </td>
                          <td>{formatDate(account.updated_at)}</td>
                          <td>
                            <div className="row-actions">
                              <button
                                className="secondary-action compact"
                                type="button"
                                disabled={account.status === "active" || exchangeAccountActionId === account.id}
                                onClick={() => void updateExchangeAccountStatus(account, "active")}
                              >
                                Aktivieren
                              </button>
                              <button
                                className="secondary-action compact"
                                type="button"
                                disabled={account.status === "disabled" || exchangeAccountActionId === account.id}
                                onClick={() => void updateExchangeAccountStatus(account, "disabled")}
                              >
                                Deaktivieren
                              </button>
                              <button
                                className="danger-action compact"
                                type="button"
                                disabled={!account.has_secret || exchangeAccountActionId === account.id}
                                onClick={() => void clearExchangeAccountSecret(account)}
                              >
                                Secret leeren
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                      {exchangeAccounts.length === 0 ? (
                        <tr>
                          <td colSpan={7}>Keine Exchange-Accounts fuer den aktuellen Filter.</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          ) : null}

          {session ? (
            <section className="panel wide" id="copy-relationships">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Copy</p>
                  <h2>Copy Relationships</h2>
                </div>
                <span className={activeRelationshipCount > 0 ? "pill ok" : "pill"}>
                  {activeRelationshipCount} aktiv
                </span>
              </div>

              <div className="admin-credential-layout">
                <form className="credential-form" onSubmit={handleCreateCopyRelationship}>
                  <datalist id="exchange-account-ids">
                    {exchangeAccountIds.map((accountId) => (
                      <option key={accountId} value={accountId} />
                    ))}
                  </datalist>
                  <div className="form-grid relationship-grid">
                    <label>
                      Source Exchange
                      <select
                        value={relationshipSourceExchange}
                        onChange={(event) => setRelationshipSourceExchange(event.target.value as Exchange)}
                      >
                        {EXCHANGES.map((item) => (
                          <option key={item} value={item}>
                            {item}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Source Account
                      <input
                        list="exchange-account-ids"
                        type="text"
                        value={relationshipSourceAccountId}
                        onChange={(event) => setRelationshipSourceAccountId(event.target.value)}
                        required
                      />
                    </label>
                    <label>
                      Source Symbol
                      <input
                        type="text"
                        value={relationshipSourceSymbol}
                        onChange={(event) => setRelationshipSourceSymbol(event.target.value)}
                      />
                    </label>
                    <label>
                      Follower Account
                      <input
                        list="exchange-account-ids"
                        type="text"
                        value={relationshipFollowerAccountId}
                        onChange={(event) => setRelationshipFollowerAccountId(event.target.value)}
                        required
                      />
                    </label>
                    <label>
                      Target Exchange
                      <select
                        value={relationshipTargetExchange}
                        onChange={(event) => setRelationshipTargetExchange(event.target.value as Exchange)}
                      >
                        {EXCHANGES.map((item) => (
                          <option key={item} value={item}>
                            {item}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Target Symbol
                      <input
                        type="text"
                        value={relationshipTargetSymbol}
                        onChange={(event) => setRelationshipTargetSymbol(event.target.value)}
                        required
                      />
                    </label>
                    <label>
                      Max Slippage bps
                      <input
                        type="number"
                        min={0}
                        max={1000}
                        value={relationshipMaxSlippageBps}
                        onChange={(event) => setRelationshipMaxSlippageBps(event.target.value)}
                        required
                      />
                    </label>
                    <label>
                      Effective From
                      <input
                        type="datetime-local"
                        value={relationshipEffectiveFrom}
                        onChange={(event) => setRelationshipEffectiveFrom(event.target.value)}
                        required
                      />
                    </label>
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={relationshipActive}
                        onChange={(event) => setRelationshipActive(event.target.checked)}
                      />
                      Active
                    </label>
                  </div>
                  <div className="action-row">
                    <button className="primary-action" type="submit" disabled={relationshipActionId === "create"}>
                      {relationshipActionId === "create" ? "Erzeugt" : "Relationship erzeugen"}
                    </button>
                    <span className="muted-line">{relationshipStatus}</span>
                  </div>
                </form>

                <div className="credential-toolbar">
                  <div className="filter-group" aria-label="Copy-Relationship-Filter">
                    <button
                      className={relationshipFilter === "active" ? "filter-button is-selected" : "filter-button"}
                      type="button"
                      onClick={() => void handleRelationshipFilterChange("active")}
                    >
                      Aktiv
                    </button>
                    <button
                      className={relationshipFilter === "all" ? "filter-button is-selected" : "filter-button"}
                      type="button"
                      onClick={() => void handleRelationshipFilterChange("all")}
                    >
                      Alle
                    </button>
                  </div>
                  <button
                    className="secondary-action"
                    type="button"
                    onClick={() => void loadCopyRelationships(relationshipFilter)}
                    disabled={relationshipsLoading}
                  >
                    {relationshipsLoading ? "Laedt" : "Aktualisieren"}
                  </button>
                </div>

                {relationshipsError ? <p className="error-line">{relationshipsError}</p> : null}

                <div className="table-wrap">
                  <table className="credential-table">
                    <thead>
                      <tr>
                        <th scope="col">Route</th>
                        <th scope="col">Source</th>
                        <th scope="col">Follower</th>
                        <th scope="col">Slippage</th>
                        <th scope="col">Status</th>
                        <th scope="col">Effective</th>
                        <th scope="col">Aktionen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {copyRelationships.map((relationship) => (
                        <tr key={relationship.id}>
                          <td>
                            <strong>{relationship.target_symbol}</strong>
                            <span>{relationship.id}</span>
                          </td>
                          <td>
                            {relationship.source_exchange}
                            <span>{relationship.source_account_id}</span>
                            <span>{relationship.source_symbol ?? "alle Symbole"}</span>
                          </td>
                          <td>
                            {relationship.target_exchange}
                            <span>{relationship.follower_account_id}</span>
                          </td>
                          <td>{relationship.max_slippage_bps} bps</td>
                          <td>
                            <span className={relationship.active ? "state-label is-active" : "state-label"}>
                              {relationship.active ? "aktiv" : "inaktiv"}
                            </span>
                          </td>
                          <td>{formatDate(relationship.effective_from)}</td>
                          <td>
                            <div className="row-actions">
                              <button
                                className="secondary-action compact"
                                type="button"
                                disabled={relationship.active || relationshipActionId === relationship.id}
                                onClick={() => void updateCopyRelationshipActive(relationship, true)}
                              >
                                Aktivieren
                              </button>
                              <button
                                className="secondary-action compact"
                                type="button"
                                disabled={!relationship.active || relationshipActionId === relationship.id}
                                onClick={() => void updateCopyRelationshipActive(relationship, false)}
                              >
                                Deaktivieren
                              </button>
                              <button
                                className="secondary-action compact"
                                type="button"
                                onClick={() => void loadRiskSettingsForRelationship(relationship.id)}
                              >
                                Risk laden
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                      {copyRelationships.length === 0 ? (
                        <tr>
                          <td colSpan={7}>Keine Copy-Relationships fuer den aktuellen Filter.</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          ) : null}

          {session ? (
            <section className="panel wide" id="risk">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Execution Safety</p>
                  <h2>Risk Settings</h2>
                </div>
                <span className={riskSettings?.enabled ? "pill ok" : "pill"}>
                  {riskSettings?.enabled ? "aktiv" : "nicht geladen"}
                </span>
              </div>

              <div className="admin-credential-layout">
                <form className="credential-form" onSubmit={handleUpsertRiskSettings}>
                  <datalist id="copy-relationship-ids">
                    {copyRelationships.map((relationship) => (
                      <option key={relationship.id} value={relationship.id}>
                        {relationship.source_account_id} to {relationship.follower_account_id}
                      </option>
                    ))}
                  </datalist>
                  <div className="form-grid risk-grid">
                    <label>
                      Relationship-ID
                      <input
                        list="copy-relationship-ids"
                        type="text"
                        value={riskRelationshipId}
                        onChange={(event) => setRiskRelationshipId(event.target.value)}
                        required
                      />
                    </label>
                    <label>
                      Max Order Quantity
                      <input
                        type="number"
                        min="0"
                        step="any"
                        value={riskMaxOrderQuantity}
                        onChange={(event) => setRiskMaxOrderQuantity(event.target.value)}
                      />
                    </label>
                    <label>
                      Max Slippage bps
                      <input
                        type="number"
                        min={0}
                        max={1000}
                        value={riskMaxSlippageBps}
                        onChange={(event) => setRiskMaxSlippageBps(event.target.value)}
                        required
                      />
                    </label>
                    <label>
                      Max Leverage
                      <input
                        type="number"
                        min="0"
                        step="any"
                        value={riskMaxLeverage}
                        onChange={(event) => setRiskMaxLeverage(event.target.value)}
                      />
                    </label>
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={riskEnabled}
                        onChange={(event) => setRiskEnabled(event.target.checked)}
                      />
                      Risk Gate enabled
                    </label>
                  </div>
                  <div className="action-row">
                    <button className="primary-action" type="submit" disabled={riskLoading}>
                      {riskLoading ? "Speichert" : "Risk Settings speichern"}
                    </button>
                    <button
                      className="secondary-action"
                      type="button"
                      disabled={riskLoading || !riskRelationshipId}
                      onClick={() => void loadRiskSettingsForRelationship(riskRelationshipId)}
                    >
                      Laden
                    </button>
                    <span className="muted-line">{riskStatus}</span>
                  </div>
                </form>

                {riskError ? <p className="error-line">{riskError}</p> : null}
                {riskSettings ? (
                  <div className="token-panel" role="status">
                    <div>
                      <p className="eyebrow">Aktuelle Risk Settings</p>
                      <h3>{riskSettings.copy_relationship_id}</h3>
                    </div>
                    <div className="summary-grid">
                      <span>Enabled: {riskSettings.enabled ? "true" : "false"}</span>
                      <span>Max Quantity: {riskSettings.max_order_quantity ?? "unbegrenzt"}</span>
                      <span>Max Slippage: {riskSettings.max_slippage_bps} bps</span>
                      <span>Max Leverage: {riskSettings.max_leverage ?? "unbegrenzt"}</span>
                    </div>
                  </div>
                ) : null}
              </div>
            </section>
          ) : null}

          {session ? (
            <section className="panel wide" id="dlq">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Operations</p>
                  <h2>Dead Letter Queue</h2>
                </div>
                <span className={openDeadLetterCount > 0 ? "pill" : "pill ok"}>
                  {openDeadLetterCount} offen
                </span>
              </div>

              <div className="admin-credential-layout">
                <div className="credential-toolbar">
                  <div className="filter-group" aria-label="DLQ-Filter">
                    <button
                      className={deadLetterFilter === "all" ? "filter-button is-selected" : "filter-button"}
                      type="button"
                      onClick={() => void handleDeadLetterFilterChange("all")}
                    >
                      Alle
                    </button>
                    {DEAD_LETTER_STATUSES.map((item) => (
                      <button
                        className={deadLetterFilter === item ? "filter-button is-selected" : "filter-button"}
                        key={item}
                        type="button"
                        onClick={() => void handleDeadLetterFilterChange(item)}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                  <button
                    className="secondary-action"
                    type="button"
                    onClick={() => void loadDeadLetterEvents(deadLetterFilter)}
                    disabled={deadLettersLoading}
                  >
                    {deadLettersLoading ? "Laedt" : "Aktualisieren"}
                  </button>
                </div>

                <span className="muted-line">{deadLettersStatus}</span>
                {deadLettersError ? <p className="error-line">{deadLettersError}</p> : null}

                <div className="table-wrap">
                  <table className="credential-table">
                    <thead>
                      <tr>
                        <th scope="col">Subject</th>
                        <th scope="col">Status</th>
                        <th scope="col">Attempts</th>
                        <th scope="col">Error</th>
                        <th scope="col">Created</th>
                        <th scope="col">Payload</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deadLetterEvents.map((event) => (
                        <tr key={event.id}>
                          <td>
                            <strong>{event.failed_subject}</strong>
                            <span>{event.idempotency_key}</span>
                          </td>
                          <td>
                            <span className={event.status === "open" ? "state-label" : "state-label is-active"}>
                              {event.status}
                            </span>
                          </td>
                          <td>
                            {event.delivery_attempt}/{event.max_delivery_attempts}
                          </td>
                          <td>{event.error_type}</td>
                          <td>{formatDate(event.created_at)}</td>
                          <td>
                            {event.payload ? (
                              <details>
                                <summary>JSON</summary>
                                <pre className="json-block">{formatJson(event.payload)}</pre>
                              </details>
                            ) : (
                              "leer"
                            )}
                          </td>
                        </tr>
                      ))}
                      {deadLetterEvents.length === 0 ? (
                        <tr>
                          <td colSpan={6}>Keine DLQ-Events fuer den aktuellen Filter.</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          ) : null}

          {session ? (
            <section className="panel wide" id="audit">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Audit</p>
                  <h2>Audit Logs</h2>
                </div>
                <span className="pill">{auditLogs.length} geladen</span>
              </div>

              <div className="admin-credential-layout">
                <form
                  className="credential-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void loadAuditLogs();
                  }}
                >
                  <div className="form-grid audit-grid">
                    <label>
                      Entity Type
                      <input
                        type="text"
                        value={auditEntityType}
                        onChange={(event) => setAuditEntityType(event.target.value)}
                      />
                    </label>
                    <label>
                      Entity ID
                      <input
                        type="text"
                        value={auditEntityId}
                        onChange={(event) => setAuditEntityId(event.target.value)}
                      />
                    </label>
                    <label>
                      Action
                      <input type="text" value={auditAction} onChange={(event) => setAuditAction(event.target.value)} />
                    </label>
                  </div>
                  <div className="action-row">
                    <button className="primary-action" type="submit" disabled={auditLoading}>
                      {auditLoading ? "Laedt" : "Audit laden"}
                    </button>
                    <button
                      className="secondary-action"
                      type="button"
                      onClick={() => {
                        setAuditEntityType("");
                        setAuditEntityId("");
                        setAuditAction("");
                        setAuditStatus("Audit-Filter geleert");
                      }}
                    >
                      Filter leeren
                    </button>
                    <span className="muted-line">{auditStatus}</span>
                  </div>
                </form>

                {auditError ? <p className="error-line">{auditError}</p> : null}

                <div className="table-wrap">
                  <table className="credential-table">
                    <thead>
                      <tr>
                        <th scope="col">Aktion</th>
                        <th scope="col">Entity</th>
                        <th scope="col">Actor</th>
                        <th scope="col">Zeit</th>
                        <th scope="col">States</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditLogs.map((log) => (
                        <tr key={log.id}>
                          <td>
                            <strong>{log.action}</strong>
                            <span>{log.id}</span>
                          </td>
                          <td>
                            {log.entity_type}
                            <span>{log.entity_id ?? "ohne Entity-ID"}</span>
                            <button
                              className="secondary-action compact inline-action"
                              type="button"
                              onClick={() => applyAuditEntity(log.entity_type, log.entity_id)}
                            >
                              Filter setzen
                            </button>
                          </td>
                          <td>
                            {log.actor_type}
                            <span>{log.actor_id ?? "system"}</span>
                          </td>
                          <td>{formatDate(log.occurred_at)}</td>
                          <td>
                            <details>
                              <summary>JSON</summary>
                              <pre className="json-block">
                                {formatJson({
                                  before_state: log.before_state,
                                  after_state: log.after_state,
                                  metadata: log.metadata
                                })}
                              </pre>
                            </details>
                          </td>
                        </tr>
                      ))}
                      {auditLogs.length === 0 ? (
                        <tr>
                          <td colSpan={5}>Keine Audit-Logs fuer den aktuellen Filter.</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          ) : null}

          <section className="panel wide">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Naechste Controls</p>
                <h2>Foundation Oberflaechen</h2>
              </div>
              <span className="pill">geplant</span>
            </div>
            <div className="control-grid">
              {[
                "Users / Roles",
                "Password Change",
                "Password Reset",
                "Browser E2E Tests"
              ].map((item) => (
                <button className="control-tile" disabled key={item}>
                  {item}
                </button>
              ))}
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}

async function apiError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      return "Request-Validierung fehlgeschlagen";
    }
  } catch {
    return `Request fehlgeschlagen (${response.status})`;
  }
  return `Request fehlgeschlagen (${response.status})`;
}

function readCookie(name: string): string {
  if (typeof document === "undefined") {
    return "";
  }
  const prefix = `${name}=`;
  const cookie = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(prefix));
  if (!cookie) {
    return "";
  }
  try {
    return decodeURIComponent(cookie.slice(prefix.length));
  } catch {
    return cookie.slice(prefix.length);
  }
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("de-DE");
}

function toDateTimeLocal(value: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  const offsetDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return offsetDate.toISOString().slice(0, 16);
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}
