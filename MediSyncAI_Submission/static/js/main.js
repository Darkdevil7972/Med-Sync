document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".flash-close").forEach(btn => {
    btn.addEventListener("click", () => btn.closest(".flash").remove());
  });

  const revealItems = document.querySelectorAll(".reveal, .feature-card, .stat-card, .panel, .quick-links > a");
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    revealItems.forEach(el => observer.observe(el));
  } else {
    revealItems.forEach(el => el.classList.add("is-visible"));
  }

  const fileInput = document.querySelector('input[type="file"]');
  const fileName = document.getElementById("file-name");
  if (fileInput && fileName) {
    fileInput.addEventListener("change", () => {
      fileName.textContent = fileInput.files.length ? fileInput.files[0].name : "PDF, PNG or JPG · Maximum 8 MB";
    });
  }

  const search = document.getElementById("doc-search");
  if (search) {
    search.addEventListener("input", () => {
      const q = search.value.toLowerCase().trim();
      let visible = 0;
      document.querySelectorAll(".searchable-doc").forEach(row => {
        const match = row.dataset.search.includes(q);
        row.style.display = match ? "flex" : "none";
        if (match) visible++;
      });
      const noResults = document.getElementById("no-results");
      if (noResults) noResults.classList.toggle("hidden", visible !== 0);
    });
  }

  document.querySelectorAll("form").forEach(form => {
    form.addEventListener("submit", () => {
      const button = form.querySelector('button[type="submit"]');
      if (button && !form.classList.contains("no-loading")) {
        button.classList.add("is-loading");
        button.dataset.originalText = button.innerText;
        button.innerText = "Processing…";
      }
    });
  });

  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener("click", e => {
      const target = document.querySelector(link.getAttribute("href"));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });
});
