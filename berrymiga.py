import pyudev
import psutil
import sh
import time
import os
import tempfile
import sys

from pprint import pprint
from collections import OrderedDict


APP_UNIXNAME = 'berrymiga'
OWN_MOUNT_POINT_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
FS_UAE_PATHNAME = '/home/sng/projects.local/fs-uae.devbox/src/fs-uae/fs-uae'


os.makedirs(OWN_MOUNT_POINT_PREFIX, exist_ok=True)

context = pyudev.Context()
old_partitions = None


def get_relative_path(pathname: str) -> str:
    if pathname[0] == os.path.sep:
        return pathname[1:]

    return pathname


def get_removable_partitions() -> OrderedDict:
    # devices = [device for device in context.list_devices(subsystem='block', DEVTYPE='disk') if device.attributes.asstring('removable') == "1"]
    devices = [device for device in context.list_devices(subsystem='block', DEVTYPE='disk')]
    removable = OrderedDict()

    for device in devices:
        partitions = [device.device_node for device in context.list_devices(subsystem='block', DEVTYPE='partition', parent=device)]

        for ipartition in partitions:
            if ipartition not in removable:
                removable[ipartition] = {
                    'mountpoint': None,
                    'internal_mountpoint': os.path.join(
                        OWN_MOUNT_POINT_PREFIX,
                        get_relative_path(ipartition)
                    ),
                    'removable': device.attributes.asstring('removable') == '1'
                }

        for p in psutil.disk_partitions():
            if p.device in partitions:
                removable[p.device]['mountpoint'] = p.mountpoint

    return removable


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


def print_removables(removables: dict):
    if not removables:
        return

    print('File systems:')

    for key, value in removables.items():
        print(key)

        print('  mountpoint: ' + str(value['mountpoint']))
        print('  internal_mountpoint: ' + value['internal_mountpoint'])
        print('  removable: ' + str(value['removable']))

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


def insert_mounted(partitions: dict, old_partitions: dict):
    # detect new mounted partition and insert ADF
    # if it is present
    for key, value in partitions.items():
        if not value['mountpoint']:
            continue

        new_mounted = False

        if key not in old_partitions:
            new_mounted = True

        if not new_mounted:
            for key2, value2 in old_partitions.items():
                if key2 == key and not value2['mountpoint']:
                    new_mounted = True
                    break

        if new_mounted:
            print('New mounted ' + key)


while True:
    partitions = get_removable_partitions()

    if not old_partitions or str(old_partitions) != str(partitions):
        # something new
        if old_partitions:
            eject_unmounted(partitions, old_partitions)
            insert_mounted(partitions, old_partitions)
            mount_partitions(partitions)

    time.sleep(0.5)

    old_partitions = partitions
