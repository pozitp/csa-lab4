.data
one: .word 1
ten: .word 10
lower: .word 0
upper: .word 0
newline: .word 10
ascii_zero: .word 48
got_input: .word 0
input_digits: .word 0
digit_counter: .word 0
i: .word 0
j: .word 0
product: .word 0
best: .word 0
pal_original: .word 0
pal_n: .word 0
pal_rev: .word 0
pal_digit: .word 0
is_pal_result: .word 0
print_n: .word 0
digit_count: .word 0
digit_ptr: .word digits
digits: .zero 16

.text
.entry main
.interrupt input_irq
main:
    ei
wait_digit:
    ld got_input
    jz wait_digit
    di
    ldi 1
    st lower
    ld input_digits
    sub one
    st digit_counter
build_lower:
    ld digit_counter
    jz build_upper
    ld lower
    mul ten
    st lower
    ld digit_counter
    sub one
    st digit_counter
    jmp build_lower
build_upper:
    ld lower
    mul ten
    sub one
    st upper
    ldi 0
    st best
    ld upper
    st i
outer_loop:
    ld i
    cmp lower
    jl done
    ld i
    mul upper
    cmp best
    jle done
    ld upper
    st j
inner_loop:
    ld j
    cmp i
    jl next_i
    ld i
    mul j
    st product
    cmp best
    jle next_i
    ld product
    call is_palindrome
    ld is_pal_result
    jz dec_j
    ld product
    st best
    jmp next_i
dec_j:
    ld j
    sub one
    st j
    jmp inner_loop
next_i:
    ld i
    sub one
    st i
    jmp outer_loop
done:
    ld best
    call print_uint
    ld newline
    st %out
    halt

input_irq:
    ld %in
    sub ascii_zero
    st input_digits
    ld one
    st got_input
    iret

is_palindrome:
    st pal_original
    st pal_n
    ldi 0
    st pal_rev
pal_loop:
    ld pal_n
    jz pal_check
    mod ten
    st pal_digit
    ld pal_rev
    mul ten
    add pal_digit
    st pal_rev
    ld pal_n
    div ten
    st pal_n
    jmp pal_loop
pal_check:
    ld pal_rev
    cmp pal_original
    jz pal_true
    ldi 0
    st is_pal_result
    ret
pal_true:
    ld one
    st is_pal_result
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
