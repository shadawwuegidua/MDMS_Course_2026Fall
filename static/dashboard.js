"use strict";
document.querySelectorAll(".deadline").forEach(input => { input.value = localDateInput(input.dataset.utc); });
document.addEventListener("click", async event => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const card = button.closest(".survey-card");
  const id = card.dataset.surveyId;
  const message = document.getElementById("dashboard-message");
  message.hidden = true;
  button.disabled = true;
  try {
    if (button.dataset.action === "copy") {
      const input = card.querySelector(".share-url");
      try { await navigator.clipboard.writeText(input.value); message.textContent = "填写链接已复制。"; }
      catch { input.focus(); input.select(); message.textContent = "链接已选中，请按 Ctrl+C 复制。"; }
      message.className = "message"; message.hidden = false;
    } else if (button.dataset.action === "deadline") {
      const value = card.querySelector(".deadline").value;
      await api(`/api/surveys/${id}/deadline`, "PATCH", { deadline: value ? new Date(value).toISOString() : null });
      location.reload();
    } else {
      await api(`/api/surveys/${id}/${button.dataset.action}`, "POST", {});
      location.reload();
    }
  } catch (error) {
    message.textContent = error.message; message.className = "message error"; message.hidden = false;
    message.scrollIntoView({ behavior: "smooth", block: "center" });
  } finally { button.disabled = false; }
});
