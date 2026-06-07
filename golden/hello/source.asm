.data
one: .word 1
pstr_ptr: .word 0
pstr_len: .word 0
msg: .pstr "Hello, world!\n"

.text
.entry main
main:
    lea msg
    call print_pstr
    halt

print_pstr:
    st pstr_ptr
    ldx pstr_ptr
    st pstr_len
    ld pstr_ptr
    add one
    st pstr_ptr
print_pstr_loop:
    ld pstr_len
    jz print_pstr_done
    ldx pstr_ptr
    st %out
    ld pstr_ptr
    add one
    st pstr_ptr
    ld pstr_len
    sub one
    st pstr_len
    jmp print_pstr_loop
print_pstr_done:
    ret

