# Copy Trade Agent Manifest

Dieses Manifest beschreibt die spezialisierten Custom Agents im Copy-Trade-Projekt und dient als zentrale Referenz für ihre Rollen, Aufgaben und Qualitätsregeln.

## Agenten

### backend-api.agent.md
Rolle: Backend / API Agent
- Fokus: Backend-Logik, API-Endpunkte, Services, Auth-Flows, interne Geschäftslogik
- Sicherheitsschwerpunkte: Auth, Autorisierung, Subscription-Status, Input Validation, CORS, Rate Limiting
- Output: klare Änderungskommunikation, Risiko- und OFFEN-Markierung

### frontend-ui.agent.md
Rolle: Frontend / UI Agent
- Fokus: Benutzeroberflächen, Dashboards, Formulare, Statusanzeigen, User-Flows
- Sicherheitsschwerpunkte: kein Storage von Secrets, keine API Keys in LocalStorage, sensible Daten minimieren
- Output: UX-Risiken, Validierung, Fehler-/Loading-/Empty States

### trading-execution.agent.md
Rolle: Trading / Exchange Execution Agent
- Fokus: Trading-Ausführung, Copy-Logik, Order-Mapping, Exchange-Ausführung
- Projektregeln: Standardmäßig keine bestehenden Positionen kopieren, Default-Slippage 1 %, Trade ablehnen bei Slippage-Überschreitung
- Sicherheitsschwerpunkte: validierte Subscription, validierte Exchange-Verbindung, Idempotency

### exchange-integration.agent.md
Rolle: Exchange API Integration Agent
- Fokus: genaue Exchange-Adapter, Authentifizierung, Rate-Limiting, Retry, Mapping
- Sicherheitsschwerpunkte: API-Key-Schutz, fehlertolerante API-Integration

### security.agent.md
Rolle: Security Agent
- Fokus: Architektur, Code, Konfiguration, Dokumentation
- Output: Risikoanalyse mit Priorität und Empfehlungen
- Sicherheitsschwerpunkte: API Keys, Auth, Billing-Manipulation, Replay, Race Conditions

### database-data-model.agent.md
Rolle: Database / Data Model Agent
- Fokus: Datenmodellierung, Migrationen, Persistenz, Audit Logs
- Sicherheitsschwerpunkte: keine Klartext-Secrets, manipulationssichere Statusdaten
- Datenqualität: eindeutige IDs, Timestamps, Statusfelder, Idempotency Keys

### billing-subscription.agent.md
Rolle: Billing / Subscription Agent
- Fokus: Billing-Logik, Zahlungsprüfung, Subscription-Aktivierung
- Projektregeln: kein internes Wallet, keine Smart Contracts, zahlungspflichtig pro Trader
- Sicherheitsschwerpunkte: Webhook-Verifikation, keine Client-Manipulation des Status

### infrastructure-devops.agent.md
Rolle: Infrastructure / DevOps Agent
- Fokus: lokale Entwicklung, Docker/Compose, CI/CD, Deployment, Monitoring, Health Checks
- Sicherheitsschwerpunkte: keine Secrets im Repo, rollbackfähige Deployments

### testing-qa.agent.md
Rolle: Testing / QA Agent
- Fokus: Testbarkeit, Regressionen, API-/Security-/Billing-/Trading-Tests
- Pflicht-Testbereiche: Slippage, Leverage, Idempotency, Subscription-Status, Retry-Verhalten

### documentation-session.agent.md
Rolle: Documentation / Session Sync Agent
- Fokus: Session Notes, Änderungsübersicht, Commit-Vorbereitung, Dokumentationsregeln
- Regeln: keine Codeänderungen, präzise Fakten, keine Spekulation

## Nutzung
- `AGENTS.md` bleibt das Team- und Rollenmodell.
- `.agents/manifest.md` ist die zentrale Agenten-Referenz für das Projekt.
- Jede Agentendatei ist ein echtes Custom-Agent-Profil.

## Hinweise
- Kein automatischer Git-Push.
- Keine Codeänderungen durch den Documentation Agent.
- Offene Punkte stets als `OFFEN` kennzeichnen.
