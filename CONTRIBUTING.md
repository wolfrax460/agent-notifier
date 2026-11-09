# Contributing

Issues and pull requests are welcome.

```bash
# local tool
cd local && pip install -e . && python tests/test_local.py && python tests/test_run.py
# hosted service (needs mcp 2.x, use a separate virtualenv)
cd cloud && pip install -e . && python tests/test_cloud.py && python tests/test_admin.py
```

Rules: keep tests passing, add a test for new behaviour, never log message text or secrets, no new dependencies without a reason.
