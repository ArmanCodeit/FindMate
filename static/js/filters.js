/**
 * FindMate - Listing and Filter Controls
 */

document.addEventListener("DOMContentLoaded", function () {
  const filterForm = document.getElementById("fm-filter-form");
  const sortSelect = document.getElementById("sort-select");
  const clearFiltersBtn = document.getElementById("clear-filters-btn");

  if (filterForm && sortSelect) {
    sortSelect.addEventListener("change", function () {
      filterForm.submit();
    });
  }

  if (clearFiltersBtn) {
    clearFiltersBtn.addEventListener("click", function (e) {
      e.preventDefault();
      window.location.href = window.location.pathname;
    });
  }

  // Gallery Thumbnail Switcher on Item Details
  const mainImage = document.getElementById("detail-main-img");
  const thumbs = document.querySelectorAll(".fm-gallery-thumb");

  if (mainImage && thumbs.length > 0) {
    thumbs.forEach((thumb) => {
      thumb.addEventListener("click", function () {
        const thumbImg = this.querySelector("img");
        const newSrc = this.getAttribute("data-src") || (thumbImg ? thumbImg.src : null);
        if (newSrc) {
          thumbs.forEach((t) => t.classList.remove("active"));
          this.classList.add("active");
          mainImage.src = newSrc;
        }
      });
    });
  }
});
