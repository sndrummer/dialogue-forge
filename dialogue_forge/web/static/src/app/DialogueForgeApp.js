/**
 * DialogueForgeApp - Main application controller for the web editor
 */
import { DialoguePlayer } from '../player/DialoguePlayer.js';
import { escapeHtml } from '../utils/helpers.js';

export class DialogueForgeApp {
    constructor() {
        this.editor = null;
        this.cy = null;
        this.currentFile = null;
        this.currentFilePath = null;
        this.originalContent = null;
        this.originalLines = [];
        this.hasUnsavedChanges = false;
        this.autoPreview = true;
        this.previewTimeout = null;
        this.vimMode = false;
        this.dialoguePlayer = null;
        this.contextMenu = null;
        this.lastPlayedPath = []; // Preserve path from last play session for "Resume" feature

        this.init();
    }

    async init() {
        // Initialize CodeMirror editor
        this.initEditor();

        // Initialize Cytoscape graph
        this.initGraph();

        // Initialize dialogue player
        this.dialoguePlayer = new DialoguePlayer(this);

        // Initialize context menu
        this.initContextMenu();

        // Load file list
        await this.loadFileList();

        // Set up event listeners
        this.setupEventListeners();

        // Set up panel resizer
        this.setupResizer();

        // Warn before leaving with unsaved changes
        window.addEventListener('beforeunload', (e) => {
            if (this.hasUnsavedChanges) {
                e.preventDefault();
                e.returnValue = '';
            }
        });

        console.log('📝 Dialogue Forge initialized');
    }

    initContextMenu() {
        // Create context menu element
        this.contextMenu = document.createElement('div');
        this.contextMenu.className = 'context-menu hidden';
        this.contextMenu.innerHTML = `
            <div class="context-menu-item" data-action="play-shortest">
                <span>▶️</span> Play (shortest path)
            </div>
            <div class="context-menu-item" data-action="play-random">
                <span>🎲</span> Play (random path)
            </div>
            <div class="context-menu-item" data-action="play-explore">
                <span>🗺️</span> Play (explore path)
            </div>
            <div class="context-menu-item context-menu-history hidden" data-action="play-history">
                <span>🔄</span> Resume from history
            </div>
            <div class="context-menu-divider"></div>
            <div class="context-menu-item" data-action="edit">
                <span>✏️</span> Edit in editor
            </div>
            <div class="context-menu-item" data-action="inspect">
                <span>🔍</span> Inspect node
            </div>
        `;
        document.body.appendChild(this.contextMenu);

        // Hide context menu on click outside
        document.addEventListener('click', () => {
            this.contextMenu.classList.add('hidden');
        });

        // Handle context menu item clicks
        this.contextMenu.addEventListener('click', (e) => {
            const item = e.target.closest('.context-menu-item');
            if (!item) return;

            const action = item.dataset.action;
            const nodeId = this.contextMenu.dataset.nodeId;

            if (action === 'edit' && nodeId) {
                this.scrollToNodeInEditor(nodeId);
            } else if (action === 'play-shortest' && nodeId) {
                this.dialoguePlayer.playFromNode(nodeId, 'shortest');
            } else if (action === 'play-random' && nodeId) {
                this.dialoguePlayer.playFromNode(nodeId, 'random');
            } else if (action === 'play-explore' && nodeId) {
                this.dialoguePlayer.playFromNode(nodeId, 'explore');
            } else if (action === 'play-history' && nodeId) {
                this.dialoguePlayer.playFromHistory(nodeId, this.lastPlayedPath);
            } else if (action === 'inspect' && nodeId) {
                const node = this.cy.getElementById(nodeId);
                if (node) {
                    this.showNodeInspector(node.data());
                }
            }

            this.contextMenu.classList.add('hidden');
        });
    }

    scrollToNodeInEditor(nodeId) {
        const content = this.editor.getValue();
        const lines = content.split('\n');

        // Find the line with [nodeId]
        let targetLine = -1;
        const nodePattern = new RegExp(`^\\[${nodeId}\\]`);

        for (let i = 0; i < lines.length; i++) {
            if (nodePattern.test(lines[i].trim())) {
                targetLine = i;
                break;
            }
        }

        if (targetLine === -1) {
            this.showNotification(`Node [${nodeId}] not found in editor`, 'warning');
            return;
        }

        // Scroll to and highlight the line
        this.editor.scrollIntoView({ line: targetLine, ch: 0 }, 100);
        this.editor.setCursor({ line: targetLine, ch: 0 });
        this.editor.focus();

        // Flash highlight effect
        const lineHandle = this.editor.addLineClass(targetLine, 'background', 'line-highlight-flash');
        setTimeout(() => {
            this.editor.removeLineClass(lineHandle, 'background', 'line-highlight-flash');
        }, 1500);
    }

    initEditor() {
        const textarea = document.getElementById('editor');
        this.editor = CodeMirror.fromTextArea(textarea, {
            mode: 'text/plain',
            theme: 'monokai',
            lineNumbers: true,
            lineWrapping: true,
            autofocus: true,
            indentUnit: 2,
            tabSize: 2,
            indentWithTabs: false,
            gutters: ['CodeMirror-linenumbers', 'CodeMirror-gutter-modified'],
            extraKeys: {
                'Ctrl-S': () => this.handleSave(),
                'Cmd-S': () => this.handleSave(),
                'Ctrl-R': () => this.handleReload(),
                'Cmd-R': () => this.handleReload(),
                'Ctrl-Enter': () => this.validateDialogue(),
                'Cmd-Enter': () => this.validateDialogue(),
                // Search: use persistent dialog (stays open on Enter)
                'Ctrl-F': 'findPersistent',
                'Cmd-F': 'findPersistent',
                // Find next/previous
                'Ctrl-G': 'findNext',
                'Cmd-G': 'findNext',
                'Ctrl-Shift-G': 'findPrev',
                'Cmd-Shift-G': 'findPrev',
                'F3': 'findNext',
                'Shift-F3': 'findPrev',
                // Escape clears search highlighting
                'Esc': (cm) => {
                    if (cm.state.search && cm.state.search.query) {
                        cm.execCommand('clearSearch');
                    }
                    // Also exit any other mode (like multi-cursor)
                    return CodeMirror.Pass;
                }
            }
        });

        // Add syntax highlighting for .dlg format
        this.setupDLGSyntaxHighlighting();

        // Define vim :w command for saving
        if (CodeMirror.Vim) {
            CodeMirror.Vim.defineEx('write', 'w', () => {
                this.handleSave();
            });
        }

        // Track changes for modified lines and unsaved state
        this.editor.on('change', (cm, change) => {
            // Update gutter markers by comparing with original
            this.updateModifiedGutters();

            // Check if content differs from original
            this.checkUnsavedChanges();

            // Always update UI (for "no file but has content" case)
            this.updateUnsavedUI();

            // Auto-preview
            if (this.autoPreview) {
                clearTimeout(this.previewTimeout);
                this.previewTimeout = setTimeout(() => {
                    this.validateDialogue();
                }, 1000);
            }
        });
    }

    updateModifiedGutters() {
        // Clear all existing markers
        this.editor.clearGutter('CodeMirror-gutter-modified');

        // If no original content, nothing to compare
        if (!this.originalLines || this.originalLines.length === 0) {
            return;
        }

        // Count occurrences of each line in original (handles duplicate lines)
        const originalLineCount = new Map();
        for (const line of this.originalLines) {
            originalLineCount.set(line, (originalLineCount.get(line) || 0) + 1);
        }

        // Get current lines
        const currentLines = this.editor.getValue().split('\n');

        // Track how many times we've "matched" each line content
        const usedCount = new Map();

        for (let i = 0; i < currentLines.length; i++) {
            const line = currentLines[i];
            const availableInOriginal = originalLineCount.get(line) || 0;
            const alreadyUsed = usedCount.get(line) || 0;

            if (alreadyUsed < availableInOriginal) {
                // This line content exists in original and we haven't used all instances
                usedCount.set(line, alreadyUsed + 1);
                // Don't mark - it's unchanged content
            } else {
                // This is new content or an extra duplicate
                const marker = document.createElement('div');
                marker.className = 'modified-line-marker';
                marker.title = 'New/Modified';
                this.editor.setGutterMarker(i, 'CodeMirror-gutter-modified', marker);
            }
        }
    }

    checkUnsavedChanges() {
        const currentContent = this.editor.getValue();
        const hasChanges = this.originalContent !== null && currentContent !== this.originalContent;

        if (hasChanges !== this.hasUnsavedChanges) {
            this.hasUnsavedChanges = hasChanges;
            this.updateUnsavedUI();
        }
    }

    updateUnsavedUI() {
        const saveBtn = document.getElementById('save-btn');
        const reloadBtn = document.getElementById('reload-btn');
        const unsavedIndicator = document.getElementById('unsaved-indicator');

        const hasFile = this.currentFilePath !== null;
        const hasContent = this.editor && this.editor.getValue().trim().length > 0;

        if (this.hasUnsavedChanges) {
            saveBtn.classList.add('has-changes');
            unsavedIndicator.classList.remove('hidden');
        } else {
            saveBtn.classList.remove('has-changes');
            unsavedIndicator.classList.add('hidden');
        }

        // Save enabled if: file with changes, OR no file but has content (Save As)
        saveBtn.disabled = hasFile ? false : !hasContent;
        // Reload only makes sense if we have a file on disk
        reloadBtn.disabled = !hasFile;
    }

    setupDLGSyntaxHighlighting() {
        // Custom mode for .dlg syntax with multi-line string support
        CodeMirror.defineMode('dlg', function() {
            return {
                startState: function() {
                    return { inString: false, afterString: false };
                },
                token: function(stream, state) {
                    // If we're inside a multi-line string, continue until closing quote
                    if (state.inString) {
                        while (!stream.eol()) {
                            const ch = stream.next();
                            if (ch === '"') {
                                state.inString = false;
                                state.afterString = true;
                                return 'string';
                            }
                            if (ch === '\\') {
                                stream.next(); // Skip escaped char
                            }
                        }
                        return 'string'; // Still in string, continue on next line
                    }

                    // Skip whitespace but track if we just finished a string
                    if (stream.eatSpace()) {
                        return null;
                    }

                    // Comments (only at start of line)
                    if (stream.sol() && stream.match(/^#.*/)) {
                        state.afterString = false;
                        return 'comment';
                    }

                    // Node definitions [node_name] - ONLY at start of line
                    if (stream.sol() && stream.match(/^\[.*?\]/)) {
                        state.afterString = false;
                        return 'keyword';
                    }

                    // Tags [tag1, tag2] - brackets AFTER a string (not at start of line)
                    if (state.afterString && stream.match(/^\[[^\]]*\]/)) {
                        // Don't reset afterString yet, conditions might follow
                        return 'tag';
                    }

                    // Commands *set, *add, etc.
                    if (stream.match(/^\*\w+/)) {
                        state.afterString = false;
                        return 'builtin';
                    }

                    // Triggers @talk:, @event:, @end
                    if (stream.match(/^@(talk|event):\w+/)) {
                        state.afterString = false;
                        return 'variable-2';  // Teal/cyan color
                    }
                    if (stream.match(/^@end/)) {
                        state.afterString = false;
                        return 'variable-3';  // Different color for end
                    }

                    // Choices ->
                    if (stream.match(/^->/)) {
                        state.afterString = false;
                        return 'operator';
                    }

                    // Conditions {...}
                    if (stream.match(/^\{[^}]*\}/)) {
                        state.afterString = false;
                        return 'string-2';
                    }

                    // String literals - check for single-line first
                    if (stream.match(/^"([^"\\]|\\.)*"/)) {
                        state.afterString = true;
                        return 'string';
                    }

                    // Opening quote for multi-line string
                    if (stream.match(/^"/)) {
                        state.inString = true;
                        // Consume rest of line
                        while (!stream.eol()) {
                            const ch = stream.next();
                            if (ch === '"') {
                                state.inString = false;
                                state.afterString = true;
                                return 'string';
                            }
                            if (ch === '\\') {
                                stream.next(); // Skip escaped char
                            }
                        }
                        return 'string'; // String continues to next line
                    }

                    // Reset afterString for other tokens
                    state.afterString = false;
                    stream.next();
                    return null;
                }
            };
        });

        this.editor.setOption('mode', 'dlg');
    }

    initGraph() {
        // Register layouts
        if (typeof cytoscape !== 'undefined') {
            if (typeof cytoscapeDagre !== 'undefined') {
                cytoscape.use(cytoscapeDagre);
            }
            if (typeof cytoscapeCoseBilkent !== 'undefined') {
                cytoscape.use(cytoscapeCoseBilkent);
            }
        }

        this.cy = cytoscape({
            container: document.getElementById('cy'),

            style: [
                {
                    selector: 'node',
                    style: {
                        'label': 'data(label)',
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'background-color': '#6366f1',
                        'color': '#ffffff',
                        'font-size': '12px',
                        'font-weight': '600',
                        'width': (ele) => Math.max(60, ele.data('lines_count') * 10 + 40),
                        'height': (ele) => Math.max(40, ele.data('lines_count') * 8 + 30),
                        'text-wrap': 'wrap',
                        'text-max-width': '100px',
                        'border-width': (ele) => ele.data('is_start') ? 4 : 2,
                        'border-color': (ele) => ele.data('is_start') ? '#10b981' : '#3d3d3d'
                    }
                },
                {
                    selector: 'node:selected',
                    style: {
                        'background-color': '#8b5cf6',
                        'border-color': '#a78bfa'
                    }
                },
                {
                    selector: 'edge',
                    style: {
                        'width': 2,
                        'line-color': '#3d3d3d',
                        'target-arrow-color': '#3d3d3d',
                        'target-arrow-shape': 'triangle',
                        'curve-style': 'bezier',
                        'label': 'data(label)',
                        'font-size': '10px',
                        'color': '#a0a0a0',
                        'text-rotation': 'autorotate',
                        'text-margin-y': -10,
                        'text-background-color': '#1e1e1e',
                        'text-background-opacity': 0.8,
                        'text-background-padding': '3px'
                    }
                },
                {
                    selector: 'edge[condition]',
                    style: {
                        'line-color': '#f59e0b',
                        'target-arrow-color': '#f59e0b',
                        'line-style': 'dashed'
                    }
                },
                {
                    selector: 'edge:selected',
                    style: {
                        'line-color': '#8b5cf6',
                        'target-arrow-color': '#8b5cf6'
                    }
                },
                // Entry/Exit node styles
                {
                    selector: 'node[is_entry_target]',
                    style: {
                        'border-color': '#22c55e',
                        'border-width': 3,
                        'border-style': 'double'
                    }
                },
                {
                    selector: 'node[is_exit_node]',
                    style: {
                        'border-color': '#eab308',
                        'border-width': 3,
                        'border-style': 'dashed'
                    }
                },
                // Nodes that are both entry and exit
                {
                    selector: 'node[is_entry_target][is_exit_node]',
                    style: {
                        'border-color': '#06b6d4',
                        'border-width': 4,
                        'border-style': 'double'
                    }
                },
                // Path highlighting styles
                {
                    selector: 'node.path-visited',
                    style: {
                        'background-color': '#10b981',
                        'border-color': '#34d399',
                        'border-width': 3
                    }
                },
                {
                    selector: 'node.path-current',
                    style: {
                        'background-color': '#f59e0b',
                        'border-color': '#fbbf24',
                        'border-width': 4
                    }
                },
                {
                    selector: 'edge.path-taken',
                    style: {
                        'line-color': '#10b981',
                        'target-arrow-color': '#10b981',
                        'width': 3
                    }
                }
            ],

            layout: {
                name: 'dagre',
                rankDir: 'TB',
                nodeSep: 50,
                rankSep: 100
            }
        });

        // Node click handler
        this.cy.on('tap', 'node', (evt) => {
            const node = evt.target;
            this.showNodeInspector(node.data());
        });

        // Edge click handler
        this.cy.on('tap', 'edge', (evt) => {
            const edge = evt.target;
            this.showEdgeInspector(edge.data());
        });

        // Click on background to close inspector
        this.cy.on('tap', (evt) => {
            if (evt.target === this.cy) {
                this.hideInspector();
            }
        });

        // Right-click context menu on nodes
        this.cy.on('cxttap', 'node', (evt) => {
            evt.originalEvent.preventDefault();
            const node = evt.target;
            const nodeId = node.data('id');

            // Don't show context menu for END node
            if (nodeId === 'END') return;

            // Show/hide "Resume from history" option based on whether node was visited
            const historyItem = this.contextMenu.querySelector('.context-menu-history');
            if (this.lastPlayedPath.includes(nodeId)) {
                historyItem.classList.remove('hidden');
            } else {
                historyItem.classList.add('hidden');
            }

            // Position and show context menu
            const pos = evt.originalEvent;
            this.contextMenu.style.left = pos.clientX + 'px';
            this.contextMenu.style.top = pos.clientY + 'px';
            this.contextMenu.dataset.nodeId = nodeId;
            this.contextMenu.classList.remove('hidden');
        });
    }

    async loadFileList() {
        try {
            const response = await fetch('/api/dialogues');
            const data = await response.json();

            const selector = document.getElementById('file-selector');
            selector.innerHTML = '<option value="">Select a dialogue file...</option>';

            if (data.files && data.files.length > 0) {
                // Group by category
                const grouped = {};
                data.files.forEach(file => {
                    if (!grouped[file.category]) {
                        grouped[file.category] = [];
                    }
                    grouped[file.category].push(file);
                });

                // Add optgroups
                Object.keys(grouped).sort().forEach(category => {
                    const optgroup = document.createElement('optgroup');
                    optgroup.label = category;

                    grouped[category].forEach(file => {
                        const option = document.createElement('option');
                        option.value = file.relative_path;
                        option.textContent = file.name;
                        optgroup.appendChild(option);
                    });

                    selector.appendChild(optgroup);
                });
            }
        } catch (error) {
            console.error('Failed to load file list:', error);
            this.showNotification('Failed to load file list', 'error');
        }
    }

    async loadFile(relativePath) {
        // Check for unsaved changes before loading new file
        if (this.hasUnsavedChanges) {
            const confirmed = confirm('You have unsaved changes. Discard them and load a new file?');
            if (!confirmed) {
                // Reset selector to current file
                document.getElementById('file-selector').value = this.currentFilePath || '';
                return;
            }
        }

        try {
            const response = await fetch(`/api/file/${relativePath}`);
            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            this.editor.setValue(data.content);
            this.currentFile = data;
            this.currentFilePath = relativePath;
            this.originalContent = data.content;
            this.originalLines = data.content.split('\n');
            this.hasUnsavedChanges = false;

            // Clear modified gutter markers
            this.editor.clearGutter('CodeMirror-gutter-modified');

            // Update UI
            this.updateUnsavedUI();

            // Clear any pending preview timeout (setValue triggers change handler)
            clearTimeout(this.previewTimeout);

            // Auto-validate on load
            await this.validateDialogue();

            console.log(`📂 Loaded: ${data.name}`);
            this.showNotification(`Loaded: ${data.name}`, 'success');
        } catch (error) {
            console.error('Failed to load file:', error);
            this.showNotification(`Failed to load file: ${error.message}`, 'error');
        }
    }

    showNewFileModal(preserveContent = false) {
        // Check for unsaved changes (only if not preserving content - i.e., normal "New" flow)
        if (!preserveContent && this.hasUnsavedChanges) {
            const confirmed = confirm('You have unsaved changes. Discard them and create a new file?');
            if (!confirmed) return;
        }

        // Create modal
        const title = preserveContent ? '💾 Save Dialogue As' : '📝 Create New Dialogue';
        const buttonText = preserveContent ? 'Save' : 'Create';

        const modal = document.createElement('div');
        modal.className = 'new-file-modal';
        modal.innerHTML = `
            <div class="new-file-backdrop"></div>
            <div class="new-file-container">
                <div class="new-file-header">
                    <h2>${title}</h2>
                    <button class="btn-close new-file-close">×</button>
                </div>
                <div class="new-file-body">
                    <label for="new-file-name">File name:</label>
                    <input type="text" id="new-file-name" placeholder="my_dialogue" class="new-file-input">
                    <small class="new-file-hint">File will be saved as <code><span class="file-preview">my_dialogue</span>.dlg</code> in the dialogues folder</small>
                    <div class="new-file-subfolder">
                        <label for="new-file-subfolder">Subfolder (optional):</label>
                        <input type="text" id="new-file-subfolder" placeholder="npcs" class="new-file-input">
                        <small class="new-file-hint">Create in a subfolder, e.g., "npcs" or "quests/chapter1"</small>
                    </div>
                </div>
                <div class="new-file-footer">
                    <button class="btn btn-secondary new-file-cancel">Cancel</button>
                    <button class="btn btn-primary new-file-create">${buttonText}</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Focus input
        const nameInput = modal.querySelector('#new-file-name');
        const subfolderInput = modal.querySelector('#new-file-subfolder');
        const previewSpan = modal.querySelector('.file-preview');
        nameInput.focus();

        // Update preview
        const updatePreview = () => {
            const name = nameInput.value.trim() || 'my_dialogue';
            const subfolder = subfolderInput.value.trim();
            previewSpan.textContent = subfolder ? `${subfolder}/${name}` : name;
        };
        nameInput.addEventListener('input', updatePreview);
        subfolderInput.addEventListener('input', updatePreview);

        // Close handlers
        const closeModal = () => modal.remove();
        modal.querySelector('.new-file-backdrop').addEventListener('click', closeModal);
        modal.querySelector('.new-file-close').addEventListener('click', closeModal);
        modal.querySelector('.new-file-cancel').addEventListener('click', closeModal);

        // Create handler
        modal.querySelector('.new-file-create').addEventListener('click', async () => {
            const name = nameInput.value.trim();
            const subfolder = subfolderInput.value.trim();

            if (!name) {
                this.showNotification('Please enter a file name', 'warning');
                return;
            }

            // Validate name (no special chars except underscores and hyphens)
            if (!/^[\w\-]+$/.test(name)) {
                this.showNotification('File name can only contain letters, numbers, underscores, and hyphens', 'warning');
                return;
            }

            const filename = subfolder ? `${subfolder}/${name}` : name;
            await this.createNewFile(filename, preserveContent);
            closeModal();
        });

        // Enter key to create
        nameInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                modal.querySelector('.new-file-create').click();
            } else if (e.key === 'Escape') {
                closeModal();
            }
        });
    }

    async createNewFile(filename, preserveContent = false) {
        // Capture current content before creating file (for "Save As" flow)
        const currentContent = preserveContent ? this.editor.getValue() : null;

        try {
            const response = await fetch('/api/new-file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename })
            });

            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            // Refresh file list
            await this.loadFileList();

            if (preserveContent && currentContent) {
                // "Save As" flow: keep current content, just associate with new file
                this.currentFile = { name: filename.split('/').pop() };
                this.currentFilePath = data.path;
                this.originalContent = currentContent;
                this.originalLines = currentContent.split('\n');

                // Update file selector
                const selector = document.getElementById('file-selector');
                if (selector) {
                    selector.value = data.path;
                }

                // Save the current content to the new file
                await this.handleSave();
                this.showNotification(`Saved as: ${data.path}`, 'success');
            } else {
                // Normal "New" flow: load the template
                await this.loadFile(data.path);
                this.showNotification(`Created: ${data.path}`, 'success');
            }

            console.log(`📝 Created new file: ${data.path}`);
        } catch (error) {
            console.error('Failed to create file:', error);
            this.showNotification(`Failed to create file: ${error.message}`, 'error');
        }
    }

    showImportStateModal() {
        // Check if a file is loaded
        if (!this.currentFile) {
            this.showNotification('Please load or create a dialogue file first', 'warning');
            return;
        }

        // Create modal
        const modal = document.createElement('div');
        modal.className = 'import-state-modal';
        modal.innerHTML = `
            <div class="import-state-backdrop"></div>
            <div class="import-state-container">
                <div class="import-state-header">
                    <h2>📥 Import Game State</h2>
                    <button class="btn-close import-state-close">×</button>
                </div>
                <div class="import-state-body">
                    <p class="import-state-description">
                        Import state from a JSON or DLG file to update the <code>[state]</code> section.
                        This is useful for carrying state between dialogue scenes.
                    </p>

                    <div class="import-state-source">
                        <label>Import from:</label>
                        <div class="import-source-tabs">
                            <button class="import-source-tab active" data-source="file">📁 File</button>
                            <button class="import-source-tab" data-source="paste">📋 Paste</button>
                        </div>
                    </div>

                    <div class="import-state-content" data-content="file">
                        <input type="file" id="import-state-file-input" accept=".json,.dlg,.txt" class="hidden">
                        <button class="btn btn-secondary import-state-choose-file">Choose File...</button>
                        <span class="import-state-filename">No file selected</span>
                    </div>

                    <div class="import-state-content hidden" data-content="paste">
                        <textarea id="import-state-paste" placeholder="Paste JSON or DLG commands here...
Example JSON:
{
  &quot;variables&quot;: {&quot;gold&quot;: 100, &quot;completed_quest&quot;: true},
  &quot;inventory&quot;: [&quot;sword&quot;, &quot;potion&quot;],
  &quot;companions&quot;: [&quot;guide&quot;]
}

Example DLG:
*set gold = 100
*set completed_quest = true
*give_item sword
*add_companion guide"></textarea>
                    </div>

                    <div class="import-state-mode">
                        <label>Import mode:</label>
                        <div class="import-mode-options">
                            <label class="import-mode-option">
                                <input type="radio" name="import-mode" value="replace" checked>
                                <span>🔄 Replace</span>
                                <small>Clear existing state and use imported values</small>
                            </label>
                            <label class="import-mode-option">
                                <input type="radio" name="import-mode" value="merge">
                                <span>➕ Merge</span>
                                <small>Keep existing state, add/override with imported values</small>
                            </label>
                        </div>
                    </div>
                </div>
                <div class="import-state-footer">
                    <button class="btn btn-secondary import-state-cancel">Cancel</button>
                    <button class="btn btn-primary import-state-import">Import</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Tab switching
        const fileContent = modal.querySelector('[data-content="file"]');
        const pasteContent = modal.querySelector('[data-content="paste"]');
        modal.querySelectorAll('.import-source-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                modal.querySelectorAll('.import-source-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                fileContent.classList.toggle('hidden', tab.dataset.source !== 'file');
                pasteContent.classList.toggle('hidden', tab.dataset.source !== 'paste');
            });
        });

        // File selection
        const fileInput = modal.querySelector('#import-state-file-input');
        const filenameSpan = modal.querySelector('.import-state-filename');
        let selectedFile = null;

        modal.querySelector('.import-state-choose-file').addEventListener('click', () => {
            fileInput.click();
        });

        fileInput.addEventListener('change', (e) => {
            selectedFile = e.target.files[0];
            filenameSpan.textContent = selectedFile ? selectedFile.name : 'No file selected';
        });

        // Close handlers
        const closeModal = () => modal.remove();
        modal.querySelector('.import-state-backdrop').addEventListener('click', closeModal);
        modal.querySelector('.import-state-close').addEventListener('click', closeModal);
        modal.querySelector('.import-state-cancel').addEventListener('click', closeModal);

        // Escape key
        const escHandler = (e) => {
            if (e.key === 'Escape') {
                closeModal();
                document.removeEventListener('keydown', escHandler);
            }
        };
        document.addEventListener('keydown', escHandler);

        // Import handler
        modal.querySelector('.import-state-import').addEventListener('click', async () => {
            const activeSource = modal.querySelector('.import-source-tab.active').dataset.source;
            const mode = modal.querySelector('input[name="import-mode"]:checked').value;

            let content = null;

            if (activeSource === 'file') {
                if (!selectedFile) {
                    this.showNotification('Please select a file', 'warning');
                    return;
                }
                content = await selectedFile.text();
            } else {
                content = modal.querySelector('#import-state-paste').value.trim();
                if (!content) {
                    this.showNotification('Please paste some content', 'warning');
                    return;
                }
            }

            try {
                let importedState;

                // Try to parse as JSON first
                try {
                    importedState = JSON.parse(content);
                } catch {
                    // Not JSON, parse as DLG commands
                    importedState = this.parseDLGState(content);
                }

                // Apply to editor
                this.applyImportedState(importedState, mode);

                this.showNotification(`State ${mode === 'replace' ? 'replaced' : 'merged'} successfully!`, 'success');
                closeModal();
            } catch (error) {
                console.error('Import error:', error);
                this.showNotification(`Failed to import: ${error.message}`, 'error');
            }
        });
    }

    parseDLGState(content) {
        const state = { variables: {}, inventory: [], companions: [] };
        const lines = content.split('\n');

        for (const line of lines) {
            const trimmed = line.trim();

            // Skip comments and empty lines
            if (!trimmed || trimmed.startsWith('#')) continue;

            // Parse commands
            if (trimmed.startsWith('*set')) {
                const match = trimmed.match(/\*set\s+(\w+)\s*=\s*(.+)/);
                if (match) {
                    let value = match[2].trim();
                    if (value.toLowerCase() === 'true') value = true;
                    else if (value.toLowerCase() === 'false') value = false;
                    else if (!isNaN(value)) value = parseInt(value, 10);
                    state.variables[match[1]] = value;
                }
            } else if (trimmed.startsWith('*give_item')) {
                const match = trimmed.match(/\*give_item\s+(\w+)/);
                if (match) state.inventory.push(match[1]);
            } else if (trimmed.startsWith('*add_companion')) {
                const match = trimmed.match(/\*add_companion\s+(\w+)/);
                if (match) state.companions.push(match[1]);
            }
        }

        return state;
    }

    applyImportedState(importedState, mode) {
        // Get current editor content
        const content = this.editor.getValue();
        const lines = content.split('\n');

        // Generate new state commands
        let stateCommands = [];

        if (mode === 'merge') {
            // Keep existing state commands, add/override with imported
            let inState = false;
            for (const line of lines) {
                const trimmed = line.trim();
                if (trimmed === '[state]') {
                    inState = true;
                    continue;
                }
                if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                    inState = false;
                }
                if (inState && trimmed.startsWith('*')) {
                    stateCommands.push(trimmed);
                }
            }
        }

        // Add imported state
        for (const [key, value] of Object.entries(importedState.variables || {})) {
            // Remove existing set for this var if merging
            stateCommands = stateCommands.filter(cmd => !cmd.match(new RegExp(`^\\*set\\s+${key}\\s*=`)));
            stateCommands.push(`*set ${key} = ${value}`);
        }

        for (const item of importedState.inventory || []) {
            if (!stateCommands.some(cmd => cmd === `*give_item ${item}`)) {
                stateCommands.push(`*give_item ${item}`);
            }
        }

        for (const companion of importedState.companions || []) {
            if (!stateCommands.some(cmd => cmd === `*add_companion ${companion}`)) {
                stateCommands.push(`*add_companion ${companion}`);
            }
        }

        // Build new content with updated [state] section
        let newContent = '';
        let foundState = false;
        let skippingState = false;

        for (let i = 0; i < lines.length; i++) {
            const trimmed = lines[i].trim();

            if (trimmed === '[state]') {
                foundState = true;
                skippingState = true;
                newContent += '[state]\n';
                for (const cmd of stateCommands) {
                    newContent += cmd + '\n';
                }
                continue;
            }

            if (skippingState) {
                if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                    skippingState = false;
                    newContent += '\n' + lines[i] + '\n';
                }
                continue;
            }

            newContent += lines[i] + '\n';
        }

        // If no [state] section existed, add one after [characters]
        if (!foundState) {
            const charactersIndex = newContent.indexOf('[characters]');
            if (charactersIndex !== -1) {
                const nextSectionMatch = newContent.slice(charactersIndex + 12).match(/\n\[/);
                if (nextSectionMatch) {
                    const insertPos = charactersIndex + 12 + nextSectionMatch.index;
                    let stateBlock = '\n[state]\n';
                    for (const cmd of stateCommands) {
                        stateBlock += cmd + '\n';
                    }
                    newContent = newContent.slice(0, insertPos) + stateBlock + newContent.slice(insertPos);
                }
            }
        }

        // Update editor
        this.editor.setValue(newContent.trim() + '\n');
        this.hasUnsavedChanges = true;
        this.updateUnsavedUI();
    }

    async handleSave() {
        const content = this.editor.getValue();

        // If no file is associated, prompt to create one (Save As flow)
        if (!this.currentFilePath) {
            if (!content.trim()) {
                this.showNotification('Nothing to save', 'warning');
                return;
            }
            this.showNewFileModal(true); // preserveContent = true
            return;
        }

        try {
            const response = await fetch('/api/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    path: this.currentFilePath,
                    content: content
                })
            });

            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            // Update original content to current
            this.originalContent = content;
            this.originalLines = content.split('\n');
            this.hasUnsavedChanges = false;

            // Clear modified gutter markers
            this.editor.clearGutter('CodeMirror-gutter-modified');

            // Update UI
            this.updateUnsavedUI();

            this.showNotification('File saved!', 'success');
            console.log('💾 Saved:', this.currentFilePath);
        } catch (error) {
            console.error('Save failed:', error);
            this.showNotification(`Save failed: ${error.message}`, 'error');
        }
    }

    async handleReload() {
        if (!this.currentFilePath) {
            this.showNotification('No file loaded to reload', 'warning');
            return;
        }

        if (this.hasUnsavedChanges) {
            const confirmed = confirm('You have unsaved changes. Discard them and reload from disk?');
            if (!confirmed) {
                return;
            }
        }

        try {
            const response = await fetch(`/api/file/${this.currentFilePath}`);
            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            this.editor.setValue(data.content);
            this.originalContent = data.content;
            this.originalLines = data.content.split('\n');
            this.hasUnsavedChanges = false;

            // Clear modified gutter markers
            this.editor.clearGutter('CodeMirror-gutter-modified');

            // Update UI
            this.updateUnsavedUI();

            // Clear any pending preview timeout (setValue triggers change handler)
            clearTimeout(this.previewTimeout);

            // Re-validate
            await this.validateDialogue();

            this.showNotification('File reloaded from disk', 'success');
            console.log('↩️ Reloaded:', this.currentFilePath);
        } catch (error) {
            console.error('Reload failed:', error);
            this.showNotification(`Reload failed: ${error.message}`, 'error');
        }
    }

    toggleVimMode() {
        this.vimMode = !this.vimMode;

        if (this.vimMode) {
            this.editor.setOption('keyMap', 'vim');
            document.getElementById('vim-mode-btn').classList.add('vim-active');
            document.getElementById('vim-indicator').classList.remove('hidden');
            this.showNotification('Vim mode enabled', 'success');
        } else {
            this.editor.setOption('keyMap', 'default');
            document.getElementById('vim-mode-btn').classList.remove('vim-active');
            document.getElementById('vim-indicator').classList.add('hidden');
            this.showNotification('Vim mode disabled', 'info');
        }

        // Re-focus editor
        this.editor.focus();
    }

    toggleGuide(show) {
        const guidePanel = document.getElementById('guide-panel');
        if (show) {
            guidePanel.classList.remove('hidden');
        } else {
            guidePanel.classList.add('hidden');
        }
    }

    async validateDialogue() {
        // Clear any existing notifications before showing new validation results
        this.clearNotifications();

        const content = this.editor.getValue();

        try {
            const response = await fetch('/api/parse', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ content })
            });

            const data = await response.json();

            if (data.error) {
                this.showValidationResults({
                    valid: false,
                    errors: [data.error],
                    warnings: []
                });
                return;
            }

            // Update stats
            if (data.stats) {
                this.updateStats(data.stats);
            }

            // Update graph
            if (data.graph) {
                this.updateGraph(data.graph);
            }

            // Show validation results
            this.showValidationResults(data);

        } catch (error) {
            console.error('Validation error:', error);
            this.showValidationResults({
                valid: false,
                errors: [error.message],
                warnings: []
            });
        }
    }

    updateStats(stats) {
        document.getElementById('stat-nodes').textContent = stats.nodes || 0;
        document.getElementById('stat-characters').textContent = stats.characters || 0;
        document.getElementById('stat-lines').textContent = stats.dialogue_lines || 0;
        document.getElementById('stat-choices').textContent = stats.choices || 0;
    }

    updateGraph(graphData) {
        // Clear existing graph
        this.cy.elements().remove();

        // Add new nodes and edges
        this.cy.add(graphData.nodes);
        this.cy.add(graphData.edges);

        // Apply layout (dagre is default)
        const layoutName = document.getElementById('layout-selector').value || 'dagre';
        this.applyLayout(layoutName);

        // Fit graph to screen after layout completes
        setTimeout(() => {
            this.cy.fit(null, 50);
        }, 100);
    }

    applyLayout(layoutName) {
        let layoutOptions;

        if (layoutName === 'breadthfirst') {
            layoutOptions = {
                name: 'breadthfirst',
                directed: true,
                spacingFactor: 1.5,
                animate: true
            };
        } else {
            // Default: dagre tree layout
            layoutOptions = {
                name: 'dagre',
                rankDir: 'TB',
                nodeSep: 50,
                rankSep: 100,
                animate: true
            };
        }

        const layout = this.cy.layout(layoutOptions);
        layout.run();
    }

    /**
     * Format a validation message, extracting line numbers and making them clickable
     */
    formatValidationMessage(message) {
        // Pattern: "Line X:" or "Line X," at the start of the message
        const lineMatch = message.match(/^Line\s+(\d+)[:\s,]/i);
        if (lineMatch) {
            const lineNum = parseInt(lineMatch[1], 10);
            const restOfMessage = message.substring(lineMatch[0].length).trim();
            return `<span class="validation-line-link" data-line="${lineNum}">Line ${lineNum}</span>: ${escapeHtml(restOfMessage)}`;
        }
        return escapeHtml(message);
    }

    showValidationResults(data) {
        const panel = document.getElementById('validation-panel');
        const content = document.getElementById('validation-content');
        const icon = document.getElementById('validation-icon');
        const title = document.getElementById('validation-title');

        // Remove collapsed class to show results
        panel.classList.remove('collapsed');

        if (data.valid && (!data.errors || data.errors.length === 0)) {
            icon.textContent = '✅';
            title.textContent = 'Validation Passed';

            let html = '<div class="validation-success">';
            html += '<strong>✓ No errors found!</strong>';

            if (data.warnings && data.warnings.length > 0) {
                html += `<p style="margin-top: 8px;">Found ${data.warnings.length} warning(s)</p>`;
            }
            html += '</div>';

            if (data.warnings && data.warnings.length > 0) {
                data.warnings.forEach(warning => {
                    html += `<div class="validation-warning">
                        <div class="validation-warning-title">⚠️ Warning</div>
                        <div>${this.formatValidationMessage(warning)}</div>
                    </div>`;
                });
            }

            content.innerHTML = html;
        } else {
            icon.textContent = '❌';
            title.textContent = 'Validation Failed';

            let html = '';

            if (data.errors && data.errors.length > 0) {
                data.errors.forEach(error => {
                    html += `<div class="validation-error">
                        <div class="validation-error-title">❌ Error</div>
                        <div>${this.formatValidationMessage(error)}</div>
                    </div>`;
                });
            }

            if (data.warnings && data.warnings.length > 0) {
                data.warnings.forEach(warning => {
                    html += `<div class="validation-warning">
                        <div class="validation-warning-title">⚠️ Warning</div>
                        <div>${this.formatValidationMessage(warning)}</div>
                    </div>`;
                });
            }

            content.innerHTML = html || '<p class="validation-empty">Unknown error occurred</p>';
        }

        // Add click handlers for line number links
        content.querySelectorAll('.validation-line-link').forEach(link => {
            link.addEventListener('click', () => {
                const lineNum = parseInt(link.dataset.line, 10);
                // Jump to line in editor (0-indexed)
                this.editor.setCursor({ line: lineNum - 1, ch: 0 });
                this.editor.focus();
                // Scroll the line into view
                this.editor.scrollIntoView({ line: lineNum - 1, ch: 0 }, 100);
            });
        });
    }

    showNodeInspector(nodeData) {
        const inspector = document.getElementById('node-inspector');
        const title = document.getElementById('inspector-title');
        const content = document.getElementById('inspector-content');

        title.textContent = `Node: ${nodeData.label}`;

        let html = '';

        // Node info
        html += '<div class="inspector-section">';
        html += '<h4>Info</h4>';
        html += `<div class="inspector-item">`;
        html += `Lines: ${nodeData.lines_count} | Choices: ${nodeData.choices_count}`;
        if (nodeData.is_start) {
            html += ' | <span style="color: #10b981">START</span>';
        }
        html += `</div>`;
        html += '</div>';

        // Dialogue lines
        if (nodeData.lines && nodeData.lines.length > 0) {
            html += '<div class="inspector-section">';
            html += '<h4>Dialogue</h4>';
            nodeData.lines.forEach(line => {
                html += '<div class="inspector-item">';
                html += `<div class="inspector-speaker">${escapeHtml(line.speaker)}</div>`;
                html += `<div class="inspector-text">"${escapeHtml(line.text)}"</div>`;
                if (line.tags && line.tags.length > 0) {
                    html += `<div class="inspector-tags" style="color: #10b981; font-size: 0.85em; margin-top: 2px;">[${escapeHtml(line.tags.join(', '))}]</div>`;
                }
                if (line.condition) {
                    html += `<div class="inspector-condition" style="color: #f59e0b; font-size: 0.85em; margin-top: 2px;">{${escapeHtml(line.condition)}}</div>`;
                }
                html += '</div>';
            });
            html += '</div>';
        }

        // Commands
        if (nodeData.commands && nodeData.commands.length > 0) {
            html += '<div class="inspector-section">';
            html += '<h4>Commands</h4>';
            nodeData.commands.forEach(cmd => {
                html += `<div class="inspector-item">`;
                html += `<div class="inspector-command">*${escapeHtml(cmd)}</div>`;
                html += `</div>`;
            });
            html += '</div>';
        }

        content.innerHTML = html;
        inspector.classList.remove('hidden');
    }

    showEdgeInspector(edgeData) {
        const inspector = document.getElementById('node-inspector');
        const title = document.getElementById('inspector-title');
        const content = document.getElementById('inspector-content');

        title.textContent = 'Choice';

        let html = '';

        html += '<div class="inspector-section">';
        html += '<h4>Details</h4>';
        html += '<div class="inspector-item">';
        html += `<div><strong>From:</strong> ${escapeHtml(edgeData.source)}</div>`;
        html += `<div><strong>To:</strong> ${escapeHtml(edgeData.target)}</div>`;
        html += '</div>';

        if (edgeData.full_text) {
            html += '<div class="inspector-item">';
            html += `<div class="inspector-text">"${escapeHtml(edgeData.full_text)}"</div>`;
            html += '</div>';
        }

        if (edgeData.condition) {
            html += '<div class="inspector-item" style="border-left: 3px solid #f59e0b;">';
            html += `<div style="color: #f59e0b; font-weight: 600; margin-bottom: 4px;">Condition</div>`;
            html += `<div class="inspector-command">{${escapeHtml(edgeData.condition)}}</div>`;
            html += '</div>';
        }

        html += '</div>';

        content.innerHTML = html;
        inspector.classList.remove('hidden');
    }

    hideInspector() {
        document.getElementById('node-inspector').classList.add('hidden');
    }

    setupExportDropdown() {
        const exportBtn = document.getElementById('export-btn');
        const exportMenu = document.querySelector('.export-menu');

        // Toggle dropdown on button click
        exportBtn.addEventListener('click', async (e) => {
            e.stopPropagation();

            // Validate first
            const isValid = await this.checkValidation();
            if (!isValid) {
                this.showNotification('Cannot export: dialogue has validation errors', 'error');
                return;
            }

            exportMenu.classList.toggle('hidden');
        });

        // Handle menu item clicks
        exportMenu.addEventListener('click', async (e) => {
            const item = e.target.closest('.export-menu-item');
            if (!item) return;

            const format = item.dataset.format;
            exportMenu.classList.add('hidden');

            if (format === 'json') {
                await this.exportJSON();
            } else if (format === 'dlg') {
                this.exportDLG();
            }
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', () => {
            exportMenu.classList.add('hidden');
        });
    }

    async checkValidation() {
        const content = this.editor.getValue();

        try {
            const response = await fetch('/api/parse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });

            const data = await response.json();
            return data.valid && (!data.errors || data.errors.length === 0);
        } catch {
            return false;
        }
    }

    exportDLG() {
        const content = this.editor.getValue();
        const filename = (this.currentFile?.name || 'dialogue') + '.dlg';

        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);

        this.showNotification(`Exported ${filename}!`, 'success');
    }

    async exportJSON() {
        const content = this.editor.getValue();

        try {
            const response = await fetch('/api/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ content })
            });

            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            // Download the JSON
            const blob = new Blob([JSON.stringify(data.json, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = (this.currentFile?.name || 'dialogue') + '.json';
            a.click();
            URL.revokeObjectURL(url);

            this.showNotification('Exported to JSON!', 'success');
        } catch (error) {
            console.error('Export error:', error);
            this.showNotification(`Export failed: ${error.message}`, 'error');
        }
    }

    setupEventListeners() {
        // File selector
        document.getElementById('file-selector').addEventListener('change', (e) => {
            if (e.target.value) {
                this.loadFile(e.target.value);
            }
        });

        // Refresh files button
        document.getElementById('refresh-files').addEventListener('click', () => {
            this.loadFileList();
        });

        // New file button
        document.getElementById('new-file-btn').addEventListener('click', () => {
            this.showNewFileModal();
        });

        // Save button
        document.getElementById('save-btn').addEventListener('click', () => {
            this.handleSave();
        });

        // Reload button
        document.getElementById('reload-btn').addEventListener('click', () => {
            this.handleReload();
        });

        // Guide button
        document.getElementById('guide-btn').addEventListener('click', () => {
            this.toggleGuide(true);
        });

        // Close guide button
        document.getElementById('close-guide').addEventListener('click', () => {
            this.toggleGuide(false);
        });

        // Close guide when clicking backdrop
        document.querySelector('.guide-backdrop').addEventListener('click', () => {
            this.toggleGuide(false);
        });

        // Close guide with Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !document.getElementById('guide-panel').classList.contains('hidden')) {
                this.toggleGuide(false);
            }
        });

        // Validate button
        document.getElementById('validate-btn').addEventListener('click', () => {
            this.validateDialogue();
        });

        // Export dropdown
        this.setupExportDropdown();

        // Import State button
        document.getElementById('import-state-btn').addEventListener('click', () => {
            this.showImportStateModal();
        });

        // Play button
        document.getElementById('play-btn').addEventListener('click', () => {
            this.dialoguePlayer.play();
        });

        // Vim mode button
        document.getElementById('vim-mode-btn').addEventListener('click', () => {
            this.toggleVimMode();
        });

        // Toggle preview
        document.getElementById('toggle-preview').addEventListener('click', (e) => {
            this.autoPreview = !this.autoPreview;
            e.target.style.opacity = this.autoPreview ? '1' : '0.5';
            if (this.autoPreview) {
                this.validateDialogue();
            }
        });

        // Layout selector
        document.getElementById('layout-selector').addEventListener('change', (e) => {
            this.applyLayout(e.target.value);
        });

        // Fit graph button
        document.getElementById('fit-graph').addEventListener('click', () => {
            this.cy.fit(null, 50);
        });

        // Reset zoom button
        document.getElementById('reset-zoom').addEventListener('click', () => {
            this.cy.zoom(1);
            this.cy.center();
        });

        // Close inspector
        document.getElementById('close-inspector').addEventListener('click', () => {
            this.hideInspector();
        });

        // Toggle validation panel
        document.getElementById('toggle-validation').addEventListener('click', () => {
            const panel = document.getElementById('validation-panel');
            panel.classList.toggle('collapsed');
            document.getElementById('toggle-validation').textContent =
                panel.classList.contains('collapsed') ? '▲' : '▼';
        });

        document.querySelector('.validation-header').addEventListener('click', (e) => {
            if (e.target.id !== 'toggle-validation') {
                const panel = document.getElementById('validation-panel');
                panel.classList.toggle('collapsed');
                document.getElementById('toggle-validation').textContent =
                    panel.classList.contains('collapsed') ? '▲' : '▼';
            }
        });
    }

    setupResizer() {
        const resizer = document.querySelector('.resizer');
        const leftPanel = document.querySelector('.panel-editor');
        const rightPanel = document.querySelector('.panel-graph');

        let isResizing = false;

        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            const containerRect = document.querySelector('.content').getBoundingClientRect();
            const leftWidth = e.clientX - containerRect.left;
            const totalWidth = containerRect.width;
            const resizerWidth = 4; // Match CSS .resizer width
            const leftPercent = (leftWidth / totalWidth) * 100;

            if (leftPercent > 20 && leftPercent < 80) {
                // Use calc() to account for resizer width (subtract 2px from each panel)
                leftPanel.style.flex = `0 0 calc(${leftPercent}% - ${resizerWidth / 2}px)`;
                rightPanel.style.flex = `0 0 calc(${100 - leftPercent}% - ${resizerWidth / 2}px)`;

                // Refresh CodeMirror
                this.editor.refresh();

                // Resize cytoscape
                if (this.cy) {
                    this.cy.resize();
                }
            }
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = '';
            }
        });
    }

    clearNotifications() {
        // Remove all existing toast notifications
        document.querySelectorAll('.dlg-toast').forEach(toast => {
            toast.remove();
        });
    }

    showNotification(message, type = 'info') {
        // Create toast notification
        const toast = document.createElement('div');
        toast.className = `dlg-toast toast toast-${type}`;
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            z-index: 99999;
            animation: slideIn 0.3s ease;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        `;

        // Set colors based on type
        const colors = {
            success: { bg: '#10b981', color: '#fff' },
            error: { bg: '#ef4444', color: '#fff' },
            warning: { bg: '#f59e0b', color: '#fff' },
            info: { bg: '#6366f1', color: '#fff' }
        };

        const style = colors[type] || colors.info;
        toast.style.background = style.bg;
        toast.style.color = style.color;
        toast.textContent = message;

        document.body.appendChild(toast);

        // Remove after 3 seconds
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);

        console.log(`[${type.toUpperCase()}] ${message}`);
    }

    // Path highlighting methods for dialogue playback visualization
    clearPathHighlight() {
        if (!this.cy) return;
        this.cy.elements().removeClass('path-visited path-current path-taken');
    }

    highlightPath(path, currentNode = null) {
        if (!this.cy || !path || path.length === 0) return;

        // Clear previous highlights
        this.clearPathHighlight();

        // Highlight visited nodes (all except current)
        for (let i = 0; i < path.length; i++) {
            const nodeId = path[i];
            const node = this.cy.getElementById(nodeId);
            if (node.length > 0) {
                if (currentNode && nodeId === currentNode) {
                    node.addClass('path-current');
                } else {
                    node.addClass('path-visited');
                }
            }

            // Highlight edge from this node to the next
            if (i < path.length - 1) {
                const nextNodeId = path[i + 1];
                // Find edge between these nodes
                const edges = this.cy.edges(`[source = "${nodeId}"][target = "${nextNodeId}"]`);
                edges.addClass('path-taken');
            }
        }
    }
}
