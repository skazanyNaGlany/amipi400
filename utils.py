import glob
import os
import time
import subprocess


_numlock_state = False
_last_system_sound_mute_state = 'unmute'
_mute_system_sound_ts = 0
_unmute_system_sound_after_secs = None
_power_led_brightness = 100
_set_power_led_process = None
_blink_numlock_ts = 0
_simple_mixer_control = None

fd_cached_percents = {}


def mute_system_sound(unmute_after_secs = None):
    global _mute_system_sound_ts
    global _unmute_system_sound_after_secs

    if unmute_after_secs is not None:
        _unmute_system_sound_after_secs = unmute_after_secs

    _mute_system_sound_ts = time.time()

    set_system_sound_mute_state('mute')


def unmute_system_sound():
    if _unmute_system_sound_after_secs is not None:
        if time.time() - _mute_system_sound_ts < _unmute_system_sound_after_secs:
            return

    set_system_sound_mute_state('unmute')


def init_simple_mixer_control():
    global _simple_mixer_control

    process = subprocess.Popen(
        [
            'amixer',
            'scontrols'
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    out, err = process.communicate()

    lines = out.splitlines()

    if not lines:
        return

    lines[0] = lines[0].strip()

    if not lines[0]:
        return

    first_control = lines[0].decode('utf-8')
    first_control = first_control.replace('Simple mixer control \'', '')
    first_control = first_control.replace('\',0', '')

    first_control = first_control.strip()

    if not first_control:
        print('Simple mixer control not found')
        return

    print('Found simple mixer control', first_control)

    _simple_mixer_control = first_control


def set_system_sound_mute_state(state: str):
    global _last_system_sound_mute_state

    if _last_system_sound_mute_state == state:
        return

    _last_system_sound_mute_state = state

    if not _simple_mixer_control:
        print('No simple mixer control, run init_simple_mixer_control()')
        return

    subprocess.Popen('amixer set ' + _simple_mixer_control + ' ' + state, shell=True)


def set_numlock_state(state: bool):
    global _numlock_state

    state = state is True

    if state == _numlock_state:
        return

    os.system('echo {state} | sudo tee /sys/class/leds/input?::numlock/brightness > /dev/null'.format(
        state = 1 if state else 0
    ))

    _numlock_state = state


def enable_numlock():
    set_numlock_state(True)


def disable_numlock():
    set_numlock_state(False)


def blink_numlock():
    global _blink_numlock_ts

    current_time = time.time()

    if current_time - _blink_numlock_ts < 1:
        return

    _blink_numlock_ts = current_time

    set_numlock_state(not _numlock_state)


def set_power_led_brightness(brightness):
    global _power_led_brightness
    global _set_power_led_process

    if brightness == _power_led_brightness:
        return

    if _set_power_led_process is not None:
        if _set_power_led_process.poll() is None:
            return

    cmd = 'echo ' + str(brightness) + ' > /sys/class/leds/led0/brightness'

    _set_power_led_process = subprocess.Popen(cmd, shell=True)
    _power_led_brightness = brightness


def enable_power_led():
    set_power_led_brightness(100)


def disable_power_led():
    set_power_led_brightness(0)


def get_dir_size(dir: str):
    # https://stackoverflow.com/a/4368431
    total_size = os.path.getsize(dir)
    for item in os.listdir(dir):
        itempath = os.path.join(dir, item)
        if os.path.isfile(itempath):
            total_size += os.path.getsize(itempath)
        elif os.path.isdir(itempath):
            total_size += get_dir_size(itempath)
    return total_size


def get_dir_oldest_file(dir: str):
    # https://stackoverflow.com/a/65464617
    return sorted(glob.glob(os.path.join(dir, '*')), key=os.path.getctime)[0]


def save_replace_file(pathname: str, contents: bytes, max_dir_size: int):
    dir = os.path.dirname(pathname)

    if get_dir_size(dir) >= max_dir_size:
        oldest_pathname = get_dir_oldest_file(dir)

        os.remove(oldest_pathname)

    file_write_bytes(pathname, 0, contents, os.O_SYNC | os.O_CREAT)


def file_read_bytes(pathname, offset, size, additional_flags = 0):
    fd = os.open(pathname, os.O_RDONLY | additional_flags)

    if fd < 0:
        return -1

    if os.lseek(fd, offset, os.SEEK_SET) < 0:
        return -1

    result = os.read(fd, size)

    os.close(fd)

    return result


def file_write_bytes(pathname, offset, data, additional_flags = 0):
    fd = os.open(pathname, os.O_WRONLY | additional_flags)

    if fd < 0:
        return -1

    if os.lseek(fd, offset, os.SEEK_SET) < 0:
        return -1

    result = os.write(fd, data)

    os.close(fd)

    return result
