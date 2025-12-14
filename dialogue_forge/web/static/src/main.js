/**
 * Dialogue Forge - Main Entry Point
 * Visual dialogue editor for .dlg format files
 */

import { DialogueForgeApp } from './app/DialogueForgeApp.js';
import { injectAnimationStyles } from './utils/helpers.js';

// Inject CSS animations
injectAnimationStyles();

// Initialize the app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new DialogueForgeApp();
});
