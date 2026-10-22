"use strict";
window.api = async function (url, method = "GET", body) {
  const options = { method, headers: { "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  const result = await response.json().catch(() => ({ error: "服务器没有返回有效结果，请刷新后重试。" }));
  if (!response.ok) {
    const error = new Error(result.error || "操作失败，请重试。");
    error.question_id = result.question_id;
    throw error;
  }
  return result;
};
window.escapeHtml = function (value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
};
window.localDateInput = function (iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
