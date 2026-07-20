# cr-agent 评测报告

## 总览

- 样本总数：**26**
- 综合得分 composite_avg：**0.8628**
- 硬指标 PRF：precision=0.0858 / recall=0.8077 / f1=0.1537
- Token 用量：prompt=46724 / completion=223901 / total=270625 / calls=125

## 分类明细

| 类别 | 样本数 | composite | completeness | accuracy | source | PRF-f1 |
|------|--------|-----------|--------------|----------|--------|--------|
| security | 7 | 0.94 | 1.0 | 0.8571 | 0.9857 | 0.146 |
| quality | 7 | 0.8903 | 0.9429 | 0.8329 | 0.9 | 0.2228 |
| performance | 6 | 0.76 | 0.8167 | 0.6583 | 0.85 | 0.1455 |
| structure | 6 | 0.8433 | 0.9833 | 0.8417 | 0.5667 | 0.09 |

## 每条样本

### sec-001（security）— composite=1.0 / PRF-f1=0.1667

- completeness=1.0 / accuracy=1.0 / source=1.0
- 裁判理由：实际报告完全识别了期望的硬编码密钥问题，并准确标注了行号。它额外发现了更多问题，但核心发现与期望一致，无漏报、无错误、无行号错误。

### sec-002（security）— composite=1.0 / PRF-f1=0.1667

- completeness=1.0 / accuracy=1.0 / source=1.0
- 裁判理由：实际报告准确识别了期望发现的SQL注入高危问题，描述正确且行号标注清晰，完全覆盖期望发现。

### sec-003（security）— composite=1.0 / PRF-f1=0.1667

- completeness=1.0 / accuracy=1.0 / source=1.0
- 裁判理由：实际报告在安全审查部分准确、完整地覆盖了期望发现的核心问题（eval执行不可信输入），并提供了精确的行号追溯。报告中的其他发现虽超出期望范围，但并未影响对期望项的评价。

### sec-004（security）— composite=0.94 / PRF-f1=0.2222

- completeness=1.0 / accuracy=0.9 / source=0.9
- 裁判理由：实际报告完全覆盖了期望发现的命令注入问题，但架构部分行号错误（标为3，应为4），且来源标注虽有行号但存在不准确之处。

### sec-005（security）— composite=0.96 / PRF-f1=0.1333

- completeness=1.0 / accuracy=0.9 / source=1.0
- 裁判理由：实际报告完全覆盖了期望发现的MD5弱哈希问题，并添加了相关建议；但严重度标注为'高危'，与期望的'中危'不一致；行号和来源标注清晰，便于追溯。

### sec-006（security）— composite=0.88 / PRF-f1=0.0

- completeness=1.0 / accuracy=0.7 / source=1.0
- 裁判理由：实际报告覆盖了期望发现的安全问题（verify=False的中间人攻击风险），但严重度标记错误（高危而非中危）且行号不匹配（行3而非行4），影响准确性；所有问题均标注行号，追溯性良好。

### sec-007（security）— composite=0.8 / PRF-f1=0.1667

- completeness=1.0 / accuracy=0.5 / source=1.0
- 裁判理由：实际报告完整覆盖了期望发现的问题（硬编码 API 密钥），且所有问题都标注了行号和来源；但报告在多个维度重复报告同一问题，且部分分类不正确（如将安全问题归为性能或架构问题），导致准确性降低。

### q-001（quality）— composite=0.98 / PRF-f1=0.25

- completeness=1.0 / accuracy=1.0 / source=0.9
- 裁判理由：实际报告完全覆盖了期望发现中'函数过长需拆分'的核心问题（体现在架构维度的单一职责原则违反中），且所有问题描述准确无幻觉。大部分问题标注了具体行号，仅少数标注为'None'，来源可追溯性良好。

### q-002（quality）— composite=0.92 / PRF-f1=0.1429

- completeness=1.0 / accuracy=0.8 / source=1.0
- 裁判理由：实际报告完全覆盖了期望发现的魔法数字问题，并在架构部分正确标注行号2，但错误地将该问题归类为structure（期望为quality），导致准确性扣分。

### q-003（quality）— composite=0.76 / PRF-f1=0.3333

- completeness=0.6 / accuracy=0.8 / source=1.0
- 裁判理由：实际报告部分覆盖了变量命名问题，但只针对 d, tmp, xx，漏掉了 a, b, c 的命名；变量命名严重度被错误地标记为中危，而期望为低危；报告提供了行号，便于追溯。

### q-004（quality）— composite=0.94 / PRF-f1=0.1667

- completeness=1.0 / accuracy=0.95 / source=0.8
- 裁判理由：期望发现（重复代码问题）被实际报告完全覆盖，描述和severity匹配；但行号未指定为期望的line 1，导致轻微准确性偏差；实际报告标注了行号（部分为'None'），但为重复代码问题提供清晰描述，追溯性尚可。

### q-005（quality）— composite=0.8 / PRF-f1=0.2222

- completeness=1.0 / accuracy=0.5 / source=1.0
- 裁判理由：实际报告完全覆盖了期望发现的问题（空 except 吞掉异常），并正确标注了行号4，但将严重度从期望的medium错误地评为高危，影响了准确性。

### q-006（quality）— composite=0.912 / PRF-f1=0.2222

- completeness=1.0 / accuracy=0.98 / source=0.6
- 裁判理由：实际报告完全覆盖了期望发现的‘深度嵌套if’问题（在quality和structure两个维度均有提及），并额外发现了死代码、输入校验等多个正确的问题，因此completeness为1.00。报告中绝大部分技术描述正确，仅将‘dead code’（逻辑冗余）标记为‘高危’（🔴）而非更常见的‘低/中危’或‘信息’级别，与通常的质量严重度分级有轻微偏差，因此accuracy略低于1.00。报告为多数问题指定了‘None’行号或模糊的描述，只有部分标注了具体行号（如line 1, line 8），降低了问题定位的精确性，因此source_traceability较低。

### q-007（quality）— composite=0.92 / PRF-f1=0.2222

- completeness=1.0 / accuracy=0.8 / source=1.0
- 裁判理由：实际报告完全覆盖了期望发现的问题（变量和函数命名不清晰），但严重度评估不准确（中危 vs 低危），来源标注清晰且一致。

### p-001（performance）— composite=1.0 / PRF-f1=0.2222

- completeness=1.0 / accuracy=1.0 / source=1.0
- 裁判理由：实际报告完全覆盖了期望发现的N+1查询性能问题，严重度、描述和建议均准确匹配，行号标注清晰，无漏报或错误。

### p-002（performance）— composite=0.84 / PRF-f1=0.1429

- completeness=1.0 / accuracy=0.75 / source=0.7
- 裁判理由：实际报告完整覆盖了期望发现的性能问题（全表加载），但相关条目中行号缺失和严重度/类别不匹配（如高危/结构）影响准确性，且来源行号标注不完整（部分为None）。

### p-003（performance）— composite=0.8 / PRF-f1=0.0

- completeness=1.0 / accuracy=0.5 / source=1.0
- 裁判理由：实际报告覆盖了期望的性能问题并给出了正确建议，但严重度（高危 vs 中危）和行号（4 vs 3）与期望发现不匹配，且标注了详细来源便于追溯。

### p-004（performance）— composite=0.9 / PRF-f1=0.2222

- completeness=1.0 / accuracy=0.8 / source=0.9
- 裁判理由：实际报告完全覆盖了期望发现的问题，但将其严重度从medium提升到high，并在分类上混淆performance与quality，导致准确性受损；来源标注基本正确，行号在多数条目中匹配，但存在不一致之处。

### p-005（performance）— composite=0.44 / PRF-f1=0.2857

- completeness=0.4 / accuracy=0.2 / source=1.0
- 裁判理由：实际报告提及了line 4的性能问题，但未准确描述'锁竞争'关键点，严重度从low误判为中危，来源标注清晰。

### p-006（performance）— composite=0.58 / PRF-f1=0.0

- completeness=0.5 / accuracy=0.7 / source=0.5
- 裁判理由：实际报告覆盖了性能问题但描述和严重度不匹配；报告本身正确但严重度估计过高、行号不精确；行号标注部分缺失，且性能问题行号与期望不符。

### st-001（structure）— composite=0.98 / PRF-f1=0.1

- completeness=1.0 / accuracy=0.95 / source=1.0
- 裁判理由：实际报告完全覆盖了期望发现的上帝函数问题，并准确标注了行号；其他审查问题基于代码片段合理推断，无明显错误，但部分推测（如SQL注入）依赖假设，准确性略减。

### st-002（structure）— composite=0.92 / PRF-f1=0.125

- completeness=1.0 / accuracy=0.8 / source=1.0
- 裁判理由：实际报告完全覆盖了期望发现（单一职责问题），但将严重度从期望的medium错误标记为high，准确性受损；报告中行号标注清晰，便于追溯。

### st-003（structure）— composite=1.0 / PRF-f1=0.1818

- completeness=1.0 / accuracy=1.0 / source=1.0
- 裁判理由：实际报告完全覆盖并准确识别了期望发现的核心问题（依赖全局可变状态CONFIG导致的测试与并发挑战），并给出了具体的行号（第1行）与详尽的改进建议。报告虽提及更多维度的问题，但核心事实无误，无幻觉或严重度错误。

### st-004（structure）— composite=0.72 / PRF-f1=0.0

- completeness=0.9 / accuracy=0.8 / source=0.2
- 裁判理由：实际报告覆盖了循环依赖问题，但严重度误报为高危（期望中危），且未提供行号或代码片段，导致可追溯性不足。

### st-005（structure）— composite=0.7 / PRF-f1=0.0

- completeness=1.0 / accuracy=0.75 / source=0.0
- 裁判理由：实际报告发现了期望的上帝类问题，覆盖完全，但严重度评估错误（高危 vs medium），且未标注具体行号。

### st-006（structure）— composite=0.74 / PRF-f1=0.1333

- completeness=1.0 / accuracy=0.75 / source=0.2
- 裁判理由：实际报告识别了期望发现的核心问题（模块化缺失），但严重度评估偏高（中危 vs 低危）且未提供行号，降低了准确性和来源追溯性。
