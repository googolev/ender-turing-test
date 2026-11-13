# FastAPI Project - Development

## Local Development

For local development, run PostgreSQL and Mailpit with Docker Compose, and run the FastAPI and Vite development servers locally.

Start the supporting services:

```bash
docker compose up -d db mailpit
```

Then, from the `backend` directory, install the dependencies and prepare the database:

```bash
uv sync
uv run bash scripts/prestart.sh
```

Start the FastAPI development server:

```bash
uv run fastapi dev
```

In another terminal, from the project root, install the frontend dependencies and start the Vite development server:

```bash
bun install
bun run dev
```

Now you can open these URLs:

Frontend development server: <http://localhost:5173>

Backend API: <http://localhost:8000>

Automatic interactive API documentation with Swagger UI: <http://localhost:8000/docs>

Mailpit: <http://localhost:8025>

The frontend development server uses the backend at `http://localhost:8000`, as configured in `frontend/.env`.

### Frontend Served by FastAPI

Build the frontend from the `frontend` directory:

```bash
bun run build
```

The build is written to `backend/app/frontend` and served by FastAPI at <http://localhost:8000>. Rebuild the frontend after making frontend changes.

## Full Stack with Docker Compose

To run the backend and built frontend in Docker Compose:

```bash
docker compose run --rm backend bash scripts/prestart.sh
docker compose watch
```

Now you can open these URLs:

Application, with the frontend and API served by FastAPI: <http://localhost:8000>

Automatic interactive API documentation with Swagger UI: <http://localhost:8000/docs>

Adminer, database web administration: <http://localhost:8080>

Traefik UI, to see how the routes are being handled by the proxy: <http://localhost:8090>

Mailpit: <http://localhost:8025>

Stop a locally running FastAPI server before starting the Compose backend because both use port `8000`.

**Note**: The first time you start the stack, it might take a minute for all the services to be ready. To monitor it, use `docker compose logs`, or `docker compose logs backend` for the backend service.

## Roles and Access Control

Every user has one role: `admin`, `manager` or `member`. The backend derives permissions from the role, and every check is done by permission:

| Permission | admin | manager | member | Allows |
|---|---|---|---|---|
| `users:read` | ✓ | ✓ | | List users and view any user |
| `users:manage` | ✓ | | | Create, edit and delete users, change their role and active status, password recovery HTML |
| `metrics:read` | ✓ | ✓ | | `GET /api/v1/metrics/` and the Metrics page |
| `items:all` | ✓ | | | See and change other users' items |
| `system:manage` | ✓ | | | Operational tools such as the test email |

Everyone can view and edit their own profile and work with their own items. Signup always creates a `member`, and nobody can change their own role or active status.

- The rules live in one place, `backend/app/core/permissions.py`. To change an access rule, change `ROLE_PERMISSIONS` there.
- Endpoints declare what they need with `Depends(require_permission(Permission.X))` from `backend/app/api/deps.py`.
- `GET /api/v1/users/me` returns `role` and `permissions`. The frontend shows pages and controls by permission (`can(...)` in `useAuth`) and guards routes with `requirePermission(...)`. A user without access who opens a page by URL is redirected to the dashboard.
- The role and active status are read from the database on every request, so changes apply to sessions that already hold a token: a deactivated or deleted user gets `401` and is logged out, and a user who lost a permission gets `403` and stays logged in. When the current user's permissions change, the frontend re-runs its route guards, so a page the user can no longer open is left as soon as the user returns to the tab.

The migration `91ade4d27122` replaced `is_superuser` with `role`: existing superusers became admins and all other users became members, without changing `is_active`. The user created from `FIRST_SUPERUSER` is an admin.

### Try the Three Roles Locally

1. Log in with the `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD` from `.env`. This user is an admin.
2. On the **Users** page, use **Add User** to create a manager and a member: pick the role in the **Role** field and check **Is active?**.
3. Log in as each of them, for example in a private browser window, to see what their role allows. An admin can change any other user's role or active status with **Edit User** while that user is logged in.

## Mailpit

[Mailpit](https://mailpit.axllent.org) captures emails sent during local development instead of delivering them. The local backend connects to it at `localhost:1025`, and the Compose backend connects to the `mailpit` service. Captured emails are available at <http://localhost:8025>.

## Docker Compose Files and Environment Variables

The main `compose.yml` file contains the configuration shared by the whole stack. Docker Compose loads it automatically.

The `compose.override.yml` file adds local development settings, such as mounting the source code as a volume. Docker Compose also loads it automatically and applies it on top of `compose.yml`.

The `compose.deploy.yml` file contains the deployment-specific settings, including HTTPS and automatic certificate handling. It is explicitly combined with `compose.yml` when deploying the application.

The backend reads local settings from the `.env` file. Docker Compose also uses it for variable interpolation and passes the settings each container needs.

After changing variables, make sure you restart the stack:

```bash
docker compose watch
```

## The `.env` File

The tracked `.env` file contains local development defaults, passwords, and other configuration. Its hostnames use `localhost` for processes running on your machine. Docker Compose overrides hostnames such as the database and SMTP server with their Compose service names.

Do not store deployment secrets in `.env`. Configure them as described in the [FastAPI Cloud deployment guide](./deployment.md) or the [Docker Compose deployment guide](./deployment-docker-compose.md).

## Pre-commit Hooks and Code Linting

The project uses [prek](https://prek.j178.dev/), a modern alternative to [pre-commit](https://pre-commit.com/), for code linting and formatting.

You can find a file `.pre-commit-config.yaml` with configurations at the root of the project.

### Install `prek` to Run Automatically

`prek` is already part of the dependencies of the project.

From the project root, install the Git hook so that `prek` runs automatically before each commit:

```bash
uv run prek install -f
```

The `-f` flag forces the installation, in case there was already a `pre-commit` hook previously installed.

Now whenever you try to commit, for example with:

```bash
git commit
```

`prek` will check and format the code you are about to commit. If it modifies any files, add those files to Git again before committing.

### Run `prek` Manually

You can also run `prek` manually on all files from the project root:

```bash
uv run prek run --all-files
```
