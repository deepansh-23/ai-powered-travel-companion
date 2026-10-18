/**
 * Suggestion dropdown for a text input: type "mun" and pick "Munich, Bavaria, Germany".
 * Works with the mouse, the arrow keys, Enter and Escape. The typed text is always kept
 * if nothing is picked, so suggestions never get in the way.
 */

import { api } from "../api.js";
import { escapeHtml } from "../utils/formatters.js";

export function attachPlaceAutocomplete(input, { onPick } = {}) {
  if (!input || input.dataset.placeAutocomplete) return;
  input.dataset.placeAutocomplete = "1";
  input.setAttribute("autocomplete", "off");
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");

  const wrap = document.createElement("div");
  wrap.className = "place-suggest-wrap";
  input.parentNode.insertBefore(wrap, input);
  wrap.appendChild(input);

  const list = document.createElement("ul");
  list.className = "place-suggest-list";
  list.setAttribute("role", "listbox");
  list.hidden = true;
  wrap.appendChild(list);

  let items = [];
  let active = -1;
  let seq = 0;
  let timer = null;

  const close = () => { list.hidden = true; active = -1; input.setAttribute("aria-expanded", "false"); };
  const highlight = () => {
    [...list.children].forEach((li, i) => li.classList.toggle("active", i === active));
  };
  const pick = (i) => {
    const item = items[i];
    if (!item) return;
    input.value = item.label;
    close();
    input.dispatchEvent(new Event("change", { bubbles: true }));
    if (onPick) onPick(item);
  };

  const render = () => {
    if (!items.length) { close(); return; }
    list.innerHTML = items.map((it, i) => `
      <li role="option" data-i="${i}" class="place-suggest-item">
        <span class="place-suggest-label">${escapeHtml(it.label)}</span>
        <span class="place-suggest-kind">${escapeHtml(it.kind_label)}</span>
      </li>`).join("");
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { items = []; close(); return; }
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const res = await api.suggestPlaces(q);
        if (mine !== seq) return; // a newer keystroke is already being answered
        items = res.suggestions || [];
        active = -1;
        render();
      } catch (_) {
        items = [];
        close();
      }
    }, 300);
  });

  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); active = (active + 1) % items.length; highlight(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); active = (active - 1 + items.length) % items.length; highlight(); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); pick(active); }
    else if (e.key === "Escape") { close(); }
  });

  list.addEventListener("mousedown", (e) => {
    const li = e.target.closest(".place-suggest-item");
    if (li) { e.preventDefault(); pick(Number(li.dataset.i)); }
  });
  input.addEventListener("blur", () => setTimeout(close, 120));
}
