from errno import EINVAL, EIO
from stat import filemode
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
    import threading
    import time
    import logging

    from collections import OrderedDict
    from io import StringIO
    from typing import Optional, List
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
    from errno import ENOENT
    from stat import S_IFDIR, S_IFREG
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
MAIN_LOOP_MAX_COUNTER = 0
# MAIN_LOOP_MAX_COUNTER = 1

fs_instance = None

class AmigaDiskDevicesFS(LoggingMixIn, Operations):
    def __init__(self, disk_devices: dict):
        self._now = time.time()
        self._disk_devices = disk_devices
        self._static_files = {
            '/': dict(
                st_mode=(S_IFDIR | 0o444),
                st_ctime=self._now,
                st_mtime=self._now,
                st_atime=self._now,
                st_nlink=2,
                st_size=4096
            )
        }
        self._handles = {}
        self._mutex = threading.Lock()


    access = None
    flush = None
    getxattr = None
    listxattr = None
    open = None
    opendir = None
    release = None
    releasedir = None
    statfs = None


    def set_disk_devices(self, disk_devices: dict):
        self._disk_devices = disk_devices

        self._flush_handles()


    def _flush_handles(self):
        for device_pathname in list(self._handles.keys()):
            if device_pathname not in self._disk_devices:
                self._close_handle(device_pathname)


    def _close_handles(self):
        for device_pathname in self._handles.keys():
            self._close_handle(device_pathname)


    def _close_handle(self, device_pathname: str) -> Optional[int]:
        with self._mutex:
            handle = self._handles[device_pathname]

            try:
                os.close(handle)
            except:
                pass

            del self._handles[device_pathname]


    def _open_handle(self, device_pathname: str) -> Optional[int]:
        with self._mutex:
            if device_pathname in self._handles:
                return self._handles[device_pathname]

            try:
                self._handles[device_pathname] = os.open(device_pathname, os.O_RDWR | os.O_SYNC)
            except:
                return None

            return self._handles[device_pathname]


    def _find_file(self, public_name: str) -> Optional[dict]:
        for ipart_dev, ipart_data in self._disk_devices.items():
            if ipart_data['public_name'] == public_name:
                return ipart_data

        return None


    def _get_file_size(self, ipart_data: dict) -> int:
        if ipart_data['amiga_device_type'] == AMIGA_DEV_TYPE_FLOPPY:
            return 901120

        return 0


    def _clear_pathname(self, pathname: str) -> str:
        if pathname.startswith(os.path.sep):
            pathname = pathname[1:]

        return pathname


    def getattr(self, path, fh=None):
        self._flush_handles()

        if path in self._static_files:
            return self._static_files[path]

        name = self._clear_pathname(path)

        ipart_data = self._find_file(name)

        if not ipart_data:
            raise FuseOSError(ENOENT)

        now = time.time()

        return dict(st_mode=(S_IFREG | 0o444),
                    st_nlink=1,
                    st_size=self._get_file_size(ipart_data),
                    st_ctime=now,
                    st_mtime=now,
                    st_atime=now)


    def read(self, path, size, offset, fh):
        self._flush_handles()

        name = self._clear_pathname(path)

        ipart_data = self._find_file(name)

        if not ipart_data:
            raise FuseOSError(ENOENT)

        file_size = self._get_file_size(ipart_data)

        if offset + size > file_size:
            size = file_size - offset

        if offset >= file_size or size <= 0:
            return b''

        handle = self._open_handle(ipart_data['device'])

        if handle is None:
            raise FuseOSError(EIO)

        os.lseek(handle, offset, os.SEEK_SET)

        return os.read(handle, size)


    def readdir(self, path, fh):
        self._flush_handles()

        entries = [
            '.',
            '..'
        ]

        if path != '/':
            return entries

        for ipart_dev, ipart_data in self._disk_devices.items():
            entries.append(
                ipart_data['public_name']
            )

        return entries


    def destroy(self, path):
        self._close_handles()


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

    disable_swap()
    set_cache_pressure()


def disable_swap():
    print_log('Disable swap')
    os.system('swapoff -a')


def set_cache_pressure():
    print_log('Set cache pressure')
    os.system('sysctl -q vm.vfs_cache_pressure=200')


def check_system_binaries():
    print_log('Checking system binaries')

    bins = [
        'lsblk',
        'sysctl',
        'swapoff',
        'clear',
        'blockdev'
    ]

    for ibin in bins:
        if not sh.which(ibin):
            print_log(ibin + ': command not found')
            sys.exit(1)


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


def device_get_public_name(ipart_data: dict):
    pathname = ipart_data['device'].replace(os.path.sep, '__')

    if ipart_data['amiga_device_type'] == AMIGA_DEV_TYPE_FLOPPY:
        pathname += '.adf'

    return pathname


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
            disk_devices[ipart_dev]['public_name'] = device_get_public_name(disk_devices[ipart_dev])

            set_device_read_a_head_sectors(ipart_dev, 0)


def set_device_read_a_head_sectors(device: str, sectors: int):
    print_log('Setting read-a-head on {pathname} to {sectors} sectors'.format(
        pathname=device,
        sectors=sectors
    ))

    os.system('blockdev --setra {sectors} {device}'.format(
        sectors=sectors,
        device=device
    ))


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


def run_fuse(disk_devices: dict):
    global fs_instance

    fs_instance = AmigaDiskDevicesFS(disk_devices)

    FUSE(fs_instance, TMP_PATH_PREFIX, foreground=True, allow_other=True, direct_io=True)


def init_fuse(disk_devices: dict):
    print_log('Init FUSE')

    fuse_instance_thread = threading.Thread(target=run_fuse, args=(disk_devices,))
    fuse_instance_thread.start()

    return fuse_instance_thread


def unmount_fuse_mountpoint():
    print_log('Unmounting FUSE mountpoint')

    os.system('umount {dir}'.format(
        dir=TMP_PATH_PREFIX
    ))


def affect_fs_disk_devices(disk_devices: dict):
    global fs_instance

    if not fs_instance:
        return

    fs_instance.set_disk_devices(disk_devices)


def main():
    partitions = None
    old_partitions = None
    sync_disks_ts = 0
    sync_process = None
    disk_devices = {}
    loop_counter = 0

    os.makedirs(TMP_PATH_PREFIX, exist_ok=True)

    print_app_version()
    init_logger()
    # logging.basicConfig(level=logging.DEBUG)
    check_pre_requirements()
    configure_system()
    init_fuse(disk_devices)

    try:
        while True:
            if not MAIN_LOOP_MAX_COUNTER or loop_counter < MAIN_LOOP_MAX_COUNTER:
                partitions = get_partitions2()

                if partitions != old_partitions:
                    # something changed
                    print_partitions(partitions)
                    update_disk_devices(partitions, disk_devices)
                    affect_fs_disk_devices(disk_devices)

                old_partitions = partitions
                sync_disks_ts, sync_process = sync(sync_disks_ts, sync_process)
                loop_counter += 1

            time.sleep(1)
    except KeyboardInterrupt as ex:
        print_log('KeyboardInterrupt')

    unmount_fuse_mountpoint()

    sys.exit()

if __name__ == '__main__':
    main()
