# 双探头配对更正事故：根因与核验

## 现象

发布 R2 更正第二对右台架样本后，已受理的旧任务仍签作 R1，却出现
`[3, −4]`、均差 `−1/2`；正确结果应为 R1 `[3, 1]`、均差 `2`，第二对
`L2/R2a`。新任务应使用 R2 的 `[3, −4]` 与 `L2/R2b`。

## 根因

`analysis/jobs.py` 的 `JobStore.advance` 每次推进都用 `job.refresh()` 重新
读取批次**当前**修订的配对与证据，而不是沿用受理时捕获的
`PublishedInput`。于是：

- 旧任务在 R1 时已受理，推进到第二对时读到 R2 的 `P02 → L2/R2b`，
  算出 `8 − 12 = −4`；
- 结果行带着 R2 的配对与原号，但 `revision_id` 仍取受理时的 `R1`，
  于是 R1 报告被 R2 的读数污染，均差被算成 `−1/2`。

配套问题是 `specimens/retirement.py` 在发布时立即把旧页设为可回收并允许
复用其槽位，未考虑仍有已受理任务持有这些页，导致更正后旧任务的页可能
被提前删除或覆盖。

## 修复

1. `analysis/jobs.py`：任务在受理时绑定 `PublishedInput`（修订号、配对、
   证据租约），推进只读该快照；完成后才释放租约。更正后新任务立即受理
   并取 R2，旧任务继续用 R1 原版。
2. `specimens/evidence.py`：`EvidenceLease` 持有期间向 `PageRetirement`
   登记持有计数，`close()` 时归还。
3. `specimens/retirement.py`：新增 `hold`/`release` 和维护持有计数；
   `_reap_locked` 跳过仍被持有的页，`reuse_candidate` 不使用被持有页的槽位。
   最后一个持有任务完成后，旧页才按原规则回收，槽位回到原复用顺序。

其余接口、缺测与精确均差规则、报告格式、事务回滚及原测试均保持不变。

## 核验

```
python3 -B check_project.py   # 39 个测试全部通过（原 35 + 新 4）
python3 -B demo.py            # R1 [3, 1] mean=2；R2 [3, -4] mean=-1/2
python3 -B incident.py        # expected == actual，无 PAIR_REVISION_MIX
```

新增回归：

- `tests/test_incident.py::test_signed_reports_keep_their_own_revision`：
  运行完整事故对账，两版报告各自持有本修订。
- `tests/test_handover.py::test_accepted_revision_survives_later_publication`：
  任务先受理、后发布更正，旧任务仍签 R1。
- `tests/test_handover.py::test_accepted_job_reserves_slot_until_finished`：
  未推进的旧任务仍可读原页，槽位不被新修订复用。
- `tests/test_handover.py::test_failed_advance_keeps_lease_and_progress`：
  推进读页失败保留此前进度，租约不泄漏。
