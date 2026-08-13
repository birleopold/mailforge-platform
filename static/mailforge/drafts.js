(() => {
  const form = document.getElementById("compose-form");
  if (!form) return;

  const autosaveUrl = form.dataset.autosaveUrl;
  const draftIdInput = document.getElementById("draft-id");
  const status = document.getElementById("draft-save-status");
  const attachmentInput = form.querySelector('input[type="file"][name="attachments"]');
  let timer = null;
  let saving = false;
  let dirty = false;

  const hasDraftContent = () => {
    const names = ["to", "cc", "bcc", "subject", "body"];
    return names.some((name) => {
      const input = form.elements.namedItem(name);
      return input && String(input.value || "").trim();
    });
  };

  const setStatus = (message) => {
    if (status) status.textContent = message;
  };

  const autosave = async () => {
    timer = null;
    if (saving || !dirty || !autosaveUrl) return;
    if (!hasDraftContent() && !(draftIdInput && draftIdInput.value)) return;

    saving = true;
    setStatus("Saving…");
    const data = new FormData(form);
    // File uploads are intentionally excluded from background autosave to avoid
    // repeatedly uploading the same large file. The explicit Save draft button
    // stores newly selected files.
    data.delete("attachments");

    try {
      const response = await fetch(autosaveUrl, {
        method: "POST",
        body: data,
        credentials: "same-origin",
        headers: {"X-Requested-With": "XMLHttpRequest"},
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setStatus(payload.detail || "Autosave paused until the draft fields are valid.");
        return;
      }
      if (draftIdInput && payload.draft_id) draftIdInput.value = payload.draft_id;
      dirty = false;
      const stamp = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
      setStatus(`Saved ${stamp}`);
    } catch (_error) {
      setStatus("Autosave unavailable. Use Save draft.");
    } finally {
      saving = false;
      if (dirty) schedule();
    }
  };

  const schedule = () => {
    dirty = true;
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(autosave, 3500);
  };

  form.addEventListener("input", (event) => {
    if (event.target === attachmentInput) return;
    schedule();
  });
  form.addEventListener("change", (event) => {
    if (event.target === attachmentInput) {
      if (attachmentInput && attachmentInput.files.length) {
        setStatus("Attachment selected — use Save draft to store new files.");
      }
      return;
    }
    schedule();
  });
  form.addEventListener("submit", () => {
    if (timer) window.clearTimeout(timer);
  });
})();
