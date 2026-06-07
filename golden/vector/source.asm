.data
one: .word 1
ten: .word 10
newline: .word 10
space: .word 32
ascii_zero: .word 48
a: .words 1 2 3 4
b: .words 5 6 7 8
limit: .words 3 3 3 3
out: .zero 4
cmp_out: .zero 4
arr_ptr: .word 0
arr_left: .word 0
print_n: .word 0
digit_count: .word 0
digit_ptr: .word digits
digits: .zero 16

.text
.entry main
main:
    vld v0, a
    vld v1, b
    vadd v0, v1
    vst v0, out
    vld v2, limit
    vcmpgt v0, v2
    vst v0, cmp_out
    lea out
    st arr_ptr
    ldi 4
    st arr_left
    call print_array
    lea cmp_out
    st arr_ptr
    ldi 4
    st arr_left
    call print_array
    halt

print_array:
    ld arr_left
    jz print_array_done
    ldx arr_ptr
    call print_uint
    ld arr_ptr
    add one
    st arr_ptr
    ld arr_left
    sub one
    st arr_left
    jz print_array_newline
    ld space
    st %out
    jmp print_array
print_array_newline:
    ld newline
    st %out
    jmp print_array
print_array_done:
    ret

print_uint:
    st print_n
    ldi 0
    st digit_count
    lea digits
    st digit_ptr
    ld print_n
    jnz print_uint_loop
    ld ascii_zero
    st %out
    ret
print_uint_loop:
    ld print_n
    jz emit_digits
    mod ten
    add ascii_zero
    stx digit_ptr
    ld digit_ptr
    add one
    st digit_ptr
    ld digit_count
    add one
    st digit_count
    ld print_n
    div ten
    st print_n
    jmp print_uint_loop
emit_digits:
    ld digit_count
    jz print_uint_done
    ld digit_ptr
    sub one
    st digit_ptr
    ldx digit_ptr
    st %out
    ld digit_count
    sub one
    st digit_count
    jmp emit_digits
print_uint_done:
    ret

