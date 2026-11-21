#!/usr/bin/env node
"use strict";
// No shell, no downloads, and no automatic installation of unverified code.
// This is a candidate npm launcher; the signed Python companion remains required.
const {spawnSync} = require("node:child_process");
const args = process.argv.slice(2);
const candidates = process.platform === "win32"
  ? [["py", ["-3"]], ["python", []]]
  : [["python3", []], ["python", []]];
for (const [executable, prefix] of candidates) {
  const result = spawnSync(executable, [...prefix, "-m", "agent_notifier", ...args], {
    stdio: "inherit", shell: false, windowsHide: true
  });
  if (result.error && result.error.code === "ENOENT") continue;
  if (result.error) {
    process.stderr.write("Agent Notifiers failed to launch Python: " + result.error.message + "\n");
    process.exitCode = 1; break;
  }
  if (result.status !== 0) {
    process.stderr.write("\nThis npm launcher requires the reviewed Agent Notifiers Python companion.\n");
    process.stderr.write("Install the official Python distribution when it is published, or install from the trusted repository.\n");
  }
  process.exitCode = result.status === null ? 1 : result.status;
  break;
}
if (process.exitCode === undefined) {
  process.stderr.write("Python 3 was not found. Install Python, then the verified Agent Notifiers companion.\n");
  process.exitCode = 1;
}
