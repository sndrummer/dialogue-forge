/**
 * DialoguePlayer - Handles interactive dialogue playback in the web UI
 */
import { GameState } from '../state/GameState.js';
import { escapeHtml, delay } from '../utils/helpers.js';

export class DialoguePlayer {
    constructor(app) {
        this.app = app;
        this.dialogueData = null;
        this.characters = {};
        this.initialStateCommands = []; // Commands from [state] section
        this.entries = {}; // Entry groups from [entry:name] sections (legacy)
        this.triggers = {}; // Trigger map: target -> [{type, target, condition, nodeId}]
        this.currentEntryGroup = null; // Currently active entry group (legacy)
        this.currentTrigger = null; // Currently active trigger target (e.g., "officer")
        this.state = null;
        this.currentNode = null;
        this.isPlaying = false;
        this.typewriterSpeed = 10; // ms per character (fast speed - default)
        this.modal = null;
        this.visitedPath = []; // Track path taken during playback
        this.knownItems = []; // Items found in dialogue (give_item, has_item)
        this.knownCompanions = []; // Companions found in dialogue (add_companion, companion:)
    }

    async play(startNode = null, initialState = null, skipPathReset = false) {
        // Get parsed dialogue data
        const content = this.app.editor.getValue();
        try {
            const response = await fetch('/api/parse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });
            const data = await response.json();

            if (data.error || !data.graph) {
                this.app.showNotification('Cannot play: dialogue has errors', 'error');
                return;
            }

            // Build dialogue data from parse result
            this.dialogueData = {};
            this.characters = data.characters || {};
            this.initialStateCommands = data.initial_state || [];
            this.entries = data.entries || {};
            this.knownItems = data.stats?.known_items || [];
            this.knownCompanions = data.stats?.known_companions || [];
            const startNodeId = startNode || data.start_node;

            // Convert graph nodes to dialogue format and build trigger map
            this.triggers = {};
            for (const node of data.graph.nodes) {
                const nodeData = node.data;
                this.dialogueData[nodeData.id] = {
                    id: nodeData.id,
                    lines: nodeData.lines || [],
                    commands: nodeData.commands || [],
                    choices: [],
                    is_exit_node: nodeData.is_exit_node || false,
                    is_end: nodeData.is_end || false,
                    is_entry_target: nodeData.is_entry_target || false,
                    entry_groups: nodeData.entry_groups || [],
                    triggers: nodeData.triggers || []
                };

                // Build trigger map: target -> list of {type, target, condition, nodeId}
                for (const trigger of (nodeData.triggers || [])) {
                    const key = trigger.target;  // e.g., "officer"
                    if (!this.triggers[key]) {
                        this.triggers[key] = [];
                    }
                    this.triggers[key].push({
                        type: trigger.type,
                        target: trigger.target,
                        condition: trigger.condition,
                        nodeId: nodeData.id
                    });
                }
            }

            // Add choices from edges
            for (const edge of data.graph.edges) {
                const edgeData = edge.data;
                const sourceNode = this.dialogueData[edgeData.source];
                if (sourceNode) {
                    sourceNode.choices.push({
                        target: edgeData.target,
                        text: edgeData.full_text || '',
                        condition: edgeData.condition
                    });
                }
            }

            // Initialize state
            if (initialState) {
                // When continuing from a previous scene with preserved state
                this.state = new GameState(initialState);
                // Execute [state] commands but DON'T overwrite existing variables
                // This allows new scene-specific variables to be initialized
                for (const cmd of this.initialStateCommands) {
                    this.state.executeCommand(cmd, true); // skipIfExists = true
                }
            } else {
                // Fresh playthrough - execute [state] commands first
                this.state = new GameState();
                for (const cmd of this.initialStateCommands) {
                    this.state.executeCommand(cmd);
                }
            }

            this.currentNode = startNodeId;
            this.isPlaying = true;

            // Initialize path tracking (unless already set by playFromNode)
            if (!skipPathReset) {
                this.visitedPath = [startNodeId];
                this.app.highlightPath(this.visitedPath, startNodeId);
            }

            // Show the play modal
            this.showModal();

            // Start playing
            await this.playNode(this.currentNode);

        } catch (error) {
            console.error('Play error:', error);
            this.app.showNotification('Failed to start playback: ' + error.message, 'error');
        }
    }

    async playFromNode(nodeId, mode = 'shortest') {
        // Compute path and state to reach this node
        const content = this.app.editor.getValue();

        try {
            const response = await fetch('/api/compute-path', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content, target_node: nodeId, mode })
            });
            const data = await response.json();

            if (data.error) {
                this.app.showNotification('Error computing path: ' + data.error, 'error');
                return;
            }

            if (data.warning) {
                this.app.showNotification(data.warning, 'warning');
            } else if (data.path_length) {
                // Show path info for non-warning cases
                const modeLabels = {
                    'shortest': 'Shortest',
                    'random': 'Random',
                    'explore': 'Exploratory'
                };
                const modeLabel = modeLabels[mode] || mode;
                this.app.showNotification(`${modeLabel} path: ${data.path_length} nodes`, 'success');
            }

            // Initialize visited path with the computed path (up to target node)
            if (data.path) {
                this.visitedPath = [...data.path];
                // Highlight the computed path with target as current
                this.app.highlightPath(this.visitedPath, nodeId);
            } else {
                this.visitedPath = [nodeId];
                this.app.highlightPath(this.visitedPath, nodeId);
            }

            // Play from the target node with computed state
            await this.play(nodeId, data.state, true); // true = skip path reset

        } catch (error) {
            console.error('Play from node error:', error);
            this.app.showNotification('Failed to compute path: ' + error.message, 'error');
        }
    }

    async playFromHistory(nodeId, fullPath) {
        // Replay the exact path from last play session up to and including the target node
        const content = this.app.editor.getValue();

        // Find the target node in the path and slice up to it
        const targetIndex = fullPath.indexOf(nodeId);
        if (targetIndex === -1) {
            this.app.showNotification('Node not found in play history', 'error');
            return;
        }

        // Get the path up to and including the target node
        const pathToReplay = fullPath.slice(0, targetIndex + 1);

        try {
            const response = await fetch('/api/replay-path', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content, path: pathToReplay })
            });
            const data = await response.json();

            if (data.error) {
                this.app.showNotification('Error replaying path: ' + data.error, 'error');
                return;
            }

            this.app.showNotification(`Resumed at node ${targetIndex + 1} of ${fullPath.length} from history`, 'success');

            // Initialize visited path with the replayed path
            this.visitedPath = [...pathToReplay];
            this.app.highlightPath(this.visitedPath, nodeId);

            // Play from the target node with replayed state
            await this.play(nodeId, data.state, true); // true = skip path reset

        } catch (error) {
            console.error('Play from history error:', error);
            this.app.showNotification('Failed to replay path: ' + error.message, 'error');
        }
    }

    showModal() {
        // Create the play modal
        this.modal = document.createElement('div');
        this.modal.className = 'play-modal';

        // Build NPC selector from triggers (@talk:npc) or legacy entries
        // Get unique talk trigger targets (NPCs you can talk to)
        const talkTargets = Object.keys(this.triggers).filter(target => {
            // Only include @talk triggers, not @event triggers
            return this.triggers[target].some(t => t.type === 'talk');
        });
        const entryNames = Object.keys(this.entries);

        // Combine both sources, preferring new triggers
        const npcList = [...new Set([...talkTargets, ...entryNames])];

        let entrySelector = '';
        if (npcList.length > 0) {
            entrySelector = `
                <div class="play-entry-selector">
                    <label>Talk to:</label>
                    <select class="entry-group-select">
                        <option value="">-- Select NPC --</option>
                        ${npcList.map(name => `<option value="${name}">${name}</option>`).join('')}
                    </select>
                    <button class="btn btn-sm btn-success talk-btn" disabled>Talk</button>
                </div>
            `;
        }

        this.modal.innerHTML = `
            <div class="play-modal-backdrop"></div>
            <div class="play-modal-container">
                <div class="play-modal-header">
                    <h2>Dialogue Playback</h2>
                    ${entrySelector}
                    <div class="play-modal-controls">
                        <button class="btn btn-sm play-state-btn" title="View/Edit game state">
                            <span>📊</span> State
                        </button>
                        <button class="btn btn-sm play-speed-btn" title="Toggle text speed">
                            <span>⚡</span> Speed: Fast
                        </button>
                        <button class="btn btn-sm btn-close-play" title="Exit playback">
                            ✕
                        </button>
                    </div>
                </div>
                <div class="play-modal-body">
                    <div class="play-dialogue-area">
                        <div class="play-dialogue-scroll">
                            <!-- Dialogue content will appear here -->
                        </div>
                    </div>
                    <div class="play-choices-area hidden">
                        <!-- Choices will appear here -->
                    </div>
                </div>
                <div class="play-modal-footer">
                    <div class="play-status">
                        <span class="play-node-indicator"></span>
                    </div>
                    <div class="play-stats">
                        <span class="play-stat harmony-stat hidden">☯️ <span class="value">0</span></span>
                        <span class="play-stat discord-stat hidden">💀 <span class="value">0</span></span>
                        <span class="play-stat xp-stat hidden">⭐ <span class="value">0</span></span>
                    </div>
                </div>
            </div>
            <div class="unified-state-panel hidden">
                <div class="play-state-header">
                    <h3>Game State</h3>
                    <button class="btn-close unified-state-close">×</button>
                </div>
                <div class="state-tabs">
                    <button class="state-tab active" data-tab="view">👁️ View</button>
                    <button class="state-tab" data-tab="edit">✏️ Edit</button>
                    <button class="state-tab" data-tab="io">💾 I/O</button>
                </div>
                <div class="state-tab-content" data-content="view">
                    <div class="play-state-content">
                        <!-- State view content -->
                    </div>
                </div>
                <div class="state-tab-content hidden" data-content="edit">
                    <div class="play-edit-state-content">
                        <!-- Editable state form -->
                    </div>
                    <div class="play-edit-state-footer">
                        <button class="btn btn-sm btn-primary play-apply-state">Apply Changes</button>
                    </div>
                </div>
                <div class="state-tab-content hidden" data-content="io">
                    <div class="play-state-io-content">
                        <div class="state-io-section">
                            <h4>Export Playthrough State</h4>
                            <p class="state-io-hint">Save your current game state to use in another dialogue file.</p>
                            <div class="state-io-buttons">
                                <button class="btn btn-sm btn-primary export-state-json">📦 JSON</button>
                                <button class="btn btn-sm btn-secondary export-state-dlg">📄 DLG Commands</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(this.modal);

        // Set up event listeners
        this.modal.querySelector('.btn-close-play').addEventListener('click', () => this.close());
        this.modal.querySelector('.play-modal-backdrop').addEventListener('click', () => this.close());
        this.modal.querySelector('.play-state-btn').addEventListener('click', () => this.toggleUnifiedStatePanel());
        this.modal.querySelector('.unified-state-close').addEventListener('click', () => this.toggleUnifiedStatePanel());
        this.modal.querySelector('.play-apply-state').addEventListener('click', () => this.applyStateChanges());
        this.modal.querySelector('.export-state-json').addEventListener('click', () => this.exportStateJSON());
        this.modal.querySelector('.export-state-dlg').addEventListener('click', () => this.exportStateDLG());
        this.modal.querySelector('.play-speed-btn').addEventListener('click', (e) => this.toggleSpeed(e.currentTarget));

        // Tab switching
        this.modal.querySelectorAll('.state-tab').forEach(tab => {
            tab.addEventListener('click', (e) => this.switchStateTab(e.target.dataset.tab));
        });

        // NPC selector (triggers or legacy entry groups)
        const entrySelect = this.modal.querySelector('.entry-group-select');
        const talkBtn = this.modal.querySelector('.talk-btn');
        if (entrySelect && talkBtn) {
            entrySelect.addEventListener('change', () => {
                talkBtn.disabled = !entrySelect.value;
            });
            talkBtn.addEventListener('click', () => {
                if (entrySelect.value) {
                    const target = entrySelect.value;
                    // Prefer new trigger system, fall back to legacy entries
                    if (this.triggers[target] && this.triggers[target].some(t => t.type === 'talk')) {
                        this.startFromTrigger(target);
                    } else if (this.entries[target]) {
                        this.startFromEntryGroup(target);
                    }
                }
            });
        }

        // Keyboard shortcuts
        this.keyHandler = (e) => {
            if (e.key === 'Escape') {
                this.close();
            }
        };
        document.addEventListener('keydown', this.keyHandler);

        // Update stats display
        this.updateStatsDisplay();
    }

    /**
     * Start dialogue from an entry group by evaluating its conditions
     */
    startFromEntryGroup(entryName) {
        const entryGroup = this.entries[entryName];
        if (!entryGroup) {
            this.app.showNotification(`Entry group "${entryName}" not found`, 'error');
            return;
        }

        this.currentEntryGroup = entryName;

        // Find the first matching route
        for (const route of entryGroup.routes) {
            if (!route.condition || this.state.evaluateCondition(route.condition)) {
                // Found a matching entry!
                this.app.showNotification(`Starting conversation with ${entryName} at [${route.target}]`, 'success');

                // Clear dialogue area for new conversation
                const scrollArea = this.modal.querySelector('.play-dialogue-scroll');
                scrollArea.innerHTML = '';

                // Reset visited path for this conversation
                this.visitedPath = [route.target];
                this.app.highlightPath(this.visitedPath, route.target);

                // Play from the matched node
                this.playNode(route.target);
                return;
            }
        }

        // No conditions matched and no default route
        this.app.showNotification(`No matching entry route for ${entryName} with current state`, 'warning');
    }

    /**
     * Start dialogue from a trigger (e.g., @talk:officer)
     * Evaluates conditions in REVERSE order (last defined = highest priority)
     * This allows natural dialogue progression: later nodes in file = later in story
     */
    startFromTrigger(triggerTarget) {
        const triggerRoutes = this.triggers[triggerTarget];
        if (!triggerRoutes || triggerRoutes.length === 0) {
            this.app.showNotification(`No triggers found for "${triggerTarget}"`, 'error');
            return;
        }

        this.currentTrigger = triggerTarget;

        // Check triggers in REVERSE order (stack behavior)
        // Later nodes in the file are checked first (more advanced conversation states)
        for (let i = triggerRoutes.length - 1; i >= 0; i--) {
            const trigger = triggerRoutes[i];
            if (!trigger.condition || this.state.evaluateCondition(trigger.condition)) {
                // Found a matching trigger!
                const triggerType = trigger.type === 'talk' ? '💬' : '⚡';
                this.app.showNotification(`${triggerType} ${triggerTarget} → [${trigger.nodeId}]`, 'success');

                // Clear dialogue area for new conversation
                const scrollArea = this.modal.querySelector('.play-dialogue-scroll');
                scrollArea.innerHTML = '';

                // Reset visited path for this conversation
                this.visitedPath = [trigger.nodeId];
                this.app.highlightPath(this.visitedPath, trigger.nodeId);

                // Play from the matched node
                this.playNode(trigger.nodeId);
                return;
            }
        }

        // No conditions matched - NPC has nothing to say
        this.app.showNotification(`${triggerTarget} has nothing to say (no conditions matched)`, 'warning');
    }

    /**
     * Check if current node is an exit node
     * Either marked with @end, is_exit_node, or listed in an entry group's exits
     */
    isExitNode(nodeId) {
        const node = this.dialogueData[nodeId];
        if (!node) return false;

        // Check for new @end marker
        if (node.is_end) return true;

        // Check legacy is_exit_node flag
        if (node.is_exit_node) return true;

        // Also check if it's an exit for the current entry group (legacy)
        if (this.currentEntryGroup) {
            const entryGroup = this.entries[this.currentEntryGroup];
            if (entryGroup && entryGroup.exits.includes(nodeId)) return true;
        }

        return false;
    }

    /**
     * Show the exit point UI when reaching an exit node (@end)
     */
    async showExitPoint() {
        const scrollArea = this.modal.querySelector('.play-dialogue-scroll');
        const choicesArea = this.modal.querySelector('.play-choices-area');

        choicesArea.classList.add('hidden');

        // Find available triggers to "talk again"
        // Priority: current trigger > triggers from current node > legacy entry groups
        const node = this.dialogueData[this.currentNode];
        let talkAgainTarget = null;
        let talkAgainType = 'trigger';  // 'trigger' or 'entry'

        // First check if we have a current trigger
        if (this.currentTrigger && this.triggers[this.currentTrigger]) {
            talkAgainTarget = this.currentTrigger;
        }
        // Then check node's triggers
        else if (node && node.triggers && node.triggers.length > 0) {
            talkAgainTarget = node.triggers[0].target;
        }
        // Legacy: check entry groups
        else if (this.currentEntryGroup) {
            talkAgainTarget = this.currentEntryGroup;
            talkAgainType = 'entry';
        } else {
            // Check all entries for this node
            for (const [name, group] of Object.entries(this.entries)) {
                if (group.exits.includes(this.currentNode)) {
                    talkAgainTarget = name;
                    talkAgainType = 'entry';
                    break;
                }
            }
        }

        const exitEl = document.createElement('div');
        exitEl.className = 'dialogue-exit-point';
        exitEl.innerHTML = `
            <div class="exit-title">💬 Conversation Ended</div>
            <div class="exit-info">Talk to other NPCs or edit game state to continue.</div>
            <div class="exit-buttons">
                ${talkAgainTarget ? `<button class="btn btn-primary talk-again-btn">🔄 Talk Again (${talkAgainTarget})</button>` : ''}
                <button class="btn btn-secondary continue-btn">▶️ Continue Flow</button>
            </div>
        `;

        scrollArea.appendChild(exitEl);
        scrollArea.scrollTop = scrollArea.scrollHeight;

        // Talk again - re-evaluate trigger/entry conditions
        const talkAgainBtn = exitEl.querySelector('.talk-again-btn');
        if (talkAgainBtn && talkAgainTarget) {
            talkAgainBtn.addEventListener('click', () => {
                if (talkAgainType === 'trigger') {
                    this.startFromTrigger(talkAgainTarget);
                } else {
                    this.startFromEntryGroup(talkAgainTarget);
                }
            });
        }

        // Continue flow - proceed with the node's choices as normal
        exitEl.querySelector('.continue-btn').addEventListener('click', async () => {
            exitEl.remove();
            const node = this.dialogueData[this.currentNode];
            if (node) {
                await this.showChoices(node.choices);
            }
        });
    }

    close() {
        this.isPlaying = false;
        // Preserve the visited path for "Resume from history" feature
        if (this.visitedPath.length > 0) {
            this.app.lastPlayedPath = [...this.visitedPath];
        }
        if (this.modal) {
            this.modal.remove();
            this.modal = null;
        }
        if (this.keyHandler) {
            document.removeEventListener('keydown', this.keyHandler);
        }
    }

    toggleUnifiedStatePanel() {
        const panel = this.modal.querySelector('.unified-state-panel');
        panel.classList.toggle('hidden');

        if (!panel.classList.contains('hidden')) {
            // Default to view tab
            this.switchStateTab('view');
        }
    }

    switchStateTab(tabName) {
        // Update tab buttons
        this.modal.querySelectorAll('.state-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });

        // Update tab content
        this.modal.querySelectorAll('.state-tab-content').forEach(content => {
            content.classList.toggle('hidden', content.dataset.content !== tabName);
        });

        // Update content based on tab
        if (tabName === 'view') {
            this.updateStatePanel();
        } else if (tabName === 'edit') {
            this.updateEditStatePanel();
        }
    }

    toggleStatePanel() {
        // Legacy method - redirect to unified panel
        this.toggleUnifiedStatePanel();
    }

    updateStatePanel() {
        const content = this.modal.querySelector('.play-state-content');

        let html = '<div class="state-section">';
        html += '<h4>Variables</h4>';
        const vars = Object.entries(this.state.variables);
        if (vars.length > 0) {
            html += '<ul class="state-list">';
            for (const [key, value] of vars) {
                html += `<li><span class="state-key">${key}</span>: <span class="state-value">${value}</span></li>`;
            }
            html += '</ul>';
        } else {
            html += '<p class="state-empty">(none)</p>';
        }
        html += '</div>';

        html += '<div class="state-section">';
        html += '<h4>Inventory</h4>';
        if (this.state.inventory.size > 0) {
            html += '<ul class="state-list">';
            for (const item of this.state.inventory) {
                html += `<li>🎒 ${item}</li>`;
            }
            html += '</ul>';
        } else {
            html += '<p class="state-empty">(empty)</p>';
        }
        html += '</div>';

        html += '<div class="state-section">';
        html += '<h4>Companions</h4>';
        if (this.state.companions.size > 0) {
            html += '<ul class="state-list">';
            for (const companion of this.state.companions) {
                html += `<li>👤 ${companion}</li>`;
            }
            html += '</ul>';
        } else {
            html += '<p class="state-empty">(none)</p>';
        }
        html += '</div>';

        html += '<div class="state-section">';
        html += `<h4>Nodes Visited: ${this.state.visitedNodes.size}</h4>`;
        html += '</div>';

        content.innerHTML = html;
    }

    updateEditStatePanel() {
        const content = this.modal.querySelector('.play-edit-state-content');

        let html = '';

        // Variables section - editable
        html += '<div class="state-section">';
        html += '<h4>Variables</h4>';
        html += '<div class="edit-state-variables">';
        const vars = Object.entries(this.state.variables);
        if (vars.length > 0) {
            for (const [key, value] of vars) {
                const inputType = typeof value === 'boolean' ? 'checkbox' : 'text';
                const inputValue = typeof value === 'boolean' ? '' : value;
                const checked = typeof value === 'boolean' && value ? 'checked' : '';
                html += `<div class="edit-state-row">
                    <label>${key}</label>
                    ${typeof value === 'boolean'
                        ? `<input type="checkbox" data-var="${key}" data-type="bool" ${checked}>`
                        : `<input type="text" data-var="${key}" data-type="${typeof value}" value="${inputValue}">`
                    }
                </div>`;
            }
        } else {
            html += '<p class="state-empty">(none)</p>';
        }
        // Add new variable
        html += `<div class="edit-state-add">
            <div class="edit-state-add-row">
                <input type="text" class="new-var-name" placeholder="variable_name">
                <select class="new-var-type">
                    <option value="bool">Bool</option>
                    <option value="number">Number</option>
                    <option value="string">String</option>
                </select>
            </div>
            <div class="edit-state-add-row">
                <span class="bool-toggle new-var-bool-value">
                    <input type="checkbox" id="new-var-bool-checkbox">
                    <label for="new-var-bool-checkbox">false</label>
                </span>
                <input type="number" class="new-var-number-value hidden" placeholder="0" value="0">
                <input type="text" class="new-var-string-value hidden" placeholder="value">
                <button class="btn btn-sm btn-success add-variable-btn">+ Add</button>
            </div>
        </div>`;
        html += '</div>';
        html += '</div>';

        // Inventory section - checkboxes + known items
        html += '<div class="state-section">';
        html += '<h4>Inventory</h4>';
        html += '<div class="edit-state-inventory">';
        if (this.state.inventory.size > 0) {
            for (const item of this.state.inventory) {
                html += `<div class="edit-state-row">
                    <label>🎒 ${item}</label>
                    <input type="checkbox" data-item="${item}" checked>
                </div>`;
            }
        } else {
            html += '<p class="state-empty">(empty)</p>';
        }
        // Known items quick-add buttons
        const availableItems = this.knownItems.filter(item => !this.state.inventory.has(item));
        if (availableItems.length > 0) {
            html += '<div class="known-items-section">';
            html += '<label class="known-label">Known items:</label>';
            html += '<div class="known-buttons">';
            for (const item of availableItems) {
                html += `<button class="btn btn-xs btn-outline known-item-btn" data-known-item="${item}">+ ${item}</button>`;
            }
            html += '</div></div>';
        }
        // Add new item (custom)
        html += `<div class="edit-state-add">
            <input type="text" class="new-item-name" placeholder="custom_item">
            <button class="btn btn-sm add-item-btn">+</button>
        </div>`;
        html += '</div>';
        html += '</div>';

        // Companions section - checkboxes + known companions
        html += '<div class="state-section">';
        html += '<h4>Companions</h4>';
        html += '<div class="edit-state-companions">';
        if (this.state.companions.size > 0) {
            for (const companion of this.state.companions) {
                html += `<div class="edit-state-row">
                    <label>👤 ${companion}</label>
                    <input type="checkbox" data-companion="${companion}" checked>
                </div>`;
            }
        } else {
            html += '<p class="state-empty">(none)</p>';
        }
        // Known companions quick-add buttons
        const availableCompanions = this.knownCompanions.filter(c => !this.state.companions.has(c));
        if (availableCompanions.length > 0) {
            html += '<div class="known-companions-section">';
            html += '<label class="known-label">Known companions:</label>';
            html += '<div class="known-buttons">';
            for (const companion of availableCompanions) {
                html += `<button class="btn btn-xs btn-outline known-companion-btn" data-known-companion="${companion}">+ ${companion}</button>`;
            }
            html += '</div></div>';
        }
        // Add new companion (custom)
        html += `<div class="edit-state-add">
            <input type="text" class="new-companion-name" placeholder="custom_companion">
            <button class="btn btn-sm add-companion-btn">+</button>
        </div>`;
        html += '</div>';
        html += '</div>';

        content.innerHTML = html;

        // Add event listeners for type selector
        const typeSelect = content.querySelector('.new-var-type');
        const boolValue = content.querySelector('.new-var-bool-value');
        const numberValue = content.querySelector('.new-var-number-value');
        const stringValue = content.querySelector('.new-var-string-value');
        const boolCheckbox = content.querySelector('#new-var-bool-checkbox');
        const boolLabel = content.querySelector('.new-var-bool-value label');

        typeSelect?.addEventListener('change', () => {
            const type = typeSelect.value;
            boolValue.classList.toggle('hidden', type !== 'bool');
            numberValue.classList.toggle('hidden', type !== 'number');
            stringValue.classList.toggle('hidden', type !== 'string');
        });

        // Update bool label when checkbox changes
        boolCheckbox?.addEventListener('change', () => {
            boolLabel.textContent = boolCheckbox.checked ? 'true' : 'false';
        });

        // Add event listeners for add buttons
        content.querySelector('.add-variable-btn')?.addEventListener('click', () => {
            const nameInput = content.querySelector('.new-var-name');
            const type = typeSelect.value;
            const name = nameInput.value.trim();

            if (!name) return;

            let val;
            if (type === 'bool') {
                val = boolCheckbox.checked;
            } else if (type === 'number') {
                val = parseInt(numberValue.value, 10) || 0;
            } else {
                val = stringValue.value;
            }

            this.state.variables[name] = val;
            this.updateEditStatePanel();
        });

        content.querySelector('.add-item-btn')?.addEventListener('click', () => {
            const nameInput = content.querySelector('.new-item-name');
            if (nameInput.value.trim()) {
                this.state.inventory.add(nameInput.value.trim());
                this.updateEditStatePanel();
            }
        });

        content.querySelector('.add-companion-btn')?.addEventListener('click', () => {
            const nameInput = content.querySelector('.new-companion-name');
            if (nameInput.value.trim()) {
                this.state.companions.add(nameInput.value.trim());
                this.updateEditStatePanel();
            }
        });

        // Known items quick-add buttons
        content.querySelectorAll('.known-item-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const item = btn.dataset.knownItem;
                this.state.inventory.add(item);
                this.updateEditStatePanel();
            });
        });

        // Known companions quick-add buttons
        content.querySelectorAll('.known-companion-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const companion = btn.dataset.knownCompanion;
                this.state.companions.add(companion);
                this.updateEditStatePanel();
            });
        });
    }

    applyStateChanges() {
        const content = this.modal.querySelector('.play-edit-state-content');

        // Update variables
        content.querySelectorAll('input[data-var]').forEach(input => {
            const varName = input.dataset.var;
            const varType = input.dataset.type;

            if (varType === 'bool') {
                this.state.variables[varName] = input.checked;
            } else {
                let val = input.value.trim();
                // Try to parse as number
                if (!isNaN(val) && val !== '') {
                    val = parseInt(val, 10);
                } else if (val.toLowerCase() === 'true') {
                    val = true;
                } else if (val.toLowerCase() === 'false') {
                    val = false;
                }
                this.state.variables[varName] = val;
            }
        });

        // Update inventory
        content.querySelectorAll('input[data-item]').forEach(input => {
            const item = input.dataset.item;
            if (input.checked) {
                this.state.inventory.add(item);
            } else {
                this.state.inventory.delete(item);
            }
        });

        // Update companions
        content.querySelectorAll('input[data-companion]').forEach(input => {
            const companion = input.dataset.companion;
            if (input.checked) {
                this.state.companions.add(companion);
            } else {
                this.state.companions.delete(companion);
            }
        });

        // Switch to view tab and update display
        this.switchStateTab('view');
        this.updateStatsDisplay();
        this.app.showNotification('State updated!', 'success');
    }

    exportStateJSON() {
        const stateData = {
            variables: { ...this.state.variables },
            inventory: Array.from(this.state.inventory),
            companions: Array.from(this.state.companions),
            exported_from: this.app.currentFilePath || 'unknown',
            exported_at: new Date().toISOString()
        };

        const blob = new Blob([JSON.stringify(stateData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'game_state.json';
        a.click();
        URL.revokeObjectURL(url);

        this.app.showNotification('State exported to JSON!', 'success');
    }

    exportStateDLG() {
        let dlgCommands = '# Exported game state\n';
        dlgCommands += `# From: ${this.app.currentFilePath || 'unknown'}\n`;
        dlgCommands += `# Exported at: ${new Date().toISOString()}\n\n`;

        // Add variables
        for (const [key, value] of Object.entries(this.state.variables)) {
            dlgCommands += `*set ${key} = ${value}\n`;
        }

        // Add items
        for (const item of this.state.inventory) {
            dlgCommands += `*give_item ${item}\n`;
        }

        // Add companions
        for (const companion of this.state.companions) {
            dlgCommands += `*add_companion ${companion}\n`;
        }

        const blob = new Blob([dlgCommands], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'game_state.dlg';
        a.click();
        URL.revokeObjectURL(url);

        this.app.showNotification('State exported to DLG format!', 'success');
    }

    toggleSpeed(btn) {
        if (this.typewriterSpeed === 10) {
            // Switch to normal
            this.typewriterSpeed = 25;
            btn.innerHTML = '<span>📝</span> Speed: Normal';
        } else {
            // Switch to fast
            this.typewriterSpeed = 10;
            btn.innerHTML = '<span>⚡</span> Speed: Fast';
        }
    }

    updateStatsDisplay() {
        const harmonyVal = this.state.variables.harmony || 0;
        const discordVal = this.state.variables.discord || 0;
        const xpVal = this.state.variables.xp || 0;

        const harmonyEl = this.modal.querySelector('.harmony-stat');
        const discordEl = this.modal.querySelector('.discord-stat');
        const xpEl = this.modal.querySelector('.xp-stat');

        if (harmonyVal !== 0) {
            harmonyEl.classList.remove('hidden');
            harmonyEl.querySelector('.value').textContent = harmonyVal;
        }
        if (discordVal !== 0) {
            discordEl.classList.remove('hidden');
            discordEl.querySelector('.value').textContent = discordVal;
        }
        if (xpVal !== 0) {
            xpEl.classList.remove('hidden');
            xpEl.querySelector('.value').textContent = xpVal;
        }
    }

    async playNode(nodeId) {
        if (!this.isPlaying) return;

        // Handle END
        if (nodeId === 'END') {
            await this.showEnding();
            return;
        }

        const node = this.dialogueData[nodeId];
        if (!node) {
            this.addMessage('system', `Error: Node "${nodeId}" not found.`);
            return;
        }

        this.currentNode = nodeId;
        this.state.visitedNodes.add(nodeId);

        // Track path and update graph highlight
        if (!this.visitedPath.includes(nodeId)) {
            this.visitedPath.push(nodeId);
        }
        this.app.highlightPath(this.visitedPath, nodeId);

        // Update node indicator
        const indicator = this.modal.querySelector('.play-node-indicator');
        indicator.textContent = `📍 ${nodeId}`;

        // Execute commands
        for (const cmd of node.commands) {
            const feedback = this.state.executeCommand(cmd);
            if (feedback) {
                await this.showFeedback(feedback);
            }
        }

        // Update stats display
        this.updateStatsDisplay();

        // Display dialogue lines with typewriter effect (filter by condition)
        for (const line of node.lines) {
            // Only show lines whose conditions are met (or have no condition)
            if (this.state.evaluateCondition(line.condition)) {
                await this.displayDialogueLine(line.speaker, line.text, line.tags || []);
            }
        }

        // Check if this is an exit node for the current entry group
        if (this.isExitNode(nodeId)) {
            await this.showExitPoint();
            return;
        }

        // Show choices
        await this.showChoices(node.choices);
    }

    async displayDialogueLine(speaker, text, tags = []) {
        const scrollArea = this.modal.querySelector('.play-dialogue-scroll');
        const speakerName = this.characters[speaker] || speaker;

        // Create dialogue box
        const box = document.createElement('div');
        box.className = `dialogue-box ${speaker === 'narrator' ? 'narrator' : ''} ${speaker === 'hero' ? 'player' : 'npc'}`;

        if (speaker !== 'narrator') {
            const nameEl = document.createElement('div');
            nameEl.className = 'dialogue-speaker';
            nameEl.textContent = speakerName;
            box.appendChild(nameEl);
        }

        const textEl = document.createElement('div');
        textEl.className = 'dialogue-text';
        box.appendChild(textEl);

        // Show tags in simple format below text
        if (tags && tags.length > 0) {
            const tagsEl = document.createElement('div');
            tagsEl.className = 'dialogue-tags-simple';
            tagsEl.textContent = `[${tags.join(', ')}]`;
            box.appendChild(tagsEl);
        }

        scrollArea.appendChild(box);
        scrollArea.scrollTop = scrollArea.scrollHeight;

        // Typewriter effect
        await this.typewriter(textEl, text);

        // Small pause after each line
        await delay(300);
    }

    async typewriter(element, text) {
        return new Promise((resolve) => {
            let i = 0;
            const interval = setInterval(() => {
                if (!this.isPlaying) {
                    clearInterval(interval);
                    resolve();
                    return;
                }

                if (i < text.length) {
                    element.textContent += text[i];
                    i++;

                    // Scroll to bottom
                    const scrollArea = this.modal.querySelector('.play-dialogue-scroll');
                    scrollArea.scrollTop = scrollArea.scrollHeight;
                } else {
                    clearInterval(interval);
                    resolve();
                }
            }, this.typewriterSpeed);
        });
    }

    async showFeedback(feedback) {
        const scrollArea = this.modal.querySelector('.play-dialogue-scroll');

        const feedbackEl = document.createElement('div');
        feedbackEl.className = 'dialogue-feedback';

        if (feedback.type === 'harmony') {
            const sign = feedback.amount >= 0 ? '+' : '';
            feedbackEl.innerHTML = `<span class="feedback-harmony">☯️ ${sign}${feedback.amount} Harmony</span> <span class="feedback-total">(Total: ${feedback.total})</span>`;
        } else if (feedback.type === 'discord') {
            const sign = feedback.amount >= 0 ? '+' : '';
            feedbackEl.innerHTML = `<span class="feedback-discord">💀 ${sign}${feedback.amount} Discord</span> <span class="feedback-total">(Total: ${feedback.total})</span>`;
        } else if (feedback.type === 'xp') {
            const sign = feedback.amount >= 0 ? '+' : '';
            feedbackEl.innerHTML = `<span class="feedback-xp">⭐ ${sign}${feedback.amount} XP</span> <span class="feedback-total">(Total: ${feedback.total})</span>`;
        } else if (feedback.type === 'item') {
            if (feedback.action === 'add') {
                feedbackEl.innerHTML = `<span class="feedback-item">🎒 Received: ${feedback.item}</span>`;
            } else {
                feedbackEl.innerHTML = `<span class="feedback-item">🎒 Lost: ${feedback.item}</span>`;
            }
        } else if (feedback.type === 'companion') {
            if (feedback.action === 'add') {
                feedbackEl.innerHTML = `<span class="feedback-companion">👤 ${feedback.name} joined your party!</span>`;
            } else {
                feedbackEl.innerHTML = `<span class="feedback-companion">👤 ${feedback.name} left your party.</span>`;
            }
        }

        scrollArea.appendChild(feedbackEl);
        scrollArea.scrollTop = scrollArea.scrollHeight;

        await delay(500);
    }

    async showChoices(choices) {
        if (!this.isPlaying) return;

        // Separate GOTOs (no text) from player choices (with text)
        // GOTOs are automatic transitions, choices are presented to the player
        const gotos = [];
        const playerChoices = [];
        const disabledChoices = [];

        for (const choice of choices) {
            if (choice.text) {
                // This is a player choice
                if (this.state.evaluateCondition(choice.condition)) {
                    playerChoices.push(choice);
                } else {
                    disabledChoices.push(choice);
                }
            } else {
                // This is a GOTO (automatic transition)
                gotos.push(choice);
            }
        }

        // First, check GOTOs - find first one with true condition (or no condition)
        for (const goto of gotos) {
            if (this.state.evaluateCondition(goto.condition)) {
                // Auto-transition to this target
                await delay(300);
                await this.playNode(goto.target);
                return;
            }
        }

        // No GOTOs matched, check if we have player choices
        if (playerChoices.length === 0) {
            // Dead end
            await this.showEnding();
            return;
        }

        const choicesArea = this.modal.querySelector('.play-choices-area');
        const scrollArea = this.modal.querySelector('.play-dialogue-scroll');
        choicesArea.innerHTML = '';
        choicesArea.classList.remove('hidden');

        // Auto-scroll dialogue to bottom so latest message is visible above choices
        setTimeout(() => {
            scrollArea.scrollTop = scrollArea.scrollHeight;
        }, 50);

        // Render player choices
        for (let i = 0; i < playerChoices.length; i++) {
            const choice = playerChoices[i];
            const btn = document.createElement('button');
            btn.className = 'play-choice-btn';

            btn.innerHTML = `<span class="choice-number">${i + 1}</span> ${escapeHtml(choice.text)}`;

            if (choice.condition) {
                btn.classList.add('conditional');
                btn.title = `Condition: ${choice.condition}`;
            }

            btn.addEventListener('click', async () => {
                // Show player's choice in dialogue
                await this.displayDialogueLine('hero', choice.text);

                choicesArea.classList.add('hidden');
                await this.playNode(choice.target);
            });

            choicesArea.appendChild(btn);
        }

        // Render disabled choices (grayed out, not clickable) - only player choices, not GOTOs
        for (const choice of disabledChoices) {
            const btn = document.createElement('button');
            btn.className = 'play-choice-btn disabled';
            btn.disabled = true;

            const conditionHtml = choice.condition
                ? `<span class="choice-condition-badge">{${escapeHtml(choice.condition)}}</span>`
                : '';

            btn.innerHTML = `<span class="choice-number disabled">✗</span> ${escapeHtml(choice.text)} ${conditionHtml}`;
            btn.title = `Condition not met: ${choice.condition || 'unknown'}`;

            choicesArea.appendChild(btn);
        }

        // Add keyboard shortcuts for choices
        const choiceHandler = async (e) => {
            // Ignore keyboard input when state panel is open (user may be editing values)
            const statePanel = this.modal.querySelector('.unified-state-panel');
            if (statePanel && !statePanel.classList.contains('hidden')) {
                return;
            }

            const num = parseInt(e.key, 10);
            if (num >= 1 && num <= playerChoices.length) {
                document.removeEventListener('keydown', choiceHandler);
                const choice = playerChoices[num - 1];

                await this.displayDialogueLine('hero', choice.text);

                choicesArea.classList.add('hidden');
                await this.playNode(choice.target);
            }
        };
        document.addEventListener('keydown', choiceHandler);
    }

    async showEnding() {
        const scrollArea = this.modal.querySelector('.play-dialogue-scroll');
        const choicesArea = this.modal.querySelector('.play-choices-area');

        choicesArea.classList.add('hidden');

        const endingEl = document.createElement('div');
        endingEl.className = 'dialogue-ending';
        endingEl.innerHTML = `
            <div class="ending-title">🎬 THE END</div>
            <div class="ending-stats">
                <div class="ending-stat">📍 Nodes visited: ${this.state.visitedNodes.size}</div>
                ${this.state.variables.harmony ? `<div class="ending-stat">☯️ Harmony: ${this.state.variables.harmony}</div>` : ''}
                ${this.state.variables.discord ? `<div class="ending-stat">💀 Discord: ${this.state.variables.discord}</div>` : ''}
                ${this.state.variables.xp ? `<div class="ending-stat">⭐ XP: ${this.state.variables.xp}</div>` : ''}
            </div>
            <div class="ending-buttons">
                <button class="btn btn-success continue-scene-btn">📂 Load New File (Keep State)</button>
                <button class="btn btn-primary play-again-btn">🔁 Play Again</button>
            </div>
        `;

        scrollArea.appendChild(endingEl);
        scrollArea.scrollTop = scrollArea.scrollHeight;

        endingEl.querySelector('.play-again-btn').addEventListener('click', () => {
            this.close();
            this.app.dialoguePlayer.play();
        });

        endingEl.querySelector('.continue-scene-btn').addEventListener('click', () => {
            this.showContinueModal();
        });
    }

    async showContinueModal() {
        // Capture current state before showing picker
        const preservedState = {
            variables: { ...this.state.variables },
            inventory: [...this.state.inventory],
            companions: [...this.state.companions]
        };

        // Create modal overlay
        const modalOverlay = document.createElement('div');
        modalOverlay.className = 'continue-modal-overlay';
        modalOverlay.innerHTML = `
            <div class="continue-modal">
                <div class="continue-modal-header">
                    <h3>📂 Load New File (Keep State)</h3>
                    <button class="btn-close continue-close">×</button>
                </div>
                <div class="continue-modal-body">
                    <p class="continue-info">Select a dialogue file. Your current state will carry over:</p>
                    <div class="continue-state-preview">
                        <div class="state-preview-item">
                            <strong>Variables:</strong>
                            <span>${Object.entries(preservedState.variables).map(([k,v]) => `${k}=${v}`).join(', ') || '(none)'}</span>
                        </div>
                        <div class="state-preview-item">
                            <strong>Inventory:</strong>
                            <span>${preservedState.inventory.join(', ') || '(empty)'}</span>
                        </div>
                        <div class="state-preview-item">
                            <strong>Companions:</strong>
                            <span>${preservedState.companions.join(', ') || '(none)'}</span>
                        </div>
                    </div>
                    <div class="continue-file-list">
                        <p class="loading">Loading files...</p>
                    </div>
                </div>
            </div>
        `;

        this.modal.appendChild(modalOverlay);

        // Close button handler
        modalOverlay.querySelector('.continue-close').addEventListener('click', () => {
            modalOverlay.remove();
        });

        // Backdrop click to close
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) {
                modalOverlay.remove();
            }
        });

        // Fetch available files
        try {
            const response = await fetch('/api/dialogues');
            const data = await response.json();

            const fileListEl = modalOverlay.querySelector('.continue-file-list');
            fileListEl.innerHTML = '';

            if (!data.files || data.files.length === 0) {
                fileListEl.innerHTML = '<p class="no-files">No dialogue files found</p>';
                return;
            }

            // Group files by category
            const grouped = {};
            data.files.forEach(file => {
                if (!grouped[file.category]) {
                    grouped[file.category] = [];
                }
                grouped[file.category].push(file);
            });

            // Create file list
            Object.keys(grouped).sort().forEach(category => {
                const categoryEl = document.createElement('div');
                categoryEl.className = 'continue-category';
                categoryEl.innerHTML = `<div class="continue-category-name">📁 ${category}</div>`;

                grouped[category].forEach(file => {
                    const fileEl = document.createElement('button');
                    fileEl.className = 'continue-file-btn';
                    fileEl.innerHTML = `<span class="file-icon">📄</span> ${file.name}`;
                    fileEl.dataset.path = file.relative_path;

                    // Highlight current file
                    if (file.relative_path === this.app.currentFilePath) {
                        fileEl.classList.add('current-file');
                        fileEl.innerHTML += ' <span class="current-badge">(current)</span>';
                    }

                    fileEl.addEventListener('click', async () => {
                        await this.continueToFile(file.relative_path, preservedState);
                        modalOverlay.remove();
                    });

                    categoryEl.appendChild(fileEl);
                });

                fileListEl.appendChild(categoryEl);
            });

        } catch (error) {
            console.error('Failed to load file list:', error);
            const fileListEl = modalOverlay.querySelector('.continue-file-list');
            fileListEl.innerHTML = `<p class="error">Failed to load files: ${error.message}</p>`;
        }
    }

    async continueToFile(relativePath, preservedState) {
        // Close current playback modal
        this.close();

        try {
            // Load the new file into the editor
            const response = await fetch(`/api/file/${relativePath}`);
            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            // Update app state (same as loadFile)
            this.app.editor.setValue(data.content);
            this.app.currentFile = data;
            this.app.currentFilePath = relativePath;
            this.app.originalContent = data.content;
            this.app.originalLines = data.content.split('\n');
            this.app.hasUnsavedChanges = false;

            // Clear modified gutter markers
            this.app.editor.clearGutter('CodeMirror-gutter-modified');

            // Update UI to reflect no unsaved changes
            this.app.updateUnsavedUI();

            // Update file selector
            const selector = document.getElementById('file-selector');
            if (selector) {
                selector.value = relativePath;
            }

            // Clear any pending preview timeout (setValue triggers change handler)
            clearTimeout(this.app.previewTimeout);

            // Validate and update graph
            await this.app.validateDialogue();

            this.app.showNotification(`Loaded: ${data.name}`, 'success');

            // Start playback with preserved state
            await this.play(null, preservedState, false);

        } catch (error) {
            console.error('Failed to continue to file:', error);
            this.app.showNotification(`Failed to load file: ${error.message}`, 'error');
        }
    }

    addMessage(type, message) {
        const scrollArea = this.modal.querySelector('.play-dialogue-scroll');
        const msgEl = document.createElement('div');
        msgEl.className = `dialogue-message ${type}`;
        msgEl.textContent = message;
        scrollArea.appendChild(msgEl);
        scrollArea.scrollTop = scrollArea.scrollHeight;
    }
}
