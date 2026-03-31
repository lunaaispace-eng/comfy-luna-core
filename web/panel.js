/**
 * comfy-luna-core - Main panel UI
 *
 * Creates a chat panel in ComfyUI's menu for interacting with AI agents.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

class LunaCorePanel {
  constructor() {
    this.messages = [];
    this.isStreaming = false;
    this.currentAgent = "ollama";
    this.currentModel = "";
    this.availableAgents = {};
    this.systemInfo = null;
    this.includeWorkflow = false;
    this.contextMode = localStorage.getItem("luna-context-mode") || "standard";
    this.knowledgeCategories = null; // null = all enabled
    this.contextOptionsOpen = false;

    this.lastDetectedWorkflow = null;

    this.pendingImages = []; // [{data, media_type, filename}]

    // Display mode: "sidebar" (docked in ComfyUI sidebar) or "floating" (draggable window)
    this.mode = localStorage.getItem("luna-mode") || "sidebar";
    this.sidebarAvailable = false;
    this.sidebarElement = null;
    this.menuButton = null;
    this.floatingButtonContainer = null;

    this.container = null;
    this.messagesContainer = null;
    this.inputField = null;
    this.sendButton = null;
    this.agentSelect = null;
    this.modelSelect = null;
    this.workflowToggle = null;
    this.imagePreviewStrip = null;
  }

  async init() {
    await this.refreshAgents();
    this.createPanel();
    this.loadSavedCategories();

    // Detect sidebar API availability
    this.sidebarAvailable = !!(app.extensionManager?.registerSidebarTab);

    // Always register the sidebar tab so the icon is always visible
    if (this.sidebarAvailable) {
      this._registerSidebarTab();
    }

    if (this.sidebarAvailable && this.mode === "sidebar") {
      // Sidebar mode — content will be mounted when the tab's render() fires
      this.container.classList.add("cp-sidebar-mode");
      this.container.classList.remove("cp-floating-mode");
      this._updateModeToggleButton();
    } else {
      this.mode = "floating";
      this._initFloating();
    }
  }

  async refreshAgents() {
    try {
      const response = await api.fetchApi("/luna/agents");
      if (response.ok) {
        this.availableAgents = await response.json();
      }
    } catch (e) {
      console.error("Failed to fetch agents:", e);
    }
  }

  async refreshSystemInfo() {
    try {
      const response = await api.fetchApi("/luna/system");
      if (response.ok) {
        this.systemInfo = await response.json();
        this.updateSystemDisplay();
      }
    } catch (e) {
      console.error("Failed to fetch system info:", e);
    }
  }

  async fetchKnowledgeCategories() {
    try {
      const response = await api.fetchApi("/luna/knowledge-categories");
      if (response.ok) {
        const categories = await response.json();
        this.updateCategoryCheckboxes(categories);
      }
    } catch (e) {
      console.error("Failed to fetch knowledge categories:", e);
    }
  }

  loadSavedCategories() {
    const saved = localStorage.getItem("luna-categories");
    if (saved) {
      try {
        this.knowledgeCategories = JSON.parse(saved);
      } catch (e) {
        this.knowledgeCategories = null;
      }
    }
  }

  createPanel() {
    this.container = document.createElement("div");
    this.container.id = "luna-panel";
    this.container.innerHTML = `
      <div class="cp-header">
        <h3>Luna Core</h3>
        <select class="cp-agent-select"></select>
        <select class="cp-model-select" style="display:none"></select>
        <button class="cp-new-chat" title="New Chat">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="12" y1="18" x2="12" y2="12"/>
            <line x1="9" y1="15" x2="15" y2="15"/>
          </svg>
        </button>
        <button class="cp-mode-toggle" title="Pop out to floating window">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
        </button>
        <button class="cp-close" title="Close">&times;</button>
      </div>
      <div class="cp-system-info">
        <span class="gpu-info">Loading system info...</span>
      </div>
      <div class="cp-context-panel">
        <button class="cp-context-toggle">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v18M3 12h18"/></svg>
          Context Options
          <span class="cp-context-mode-badge">${this.contextMode}</span>
        </button>
        <div class="cp-context-body" style="display:none">
          <div class="cp-context-row">
            <label>Context mode:</label>
            <select class="cp-context-mode">
              <option value="minimal"${this.contextMode === "minimal" ? " selected" : ""}>Minimal (5K)</option>
              <option value="standard"${this.contextMode === "standard" ? " selected" : ""}>Standard (15K)</option>
              <option value="verbose"${this.contextMode === "verbose" ? " selected" : ""}>Verbose (30K)</option>
            </select>
          </div>
          <div class="cp-categories">
            <label>Knowledge:</label>
            <div class="cp-category-list">Loading...</div>
          </div>
        </div>
      </div>
      <div class="cp-messages"></div>
      <div class="cp-workflow-context">
        <label class="cp-toggle">
          <input type="checkbox" class="cp-workflow-toggle">
          <span class="toggle-label">Include current workflow</span>
        </label>
        <span class="workflow-status"></span>
      </div>
      <div class="cp-persistent-actions" style="display:none">
        <span class="cp-detected-label">Workflow detected</span>
        <button class="cp-btn-validate">Validate</button>
        <button class="cp-btn-apply">Apply</button>
        <button class="cp-btn-log">Log</button>
      </div>
      <div class="cp-image-preview" style="display:none"></div>
      <div class="cp-input-area">
        <button class="cp-upload" title="Attach image for analysis">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
          </svg>
        </button>
        <input type="file" class="cp-file-input" accept="image/png,image/jpeg,image/webp,image/gif" multiple style="display:none">
        <textarea
          class="cp-input"
          placeholder="Ask me to create or modify a workflow..."
          rows="2"
        ></textarea>
        <button class="cp-send">Send</button>
      </div>
      <div class="cp-footer">
        Developed by <a href="https://github.com/lunaaispace-eng" target="_blank">lunaaispace</a>
      </div>
    `;

    this.applyStyles();

    // Get references
    this.messagesContainer = this.container.querySelector(".cp-messages");
    this.inputField = this.container.querySelector(".cp-input");
    this.sendButton = this.container.querySelector(".cp-send");
    this.agentSelect = this.container.querySelector(".cp-agent-select");
    this.modelSelect = this.container.querySelector(".cp-model-select");
    this.workflowToggle = this.container.querySelector(".cp-workflow-toggle");
    this.workflowStatus = this.container.querySelector(".workflow-status");
    this.imagePreviewStrip = this.container.querySelector(".cp-image-preview");
    this.fileInput = this.container.querySelector(".cp-file-input");
    this.uploadButton = this.container.querySelector(".cp-upload");

    this.updateAgentSelect();

    // Event listeners
    this.sendButton.addEventListener("click", () => this.sendMessage());
    this.inputField.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    this.agentSelect.addEventListener("change", (e) => {
      this.currentAgent = e.target.value;
      this.updateModelSelect();
    });

    this.modelSelect.addEventListener("change", (e) => {
      this.currentModel = e.target.value;
    });

    this.workflowToggle.addEventListener("change", (e) => {
      this.includeWorkflow = e.target.checked;
      this.updateWorkflowStatus();
    });

    // Image upload
    this.uploadButton.addEventListener("click", () => this.fileInput.click());
    this.fileInput.addEventListener("change", (e) => {
      this.handleImageFiles(e.target.files);
      e.target.value = "";
    });

    // Drag-and-drop on input area
    const inputArea = this.container.querySelector(".cp-input-area");
    inputArea.addEventListener("dragover", (e) => {
      e.preventDefault();
      inputArea.style.borderColor = "var(--cp-accent)";
    });
    inputArea.addEventListener("dragleave", () => {
      inputArea.style.borderColor = "";
    });
    inputArea.addEventListener("drop", (e) => {
      e.preventDefault();
      inputArea.style.borderColor = "";
      const files = [...e.dataTransfer.files].filter((f) => f.type.startsWith("image/"));
      if (files.length) this.handleImageFiles(files);
    });

    // Paste images from clipboard
    this.inputField.addEventListener("paste", (e) => {
      const items = [...(e.clipboardData?.items || [])];
      const imageItems = items.filter((item) => item.type.startsWith("image/"));
      if (imageItems.length) {
        e.preventDefault();
        const files = imageItems.map((item) => item.getAsFile()).filter(Boolean);
        this.handleImageFiles(files);
      }
    });

    this.container.querySelector(".cp-close").addEventListener("click", () => {
      this.hide();
    });

    this.container.querySelector(".cp-mode-toggle").addEventListener("click", () => {
      this.switchMode(this.mode === "sidebar" ? "floating" : "sidebar");
    });

    this.container.querySelector(".cp-new-chat").addEventListener("click", () => {
      this.resetChat();
    });

    // Context options toggle
    const ctxToggle = this.container.querySelector(".cp-context-toggle");
    const ctxBody = this.container.querySelector(".cp-context-body");
    ctxToggle.addEventListener("click", () => {
      this.contextOptionsOpen = !this.contextOptionsOpen;
      ctxBody.style.display = this.contextOptionsOpen ? "block" : "none";
      if (this.contextOptionsOpen) {
        this.fetchKnowledgeCategories();
      }
    });

    // Context mode change
    this.container.querySelector(".cp-context-mode").addEventListener("change", (e) => {
      this.contextMode = e.target.value;
      localStorage.setItem("luna-context-mode", this.contextMode);
      this.container.querySelector(".cp-context-mode-badge").textContent = this.contextMode;
    });

    // Persistent actions bar
    const persistentBar = this.container.querySelector(".cp-persistent-actions");
    persistentBar.querySelector(".cp-btn-validate").addEventListener("click", async () => {
      if (!this.lastDetectedWorkflow) return;
      await this.validateWorkflowUI(this.lastDetectedWorkflow, persistentBar);
    });
    persistentBar.querySelector(".cp-btn-apply").addEventListener("click", async () => {
      if (!this.lastDetectedWorkflow) return;
      const btn = persistentBar.querySelector(".cp-btn-apply");
      btn.textContent = "Validating...";
      btn.disabled = true;
      try {
        // Validate first
        const valResponse = await api.fetchApi("/luna/validate-workflow", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workflow: this.lastDetectedWorkflow }),
        });
        const valResult = await valResponse.json();
        if (!valResult.valid) {
          btn.textContent = "Invalid!";
          btn.style.background = "var(--cp-danger)";
          await this.validateWorkflowUI(this.lastDetectedWorkflow, persistentBar);
          setTimeout(() => { btn.textContent = "Apply"; btn.style.background = ""; btn.disabled = false; }, 2000);
          return;
        }
        // Apply
        btn.textContent = "Applying...";
        await this.applyWorkflow(this.lastDetectedWorkflow);
        btn.textContent = "Applied!";
        btn.style.background = "var(--cp-success)";
      } catch (e) {
        btn.textContent = "Failed";
        btn.style.background = "var(--cp-danger)";
      }
      setTimeout(() => {
        btn.textContent = "Apply";
        btn.style.background = "";
        btn.disabled = false;
      }, 2000);
    });
    persistentBar.querySelector(".cp-btn-log").addEventListener("click", () => {
      if (!this.lastDetectedWorkflow) return;
      console.log("[luna-core] Workflow JSON:", this.lastDetectedWorkflow);
      console.log("[luna-core] Workflow (formatted):", JSON.stringify(this.lastDetectedWorkflow, null, 2));
      const btn = persistentBar.querySelector(".cp-btn-log");
      btn.textContent = "Logged!";
      setTimeout(() => { btn.textContent = "Log"; }, 1500);
    });

  }

  applyStyles() {
    if (document.getElementById("luna-styles")) return;

    const styles = document.createElement("style");
    styles.id = "luna-styles";
    styles.textContent = `
      :root {
        --cp-bg: var(--comfy-menu-bg, #1a1a2e);
        --cp-bg-secondary: var(--comfy-input-bg, #2a2a3e);
        --cp-border: var(--border-color, #333);
        --cp-text: var(--fg-color, #fff);
        --cp-text-dim: var(--fg-color, #888);
        --cp-accent: var(--p-button-text-primary-color, #4a9eff);
        --cp-success: #28a745;
        --cp-danger: #dc3545;
        --cp-warning: #ffc107;
        --cp-radius: 8px;
      }

      #luna-panel {
        position: fixed;
        top: 50px;
        right: 20px;
        width: 420px;
        height: 620px;
        background: var(--cp-bg);
        border: 1px solid var(--cp-border);
        border-radius: var(--cp-radius);
        display: flex;
        flex-direction: column;
        z-index: 10000;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5);
        font-family: system-ui, -apple-system, sans-serif;
        font-size: 14px;
        color: var(--cp-text);
      }

      /* Header — drag handle */
      .cp-header {
        display: flex;
        align-items: center;
        padding: 10px 12px;
        border-bottom: 1px solid var(--cp-border);
        cursor: grab;
        user-select: none;
        gap: 8px;
      }
      .cp-header h3 {
        margin: 0;
        flex-grow: 1;
        font-size: 15px;
        font-weight: 600;
      }
      .cp-agent-select, .cp-model-select {
        background: var(--cp-bg-secondary);
        color: var(--cp-text);
        border: 1px solid var(--cp-border);
        border-radius: 4px;
        padding: 4px 6px;
        font-size: 12px;
        max-width: 120px;
      }
      .cp-new-chat, .cp-close {
        background: none;
        border: none;
        color: var(--cp-text-dim);
        cursor: pointer;
        padding: 4px 6px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .cp-new-chat:hover, .cp-close:hover {
        color: var(--cp-text);
        background: rgba(255,255,255,0.1);
      }
      .cp-close { font-size: 22px; line-height: 1; }

      /* System info */
      .cp-system-info {
        padding: 6px 12px;
        font-size: 11px;
        color: var(--cp-text-dim);
        background: var(--cp-bg-secondary);
        border-bottom: 1px solid var(--cp-border);
      }

      /* Context panel */
      .cp-context-panel {
        border-bottom: 1px solid var(--cp-border);
      }
      .cp-context-toggle {
        display: flex;
        align-items: center;
        gap: 6px;
        width: 100%;
        padding: 6px 12px;
        background: none;
        border: none;
        color: var(--cp-text-dim);
        cursor: pointer;
        font-size: 12px;
        text-align: left;
      }
      .cp-context-toggle:hover { color: var(--cp-text); background: rgba(255,255,255,0.03); }
      .cp-context-mode-badge {
        margin-left: auto;
        background: var(--cp-bg-secondary);
        padding: 1px 6px;
        border-radius: 3px;
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .cp-context-body {
        padding: 8px 12px;
        background: var(--cp-bg-secondary);
        border-top: 1px solid var(--cp-border);
      }
      .cp-context-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
      }
      .cp-context-row label { font-size: 12px; color: var(--cp-text-dim); white-space: nowrap; }
      .cp-context-mode {
        background: var(--cp-bg);
        color: var(--cp-text);
        border: 1px solid var(--cp-border);
        border-radius: 4px;
        padding: 3px 6px;
        font-size: 12px;
        flex: 1;
      }
      .cp-categories label { font-size: 12px; color: var(--cp-text-dim); display: block; margin-bottom: 4px; }
      .cp-category-list {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        font-size: 11px;
      }
      .cp-category-chip {
        display: flex;
        align-items: center;
        gap: 3px;
        padding: 2px 8px;
        background: var(--cp-bg);
        border: 1px solid var(--cp-border);
        border-radius: 12px;
        cursor: pointer;
        user-select: none;
      }
      .cp-category-chip.active { border-color: var(--cp-accent); background: rgba(74,158,255,0.1); }
      .cp-category-chip input { display: none; }

      /* Messages */
      .cp-messages {
        flex-grow: 1;
        overflow-y: auto;
        padding: 12px;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .cp-message {
        padding: 8px 12px;
        border-radius: var(--cp-radius);
        max-width: 90%;
        word-wrap: break-word;
        line-height: 1.5;
        font-size: 13px;
      }
      .cp-message.user {
        background: var(--cp-bg-secondary);
        align-self: flex-end;
        border-bottom-right-radius: 2px;
      }
      .cp-message.assistant {
        background: var(--p-surface-700, #252538);
        color: var(--fg-color, #ddd);
        align-self: flex-start;
        border-bottom-left-radius: 2px;
      }
      .cp-message pre {
        background: #1a1a2a;
        padding: 8px;
        border-radius: 4px;
        overflow-x: auto;
        font-size: 11px;
        margin: 6px 0;
      }
      .cp-message code { font-family: monospace; }

      /* Workflow actions */
      .cp-workflow-actions {
        display: flex;
        gap: 6px;
        margin-top: 8px;
        flex-wrap: wrap;
      }
      .cp-workflow-actions button {
        border: none;
        padding: 5px 10px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 11px;
        font-weight: 500;
        color: white;
      }
      .cp-workflow-actions button:hover { opacity: 0.9; }
      .cp-btn-apply { background: var(--cp-accent); }
      .cp-btn-validate { background: #6c757d; }
      .cp-btn-log { background: #6c757d; }
      .cp-btn-fix {
        background: #6c757d;
        color: white;
        border: none;
        padding: 4px 10px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 11px;
        font-weight: 500;
      }
      .cp-btn-fix:hover { opacity: 0.9; }

      /* Validation result */
      .cp-validation-result {
        margin-top: 6px;
        padding: 6px 8px;
        border-radius: 4px;
        font-size: 11px;
      }
      .cp-validation-result.valid { background: rgba(40,167,69,0.15); color: #28a745; }
      .cp-validation-result.invalid { background: rgba(220,53,69,0.15); color: #dc3545; }
      .cp-validation-result ul { margin: 4px 0 0 16px; padding: 0; }

      /* Collapsible messages */
      .cp-message.collapsed .cp-msg-content {
        max-height: 120px;
        overflow: hidden;
        mask-image: linear-gradient(to bottom, #000 60%, transparent 100%);
        -webkit-mask-image: linear-gradient(to bottom, #000 60%, transparent 100%);
      }
      .cp-msg-toggle {
        display: block;
        background: none;
        border: none;
        color: var(--cp-accent);
        cursor: pointer;
        font-size: 11px;
        padding: 2px 0;
        margin-top: 2px;
      }
      .cp-msg-toggle:hover { text-decoration: underline; }
      .cp-validation-result.collapsed .cp-val-details { display: none; }
      .cp-val-toggle {
        background: none;
        border: none;
        color: inherit;
        cursor: pointer;
        font-size: 11px;
        opacity: 0.8;
        padding: 0;
        margin-left: 6px;
      }
      .cp-val-toggle:hover { opacity: 1; }

      /* Workflow context */
      .cp-workflow-context {
        display: flex;
        align-items: center;
        padding: 6px 12px;
        gap: 8px;
        border-top: 1px solid var(--cp-border);
        background: var(--cp-bg-secondary);
      }
      .cp-toggle {
        display: flex;
        align-items: center;
        gap: 5px;
        cursor: pointer;
        font-size: 12px;
        color: var(--cp-text-dim);
      }
      .cp-toggle input { cursor: pointer; }
      .cp-toggle:hover { color: var(--cp-text); }
      .workflow-status { font-size: 11px; color: var(--cp-text-dim); }

      /* Persistent actions bar */
      .cp-persistent-actions {
        display: flex;
        align-items: center;
        padding: 6px 12px;
        gap: 6px;
        border-top: 1px solid var(--cp-border);
        background: var(--cp-bg-secondary);
      }
      .cp-persistent-actions .cp-detected-label {
        font-size: 11px;
        color: var(--cp-text-dim);
        flex: 1;
      }
      .cp-persistent-actions button {
        border: none;
        padding: 4px 10px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 11px;
        font-weight: 500;
        color: white;
      }
      .cp-persistent-actions button:hover { opacity: 0.9; }
      .cp-persistent-actions .cp-btn-validate { background: #6c757d; }
      .cp-persistent-actions .cp-btn-apply { background: var(--cp-accent); }
      .cp-persistent-actions .cp-btn-log { background: #6c757d; }

      /* Image preview strip */
      .cp-image-preview {
        display: flex;
        gap: 6px;
        padding: 6px 10px;
        border-top: 1px solid var(--cp-border);
        background: var(--cp-bg-secondary);
        overflow-x: auto;
        flex-shrink: 0;
      }
      .cp-image-thumb {
        position: relative;
        flex-shrink: 0;
      }
      .cp-image-thumb img {
        width: 56px;
        height: 56px;
        object-fit: cover;
        border-radius: 4px;
        border: 1px solid var(--cp-border);
      }
      .cp-image-remove {
        position: absolute;
        top: -4px;
        right: -4px;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: var(--cp-danger);
        color: white;
        border: none;
        font-size: 12px;
        line-height: 1;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0;
      }
      .cp-image-remove:hover { opacity: 0.8; }

      /* Message images */
      .cp-msg-images {
        display: flex;
        gap: 4px;
        margin-bottom: 6px;
        flex-wrap: wrap;
      }
      .cp-msg-image {
        max-width: 120px;
        max-height: 90px;
        object-fit: cover;
        border-radius: 4px;
        border: 1px solid var(--cp-border);
        cursor: pointer;
      }
      .cp-msg-image:hover { opacity: 0.85; }

      /* Upload button */
      .cp-upload {
        background: none;
        border: none;
        color: var(--cp-text-dim);
        cursor: pointer;
        padding: 6px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        flex-shrink: 0;
      }
      .cp-upload:hover { color: var(--cp-text); background: rgba(255,255,255,0.1); }

      /* Input */
      .cp-input-area {
        display: flex;
        padding: 10px;
        gap: 6px;
      }
      .cp-input {
        flex-grow: 1;
        background: var(--cp-bg-secondary);
        color: var(--cp-text);
        border: 1px solid var(--cp-border);
        border-radius: 6px;
        padding: 8px 10px;
        font-size: 13px;
        resize: none;
        font-family: inherit;
      }
      .cp-input:focus {
        outline: none;
        border-color: var(--cp-accent);
      }
      .cp-send {
        background: var(--cp-accent);
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 16px;
        cursor: pointer;
        font-size: 13px;
        font-weight: 500;
      }
      .cp-send:hover { opacity: 0.9; }
      .cp-send:disabled { opacity: 0.5; cursor: not-allowed; }

      /* Footer */
      .cp-footer {
        padding: 6px 12px;
        font-size: 10px;
        color: var(--cp-text-dim);
        text-align: center;
        border-top: 1px solid var(--cp-border);
        opacity: 0.4;
      }
      .cp-footer a { color: inherit; text-decoration: none; }
      .cp-footer a:hover { text-decoration: underline; }

      /* Resize handle (bottom-right corner) */
      .cp-resize-handle {
        position: absolute;
        bottom: 0;
        right: 0;
        width: 16px;
        height: 16px;
        cursor: nwse-resize;
        background: linear-gradient(135deg, transparent 50%, var(--cp-text-dim) 50%, transparent 55%,
                    transparent 65%, var(--cp-text-dim) 65%, transparent 70%,
                    transparent 80%, var(--cp-text-dim) 80%, transparent 85%);
        opacity: 0.4;
        border-radius: 0 0 var(--cp-radius) 0;
      }
      .cp-resize-handle:hover { opacity: 0.8; }

      /* Mode toggle button */
      .cp-mode-toggle {
        background: none;
        border: none;
        color: var(--cp-text-dim);
        cursor: pointer;
        padding: 4px 6px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .cp-mode-toggle:hover {
        color: var(--cp-text);
        background: rgba(255,255,255,0.1);
      }

      /* Sidebar mode overrides */
      #luna-panel.cp-sidebar-mode {
        position: relative;
        top: auto;
        right: auto;
        left: auto;
        width: 100%;
        height: 100%;
        border: none;
        border-radius: 0;
        box-shadow: none;
        z-index: auto;
      }
      #luna-panel.cp-sidebar-mode .cp-header {
        cursor: default;
        user-select: auto;
      }
      #luna-panel.cp-sidebar-mode .cp-resize-handle {
        display: none;
      }
      #luna-panel.cp-sidebar-mode .cp-close {
        display: none;
      }

      /* Menu button */
      #luna-menu-button {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        background: transparent;
        border: none;
        color: var(--cp-text);
        cursor: pointer;
        font-size: 14px;
      }
      #luna-menu-button:hover {
        background: var(--cp-bg-secondary);
        border-radius: 4px;
      }

      .luna-hidden { display: none !important; }

      /* Thinking */
      .cp-thinking {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        color: var(--cp-text-dim);
        font-size: 12px;
      }
      .thinking-dots {
        display: flex;
        gap: 3px;
      }
      .thinking-dots span {
        animation: cp-pulse 1.4s infinite ease-in-out both;
        font-size: 8px;
      }
      .thinking-dots span:nth-child(1) { animation-delay: 0s; }
      .thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
      .thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
      @keyframes cp-pulse {
        0%, 80%, 100% { opacity: 0.3; }
        40% { opacity: 1; }
      }
      .thinking-text { font-style: italic; opacity: 0.7; }
    `;
    document.head.appendChild(styles);
  }

  updateAgentSelect() {
    this.agentSelect.innerHTML = "";

    for (const [name, info] of Object.entries(this.availableAgents)) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = info.display_name;
      option.disabled = !info.available;
      if (!info.available) {
        option.textContent += " (unavailable)";
      }
      this.agentSelect.appendChild(option);
    }

    // Select first available agent
    for (const [name, info] of Object.entries(this.availableAgents)) {
      if (info.available) {
        this.currentAgent = name;
        this.agentSelect.value = name;
        break;
      }
    }

    this.updateModelSelect();
  }

  updateModelSelect() {
    const info = this.availableAgents[this.currentAgent];
    if (!info || !info.models || info.models.length === 0) {
      this.modelSelect.style.display = "none";
      this.currentModel = "";
      return;
    }

    this.modelSelect.style.display = "";
    this.modelSelect.innerHTML = "";

    for (const model of info.models) {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model;
      this.modelSelect.appendChild(option);
    }

    this.currentModel = info.models[0];
    this.modelSelect.value = this.currentModel;
  }

  updateCategoryCheckboxes(categories) {
    const listEl = this.container.querySelector(".cp-category-list");
    if (!listEl) return;
    listEl.innerHTML = "";

    const savedCategories = this.knowledgeCategories;

    for (const [category, titles] of Object.entries(categories)) {
      const chip = document.createElement("label");
      chip.className = "cp-category-chip";
      const isActive = !savedCategories || savedCategories.includes(category);
      if (isActive) chip.classList.add("active");

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = isActive;
      cb.value = category;

      cb.addEventListener("change", () => {
        chip.classList.toggle("active", cb.checked);
        this.saveCategories();
      });

      chip.appendChild(cb);
      chip.appendChild(document.createTextNode(category));
      listEl.appendChild(chip);
    }
  }

  saveCategories() {
    const checkboxes = this.container.querySelectorAll(".cp-category-list input[type=checkbox]");
    const active = [];
    let allChecked = true;
    for (const cb of checkboxes) {
      if (cb.checked) active.push(cb.value);
      else allChecked = false;
    }

    if (allChecked) {
      this.knowledgeCategories = null;
      localStorage.removeItem("luna-categories");
    } else {
      this.knowledgeCategories = active;
      localStorage.setItem("luna-categories", JSON.stringify(active));
    }
  }

  updateSystemDisplay() {
    const gpuInfo = this.container.querySelector(".gpu-info");
    if (this.systemInfo?.gpus?.length > 0) {
      const gpu = this.systemInfo.gpus[0];
      gpuInfo.textContent = `${gpu.name} | ${gpu.vram_free_mb}MB free`;
    } else {
      gpuInfo.textContent = "GPU info unavailable";
    }
  }

  getCurrentWorkflow() {
    try {
      if (app.graph) {
        return app.graph.serialize();
      }
      return null;
    } catch (e) {
      console.error("Failed to get current workflow:", e);
      return null;
    }
  }

  getWorkflowSummary(workflow) {
    if (!workflow || !workflow.nodes) return null;
    return {
      nodeCount: workflow.nodes.length,
      nodeTypes: {},
      connections: workflow.links?.length || 0,
    };
  }

  updateWorkflowStatus() {
    if (!this.includeWorkflow) {
      this.workflowStatus.textContent = "";
      return;
    }
    const workflow = this.getCurrentWorkflow();
    if (workflow) {
      const summary = this.getWorkflowSummary(workflow);
      this.workflowStatus.textContent = summary ? `(${summary.nodeCount} nodes)` : "(empty)";
    } else {
      this.workflowStatus.textContent = "(no workflow)";
    }
  }

  registerMenuButton() {
    const checkMenu = setInterval(() => {
      const selectors = [
        ".comfyui-menu .comfyui-menu-right",
        ".comfyui-menu-right",
        ".comfy-menu-btns",
        "header nav",
        ".comfyui-menu",
        "#comfyui-body-top",
      ];

      let menuContainer = null;
      for (const selector of selectors) {
        menuContainer = document.querySelector(selector);
        if (menuContainer) break;
      }

      if (menuContainer) {
        clearInterval(checkMenu);
        const button = document.createElement("button");
        button.id = "luna-menu-button";
        button.className = "comfyui-button comfyui-menu-mobile-collapse primary";
        button.innerHTML = `
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          <span class="comfyui-button-text">Luna</span>
        `;
        button.addEventListener("click", () => this.toggle());
        menuContainer.appendChild(button);
        this.menuButton = button;
      }
    }, 500);

    setTimeout(() => {
      clearInterval(checkMenu);
      this.createFloatingButton();
    }, 2000);
  }

  createFloatingButton() {
    this.isButtonMinimized = localStorage.getItem("luna-minimized") === "true";

    const container = document.createElement("div");
    container.id = "luna-floating-container";
    container.style.cssText = `
      position: fixed; bottom: 20px; right: 20px; z-index: 9999;
      display: flex; flex-direction: column; align-items: flex-end; gap: 8px;
    `;

    const button = document.createElement("button");
    button.id = "luna-floating-button";
    button.title = "Open Luna Core - AI Assistant";

    const minimizeBtn = document.createElement("button");
    minimizeBtn.id = "luna-minimize-btn";
    minimizeBtn.title = "Minimize";
    minimizeBtn.innerHTML = "\u2212";
    minimizeBtn.style.cssText = `
      position: absolute; top: -8px; right: -8px; width: 20px; height: 20px;
      border-radius: 50%; background: #444; border: 2px solid #222;
      color: white; font-size: 14px; line-height: 1; cursor: pointer;
      display: none; align-items: center; justify-content: center;
    `;

    const wrapper = document.createElement("div");
    wrapper.style.cssText = "position: relative;";
    wrapper.appendChild(button);
    wrapper.appendChild(minimizeBtn);
    container.appendChild(wrapper);

    const updateButtonStyle = () => {
      if (this.isButtonMinimized) {
        button.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;
        button.style.cssText = `
          padding: 10px; border-radius: 50%;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          border: none; cursor: pointer; display: flex; align-items: center;
          justify-content: center; box-shadow: 0 2px 10px rgba(102,126,234,0.3);
          color: white; transition: transform 0.2s, box-shadow 0.2s; opacity: 0.7;
        `;
        minimizeBtn.innerHTML = "+";
        minimizeBtn.title = "Expand";
      } else {
        button.innerHTML = `
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <span>Luna Core</span>
        `;
        button.style.cssText = `
          padding: 12px 16px; border-radius: 12px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          border: none; cursor: pointer; display: flex; flex-direction: column;
          align-items: center; justify-content: center; gap: 4px;
          box-shadow: 0 4px 15px rgba(102,126,234,0.4); color: white;
          font-size: 11px; font-weight: 500; font-family: system-ui, -apple-system, sans-serif;
          transition: transform 0.2s, box-shadow 0.2s;
        `;
        minimizeBtn.innerHTML = "\u2212";
        minimizeBtn.title = "Minimize";
      }
    };

    updateButtonStyle();

    wrapper.addEventListener("mouseenter", () => {
      minimizeBtn.style.display = "flex";
      if (!this.isButtonMinimized) {
        button.style.transform = "scale(1.05)";
        button.style.boxShadow = "0 6px 20px rgba(102,126,234,0.5)";
      } else {
        button.style.opacity = "1";
      }
    });
    wrapper.addEventListener("mouseleave", () => {
      minimizeBtn.style.display = "none";
      if (!this.isButtonMinimized) {
        button.style.transform = "scale(1)";
        button.style.boxShadow = "0 4px 15px rgba(102,126,234,0.4)";
      } else {
        button.style.opacity = "0.7";
      }
    });

    button.addEventListener("click", () => this.toggle());
    minimizeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      this.isButtonMinimized = !this.isButtonMinimized;
      localStorage.setItem("luna-minimized", this.isButtonMinimized);
      updateButtonStyle();
    });

    document.body.appendChild(container);
    this.floatingButton = button;
    this.floatingButtonContainer = container;
  }

  // ---- Mode initialization ----

  _registerSidebarTab() {
    if (this._sidebarRegistered) return;
    try {
      app.extensionManager.registerSidebarTab({
        id: "luna-core",
        icon: "pi pi-comments",
        title: "Luna",
        tooltip: "AI Assistant for ComfyUI workflows",
        type: "custom",
        render: (el) => {
          this.sidebarElement = el;
          // If currently in floating mode, switch to sidebar mode
          if (this.mode === "floating") {
            this._teardownFloating();
            this.container.remove();
            this.mode = "sidebar";
            localStorage.setItem("luna-mode", "sidebar");
          }
          this.container.classList.remove("cp-floating-mode");
          this.container.classList.add("cp-sidebar-mode");
          this.container.classList.remove("luna-hidden");
          this._updateModeToggleButton();
          el.appendChild(this.container);
          this.refreshAgents();
          this.refreshSystemInfo();
          this.updateWorkflowStatus();
          this.inputField.focus();
        },
      });
      this._sidebarRegistered = true;
    } catch (e) {
      console.warn("[luna-core] Sidebar registration failed:", e);
      this.sidebarAvailable = false;
    }
  }

  _initSidebar() {
    this.container.classList.remove("cp-floating-mode");
    this.container.classList.add("cp-sidebar-mode");
    this.container.classList.remove("luna-hidden");
    this._updateModeToggleButton();

    // Re-attach to sidebar element if it exists (from a previous render call)
    if (this.sidebarElement) {
      this.sidebarElement.appendChild(this.container);
      this.refreshAgents();
      this.refreshSystemInfo();
      this.inputField.focus();
    }
  }

  _initFloating() {
    this.container.classList.remove("cp-sidebar-mode");
    this.container.classList.add("cp-floating-mode");
    this._updateModeToggleButton();

    if (this.container.parentNode !== document.body) {
      document.body.appendChild(this.container);
    }

    this._setupDrag();
    this._setupResize();
    this._restorePosition();
    this.hide();

    // Only create floating button if sidebar is not available (no sidebar icon to click)
    if (!this.sidebarAvailable) {
      this.registerMenuButton();
    }
  }

  _teardownFloating() {
    this._teardownDrag();
    this._teardownResize();

    // Remove menu button
    if (this.menuButton) {
      this.menuButton.remove();
      this.menuButton = null;
    }

    // Remove floating button
    if (this.floatingButtonContainer) {
      this.floatingButtonContainer.remove();
      this.floatingButtonContainer = null;
      this.floatingButton = null;
    }

    // Clear inline position/size styles
    this.container.style.left = "";
    this.container.style.top = "";
    this.container.style.right = "";
    this.container.style.width = "";
    this.container.style.height = "";
  }

  switchMode(newMode) {
    if (newMode === this.mode) return;
    if (newMode === "sidebar" && !this.sidebarAvailable) return;

    if (this.mode === "floating") {
      this._teardownFloating();
    }

    this.container.remove();
    this.mode = newMode;
    localStorage.setItem("luna-mode", newMode);

    if (newMode === "sidebar") {
      this._initSidebar();
    } else {
      this._initFloating();
      this.show();
    }
  }

  _updateModeToggleButton() {
    const btn = this.container.querySelector(".cp-mode-toggle");
    if (!btn) return;

    if (!this.sidebarAvailable) {
      btn.style.display = "none";
      return;
    }

    if (this.mode === "sidebar") {
      btn.title = "Pop out to floating window";
      btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
        <polyline points="15 3 21 3 21 9"/>
        <line x1="10" y1="14" x2="21" y2="3"/>
      </svg>`;
    } else {
      btn.title = "Dock to sidebar";
      btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
        <line x1="9" y1="3" x2="9" y2="21"/>
      </svg>`;
    }
  }

  // ---- Drag (teardown-friendly) ----

  _setupDrag() {
    const header = this.container.querySelector(".cp-header");
    let isDragging = false;
    let startX, startY, startLeft, startTop;

    this._dragHeaderHandler = (e) => {
      if (e.target.closest("button, select")) return;
      isDragging = true;
      const rect = this.container.getBoundingClientRect();
      startX = e.clientX;
      startY = e.clientY;
      startLeft = rect.left;
      startTop = rect.top;
      header.style.cursor = "grabbing";
      e.preventDefault();
    };

    this._dragMoveHandler = (e) => {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      let newLeft = startLeft + dx;
      let newTop = startTop + dy;
      const w = this.container.offsetWidth;
      newLeft = Math.max(0, Math.min(window.innerWidth - w, newLeft));
      newTop = Math.max(0, Math.min(window.innerHeight - 40, newTop));
      this.container.style.left = newLeft + "px";
      this.container.style.top = newTop + "px";
      this.container.style.right = "auto";
    };

    this._dragUpHandler = () => {
      if (!isDragging) return;
      isDragging = false;
      header.style.cursor = "";
      this._savePosition();
    };

    header.addEventListener("mousedown", this._dragHeaderHandler);
    document.addEventListener("mousemove", this._dragMoveHandler);
    document.addEventListener("mouseup", this._dragUpHandler);
  }

  _teardownDrag() {
    const header = this.container.querySelector(".cp-header");
    if (this._dragHeaderHandler) header.removeEventListener("mousedown", this._dragHeaderHandler);
    if (this._dragMoveHandler) document.removeEventListener("mousemove", this._dragMoveHandler);
    if (this._dragUpHandler) document.removeEventListener("mouseup", this._dragUpHandler);
    this._dragHeaderHandler = null;
    this._dragMoveHandler = null;
    this._dragUpHandler = null;
  }

  // ---- Resize (teardown-friendly) ----

  _setupResize() {
    this._resizeHandle = document.createElement("div");
    this._resizeHandle.className = "cp-resize-handle";
    this.container.appendChild(this._resizeHandle);

    let isResizing = false;
    let startX, startY, startW, startH;

    this._resizeDownHandler = (e) => {
      isResizing = true;
      startX = e.clientX;
      startY = e.clientY;
      startW = this.container.offsetWidth;
      startH = this.container.offsetHeight;
      e.preventDefault();
      e.stopPropagation();
    };

    this._resizeMoveHandler = (e) => {
      if (!isResizing) return;
      const newW = Math.max(320, startW + (e.clientX - startX));
      const newH = Math.max(400, startH + (e.clientY - startY));
      this.container.style.width = newW + "px";
      this.container.style.height = newH + "px";
    };

    this._resizeUpHandler = () => {
      if (!isResizing) return;
      isResizing = false;
      this._savePosition();
    };

    this._resizeHandle.addEventListener("mousedown", this._resizeDownHandler);
    document.addEventListener("mousemove", this._resizeMoveHandler);
    document.addEventListener("mouseup", this._resizeUpHandler);
  }

  _teardownResize() {
    if (this._resizeMoveHandler) document.removeEventListener("mousemove", this._resizeMoveHandler);
    if (this._resizeUpHandler) document.removeEventListener("mouseup", this._resizeUpHandler);
    if (this._resizeHandle) this._resizeHandle.remove();
    this._resizeHandle = null;
    this._resizeMoveHandler = null;
    this._resizeUpHandler = null;
    this._resizeDownHandler = null;
  }

  // ---- Position persistence (floating only) ----

  _savePosition() {
    if (this.mode === "sidebar") return;
    const rect = this.container.getBoundingClientRect();
    localStorage.setItem("luna-position", JSON.stringify({
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    }));
  }

  _restorePosition() {
    if (this.mode === "sidebar") return;
    const saved = localStorage.getItem("luna-position");
    if (!saved) return;
    try {
      const pos = JSON.parse(saved);
      if (pos.left >= 0 && pos.top >= 0 &&
          pos.left < window.innerWidth - 100 &&
          pos.top < window.innerHeight - 100) {
        this.container.style.left = pos.left + "px";
        this.container.style.top = pos.top + "px";
        this.container.style.right = "auto";
        if (pos.width >= 320) this.container.style.width = pos.width + "px";
        if (pos.height >= 400) this.container.style.height = pos.height + "px";
      }
    } catch (e) { /* ignore bad data */ }
  }

  // ---- Visibility (floating only — sidebar handles its own) ----

  show() {
    if (this.mode === "sidebar") return;
    this.container.classList.remove("luna-hidden");
    this.refreshAgents();
    this.refreshSystemInfo();
    this.updateWorkflowStatus();
    this.inputField.focus();
  }

  hide() {
    if (this.mode === "sidebar") return;
    this.container.classList.add("luna-hidden");
  }

  resetChat() {
    this.messages = [];
    this.messagesContainer.innerHTML = "";
    this.includeWorkflow = false;
    this.workflowToggle.checked = false;
    this.updateWorkflowStatus();
    this.lastDetectedWorkflow = null;
    this.clearPendingImages();
    this.updatePersistentActions();
    // Clear backend conversation + agent chat sessions
    fetch("/luna/reset-chat", { method: "POST" }).catch(() => {});
    this.addMessage("assistant", "Chat reset! How can I help you with ComfyUI today?");
  }

  toggle() {
    if (this.mode === "sidebar") return;
    if (this.container.classList.contains("luna-hidden")) {
      this.show();
    } else {
      this.hide();
    }
  }

  handleImageFiles(files) {
    const MAX_IMAGES = 5;
    const MAX_SIZE_MB = 10;
    for (const file of files) {
      if (this.pendingImages.length >= MAX_IMAGES) {
        console.warn("[luna-core] Maximum 5 images allowed");
        break;
      }
      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        console.warn(`[luna-core] Image ${file.name} exceeds ${MAX_SIZE_MB}MB limit`);
        continue;
      }
      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = e.target.result;
        const base64 = dataUrl.split(",")[1];
        const media_type = file.type || "image/png";
        this.pendingImages.push({ data: base64, media_type, filename: file.name });
        this.updateImagePreview();
      };
      reader.readAsDataURL(file);
    }
  }

  removePendingImage(index) {
    this.pendingImages.splice(index, 1);
    this.updateImagePreview();
  }

  clearPendingImages() {
    this.pendingImages = [];
    this.updateImagePreview();
  }

  updateImagePreview() {
    if (!this.imagePreviewStrip) return;
    if (this.pendingImages.length === 0) {
      this.imagePreviewStrip.style.display = "none";
      this.imagePreviewStrip.innerHTML = "";
      return;
    }
    this.imagePreviewStrip.style.display = "flex";
    this.imagePreviewStrip.innerHTML = "";
    this.pendingImages.forEach((img, i) => {
      const thumb = document.createElement("div");
      thumb.className = "cp-image-thumb";
      thumb.innerHTML = `
        <img src="data:${img.media_type};base64,${img.data}" alt="${img.filename || "image"}">
        <button class="cp-image-remove" title="Remove">&times;</button>
      `;
      thumb.querySelector(".cp-image-remove").addEventListener("click", () => {
        this.removePendingImage(i);
      });
      this.imagePreviewStrip.appendChild(thumb);
    });
  }

  async sendMessage() {
    const text = this.inputField.value.trim();
    if (!text && this.pendingImages.length === 0) return;
    if (this.isStreaming) return;

    // Capture images before clearing
    const images = [...this.pendingImages];
    this.addMessage("user", text || "(image)", images);
    this.inputField.value = "";
    this.clearPendingImages();

    this.isStreaming = true;
    this.sendButton.disabled = true;
    this.sendButton.textContent = "...";

    this.addThinkingIndicator();

    try {
      const payload = {
        agent: this.currentAgent,
        message: text || "Analyze this image.",
        // Strip image data from history to avoid huge payloads
        history: this.messages.slice(-20).map((m) => ({
          role: m.role,
          content: m.content,
          // Only include image metadata (not data) for recent history
        })),
        context_mode: this.contextMode,
      };

      // Attach current images (only for this message)
      if (images.length > 0) {
        payload.images = images;
      }

      if (this.currentModel) {
        payload.model = this.currentModel;
      }

      if (this.knowledgeCategories) {
        payload.knowledge_categories = this.knowledgeCategories;
      }

      if (this.includeWorkflow) {
        try {
          const workflow = this.getCurrentWorkflow();
          if (workflow) payload.current_workflow = workflow;
        } catch (e) {
          console.warn("[luna-core] Failed to get workflow for context:", e);
        }
      }

      const response = await api.fetchApi("/luna/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantMessage = "";
      let messageEl = null;
      let firstChunk = true;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        assistantMessage += chunk;

        // Check for tool approval requests
        const approvalMatch = assistantMessage.match(/<!-- TOOL_APPROVAL_NEEDED:(.*?) -->/);
        if (approvalMatch) {
          try {
            const approvalData = JSON.parse(approvalMatch[1]);
            // Remove marker from displayed message
            assistantMessage = assistantMessage.replace(/<!-- TOOL_APPROVAL_NEEDED:.*? -->/, "");
            if (messageEl) this.updateMessage(messageEl, assistantMessage);
            // Show approval dialog and wait for user decision
            const approved = await this.showToolApprovalDialog(approvalData);
            // Send decision to backend
            await api.fetchApi("/luna/tool-approval", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                approval_id: approvalData.approval_id,
                approved: approved,
              }),
            });
          } catch (e) {
            console.error("[luna-core] Tool approval error:", e);
          }
        }

        // Strip approval/confirmation markers from displayed text
        const displayMessage = assistantMessage
          .replace(/<!-- TOOL_APPROVAL_NEEDED:.*? -->/g, "")
          .replace(/<!-- TOOL_APPROVED:.*? -->/g, "")
          .replace(/<!-- TOOL_DENIED:.*? -->/g, "");

        if (firstChunk) {
          this.removeThinkingIndicator();
          firstChunk = false;
        }

        if (!messageEl) {
          messageEl = this.addMessage("assistant", displayMessage);
        } else {
          this.updateMessage(messageEl, displayMessage);
        }
      }

      this.checkForWorkflow(messageEl, assistantMessage);
      this.applyCanvasModifications(assistantMessage, messageEl);
    } catch (error) {
      this.addMessage("assistant", `Error: ${error.message}`);
    } finally {
      this.isStreaming = false;
      this.sendButton.disabled = false;
      this.sendButton.textContent = "Send";
      this.removeThinkingIndicator();
    }
  }

  addThinkingIndicator() {
    const thinkingEl = document.createElement("div");
    thinkingEl.className = "cp-thinking";
    thinkingEl.innerHTML = `
      <span class="thinking-dots"><span>\u25cf</span><span>\u25cf</span><span>\u25cf</span></span>
      <span class="thinking-text">Thinking...</span>
    `;
    this.messagesContainer.appendChild(thinkingEl);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;

    const messages = [
      "Untangling the noodles...",
      "Asking the VAE nicely...",
      "Sacrificing VRAM to the GPU gods...",
      "Reticulating splines...",
      "Have you tried more steps?",
      "CFG goes brrrrr...",
      "Consulting the LoRA council...",
      "Praying to the checkpoint...",
      "Converting creativity to latent space...",
      "Denoising my thoughts...",
      "It's not a bug, it's a feature...",
      "Training on your patience...",
      "50% done (for the last 5 minutes)...",
      "Downloading more VRAM...",
      "Blaming CLIP for everything...",
      "Just one more LoRA, I promise...",
      "Workflow.json has mass...",
      "Fighting with ComfyUI-Manager...",
      "NaN% complete...",
      "Generating excuses...",
    ];
    let idx = Math.floor(Math.random() * messages.length);
    const textEl = thinkingEl.querySelector(".thinking-text");
    if (textEl) textEl.textContent = messages[idx];

    this.thinkingInterval = setInterval(() => {
      idx = Math.floor(Math.random() * messages.length);
      if (textEl) textEl.textContent = messages[idx];
    }, 2500);

    return thinkingEl;
  }

  removeThinkingIndicator() {
    if (this.thinkingInterval) {
      clearInterval(this.thinkingInterval);
      this.thinkingInterval = null;
    }
    const thinking = this.messagesContainer.querySelector(".cp-thinking");
    if (thinking) thinking.remove();
  }

  addMessage(role, content, images = null) {
    this.messages.push({ role, content });

    const messageEl = document.createElement("div");
    messageEl.className = `cp-message ${role}`;

    // Show image thumbnails if present
    if (images && images.length > 0) {
      const imgRow = document.createElement("div");
      imgRow.className = "cp-msg-images";
      for (const img of images) {
        const imgEl = document.createElement("img");
        imgEl.src = `data:${img.media_type};base64,${img.data}`;
        imgEl.alt = img.filename || "attached image";
        imgEl.className = "cp-msg-image";
        imgRow.appendChild(imgEl);
      }
      messageEl.appendChild(imgRow);
    }

    const contentEl = document.createElement("div");
    contentEl.className = "cp-msg-content";
    contentEl.innerHTML = this.formatContent(content);
    messageEl.appendChild(contentEl);

    // Collapse long messages (> 500 chars)
    if (content.length > 500) {
      messageEl.classList.add("collapsed");
      const toggle = document.createElement("button");
      toggle.className = "cp-msg-toggle";
      toggle.textContent = "\u25bc Show more";
      toggle.addEventListener("click", () => {
        const isCollapsed = messageEl.classList.toggle("collapsed");
        toggle.textContent = isCollapsed ? "\u25bc Show more" : "\u25b2 Show less";
      });
      messageEl.appendChild(toggle);
    }

    this.messagesContainer.appendChild(messageEl);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;

    return messageEl;
  }

  updateMessage(messageEl, content) {
    let contentEl = messageEl.querySelector(".cp-msg-content");
    if (contentEl) {
      contentEl.innerHTML = this.formatContent(content);
    } else {
      messageEl.innerHTML = this.formatContent(content);
    }
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;

    // Add/update collapse toggle for long messages
    if (content.length > 500 && !messageEl.querySelector(".cp-msg-toggle")) {
      if (!contentEl) {
        const wrapper = document.createElement("div");
        wrapper.className = "cp-msg-content";
        wrapper.innerHTML = messageEl.innerHTML;
        messageEl.innerHTML = "";
        messageEl.appendChild(wrapper);
        contentEl = wrapper;
      }
      messageEl.classList.add("collapsed");
      const toggle = document.createElement("button");
      toggle.className = "cp-msg-toggle";
      toggle.textContent = "\u25bc Show more";
      toggle.addEventListener("click", () => {
        const isCollapsed = messageEl.classList.toggle("collapsed");
        toggle.textContent = isCollapsed ? "\u25bc Show more" : "\u25b2 Show less";
      });
      messageEl.appendChild(toggle);
    }

    const lastMsg = this.messages[this.messages.length - 1];
    if (lastMsg) lastMsg.content = content;
  }

  formatContent(content) {
    return content
      .replace(/```(\w*)\n([\s\S]*?)```/g, "<pre><code>$2</code></pre>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br>");
  }

  applyCanvasModifications(responseText, messageEl) {
    // Look for the CANVAS_MODIFICATIONS marker from the backend
    const modMatch = responseText.match(/<!-- CANVAS_MODIFICATIONS:(.*?) -->/);
    if (!modMatch) return;

    let modifications;
    try {
      modifications = JSON.parse(modMatch[1]);
    } catch (e) {
      console.error("[luna-core] Failed to parse modifications:", e);
      return;
    }

    if (!modifications || !modifications.length) return;

    // Apply each modification directly to the canvas
    let applied = 0;
    let failed = 0;
    // Map backend node IDs to LiteGraph IDs (for newly added nodes)
    const nodeIdMap = {};
    // Track rightmost node position for placing new nodes
    let lastX = 100;
    const existingNodes = app.graph._nodes || [];
    for (const n of existingNodes) {
      if (n.pos && n.pos[0] > lastX) lastX = n.pos[0] + (n.size?.[0] || 200);
    }

    for (const mod of modifications) {
      try {
        // --- MODIFY: change a widget value on an existing node ---
        if (mod.action === "modify" && mod.node_id && mod.input_name !== undefined) {
          const node = app.graph.getNodeById(parseInt(mod.node_id));
          if (!node) {
            console.warn(`[luna-core] Node ${mod.node_id} not found on canvas`);
            failed++;
            continue;
          }

          // Find widget: exact match, then case-insensitive fallback
          let widget = node.widgets?.find((w) => w.name === mod.input_name);
          if (!widget) {
            widget = node.widgets?.find(
              (w) => w.name.toLowerCase() === mod.input_name.toLowerCase()
            );
          }

          if (widget) {
            widget.value = mod.value;
            if (widget.callback) widget.callback(mod.value);
            applied++;
          } else {
            console.warn(`[luna-core] Widget '${mod.input_name}' not found on node ${mod.node_id} (${node.type}). Available: ${node.widgets?.map(w => w.name).join(", ")}`);
            failed++;
          }
        }

        // --- ADD: create a new node on canvas ---
        else if (mod.action === "add" && mod.class_type) {
          const node = LiteGraph.createNode(mod.class_type);
          if (!node) {
            console.warn(`[luna-core] Could not create node of type '${mod.class_type}'`);
            failed++;
            continue;
          }
          node.title = mod.title || mod.class_type;
          if (mod.x !== undefined && mod.y !== undefined && mod.x >= 0 && mod.y >= 0) {
            node.pos = [mod.x, mod.y];
          } else {
            node.pos = [lastX + 50, 200];
          }
          lastX = node.pos[0] + (node.size?.[0] || 200);

          // Set widget values from inputs (skip connections which are arrays)
          if (mod.inputs) {
            for (const [name, val] of Object.entries(mod.inputs)) {
              if (Array.isArray(val)) continue; // connection, handle later
              const w = node.widgets?.find((w) => w.name === name);
              if (w) {
                w.value = val;
                if (w.callback) w.callback(val);
              }
            }
          }

          app.graph.add(node);
          // Map backend ID to real LiteGraph ID for connections
          nodeIdMap[mod.node_id] = node.id;
          applied++;
        }

        // --- REMOVE: delete a node from canvas ---
        else if (mod.action === "remove" && mod.node_id) {
          const node = app.graph.getNodeById(parseInt(mod.node_id));
          if (node) {
            app.graph.remove(node);
            applied++;
          } else {
            console.warn(`[luna-core] Node ${mod.node_id} not found for removal`);
            failed++;
          }
        }

        // --- AUTO ARRANGE: reorganize node layout ---
        else if (mod.action === "auto_arrange") {
          try {
            app.graph.arrange();
            applied++;
          } catch (e) {
            console.warn("[luna-core] Auto-arrange failed:", e);
            failed++;
          }
        }

        // --- CONNECT: link two nodes together ---
        else if (mod.action === "connect") {
          // Resolve IDs — use nodeIdMap for newly added nodes, else parse as int
          const sourceId = nodeIdMap[mod.source_node_id] || parseInt(mod.source_node_id);
          const targetId = nodeIdMap[mod.target_node_id] || parseInt(mod.target_node_id);
          const source = app.graph.getNodeById(sourceId);
          const target = app.graph.getNodeById(targetId);

          if (!source || !target) {
            console.warn(`[luna-core] Connect failed: source(${mod.source_node_id}→${sourceId})=${!!source}, target(${mod.target_node_id}→${targetId})=${!!target}`);
            failed++;
            continue;
          }

          // Find target input slot by name
          const slotIdx = target.findInputSlot(mod.target_input_name);
          if (slotIdx >= 0) {
            source.connect(mod.source_output_slot, target, slotIdx);
            applied++;
          } else {
            console.warn(`[luna-core] Input '${mod.target_input_name}' not found on ${target.type}`);
            failed++;
          }
        }
      } catch (e) {
        console.error(`[luna-core] Failed to apply ${mod.action} modification:`, e);
        failed++;
      }
    }

    // Force canvas redraw
    if (applied > 0) {
      app.graph.setDirtyCanvas(true, true);
    }

    // Show result on the message
    const statusEl = document.createElement("div");
    statusEl.style.cssText = "font-size:11px; margin-top:6px; padding:4px 8px; border-radius:4px;";
    if (failed === 0 && applied > 0) {
      statusEl.style.background = "rgba(40, 167, 69, 0.2)";
      statusEl.style.color = "var(--cp-success)";
      statusEl.textContent = `\u2713 Applied ${applied} change${applied !== 1 ? "s" : ""} directly to canvas`;
    } else if (applied > 0) {
      statusEl.style.background = "rgba(255, 193, 7, 0.2)";
      statusEl.style.color = "var(--cp-warning)";
      statusEl.textContent = `Applied ${applied}, failed ${failed} change${failed !== 1 ? "s" : ""}`;
    } else if (failed > 0) {
      statusEl.style.background = "rgba(220, 53, 69, 0.2)";
      statusEl.style.color = "var(--cp-error, #dc3545)";
      statusEl.textContent = `Failed to apply ${failed} change${failed !== 1 ? "s" : ""}`;
    }
    if (applied > 0 || failed > 0) messageEl.appendChild(statusEl);

    // Strip the marker from the displayed message
    const cleanContent = responseText.replace(/<!-- CANVAS_MODIFICATIONS:.*? -->/, "").trim();
    this.updateMessage(messageEl, cleanContent);
  }

  showToolApprovalDialog(approvalData) {
    return new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.style.cssText = `
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0, 0, 0, 0.6); z-index: 100000;
        display: flex; align-items: center; justify-content: center;
      `;

      const toolName = approvalData.tool_name === "web_search" ? "Web Search" : "Web Fetch";
      const toolIcon = approvalData.tool_name === "web_search" ? "🔍" : "🌐";
      const detail = approvalData.tool_name === "web_search"
        ? `Query: "${approvalData.arguments.query || ""}"`
        : `URL: ${approvalData.arguments.url || ""}`;

      const dialog = document.createElement("div");
      dialog.style.cssText = `
        background: var(--comfy-menu-bg, #1a1a2e); color: var(--input-text, #e0e0e0);
        border: 1px solid var(--border-color, #444); border-radius: 12px;
        padding: 24px; max-width: 420px; width: 90%;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5); font-family: inherit;
      `;

      dialog.innerHTML = `
        <div style="font-size: 16px; font-weight: 600; margin-bottom: 12px;">
          ${toolIcon} ${toolName} Request
        </div>
        <div style="font-size: 13px; color: var(--descrip-text, #aaa); margin-bottom: 16px;">
          The agent wants to access the web. Allow this request?
        </div>
        <div style="
          background: rgba(255, 255, 255, 0.05); border-radius: 8px;
          padding: 12px; font-size: 13px; margin-bottom: 20px;
          word-break: break-all; border: 1px solid rgba(255, 255, 255, 0.08);
        ">
          ${detail}
        </div>
        <div style="display: flex; gap: 10px; justify-content: flex-end;">
          <button id="luna-deny-btn" style="
            padding: 8px 20px; border-radius: 8px; border: 1px solid var(--border-color, #555);
            background: transparent; color: var(--input-text, #ccc);
            cursor: pointer; font-size: 13px; font-weight: 500;
          ">Deny</button>
          <button id="luna-approve-btn" style="
            padding: 8px 20px; border-radius: 8px; border: none;
            background: #4a9eff; color: white;
            cursor: pointer; font-size: 13px; font-weight: 600;
          ">Allow</button>
        </div>
      `;

      overlay.appendChild(dialog);
      document.body.appendChild(overlay);

      const cleanup = (result) => {
        document.body.removeChild(overlay);
        resolve(result);
      };

      dialog.querySelector("#luna-approve-btn").addEventListener("click", () => cleanup(true));
      dialog.querySelector("#luna-deny-btn").addEventListener("click", () => cleanup(false));
      overlay.addEventListener("click", (e) => { if (e.target === overlay) cleanup(false); });

      // Auto-deny after 55 seconds (before server timeout)
      setTimeout(() => {
        if (document.body.contains(overlay)) cleanup(false);
      }, 55000);
    });
  }

  checkForWorkflow(messageEl, content) {
    const jsonMatch = content.match(/```(?:json)?\s*([\s\S]*?)```/);
    if (!jsonMatch) return;

    let workflow;
    try {
      workflow = JSON.parse(jsonMatch[1]);
    } catch (e) {
      return;
    }

    const hasNodes = Object.values(workflow).some(
      (v) => typeof v === "object" && v !== null && v.class_type
    );
    if (!hasNodes) return;

    // Track the last detected workflow for the persistent bar
    this.lastDetectedWorkflow = workflow;
    this.updatePersistentActions();

    // Clear old validation results everywhere (stale from previous workflow)
    this.container.querySelectorAll(".cp-validation-result").forEach((el) => el.remove());

    // Inline marker on the message
    const marker = document.createElement("div");
    marker.className = "cp-workflow-actions";
    marker.innerHTML = `<span style="font-size:11px;color:var(--cp-text-dim)">Workflow detected (${Object.keys(workflow).length} nodes) - use buttons below to validate/apply</span>`;
    messageEl.appendChild(marker);
  }

  updatePersistentActions() {
    const bar = this.container.querySelector(".cp-persistent-actions");
    if (!bar) return;
    if (this.lastDetectedWorkflow) {
      const count = Object.keys(this.lastDetectedWorkflow).length;
      bar.style.display = "flex";
      bar.querySelector(".cp-detected-label").textContent = `Workflow detected (${count} nodes)`;
      // Remove old validation results
      const oldResult = bar.parentElement.querySelector(".cp-persistent-actions + .cp-validation-result");
      if (oldResult) oldResult.remove();
    } else {
      bar.style.display = "none";
    }
  }

  async validateWorkflowUI(workflow, container) {
    // Remove existing validation results near this container
    const parent = container.parentElement || container;
    parent.querySelectorAll(".cp-validation-result").forEach((el) => el.remove());

    try {
      const response = await api.fetchApi("/luna/validate-workflow", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflow }),
      });
      const result = await response.json();

      const resultDiv = document.createElement("div");
      resultDiv.className = `cp-validation-result ${result.valid ? "valid" : "invalid"}`;

      if (result.valid) {
        resultDiv.innerHTML = `<strong>\u2713 Valid</strong> (${result.node_count} nodes${result.validated_against_registry ? ", checked against registry" : ""})`;
      } else {
        let html = `<strong>\u2717 Invalid</strong> (${result.errors.length} error${result.errors.length !== 1 ? "s" : ""})`;
        html += `<button class="cp-val-toggle">\u25bc details</button>`;
        html += `<div class="cp-val-details"><ul>`;
        for (const err of result.errors) {
          html += `<li>${err.message}${err.suggestion ? ` <em>${err.suggestion}</em>` : ""}</li>`;
        }
        html += "</ul>";

        if (result.warnings?.length) {
          html += `<div style="margin-top:4px;color:#ffc107"><strong>Warnings:</strong></div><ul>`;
          for (const w of result.warnings) {
            html += `<li>${w.message}</li>`;
          }
          html += "</ul>";
        }
        html += "</div>";

        resultDiv.innerHTML = html;

        // Toggle validation details
        const valToggle = resultDiv.querySelector(".cp-val-toggle");
        valToggle.addEventListener("click", () => {
          resultDiv.classList.toggle("collapsed");
          valToggle.textContent = resultDiv.classList.contains("collapsed") ? "\u25bc details" : "\u25b2 hide";
        });

        // Add "Ask agent to fix" button
        const fixBtn = document.createElement("button");
        fixBtn.className = "cp-btn-fix";
        fixBtn.textContent = "Ask agent to fix";
        fixBtn.style.marginTop = "6px";
        fixBtn.addEventListener("click", () => {
          const errorText = result.errors.map((e) => e.message).join("\n");
          this.inputField.value = `The workflow has validation errors:\n${errorText}\n\nPlease fix these errors and provide a corrected workflow.`;
          this.sendMessage();
        });
        resultDiv.appendChild(fixBtn);
      }

      (parent || container).appendChild(resultDiv);
    } catch (e) {
      console.error("Validation failed:", e);
    }
  }

  async applyWorkflow(workflow) {
    try {
      const format = this.detectWorkflowFormat(workflow);

      if (format === "api") {
        await this.loadApiWorkflow(workflow);
      } else if (format === "graph") {
        await this.loadGraphWorkflow(workflow);
      } else {
        throw new Error("Unknown workflow format");
      }
    } catch (error) {
      console.error("[luna-core] Failed to apply workflow:", error);
      console.log("[luna-core] Workflow JSON to copy:", JSON.stringify(workflow, null, 2));
      throw error;
    }
  }

  detectWorkflowFormat(workflow) {
    if (workflow.nodes && Array.isArray(workflow.nodes)) return "graph";
    const keys = Object.keys(workflow);
    if (keys.length > 0 && workflow[keys[0]]?.class_type) return "api";
    if (workflow.output && typeof workflow.output === "object") {
      return this.detectWorkflowFormat(workflow.output);
    }
    return "unknown";
  }

  async loadApiWorkflow(apiWorkflow) {
    try {
      if (app.loadApiJson) {
        await app.loadApiJson(apiWorkflow);
        return;
      }

      if (app.graph) {
        app.graph.clear();
        const nodeIdMap = {};

        for (const [id, nodeData] of Object.entries(apiWorkflow)) {
          const node = window.LiteGraph.createNode(nodeData.class_type);
          if (node) {
            node.id = parseInt(id);
            nodeIdMap[id] = node;

            if (nodeData.inputs) {
              for (const [inputName, inputValue] of Object.entries(nodeData.inputs)) {
                if (!Array.isArray(inputValue)) {
                  const widget = node.widgets?.find((w) => w.name === inputName);
                  if (widget) widget.value = inputValue;
                }
              }
            }

            const idx = parseInt(id);
            node.pos = [150 + (idx % 5) * 300, 100 + Math.floor(idx / 5) * 200];
            app.graph.add(node);
          } else {
            console.warn(`[luna-core] Unknown node type: ${nodeData.class_type}`);
          }
        }

        for (const [id, nodeData] of Object.entries(apiWorkflow)) {
          if (!nodeData.inputs) continue;
          const targetNode = nodeIdMap[id];
          if (!targetNode) continue;

          for (const [inputName, inputValue] of Object.entries(nodeData.inputs)) {
            if (Array.isArray(inputValue) && inputValue.length === 2) {
              const [sourceId, sourceSlot] = inputValue;
              const sourceNode = nodeIdMap[sourceId];
              if (sourceNode && targetNode) {
                const targetSlot = targetNode.findInputSlot(inputName);
                if (targetSlot !== -1) {
                  sourceNode.connect(sourceSlot, targetNode, targetSlot);
                }
              }
            }
          }
        }

        app.graph.setDirtyCanvas(true, true);
        return;
      }

      throw new Error("No suitable method to load API workflow");
    } catch (error) {
      console.error("[luna-core] loadApiWorkflow error:", error);
      throw error;
    }
  }

  async loadGraphWorkflow(graphWorkflow) {
    try {
      if (app.loadGraphData) {
        await app.loadGraphData(graphWorkflow);
        return;
      }
      if (app.graph && app.graph.configure) {
        app.graph.configure(graphWorkflow);
        app.graph.setDirtyCanvas(true, true);
        return;
      }
      throw new Error("No suitable method to load graph workflow");
    } catch (error) {
      console.error("[luna-core] loadGraphWorkflow error:", error);
      throw error;
    }
  }
}

// Initialize when ComfyUI is ready
app.registerExtension({
  name: "luna-core",
  async setup() {
    try {
      const panel = new LunaCorePanel();
      await panel.init();
      window.lunaCore = panel;
      console.log("[luna-core] Setup complete!");
    } catch (error) {
      console.error("[luna-core] Setup failed:", error);
    }
  },
});
