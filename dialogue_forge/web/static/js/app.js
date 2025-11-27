// Dialogue Forge - Main Application

/**
 * GameState - Tracks game state during dialogue playback
 * Handles condition evaluation and command execution
 */
class GameState {
    constructor(initialState = null) {
        if (initialState) {
            this.variables = { ...initialState.variables };
            this.inventory = new Set(initialState.inventory || []);
            this.companions = new Set(initialState.companions || []);
        } else {
            this.variables = {};
            this.inventory = new Set();
            this.companions = new Set();
        }
        this.visitedNodes = new Set();
    }

    copy() {
        const newState = new GameState();
        newState.variables = { ...this.variables };
        newState.inventory = new Set(this.inventory);
        newState.companions = new Set(this.companions);
        newState.visitedNodes = new Set(this.visitedNodes);
        return newState;
    }

    evaluateCondition(condition) {
        if (!condition) return true;

        // Replace DLG syntax with JavaScript syntax
        let jsCondition = condition
            .replace(/!/g, ' not_op ')
            .replace(/&&/g, ' && ')
            .replace(/\|\|/g, ' || ');

        // Handle has_item:xxx
        jsCondition = jsCondition.replace(/has_item:(\w+)/g, (_, item) => {
            return this.inventory.has(item) ? 'true' : 'false';
        });

        // Handle companion:xxx
        jsCondition = jsCondition.replace(/companion:(\w+)/g, (_, companion) => {
            return this.companions.has(companion) ? 'true' : 'false';
        });

        // Handle not_op for negation
        jsCondition = jsCondition.replace(/not_op\s+(\w+)/g, (_, varName) => {
            if (varName === 'true' || varName === 'false') {
                return varName === 'true' ? 'false' : 'true';
            }
            const value = this.variables[varName];
            if (value === undefined) return 'true'; // undefined is falsy, so !undefined = true
            return value ? 'false' : 'true';
        });

        // Replace remaining variable names with their values
        jsCondition = jsCondition.replace(/\b([a-zA-Z_]\w*)\b/g, (match) => {
            if (match === 'true' || match === 'false' || match === 'not_op') {
                return match;
            }
            const value = this.variables[match];
            if (value === undefined) return 'false';
            if (typeof value === 'boolean') return value.toString();
            if (typeof value === 'number') return value.toString();
            return `"${value}"`;
        });

        try {
            // Safely evaluate the condition
            return Function('"use strict"; return (' + jsCondition + ')')();
        } catch (e) {
            console.warn('Condition evaluation error:', condition, '->', jsCondition, e);
            return false;
        }
    }

    executeCommand(command) {
        const parts = command.split(/\s+/);
        if (parts.length === 0) return null;

        const cmd = parts[0];
        let feedback = null;

        if (cmd === 'set' && parts.length >= 4) {
            const varName = parts[1];
            const value = parts.slice(3).join(' ');
            if (value.toLowerCase() === 'true') {
                this.variables[varName] = true;
            } else if (value.toLowerCase() === 'false') {
                this.variables[varName] = false;
            } else {
                const numVal = parseInt(value, 10);
                this.variables[varName] = isNaN(numVal) ? value : numVal;
            }
        } else if (cmd === 'add' && parts.length >= 4) {
            const varName = parts[1];
            const amount = parseInt(parts[3], 10);
            if (!isNaN(amount)) {
                const current = this.variables[varName] || 0;
                this.variables[varName] = current + amount;

                // Generate feedback for special variables
                if (varName === 'harmony') {
                    feedback = { type: 'harmony', amount, total: this.variables[varName] };
                } else if (varName === 'discord') {
                    feedback = { type: 'discord', amount, total: this.variables[varName] };
                } else if (varName === 'xp') {
                    feedback = { type: 'xp', amount, total: this.variables[varName] };
                }
            }
        } else if (cmd === 'sub' && parts.length >= 4) {
            const varName = parts[1];
            const amount = parseInt(parts[3], 10);
            if (!isNaN(amount)) {
                const current = this.variables[varName] || 0;
                this.variables[varName] = current - amount;

                if (varName === 'harmony') {
                    feedback = { type: 'harmony', amount: -amount, total: this.variables[varName] };
                } else if (varName === 'discord') {
                    feedback = { type: 'discord', amount: -amount, total: this.variables[varName] };
                } else if (varName === 'xp') {
                    feedback = { type: 'xp', amount: -amount, total: this.variables[varName] };
                }
            }
        } else if (cmd === 'give_item' && parts.length >= 2) {
            this.inventory.add(parts[1]);
            feedback = { type: 'item', action: 'add', item: parts[1] };
        } else if (cmd === 'remove_item' && parts.length >= 2) {
            this.inventory.delete(parts[1]);
            feedback = { type: 'item', action: 'remove', item: parts[1] };
        } else if (cmd === 'add_companion' && parts.length >= 2) {
            this.companions.add(parts[1]);
            feedback = { type: 'companion', action: 'add', name: parts[1] };
        } else if (cmd === 'remove_companion' && parts.length >= 2) {
            this.companions.delete(parts[1]);
            feedback = { type: 'companion', action: 'remove', name: parts[1] };
        }

        return feedback;
    }
}


/**
 * DialoguePlayer - Handles interactive dialogue playback in the web UI
 */
class DialoguePlayer {
    constructor(app) {
        this.app = app;
        this.dialogueData = null;
        this.characters = {};
        this.initialStateCommands = []; // Commands from [state] section
        this.state = null;
        this.currentNode = null;
        this.isPlaying = false;
        this.typewriterSpeed = 25; // ms per character (normal speed)
        this.modal = null;
    }

    async play(startNode = null, initialState = null) {
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
            const startNodeId = startNode || data.start_node;

            // Convert graph nodes to dialogue format
            for (const node of data.graph.nodes) {
                const nodeData = node.data;
                this.dialogueData[nodeData.id] = {
                    id: nodeData.id,
                    lines: nodeData.lines || [],
                    commands: nodeData.commands || [],
                    choices: []
                };
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
                // When playing from a specific node with computed state
                this.state = new GameState(initialState);
            } else {
                // Fresh playthrough - execute [state] commands first
                this.state = new GameState();
                for (const cmd of this.initialStateCommands) {
                    this.state.executeCommand(cmd);
                }
            }

            this.currentNode = startNodeId;
            this.isPlaying = true;

            // Show the play modal
            this.showModal();

            // Start playing
            await this.playNode(this.currentNode);

        } catch (error) {
            console.error('Play error:', error);
            this.app.showNotification('Failed to start playback: ' + error.message, 'error');
        }
    }

    async playFromNode(nodeId) {
        // Compute path and state to reach this node
        const content = this.app.editor.getValue();

        try {
            const response = await fetch('/api/compute-path', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content, target_node: nodeId })
            });
            const data = await response.json();

            if (data.error) {
                this.app.showNotification('Error computing path: ' + data.error, 'error');
                return;
            }

            if (data.warning) {
                this.app.showNotification(data.warning, 'warning');
            }

            // Play from the target node with computed state
            await this.play(nodeId, data.state);

        } catch (error) {
            console.error('Play from node error:', error);
            this.app.showNotification('Failed to compute path: ' + error.message, 'error');
        }
    }

    showModal() {
        // Create the play modal
        this.modal = document.createElement('div');
        this.modal.className = 'play-modal';
        this.modal.innerHTML = `
            <div class="play-modal-backdrop"></div>
            <div class="play-modal-container">
                <div class="play-modal-header">
                    <h2>Dialogue Playback</h2>
                    <div class="play-modal-controls">
                        <button class="btn btn-sm play-state-btn" title="View/Edit game state">
                            <span>📊</span> State
                        </button>
                        <button class="btn btn-sm play-speed-btn" title="Toggle text speed">
                            <span>📝</span> Speed: Normal
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

    close() {
        this.isPlaying = false;
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
            <input type="text" class="new-var-name" placeholder="new_variable">
            <input type="text" class="new-var-value" placeholder="value">
            <button class="btn btn-sm add-variable-btn">+</button>
        </div>`;
        html += '</div>';
        html += '</div>';

        // Inventory section - checkboxes
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
        // Add new item
        html += `<div class="edit-state-add">
            <input type="text" class="new-item-name" placeholder="new_item">
            <button class="btn btn-sm add-item-btn">+</button>
        </div>`;
        html += '</div>';
        html += '</div>';

        // Companions section - checkboxes
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
        // Add new companion
        html += `<div class="edit-state-add">
            <input type="text" class="new-companion-name" placeholder="new_companion">
            <button class="btn btn-sm add-companion-btn">+</button>
        </div>`;
        html += '</div>';
        html += '</div>';

        content.innerHTML = html;

        // Add event listeners for add buttons
        content.querySelector('.add-variable-btn')?.addEventListener('click', () => {
            const nameInput = content.querySelector('.new-var-name');
            const valueInput = content.querySelector('.new-var-value');
            if (nameInput.value.trim()) {
                let val = valueInput.value.trim();
                // Try to parse as number or boolean
                if (val.toLowerCase() === 'true') val = true;
                else if (val.toLowerCase() === 'false') val = false;
                else if (!isNaN(val) && val !== '') val = parseInt(val, 10);
                this.state.variables[nameInput.value.trim()] = val;
                this.updateEditStatePanel();
            }
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
        if (this.typewriterSpeed === 25) {
            // Switch to fast
            this.typewriterSpeed = 5;
            btn.innerHTML = '<span>⚡</span> Speed: Fast';
        } else {
            // Switch to normal
            this.typewriterSpeed = 25;
            btn.innerHTML = '<span>📝</span> Speed: Normal';
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

        // Display dialogue lines with typewriter effect
        for (const line of node.lines) {
            await this.displayDialogueLine(line.speaker, line.text);
        }

        // Show choices
        await this.showChoices(node.choices);
    }

    async displayDialogueLine(speaker, text) {
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

        scrollArea.appendChild(box);
        scrollArea.scrollTop = scrollArea.scrollHeight;

        // Typewriter effect
        await this.typewriter(textEl, text);

        // Small pause after each line
        await this.delay(300);
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

        await this.delay(500);
    }

    async showChoices(choices) {
        if (!this.isPlaying) return;

        // Filter choices by conditions
        const availableChoices = choices.filter(choice =>
            this.state.evaluateCondition(choice.condition)
        );

        if (availableChoices.length === 0) {
            // Dead end
            await this.showEnding();
            return;
        }

        // Check for auto-continue (single choice with no text)
        if (availableChoices.length === 1 && !availableChoices[0].text) {
            await this.delay(500);
            await this.playNode(availableChoices[0].target);
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

        for (let i = 0; i < availableChoices.length; i++) {
            const choice = availableChoices[i];
            const btn = document.createElement('button');
            btn.className = 'play-choice-btn';

            if (choice.text) {
                btn.innerHTML = `<span class="choice-number">${i + 1}</span> ${this.escapeHtml(choice.text)}`;
            } else {
                btn.innerHTML = `<span class="choice-number">${i + 1}</span> <span class="choice-continue">Continue...</span>`;
            }

            if (choice.condition) {
                btn.classList.add('conditional');
                btn.title = `Condition: ${choice.condition}`;
            }

            btn.addEventListener('click', async () => {
                // Show player's choice in dialogue
                if (choice.text) {
                    await this.displayDialogueLine('hero', choice.text);
                }

                choicesArea.classList.add('hidden');
                await this.playNode(choice.target);
            });

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
            if (num >= 1 && num <= availableChoices.length) {
                document.removeEventListener('keydown', choiceHandler);
                const choice = availableChoices[num - 1];

                if (choice.text) {
                    await this.displayDialogueLine('hero', choice.text);
                }

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
            <button class="btn btn-primary play-again-btn">Play Again</button>
        `;

        scrollArea.appendChild(endingEl);
        scrollArea.scrollTop = scrollArea.scrollHeight;

        endingEl.querySelector('.play-again-btn').addEventListener('click', () => {
            this.close();
            this.app.dialoguePlayer.play();
        });
    }

    addMessage(type, message) {
        const scrollArea = this.modal.querySelector('.play-dialogue-scroll');
        const msgEl = document.createElement('div');
        msgEl.className = `dialogue-message ${type}`;
        msgEl.textContent = message;
        scrollArea.appendChild(msgEl);
        scrollArea.scrollTop = scrollArea.scrollHeight;
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}


class DialogueForgeApp {
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
            <div class="context-menu-item" data-action="play-from">
                <span>▶️</span> Play from here
            </div>
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
            } else if (action === 'play-from' && nodeId) {
                this.dialoguePlayer.playFromNode(nodeId);
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
            lineWrapping: false,
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
                'Cmd-Enter': () => this.validateDialogue()
            }
        });

        // Add syntax highlighting for .dlg format
        this.setupDLGSyntaxHighlighting();

        // Track changes for modified lines and unsaved state
        this.editor.on('change', (cm, change) => {
            // Update gutter markers by comparing with original
            this.updateModifiedGutters();

            // Check if content differs from original
            this.checkUnsavedChanges();

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

        if (this.hasUnsavedChanges) {
            saveBtn.classList.add('has-changes');
            unsavedIndicator.classList.remove('hidden');
        } else {
            saveBtn.classList.remove('has-changes');
            unsavedIndicator.classList.add('hidden');
        }

        // Enable/disable buttons based on file loaded
        const hasFile = this.currentFilePath !== null;
        saveBtn.disabled = !hasFile;
        reloadBtn.disabled = !hasFile;
    }

    setupDLGSyntaxHighlighting() {
        // Custom overlay mode for .dlg syntax
        CodeMirror.defineMode('dlg', function() {
            return {
                token: function(stream) {
                    // Comments
                    if (stream.match(/^#.*/)) {
                        return 'comment';
                    }

                    // Node definitions [node_name]
                    if (stream.match(/^\[.*?\]/)) {
                        return 'keyword';
                    }

                    // Commands *set, *add, etc.
                    if (stream.match(/^\*\w+/)) {
                        return 'builtin';
                    }

                    // Choices ->
                    if (stream.match(/^->/)) {
                        return 'operator';
                    }

                    // Conditions {...}
                    if (stream.match(/^\{[^}]*\}/)) {
                        return 'string-2';
                    }

                    // String literals
                    if (stream.match(/^"([^"\\]|\\.)*"/)) {
                        return 'string';
                    }

                    // Action brackets
                    if (stream.match(/^\[[^\]]*\]/)) {
                        return 'variable-2';
                    }

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

            // Auto-validate on load
            await this.validateDialogue();

            console.log(`📂 Loaded: ${data.name}`);
            this.showNotification(`Loaded: ${data.name}`, 'success');
        } catch (error) {
            console.error('Failed to load file:', error);
            this.showNotification(`Failed to load file: ${error.message}`, 'error');
        }
    }

    showNewFileModal() {
        // Check for unsaved changes
        if (this.hasUnsavedChanges) {
            const confirmed = confirm('You have unsaved changes. Discard them and create a new file?');
            if (!confirmed) return;
        }

        // Create modal
        const modal = document.createElement('div');
        modal.className = 'new-file-modal';
        modal.innerHTML = `
            <div class="new-file-backdrop"></div>
            <div class="new-file-container">
                <div class="new-file-header">
                    <h2>📝 Create New Dialogue</h2>
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
                    <button class="btn btn-primary new-file-create">Create</button>
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
            await this.createNewFile(filename);
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

    async createNewFile(filename) {
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

            // Refresh file list and load the new file
            await this.loadFileList();
            await this.loadFile(data.path);

            this.showNotification(`Created: ${data.path}`, 'success');
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
        if (!this.currentFilePath) {
            this.showNotification('No file loaded to save', 'warning');
            return;
        }

        const content = this.editor.getValue();

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
                        <div>${this.escapeHtml(warning)}</div>
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
                        <div>${this.escapeHtml(error)}</div>
                    </div>`;
                });
            }

            if (data.warnings && data.warnings.length > 0) {
                data.warnings.forEach(warning => {
                    html += `<div class="validation-warning">
                        <div class="validation-warning-title">⚠️ Warning</div>
                        <div>${this.escapeHtml(warning)}</div>
                    </div>`;
                });
            }

            content.innerHTML = html || '<p class="validation-empty">Unknown error occurred</p>';
        }
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
                html += `<div class="inspector-speaker">${this.escapeHtml(line.speaker)}</div>`;
                html += `<div class="inspector-text">"${this.escapeHtml(line.text)}"</div>`;
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
                html += `<div class="inspector-command">*${this.escapeHtml(cmd)}</div>`;
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
        html += `<div><strong>From:</strong> ${this.escapeHtml(edgeData.source)}</div>`;
        html += `<div><strong>To:</strong> ${this.escapeHtml(edgeData.target)}</div>`;
        html += '</div>';

        if (edgeData.full_text) {
            html += '<div class="inspector-item">';
            html += `<div class="inspector-text">"${this.escapeHtml(edgeData.full_text)}"</div>`;
            html += '</div>';
        }

        if (edgeData.condition) {
            html += '<div class="inspector-item" style="border-left: 3px solid #f59e0b;">';
            html += `<div style="color: #f59e0b; font-weight: 600; margin-bottom: 4px;">Condition</div>`;
            html += `<div class="inspector-command">{${this.escapeHtml(edgeData.condition)}}</div>`;
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
            const leftPercent = (leftWidth / totalWidth) * 100;

            if (leftPercent > 20 && leftPercent < 80) {
                leftPanel.style.flex = `0 0 ${leftPercent}%`;
                rightPanel.style.flex = `0 0 ${100 - leftPercent}%`;

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

    showNotification(message, type = 'info') {
        // Create toast notification
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            z-index: 9999;
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

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Add animation keyframes
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);

// Initialize the app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new DialogueForgeApp();
});
