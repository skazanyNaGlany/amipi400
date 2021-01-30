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


APP_UNIXNAME = 'berrymiga'
OWN_MOUNT_POINT_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
FS_UAE_PATHNAME = '/home/sng/projects.local/fs-uae.devbox/src/fs-uae/fs-uae'
FS_UAE_TMP_INI = os.path.join(os.path.dirname(FS_UAE_PATHNAME), 'fs-uae.tmp.ini')
COUNT_FLOPPIES = 1

floppies = [None for x in range(COUNT_FLOPPIES)]
context = pyudev.Context()
old_partitions = None
first_run = True

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


def get_partitions() -> OrderedDict:
    raw_disks = list(device for device in context.list_devices(subsystem='block', DEVTYPE='disk'))
    raw_partitions = list(context.list_devices(subsystem='block', DEVTYPE='partition'))
    return_partitions = OrderedDict()
    all_blocks = raw_disks+raw_partitions

    for idevice in all_blocks:
        attributes = list(idevice.attributes.available_attributes)

        device_data = {
            'mountpoint': '',
            'internal_mountpoint': os.path.join(
                OWN_MOUNT_POINT_PREFIX,
                get_relative_path(idevice.device_node)
            ),
            'removable': 'removable' in attributes,
            'label': idevice.get('ID_FS_LABEL', '')
        }

        for ipartition in psutil.disk_partitions():
            if ipartition.device == idevice.device_node:
                device_data['mountpoint'] = ipartition.mountpoint

        return_partitions[idevice.device_node] = device_data

    return return_partitions


def mount_partitions(partitions: dict) -> list:
    # just mount new removable drives (as partitions)
    mounted = []

    for key, value in partitions.items():
        if value['mountpoint'] or not value['label'].startswith('BM_DF'):
            continue

        # if not value['removable'] or value['mountpoint']:
        #     continue

        print('Mounting ' + key + ' as ' + value['internal_mountpoint'])

        os.makedirs(value['internal_mountpoint'], exist_ok=True)

        try:
            # pass
           sh.fsck('-y', key)
        except sh.ErrorReturnCode_1 as x1:
            print(str(x1))

        sh.mount(key, value['internal_mountpoint'])

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


def eject_unmounted(partitions: dict, old_partitions: dict) -> int:
    # eject all ADFs that file-system is unmounted
    # but was mounted before
    count_ejected = 0

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

            if floppies[0]:
                if floppies[0].startswith(value['mountpoint']):
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
            print('dddddddddddddd')
            if insert_mounted_floppy(key, value, force):
                print('22222222222222')
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
        if floppies[0] != roms[0]:
            print('Assigning "' + roms[0] + '" to DF0')

            floppies[0] = roms[0]


def generate_mount_table():
    cmd_no = 0
    contents = '[commands]\n'

    for index, ifloppy in enumerate(floppies):
        contents += 'cmd' + str(cmd_no) + '=ext_disk_eject ' + str(index) + '\n'
        cmd_no += 1

        if ifloppy:
            contents += 'cmd' + str(cmd_no) + '=ext_disk_insert_force ' + str(index) + ',' + ifloppy + ',0\n'
            cmd_no += 1

    print(FS_UAE_TMP_INI + ' contents:')
    print(contents)

    with open(FS_UAE_TMP_INI, 'w', newline=None) as f:
        f.write(contents)


def send_SIGUSR1_signal():
    print('Sending SIGUSR1 signal to FS-UAE emulator')

    try:
        sh.killall('-USR1', 'fs-uae')
    except sh.ErrorReturnCode_1:
        print('No process found')


# def get_partitions2() -> OrderedDict:
#     lsblk_buf = StringIO()
#     pattern = r'NAME="(\w*)" SIZE="(\d{0,}.\d{0,}[G|M|K])" TYPE="(\w*)" MOUNTPOINT="(.*)"'
#     lsblk = []

#     sh.lsblk('-P', '-o', 'path,mountpoint,label', '-n', _out=lsblk_buf)

#     for line in lsblk_buf.getvalue().splitlines()[1:]:
#         line = line.strip()

#         if not line:
#             continue


def get_partitions2() -> OrderedDict:
    lsblk_buf = StringIO()
    pattern = r'NAME="(\w*)" SIZE="(\d{0,}.\d{0,}[G|M|K])" TYPE="(\w*)" MOUNTPOINT="(.*)" LABEL="(.*)"'
    ret = OrderedDict()

    sh.lsblk('-P', '-o', 'name,size,type,mountpoint,label', '-n', _out=lsblk_buf)

    for line in lsblk_buf.getvalue().splitlines()[1:]:
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


last_clear_system_cache = 0


def clear_system_cache():
    global last_clear_system_cache

    ts = int(time.time())

    if last_clear_system_cache and ts - last_clear_system_cache <= 32:
        return

    print('Clearing system cache')

    os.system('sync')
    os.system('echo 3 > /proc/sys/vm/drop_caches')
    os.system('sync')

    last_clear_system_cache = ts


partitions = None
old_partitions = None

while True:
    partitions = get_partitions2()

    if old_partitions and str(old_partitions) != str(partitions):
        print('changed')

        print_partitions(partitions)
        mount_partitions(partitions)
        eject_unmounted(partitions, old_partitions)
        insert_mounted(partitions, old_partitions)
        generate_mount_table()
        send_SIGUSR1_signal()

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


        # mount_partitions(partitions)

        # partitions = get_partitions2()

        # eject_unmounted(partitions, old_partitions)
        # insert_mounted(partitions, old_partitions)
        # generate_mount_table()
        # send_SIGUSR1_signal()

    if not old_partitions:
        old_partitions = partitions

    clear_system_cache()

    time.sleep(1)


# partitions = get_partitions()
# print_partitions(partitions)
# insert_mounted(partitions, None, True)
# # generate_mount_table()
# # send_SIGUSR1_signal()
# mount_partitions(partitions)

# while True:
#     partitions = get_partitions()

#     if not old_partitions or str(old_partitions) != str(partitions):
#         # something new
#         if old_partitions:
#             eject_unmounted(partitions, old_partitions)
#             insert_mounted(partitions, old_partitions)
#             generate_mount_table()
#             send_SIGUSR1_signal()
#             mount_partitions(partitions)

#     time.sleep(1)

#     old_partitions = partitions









# partitions = get_partitions2()
# print_partitions(partitions)
# insert_mounted(partitions, None, True)
# # generate_mount_table()
# # send_SIGUSR1_signal()
# mount_partitions(partitions)

# while True:
#     partitions = get_partitions2()

#     if not old_partitions or str(old_partitions) != str(partitions):
#         # something new
#         if old_partitions:
#             eject_unmounted(partitions, old_partitions)
#             insert_mounted(partitions, old_partitions)
#             generate_mount_table()
#             send_SIGUSR1_signal()
#             mount_partitions(partitions)

#     time.sleep(0.5)

#     old_partitions = partitions








# while True:
#     partitions = get_partitions2()

#     time.sleep(1)













    # raw_disks = list(device for device in context.list_devices(subsystem='block', DEVTYPE='disk'))
    # raw_partitions = list(context.list_devices(subsystem='block', DEVTYPE='partition'))
    # return_partitions = OrderedDict()
    # all_blocks = raw_disks+raw_partitions

    # for idevice in all_blocks:
    #     attributes = list(idevice.attributes.available_attributes)

    #     device_data = {
    #         'mountpoint': '',
    #         'internal_mountpoint': os.path.join(
    #             OWN_MOUNT_POINT_PREFIX,
    #             get_relative_path(idevice.device_node)
    #         ),
    #         'removable': 'removable' in attributes,
    #         'label': idevice.get('ID_FS_LABEL', '')
    #     }

    #     for ipartition in psutil.disk_partitions():
    #         if ipartition.device == idevice.device_node:
    #             device_data['mountpoint'] = ipartition.mountpoint

    #     return_partitions[idevice.device_node] = device_data

    # return return_partitions


# import re

# disk_pattern1 = re.compile(r'.*\ \[[a-z]{3}\]\ .*')
# disk_pattern2 = re.compile(r'\ busy inodes on changed media or resized disk\ ')

# def dmesg_process(line):
#     line = line.strip()

#     if line:
#         print(line)

#         if disk_pattern1.match(line) or disk_pattern2.match(line):
#             print('ddd')

#             partitions = get_partitions()
#             print_partitions(partitions)


# dmesg_process = sh.dmesg('-Hw', _out=dmesg_process, _bg=True)
# dmesg_process.wait()


# from io import StringIO


# dmesg_buf = StringIO()

# sh.dmesg(_out = dmesg_buf)

# while True:
#     for line in dmesg_buf:
#         print(line)

#     # time.sleep(1)

#     # time.sleep(1)


# # for line in dmesg_buf:
# #     print(line)

# # print(dmesg_buf.getvalue())


# # print(sh.wc(sh.dmesg()))



# while True:
#     dmesg = sh.dmesg()
#     print(dmesg.split())




# while True:
#     partitions = get_partitions()

#     if first_run:
#         first_run = False
#         print_partitions(partitions)

#     mount_partitions(partitions)

#     if old_partitions:
#         if eject_unmounted(partitions, old_partitions):
#             generate_mount_table()
#             send_SIGUSR1_signal()

#     if insert_mounted(partitions, None):
#         generate_mount_table()
#         send_SIGUSR1_signal()

#     old_partitions = partitions

#     time.sleep(0.5)







# partitions = get_partitions()
# print_partitions(partitions)
# mount_partitions(partitions)
# insert_mounted(partitions, None, True)
# generate_mount_table()
# send_SIGUSR1_signal()
# # mount_partitions(partitions)

# while True:
#     partitions = get_partitions()

#     if not old_partitions or str(old_partitions) != str(partitions):
#         # something new
#         if old_partitions:
#             eject_unmounted(partitions, old_partitions)
#             insert_mounted(partitions, old_partitions)
#             generate_mount_table()
#             send_SIGUSR1_signal()
#             mount_partitions(partitions)

#     time.sleep(0.5)

#     old_partitions = partitions









# partitions = get_partitions()
# print_partitions(partitions)
# insert_mounted(partitions, None, True)
# # generate_mount_table()
# # send_SIGUSR1_signal()
# mount_partitions(partitions)

# while True:
#     partitions = get_partitions()

#     if not old_partitions or str(old_partitions) != str(partitions):
#         # something new
#         if old_partitions:
#             eject_unmounted(partitions, old_partitions)
#             insert_mounted(partitions, old_partitions)
#             generate_mount_table()
#             send_SIGUSR1_signal()
#             mount_partitions(partitions)

#     time.sleep(0.5)

#     old_partitions = partitions
