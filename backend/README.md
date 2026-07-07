# MeshNet AI — Backend

Node.js + Express REST API. Handles mesh topology state, alert broadcasting, message relay, and device registration. Designed to run on a local device (command center laptop) with no internet dependency.

## Team setup

```bash
cd backend
npm install
cp config/.env.example config/.env   # fill in values
npm run dev      # ts-node-dev hot reload on port 4000
npm run build    # compile TypeScript → dist/
npm start        # run compiled build
```

## Folder structure

```
backend/
├── src/
│   ├── routes/
│   │   ├── mesh.ts        # GET  /api/mesh/topology
│   │   │                  # POST /api/mesh/register
│   │   ├── alerts.ts      # POST /api/alerts
│   │   │                  # GET  /api/alerts
│   │   ├── messages.ts    # POST /api/messages
│   │   │                  # GET  /api/messages
│   │   └── health.ts      # GET  /api/health
│   ├── middleware/
│   │   ├── auth.ts        # Shared-secret auth for node-to-node calls
│   │   ├── logger.ts      # Request logging (no external service needed)
│   │   └── rateLimit.ts   # Prevent broadcast storms
│   ├── services/
│   │   ├── meshService.ts    # Topology tracking, AODV routing table
│   │   ├── alertService.ts   # Alert persistence + broadcast
│   │   └── cryptoService.ts  # Node identity verification (Ed25519)
│   └── models/
│       ├── node.ts         # MeshNode type
│       ├── alert.ts        # Alert type
│       └── message.ts      # Message type
├── config/
│   └── .env.example
└── package.json
```

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Liveness check |
| GET | `/api/mesh/topology` | Full node + edge graph |
| POST | `/api/mesh/register` | Register a new node |
| GET | `/api/alerts` | List recent alerts |
| POST | `/api/alerts` | Broadcast a new alert |
| GET | `/api/messages` | List messages |
| POST | `/api/messages` | Send a mesh message |
