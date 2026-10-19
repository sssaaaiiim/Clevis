({generation, firstRef, maxElements, maxText, textOnly = false, targetRef = null}) => {
  const collapse = value => (value || "").replace(/\s+/g, " ").trim();
  const secret = /password|otp|one[-_ ]?time|token|secret|cvv|cvc|card|cc[-_ ]?(number|csc|exp)|ssn/i;
  const isSecret = el => el instanceof HTMLInputElement && (
    el.type === "password" || secret.test([el.name, el.id, el.autocomplete, el.getAttribute("aria-label")].join(" "))
  );
  const sensitive = [...document.querySelectorAll("input")].filter(isSecret).map(el => el.value).filter(Boolean);
  const redact = text => {
    for (const value of sensitive) text = text.split(value).join("[redacted]");
    return text;
  };
  const visible = el => {
    if (!el || !el.isConnected) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    const doc = document.documentElement;
    let scrollableAncestor = false;
    for (let parent = el.parentElement; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      if ((["auto","scroll"].includes(style.overflowY) && parent.scrollHeight > parent.clientHeight) ||
          (["auto","scroll"].includes(style.overflowX) && parent.scrollWidth > parent.clientWidth)) {
        scrollableAncestor = true;
      }
    }
    if (!scrollableAncestor && (rect.right + scrollX <= 0 || rect.bottom + scrollY <= 0 ||
        rect.left + scrollX > doc.scrollWidth || rect.top + scrollY > doc.scrollHeight)) return false;
    for (let parent = el; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      if (parent.hidden || parent.getAttribute("aria-hidden") === "true" ||
          style.display === "none" || ["hidden", "collapse"].includes(style.visibility) ||
          Number(style.opacity) === 0 || Number(style.fontSize.replace("px", "")) <= 2 ||
          style.color === "transparent" || /rgba\([^)]*,\s*0\)$/.test(style.color)) return false;
      const bound = parent.getBoundingClientRect();
      if (parent !== el && ["hidden", "clip"].includes(style.overflowY) &&
          (rect.bottom <= bound.top || rect.top >= bound.bottom || bound.height === 0)) return false;
      if (parent !== el && ["hidden", "clip"].includes(style.overflowX) &&
          (rect.right <= bound.left || rect.left >= bound.right || bound.width === 0)) return false;
    }
    return true;
  };
  const textFor = (root, excluded = null) => {
    if (!root || !visible(root)) return "";
    const parts = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (!parent || parent.closest("script,style,noscript,template") || !visible(parent)) continue;
      if (excluded instanceof Element && excluded.contains(parent)) continue;
      parts.push(node.textContent || "");
    }
    return redact(collapse(parts.join(" ")));
  };
  const accessibleName = el => {
    const labelled = (el.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean)
      .map(id => textFor(document.getElementById(id))).filter(Boolean).join(" ");
    const forLabel = el.id ? [...document.querySelectorAll("label[for]")]
      .filter(label => label.htmlFor === el.id).map(textFor).join(" ") : "";
    const associated = el.labels ? [...el.labels].map(textFor).join(" ") : textFor(el.closest("label"));
    return redact(collapse(el.getAttribute("aria-label") || labelled || forLabel || associated ||
      el.getAttribute("placeholder") || el.getAttribute("alt") || el.getAttribute("title") ||
      textFor(el) || ((el.type === "submit" || el.type === "button") ? el.value : ""))).slice(0, 80);
  };
  const roleFor = el => {
    const explicit = collapse(el.getAttribute("role")).split(" ")[0];
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === "a") return "link";
    if (tag === "button" || tag === "summary") return "button";
    if (tag === "textarea" || el.isContentEditable) return "textbox";
    if (tag === "select") return el.multiple ? "listbox" : "combobox";
    if (tag === "option") return "option";
    if (tag === "input") {
      if (["button", "submit", "reset", "image"].includes(el.type)) return "button";
      return ({checkbox:"checkbox", radio:"radio", range:"slider", number:"spinbutton", search:"searchbox"})[el.type] || "textbox";
    }
    return "button";
  };
  const ariaBool = (el, name) => el.hasAttribute("aria-" + name) ? el.getAttribute("aria-" + name) === "true" : null;
  const preferred = [...document.querySelectorAll("main,article")].find(visible) || document.body;
  const textRoot = targetRef ? [...document.querySelectorAll("[data-agent-ref]")]
    .find(el => el.getAttribute("data-agent-ref") === targetRef) : preferred;
  const primaryText = textFor(textRoot);
  const remainingText = !targetRef && preferred !== document.body ? textFor(document.body, preferred) : "";
  const fullText = collapse(primaryText + " " + remainingText);
  if (textOnly) return fullText.slice(0, maxText);
  const selector = "a[href],button,input,textarea,select,option,[role],[contenteditable]:not([contenteditable=false]),[onclick],summary";
  const candidates = [...document.querySelectorAll(selector)].filter(visible)
    .filter(el => el.getAttribute("type") !== "hidden")
    .filter(el => !el.hasAttribute("role") || ["button","link","textbox","checkbox","radio","menuitem","tab","combobox","option","switch","searchbox","slider","spinbutton","listbox"].includes(roleFor(el)))
    .sort((a,b) => {
      const ra=a.getBoundingClientRect(), rb=b.getBoundingClientRect();
      return ra.top - rb.top || ra.left - rb.left;
    });
  document.querySelectorAll("[data-agent-ref]").forEach(el => el.removeAttribute("data-agent-ref"));
  const elements = candidates.slice(0, maxElements).map((el, index) => {
    const ref = "e" + (firstRef + index);
    el.setAttribute("data-agent-ref", ref);
    let value = "value" in el ? String(el.value) : (el.isContentEditable ? textFor(el) : null);
    if (value !== null) value = isSecret(el) ? (value ? "[redacted]" : "") : redact(value).slice(0,100);
    return {
      ref, role: roleFor(el), name: accessibleName(el), tag: el.tagName.toLowerCase(),
      type: el.getAttribute("type"), value, href: el instanceof HTMLAnchorElement ? el.href : null,
      state: {
        disabled: "disabled" in el ? Boolean(el.disabled) : ariaBool(el,"disabled"),
        checked: el instanceof HTMLInputElement && ["checkbox","radio"].includes(el.type) ? el.checked : ariaBool(el,"checked"),
        expanded: ariaBool(el,"expanded"),
        selected: el instanceof HTMLOptionElement ? el.selected : ariaBool(el,"selected"),
        required: "required" in el ? Boolean(el.required) : ariaBool(el,"required")
      }
    };
  });
  return {
    url: location.href, title: redact(document.title), generation, elements,
    text_excerpt: fullText.slice(0,maxText),
    truncated: candidates.length > maxElements || fullText.length > maxText,
    summary: `Observed ${elements.length} interactive elements.`
  };
}
