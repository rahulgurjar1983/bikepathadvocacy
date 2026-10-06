# Progress

The loop works these rows from the top down, one row per turn. A row is done (`[x]`) only when its PR merged to `main` with green CI.

Marks: `[ ]` open, `[~]` started, `[x]` done. 🔒 waits on a sign-off. 👤 needs a person. Each row ends with the spec IDs its tests must cover.

## Phase S: Scaffold (operator)

- [x] **S0.1** Gates: red-green, test retention, no comments, no source reads, reading level, secrets, spec coverage, verification, inputs, generic code, ledger (FR-0.2, FR-0.3, FR-0.4, FR-0.5, FR-0.6, FR-0.7, FR-0.8, FR-0.9, FR-0.10, FR-0.16, FR-0.17, FR-0.18)
- [x] **S0.2** Ralph loop and row picker (FR-0.13, FR-0.14)
- [x] **S0.3** Git hooks and Telegram notes (FR-0.15, FR-0.19)
