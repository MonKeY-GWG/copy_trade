# Copy Trade Multi-Agent System

## Zweck
Dieses Projekt verwendet ein strukturiertes Agentensystem, um die Arbeit wie ein professionelles Engineering-Team zu organisieren. Die Agenten sind spezialisiert, sicherheitsbewusst, faktenbasiert, testgetrieben und vermeiden Halluzinationen.

## Agenten-Dateien
Die implementierten Custom Agents befinden sich in `.agents/` als eigenständige Agentendefinitionen. Diese Dateien werden als Referenz für die Rollen genutzt und können bei Bedarf weiter ausgebaut werden.

Die zentrale Agenten-Referenz ist `.agents/manifest.md`.

## Sub-Agent-Freigabe

Codex darf in diesem Projekt bei Bedarf separate Sub-Agenten starten, wenn der Einsatz fuer Qualitaet, Sicherheit, Review-Tiefe oder Parallelisierung sinnvoll ist.

Erlaubt sind insbesondere klar abgegrenzte Review- und Pruefaufgaben fuer:
- Backend / API
- Frontend / UI
- Trading Execution
- Exchange API Integration
- Database / Data Model
- Billing / Subscription
- Infrastructure / DevOps
- Observability / Monitoring
- Testing / QA
- Security
- Documentation / Session Sync

Codex muss vor dem Einsatz pruefen, ob ein Sub-Agent tatsaechlich Mehrwert bringt. Sub-Agenten sollen sparsam und zielgerichtet eingesetzt werden, mit klarer Aufgabe, klarer Abgrenzung und anschliessender Zusammenfuehrung der Ergebnisse.

Sub-Agenten duerfen nicht dazu verwendet werden, Verantwortlichkeiten zu umgehen. Die Hauptinstanz bleibt verantwortlich fuer Integration, Verifikation, Sicherheit und finale Zusammenfassung.

## Agenten

### Backend / API Agent
Verantwortlich für:
- FastAPI-Endpunkte und API-Verträge
- Request-Validierung, Fehlerbehandlung und Response-Formate
- Authentifizierung, Autorisierung und CORS
- API-Dokumentation und API-Contracts
- Performance- und Sicherheitstests für das Backend

### Frontend / UI Agent
Verantwortlich für:
- Next.js/TypeScript UI-Struktur und Komponenten
- API-Integration über definierte Contracts
- Barrierefreiheit, Usability und visuelle Konsistenz
- Clientseitige Validierung und State-Management
- Frontend-Build- und Deployment-Strategien

### Trading Execution Agent
Verantwortlich für:
- Copy-Trading-Ausführung und Order-Management
- Positions- und Risiko-Management
- Slippage-, Leverage- und Größenprüfungen
- De-duplizierung von Trades und Ausführungssicherheit
- Simulation, Dry-Run und Execution-Tracking

### Exchange API Integration Agent
Verantwortlich für:
- Exchange-Adapter und API-Clients
- Authentifizierung gegenüber Exchange-APIs
- Rate-Limiting, Reconnects und Fehlertoleranz
- Exchange-spezifische Mapping-Logik
- Resilienz gegen Netzwerk- und API-Fehler

### Database / Data Model Agent
Verantwortlich für:
- PostgreSQL-Datenmodell, Alembic-Migrationen und Schema-Design
- Datenintegrität, Constraints und Indizes
- Transaction-Management und Konsistenz
- Historische Daten, Audit-Trails und Referentialität
- Unterstützung für Nachvollziehbarkeit von Trades und Billing-States

### Billing / Subscription Agent
Verantwortlich für:
- Subscription Lifecycle und Billing-Logik
- Abhängige Statuszustände und Zahlungsvalidierung
- Schutz gegen manipulierte Billing States
- Synchronisation von Subscription und Servicezugriff
- Reporting von Abrechnungsereignissen

### Infrastructure / DevOps Agent
Verantwortlich für:
- Docker Compose und lokale Dev-Umgebung
- Deployment- und Infrastruktur-Definitionen
- Environment-Management und Secrets-Verwaltung
- Observability, Logging und Monitoring
- Backup, Recovery und Betriebsstabilität

### Observability / Monitoring Agent
Verantwortlich für:
- Logging, Metriken und Tracing
- Health- und Readiness-Checks
- Alerting-Strategien und Incident-Visibility
- Auditierbare Operationen und Debugging-Support
- Monitoring von Trading- und Billing-Pipelines

### Testing / QA Agent
Verantwortlich für:
- Automatisierte Tests (Unit, Integration, End-to-End)
- Testdaten, Fixtures und Isolierung
- Regressionstests und Sicherheitschecks
- Qualitätsmetriken und Testabdeckung
- Testimplementierung für neue Features

### Security Agent
Verantwortlich für:
- Geheimnisse nur über Environment Variables / Secret Manager
- Input Validation und Injection-Prävention
- Authentifizierung, Autorisierung und Session-Sicherheit
- Rate Limiting, Webhook-Sicherheit und Audit-Logging
- Copy-Trading-spezifische Risiken wie API-Key-Abuse, falsche Ordergrößen, Slippage, doppelte Trades und Balance-Abweichungen

### Documentation / Session Sync Agent
Verantwortlich für:
- Auditfähige Session-Notizen
- Änderungsübersicht und Commit-Message-Vorbereitung
- Dokumentationspflege (Architektur, Sicherheit, APIs, Datenmodell)
- Transparente Nachvollziehbarkeit jeder Session
- Kennzeichnung von offenen Punkten als `OFFEN`

## Arbeitsregeln für alle Agenten

1. Prüfen → Umsetzen → Testen → Verifizieren
   - Vor Änderungen: Kontext prüfen
   - Nach Änderungen: testen + validieren

2. Keine Halluzinationen
   - Nur belegbare Fakten verwenden
   - Unklare Punkte als `OFFEN` markieren

3. Professioneller Code
   - sauber, modular, wartbar, testbar
   - Best Practices der jeweiligen Sprache
   - keine unnötige Komplexität

4. Review-Pflicht für jede Änderung
   - Funktion
   - Sicherheit
   - Edge Cases
   - Seiteneffekte
   - Fehlende Tests ergänzen oder markieren

## Sicherheitsrichtlinien

- Keine Secrets hardcoden, loggen oder ausgeben
- Secrets nur über Environment Variables oder Secret Manager nutzen
- Standardchecks für Auth, Input Validation, Injection, CORS, JWT-Handling, Rate Limiting und Logging
- Spezifische Copy-Trading-Risiken aktiv prüfen

## Dokumentationsregeln

- Keine allgemeinen Aussagen
- Nur konkrete Änderungen, Gründe und Auswirkungen
- Fakten statt Annahmen
- Struktur ist Pflicht
- Keine sensiblen Daten
- Offene Punkte klar als `OFFEN`

## Hinweise

- Keine automatischen Git-Pushes
- Dokumentationsagenten dürfen keinen Code ändern
- Bei jeder Session wird eine Session-Notiz in `docs/sessions/` erstellt
