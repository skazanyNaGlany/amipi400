import pyudev
import psutil
import sh
import time
import os
import tempfile
import sys
import fnmatch

from pprint import pprint
from collections import OrderedDict
from typing import Optional


APP_UNIXNAME = 'berrymiga'
OWN_MOUNT_POINT_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
FS_UAE_PATHNAME = '/home/sng/projects.local/fs-uae.devbox/src/fs-uae/fs-uae'
FS_UAE_TMP_INI = os.path.join(os.path.dirname(FS_UAE_PATHNAME), 'fs-uae.tmp.ini')
COUNT_FLOPPIES = 1

floppies = [None for x in range(COUNT_FLOPPIES)]
context = pyudev.Context()
old_partitions = None

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


def get_partitions(removables_only: Optional[bool] = False) -> OrderedDict:
    if removables_only:
        disks = [device for device in context.list_devices(subsystem='block', DEVTYPE='disk') if device.attributes.asstring('removable') == "1"]
    else:
        disks = [device for device in context.list_devices(subsystem='block', DEVTYPE='disk')]

    raw_partitions = context.list_devices(subsystem='block', DEVTYPE='partition')
    return_partitions = OrderedDict()

    for device in disks:
        partitions = [device.device_node for device in context.list_devices(subsystem='block', DEVTYPE='partition', parent=device)]

        for ipartition in partitions:
            if ipartition not in return_partitions:
                return_partitions[ipartition] = {
                    'mountpoint': None,
                    'internal_mountpoint': os.path.join(
                        OWN_MOUNT_POINT_PREFIX,
                        get_relative_path(ipartition)
                    ),
                    'removable': device.attributes.asstring('removable') == '1',
                    'label': get_partition_label(raw_partitions, ipartition, '')
                }

        for p in psutil.disk_partitions():
            if p.device in partitions:
                return_partitions[p.device]['mountpoint'] = p.mountpoint

    return return_partitions


def mount_partitions(partitions: dict) -> list:
    # just mount new removable drives (as partitions)
    mounted = []

    for key, value in partitions.items():
        if not value['removable'] or value['mountpoint']:
            continue

        print('Mounting ' + key + ' as ' + value['internal_mountpoint'])

        os.makedirs(value['internal_mountpoint'], exist_ok=True)
        sh.fsck('-y', key)
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
        print('  removable: ' + str(value['removable']))
        print('  label: ' + str(value['label']))

        print()


def eject_unmounted(partitions: dict, old_partitions: dict):
    # eject all ADFs that file-system is unmounted
    # but was mounted before
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


def insert_mounted_floppy(ipartition: str, ipartition_data, force: Optional[bool] = False):
    new_mounted = False

    if not old_partitions:
        new_mounted = True

    if not new_mounted:
        if ipartition not in old_partitions:
            new_mounted = True

        if not new_mounted:
            for key2, value2 in old_partitions.items():
                if key2 == ipartition and not value2['mountpoint']:
                    new_mounted = True
                    break

    if force:
        new_mounted = True

    if new_mounted:
        print('New mounted ' + ipartition)

        assign_floppy_from_mountpoint(ipartition_data['mountpoint'])

        return True

    return False


def insert_mounted(partitions: dict, old_partitions: dict, force: Optional[bool] = False):
    # detect new mounted partition and insert ADF
    # if it is present
    for key, value in partitions.items():
        if not value['mountpoint']:
            continue

        if value['label'].startswith('BM_DF'):
            if insert_mounted_floppy(key, value, force):
                break


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


partitions = get_partitions(True)
print_partitions(partitions)

insert_mounted(partitions, None, True)
generate_mount_table()
send_SIGUSR1_signal()

while True:
    partitions = get_partitions(True)

    if not old_partitions or str(old_partitions) != str(partitions):
        # something new
        if old_partitions:
            eject_unmounted(partitions, old_partitions)
            insert_mounted(partitions, old_partitions)
            generate_mount_table()
            send_SIGUSR1_signal()
            mount_partitions(partitions)

    time.sleep(0.5)

    old_partitions = partitions
