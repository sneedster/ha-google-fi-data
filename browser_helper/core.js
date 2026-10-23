/* Local, read-only capture logic. No requests, cookie writes, or persistence. */
(function (root) {
  "use strict";
  const FI = "https://fi.google.com/account";
  const AUTH = /^(?:SID|HSID|SSID|APISID|OSID|SIDCC|__Secure-(?:OSID|[13]P(?:SID|APISID|SIDCC|SIDTS)))$/;
  const ERRORS = {
    wrong_tab: "Open Google Fi and sign in, then open this helper from that tab.",
    wrong_account: "Use a browser profile signed into only the Google account you want to connect. Open Fi there and try again.",
    not_ready: "Fi is not ready. Finish signing in, reload the account page, then try again.",
    no_store: "The browser session could not be identified. Reopen this helper from the Google Fi tab.",
    no_cookies: "No usable Google session was found. Sign in to Fi in this browser profile and try again.",
    changed: "The Fi account changed during capture. Check the account in Fi, then try again.",
    too_large: "The browser session could not be captured. Use a profile with only your intended Google account.",
    copy_failed: "The browser could not copy the setup code. Reopen the helper and try again.",
    unavailable: "The browser could not read Fi. Reload its account page and try again. Check this helper’s site permissions if it keeps failing."
  };

  function checkUrl(text) {
    let url;
    try { url = new URL(text); } catch { throw new Error("wrong_tab"); }
    if (url.origin !== "https://fi.google.com" || !/^\/account\/?$/.test(url.pathname)) {
      throw new Error("wrong_tab");
    }
    if (url.searchParams.has("authuser") && url.searchParams.get("authuser") !== "0") {
      throw new Error("wrong_account");
    }
    return url;
  }

  // Passed to scripting.executeScript: deliberately self-contained and read-only.
  function readFiPage() {
    let memberId = null, tokenPresent = false, sessionIndex = null;
    for (const script of document.scripts) {
      const text = script.textContent;
      if (text.includes("WIZ_global_data")) {
        const member = text.match(/"EEqW7b"\s*:\s*("(?:[^"\\]|\\.)*")/);
        const token = text.match(/"SNlM0e"\s*:\s*("(?:[^"\\]|\\.)*")/);
        if (member) { try { memberId = JSON.parse(member[1]); } catch { /* invalid bootstrap */ } }
        if (token) { try { tokenPresent = Boolean(JSON.parse(token[1])); } catch { /* invalid bootstrap */ } }
      }
      const index = text.match(/(?:window\.)?SESSION_INDEX\s*=\s*["']?(\d+)/);
      if (index) sessionIndex = index[1];
    }
    return { url: location.href, member_id: memberId, token_present: tokenPresent,
      session_index: sessionIndex, user_agent: navigator.userAgent };
  }

  function checkPage(page) {
    checkUrl(page?.url);
    if (page.session_index !== null && page.session_index !== undefined && String(page.session_index) !== "0") {
      throw new Error("wrong_account");
    }
    if (!page.token_present || typeof page.member_id !== "string" || !/^[1-9][0-9]{0,19}$/.test(page.member_id)
        || BigInt(page.member_id) > 18446744073709551615n || typeof page.user_agent !== "string"
        || !page.user_agent || page.user_agent.length > 2048 || /[\r\n]/.test(page.user_agent)) {
      throw new Error("not_ready");
    }
  }

  function makeSession(page, source) {
    checkPage(page);
    const cookies = source.filter(c =>
      ["google.com", ".google.com", "fi.google.com", ".fi.google.com"].includes(c.domain)
      && AUTH.test(c.name) && typeof c.value === "string" && c.value && !/[\r\n]/.test(c.value)
      && c.secure === true && !c.partitionKey && !c.firstPartyDomain
    ).map(c => ({ name: c.name, value: c.value, domain: c.domain, secure: true,
      path: c.path || "/", expires: Number.isFinite(c.expirationDate) ? c.expirationDate : null }));
    if (!cookies.length) throw new Error("no_cookies");
    // HA obtains context from its own authenticated bootstrap, never a captured action.
    const code = JSON.stringify({ user_agent: page.user_agent, cookies });
    if (new TextEncoder().encode(code).length > 256000) throw new Error("too_large");
    return code;
  }

  async function capture(api) {
    const tabs = await api.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];
    checkUrl(tab?.url);
    const read = async () => {
      const results = await api.scripting.executeScript({ target: { tabId: tab.id }, func: readFiPage });
      const page = results[0]?.result;
      checkPage(page);
      return page;
    };
    const first = await read();
    const stores = await api.cookies.getAllCookieStores();
    const store = stores.find(s => s.tabIds.includes(tab.id));
    if (!store || (tab.cookieStoreId && tab.cookieStoreId !== store.id)) throw new Error("no_store");
    const cookies = await api.cookies.getAll({ url: FI, storeId: store.id });
    const second = await read();
    if (first.member_id !== second.member_id || first.url !== second.url || first.user_agent !== second.user_agent) {
      throw new Error("changed");
    }
    return makeSession(second, cookies);
  }

  const exported = { FI, ERRORS, checkUrl, readFiPage, checkPage, makeSession, capture };
  if (typeof module !== "undefined" && module.exports) module.exports = exported;
  else root.FiSetup = exported;
})(globalThis);
