# 提前还贷计算器：产品与算法设计说明（给实现用）

> 目标：做一个可交互的“提前还贷/部分提前还款”计算器，支持常见还款方式、提前还款策略对比，并输出清晰的节省利息与剩余计划。

---

## 1. 使用场景与核心问题

用户通常想回答这些问题：

1) **我现在提前还 X 万，能省多少利息？**  
2) **提前还后，我是该缩短年限还是降低月供？两种差多少？**  
3) **不同提前还款时间点/金额，哪个更划算？**  
4) **如果有违约金/手续费，提前还款还值吗？**  
5) **我已经还了 N 期，现在剩余本金多少？提前结清要付多少？**

因此产品要提供：

- 计算 **剩余本金**、**提前结清金额**、**节省利息**  
- 对比 **策略 A：缩短期限（月供不变）** vs **策略 B：降低月供（期限不变）**  
- 输出 **新的还款计划表（可选）**：每期本金/利息/余额  
- 支持 **等额本息** 与 **等额本金** 两类

---

## 2. 输入参数（建议 UI 表单）

### 2.1 基础贷款信息
- `principal`：贷款总额（元）
- `annual_rate`：年利率（如 3.95%）
- `term_months`：总期数（月）
- `repayment_type`：还款方式
  - `"EPI"`：等额本息
  - `"EP"`：等额本金

### 2.2 已还情况（用于计算当前剩余）
二选一，建议都支持：

- 方式 A（常用）：  
  - `paid_months`：已还期数（整数，0～term_months）
- 方式 B（更精确）：  
  - `as_of_date`：查询日期  
  - `first_payment_date`：首期还款日  
  - `calendar_rule`：按月计息规则（可选，默认“按期数”简化）

> MVP 建议先用 `paid_months`，避免日期/闰月/不规则天数复杂度。

### 2.3 提前还款信息
- `prepay_amount`：提前还款金额（元）
- `prepay_month_index`：第几期之后提前还（一般等价于 `paid_months`）
- `prepay_type`：
  - `"partial"`：部分提前还款
  - `"full"`：提前结清（可把 `prepay_amount` 忽略，直接结清）

### 2.4 提前还款策略（部分提前还款时）
- `strategy`：
  - `"reduce_term"`：月供不变，缩短期限
  - `"reduce_payment"`：期限不变，降低月供
- `recalc_rule`：提前还后重算规则（不同银行可能不同，建议提供选项）
  - `"recalc_by_remaining_principal"`：用剩余本金重算（常见）
  - `"keep_rate_keep_type"`：保持利率/还款方式不变（默认就是这个）

### 2.5 费用与限制（可选）
- `penalty_rate`：违约金比例（如 1%）
- `penalty_fixed`：固定违约金（元）
- `penalty_free_months`：免违约金窗口（如放款后 12 个月内不免/免，视产品）
- `min_prepay_amount`：最低提前还金额（元）
- `max_prepay_times_per_year`：每年次数限制（提示用）

> 费用会影响“净节省”：净节省 = 节省利息 - 违约金/手续费。

---

## 3. 输出结果（建议）

### 3.1 总览指标
- `original_monthly_payment`：原月供（等额本息）或首期月供（等额本金）
- `original_total_interest`：原计划总利息（或剩余总利息）
- `remaining_principal_before`：提前还前剩余本金
- `interest_remaining_before`：提前还前剩余利息（从当前到结束）
- `prepay_penalty`：违约金/手续费
- `remaining_principal_after`：提前还后剩余本金（部分提前后）
- `new_monthly_payment`：新月供（降低月供策略）或保持不变（缩短期限策略）
- `new_term_months_remaining`：提前还后剩余期数（缩短期限策略会减少）
- `interest_remaining_after`：提前还后剩余利息
- `interest_saved_gross`：节省利息（不扣费用）
- `interest_saved_net`：净节省利息（扣费用）
- `break_even_months`（可选）：多久能“回本”（如果比较投资收益/机会成本）

### 3.2 计划表（可选，但很有用）
每期：
- `period`：期数（从 1 开始或从当前+1 开始）
- `payment`：当期应还
- `principal_paid`：当期本金
- `interest_paid`：当期利息
- `balance`：期末剩余本金

---

## 4. 计算模型与公式

下面用“按月、期末还款”来描述（MVP 常见假设）。  
符号：
- `P`：贷款本金（principal）
- `r`：月利率 = `annual_rate / 12`
- `N`：总期数（月）
- `k`：已还期数（paid_months）
- `A`：等额本息月供
- `B_k`：第 k 期还完后的剩余本金（k=0 表示未还）

### 4.1 等额本息（EPI）

#### 4.1.1 月供
\[
A = P \cdot \frac{r(1+r)^N}{(1+r)^N - 1}
\]

#### 4.1.2 剩余本金（已还 k 期后）
\[
B_k = P(1+r)^k - A \cdot \frac{(1+r)^k - 1}{r}
\]

#### 4.1.3 剩余利息（从 k+1 到 N）
\[
\text{interest\_remaining\_before} = A \cdot (N-k) - B_k
\]

---

### 4.2 等额本金（EP）

#### 4.2.1 每期应还本金
\[
p = \frac{P}{N}
\]

#### 4.2.2 第 t 期利息（t 从 1..N）
\[
\text{balance}_{t-1} = P - p\cdot(t-1)
\]
\[
i_t = \text{balance}_{t-1}\cdot r
\]
\[
A_t = p + i_t
\]

#### 4.2.3 已还 k 期后的剩余本金
\[
B_k = P - p\cdot k
\]

#### 4.2.4 剩余利息（建议循环求和）
\[
\text{interest\_remaining\_before} = \sum_{t=k+1}^{N} \left( (P - p\cdot(t-1))\cdot r \right)
\]

---

## 5. 提前还款后的重算逻辑（核心）

提前还款发生在“已还 k 期之后”，此时剩余本金 `B_k` 已知。

### 5.1 提前结清（full）
MVP（按期数简化）：
- `settlement_amount = B_k`
- `prepay_penalty = max(B_k * penalty_rate, penalty_fixed)`（按业务规则组合）
- 节省利息 = `interest_remaining_before`
- 净节省 = 节省利息 - 违约金

### 5.2 部分提前还款（partial）
\[
B'_k = \max(0, B_k - \text{prepay\_amount})
\]

#### 5.2.1 期限不变（reduce_payment）
- 剩余期数：`N' = N - k`
- 用 `B'_k` 在 `N'` 内重算

等额本息新月供：
\[
A' = B'_k \cdot \frac{r(1+r)^{N'}}{(1+r)^{N'} - 1}
\]
等额本金：每期本金 `B'_k / N'`，利息按余额递减。

#### 5.2.2 月供不变（reduce_term）
等额本息保持原 `A`，对 `B'_k` 循环摊还直到归零（最后一期可能小于 A）：
```text
balance = B'_k
months = 0
while balance > 0:
  interest = balance * r
  principal_paid = A - interest
  if principal_paid <= 0:
     error
  if principal_paid > balance:
     principal_paid = balance
     payment_last = interest + principal_paid
     balance = 0
     months += 1
     break
  balance -= principal_paid
  months += 1
```

---

## 6. 计算流程（推荐实现结构）

1) 校验输入（金额>0、期数整数、利率>=0、paid_months 合法、prepay_amount 不超过余额等）  
2) 计算原计划关键量：`A`/`B_k`/`interest_remaining_before`  
3) 计算费用 `prepay_penalty`  
4) 按 `prepay_type` 与 `strategy` 重算新计划/新指标  
5) 计算节省：
- `interest_saved_gross = interest_remaining_before - interest_remaining_after`
- `interest_saved_net = interest_saved_gross - prepay_penalty`

---

## 7. 边界条件与坑位

- 利率为 0：`A = P / N`，利息全 0  
- 提前还款金额 >= 余额：按结清处理  
- 浮点误差：建议用 decimal/分，余额 clamp 到 0  
- 等额本金 + 缩短期限：不同银行规则不一，MVP 需在 UI 明确假设

---

## 8. 免责声明
- 本工具按“按月计息、按期还款”简化估算，可能与银行按日计息/合同条款存在差异。  
- 违约金/手续费以合同/银行说明为准。
