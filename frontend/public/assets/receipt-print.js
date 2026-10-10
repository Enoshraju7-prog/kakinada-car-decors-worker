document
  .getElementById("print")
  .addEventListener("click", () => window.print());
window.addEventListener("load", () => window.print(), { once: true });
