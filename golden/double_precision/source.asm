.data
one: .word 1
ten: .word 10
newline: .word 10
ascii_zero: .word 48
base: .word 1000000000
a_hi: .word 123
a_lo: .word 999999999
b_hi: .word 789
b_lo: .word 2
sum_hi: .word 0
sum_lo: .word 0
carry: .word 0
print_n: .word 0
digit_count: .word 0
digit_ptr: .word digits
digits: .zero 16
pad_value: .word 0
pad_div: .word 100000000

.text
.entry main
main:
    ld a_lo
    add b_lo
    st sum_lo
    cmp base
    jl no_carry
    sub base
    st sum_lo
    ld one
    st carry
no_carry:
    ld a_hi
    add b_hi
    add carry
    st sum_hi
    ld sum_hi
    call print_uint
    ld sum_lo
    call print_padded9
    ld newline
    st %out
    halt

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

print_padded9:
    st pad_value
pad_loop:
    ld pad_div
    jz pad_done
    ld pad_value
    div pad_div
    add ascii_zero
    st %out
    ld pad_value
    mod pad_div
    st pad_value
    ld pad_div
    div ten
    st pad_div
    jmp pad_loop
pad_done:
    ret

