# agent-notifiers npm launcher (unpublished)

This is a **candidate** npm launcher, not a public installer yet.
It forwards `agent-notifiers ...` to `python -m agent_notifier ...` without
starting a shell or downloading executable code. The trusted Python companion
must be installed separately (from a reviewed source release or a future
verified `agent-notifiers` PyPI release).

The name and publisher must be verified on the npm registry before changing
`"private": true` and using an account with publish permission.
The resulting npm package is only a launcher, not a full Python or Windows
installer. No automatic network downloads occur.

## Development check

```sh
node --check bin/agent-notifiers.cjs
node bin/agent-notifiers.cjs --help
npm pack --dry-run
```
