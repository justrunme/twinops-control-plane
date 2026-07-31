# TwinOps Web Control Plane

Live UI for the TwinOps drift timeline.

## Develop

Terminal 1:

```bash
make serve
```

Terminal 2:

```bash
cd web
npm install
npm run dev
```

Open http://127.0.0.1:5173

Vite proxies `/api` and `/ws` to the live API on port 8080.

## Production build

```bash
npm run build
```

The API can serve `web/dist` when present (`twinopsctl serve`).
