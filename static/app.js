const state = {
  jobId: null,
  workflowState: "IDLE",
  pollTimerId: null,
  reinsertDialogShown: false,
  printMode: "duplex",
  currentJob: null,
  isUploading: false,
  isInspecting: false,
  fileMetadata: null,
};

const fallbackPrinters = [
  "EPSON_M2110_Series_68163E",
  "EPSON_M2110_Series_D9706C",
];

const elements = {
  pdfFile: document.getElementById("pdfFile"),
  dropzone: document.getElementById("dropzone"),
  dropzoneBadge: document.getElementById("dropzoneBadge"),
  dropzoneTitle: document.getElementById("dropzoneTitle"),
  dropzoneText: document.getElementById("dropzoneText"),
  dropzoneMeta: document.getElementById("dropzoneMeta"),
  dropzoneFile: document.getElementById("dropzoneFile"),
  pageRange: document.getElementById("pageRange"),
  pageRangeBadge: document.getElementById("pageRangeBadge"),
  metaFileName: document.getElementById("metaFileName"),
  metaTotalPages: document.getElementById("metaTotalPages"),
  metaFileSize: document.getElementById("metaFileSize"),
  uploadButton: document.getElementById("uploadButton"),
  printerSelect: document.getElementById("printerSelect"),
  refreshPrintersButton: document.getElementById("refreshPrintersButton"),
  summaryFile: document.getElementById("summaryFile"),
  summaryOriginalPages: document.getElementById("summaryOriginalPages"),
  summaryPages: document.getElementById("summaryPages"),
  summaryPageRange: document.getElementById("summaryPageRange"),
  summaryAdjustedLabel: document.getElementById("summaryAdjustedLabel"),
  summaryAdjustedPages: document.getElementById("summaryAdjustedPages"),
  summaryPrinter: document.getElementById("summaryPrinter"),
  workflowState: document.getElementById("workflowState"),
  currentInstruction: document.getElementById("currentInstruction"),
  printerStatus: document.getElementById("printerStatus"),
  jobStatus: document.getElementById("jobStatus"),
  startButton: document.getElementById("startButton"),
  message: document.getElementById("message"),
  reinsertDialog: document.getElementById("reinsertDialog"),
  continueButton: document.getElementById("continueButton"),
  stepUpload: document.getElementById("stepUpload"),
  stepPrinter: document.getElementById("stepPrinter"),
  stepPass1: document.getElementById("stepPass1"),
  stepPass2: document.getElementById("stepPass2"),
  selectedFileHint: document.getElementById("selectedFileHint"),
  printerCountHint: document.getElementById("printerCountHint"),
  printModeInputs: document.querySelectorAll('input[name="printMode"]'),
  stepPass2Text: document.getElementById("stepPass2Text"),
  tipPanelTitle: document.getElementById("tipPanelTitle"),
  tipList: document.getElementById("tipList"),
};

function getSelectedFile() {
  return elements.pdfFile.files[0] || null;
}

function getRequestedPageRange() {
  return elements.pageRange.value.trim();
}

function updateSelectedFileHint() {
  const file = getSelectedFile();
  elements.selectedFileHint.textContent = file ? `${file.name} ready` : "No file selected";
  elements.dropzone.classList.toggle("has-file", Boolean(file));
  elements.dropzoneBadge.textContent = file ? "File added" : "PDF or DOCX";
  elements.dropzoneTitle.textContent = file ? "File loaded for this print session" : "Drop your print file here";
  elements.dropzoneText.textContent = file
    ? (state.isInspecting ? "Reading document details and total page count..." : "Review the page range, then click Prepare Print File")
    : "or click to browse from this device";
  elements.dropzoneMeta.textContent = file
    ? "You can replace this file at any time before preparing the print-ready copy."
    : "DOCX files are converted to PDF before the print workflow starts.";
  elements.dropzoneFile.hidden = !file;
  elements.dropzoneFile.textContent = file ? file.name : "";
}

function resetFileMetadata() {
  state.fileMetadata = null;
  elements.metaFileName.textContent = "-";
  elements.metaTotalPages.textContent = "-";
  elements.metaFileSize.textContent = "-";
}

function renderFileMetadata(metadata) {
  state.fileMetadata = metadata;
  elements.metaFileName.textContent = metadata.file_name || "-";
  elements.metaTotalPages.textContent = metadata.total_pages != null ? String(metadata.total_pages) : "-";
  elements.metaFileSize.textContent = metadata.file_size_label || "-";
}

function updatePageRangeBadge() {
  const pageRange = getRequestedPageRange();
  elements.pageRangeBadge.textContent = pageRange ? `Range: ${pageRange}` : "All pages";
}

function setPendingFile(file) {
  const dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);
  elements.pdfFile.files = dataTransfer.files;
  resetPreparedJob();
  resetFileMetadata();
  updateSelectedFileHint();
  updateUploadButton();
  inspectSelectedFile();
}

async function inspectSelectedFile() {
  const file = getSelectedFile();
  if (!file) {
    resetFileMetadata();
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  state.isInspecting = true;
  updateSelectedFileHint();

  try {
    const response = await fetch("/api/inspect", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Unable to inspect the document.");
    }
    renderFileMetadata(data);
    if (!getRequestedPageRange()) {
      elements.pageRange.placeholder = `Choose pages from 1-${data.total_pages}, or leave blank for all pages`;
    }
  } catch (error) {
    resetFileMetadata();
    setMessage(error.message, "error");
  } finally {
    state.isInspecting = false;
    updateSelectedFileHint();
  }
}

function resetPreparedJob() {
  state.jobId = null;
  state.currentJob = null;
  state.workflowState = "IDLE";
  state.reinsertDialogShown = false;
  elements.summaryFile.textContent = "-";
  elements.summaryOriginalPages.textContent = "-";
  elements.summaryPages.textContent = "-";
  elements.summaryPageRange.textContent = getRequestedPageRange() || "All pages";
  elements.summaryAdjustedPages.textContent = "-";
  elements.summaryPrinter.textContent = elements.printerSelect.value || "-";
  elements.workflowState.textContent = "IDLE";
  elements.currentInstruction.textContent = "Choose a PDF, set a page range if needed, then prepare the print file.";
  elements.printerStatus.textContent = "Printer: -";
  elements.jobStatus.textContent = "Job: -";
  updateStepCards({});
}

async function fetchPrinters() {
  console.log("[Duplex Print Helper] Fetching printers from /api/printers");
  setMessage("Loading printers...");
  try {
    const response = await fetch("/api/printers");
    console.log("[Duplex Print Helper] /api/printers status:", response.status, response.statusText);

    let data;
    try {
      data = await response.json();
    } catch (error) {
      throw new Error("Printer API did not return valid JSON.");
    }

    console.log("[Duplex Print Helper] Printer API payload:", data);

    if (!response.ok) {
      throw new Error(data.error || "Unable to load printers.");
    }

    if (!data || !Array.isArray(data.printers)) {
      throw new Error("Printer API payload is missing the printers array.");
    }

    populatePrinterDropdown(data.printers);
    elements.printerCountHint.textContent = `${data.printers.length} printer${data.printers.length === 1 ? "" : "s"} found`;

    if (data.warning) {
      setMessage(data.warning, "warning");
    } else {
      setMessage("");
    }
  } catch (error) {
    console.error("[Duplex Print Helper] Printer fetch failed:", error);
    populatePrinterDropdown(fallbackPrinters);
    elements.printerCountHint.textContent = "Using fallback printers";
    setMessage(`${error.message} Using fallback printers.`, "warning");
  }
  updateStartButton();
}

async function uploadPdf() {
  if (state.isUploading) {
    return;
  }

  const file = getSelectedFile();
  if (!file) {
    setMessage("Choose a PDF or DOCX file first.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  if (getRequestedPageRange()) {
    formData.append("page_range", getRequestedPageRange());
  }
  state.isUploading = true;
  updateUploadButton();
  setMessage("Preparing print file...");

  try {
    const response = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Upload failed.");
    }

    state.jobId = data.job_id;
    state.reinsertDialogShown = false;
    renderJob(data);
    setMessage(
      data.selected_page_range === "All pages"
        ? "PDF prepared for printing."
        : `PDF prepared with pages ${data.selected_page_range}.`,
    );
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    state.isUploading = false;
    updateUploadButton();
  }
}

async function startDuplexPrint() {
  if (!state.jobId) {
    setMessage("Prepare a print file first.", "error");
    return;
  }

  const printerName = elements.printerSelect.value;
  if (!printerName) {
    setMessage("Select a printer first.", "error");
    return;
  }

  setMessage(state.printMode === "single" ? "Sending document to printer..." : "Sending pass 1 to printer...");
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ printer_name: printerName, print_mode: state.printMode }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Pass 1 failed.");
    }

    state.reinsertDialogShown = false;
    renderJob(data);
    ensurePolling();
    setMessage(
      state.printMode === "single"
        ? "Print job submitted. Waiting for printer to finish."
        : "Pass 1 submitted. Waiting for printer to finish.",
    );
  } catch (error) {
    setMessage(error.message, "error");
  }
}

async function continueDuplexPrint() {
  setMessage("Sending pass 2 to printer...");
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/continue`, {
      method: "POST",
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Pass 2 failed.");
    }

    elements.reinsertDialog.close();
    state.reinsertDialogShown = true;
    renderJob(data);
    ensurePolling();
    setMessage("Pass 2 submitted. Waiting for printer to finish.");
  } catch (error) {
    setMessage(error.message, "error");
  }
}

async function pollActiveStatuses() {
  if (!state.jobId) {
    stopPolling();
    return;
  }

  try {
    const jobResponse = await fetch(`/api/jobs/${state.jobId}`);
    const jobData = await jobResponse.json();
    if (!jobResponse.ok) {
      throw new Error(jobData.error || "Unable to refresh job status.");
    }

    console.log("[Duplex Print Helper] Job status payload:", jobData);
    renderJob(jobData);

    if (jobData.printer_name) {
      await fetchPrinterStatus(jobData.printer_name);
    }

    if (jobData.active_cups_job_id) {
      await fetchCupsJobStatus(jobData.active_cups_job_id);
    }

    if (jobData.state === "WAITING_FOR_REINSERT" && !state.reinsertDialogShown) {
      state.reinsertDialogShown = true;
      setMessage("Pass 1 completed. Rotate and reinsert the pages to continue.");
      elements.reinsertDialog.showModal();
    }

    if (jobData.state === "FAILED") {
      stopPolling();
      setMessage(jobData.error_message || "Print job failed.", "error");
      return;
    }

    if (jobData.state === "COMPLETED") {
      stopPolling();
      setMessage(jobData.print_mode === "single" ? "Single-sided printing completed." : "Duplex printing completed.");
      return;
    }

    if (!["PRINTING_PASS_1", "PRINTING_PASS_2"].includes(jobData.state)) {
      stopPolling();
    }
  } catch (error) {
    console.error("[Duplex Print Helper] Polling failed:", error);
    stopPolling();
    setMessage(error.message, "error");
  }
}

async function fetchPrinterStatus(printerName) {
  const response = await fetch(`/api/printer/status/${encodeURIComponent(printerName)}`);
  const data = await response.json();
  console.log("[Duplex Print Helper] Printer status payload:", data);
  if (!response.ok) {
    throw new Error(data.error || "Unable to load printer status.");
  }
  elements.printerStatus.textContent = `Printer: ${data.state}`;
}

async function fetchCupsJobStatus(cupsJobId) {
  const response = await fetch(`/api/job/status/${cupsJobId}`);
  const data = await response.json();
  console.log("[Duplex Print Helper] CUPS job status payload:", data);
  if (!response.ok) {
    throw new Error(data.error || "Unable to load print job status.");
  }
  elements.jobStatus.textContent = `Job: ${data.state}`;
}

function renderJob(job) {
  state.currentJob = job;
  state.workflowState = job.state;
  state.printMode = job.print_mode || state.printMode;
  elements.summaryFile.textContent = job.file_name || "-";
  elements.summaryOriginalPages.textContent = job.original_total_pages ?? job.total_pages ?? "-";
  elements.summaryPages.textContent = job.total_pages ?? "-";
  elements.summaryPageRange.textContent = job.selected_page_range || "All pages";
  elements.summaryAdjustedPages.textContent =
    state.printMode === "single" ? (job.total_pages ?? "-") : (job.adjusted_total_pages ?? "-");
  elements.summaryPrinter.textContent = job.printer_name || elements.printerSelect.value || "-";
  elements.workflowState.textContent = job.state;
  elements.printerStatus.textContent = `Printer: ${job.printer_status || "-"}`;
  elements.jobStatus.textContent = `Job: ${job.job_status || "-"}`;
  elements.currentInstruction.textContent = getInstructionText(job);
  updatePrintModeUI();

  if (job.printer_name) {
    elements.printerSelect.value = job.printer_name;
  }

  updateStepCards(job);
  updateStartButton();
}

function updateUploadButton() {
  const isBusy = ["PRINTING_PASS_1", "WAITING_FOR_REINSERT", "PRINTING_PASS_2"].includes(state.workflowState);
  const canUpload = Boolean(getSelectedFile()) && !state.isUploading && !isBusy;
  elements.uploadButton.disabled = !canUpload;
  elements.pageRange.disabled = isBusy || state.isUploading;
  elements.dropzone.classList.toggle("is-disabled", isBusy || state.isUploading);
}

function populatePrinterDropdown(printers) {
  console.log("[Duplex Print Helper] Populating printer dropdown with:", printers);
  elements.printerSelect.innerHTML = '<option value="">Select a printer</option>';

  printers.forEach((printer) => {
    const option = document.createElement("option");
    option.value = printer;
    option.textContent = printer;
    elements.printerSelect.appendChild(option);
  });

  console.log(
    "[Duplex Print Helper] Printer dropdown populated. option_count=",
    elements.printerSelect.options.length,
  );
}

function updateStartButton() {
  const isPrintLocked = ["PRINTING_PASS_1", "WAITING_FOR_REINSERT", "PRINTING_PASS_2"].includes(state.workflowState);
  const canStart =
    Boolean(state.jobId) &&
    Boolean(elements.printerSelect.value) &&
    state.workflowState === "IDLE";
  elements.startButton.disabled = !canStart;
  elements.pdfFile.disabled = state.isUploading || isPrintLocked;
  elements.refreshPrintersButton.disabled = ["PRINTING_PASS_1", "PRINTING_PASS_2"].includes(state.workflowState);
  elements.printModeInputs.forEach((input) => {
    input.disabled = isPrintLocked;
  });
  updateUploadButton();
}

function updateStepCards(job) {
  const cards = [
    elements.stepUpload,
    elements.stepPrinter,
    elements.stepPass1,
    elements.stepPass2,
  ];

  cards.forEach((card) => {
    card.classList.remove("is-active", "is-done");
  });

  if (!job.file_name || job.file_name === "-") {
    elements.stepUpload.classList.add("is-active");
    return;
  }

  elements.stepUpload.classList.add("is-done");

  if (!job.printer_name) {
    elements.stepPrinter.classList.add("is-active");
    return;
  }

  elements.stepPrinter.classList.add("is-done");

  if (job.state === "IDLE") {
    elements.stepPass1.classList.add("is-active");
    return;
  }

  if (job.state === "PRINTING_PASS_1") {
    elements.stepPass1.classList.add("is-active");
    return;
  }

  elements.stepPass1.classList.add("is-done");

  if (job.print_mode === "single") {
    if (job.state === "COMPLETED") {
      elements.stepPass2.classList.add("is-done");
    }
    return;
  }

  if (["WAITING_FOR_REINSERT", "PRINTING_PASS_2", "FAILED"].includes(job.state)) {
    elements.stepPass2.classList.add("is-active");
    return;
  }

  if (job.state === "COMPLETED") {
    elements.stepPass2.classList.add("is-done");
  }
}

function getInstructionText(job) {
  if (!job.file_name) {
    return "Choose a PDF, set a page range if needed, then prepare the print file.";
  }

  if (!job.printer_name && job.state === "IDLE") {
    return "Select a printer, then review the summary before starting.";
  }

  if (job.state === "IDLE") {
    return job.print_mode === "single"
      ? "Click Start Print to print the document."
      : "Click Start Duplex Print to begin.";
  }

  if (job.state === "PRINTING_PASS_1") {
    return job.print_mode === "single"
      ? "Printing your document. Please wait until it finishes."
      : "Printing the first pass. Wait until printing finishes before handling the paper.";
  }

  if (job.state === "WAITING_FOR_REINSERT") {
    return "Rotate the full stack 180 degrees, do not flip it, then reinsert and continue.";
  }

  if (job.state === "PRINTING_PASS_2") {
    return "Printing the second pass. Please wait until it finishes.";
  }

  if (job.state === "COMPLETED") {
    return job.print_mode === "single"
      ? "Printing is complete. Remove the document from the output tray."
      : "Duplex printing is complete. Remove the document from the output tray.";
  }

  if (job.state === "FAILED") {
    return job.error_message || "The print workflow stopped because the printer or job failed.";
  }

  return "Follow the on-screen steps.";
}

function ensurePolling() {
  if (state.pollTimerId !== null) {
    return;
  }
  state.pollTimerId = window.setInterval(pollActiveStatuses, 2000);
}

function stopPolling() {
  if (state.pollTimerId !== null) {
    window.clearInterval(state.pollTimerId);
    state.pollTimerId = null;
  }
}

function setMessage(text, tone = "info") {
  elements.message.textContent = text;
  elements.message.classList.toggle("error", tone === "error");
  elements.message.classList.toggle("warning", tone === "warning");
}

function updatePrintModeUI() {
  const isSingle = state.printMode === "single";
  elements.startButton.textContent = isSingle ? "Start Print" : "Start Duplex Print";
  elements.summaryAdjustedLabel.textContent = isSingle ? "Pages" : "Pages to Print";
  elements.stepPass2Text.textContent = isSingle
    ? "Single-sided printing finishes after one print pass."
    : "When Pass 1 completes, rotate the stack 180 degrees, do not flip it, reinsert it, then continue.";
  elements.tipPanelTitle.textContent = isSingle ? "Single-Sided Print" : "Quick Reminder";
  elements.tipList.innerHTML = isSingle
    ? "<li>Your document prints in one pass.</li><li>Wait until printing finishes before removing pages.</li>"
    : "<li>Wait for Pass 1 to finish completely.</li><li>Rotate the whole stack 180 degrees.</li><li>Do not flip the pages.</li><li>Reinsert the stack and continue.</li>";

  elements.printModeInputs.forEach((input) => {
    input.checked = input.value === state.printMode;
  });
}

elements.pdfFile.addEventListener("change", () => {
  resetPreparedJob();
  resetFileMetadata();
  updateSelectedFileHint();
  updateUploadButton();
  inspectSelectedFile();
});

elements.dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  if (elements.dropzone.classList.contains("is-disabled")) {
    return;
  }
  elements.dropzone.classList.add("is-dragover");
});

elements.dropzone.addEventListener("dragleave", () => {
  elements.dropzone.classList.remove("is-dragover");
});

elements.dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  elements.dropzone.classList.remove("is-dragover");
  if (elements.dropzone.classList.contains("is-disabled")) {
    return;
  }

  const [file] = event.dataTransfer?.files || [];
  if (!file) {
    return;
  }
  if (!file.name.toLowerCase().endsWith(".pdf") && !file.name.toLowerCase().endsWith(".docx")) {
    setMessage("Only PDF and DOCX files are supported.", "error");
    return;
  }

  setPendingFile(file);
  setMessage("File ready. Review the page range and click Prepare Print File.");
});

elements.refreshPrintersButton.addEventListener("click", fetchPrinters);
elements.uploadButton.addEventListener("click", uploadPdf);
elements.startButton.addEventListener("click", startDuplexPrint);
elements.continueButton.addEventListener("click", continueDuplexPrint);
elements.pageRange.addEventListener("input", updatePageRangeBadge);
elements.pageRange.addEventListener("change", () => {
  if (getSelectedFile() && !state.isUploading && state.workflowState === "IDLE") {
    resetPreparedJob();
    setMessage("Page range updated. Click Prepare Print File to apply it.");
  }
  updatePageRangeBadge();
  updateUploadButton();
});
elements.printModeInputs.forEach((input) => {
  input.addEventListener("change", () => {
    state.printMode = input.value;
    updatePrintModeUI();
    if (!state.currentJob) {
      elements.summaryAdjustedPages.textContent = "-";
    } else {
      elements.summaryAdjustedPages.textContent =
        state.printMode === "single"
          ? (state.currentJob.total_pages ?? "-")
          : (state.currentJob.adjusted_total_pages ?? "-");
    }
  });
});
elements.printerSelect.addEventListener("change", () => {
  elements.summaryPrinter.textContent = elements.printerSelect.value || "-";
  elements.printerCountHint.textContent = elements.printerSelect.value
    ? `Selected: ${elements.printerSelect.value}`
    : "Choose a printer";
  updateStartButton();
});

updateSelectedFileHint();
updatePageRangeBadge();
updatePrintModeUI();
updateUploadButton();
fetchPrinters();
