# GitHub Actions、PR 和 trigger 关联

## 何时解析远端链接

先检查用户提供的本地运行记录、日志目录、本地源码路径和显式 commit。只要本地信息已经能定位本轮日志并确定 XiangShan commit，就直接使用本地信息，不请求 GitHub API，也不解析同时给出的 PR、trigger 或 Actions run 链接。

运行目录名常同时携带归档日期、短 commit 和配置。例如：

```text
/nfs/home/cirunner/perf-report/cr260917-c8d7b3a5c-DefaultConfig
```

该路径既是应优先检查的本地运行记录目录，也给出候选短 commit `c8d7b3a5c`。从用户指定仓库或默认的 `https://github.com/OpenXiangShan/XiangShan.git` 准备源码后，将短 commit 解析为唯一完整 commit 并记录。如果目录名没有 commit，或者没有提供本地日志目录，才解析远端链接以补齐对应缺失项。

## 链接解析目标

确实需要解析 PR 或 trigger 链接时，至少提取：仓库、workflow 名称、run `id`、`run_number`、触发事件、分支、`head_sha`、提交信息、运行状态、失败 job、artifact 名称和日志下载状态。优先使用 API 结构化字段，不从网页标题猜测 commit。

## 入口类型

- PR URL：`https://github.com/<owner>/<repo>/pull/<number>`。先查询 PR 的最新 `head.sha`，再按该 SHA 查 Actions；旧 SHA 的成功或失败不能代表当前 PR。
- trigger/run URL：`https://github.com/<owner>/<repo>/actions/runs/<run_id>`。URL 中数字是 run `id`，可直接查询 run、jobs 和 artifacts。

## API 查询模板

```text
https://api.github.com/repos/<owner>/<repo>/pulls/<pr_number>
https://api.github.com/repos/<owner>/<repo>/actions/runs?head_sha=<head_sha>&per_page=100
https://api.github.com/repos/OpenXiangShan/XiangShan/actions/runs/<run_id>
https://api.github.com/repos/OpenXiangShan/XiangShan/actions/runs/<run_id>/jobs?per_page=100
https://api.github.com/repos/OpenXiangShan/XiangShan/actions/runs/<run_id>/artifacts?per_page=100
```

通过当前环境允许的网络访问方式请求 GitHub API。把响应写入任务临时目录或用户指定的输出目录，不假设固定的系统临时路径：

```bash
API_OUTPUT_DIR=/path/to/task-temporary-output
curl --fail --silent --show-error -L \
  "https://api.github.com/repos/OpenXiangShan/XiangShan/actions/runs/<run_id>" \
  -o "$API_OUTPUT_DIR/run-<run_id>.json"
```

若 API 返回 401/403，记录为认证或权限问题；不能把它解释成 workflow 没有日志。artifact 下载还可能受 token、过期时间或仓库权限影响。

## 字段和本地映射

`id` 用于 Actions URL、run/jobs/artifacts API；`run_number` 常用于 PR EMU 本地归档目录。两者不能互换。对 Weekly SPEC/perf-report，使用 `head_sha` 的短 SHA、运行日期和配置名关联 `cr<date>-<sha>-<config>`，不要强行套用 `run_number`。

PR 页面可能有多个 workflow 和 rerun。只保留 `head_sha` 匹配当前 PR head 的运行，再按 workflow 名称、事件、创建时间和 attempt 选择当前结果。对每个 run 查询 `/jobs`，记录失败、取消、跳过和仍在运行的 job 以及首个失败 step。

## 可用归档关联

CI job 名称、workflow 和归档目录名不一定一一对应。归档根目录必须由用户、CI 配置、挂载信息或任务上下文提供，不能写死或从另一环境猜测。用 `head_sha`、workflow、`run_number`、配置、benchmark 和 checkpoint 交叉匹配。归档目录为空时分别标注“产物缺失”和“远端 job 状态”，不要把二者互相推导。

归档通常按测试名保存。先只读列目录或成员，再按需读取：

```bash
tar -tzf /path/to/test.tar.gz
tar -xOzf /path/to/test.tar.gz stdout.log
tar -xOzf /path/to/test.tar.gz stderr.log
tar --zstd -tf /path/to/test.tar.zst
```

GitHub job log/artifact API 返回 `401/403/404` 时，记录认证、权限或过期状态，然后转向当前任务可访问的归档；这不表示 workflow 或测试本身成功/失败。
