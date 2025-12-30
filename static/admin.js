// admin.js — Neon styled Admin interactivity
document.addEventListener("DOMContentLoaded", () => {
  const rows = document.querySelectorAll(".admin-table tr");
  rows.forEach(row => {
    row.addEventListener("mouseenter", () => {
      row.style.background = "rgba(255, 187, 64, 0.08)";
    });
    row.addEventListener("mouseleave", () => {
      row.style.background = "transparent";
    });
  });

  const flash = (msg, type = "info") => {
    const div = document.createElement("div");
    div.className = `flash ${type}`;
    div.textContent = msg;
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 2500);
  };

  // Example: allow removing users dynamically
  document.querySelectorAll("[data-remove-user]").forEach(btn => {
    btn.addEventListener("click", async e => {
      const user = e.target.dataset.removeUser;
      if (!confirm(`Delete user ${user}?`)) return;
      const res = await fetch(`/api/delete_user/${user}`, { method: "DELETE" });
      if (res.ok) {
        flash(`Removed ${user}`, "ok");
        e.target.closest("tr").remove();
      } else flash("Error removing user", "error");
    });
  });
});
