" Vim syntax file for .dlg dialogue files
" Language: DLG (Dialogue Forge)
" Maintainer: Dialogue Forge
" Latest Revision: 2025
" Features: Multi-line string support, conditions, state section

if exists("b:current_syntax")
  finish
endif

" Sync from start to handle multi-line strings correctly
syn sync fromstart

" Comments (lines starting with #)
syn match dlgComment "^\s*#.*$"

" Node definitions [node_name]
syn match dlgNode "^\s*\[[^\]]\+\]"

" Special sections
syn match dlgSpecialNode "^\s*\[\(start\|characters\|state\)\]"

" Character definitions in [characters] section
syn match dlgCharacterDef "^\s*\w\+:" nextgroup=dlgCharacterName skipwhite
syn match dlgCharacterName ".*$" contained

" Multi-line string support - strings that can span lines
" This is the key change: removed 'oneline' and added 'extend'
syn region dlgString start=/"/ skip=/\\"/ end=/"/ contains=dlgEscape extend

" Tags [tag1, tag2] - optional metadata after strings (e.g., for emotions/portraits)
" Note: This matches [...] that appears AFTER a string on a line, not node definitions
syn region dlgTag start=/"\s*\zs\[/ end=/\]/ contains=dlgTagContent
syn match dlgTagContent "[^\[\]]*" contained contains=dlgTagName,dlgTagComma
syn match dlgTagName "\w\+" contained
syn match dlgTagComma "," contained

" Conditions {...} - can appear after strings or tags
syn region dlgCondition start=/{/ end=/}/ contains=dlgConditionContent,dlgOperator,dlgNumber,dlgBoolean,dlgKeyword
syn match dlgConditionContent "[^{}]*" contained contains=dlgOperator,dlgNumber,dlgBoolean,dlgKeyword

" Speaker at start of line (before the string)
syn match dlgSpeaker "^\s*\w\+\ze\s*:" nextgroup=dlgSpeakerColon
syn match dlgSpeakerColon ":" contained nextgroup=dlgString skipwhite

" Choices (-> target: "text" {condition})
syn match dlgChoice "^\s*->" nextgroup=dlgChoiceTarget skipwhite
syn match dlgChoiceTarget "\w\+" contained nextgroup=dlgChoiceColon skipwhite
syn match dlgChoiceColon ":" contained nextgroup=dlgString,dlgActionText skipwhite

" Action text with brackets [action text]
syn region dlgActionText start=/\[/ end=/\]/ contained nextgroup=dlgCondition skipwhite

" Commands (*command parameter = value)
syn match dlgCommand "^\s*\*\w\+" nextgroup=dlgCommandArgs skipwhite
syn match dlgCommandArgs ".*$" contained contains=dlgNumber,dlgBoolean,dlgOperator,dlgString

" Special patterns
syn match dlgEscape /\\./ contained
syn match dlgNumber "\<-\?\d\+\>" contained
syn keyword dlgBoolean true false contained
syn match dlgOperator "[=<>!&|+-]" contained
syn match dlgOperator "&&\|||" contained

" Special keywords in conditions
syn keyword dlgKeyword has_item companion contained

" END keyword (special target for choices)
syn keyword dlgEnd END

" Define the default highlighting
hi def link dlgComment        Comment
hi def link dlgNode           Statement
hi def link dlgSpecialNode    PreProc
hi def link dlgCharacterDef   Type
hi def link dlgCharacterName  String
hi def link dlgSpeaker        Identifier
hi def link dlgSpeakerColon   Operator
hi def link dlgString         String
hi def link dlgChoice         Keyword
hi def link dlgChoiceTarget   Function
hi def link dlgChoiceColon    Operator
hi def link dlgActionText     Type
hi def link dlgCondition      Special
hi def link dlgConditionContent Special
hi def link dlgCommand        PreProc
hi def link dlgCommandArgs    Normal
hi def link dlgEscape         SpecialChar
hi def link dlgNumber         Number
hi def link dlgBoolean        Boolean
hi def link dlgOperator       Operator
hi def link dlgKeyword        Keyword
hi def link dlgEnd            Error
hi def link dlgTag            Type
hi def link dlgTagContent     Type
hi def link dlgTagName        Type
hi def link dlgTagComma       Operator

" Custom highlighting for action text (italicized)
hi dlgActionText gui=italic cterm=italic guifg=#87ceeb ctermfg=117

" Custom highlighting for tags (green, to stand out as metadata)
hi dlgTag gui=NONE cterm=NONE guifg=#10b981 ctermfg=36
hi dlgTagName gui=NONE cterm=NONE guifg=#10b981 ctermfg=36

let b:current_syntax = "dlg"
