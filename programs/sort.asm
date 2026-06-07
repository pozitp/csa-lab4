.data
one: .word 1
newline: .word 10
ascii_zero: .word 48
space: .word 32
done: .word 0
char: .word 0
arr: .zero 8
arr_ptr: .word arr
count: .word 0
i: .word 0
j: .word 0
limit: .word 0
left_ptr: .word 0
right_ptr: .word 0
left_val: .word 0
right_val: .word 0

.text
.entry main
.interrupt input_irq
main:
    ei
wait_input:
    ld done
    jz wait_input
    di
    ldi 0
    st i
outer_loop:
    ld i
    cmp count
    jge print_result
    ldi 0
    st j
    ld count
    sub one
    sub i
    st limit
inner_loop:
    ld j
    cmp limit
    jge outer_next
    lea arr
    add j
    st left_ptr
    ld left_ptr
    add one
    st right_ptr
    ldx left_ptr
    st left_val
    ldx right_ptr
    st right_val
    ld left_val
    cmp right_val
    jle no_swap
    ld right_val
    stx left_ptr
    ld left_val
    stx right_ptr
no_swap:
    ld j
    add one
    st j
    jmp inner_loop
outer_next:
    ld i
    add one
    st i
    jmp outer_loop

print_result:
    ldi 0
    st j
print_loop:
    ld j
    cmp count
    jge end
    lea arr
    add j
    st left_ptr
    ldx left_ptr
    add ascii_zero
    st %out
    ld j
    add one
    st j
    cmp count
    jge print_loop
    ld space
    st %out
    jmp print_loop
end:
    ld newline
    st %out
    halt

input_irq:
    ld %in
    st char
    cmp newline
    jz input_done
    ld char
    sub ascii_zero
    stx arr_ptr
    ld arr_ptr
    add one
    st arr_ptr
    ld count
    add one
    st count
    iret
input_done:
    ld one
    st done
    iret

