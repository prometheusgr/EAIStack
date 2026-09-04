# User Management

**Status**: docs + deep link implemented (issue #40). An in-app user list/role-editor was considered and deliberately not built — see "Why there's no in-app user editor" below. Surfacing Keycloak's own admin/login events inside EAIStack's own Audit Log screen is a separate, deferred follow-up ([issue #63](../../../issues/63)).

This guide assumes **zero prior Keycloak knowledge**. If you've never used Keycloak before, read this top to bottom before touching anything.

## Why Keycloak, not EAIStack, owns this

EAIStack delegates identity and authorization entirely to Keycloak — the backend never stores a password or owns a session itself. Every API request carries a JWT that Keycloak issued; `require_admin` (`backend/app/core/auth.py`) checks that JWT's `realm_access.roles` claim for the `admin` role and nothing else. This is the right boundary, but it means **onboarding a teammate or granting admin access happens in Keycloak's own console, not in EAIStack's UI.**

## Getting to the Keycloak admin console

If you're logged into EAIStack as an admin, the fastest path is the **"User Management"** link in the main navigation bar (next to Settings, Dashboard, and Audit Log) — it opens Keycloak's admin console for this deployment's realm in a new tab. It's only visible to admins, same as the other admin-only nav entries.

If you don't have that link yet, or you're setting up Keycloak for the first time:

- **Local dev / `docker-compose up`**: the admin console is at [http://localhost:8080](http://localhost:8080). Log in with the seeded admin credentials — `admin` / `admin` (see `docker-compose.yml`'s `KEYCLOAK_ADMIN`/`KEYCLOAK_ADMIN_PASSWORD`). This is a Keycloak **master-realm** admin login, separate from any EAIStack user account.
- **A real deployment (Helm/K8s)**: the URL depends on how your fork exposed Keycloak (`infra/helm/charts/keycloak`'s `externalHostname` value). Ask whoever installed the chart, or check that chart's `values.yaml`.

Once logged in, switch from the `master` realm (top-left realm selector) to the **`eaistack`** realm — that's where this application's users and roles live, not `master`.

## Creating a user

1. In the Keycloak admin console, with the `eaistack` realm selected, go to **Users** (left sidebar) → **Add user**.
2. Fill in username and email (email verification isn't enforced by this template's realm config, but fill it in for real deployments).
3. Save, then go to the new user's **Credentials** tab → **Set password**. Untick "Temporary" if you don't want to force a password change on first login.
4. The user can now log into EAIStack's frontend with that username/password — they'll land with ordinary (non-admin) access.

## Granting or removing the `admin` role

EAIStack has exactly one realm role that matters to it: `admin`. Anyone without it gets ordinary user access; anyone with it can see the Settings, Dashboard, Audit Log, and User Management nav entries and call the endpoints behind `require_admin`.

1. **Users** → select the user → **Role mapping** tab.
2. **Assign role** → find `admin` in the list (filter by realm roles, not client roles) → **Assign**.
3. To remove it: same tab, select the `admin` role row → **Unassign**.

The change takes effect on that user's **next login or token refresh** — an already-issued JWT keeps whatever roles it was minted with until it's refreshed, so don't expect a role change to apply to an already-open browser tab instantly.

## Disabling vs. deleting a user

These are different actions with different consequences for that user's EAIStack data:

- **Disable** (**Users** → select user → toggle **Enabled** off, or the **Details** tab depending on Keycloak version): the account can no longer log in or refresh a token, but nothing in EAIStack is touched. Their conversation threads, API keys, and any other data they created remain exactly as they were — EAIStack's own [retention policy](SECURITY.md#data-retention-policy) is the only thing that will eventually purge that data, on its own configured schedule (or never, if retention is set to "keep forever"). Disabling someone in Keycloak does **not** trigger EAIStack's logout-triggered cleanup, because there is no logout event — the session simply can't be renewed going forward.
- **Delete** (**Users** → select user → **Delete**): permanently removes the Keycloak identity. This does **not** cascade-delete anything in EAIStack's own database — see [docs/REPOSITORY_PATTERN.md](REPOSITORY_PATTERN.md)'s user-isolation model: every EAIStack row (threads, API keys) is scoped by `user_id`, a plain string copied from the JWT's `sub` claim at the time it was created. Deleting the Keycloak user leaves those rows in place, now "orphaned" from any Keycloak identity, until EAIStack's retention sweep purges them on its own schedule.

**In short: neither disabling nor deleting a Keycloak user is a substitute for EAIStack's retention policy, and neither immediately purges that user's data.** If you need a former teammate's EAIStack data gone immediately, that's a retention/manual-purge question — see `docs/SECURITY.md`'s retention table — not something disabling or deleting their Keycloak account accomplishes by itself.

## Seeing who did what: Keycloak's Admin and Login Events

This deployment's realm ships with Keycloak's own event logging turned on by default (`infra/keycloak/realm-import.json`'s `eventsEnabled`/`adminEventsEnabled`/`adminEventsDetailsEnabled`, and the matching block in the Helm chart's realm-import ConfigMap) — no extra setup needed on a fresh install.

- **Admin Events** (who created/disabled/deleted a user, who assigned/removed a role, and when): **Realm Settings** → **Events** tab → **Admin events**. Requires **Save events** to be on in that same tab's config (already enabled by this realm's default config) to actually retain history rather than just live-tailing.
- **Login Events** (successful/failed logins, logouts): same **Events** tab → **User events**.

These events live entirely in Keycloak's own store — they are **not** part of EAIStack's `audit_logs` table or its in-app Audit Log screen (`docs/AUDIT_EVENTS.md`). If you need to correlate "an admin disabled a user" with an EAIStack config change (e.g. a retention window edit) that happened around the same time, you currently have to check both consoles separately. Surfacing Keycloak's events inside EAIStack's own Audit Log screen was considered and filed as a follow-up ([issue #63](../../../issues/63)) rather than built now.

## Why there's no in-app user editor

An earlier version of this plan considered building a full in-app user list/role-editor — listing users, toggling roles, disabling/deleting, all from inside EAIStack's UI. That would require granting the backend's Keycloak service account (`eaistack-api`) the `manage-users` realm-management role: a meaningfully larger trust surface than "verify a JWT," and it would duplicate an audit capability (who changed a user's role, when) that Keycloak's own Admin Events already provide for free once turned on. Given EAIStack's stated architectural boundary — identity and authorization are Keycloak's job, not the backend's — the deep link plus documentation was judged the right scope, matching this issue's own stated minimum bar. If a fork's operational needs later justify the in-app editor, it deserves its own issue and its own look at that trust-surface trade-off at that time.
