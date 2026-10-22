"use strict";
(() => {
  const initial = JSON.parse(document.getElementById("survey-data").textContent);
  let surveyId = initial?.id || null;
  let questions = initial?.questions || [];
  let dirty = false;
  let busy = false;
  const form = document.getElementById("editor-form");
  const container = document.getElementById("questions");
  const message = document.getElementById("editor-message");
  const labels = { single: "单选题", multiple: "多选题", text: "文本填空", number: "数字填空" };
  const operators = { eq: "等于", contains: "包含选项", gt: "大于", gte: "大于等于", lt: "小于", lte: "小于等于" };
  const uid = prefix => prefix + crypto.randomUUID().replaceAll("-", "").slice(0, 12);
  const esc = escapeHtml;
  document.getElementById("survey-deadline").value = localDateInput(initial?.deadline);

  function showMessage(text, error = false) {
    message.textContent = text;
    message.className = error ? "message error" : "message";
    message.hidden = !text;
  }

  function sync() {
    container.querySelectorAll(".question-card").forEach(card => {
      const question = questions.find(item => item.id === card.dataset.qid);
      question.title = card.querySelector(".question-title-input").value;
      question.required = card.querySelector(".question-required").checked;
      question.options = [...card.querySelectorAll(".option-row")].map(row => ({ id: row.dataset.optionId, text: row.querySelector("input").value }));
      question.validation = {};
      card.querySelectorAll("[data-validation]").forEach(input => {
        if (input.type === "checkbox") question.validation[input.dataset.validation] = input.checked;
        else if (input.value !== "") question.validation[input.dataset.validation] = input.value;
      });
      question.rules = [...card.querySelectorAll(".rule-row")].map(row => ({
        operator: row.querySelector(".rule-operator").value,
        value: row.querySelector(".rule-value").value,
        target_id: row.querySelector(".rule-target").value,
      }));
    });
  }

  function limitInput(question, key, label, integer = true) {
    return `<label>${label}<input type="number" ${integer ? 'min="0" step="1"' : 'step="any"'} data-validation="${key}" value="${esc(question.validation[key] ?? "")}" placeholder="不限制"></label>`;
  }

  function renderRules(question, index) {
    if (question.type === "text") return '<p class="hint">文本填空按顺序进入下一题。</p>';
    const future = questions.slice(index + 1);
    const allowed = question.type === "number" ? ["eq", "gt", "gte", "lt", "lte"] : [question.type === "multiple" ? "contains" : "eq"];
    const rows = question.rules.map((rule, ruleIndex) => {
      const operatorSelect = allowed.map(op => `<option value="${op}" ${op === rule.operator ? "selected" : ""}>${operators[op]}</option>`).join("");
      const valueControl = question.type === "number"
        ? `<input class="rule-value" type="number" step="any" required value="${esc(rule.value)}" aria-label="条件数值">`
        : `<select class="rule-value" required aria-label="条件选项"><option value="">选择选项</option>${question.options.map(option => `<option value="${esc(option.id)}" ${option.id === rule.value ? "selected" : ""}>${esc(option.text || "未填写选项文字")}</option>`).join("")}</select>`;
      const invalidTarget = rule.target_id && !future.some(item => item.id === rule.target_id);
      const targets = future.map(item => `<option value="${esc(item.id)}" ${item.id === rule.target_id ? "selected" : ""}>第 ${questions.indexOf(item) + 1} 题：${esc(item.title || "未填写标题")}</option>`).join("");
      return `<div class="rule-row" data-rule-index="${ruleIndex}"><label>比较方式<select class="rule-operator">${operatorSelect}</select></label><label>回答条件${valueControl}</label><label>跳转到<select class="rule-target" required><option value="">选择后续题目</option>${invalidTarget ? `<option value="" selected>原目标位置无效，请重新选择</option>` : ""}${targets}</select></label><button type="button" class="small danger" data-action="remove-rule" data-index="${ruleIndex}">删除</button></div>`;
    }).join("");
    return `<h3>跳转规则</h3><p class="hint">按顺序判断，采用第一条命中规则；没有命中就进入下一题。</p>${rows}<button type="button" class="secondary small" data-action="add-rule" ${future.length ? "" : "disabled"}>＋ 添加规则</button>${future.length ? "" : '<span class="hint"> 最后一题无需跳转</span>'}`;
  }

  function render() {
    container.innerHTML = questions.length ? questions.map((question, index) => {
      const choice = ["single", "multiple"].includes(question.type);
      let limits = "";
      if (question.type === "multiple") limits = limitInput(question, "min_choices", "最少选择数") + limitInput(question, "max_choices", "最多选择数") + '<p class="hint">要求恰好选 N 个时，两项都填 N。</p>';
      if (question.type === "text") limits = limitInput(question, "min_length", "最少字符数") + limitInput(question, "max_length", "最多字符数");
      if (question.type === "number") limits = limitInput(question, "min_value", "最小值", false) + limitInput(question, "max_value", "最大值", false) + `<label class="check"><input type="checkbox" data-validation="integer_only" ${question.validation.integer_only ? "checked" : ""}>必须为整数</label>`;
      return `<section class="panel question-card" data-qid="${esc(question.id)}"><div class="question-heading"><h2>第 ${index + 1} 题 <span class="badge">${labels[question.type]}</span></h2><div class="actions"><button type="button" class="secondary small" data-action="up" ${index ? "" : "disabled"} aria-label="第 ${index + 1} 题上移">↑</button><button type="button" class="secondary small" data-action="down" ${index < questions.length - 1 ? "" : "disabled"} aria-label="第 ${index + 1} 题下移">↓</button><button type="button" class="danger small" data-action="remove-question">删除题目</button></div></div><label>题目标题<input class="question-title-input" value="${esc(question.title)}" required placeholder="输入题目"></label><label class="check"><input class="question-required" type="checkbox" ${question.required ? "checked" : ""}>必答</label>${choice ? `<h3>选项</h3><div class="options">${question.options.map((option, optionIndex) => `<div class="option-row" data-option-id="${esc(option.id)}"><span class="hint">${optionIndex + 1}.</span><input required value="${esc(option.text)}" aria-label="第 ${index + 1} 题选项 ${optionIndex + 1}"><button type="button" class="small danger" data-action="remove-option" data-index="${optionIndex}">删除</button></div>`).join("")}</div><button type="button" class="secondary small" data-action="add-option">＋ 添加选项</button>` : ""}<div class="limits-grid">${limits}</div>${renderRules(question, index)}</section>`;
    }).join("") : '<p class="message">还没有题目。请在下方选择题型并添加。</p>';
  }

  function markDirty() {
    dirty = true;
    document.getElementById("save-state").textContent = "有未保存的修改";
  }
  form.addEventListener("input", markDirty);
  form.addEventListener("change", markDirty);
  document.getElementById("add-question").addEventListener("click", () => {
    sync();
    const type = document.getElementById("new-question-type").value;
    questions.push({ id: uid("q_"), title: "", type, required: true, options: ["single", "multiple"].includes(type) ? [{ id: uid("opt_"), text: "选项 1" }, { id: uid("opt_"), text: "选项 2" }] : [], validation: {}, rules: [] });
    markDirty(); render(); container.lastElementChild.querySelector(".question-title-input").focus();
  });
  container.addEventListener("click", event => {
    const button = event.target.closest("button[data-action]");
    if (!button || button.disabled) return;
    sync();
    const card = button.closest(".question-card");
    const index = questions.findIndex(item => item.id === card.dataset.qid);
    const question = questions[index];
    switch (button.dataset.action) {
      case "remove-question":
        questions.splice(index, 1);
        questions.forEach(item => { item.rules = item.rules.filter(rule => rule.target_id !== question.id); });
        break;
      case "up": [questions[index - 1], questions[index]] = [question, questions[index - 1]]; break;
      case "down": [questions[index + 1], questions[index]] = [question, questions[index + 1]]; break;
      case "add-option": question.options.push({ id: uid("opt_"), text: "" }); break;
      case "remove-option": {
        const [removed] = question.options.splice(Number(button.dataset.index), 1);
        question.rules = question.rules.filter(rule => rule.value !== removed.id);
        break;
      }
      case "add-rule": question.rules.push({ operator: question.type === "multiple" ? "contains" : "eq", value: question.type === "number" ? 0 : question.options[0]?.id || "", target_id: questions[index + 1]?.id || "" }); break;
      case "remove-rule": question.rules.splice(Number(button.dataset.index), 1); break;
    }
    markDirty(); render();
  });

  async function persist() {
    sync();
    const deadline = document.getElementById("survey-deadline").value;
    const payload = { title: document.getElementById("survey-title").value, description: document.getElementById("survey-description").value, is_anonymous: document.getElementById("is-anonymous").checked, allow_multiple: document.getElementById("allow-multiple").checked, deadline: deadline ? new Date(deadline).toISOString() : null, questions };
    const result = await api(surveyId ? `/api/surveys/${surveyId}` : "/api/surveys", surveyId ? "PUT" : "POST", payload);
    surveyId = result.id;
    const saved = await api(`/api/surveys/${surveyId}`);
    questions = saved.questions;
    dirty = false;
    history.replaceState(null, "", `/surveys/${surveyId}/edit`);
    document.querySelector(".page-heading h1").textContent = "编辑问卷";
    document.title = "编辑问卷 · 问卷系统";
    document.getElementById("save-state").textContent = `已保存于 ${new Date().toLocaleTimeString()}`;
    render();
  }

  async function save(publish) {
    if (busy || !form.reportValidity()) return;
    busy = true;
    const buttons = [document.getElementById("save-draft"), document.getElementById("publish-survey")];
    buttons.forEach(button => { button.disabled = true; });
    showMessage("正在保存……");
    container.querySelectorAll(".invalid").forEach(card => card.classList.remove("invalid"));
    try {
      await persist();
      if (publish) { await api(`/api/surveys/${surveyId}/publish`, "POST", {}); location.href = "/dashboard"; }
      else showMessage("草稿已保存。可以继续编辑，或保存并发布。");
    } catch (error) {
      showMessage(error.message, true);
      const card = [...container.querySelectorAll(".question-card")].find(item => item.dataset.qid === error.question_id);
      if (card) { card.classList.add("invalid"); card.scrollIntoView({ behavior: "smooth", block: "center" }); }
    } finally { busy = false; buttons.forEach(button => { button.disabled = false; }); }
  }
  form.addEventListener("submit", event => { event.preventDefault(); save(false); });
  document.getElementById("publish-survey").addEventListener("click", () => save(true));
  window.addEventListener("beforeunload", event => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
  render();
})();
