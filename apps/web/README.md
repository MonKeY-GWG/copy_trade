# Web App

Next.js/TypeScript frontend for the fresh Copy Trade platform.

Status: initial operations console with session auth and first foundation controls.

First implementation scope:

- auth/session shell
- system status links
- foundation control navigation
- admin credential create/list/rotate/deactivate
- subscription list/filter/upsert
- exchange account create/list/status patch/secret metadata clear
- copy relationship create/list/activate/deactivate
- risk settings load/upsert
- dead letter event list/filter
- audit log list/filter

Local start:

```powershell
cd D:\VSC_Projekte\Copy_Trade\apps\web
cmd /c npm install
cmd /c npm run dev
```

The API must allow `http://localhost:3000` via `COPY_TRADE_CORS_ORIGINS`.

Browser smoke tests:

```powershell
cd D:\VSC_Projekte\Copy_Trade\apps\web
cmd /c npm run test:e2e
```

The Playwright smoke tests mock API responses and use the locally installed Chrome channel.
