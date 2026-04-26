# Projekt-Anweisungen für Copilot/Agenten

## Ziel
Nutze das in `AGENTS.md` definierte Multi-Agenten-System als Arbeitsrahmen für dieses Projekt.

## Verbindliche Arbeitsweise
- Prüfen → Umsetzen → Testen → Verifizieren
- Vor jeder Änderung Kontext prüfen
- Nach jeder Änderung Tests und Validierung durchführen
- Fehlende Tests ergänzen oder als `OFFEN` markieren

## Sicherheitsgrundsätze
- Keine API-Keys, Tokens, Passwörter oder Private Keys im Code
- Geheimnisse nur über Environment Variables oder einen Secret Manager
- Keine Ausgabe oder Log-Erstellung sensibler Daten
- Spezifische Copy-Trading-Risiken aktiv prüfen

## Verhalten
- Keine Halluzinationen
- Keine erfundenen APIs oder Funktionen
- Unsichere oder unklare Stellen als `OFFEN` kennzeichnen
- Keine Codeänderungen durch die Dokumentations-/Session-Agenten
- Keine automatischen Git-Pushes

## Session Sync
- Am Ende jeder Session eine Datei in `docs/sessions/YYYY-MM-DD-session.md` erstellen
- Struktur:
  - Ziel der Session
  - Umgesetzt
  - Geändert
  - Entscheidungen
  - Offene Punkte
  - Risiken
  - Nächste Schritte

## Qualitätsanforderungen
- Code muss testbar sein
- Projektweite Sicherheits- und Architekturregeln gelten für alle Änderungen
- Dokumentation muss präzise, faktisch und auditfähig sein
