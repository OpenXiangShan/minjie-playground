# GitHub Actions, PRs, and Triggers

Inspect local logs, source metadata, and explicit commits first. If they identify the failure and source
commit, do not query GitHub merely because a PR or Actions URL is also present. Fetch XiangShan source from
the confirmed official repository.

When a remote lookup is necessary, extract structured fields rather than guessing from page titles:
repository, workflow, run `id`, `run_number`, event, branch, `head_sha`, commit message, status, failed
jobs and steps, artifacts, and download status.

Useful API endpoints include:

```text
https://api.github.com/repos/<owner>/<repo>/pulls/<number>
https://api.github.com/repos/<owner>/<repo>/actions/runs?head_sha=<sha>&per_page=100
https://api.github.com/repos/<owner>/<repo>/actions/runs/<run_id>
https://api.github.com/repos/<owner>/<repo>/actions/runs/<run_id>/jobs?per_page=100
https://api.github.com/repos/<owner>/<repo>/actions/runs/<run_id>/artifacts?per_page=100
```

For a PR, resolve the current `head.sha` before selecting a run; an older SHA or rerun may not represent
the current PR. Match workflow, event, creation time, and attempt; record failed, cancelled, skipped, and
running jobs and the first failed step. `id` identifies the API run, while `run_number` often identifies a
local archive. Do not interchange them. A `401`, `403`, or `404` indicates an authentication, permission,
or retention issue, not a test result.

Performance archives named `cr<date>-<sha>-<config>` use the date, short commit, and configuration rather
than `run_number`. Resolve a short commit uniquely in the source repository before using it.

Inspect local archives read-only, for example with `tar -tzf`, `tar -xOzf`, or `tar --zstd -tf`. Match
`head_sha`, workflow, event, configuration, benchmark, and checkpoint before associating an artifact.
