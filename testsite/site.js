"use strict";
document.querySelector("#search-form")?.addEventListener("submit", event => {
  event.preventDefault();
  const query = document.querySelector("#search").value.toLowerCase();
  document.querySelectorAll("#results li").forEach(item => { item.hidden = !item.textContent.toLowerCase().includes(query); });
});
document.querySelector("#contact-form")?.addEventListener("submit", event => {
  event.preventDefault();
  document.querySelector("#confirmation").textContent = "Form submitted successfully.";
});
document.querySelector("#login-form")?.addEventListener("submit", event => {
  event.preventDefault();
  const user = document.querySelector("#username").value;
  const pass = document.querySelector("#password").value;
  document.querySelector("#login-status").textContent = user === "demo-user" && pass === "demo-pass-only" ? "Welcome, " + user : "Invalid demo credentials";
});
document.querySelector("#load-more")?.addEventListener("click", () => {
  const p = document.createElement("p");
  p.textContent = "Loaded more fake content.";
  document.querySelector("#more").append(p);
});
document.querySelector("#alert-button")?.addEventListener("click", () => alert("Fake dialog text must not enter observations or logs."));
