# Editor Support for DLG Files

Syntax highlighting and editor support for `.dlg` dialogue files.

## VSCode

### Quick Install (VSIX)

1. Build the extension (requires Node.js):
   ```bash
   cd editors/vscode/dlg-language
   npx @vscode/vsce package
   ```

2. Install the generated `.vsix` file:
   ```bash
   code --install-extension dlg-language-1.0.0.vsix
   ```

Or install via VSCode: `Extensions` > `...` menu > `Install from VSIX...`

### Features
- Syntax highlighting for nodes, speakers, choices, conditions, commands
- Comment support (`#`)
- Bracket matching and auto-closing
- Folding by node sections

## Neovim

### Installation

Copy or symlink the files to your Neovim config:

```bash
# Create directories if needed
mkdir -p ~/.config/nvim/after/syntax
mkdir -p ~/.config/nvim/after/ftdetect

# Symlink (recommended - stays in sync)
ln -s /path/to/dialogue-forge/editors/neovim/syntax/dlg.vim ~/.config/nvim/after/syntax/dlg.vim
ln -s /path/to/dialogue-forge/editors/neovim/ftdetect/dlg.vim ~/.config/nvim/after/ftdetect/dlg.vim

# Or copy
cp editors/neovim/syntax/dlg.vim ~/.config/nvim/after/syntax/
cp editors/neovim/ftdetect/dlg.vim ~/.config/nvim/after/ftdetect/
```

### Features
- Full syntax highlighting matching the DLG language spec
- Multi-line string support
- Special highlighting for `[start]`, `[characters]`, `[state]` sections
- Condition highlighting with operators and keywords
