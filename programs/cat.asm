.data
one: .word 1
newline: .word 10
done: .word 0
char: .word 0

.text
.entry main
.interrupt input_irq
main:
    ei
wait_input:
    ld done
    jz wait_input
    halt

input_irq:
    ld %in
    st char
    cmp newline
    jz input_done
    ld char
    st %out
    iret
input_done:
    ld one
    st done
    iret

