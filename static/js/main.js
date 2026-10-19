/**
 * FindMate - Main Client-Side JavaScript
 */

document.addEventListener("DOMContentLoaded", function () {
  // 1. Report Type Switcher (Lost vs Found)
  const lostCard = document.getElementById("select-type-lost");
  const foundCard = document.getElementById("select-type-found");
  const reportTypeInput = document.getElementById("report_type_input");
  const submitBtnText = document.getElementById("submit-btn-text");

  if (lostCard && foundCard && reportTypeInput) {
    function setReportType(type) {
      reportTypeInput.value = type;
      if (type === "lost") {
        lostCard.classList.add("selected-lost");
        foundCard.classList.remove("selected-found");
        const lostCheck = document.getElementById("lost-check");
        const foundCheck = document.getElementById("found-check");
        if (lostCheck) lostCheck.style.display = "block";
        if (foundCheck) foundCheck.style.display = "none";
        if (submitBtnText) submitBtnText.textContent = "Submit Lost Report";
        const dateLabel = document.getElementById("date-label");
        if (dateLabel) dateLabel.textContent = "Date Lost *";
      } else {
        foundCard.classList.add("selected-found");
        lostCard.classList.remove("selected-lost");
        const lostCheck = document.getElementById("lost-check");
        const foundCheck = document.getElementById("found-check");
        if (lostCheck) lostCheck.style.display = "none";
        if (foundCheck) foundCheck.style.display = "block";
        if (submitBtnText) submitBtnText.textContent = "Submit Found Item";
        const dateLabel = document.getElementById("date-label");
        if (dateLabel) dateLabel.textContent = "Date Found *";
      }
    }

    lostCard.addEventListener("click", () => setReportType("lost"));
    foundCard.addEventListener("click", () => setReportType("found"));
  }

  // 2. Photo Upload Drag & Drop and Preview
  const dropzone = document.getElementById("fm-dropzone");
  const fileInput = document.getElementById("item_photo");
  const previewBox = document.getElementById("image-preview-container");
  const previewImg = document.getElementById("image-preview-img");
  const dropzoneContent = document.getElementById("dropzone-content");
  const removePhotoBtn = document.getElementById("remove-photo-btn");

  if (dropzone && fileInput) {
    dropzone.addEventListener("click", () => fileInput.click());

    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.add("border-primary", "bg-light");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.remove("border-primary", "bg-light");
      });
    });

    dropzone.addEventListener("drop", (e) => {
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        fileInput.files = e.dataTransfer.files;
        handleFileSelect(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener("change", function () {
      if (this.files && this.files[0]) {
        handleFileSelect(this.files[0]);
      }
    });

    function handleFileSelect(file) {
      if (!file.type.match("image.*")) {
        alert("Please select a valid image file (PNG, JPG, WEBP).");
        return;
      }
      if (file.size > 5 * 1024 * 1024) {
        alert("File size exceeds 5MB limit. Please choose a smaller photo.");
        return;
      }

      const reader = new FileReader();
      reader.onload = function (e) {
        if (previewImg && previewBox && dropzoneContent) {
          previewImg.src = e.target.result;
          previewBox.style.display = "block";
          dropzoneContent.style.display = "none";
        }
      };
      reader.readAsDataURL(file);
    }

    if (removePhotoBtn) {
      removePhotoBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        fileInput.value = "";
        if (previewBox && dropzoneContent) {
          previewBox.style.display = "none";
          dropzoneContent.style.display = "block";
        }
      });
    }
  }

  // 3. Description Character Counter
  const descTextarea = document.getElementById("public-description");
  const descCounter = document.getElementById("desc-counter");
  if (descTextarea && descCounter) {
    descTextarea.addEventListener("input", function () {
      const len = this.value.length;
      descCounter.textContent = `${len} / 400`;
      if (len > 400) {
        descCounter.classList.add("text-danger");
      } else {
        descCounter.classList.remove("text-danger");
      }
    });
  }

  // 4. Auto-dismiss flash alerts after 5 seconds
  const alerts = document.querySelectorAll(".alert-dismissible");
  alerts.forEach(function (alertElem) {
    setTimeout(function () {
      try {
        const bsAlert = new bootstrap.Alert(alertElem);
        bsAlert.close();
      } catch (e) {
        alertElem.style.display = "none";
      }
    }, 6000);
  });

  // 5. Restrict all Lost/Found Date Inputs to today or earlier (Disable future dates in calendar UI)
  const dateInputs = document.querySelectorAll('input[type="date"][name="date_lost_or_found"], input[type="date"][name="date"]');
  if (dateInputs.length > 0) {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");
    const dd = String(today.getDate()).padStart(2, "0");
    const localToday = `${yyyy}-${mm}-${dd}`;

    dateInputs.forEach(function (input) {
      input.max = localToday;

      // Event listener to immediately intercept and reject any manual future date entry
      input.addEventListener("change", function () {
        if (this.value && this.value > localToday) {
          alert("Future dates are not permitted. Please select today's date or an earlier date.");
          this.value = localToday;
        }
      });
    });
  }
});
