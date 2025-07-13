Website Template
---

A website template based on [Piccolo](https://github.com/piccolo-orm/piccolo) with [Litestar](https://litestar.dev/).

Features:
- Authentication
- Test setup
- [Tabler](https://tabler.io/admin-template) based CSS
- CSP on templates
- Secrets management via [Infisical](https://infisical.com/)
- Logging via [OpenObserve](https://openobserve.ai/)

### Usage

#### Quick Start Guide

1. `git clone https://github.com/Skelmis/Template-Website.git website_template`
2. `cd website_template`
3. Modify `DISABLE_AUTH: false` to `DISABLE_AUTH: true` in the `docker-compose-dev.yml` file if you don't want to have to create an account.
4. `docker compose -f ./docker-compose-dev.yml up`
5. Navigate to http://127.0.0.1:8800 and you are good to go.

#### Configuration Options

These are environment variables by default. If `(Infisical)` is shown, then they should be set in the secrets manager,

##### Required
*These must be set for the application to function*

- `CSRF_TOKEN` (Infisical): The token to use as the CSRF secret.
- `SESSION_KEY` (Infisical): Must have a length of 16 (128 bits), 24 (192 bits) or 32 (256 bits) characters. Stored as hex.
- `LOGOO_STREAM` (Infisical): OpenObserve logging stream.
- `LOGOO_USER` (Infisical): OpenObserve username.
- `LOGOO_PASSWORD` (Infisical): OpenObserve password.
- `POSTGRES_DB`: The Postgres database to use.
- `POSTGRES_USER`: The Postgres user to auth as.
- `POSTGRES_PASSWORD`: The password for said Postgres user.
- `POSTGRES_HOST`: The host Postgres is running on.
- `POSTGRES_PORT`: The port for Postgres.
- `REDIS_URL`: The URL to use when attempting to connect to Redis.
- `SERVING_DOMAIN`: The domain this site will run on. Used for cookies etc.

##### Optional
*These are optional feature flags to provide*

- `DEBUG`: If set to a truthy value, dump tracebacks etc on error. Defaults to `false`
- `ALLOW_REGISTRATION`: Whether to let user's self sign up for accounts on the platform. Defaults to `true`. If you want to disable this, set it to `false`.
- `DISABLE_HIBP`: If set to a truthy value, bypass the Have I Been Pwned checks on passwords. Defaults to `false`.
- `MAKE_FIRST_USER_ADMIN`: If truthy, makes the first user created admin. Just simplifies things. Defaults to `true`

#### Deployment Hardening

While efforts have been taken to secure this application, nothing is perfect.

It is recommended that if you do wish to deploy this outside of locally that the following conditions are met:
- Ensure debug mode is not enabled
- Disable user sign up (`ALLOW_REGISTRATION=false`)
- Ensure platform users are considered relatively trusted
- Set strong passwords for Postgres and Redis as well as ensuring they are only exposed to the local network
- Set a strong CSRF token and session key

If you encounter security issues when deploying in environments that meet the above expectations I'd love to hear about it! When doing so please follow the security policy located [here](https://data.skelmis.co.nz/.well-known/security.txt) or the more user-friendly version [here](https://data.skelmis.co.nz/disclosure-policy).

### Feature Set Tuning

_This project is catered to my tech stack. Here are some common gotchas you may encounter_

#### I don't run Logoo / OpenObserve

You'll have to download the template, run `uv remove logoo` and then rip all the logging out.

#### I don't use Infisical

Grep for `get_secret` and replace them all with your equivalent.

Please don't hard code them.

### Development

#### Local Dev Env

Good commands for development usage:
- `docker compose -f ./docker-compose-dev.yml up template_saq template_redis template_db`
- `docker compose -f ./docker-compose-dev.yml up --build template_saq template_redis template_db`

And then run `uv main.py`

In order to do DB migrations run the following. DB must be up to do so.
- `make_migrations.sh`
- `migrate.sh`