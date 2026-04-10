# FpgaDiff Playground Guidelines

Before doing anything in this repository, read [`docs/README.md`](docs/README.md).

For complex debugging or multi-step FPGA work, follow [`docs/debug-workflow.md`](docs/debug-workflow.md): create a job directory under `jobs/`, write the plan, and keep a progress log there.

## Mandatory Environment Rules

Match the current environment. If multiple conditions apply, obey all of them.

### 1. VSCode Copilot

If running in VSCode Copilot, the following rules are mandatory:

- You must use `#askUser`, `#askQuestions`, `vscode_askQuestions` or `ask_user` at the end of every step, every reply, every task, and every return.
- Use this priority: `#askUser` > `#askQuestions` > `ask_user`.
- Never assume the task is finished without asking for confirmation or next action.
- Every response must end with an actual ask tool/plugin call. Do not end with any additional plain text.
- For long-running or background tasks, you must keep monitoring progress and final status. Do not just start the task and stop tracking it. This especially applies to Vivado runs, bitstream generation, long simulations, and other FPGA build/debug flows.

#### VSCode Copilot Terminal Rules

These rules are strict:

- Never run interactive commands.
- Assume the program is non-interactive unless the task explicitly requires human input.
- Do not ask the user for input while a command is running unless the task explicitly requires it.
- Do not mistake normal program output for an input request.
- Do not treat `:`, `password:`, `input:`, `select`, or similar text as proof that stdin is required.
- Always append `; echo ""` to every command so the output ends with a newline.
- Prefer `bash`. Avoid shells, prompts, or themes that may break command-finish detection.
- For long commands, write logs to a file and still append a newline:
  `command 2>&1 | tee /tmp/agent.log ; echo ""`
- Save files before running commands that depend on them.
- Do not leave commands hanging indefinitely.
- Do not start commands that may silently block or wait for confirmation.

### 2. Plan / Walkthrough Tools (Provided by Seamless Agent)

If `#planView` or `#planReview` is available:

- For any multi-step task, non-trivial change, FPGA build/debug flow, or long-running operation, you must show a plan first and wait for approval before executing.
- If the plan is rejected, revise it and submit again with the same plan tool.
- Do not execute first and explain later.

If `#walkthroughView` or `#walkthroughReview` is available:

- When the user asks for step-by-step guidance, you must present it with the walkthrough tool.

### 3. Notification and Job Log

If a notification script path is provided, you must use it.

- Before every call to `ask_user`, send a notification with the notify script first.
- Before every long-running task, send a notification.
- After every long-running task, send a notification.
- When the entire task is completed, send a final notification, even if long-running task notifications were already sent.
- The notification must include task status and conclusion.
- The final conclusion must be written into the corresponding file under `jobs/`.
- Do not finish any task without recording the result in `jobs/` and sending the final notification.

Example:
`sh "<notify_script_path>" "<content>" ; echo ""`

## Execution Order

Follow this order:

1. safe, non-interactive execution
2. send notification before calling `ask_user` if a script path is provided
3. required confirmation tool (`#askUser` / `#askQuestions` / `ask_user`)
4. required plan tool for multi-step work
5. required walkthrough tool for guided explanations
6. monitor long-running tasks until completion
7. write result and conclusion to `jobs/`
8. send notification if a script path is provided
