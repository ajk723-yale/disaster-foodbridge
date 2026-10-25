// Enter sends, Shift+Enter inserts a newline.
document.addEventListener("keydown", function (e) {
  if (e.target.id !== "message-input" || e.key !== "Enter" || e.shiftKey || e.isComposing) return;
  e.preventDefault();
  var send = document.getElementById("send");
  if (send && !send.disabled) send.click();
});

// Keep the newest message in view.
new MutationObserver(function () {
  var box = document.getElementById("messages");
  if (box) box.scrollTop = box.scrollHeight;
}).observe(document.documentElement, { childList: true, subtree: true });
