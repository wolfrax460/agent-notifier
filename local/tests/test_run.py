import json, os, sys, tempfile

os.environ["AGENT_NOTIFIER_HOME"] = tempfile.mkdtemp()
from agent_notifier import cli, hooks, state
from agent_notifier.config import Settings

sent = []
cli.notify = lambda message, title="Claude", priority="normal", channels=None, settings=None: sent.append((title, priority, message)) or {"sent": ["x"]}
hooks.notify = cli.notify
PY = sys.executable


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        raise SystemExit(1)


# run: success, failure, fast-skip, missing command, args never leaked
rc = cli.main(["run", "--title", "build", "--", PY, "-c", "pass"])
ok(rc == 0 and sent[-1][0] == "build finished" and sent[-1][1] == "normal", "run success -> normal ping")
rc = cli.main(["run", "--", PY, "-c", "import sys; sys.exit(3)", "SECRET_KEY_123"])
ok(rc == 3 and sent[-1][1] == "high" and "FAILED" in sent[-1][0] and "3" in sent[-1][2], "run failure -> high ping with exit code")
ok("SECRET_KEY_123" not in json.dumps(sent), "command arguments never sent")
n = len(sent)
cli.main(["run", "--min-seconds", "60", "--", PY, "-c", "pass"])
ok(len(sent) == n, "fast success skipped with --min-seconds")
n = len(sent)
cli.main(["run", "--min-seconds", "60", "--", PY, "-c", "import sys; sys.exit(1)"])
ok(len(sent) == n + 1, "failure always notifies")
ok(cli.main(["run", "--", "definitely-not-a-command-xyz"]) == 127, "missing command -> 127, no crash")
ok(cli.main(["run"]) == 2, "no command -> usage error")

# codex-notify
state.save({}); n = len(sent)
payload = json.dumps({"type": "agent-turn-complete", "turn-id": "t1", "last-assistant-message": "All tests pass.", "input-messages": ["x"]})
ok(cli.main(["codex-notify", payload]) == 0 and len(sent) == n + 1 and "All tests pass." in sent[-1][2], "codex-notify sends summary")
cli.main(["codex-notify", payload])
ok(len(sent) == n + 1, "codex-notify debounced")
state.save({}); n = len(sent)
cli.main(["codex-notify", json.dumps({"type": "something-else"})])
ok(len(sent) == n, "other event types ignored")
ok(cli.main(["codex-notify", "{not json"]) == 0, "bad JSON never fails the agent")
print("RUN_TESTS_PASSED")
