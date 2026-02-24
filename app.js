const EPS = 1e-8;

const summaryFields = [
  { key: "original_monthly_payment", label: "原月供/首期月供" },
  { key: "original_total_interest", label: "原计划总利息" },
  { key: "remaining_principal_before", label: "提前还前剩余本金" },
  { key: "interest_remaining_before", label: "提前还前剩余利息" },
  { key: "prepay_penalty", label: "违约金/手续费" },
  { key: "remaining_principal_after", label: "提前还后剩余本金" },
  { key: "new_monthly_payment", label: "新月供" },
  { key: "new_term_months_remaining", label: "剩余期数" },
  { key: "interest_remaining_after", label: "提前还后剩余利息" },
  { key: "interest_saved_gross", label: "节省利息（未扣费用）" },
  { key: "interest_saved_net", label: "净节省利息" },
  { key: "settlement_amount", label: "提前结清金额" },
  { key: "effective_prepay_type", label: "实际提前还类型" },
];

const form = document.getElementById("calc-form");
const errorBox = document.getElementById("error");
const warningsBox = document.getElementById("warnings");
const summaryBox = document.getElementById("summary");
const scheduleBox = document.getElementById("schedule");
const scheduleBody = document.getElementById("schedule-body");

function parseNumber(value, field, allowEmpty = false) {
  let raw = String(value ?? "").trim();
  if (!raw) {
    if (allowEmpty) return null;
    throw new Error(`${field} 不能为空`);
  }
  if (raw.endsWith("%")) {
    raw = raw.slice(0, -1).trim();
  }
  const num = Number(raw);
  if (!Number.isFinite(num)) {
    throw new Error(`${field} 不是有效数字`);
  }
  return num;
}

function parseIntStrict(value, field, allowEmpty = false) {
  const raw = String(value ?? "").trim();
  if (!raw) {
    if (allowEmpty) return null;
    throw new Error(`${field} 不能为空`);
  }
  const num = Number(raw);
  if (!Number.isFinite(num) || !Number.isInteger(num)) {
    throw new Error(`${field} 必须是整数`);
  }
  return num;
}

function round2(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function fmtMoney(value) {
  return round2(value).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function monthlyRate(annualRatePercent) {
  if (annualRatePercent < 0) throw new Error("年利率必须 >= 0");
  return annualRatePercent / 100 / 12;
}

function epiPayment(principal, rate, months) {
  if (months <= 0) throw new Error("总期数必须 > 0");
  if (rate === 0) return principal / months;
  const factor = Math.pow(1 + rate, months);
  return (principal * rate * factor) / (factor - 1);
}

function epiRemainingPrincipal(principal, rate, months, paidMonths, payment) {
  if (paidMonths <= 0) return principal;
  if (paidMonths >= months) return 0;
  if (rate === 0) return Math.max(0, principal - payment * paidMonths);
  const factor = Math.pow(1 + rate, paidMonths);
  const remaining = principal * factor - payment * (factor - 1) / rate;
  return Math.max(0, remaining);
}

function epPrincipalPayment(principal, months) {
  if (months <= 0) throw new Error("总期数必须 > 0");
  return principal / months;
}

function epRemainingPrincipal(principal, principalPayment, paidMonths) {
  if (paidMonths <= 0) return principal;
  return Math.max(0, principal - principalPayment * paidMonths);
}

function epTotalInterest(principal, rate, months) {
  if (rate === 0) return 0;
  const p = epPrincipalPayment(principal, months);
  const n = months;
  const sumBalances = n * principal - p * (n - 1) * n / 2;
  return sumBalances * rate;
}

function calcPenalty(base, penaltyRatePercent, penaltyFixed, paidMonths, penaltyFreeMonths) {
  if (penaltyFreeMonths != null && paidMonths >= penaltyFreeMonths) return 0;
  const byRate = penaltyRatePercent > 0 ? base * (penaltyRatePercent / 100) : 0;
  const byFixed = penaltyFixed > 0 ? penaltyFixed : 0;
  if (byRate === 0 && byFixed === 0) return 0;
  return Math.max(byRate, byFixed);
}

function simulateEPI(balance, rate, payment, termMonths, buildSchedule) {
  let months = 0;
  let totalInterest = 0;
  const schedule = [];

  while (balance > EPS && (termMonths == null || months < termMonths)) {
    const interest = balance * rate;
    let principalPaid = payment - interest;
    if (principalPaid <= 0) throw new Error("月供不足以覆盖利息");

    const isLast = termMonths != null && months + 1 >= termMonths;
    let paymentThis = payment;
    if (principalPaid > balance || isLast) {
      principalPaid = balance;
      paymentThis = principalPaid + interest;
    }

    balance = Math.max(0, balance - principalPaid);
    months += 1;
    totalInterest += interest;

    if (buildSchedule) {
      schedule.push({
        period: months,
        payment: paymentThis,
        principal_paid: principalPaid,
        interest_paid: interest,
        balance,
      });
    }

    if (termMonths == null && balance <= EPS) break;
  }

  return { months, totalInterest, schedule };
}

function simulateEP(balance, rate, principalPayment, termMonths, buildSchedule) {
  let months = 0;
  let totalInterest = 0;
  const schedule = [];

  while (balance > EPS && (termMonths == null || months < termMonths)) {
    const interest = balance * rate;
    const isLast = termMonths != null && months + 1 >= termMonths;
    const principalPaid = principalPayment > balance || isLast ? balance : principalPayment;
    const paymentThis = principalPaid + interest;

    balance = Math.max(0, balance - principalPaid);
    months += 1;
    totalInterest += interest;

    if (buildSchedule) {
      schedule.push({
        period: months,
        payment: paymentThis,
        principal_paid: principalPaid,
        interest_paid: interest,
        balance,
      });
    }

    if (termMonths == null && balance <= EPS) break;
  }

  return { months, totalInterest, schedule };
}

function normalizeInputs(formData) {
  const principal = parseNumber(formData.get("principal"), "贷款总额");
  const annualRate = parseNumber(formData.get("annual_rate"), "年利率");
  const termMonths = parseIntStrict(formData.get("term_months"), "总期数");

  const repaymentType = String(formData.get("repayment_type") || "EPI").toUpperCase();
  if (!["EPI", "EP"].includes(repaymentType)) {
    throw new Error("还款方式必须是 EPI 或 EP");
  }

  const paidMonths = parseIntStrict(formData.get("paid_months"), "已还期数");
  const prepayType = String(formData.get("prepay_type") || "partial").toLowerCase();
  const strategy = String(formData.get("strategy") || "reduce_term").toLowerCase();
  const prepayAmount = parseNumber(formData.get("prepay_amount"), "提前还款金额", true) ?? 0;
  const penaltyRate = parseNumber(formData.get("penalty_rate"), "违约金比例", true) ?? 0;
  const penaltyFixed = parseNumber(formData.get("penalty_fixed"), "固定违约金", true) ?? 0;
  const penaltyFreeMonths = parseIntStrict(formData.get("penalty_free_months"), "免违约金窗口", true);
  const minPrepayAmount = parseNumber(formData.get("min_prepay_amount"), "最低提前还金额", true);

  if (principal <= 0) throw new Error("贷款总额必须 > 0");
  if (termMonths <= 0) throw new Error("总期数必须 > 0");
  if (paidMonths < 0 || paidMonths > termMonths) throw new Error("已还期数不合法");
  if (annualRate < 0) throw new Error("年利率必须 >= 0");
  if (prepayAmount < 0) throw new Error("提前还款金额必须 >= 0");
  if (prepayType === "partial" && prepayAmount <= 0) throw new Error("部分提前还款需填写金额");
  if (minPrepayAmount != null && prepayAmount > 0 && prepayAmount < minPrepayAmount) {
    throw new Error("提前还款金额低于最低要求");
  }

  return {
    principal,
    annualRate,
    termMonths,
    repaymentType,
    paidMonths,
    prepayType,
    strategy,
    prepayAmount,
    penaltyRate,
    penaltyFixed,
    penaltyFreeMonths,
    minPrepayAmount,
    includeSchedule: formData.get("include_schedule") === "on",
  };
}

function calculate(inputs) {
  const warnings = [];
  const rate = monthlyRate(inputs.annualRate);

  let originalMonthlyPayment = 0;
  let remainingPrincipalBefore = 0;
  let interestRemainingBefore = 0;
  let originalTotalInterest = 0;

  if (inputs.repaymentType === "EPI") {
    originalMonthlyPayment = epiPayment(inputs.principal, rate, inputs.termMonths);
    remainingPrincipalBefore = epiRemainingPrincipal(
      inputs.principal,
      rate,
      inputs.termMonths,
      inputs.paidMonths,
      originalMonthlyPayment
    );
    interestRemainingBefore =
      originalMonthlyPayment * (inputs.termMonths - inputs.paidMonths) - remainingPrincipalBefore;
    originalTotalInterest = originalMonthlyPayment * inputs.termMonths - inputs.principal;
  } else {
    const principalPayment = epPrincipalPayment(inputs.principal, inputs.termMonths);
    remainingPrincipalBefore = epRemainingPrincipal(
      inputs.principal,
      principalPayment,
      inputs.paidMonths
    );
    originalMonthlyPayment = principalPayment + inputs.principal * rate;
    originalTotalInterest = epTotalInterest(inputs.principal, rate, inputs.termMonths);
    const sim = simulateEP(
      remainingPrincipalBefore,
      rate,
      principalPayment,
      inputs.termMonths - inputs.paidMonths,
      false
    );
    interestRemainingBefore = sim.totalInterest;
  }

  if (remainingPrincipalBefore < EPS) {
    remainingPrincipalBefore = 0;
  }

  let effectivePrepayType = inputs.prepayType;
  if (inputs.prepayAmount >= remainingPrincipalBefore && remainingPrincipalBefore > 0) {
    effectivePrepayType = "full";
    warnings.push("提前还款金额 >= 剩余本金，按提前结清处理");
  }

  if (inputs.repaymentType === "EP" && inputs.strategy === "reduce_term") {
    warnings.push("等额本金缩短期限默认保持原每期固定本金不变");
  }

  const penalty = calcPenalty(
    effectivePrepayType === "full" ? remainingPrincipalBefore : inputs.prepayAmount,
    inputs.penaltyRate,
    inputs.penaltyFixed,
    inputs.paidMonths,
    inputs.penaltyFreeMonths
  );

  let remainingPrincipalAfter = 0;
  let interestRemainingAfter = 0;
  let newTermMonthsRemaining = 0;
  let newMonthlyPayment = 0;
  let settlementAmount = 0;
  let scheduleAfter = [];

  if (effectivePrepayType === "full") {
    settlementAmount = remainingPrincipalBefore;
  } else {
    remainingPrincipalAfter = Math.max(0, remainingPrincipalBefore - inputs.prepayAmount);

    if (inputs.strategy === "reduce_payment") {
      const remainingTerm = inputs.termMonths - inputs.paidMonths;
      if (inputs.repaymentType === "EPI") {
        newMonthlyPayment = epiPayment(remainingPrincipalAfter, rate, remainingTerm);
        const sim = simulateEPI(
          remainingPrincipalAfter,
          rate,
          newMonthlyPayment,
          remainingTerm,
          inputs.includeSchedule
        );
        newTermMonthsRemaining = sim.months;
        interestRemainingAfter = sim.totalInterest;
        scheduleAfter = sim.schedule;
      } else {
        const newPrincipalPayment = remainingPrincipalAfter / remainingTerm;
        const sim = simulateEP(
          remainingPrincipalAfter,
          rate,
          newPrincipalPayment,
          remainingTerm,
          inputs.includeSchedule
        );
        newTermMonthsRemaining = sim.months;
        interestRemainingAfter = sim.totalInterest;
        scheduleAfter = sim.schedule;
        newMonthlyPayment = sim.schedule.length > 0 ? sim.schedule[0].payment : 0;
      }
    } else {
      if (inputs.repaymentType === "EPI") {
        const sim = simulateEPI(
          remainingPrincipalAfter,
          rate,
          originalMonthlyPayment,
          null,
          inputs.includeSchedule
        );
        newTermMonthsRemaining = sim.months;
        interestRemainingAfter = sim.totalInterest;
        scheduleAfter = sim.schedule;
        newMonthlyPayment = originalMonthlyPayment;
      } else {
        const originalPrincipalPayment = epPrincipalPayment(inputs.principal, inputs.termMonths);
        const sim = simulateEP(
          remainingPrincipalAfter,
          rate,
          originalPrincipalPayment,
          null,
          inputs.includeSchedule
        );
        newTermMonthsRemaining = sim.months;
        interestRemainingAfter = sim.totalInterest;
        scheduleAfter = sim.schedule;
        newMonthlyPayment = sim.schedule.length > 0 ? sim.schedule[0].payment : 0;
      }
    }
  }

  const interestSavedGross = interestRemainingBefore - interestRemainingAfter;
  const interestSavedNet = interestSavedGross - penalty;

  return {
    summary: {
      original_monthly_payment: originalMonthlyPayment,
      original_total_interest: originalTotalInterest,
      remaining_principal_before: remainingPrincipalBefore,
      interest_remaining_before: interestRemainingBefore,
      prepay_penalty: penalty,
      remaining_principal_after: remainingPrincipalAfter,
      new_monthly_payment: newMonthlyPayment,
      new_term_months_remaining: newTermMonthsRemaining,
      interest_remaining_after: interestRemainingAfter,
      interest_saved_gross: interestSavedGross,
      interest_saved_net: interestSavedNet,
      settlement_amount: settlementAmount,
      effective_prepay_type: effectivePrepayType,
    },
    warnings,
    schedule_after: scheduleAfter,
  };
}

function renderSummary(summary) {
  summaryBox.innerHTML = "";
  summaryFields.forEach((item) => {
    if (!(item.key in summary)) return;
    const value = summary[item.key];
    const wrapper = document.createElement("div");
    wrapper.className = "summary-item";

    const label = document.createElement("span");
    label.textContent = item.label;

    const content = document.createElement("strong");
    if (typeof value === "number") {
      if (item.key.includes("term_months")) {
        content.textContent = `${value} 期`;
      } else if (item.key === "effective_prepay_type") {
        content.textContent = value === "full" ? "提前结清" : "部分提前还款";
      } else {
        content.textContent = `${fmtMoney(value)} 元`;
      }
    } else {
      content.textContent = value;
    }

    wrapper.appendChild(label);
    wrapper.appendChild(content);
    summaryBox.appendChild(wrapper);
  });
}

function renderWarnings(warnings) {
  if (!warnings || warnings.length === 0) {
    warningsBox.hidden = true;
    warningsBox.innerHTML = "";
    return;
  }
  warningsBox.hidden = false;
  warningsBox.innerHTML = `<strong>提示：</strong> ${warnings.join("；")}`;
}

function renderSchedule(schedule) {
  if (!schedule || schedule.length === 0) {
    scheduleBox.hidden = true;
    scheduleBody.innerHTML = "";
    return;
  }
  scheduleBox.hidden = false;
  scheduleBody.innerHTML = schedule
    .map(
      (row) => `
      <tr>
        <td>${row.period}</td>
        <td>${fmtMoney(row.payment)}</td>
        <td>${fmtMoney(row.principal_paid)}</td>
        <td>${fmtMoney(row.interest_paid)}</td>
        <td>${fmtMoney(row.balance)}</td>
      </tr>
    `
    )
    .join("");
}

function showError(message) {
  errorBox.hidden = false;
  errorBox.textContent = message;
}

function clearError() {
  errorBox.hidden = true;
  errorBox.textContent = "";
}

function updateFormState() {
  const prepayType = form.elements.prepay_type.value;
  const prepayAmount = form.elements.prepay_amount;
  const strategy = form.elements.strategy;
  if (prepayType === "full") {
    prepayAmount.disabled = true;
    prepayAmount.value = "";
    strategy.disabled = true;
  } else {
    prepayAmount.disabled = false;
    if (!prepayAmount.value) prepayAmount.value = "200000";
    strategy.disabled = false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  clearError();

  try {
    const inputs = normalizeInputs(new FormData(form));
    const result = calculate(inputs);
    renderWarnings(result.warnings);
    renderSummary(result.summary);
    renderSchedule(result.schedule_after);
  } catch (error) {
    showError(error.message || "计算失败，请检查输入");
  }
});

form.addEventListener("reset", () => {
  window.setTimeout(() => {
    updateFormState();
    clearError();
    renderWarnings([]);
    renderSummary({});
    renderSchedule([]);
  }, 0);
});

form.addEventListener("change", updateFormState);
updateFormState();
