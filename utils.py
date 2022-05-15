import os
import time
import subprocess
import sh

from io import StringIO


_numlock_state = False
_last_system_sound_mute_state = 'unmute'
_mute_system_sound_ts = 0
_unmute_system_sound_after_secs = None
_power_led_brightness = 100
_set_power_led_process = None
_blink_numlock_ts = 0

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


def set_system_sound_mute_state(state: str):
    global _last_system_sound_mute_state

    if _last_system_sound_mute_state == state:
        return

    _last_system_sound_mute_state = state

    subprocess.Popen('amixer set Master ' + state, shell=True)


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


def get_devices_diskstats():
    devices = []

    with open('/proc/diskstats', 'r') as file:
        lines = file.read().splitlines()

        for iline in lines:
            iline = iline.strip()

            if not iline:
                continue

            parts = iline.split()

            if len(parts) != 20:
                continue

            device_basename = parts[2]
            len_device_basename = len(device_basename)

            if device_basename.startswith('sd') and len_device_basename == 3:
                devices.append(device_basename)
            elif device_basename.startswith('mmcblk') and len_device_basename == 7:
                devices.append(device_basename)

    return devices


def get_devices_mounts():
    mounts = {}

    with open('/proc/mounts', 'r') as file:
        lines = file.read().splitlines()

        for iline in lines:
            iline = iline.strip()

            if not iline:
                continue

            parts = iline.split(' ', 2)

            if len(parts) != 3:
                continue

            device = parts[0]
            len_device = len(device)

            if device.startswith('/dev/sd') and (len_device >= 8 and len_device <= 10):
                mounts[device] = parts[1]
            elif device.startswith('/dev/mmcblk') and (len_device >= 12 and len_device <= 16):
                mounts[device] = parts[1]

    return mounts


def get_devices_lables():
    labels = {}
    by_label = '/dev/disk/by-label/'

    for entry in os.listdir(by_label):
        device_basename = os.path.basename(os.path.realpath(by_label + entry))

        labels[device_basename] = entry

    return labels


def get_parsed_uevent(pathname):
    parsed = {}

    with open(pathname, 'r') as file:
        lines = file.read().splitlines()

        for iline in lines:
            iline = iline.strip()

            if not iline:
                continue

            parts = iline.split('=', 1)

            if len(parts) != 2:
                continue

            parsed[parts[0]] = parts[1]

    return parsed


def file_get_contents(pathname, size=None):
    if not os.path.exists(pathname) or not os.path.isfile(pathname):
        return ''

    with open(pathname) as f:
        return f.read(size)


def get_disk_partitions():
    '''
    Same as lsblk but much quicker.

    Missing:
    type (disk, partition)
    from uevent:DEVTYPE

    sector size
    from queue/hw_sector_size
    
    size
    from size:<size>*sector size
    
    fstype
    pttype
    ro
    '''
    devices = get_devices_diskstats()
    mounts = get_devices_mounts()
    labels = get_devices_lables()

    return_devices = {}

    for device_basename in devices:
        if file_get_contents('/sys/block/' + device_basename + '/size').strip() == '0':
            # no medium found
            continue

        uevent = get_parsed_uevent('/sys/block/' + device_basename + '/uevent')
        full_block_path = '/sys/block/' + device_basename

        path = '/dev/' + device_basename

        mountpoint = mounts[path] if path in mounts else ''
        label = labels[device_basename] if device_basename in labels else ''
        _type = uevent['DEVTYPE']

        item = {
            'path': path,
            'mountpoint': mountpoint,
            'name': device_basename,
            'label': label,
            'type': _type
        }

        return_devices[path] = item

        for sub_entry in os.listdir(full_block_path):
            if not sub_entry.startswith(device_basename):
                continue

            if not os.path.exists(full_block_path + '/' + sub_entry + '/partition'):
                continue

            if file_get_contents(full_block_path + '/' + sub_entry + '/size').strip() == '0':
                # no medium found
                continue

            sub_entry_uevent = get_parsed_uevent(full_block_path + '/' + sub_entry + '/uevent')

            sub_entry_path = '/dev/' + sub_entry
            sub_entry_mountpoint = mounts[sub_entry_path] if sub_entry_path in mounts else ''
            sub_entry_label = labels[sub_entry] if sub_entry in labels else ''
            sub_entry_type = sub_entry_uevent['DEVTYPE']

            sub_item = {
                'path': sub_entry_path,
                'mountpoint': sub_entry_mountpoint,
                'name': sub_entry,
                'label': sub_entry_label,
                'type': sub_entry_type
            }

            return_devices[sub_entry_path] = sub_item

    return return_devices


def get_fd_cached_percent(fd, size, between_secs = None):
    global fd_cached_percents

    current_time = time.time()

    if between_secs is not None:
        if fd in fd_cached_percents:
            if current_time - fd_cached_percents[fd]['time'] <= between_secs:
                return fd_cached_percents[fd]['percent']

    pid = os.getpid()
    vmtouch_buf = StringIO()
    proc_fd = '/proc/' + str(pid) + '/fd/' + str(fd)
    percent = 0

    sh.vmtouch('-f', '-p', str(size), proc_fd, _out=vmtouch_buf)

    for iline in vmtouch_buf.getvalue().splitlines():
        iline = iline.strip()

        if not iline:
            continue

        if not iline.startswith('Resident Pages: '):
            continue

        iline = iline.replace('Resident Pages: ', '').strip()

        if not iline:
            percent = 0
            break

        parts = iline.split('  ')

        if len(parts) != 3:
            percent = 0
            break

        last_part = parts[2]

        if not last_part.endswith('%'):
            percent = 0
            break

        last_part = last_part.replace('%', '')

        percent = float(last_part)
        break

    fd_cached_percents[fd] = {
        'percent': percent,
        'time': current_time
    }

    return percent
