# GitHub Delivery

Successful queued runs can publish generated code directly to a repository owned by the configured
GitHub user. No local Git repository or credential-bearing remote is created.

## Configuration

```env
GITHUB_OWNER=your-github-username
GITHUB_TOKEN=github_pat_xxxxxxxxx
GITHUB_REPOSITORY_VISIBILITY=private
GITHUB_COMMIT_AUTHOR_NAME=Your Name
GITHUB_COMMIT_AUTHOR_EMAIL=you@example.com
CONTROL_RETAIN_LOCAL_BUILDS=true
```

The fine-grained token needs Repository creation (write), Contents (write), and Metadata (read).
Add Workflows (write) when generated `.github/workflows/*` files should be published.

If both owner and token are absent, delivery is recorded as `skipped`. A partial configuration or
GitHub API failure fails the run while retaining all local artifacts.

## Local retention

Generation and quality checks always use a run-isolated local workspace. Set
`CONTROL_RETAIN_LOCAL_BUILDS=false` to remove the local `builds/` tree only after GitHub has accepted
the generated commit. Failed, skipped, or unpublished builds remain local so source is never deleted
without a durable GitHub copy.

PostgreSQL always retains the run, steps, events, artifact names/hashes, cleanup timestamp, and
GitHub repository/commit references. It does not store source-file bytes. Readable run diagnostics
outside `builds/` also remain on disk. Artifacts removed by policy report `local_available=false`
and their download endpoint returns `410 Gone`.

## Naming and commit behavior

1. The normalized project slug is checked first, such as `todo`.
2. When it already exists, a six-character random suffix is used, such as `todo-a4f19c`.
3. The chosen name is persisted before repository creation.
4. GitHub initializes the repository, then the worker creates blobs/tree/commit through the Git
   database API and advances the default branch without a force push.
5. The repository URL, branch, commit SHA, commit URL, and publication time are stored on the run.

Each repository description and generated commit contains the run ID. If a worker is redelivered
after an uncertain failure, it recognizes and reuses the repository or commit created by that run.

## Published files

- Python-only run: contents of `builds/python` are placed at repository root.
- Node.js-only run: contents of `builds/nodejs` are placed at repository root.
- Dual-stack run: `builds/python` and `builds/nodejs` are published as subdirectories.

Local `.env`, private keys/certificates, credential/secret JSON files, virtual environments, caches,
`node_modules`, and `.git` content are excluded. `.env.example` remains publishable.

## Monitoring

The run API exposes `delivery_status`, `delivery_error`, `repository_url`, and commit fields. The
event stream emits `github_publish_started`, `github_publish_completed`, `github_publish_failed`, or
`github_publish_skipped`.

