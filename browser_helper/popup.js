"use strict";
const api = globalThis.browser || globalThis.chrome;
const openFi = document.getElementById("open-fi");
const copyCode = document.getElementById("copy-code");
const status = document.getElementById("status");
function message(text, state) { status.textContent = text; status.dataset.state = state; }

openFi.addEventListener("click", async () => {
  try {
    await api.tabs.create({ url: FiSetup.FI });
    message("Finish signing in to Fi, then reopen this helper from that tab.", "idle");
  } catch { message("The browser could not open Fi. Open fi.google.com/account and try again.", "error"); }
});

copyCode.addEventListener("click", async () => {
  copyCode.disabled = openFi.disabled = true;
  copyCode.setAttribute("aria-busy", "true");
  message("Reading your signed-in Fi session…", "busy");
  try {
    const code = await FiSetup.capture(api);
    try { await navigator.clipboard.writeText(code); } catch { throw new Error("copy_failed"); }
    message("Copied. Paste into Home Assistant’s Setup code field, then choose your phone lines.", "success");
  } catch (error) {
    message(FiSetup.ERRORS[error?.message] || FiSetup.ERRORS.unavailable, "error");
  } finally {
    copyCode.disabled = openFi.disabled = false;
    copyCode.removeAttribute("aria-busy");
  }
});

// Controls are unavailable until their privileged API and handlers are ready.
copyCode.disabled = openFi.disabled = !api;
if (!api) message("Install this helper as a browser extension using the setup guide.", "error");
