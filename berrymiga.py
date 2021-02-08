import pyudev
import psutil
import sh
import time
import os
import tempfile
import sys
import fnmatch
import re

from pprint import pprint
from collections import OrderedDict
from typing import Optional
from io import StringIO
from pynput.keyboard import Key, Listener


APP_UNIXNAME = 'berrymiga'
OWN_MOUNT_POINT_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
FS_UAE_PATHNAME = '/home/pi/projects.local/amiberry/amiberry'
FS_UAE_TMP_INI = os.path.join(os.path.dirname(FS_UAE_PATHNAME), 'amiberry.tmp.ini')
COUNT_FLOPPIES = 1

floppies = [None for x in range(COUNT_FLOPPIES)]
context = pyudev.Context()
old_partitions = None
first_run = True
partitions = None
old_partitions = None
key_ctrl_pressed = False
key_alt_pressed = False
key_delete_pressed = False


os.makedirs(OWN_MOUNT_POINT_PREFIX, exist_ok=True)


def get_relative_path(pathname: str) -> str:
    if pathname[0] == os.path.sep:
        return pathname[1:]

    return pathname


def get_partition_label(raw_partitions, device_pathname: str, default: str) ->  Optional[str]:
    for ipartition in raw_partitions:
        if ipartition.device_node == device_pathname:
            return ipartition.get('ID_FS_LABEL', '')
    
    return default


def mount_partitions(partitions: dict) -> list:
    # just mount new removable drives (as partitions)
    mounted = []

    for key, value in partitions.items():
        if value['mountpoint'] or not value['label'].startswith('BM_DF'):
            continue

        print('Mounting ' + key + ' as ' + value['internal_mountpoint'])

        os.makedirs(value['internal_mountpoint'], exist_ok=True)

        try:
           sh.fsck('-y', key)
        except sh.ErrorReturnCode_1 as x1:
            print(str(x1))
        except sh.ErrorReturnCode_6 as x2:
            print(str(x2))

        sh.mount(key, '-ouser,umask=0000', value['internal_mountpoint'])

        mounted.append(key)

    return mounted


def print_partitions(partitions: dict):
    if not partitions:
        return

    print('Known partitions:')

    for key, value in partitions.items():
        print(key)

        print('  mountpoint: ' + str(value['mountpoint']))
        print('  internal_mountpoint: ' + value['internal_mountpoint'])
        # print('  removable: ' + str(value['removable']))
        print('  label: ' + str(value['label']))

        print()


def force_umount(pathname: str):
    try:
        sh.umount('-l', pathname)
    except sh.ErrorReturnCode_1:
        print('Failed to force-umount ' + pathname + ', maybe it is umounted already')


def eject_unmounted(partitions: dict, old_partitions: dict) -> int:
    # eject all ADFs that file-system is unmounted
    # but was mounted before
    count_ejected = 0

    if not old_partitions:
        return count_ejected

    for key, value in old_partitions.items():
        mounted = True

        if key not in partitions:
            mounted = False

        if mounted:
            for key2, value2 in partitions.items():
                if key2 == key and not value2['mountpoint'] and value['mountpoint']:
                    mounted = False
                    break
        
        if not mounted:
            print('Unmounted ' + key)

            force_umount(key)

            if floppies[0]:
                if floppies[0]['pathname'].startswith(value['mountpoint']):
                    print('Ejecting DF0')

                    floppies[0] = None

                    count_ejected += 1

    return count_ejected


def insert_mounted_floppy(ipartition: str, ipartition_data, force: Optional[bool] = False):
    new_mounted = False

    if not old_partitions:
        new_mounted = True

    if not new_mounted:
        if ipartition not in old_partitions:
            new_mounted = True

        if not new_mounted:
            for key2, value2 in old_partitions.items():
                if key2 == ipartition and (not value2['mountpoint'] or not value2['label']):
                    new_mounted = True
                    break

    if force:
        new_mounted = True

    if new_mounted:
        print('New mounted ' + ipartition)

        try:
            sh.chmod('-R', 'a+rw', ipartition_data['mountpoint'])
        except sh.ErrorReturnCode_1 as x1:
            print(str(x1))

        assign_floppy_from_mountpoint(ipartition_data['mountpoint'])

        return True

    return False


def insert_mounted(partitions: dict, old_partitions: dict, force: Optional[bool] = False) -> bool:
    # detect new mounted partition and insert ADF
    # if it is present
    for key, value in partitions.items():
        if not value['mountpoint']:
            continue

        if value['label'].startswith('BM_DF'):
            if insert_mounted_floppy(key, value, force):
                return True

    return False


def assign_floppy_from_mountpoint(mountpoint: str):
    roms = []

    for file in os.listdir(mountpoint):
        file_lower = file.lower()

        if not fnmatch.fnmatch(file_lower, '*.adf'):
            continue

        roms.append(os.path.join(mountpoint, file))

    roms = sorted(roms)

    if roms:
        if not floppies[0] or floppies[0]['pathname'] != roms[0]:
            print('Assigning "' + roms[0] + '" to DF0')

            floppies[0] = {
                'pathname': roms[0],
                'file_size': os.path.getsize(roms[0]),
                'last_access_ts': 0,
                'last_cached_size': 0
            }


def generate_mount_table():
    cmd_no = 0
    contents = '[commands]\n'

    for index, ifloppy in enumerate(floppies):
        contents += 'cmd' + str(cmd_no) + '=ext_disk_eject ' + str(index) + '\n'
        cmd_no += 1

        if ifloppy:
            contents += 'cmd' + str(cmd_no) + '=ext_disk_insert_force ' + str(index) + ',' + ifloppy['pathname'] + ',0\n'
            cmd_no += 1

    print(FS_UAE_TMP_INI + ' contents:')
    print(contents)

    with open(FS_UAE_TMP_INI, 'w+', newline=None) as f:
        f.write(contents)


def generate_soft_reset():
    contents = '[commands]\n'
    contents += 'cmd0=uae_reset 0,0\n'

    print(FS_UAE_TMP_INI + ' contents:')
    print(contents)

    with open(FS_UAE_TMP_INI, 'w+', newline=None) as f:
        f.write(contents)


def send_SIGUSR1_signal():
    print('Sending SIGUSR1 signal to Amiberry emulator')

    try:
        sh.killall('-USR1', 'amiberry')
    except sh.ErrorReturnCode_1:
        print('No process found')


def get_partitions2() -> OrderedDict:
    lsblk_buf = StringIO()
    pattern = r'NAME="(\w*)" SIZE="(\d{0,}.\d{0,}[G|M|K])" TYPE="(\w*)" MOUNTPOINT="(.*)" LABEL="(.*)"'
    ret = OrderedDict()

    sh.lsblk('-P', '-o', 'name,size,type,mountpoint,label', '-n', _out=lsblk_buf)

    for line in lsblk_buf.getvalue().splitlines():
        line = line.strip()

        if not line:
            continue

        found = re.search(pattern,line).groups()

        full_path = os.path.join(os.path.sep, 'dev', found[0])
        device_data = {
            'mountpoint': found[3],
            'internal_mountpoint': os.path.join(
                OWN_MOUNT_POINT_PREFIX,
                get_relative_path(full_path)
            ),
            'label': found[4]
        }

        ret[full_path] = device_data

    return ret


def clear_system_cache(force = False):
    print('Clearing system cache')

    os.system('sync')
    #os.system('echo 3 > /proc/sys/vm/drop_caches')
    os.system('echo 1 > /proc/sys/vm/drop_caches')
    os.system('sync')


def from_filesize(spec, si=True):
    decade = 1000 if si else 1024
    suffixes = tuple('BKMGTP')

    num = float(spec[:-1])
    s = spec[-1]
    i = suffixes.index(s)

    for n in range(i):
        num *= decade

    return int(num)


def get_file_cached_size(pathname: str) -> int:
    fincore_buf = StringIO()

    try:
        sh.fincore('-b', pathname, _out=fincore_buf)
    except sh.ErrorReturnCode_1:
        return 0

    for line in fincore_buf.getvalue().splitlines():
        line = line.strip()

        if not line:
            continue

        line = line.replace('  ', ' ')
        parts = [ipart.strip() for ipart in line.split(' ', 4) if ipart.strip()]

        if len(parts) == 4 and parts[3] == pathname:
            return int(parts[0])

    return 0


def check_need_clear_cache() -> bool:
    ts = int(time.time())

    for ifloppy in floppies:
        if not ifloppy:
            continue

        file_size = ifloppy['file_size']

        if not file_size:
            continue

        new_cached_size = get_file_cached_size(ifloppy['pathname'])

        if new_cached_size > ifloppy['last_cached_size']:
            ifloppy['last_cached_size'] = new_cached_size
            ifloppy['last_access_ts'] = ts

        if ifloppy['last_access_ts'] and ts - ifloppy['last_access_ts'] >= 60:
            if ifloppy['last_cached_size'] >= 99 / 100 * file_size:
                print(str(ts - ifloppy['last_access_ts']))
                print(ifloppy)

                ifloppy['last_cached_size'] = 0
                ifloppy['last_access_ts'] = 0

                return True

    return False


def on_key_press(key):
    global key_ctrl_pressed
    global key_alt_pressed
    global key_delete_pressed

    if key == Key.ctrl:
        key_ctrl_pressed = True

    if key == Key.alt:
        key_alt_pressed = True

    if key == Key.delete:
        key_delete_pressed = True

    if key_ctrl_pressed and key_alt_pressed and key_delete_pressed:
        key_ctrl_pressed = False
        key_alt_pressed = False
        key_delete_pressed = False

        generate_soft_reset()
        send_SIGUSR1_signal()
        clear_system_cache()


keyboard_listener = Listener(on_press=on_key_press)
keyboard_listener.start()

clear_system_cache(True)

while True:
    partitions = get_partitions2()

    if str(old_partitions) != str(partitions):
        print('Changed')

        print_partitions(partitions)
        mount_partitions(partitions)
        eject_unmounted(partitions, old_partitions)
        insert_mounted(partitions, old_partitions)
        generate_mount_table()
        send_SIGUSR1_signal()
        clear_system_cache(True)
        old_partitions = partitions

        print()
        print()
        print()
        print()
        print()
        print()
        print()
        print()
        print()
        print()
        print()

    if not old_partitions:
        old_partitions = partitions

    if check_need_clear_cache():
        clear_system_cache(True)

    time.sleep(1)
