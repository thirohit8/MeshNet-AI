# MeshNet AI — Frontend

React 18 + Vite + Tailwind CSS mobile UI for the MeshNet AI offline emergency routing system.

## Team setup

```bash
cd frontend
pnpm install        # or npm install
pnpm dev            # starts Vite dev server at http://localhost:5173
pnpm build          # production build → dist/
pnpm preview        # preview production build locally
```

## Folder structure

```
frontend/
├── src/
│   ├── app/
│   │   └── App.tsx          # Root component — all screens live here
│   ├── components/          # Shared UI primitives (Button, Badge, Card…)
│   ├── hooks/               # Custom React hooks (useMesh, useGPS, useBLE…)
│   ├── lib/                 # Utilities (mesh protocol helpers, crypto, formatting)
│   └── styles/
│       ├── fonts.css        # Google Fonts imports
│       ├── theme.css        # Design tokens (colors, radius, typography)
│       └── index.css        # Tailwind directives + base layer
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## Screens / tabs

| Tab | Path | Owner |
|-----|------|-------|
| Home (dashboard) | `App.tsx → HomeTab` | — |
| Alert broadcast | `App.tsx → AlertTab` | — |
| Mesh map | `App.tsx → MapTab` | — |
| Comms (messages) | `App.tsx → CommsTab` | — |

## Environment variables

Create a `.env.local` file (never commit this):

```
VITE_API_BASE_URL=http://localhost:4000
VITE_MESH_NODE_ID=self
```

## Key dependencies

- `react` + `react-dom` — UI runtime
- `motion/react` — animations
- `lucide-react` — icons
- `tailwind-merge` + `clsx` — class composition
- `@radix-ui/*` — accessible primitives (Dialog, Tabs…)
