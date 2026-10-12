/**
 * Accessible Modal Dialog Component.
 */

class ModalService {
  constructor() {
    this.overlay = document.createElement("div");
    this.overlay.className = "modal-overlay";
    this.overlay.setAttribute("role", "dialog");
    this.overlay.setAttribute("aria-modal", "true");

    this.overlay.innerHTML = `
      <div class="modal-dialog">
        <div class="modal-header">
          <h3 id="modalTitle">Details</h3>
          <button class="btn-close-modal dismiss-btn" aria-label="Close modal">&times;</button>
        </div>
        <div class="modal-body" id="modalBody"></div>
        <div class="modal-footer" id="modalFooter">
          <button class="btn btn-secondary btn-sm btn-close-modal">Close</button>
        </div>
      </div>
    `;

    document.body.appendChild(this.overlay);

    this.overlay.querySelectorAll(".btn-close-modal").forEach(btn => {
      btn.addEventListener("click", () => this.close());
    });

    this.overlay.addEventListener("click", (e) => {
      if (e.target === this.overlay) this.close();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.overlay.classList.contains("open")) {
        this.close();
      }
    });
  }

  open({ title, bodyHtml, footerHtml = null }) {
    document.getElementById("modalTitle").textContent = title || "Details";
    document.getElementById("modalBody").innerHTML = bodyHtml || "";
    if (footerHtml !== null) {
      document.getElementById("modalFooter").innerHTML = footerHtml;
      document.getElementById("modalFooter").querySelectorAll(".btn-close-modal").forEach(btn => {
        btn.addEventListener("click", () => this.close());
      });
    }
    this.overlay.classList.add("open");
    document.body.style.overflow = "hidden";
  }

  close() {
    this.overlay.classList.remove("open");
    document.body.style.overflow = "";
  }
}

export const modal = new ModalService();
