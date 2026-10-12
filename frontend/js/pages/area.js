/**
 * Area Guide / Summarizer Page Initializer (Section 10).
 */

import { api } from "../api.js";
import { toast } from "../components/toast.js";
import { escapeHtml } from "../utils/formatters.js";
import { announceServiceReady, announceServiceReset } from "../components/review-widget.js";
import { initSavedSessions, forgetDraft } from "../components/saved-sessions.js";

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("areaForm");
  const resultsContainer = document.getElementById("areaResults");
  const STORAGE_KEY = "slg_area_state"; // temporary session state (not History)

  function renderPrompt() {
    announceServiceReset("Area Guide");
    resultsContainer.innerHTML = `
      <div class="empty-state">
        <h3>Enter a neighborhood to get started</h3>
        <p>Type an area above to generate its character profile, amenities and transit overview.</p>
      </div>
    `;
  }

  function saveSession(snapshot) {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot)); } catch (_) {}
  }

  function restoreSession() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      const snap = JSON.parse(raw);
      // Needs a full guide (older history records only stored the area name)
      if (!snap || !snap.sections || !snap.quick_facts) {
        const name = snap && (snap.area_input || snap.area);
        if (name) {
          document.getElementById("areaInput").value = name;
          form.requestSubmit();
          return true;
        }
        return false;
      }
      document.getElementById("areaInput").value = snap.area_input || snap.area_name || "";
      renderAreaGuide(snap);
      return true;
    } catch (_) {
      return false;
    }
  }

  initSavedSessions({
    service: "area",
    saveButtonId: "btnSaveSession",
    hasActiveState: () => !!sessionStorage.getItem(STORAGE_KEY),
    buildSave: () => {
      let snap = null;
      try { snap = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null"); } catch (_) {}
      const has = !!snap && !!snap.area_name;
      return { hasContent: has, title: `Area Guide: ${has ? snap.area_name : ""}`.trim(), state: snap };
    }
  });

  const btnGenerateNew = document.getElementById("btnGenerateNew");
  if (btnGenerateNew) {
    btnGenerateNew.addEventListener("click", () => {
      try { sessionStorage.removeItem(STORAGE_KEY); } catch (_) {}
      forgetDraft("area");
      document.getElementById("areaInput").value = "";
      renderPrompt();
      document.getElementById("areaInput").focus();
    });
  }

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const areaInput = document.getElementById("areaInput").value.trim();
      if (!areaInput) {
        toast.error("Please enter a neighborhood or area.");
        return;
      }

      resultsContainer.innerHTML = `
        <div class="empty-state">
          <div class="skeleton" style="width:60px;height:60px;border-radius:50%;margin:0 auto 16px auto;"></div>
          <h3>Analyzing ${escapeHtml(areaInput)}…</h3>
          <p>Compiling character profile, local amenities, transit hubs, and lifestyle suitability.</p>
        </div>
      `;

      try {
        const res = await api.summarizeArea({ area: areaInput, radius_km: 3.0 });
        renderAreaGuide(res);

        // Full guide goes to both the session (survives navigation) and
        // persistent History (survives refresh / reopen)
        const snapshot = { ...res, area_input: areaInput };
        saveSession(snapshot);
        api.createHistory({
          feature_type: "area",
          title: `Area Guide: ${res.area_name}`,
          preview: res.character_summary,
          payload: snapshot
        }).catch(() => {});

      } catch (err) {
        resultsContainer.innerHTML = `
          <div class="error-state">
            <h3>Unable to summarize area</h3>
            <p>${escapeHtml(err.message || "An unexpected error occurred.")}</p>
          </div>
        `;
      }
    });

    // Restore this session's guide (or a History item) instead of auto-searching
    if (!restoreSession()) renderPrompt();
  }

  function renderAreaGuide(data) {
    announceServiceReady("Area Guide");
    const qf = data.quick_facts;

    let sectionsHtml = "";
    Object.values(data.sections).forEach(sec => {
      sectionsHtml += `
        <div class="area-section-card">
          <h4>${escapeHtml(sec.title)}</h4>
          <p style="margin-top:6px;margin-bottom:12px;">${escapeHtml(sec.summary)}</p>
          ${sec.highlights && sec.highlights.length > 0 ? `
            <div style="display:flex;flex-wrap:wrap;gap:6px;">
              ${sec.highlights.map(h => `<span class="badge badge-primary">${escapeHtml(h)}</span>`).join("")}
            </div>
          ` : ""}
        </div>
      `;
    });

    resultsContainer.innerHTML = `
      <!-- Hero Summary -->
      <div class="area-hero-summary">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
          <div>
            <span class="badge badge-primary" style="margin-bottom:6px;">${escapeHtml(data.region)}</span>
            <h2>${escapeHtml(data.area_name)} Guide</h2>
            <p style="font-size:1.05rem;margin-top:8px;max-width:800px;">${escapeHtml(data.character_summary)}</p>
          </div>
          <button class="btn btn-secondary btn-sm" id="btnExportAreaPdf">Export Area Report</button>
        </div>

        <!-- Quick Facts -->
        <div class="quick-facts-row">
          <div class="fact-item">
            <div class="fact-label">Walkability</div>
            <div class="fact-val">${escapeHtml(qf.walkability)}</div>
          </div>
          <div class="fact-item">
            <div class="fact-label">Transit</div>
            <div class="fact-val">${escapeHtml(qf.transit_connectivity)}</div>
          </div>
          <div class="fact-item">
            <div class="fact-label">Vibe</div>
            <div class="fact-val">${escapeHtml(qf.vibe)}</div>
          </div>
          <div class="fact-item">
            <div class="fact-label">Best For</div>
            <div class="fact-val">${escapeHtml(qf.best_for)}</div>
          </div>
          <div class="fact-item">
            <div class="fact-label">Avg Meal Cost</div>
            <div class="fact-val">${escapeHtml(qf.average_meal_cost)}</div>
          </div>
        </div>
      </div>

      <!-- Map Area Placeholder (Section 10 & 29: Area guide keeps map placeholder) -->
      <div style="background:var(--color-surface);border:1px dashed var(--color-border);border-radius:var(--radius-xl);padding:var(--space-lg);margin-bottom:var(--space-xl);text-align:center;color:var(--color-text-muted);">
        <p style="font-weight:600;">🗺️ Area Boundary Overview Placeholder</p>
        <small>Interactive perimeter mapping will be connected in Phase 6. Sights and amenities are detailed below.</small>
      </div>

      <!-- 12 Analytical Sections -->
      <h3 style="margin-bottom:var(--space-md);">Neighborhood Amenities & Character</h3>
      <div class="area-sections-grid">
        ${sectionsHtml}
      </div>

      <!-- Pros, Cons, and Suitability -->
      <div class="pro-con-grid">
        <div class="pro-box">
          <h4 style="color:var(--color-success);display:flex;align-items:center;gap:6px;">
            <span>✓</span> Neighborhood Advantages
          </h4>
          <ul style="margin-top:10px;padding-left:20px;font-size:0.925rem;line-height:1.6;">
            ${data.advantages.map(a => `<li>${escapeHtml(a)}</li>`).join("")}
          </ul>
        </div>

        <div class="con-box">
          <h4 style="color:var(--color-warning);display:flex;align-items:center;gap:6px;">
            <span>⚠️</span> Limitations to Note
          </h4>
          <ul style="margin-top:10px;padding-left:20px;font-size:0.925rem;line-height:1.6;">
            ${data.limitations.map(l => `<li>${escapeHtml(l)}</li>`).join("")}
          </ul>
        </div>
      </div>

      <!-- Who It Suits -->
      <div class="area-section-card" style="margin-top:var(--space-lg);">
        <h4>👥 Who This Area May Suit</h4>
        <ul style="margin-top:10px;padding-left:20px;font-size:0.925rem;line-height:1.6;">
          ${data.suitability.map(s => `<li>${escapeHtml(s)}</li>`).join("")}
        </ul>
        <div class="card-source-line" style="margin-top:14px;">Source: ${escapeHtml(data.source)}</div>
      </div>
    `;

    document.getElementById("btnExportAreaPdf").addEventListener("click", async () => {
      try {
        toast.info("Preparing Area Report PDF…");
        const blob = await api.exportPdf(`Area Guide: ${data.area_name}`, data);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = url;
        a.download = `${(data.area_name || "area_guide").replace(/[^a-z0-9]+/gi, "_")}_Area_Guide.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        toast.success("PDF downloaded successfully!");
      } catch (err) {
        toast.error("Export failed: " + err.message);
      }
    });
  }
});
