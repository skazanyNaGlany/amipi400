import os


numlock_state = False


def set_numlock_state(state: bool):
    global numlock_state

    state = state is True

    if state == numlock_state:
        return

    os.system('echo {state} | sudo tee /sys/class/leds/input?::numlock/brightness > /dev/null'.format(
        state = 1 if state else 0
    ))

    numlock_state = state


def enable_numlock():
    set_numlock_state(True)


def disable_numlock():
    set_numlock_state(False)
