/**
 * GameState - Tracks game state during dialogue playback
 * Handles condition evaluation and command execution
 */
export class GameState {
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

    executeCommand(command, skipIfExists = false) {
        const parts = command.split(/\s+/);
        if (parts.length === 0) return null;

        const cmd = parts[0];
        let feedback = null;

        if (cmd === 'set' && parts.length >= 4) {
            const varName = parts[1];

            // Skip if variable already exists and skipIfExists is true
            // Used when continuing to a new scene with preserved state
            if (skipIfExists && varName in this.variables) {
                return null;
            }

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
