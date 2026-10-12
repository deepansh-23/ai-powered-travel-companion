/**
 * Accessible Toast Notifications (Section 18).
 */

class ToastService {
  constructor() {
    this.container = document.createElement("div");
    this.container.className = "toast-container";
    this.container.setAttribute("aria-live", "polite");
    document.body.appendChild(this.container);
  }

  show(message, type = "info", duration = 4000) {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.setAttribute("role", "status");

    toast.innerHTML = `
      <span>${message}</span>
      <button class="dismiss-btn" aria-label="Close notification" style="background:none;border:none;cursor:pointer;color:inherit;font-size:1.1rem;">&times;</button>
    `;

    const closeBtn = toast.querySelector(".dismiss-btn");
    closeBtn.addEventListener("click", () => toast.remove());

    this.container.appendChild(toast);

    if (duration > 0) {
      setTimeout(() => {
        if (toast.parentElement) {
          toast.remove();
        }
      }, duration);
    }
  }

  success(msg) { this.show(msg, "success"); }
  error(msg) { this.show(msg, "error", 6000); }
  info(msg) { this.show(msg, "info"); }
}

export const toast = new ToastService();
