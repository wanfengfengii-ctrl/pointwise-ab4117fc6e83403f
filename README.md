# 澄浦涂布试验室双探头配对分析

白班计量员将左右台架的厚度读数入册。质检员用同批原号编制配对，核算探头偏差，并在发现误配或误读时发布更正。夜班按正式报告号核对配对、读数、缺测位置和均差。

## 运行

使用 Python 3.11 标准库。完整回归由项目运行环境提供的校验入口启动。

```sh
python3 -B check_project.py
python3 -B demo.py
```

演示使用隔离的临时目录导入 `samples/trial.json`。第一对得到 3 微米后，质检员按 `samples/correction.json` 发布第二版并受理新任务。演示完成两份任务、签发报告、重开并按号领取。R1 的差值为 3 和 1，均差为 2 微米。R2 的差值为 3 和 −4，均差为 −1/2 微米。演示会核对实际分析和领取结果，再输出两份报告的摘要。

## 公开接口

`demo.open_lab(directory)` 将组件组装为一个运行实例。运行目录须可写。建议同一运行目录同一时段由一个实例持有，实例内可以由多个线程调用发布和受理。独立运行需要分别选择目录。

| 操作 | Python 接口 | 返回值与错误 |
| --- | --- | --- |
| 入册 | `lab.importer.import_batch(trial_id, side, rows)` | 返回 `TrialBatch`，其 `references` 为原样本引用。重复键或无效输入触发 `ValueError`，整次输入撤销。 |
| 发布 | `lab.revisions.publish(trial_id, pairs)` 或 `lab.revisions.publish(trial_id, amendment=edit)` | 返回该批的发布号 `R1`、`R2` 等。无效候选、过期父修订或提交错误触发 `PublicationError`。 |
| 受理 | `lab.admission.admit(trial_id)` | 返回任务号。无当前修订或无法取得其完整证据时触发 `AdmissionError`。 |
| 推进 | `lab.jobs.advance(job_id, batch_size)` | 返回本批明细、已处理数量、配对总数和完成标志。未知任务触发 `KeyError`，非法批量触发 `ValueError`。证据读取失败时保留此前进度。 |
| 签发 | `lab.reports.issue(job_id)` | 返回含 `report_id`、任务、批号及修订的 `IssueReceipt`。未知或未完成任务、核账或提交失败触发 `IssueError`。 |
| 领取 | `lab.reports.read(report_id)` | 返回固定的 `ReportDetail`。未知报告号触发 `KeyError`。 |

导入行用 `original_id`、`value` 和 `unit` 表达，侧别为 `left` 或 `right`。具值记录可使用十进制字符串或整数。单位接受 `mm`、`um`、`µm` 和 `μm`。显式缺测使用 `value=None`，可以带合法单位。不同侧及不同批的同名原号相互独立。每次导入至少一行。

`PairSpec(pair_id, left_key, right_key)` 引用该批登记的 `SampleKey(trial_id, side, original_id)`。一个样本可用于多个具名配对。`NamedAmendment(name, parent_revision, pairs=(), readings=())` 按配对号合并配对编辑，并可带 `ReadingChange(key, value, unit)`。同一份更正至少包含一项编辑。有效读数更正随新修订保留，原入册读数仍可按原键查询。

## 分析与保存

每个配对按标识符字序处理。差值为左侧微米值减右侧微米值。使用 `Fraction` 保存有效读数、差值与均差。任一侧缺测时保留两侧原号、已知读数和缺测位置，该对在报告中差值为空且不占均差分母。合法零读数和零差值照常计算。没有有效对时均差为空。

入册、配对目录和正式报告分别由 SQLite 保存。样本页以槽位和代次保存在运行目录，已受理任务持有完成所需的页，完成后释放。后续受理可以立即取得更正版。签发先按完成明细复算并核对，再在一个事务中写入正文和回执。成功后按号领取原正文。

初始化创建缺失的存储结构，并从已提交目录恢复当前页归属。重复初始化保留原样本、已发布更正和报告。任务调度与未完成进度存在当前运行实例内，关停前可完成当班在途任务。完整回归覆盖单位和入册、分批与缺测、无效更正、证据不可读、修订交接、报告重读与事务回滚。
