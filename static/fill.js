"use strict";
(() => {
  const survey = JSON.parse(document.getElementById("survey-data").textContent);
  const questions = survey.questions;
  const byId = Object.fromEntries(questions.map(question => [question.id, question]));
  let path = [questions[0].id];
  let cursor = 0;
  let answers = Object.create(null);
  let busy = false;
  let finished = false;
  let edited = false;
  const form = document.getElementById("answer-form");
  const controls = document.getElementById("answer-controls");
  const errorBox = document.getElementById("answer-error");
  const nextButton = document.getElementById("next-question");
  const previousButton = document.getElementById("previous-question");
  const esc = escapeHtml;

  function hint(question) {
    const v = question.validation;
    const pieces = [question.required ? "必答" : "选填"];
    if (question.type === "multiple") {
      if (v.min_choices != null && v.min_choices === v.max_choices) pieces.push(`恰好选择 ${v.min_choices} 项`);
      else { if (v.min_choices != null) pieces.push(`至少选 ${v.min_choices} 项`); if (v.max_choices != null) pieces.push(`最多选 ${v.max_choices} 项`); }
    }
    if (question.type === "text") { if (v.min_length != null) pieces.push(`至少 ${v.min_length} 个字符`); if (v.max_length != null) pieces.push(`最多 ${v.max_length} 个字符`); }
    if (question.type === "number") { if (v.integer_only) pieces.push("必须为整数"); if (v.min_value != null) pieces.push(`不小于 ${v.min_value}`); if (v.max_value != null) pieces.push(`不大于 ${v.max_value}`); }
    return pieces.join(" · ");
  }

  function currentAnswer() {
    const question = byId[path[cursor]];
    if (question.type === "single") return controls.querySelector("input:checked")?.value ?? null;
    if (question.type === "multiple") return [...controls.querySelectorAll("input:checked")].map(input => input.value);
    return controls.querySelector("input, textarea").value;
  }

  function render() {
    const question = byId[path[cursor]];
    const answer = answers[question.id];
    const index = questions.findIndex(item => item.id === question.id);
    document.getElementById("question-progress").textContent = `第 ${index + 1} / ${questions.length} 题 · 本次已到达 ${cursor + 1} 题`;
    document.getElementById("question-title").textContent = question.title;
    document.getElementById("question-hint").textContent = hint(question);
    if (["single", "multiple"].includes(question.type)) {
      controls.innerHTML = question.options.map(option => `<label class="answer-option"><input type="${question.type === "single" ? "radio" : "checkbox"}" name="answer" value="${esc(option.id)}" ${(question.type === "single" ? answer === option.id : Array.isArray(answer) && answer.includes(option.id)) ? "checked" : ""}><span>${esc(option.text)}</span></label>`).join("");
    } else if (question.type === "text") controls.innerHTML = `<label>填写内容<textarea rows="4" aria-label="填写内容">${esc(answer ?? "")}</textarea></label>`;
    else controls.innerHTML = `<label>填写数字<input type="number" step="any" inputmode="decimal" aria-label="填写数字" value="${esc(answer ?? "")}"></label>`;
    previousButton.hidden = cursor === 0;
    nextButton.textContent = index === questions.length - 1 ? "提交问卷" : "下一题";
    errorBox.hidden = true;
  }

  form.addEventListener("input", () => { edited = true; errorBox.hidden = true; });
  previousButton.addEventListener("click", () => {
    if (busy || cursor === 0) return;
    answers[path[cursor]] = currentAnswer();
    cursor -= 1; render();
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy) return;
    busy = true; nextButton.disabled = true; previousButton.disabled = true; errorBox.hidden = true;
    const question = byId[path[cursor]];
    const raw = currentAnswer();
    try {
      const checked = await api(`/api/surveys/${survey.id}/check-answer`, "POST", { question_id: question.id, value: raw });
      // Keep the original numeric string so browser number rounding cannot change it.
      answers[question.id] = question.type === "number" ? raw : checked.answer;
      if (checked.next_id === null) {
        const result = await api(`/api/surveys/${survey.id}/responses`, "POST", { answers });
        finished = true; location.href = result.redirect;
      } else {
        if (path[cursor + 1] !== checked.next_id) {
          path.slice(cursor + 1).forEach(id => { delete answers[id]; });
          path = path.slice(0, cursor + 1);
          path.push(checked.next_id);
        }
        cursor += 1; render();
        document.querySelector(".answer-panel").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (error) {
      errorBox.textContent = error.message; errorBox.hidden = false;
    } finally { busy = false; nextButton.disabled = false; previousButton.disabled = false; }
  });
  window.addEventListener("beforeunload", event => { if (edited && !finished) { event.preventDefault(); event.returnValue = ""; } });
  render();
})();
