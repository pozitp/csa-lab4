.data
one: .word 1
newline: .word 10
ascii_bang: .word 33
done: .word 0
char: .word 0
name: .word 0
name_chars: .zero 32
name_ptr: .word name_chars
pstr_ptr: .word 0
pstr_len: .word 0
prompt: .pstr "What is your name?\n"
hello: .pstr "Hello, "

.text
.entry main
.interrupt input_irq
main:
    lea prompt
    call print_pstr
    ei
wait_name:
    ld done
    jz wait_name
    di
    lea hello
    call print_pstr
    lea name
    call print_pstr
    ld ascii_bang
    st %out
    ld newline
    st %out
    halt

input_irq:
    ld %in
    st char
    cmp newline
    jz input_done
    ld char
    stx name_ptr
    ld name_ptr
    add one
    st name_ptr
    ld name
    add one
    st name
    iret
input_done:
    ld one
    st done
    iret

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

