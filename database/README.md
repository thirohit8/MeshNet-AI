# MeshNet AI — Database

SQLite (via `better-sqlite3`) for offline-first, zero-dependency local persistence. No Postgres, no cloud — the entire DB runs on the command center device as a single file.

## Team setup

```bash
cd database
node migrations/run.js     # applies all migrations in order
node seeds/run.js          # loads development seed data
```

## Folder structure

```
database/
├── schema/
│   └── schema.sql         # Canonical schema (source of truth)
├── migrations/
│   ├── 001_create_nodes.sql
│   ├── 002_create_alerts.sql
│   ├── 003_create_messages.sql
│   └── run.js             # Migration runner
└── seeds/
    ├── nodes.json          # Sample mesh nodes
    ├── alerts.json         # Sample alerts
    └── run.js              # Seed runner
```

## Design decisions

- **SQLite** — single file, zero network, works offline. The DB file path is set via `DB_PATH` in backend `.env`.
- **No ORM** — raw SQL with prepared statements for clarity and minimal dependencies.
- **Migrations are append-only** — never edit an existing migration. Add a new numbered file instead.
- **Encryption at rest** — message ciphertext is stored as-is (already AES-GCM encrypted by the sender). The DB does not hold plaintext message content.
