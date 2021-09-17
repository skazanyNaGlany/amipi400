import sys
import os

assert sys.platform == 'linux', 'This script must be run only on Linux'
assert sys.version_info.major >= 3 and sys.version_info.minor >= 5, 'This script requires Python 3.5+'
assert os.geteuid() == 0, 'This script must be run as root'

try:
    import sh
    import time
    import tempfile
    import re
    import subprocess
    import logzero
    import numpy

    from collections import OrderedDict
    from io import StringIO
    from typing import Optional, List
except ImportError as xie:
    print(str(xie))
    sys.exit(1)


APP_UNIXNAME = 'amiga_disk_devices'
APP_VERSION = '0.1'
TMP_PATH_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
LOG_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'amiga_disk_devices.log')
ENABLE_LOGGER = False
SYNC_DISKS_SECS = 60 * 3
FLOPPY_EXTENSIONS = ['*.adf']
AMIGA_DEV_TYPE_FLOPPY = 1
FLOPPY_DEVICE_SIZE = 1474560
ADF_BOOTBLOCK = numpy.dtype([
    ('DiskType',    numpy.byte,     (4, )   ),
    ('Chksum',      numpy.uint32            ),
    ('Rootblock',   numpy.uint32            )
])


def print_log(*args):
    if ENABLE_LOGGER:
        if args:
            logzero.logger.info(*args)
    else:
        print(*args)


def init_logger():
    if not ENABLE_LOGGER:
        return

    print('Logging to ' + LOG_PATHNAME)

    logzero.logfile(LOG_PATHNAME, maxBytes=1e6, backupCount=3, disableStderrLogger=True)


def print_app_version():
    print('{name} v{version}'. format(
        name=APP_UNIXNAME.upper(),
        version=APP_VERSION
    ))


def check_pre_requirements():
    check_system_binaries()


def configure_system():
    print_log('Configuring system')


def check_system_binaries():
    print_log('Checking system binaries')

    bins = [
        'lsblk',
        'clear'
    ]

    for ibin in bins:
        if not sh.which(ibin):
            print_log(ibin + ': command not found')
            sys.exit(1)


def other_actions():
    if ENABLE_LOGGER:
        # logger enabled so clear the console
        os.system('clear')


def is_sync_running(sync_process) -> bool:
    if not sync_process:
        return False

    if sync_process.poll() is None:
        return True

    sync_process = None

    return False


def sync(sync_disks_ts: int, sync_process):
    if is_sync_running(sync_process):
        return sync_disks_ts, sync_process

    current_ts = int(time.time())

    if not sync_disks_ts:
        sync_disks_ts = current_ts

    if current_ts - sync_disks_ts < SYNC_DISKS_SECS:
        return sync_disks_ts, sync_process

    print_log('Syncing disks')

    sync_process = subprocess.Popen('sync')
    sync_disks_ts = current_ts

    return sync_disks_ts, sync_process


def get_partitions2() -> OrderedDict:
    lsblk_buf = StringIO()
    pattern = r'NAME="(\w*)" SIZE="(\d*)" TYPE="(\w*)" MOUNTPOINT="(.*)" LABEL="(.*)" PATH="(.*)"'
    ret = OrderedDict()

    # lsblk -P -o name,size,type,mountpoint,label,path -n -b
    sh.lsblk('-P', '-o', 'name,size,type,mountpoint,label,path', '-n', '-b', _out=lsblk_buf)

    for line in lsblk_buf.getvalue().splitlines():
        line = line.strip()

        if not line:
            continue

        search_result = re.search(pattern, line)

        if not search_result:
            continue

        found = search_result.groups()

        full_path = found[5]
        device_data = {
            'mountpoint': found[3],
            'label': found[4],
            'config': None,
            'device': full_path,
            'is_floppy_drive': False,
            'size': int(found[1]) if found[1] else 0,
            'type': found[2]
        }

        ret[full_path] = device_data

    return ret


def print_partitions(partitions: dict):
    if not partitions:
        return

    print_log('Known partitions:')

    for key, value in partitions.items():
        print_log(key)

        print_log('  mountpoint: ' + str(value['mountpoint']))
        print_log('  label: ' + str(value['label']))
        print_log('  is_floppy_drive: ' + str(value['is_floppy_drive']))
        print_log('  size: ' + str(value['size']))
        print_log('  type: ' + str(value['type']))

        print_log()


def cleanup_disk_devices(partitions: dict, disk_devices: dict):
    for ipart_dev in list(disk_devices.keys()):
        if ipart_dev not in partitions:
            del disk_devices[ipart_dev]


def add_disk_devices(partitions: dict, disk_devices: dict):
    for ipart_dev, ipart_data in partitions.items():
        if ipart_dev in disk_devices:
            continue

        if ipart_data['type'] != 'disk':
            continue

        if ipart_data['size'] != FLOPPY_DEVICE_SIZE:
            continue

        header = read_file_header(ipart_dev)

        if not header or len(header) < 512:
            print_log('Cannot read header from {filename}'.format(
                filename=ipart_dev
            ))

            continue

        if is_adf_header(header):
            print_log('{filename} seems to be ADF'.format(
                filename=ipart_dev
            ))

            disk_devices[ipart_dev] = ipart_data.copy()
            disk_devices[ipart_dev]['amiga_device_type'] = AMIGA_DEV_TYPE_FLOPPY


def is_adf_header(header: bytes) -> bool:
    # TODO provide better method to detect ADF header
    parsed_header = numpy.frombuffer(header, ADF_BOOTBLOCK, 1)[0]

    disk_type = parsed_header['DiskType'].tobytes().decode('ascii', 'ignore').rstrip('\0')

    if disk_type != 'DOS':
        return False

    disk_type_other_bits = clear_bits(
        parsed_header['DiskType'][3],
        [0, 1, 2]
    )

    if disk_type_other_bits != 0:
        return False

    if parsed_header['Rootblock'] not in [0, 880]:
        return False

    return True


def clear_bits(i: int, bits: list) -> int:
    for ibit in bits:
        i = i & ~(1<<ibit)

    return i


def read_file_header(filename: str) -> Optional[bytes]:
    with open(filename, 'rb') as f:
        return f.read(512)


def update_disk_devices(partitions: dict, disk_devices: dict):
    cleanup_disk_devices(partitions, disk_devices)
    add_disk_devices(partitions, disk_devices)


def main():
    partitions = None
    old_partitions = None
    sync_disks_ts = 0
    sync_process = None
    disk_devices = {}

    os.makedirs(TMP_PATH_PREFIX, exist_ok=True)

    print_app_version()
    init_logger()
    check_pre_requirements()
    configure_system()

    while True:
        partitions = get_partitions2()

        if partitions != old_partitions:
            # something changed
            print_partitions(partitions)
            update_disk_devices(partitions, disk_devices)

        old_partitions = partitions

        other_actions()
        sync_disks_ts, sync_process = sync(sync_disks_ts, sync_process)

        time.sleep(1)

if __name__ == '__main__':
    main()
