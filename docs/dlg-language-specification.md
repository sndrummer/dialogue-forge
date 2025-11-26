# DLG Language Specification v1.0
## A Vim-Optimized Dialogue Format

---

## Quick Reference

```
# Comment
[node_name]                          # Define a node
speaker: "Dialogue text"             # Speaker line
-> target: "Choice text"             # Choice
-> target: "Choice" {condition}     # Conditional choice
*set flag = true                     # Set variable
*add karma = 10                      # Modify number
-> END                               # End conversation
```

---

## 1. File Structure

### 1.1 File Extension
- Files use `.dlg` extension
- UTF-8 encoding
- Unix line endings (LF)

### 1.2 Basic Structure
```
# Optional file header comment
[characters]
character_id: Display Name

[node_name]
dialogue and choices...

[another_node]  
more dialogue...
```

---

## 2. Comments

```
# This is a comment
# Comments can appear anywhere
# They are ignored by the parser
```

---

## 3. Character Definitions

```
[characters]
hero: Fire Nation Soldier
peng: Peng Ruogang  
narrator: Narrator
fu_yang: Fu Yang
```

- **Required** at the start of each file
- Format: `identifier: Display Name`
- Identifiers are used in dialogue
- Display names shown to player

---

## 4. Dialogue Nodes

### 4.1 Node Definition
```
[node_name]
```
- Node names must be unique within a file
- Use lowercase with underscores
- Good: `[cliff_rescue]`, `[talk_to_peng]`
- Bad: `[CLIFF-RESCUE]`, `[node 1]`

### 4.2 Speaker Lines
```
[greeting]
peng: "Hello there!"
hero: "Hi Peng."
peng: "How are you today?"
```
- Format: `speaker: "text"`
- Multiple lines create sequential dialogue
- Speaker must be defined in `[characters]`

### 4.3 Narrator Lines
```
[scene_description]
narrator: "The sun sets over the mountains."
narrator: "A cold wind blows through the valley."
```

---

## 5. Choices

### 5.1 Basic Choices
```
[decision_point]
narrator: "You see a wounded soldier."
-> help_soldier: "Help them"
-> ignore: "Walk away"
-> mock: "Mock their weakness"
```

### 5.2 Conditional Choices
```
[shop]
merchant: "What would you like?"
-> buy_sword: "Buy sword (50 gold)" {gold >= 50}
-> buy_potion: "Buy potion (20 gold)" {gold >= 20}
-> leave: "Leave"
```

### 5.3 Complex Conditions
```
-> secret_path: "Take the hidden path" {perception > 10 && knows_secret}
-> threaten: "Threaten him" {strength > 15 || has_weapon}
-> negotiate: "Negotiate" {charisma > 8 && !is_hostile}
```

---

## 6. Conditions

### 6.1 Operators
- `==` Equal to
- `!=` Not equal to  
- `>` Greater than
- `<` Less than
- `>=` Greater than or equal
- `<=` Less than or equal
- `&&` AND
- `||` OR
- `!` NOT

### 6.2 Variable Types
```
{flag_name}                  # Boolean check (true if exists)
{flag_name == true}          # Explicit boolean
{number_var > 10}           # Numeric comparison
{has_item:sword}            # Special item check
{companion:peng}            # Companion check
```

---

## 7. Effects/Commands

All commands start with `*` and modify game state:

### 7.1 Variable Commands
```
*set flag_name = true        # Set boolean
*set flag_name = false       # Unset boolean
*add numeric_var = 10        # Add to number
*sub numeric_var = 5         # Subtract from number
*set numeric_var = 100       # Set number directly
```

### 7.2 Game Commands
```
*give_item sword             # Add item to inventory
*remove_item sword           # Remove item
*add_companion peng          # Add to party
*remove_companion peng       # Remove from party
*start_combat boss_fight     # Trigger combat
*start_conversation other_dlg # Jump to another dialogue
*unlock_achievement hero     # Unlock achievement
```

### 7.3 Command Placement
```
[node_name]
*set visited_shop = true     # Effects before dialogue
merchant: "Welcome!"
-> buy: "Show me your wares"
-> leave: "Goodbye"

[buy]
hero: "I'll take the sword."
*remove_item gold 50         # Effects after dialogue
*give_item sword
merchant: "Excellent choice!"
-> END
```

---

## 8. Special Nodes

### 8.1 END Node
```
[farewell]
npc: "Goodbye, traveler."
-> END                       # Ends conversation
```

### 8.2 Start Node
```
[start]                      # Optional explicit start
narrator: "Your adventure begins..."
```
If no `[start]` node exists, the first node in the file is used.

---

## 9. Complete Examples

### Example 1: Simple Conversation
```
# === village_elder.dlg ===

[characters]
hero: Player
elder: Village Elder

[start]
elder: "Welcome to our village, traveler."
elder: "We don't get many visitors these days."
-> ask_why: "Why is that?"
-> ask_help: "Do you need help?"
-> leave: "I should go"

[ask_why]
elder: "The roads have become dangerous."
elder: "Bandits prey on travelers."
-> ask_help: "Can I help?"
-> leave: "I'll be careful"

[ask_help]
*set quest_bandits = true
elder: "Would you really help us?"
elder: "The bandits hide in the eastern woods."
-> accept: "I'll deal with them"
-> decline: "On second thought..."

[accept]
*set quest_accepted = true
*add karma = 10
elder: "Thank you! You're a true hero!"
-> END

[decline]
elder: "I understand. It's dangerous."
-> END

[leave]
elder: "Safe travels."
-> END
```

### Example 2: Complex Scene with Combat
```
# === peng_cliff_rescue.dlg ===

[characters]
hero: Fire Nation Soldier
peng: Peng Ruogang
narrator: Narrator

[start]
narrator: "You find an airbender boy hanging from a cliff."
narrator: "The edge is crumbling."
-> approach: "Try to help"
-> leave: "Leave him"
-> push: "Push him off" {discord > 20}

[approach]
narrator: "As you get closer, you notice an artifact in his belt."
-> save_boy: "Pull him up"
-> take_artifact: "Grab the artifact"

[save_boy]
*set peng_saved = true
*add harmony = 20
narrator: "You pull him to safety."
peng: "You... saved me? But you're Fire Nation!"
-> explain: "Not all of us are monsters"
-> hostile: "You're my prisoner now"

[explain]
*add peng_relationship = 10
peng: "Maybe there's hope for peace after all."
peng: "I'm Peng. Want to travel together?"
-> accept_companion: "Sure"
-> refuse_companion: "I work alone"

[accept_companion]
*add_companion peng
*set peng_in_party = true
peng: "Great! Let's go!"
-> END

[refuse_companion]
peng: "Oh... okay. Well, goodbye then."
-> END

[hostile]
peng: "I'd rather die!"
*start_combat peng_fight
-> END

[take_artifact]
*give_item avatar_artifact
*set peng_saved = false
*add discord = 20
narrator: "You grab the artifact as the boy falls."
narrator: "His scream echoes as he disappears."
-> END

[push]
*set peng_dead = true
*add discord = 50
narrator: "You kick the boy off the cliff."
narrator: "The artifact falls at your feet."
*give_item avatar_artifact
-> END

[leave]
narrator: "You walk away as the cliff crumbles."
narrator: "The boy's fate is sealed."
*set peng_dead = true
-> END
```

---

## 10. Best Practices

### 10.1 Node Naming
- Use descriptive names: `[peng_explains_artifact]`
- Not generic: `[node_1]`, `[continue]`
- Group related nodes: `[shop_enter]`, `[shop_buy]`, `[shop_leave]`

### 10.2 Variable Naming
- Booleans: `has_sword`, `knows_secret`, `door_opened`
- Numbers: `gold`, `karma`, `player_level`
- Relationships: `peng_relationship`, `vendor_trust`

### 10.3 Writing Style
- Keep speaker lines concise
- Break long speeches into multiple lines
- Use narrator for actions/descriptions
- Show emotional context in the writing

### 10.4 Choice Design
- Make choices meaningful
- Show consequences in choice text when helpful
- Use conditions to create dynamic options
- Always have at least one available choice

### 10.5 File Organization
```
dialogues/
├── main_story/
│   ├── prologue/
│   │   ├── ship_intro.dlg
│   │   ├── beach_landing.dlg
│   │   └── peng_rescue.dlg
│   └── act1/
│       └── earth_kingdom.dlg
├── companions/
│   ├── peng_conversations.dlg
│   └── peng_quest.dlg
└── npcs/
    ├── merchants.dlg
    └── villagers.dlg
```

---

## 11. Vim Tips

### Search and Navigation
```vim
/\[node_name         " Find specific node
/\[                  " Jump between nodes
/->                  " Find all choices
/\*set               " Find all variable changes
/\{.*peng.*\}        " Find conditions with 'peng'
```

### Useful Mappings
```vim
" Add to .vimrc for .dlg files
autocmd FileType dlg nnoremap <leader>n /\[<CR>
autocmd FileType dlg nnoremap <leader>c /->.*:<CR>
autocmd FileType dlg setlocal foldmethod=expr
autocmd FileType dlg setlocal foldexpr=getline(v:lnum)=~'^\\[.*\\]$'?'>1':'='
```

### Folding
Nodes can be folded at `[node_name]` boundaries for easier navigation.

---

## 12. Error Messages

Parser will report:
- **Undefined target**: `-> unknown_node` doesn't exist
- **Undefined speaker**: Speaker not in `[characters]`
- **Undefined variable**: Using unset variable in condition
- **Unreachable node**: No path leads to this node
- **Missing END**: No way to exit conversation

---

## 13. Quick Conversion Guide

### From Your Hierarchical Format:
```
:node_name
Speaker: "Text"
Player:
  > "Choice"
    Response: "Text"
    -> next
```

### To DLG Format:
```
[node_name]
speaker: "Text"
-> player_response_1: "Choice"

[player_response_1]
speaker: "Response: Text"
-> next
```

The key difference: flatten the hierarchy into discrete nodes.

---

*This specification defines a format optimized for writing branching dialogue in vim while maintaining clarity and simplicity.*
