" Vim filetype plugin for .dlg dialogue files
" Language: DLG (Dialogue Forge)

" Set comment string for commenting plugins
setlocal commentstring=#\ %s

" Tab settings for clean indentation
setlocal tabstop=4
setlocal shiftwidth=4
setlocal expandtab

" Text width for dialogue lines
setlocal textwidth=100

" Enable line wrapping (useful for multi-line dialogue)
setlocal wrap
setlocal linebreak

" Fold at node boundaries
setlocal foldmethod=expr
setlocal foldexpr=DlgFoldExpr(v:lnum)
setlocal foldlevel=99

" Fold expression for .dlg files
function! DlgFoldExpr(lnum)
    let line = getline(a:lnum)

    " Node definitions start a new fold
    if line =~# '^\s*\[.\+\]$'
        return '>1'
    endif

    " Special sections
    if line =~# '^\s*\[\(characters\|state\)\]$'
        return '>1'
    endif

    " Empty lines don't change fold level
    if line =~# '^\s*$'
        return '='
    endif

    " Everything else continues the current fold
    return '='
endfunction

" Fold text shows node name
setlocal foldtext=DlgFoldText()

function! DlgFoldText()
    let line = getline(v:foldstart)
    let node_match = matchstr(line, '\[\zs[^\]]\+\ze\]')
    let lines_count = v:foldend - v:foldstart + 1
    if node_match != ''
        return '+-- [' . node_match . '] (' . lines_count . ' lines) '
    endif
    return '+-- ' . lines_count . ' lines '
endfunction
