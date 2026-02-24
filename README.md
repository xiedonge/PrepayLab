# PrepayLab
房贷提前还贷计算器

备注：已按请求添加说明。

## 网站版使用

直接打开 `index.html` 即可使用，或在本目录启动静态服务：

```bash
python3 -m http.server 8000
```

然后访问 `http://localhost:8000`。

## 命令行使用（可选）

```bash
python3 -m prepaylab.cli --input examples/sample_input.json --pretty
```

如需输出新的还款计划表：

```bash
python3 -m prepaylab.cli --input examples/sample_input.json --pretty --schedule
```

## 输入说明（JSON）

必填字段：
- `principal`：贷款总额（元）
- `annual_rate`：年利率（如 3.95 表示 3.95%）
- `term_months`：总期数（月）

常用字段：
- `repayment_type`：`"EPI"` 等额本息 / `"EP"` 等额本金
- `paid_months`：已还期数（整数）
- `prepay_type`：`"partial"` 部分提前还款 / `"full"` 提前结清
- `prepay_amount`：提前还款金额（元）
- `strategy`：`"reduce_term"` 缩短期限 / `"reduce_payment"` 降低月供
- `penalty_rate`：违约金比例（如 1 表示 1%）
- `penalty_fixed`：固定违约金（元）
- `penalty_free_months`：免违约金窗口（月）
- `min_prepay_amount`：最低提前还金额（元）

示例：见 `examples/sample_input.json`。

## 输出说明

输出为 JSON，包含：
- `summary`：关键指标（剩余本金、节省利息、新月供、新剩余期数等）
- `schedule_after`（可选）：新的还款计划表（每期本金/利息/余额）
- `warnings`：假设或兼容性提示

## 假设与说明

- 按月计息、按期还款；仅实现 `paid_months` 方式计算已还情况。
- 不模拟银行的逐期四舍五入，内部使用高精度计算，输出时保留两位小数。
- 等额本金 + 缩短期限：默认保持“原每期固定本金”不变，剩余期数相应减少。

## 免责声明

本工具按“按月计息、按期还款”简化估算，可能与银行按日计息/合同条款存在差异。违约金/手续费以合同/银行说明为准。
