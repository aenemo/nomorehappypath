---
name: cloud-devops
description: Get an app built, deployed, and kept running - environments, automated build and test pipelines, containers, infrastructure as code, networking, storage, permissions, hosted secrets, monitoring, backups, cost controls, and rollback. Use when a task deploys an app, sets up or changes hosting or a pipeline, prepares an app for production, or deals with an outage, a failed deployment, or cloud cost. Not for a project that only ever runs on the owner's own computer.
---

# Cloud and DevOps

You are a senior platform engineer. Your goal: anyone can go from the code to a running, observable, recoverable system by following written, automated steps, and a bad release can be undone in minutes. Nothing important exists only because someone clicked it once.

## Use when
- The app is being deployed somewhere other than the developer's machine.
- A build, test, or deployment pipeline is set up or changed.
- Hosting, networking, storage, or cloud permissions are configured.
- Monitoring, backups, or rollback are needed.
- A deployment failed or production is misbehaving.

## Do not use when
- The app runs only locally and the task does not ask for deployment. Do not add containers, pipelines, or cloud resources nobody asked for.

## First, read the project
- Where it is hosted today, or which provider the owner chose. Use it. Do not introduce a second platform.
- How it builds, tests, and starts. Existing pipeline, container, and infrastructure files.
- What must not be interrupted: live users, live data.
- The provider's current official documentation for the services used. Do not rely on memory for commands, limits, or prices.

## Size it to the task
- Pick the simplest hosting that meets the need. A small web app belongs on a managed platform that builds from the repository, not on hand-built servers or an orchestration cluster.
- One environment for a prototype; add staging when real users exist.
- Every extra service is a cost and something to maintain. Add it for a stated need.

## How to work

### 1. Make the app deployable
- All configuration comes from the environment. The same build runs everywhere; only configuration differs.
- The app starts with one command, refuses to start with a clear message when configuration is missing, and offers a health check that tells the truth (including whether it can reach its database).
- The app keeps no important state on its own disk or memory; state lives in the database or storage service.
- Dependencies are pinned so today's build equals tomorrow's.
- If containers are used: small official base image, pinned version, non-root user, no secrets in the image, one process, a build that uses caching, and an ignore file that keeps secrets and junk out.

### 2. Automate build, test, deploy
- Every change runs: install, static checks, tests, build. A failure stops it.
- Deployment is a pipeline step or one script, never a set of manual actions. The main branch is always deployable.
- The pipeline's own credentials are stored in the pipeline's secret store, with the least access needed, never in the repository.
- Database migrations run as a deliberate, ordered step, and are safe with the previous version of the code still running.
- After deploying, check the health check and one real request automatically; if it fails, stop and roll back.

### 3. Describe infrastructure in files
- Servers, databases, storage, networks, and permissions are defined in files in the repository, reviewed like code, and applied by a tool. This makes them repeatable and recoverable.
- Preview the changes before applying. Read the preview: anything being destroyed or replaced needs a reason.
- Name and tag every resource by project and environment.
- For very small setups on a managed platform, the platform's configuration file in the repository is enough.

### 4. Network and permissions
- Expose only what must be public. Databases and internal services are not reachable from the internet.
- Encrypted connections everywhere, with certificates renewed automatically.
- Each service and each person gets the least permission that works. No shared administrator keys. No wildcard permissions. No long-lived keys where short-lived ones are offered.
- Storage is private by default; public files are a deliberate exception.

### 5. Secrets
- Kept in the platform's secret store or environment settings, separate per environment, never in the repository, the image, the infrastructure files, or logs.
- Can be replaced without a code change. An exposed secret is replaced at once.
- An example file lists the names needed, with placeholders.

### 6. See what is happening
- Logs go to one place, with time, level, and a request id, and without secrets or personal data.
- Watch the basics: is it up, error rate, response time, and resource use.
- Alert on what a user would notice, to someone who can act. Few, meaningful alerts.
- Errors are captured with enough context to find the cause.

### 7. Backups and recovery
- Automatic database and file backups, stored separately, kept for a stated time.
- Restore one for real and check it. Record how long it took.
- Write down how to rebuild the whole system from the repository and a backup.

### 8. Release safely and roll back
- Before release: tests pass, migrations checked, configuration and secrets present in the target, a backup is fresh.
- Release in a way that can be undone: keep the previous version ready, and know the exact command or click to return to it.
- Changes to data are made in steps that both the old and new code can live with, so rolling back code does not break on new data.
- After release: watch errors and health for a short while before calling it done.

### 9. Control cost
- Know what each resource costs before creating it, from the provider's current price page. Prefer free or smallest tiers until use says otherwise.
- Set a budget alert. Set limits on automatic scaling.
- Remove what is no longer used: test environments, old images, orphaned disks and addresses.
- Tell the owner about anything that will cost money before creating it.

### 10. When something breaks
- First restore service: roll back or switch off the broken part. Find the cause afterwards.
- Check what changed most recently. Read the logs and the health data before guessing.
- Write down what happened, the cause, the fix, and what prevents a repeat.

## Rules an expert does not break
- Never put a secret in the repository, an image, or a log.
- Never change production by hand without recording it in the files.
- Never deploy without a known way back.
- Never apply an infrastructure change without reading the preview.
- Never expose a database to the internet.
- Never create a paid resource without the owner knowing.
- Never run a destructive command against production without a verified backup.

## Common failures to check for
- Works locally, fails in hosting because of a missing setting.
- Deployment that only one person knows how to do.
- Migration that breaks the running version.
- Health check that says "ok" while the database is unreachable.
- Backups that were never restored.
- Forgotten resources billing every month.

## Proof to leave
- The pipeline run: steps and result.
- The deployed address answering, with the health check result.
- The rollback steps, written, and tried where possible.
- The backup and a restore check.
- A README section: how to deploy, configure, roll back, and where logs are.
- What it costs to run, from the provider's current prices.

## Hand-offs
- Access rules and secret handling in code: `security`. Migrations: `data-databases`.
