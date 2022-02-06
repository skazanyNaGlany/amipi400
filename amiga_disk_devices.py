from errno import EINVAL, EIO, ENOSPC, EROFS
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
    from typing import Optional, List, Dict
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
    from errno import ENOENT
    from stat import S_IFDIR, S_IFREG
    from pynput.keyboard import Key, Listener
    from array import array
except ImportError as xie:
    print(str(xie))
    sys.exit(1)


APP_UNIXNAME = 'amiga_disk_devices'
APP_VERSION = '0.1'
TMP_PATH_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
LOG_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'amiga_disk_devices.log')
ENABLE_LOGGER = False
ENABLE_REINIT_HANDLE_AFTER_SECS = 64 * 4
DISABLE_SWAP = False
SYNC_DISKS_SECS = 60 * 3
AMIGA_DISK_DEVICE_TYPE_ADF = 1
AMIGA_DISK_DEVICE_TYPE_HDF_HDFRDB = 8
AMIGA_DISK_DEVICE_TYPE_HDF_DISKIMAGE = 2
AMIGA_DISK_DEVICE_TYPE_HDF = 5
AMIGA_DISK_DEVICE_TYPE_ISO = 10
FLOPPY_DEVICE_SIZE = 1474560
FLOPPY_ADF_SIZE = 901120
FLOPPY_ADF_EXTENSION = '.adf'
HD_HDF_EXTENSION = '.hdf'
CD_ISO_EXTENSION = '.iso'
ADF_BOOTBLOCK = numpy.dtype([
    ('DiskType',    numpy.byte,     (4, )   ),
    ('Chksum',      numpy.uint32            ),
    ('Rootblock',   numpy.uint32            )
])
MAIN_LOOP_MAX_COUNTER = 0


fs_instance = None
key_ctrl_pressed = False
key_shift_pressed = False


class AmigaDiskDevicesFS(LoggingMixIn, Operations):
    _handles: Dict[str, int]
    _access_times: Dict[str, float]
    _modification_times: Dict[str, float]

    def __init__(self, disk_devices: dict):
        self._instance_time = time.time()
        self._disk_devices = disk_devices
        self._static_files = {
            '/': dict(
                st_mode=(S_IFDIR | 0o444),
                st_ctime=self._instance_time,
                st_mtime=self._instance_time,
                st_atime=self._instance_time,
                st_nlink=2,
                st_size=4096
            )
        }
        self._handles = {}
        self._mutex = threading.Lock()
        self._access_times = {}
        self._modification_times = {}
        self._last_write_ts = 0


    access = None
    flush = None
    getxattr = None
    listxattr = None
    open = None
    opendir = None
    release = None
    releasedir = None
    statfs = None


    def get_last_write_ts(self):
        return self._last_write_ts


    def clear_last_write_ts(self):
        self._last_write_ts = 0


    def sync_handles(self):
        for device_pathname in list(self._handles.keys()):
            handle = self._handles[device_pathname]

            os.fsync(handle)


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


    def _close_handle(self, device_pathname: str):
        with self._mutex:
            try:
                handle = self._handles[device_pathname]

                os.close(handle)
            except:
                pass

            try:
                del self._handles[device_pathname]
            except:
                pass

            try:
                del self._access_times[device_pathname]
            except:
                pass

            try:
                del self._modification_times[device_pathname]
            except:
                pass


    def _open_handle(self, ipart_data: dict) -> Optional[int]:
        with self._mutex:
            device_pathname = ipart_data['device']

            if device_pathname in self._handles:
                return self._handles[device_pathname]

            is_readable = ipart_data['is_readable']
            is_writable = ipart_data['is_writable']

            mode = os.O_SYNC | os.O_DSYNC | os.O_RSYNC

            if is_readable and is_writable:
                mode |= os.O_RDWR
            else:
                mode |= os.O_RDONLY

            try:
                self._handles[device_pathname] = os.open(device_pathname, mode)
            except:
                return None

            os.posix_fadvise(
                self._handles[device_pathname],
                0,
                ipart_data['size'] - 1,
                os.POSIX_FADV_DONTNEED
            )

            return self._handles[device_pathname]


    def _find_file(self, public_name: str) -> Optional[dict]:
        for ipart_dev, ipart_data in self._disk_devices.items():
            if ipart_data['public_name'] == public_name:
                return ipart_data

        return None


    def _save_file_access_time(self, device_pathname: str) -> float:
        current_time = time.time()

        self._access_times[device_pathname] = current_time

        return current_time


    def _save_file_modification_time(self, device_pathname: str) -> float:
        current_time = time.time()

        self._modification_times[device_pathname] = current_time
        self._last_write_ts = current_time

        return current_time


    def _get_file_access_time(self, device: str) -> float:
        try:
            return self._access_times[device]
        except:
            return self._save_file_access_time(device)


    def _get_file_modification_time(self, device: str) -> float:
        try:
            return self._modification_times[device]
        except:
            return self._save_file_modification_time(device)


    def _clear_pathname(self, pathname: str) -> str:
        if pathname.startswith(os.path.sep):
            pathname = pathname[1:]

        return pathname


    def _genrate_perm_int_mask(self,
        user_can_read: bool,
        user_can_write: bool,
        user_can_execute: bool,
        group_can_read: bool,
        group_can_write: bool,
        group_can_execute: bool,
        other_can_read: bool,
        other_can_write: bool,
        other_can_execute: bool
        ) -> int:
        bin_string = ''

        bin_string += str(int(user_can_read))
        bin_string += str(int(user_can_write))
        bin_string += str(int(user_can_execute))
        bin_string += str(int(group_can_read))
        bin_string += str(int(group_can_write))
        bin_string += str(int(group_can_execute))
        bin_string += str(int(other_can_read))
        bin_string += str(int(other_can_write))
        bin_string += str(int(other_can_execute))

        return int(bin_string, 2)


    def getattr(self, path, fh=None):
        self._flush_handles()

        if path in self._static_files:
            return self._static_files[path]

        name = self._clear_pathname(path)

        ipart_data = self._find_file(name)

        if not ipart_data:
            raise FuseOSError(ENOENT)

        access_time = self._get_file_access_time(ipart_data['device'])
        modification_time = self._get_file_modification_time(ipart_data['device'])

        is_readable = ipart_data['is_readable']
        is_writable = ipart_data['is_writable']

        perm_int_mask = self._genrate_perm_int_mask(
            is_readable, is_writable, False,
            is_readable, is_writable, False,
            is_readable, is_writable, False
        )

        return dict(st_mode=(S_IFREG | perm_int_mask),
                    st_nlink=1,
                    st_size=ipart_data['size'],
                    st_ctime=self._instance_time,
                    st_atime=access_time,
                    st_mtime=modification_time
                )


    def _reinit_handle(self, ipart_data):
        if not ENABLE_REINIT_HANDLE_AFTER_SECS:
            return

        if ipart_data['amiga_device_type'] != AMIGA_DISK_DEVICE_TYPE_ADF:
            return

        current_time = time.time()
        access_time = self._get_file_access_time(ipart_data['device'])

        if current_time - access_time >= ENABLE_REINIT_HANDLE_AFTER_SECS:
            self._close_handle(ipart_data['device'])


    def read(self, path, size, offset, fh):
        self._flush_handles()

        name = self._clear_pathname(path)
        ipart_data = self._find_file(name)

        if not ipart_data:
            raise FuseOSError(ENOENT)

        self._reinit_handle(ipart_data)
        self._save_file_access_time(ipart_data['device'])

        file_size = ipart_data['size']

        if offset + size > file_size:
            size = file_size - offset

        if offset >= file_size or size <= 0:
            self._save_file_access_time(ipart_data['device'])

            return b''

        handle = self._open_handle(ipart_data)

        if handle is None:
            self._save_file_access_time(ipart_data['device'])

            raise FuseOSError(EIO)

        ex = None
        to_read_size = size
        all_data = bytes()

        os.lseek(handle, offset, os.SEEK_SET)

        while to_read_size > 0:
            try:
                self._save_file_access_time(ipart_data['device'])

                data = os.read(handle, 512)
                len_data = len(data)

                all_data += data
                to_read_size -= len_data

                if len_data < 512:
                    break
            except Exception as x:
                ex = x

                break

        self._save_file_access_time(ipart_data['device'])

        if ex is not None:
            raise ex

        return all_data


    def truncate(self, path, length, fh=None):
        # block devices cannot be truncated, so just return
        return


    def write(self, path, data, offset, fh):
        self._flush_handles()

        name = self._clear_pathname(path)
        ipart_data = self._find_file(name)

        if not ipart_data:
            raise FuseOSError(ENOENT)

        if not ipart_data['is_writable']:
            raise FuseOSError(EROFS)

        self._save_file_modification_time(ipart_data['device'])

        max_file_size = ipart_data['size']
        len_data = len(data)

        if offset + len_data > max_file_size or offset >= max_file_size:
            self._save_file_modification_time(ipart_data['device'])

            raise FuseOSError(ENOSPC)

        if len_data == 0:
            self._save_file_modification_time(ipart_data['device'])

            return b''

        handle = self._open_handle(ipart_data)

        if handle is None:
            self._save_file_modification_time(ipart_data['device'])

            raise FuseOSError(EIO)

        os.lseek(handle, offset, os.SEEK_SET)

        ex = None

        try:
            result = os.write(handle, data)
        except Exception as x:
            ex = x

        self._save_file_modification_time(ipart_data['device'])

        if ex is not None:
            raise ex

        return result


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
    if not DISABLE_SWAP:
        return

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
        'blockdev',
        'umount'
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


def is_device_physical_floppy(
    device_pathname: str,
    device_data: dict,
    physical_floppy_drives: dict
) -> bool:
    return (
        device_pathname in physical_floppy_drives
    ) and \
    device_data['type'] == 'disk' and \
    device_data['size'] == FLOPPY_DEVICE_SIZE


def is_device_physical_cdrom(
    device_pathname: str,
    device_data: dict,
    physical_cdrom_drives: dict
) -> bool:
    return (
        device_pathname in physical_cdrom_drives
    ) and device_data['type'] == 'rom'


def is_device_physical_disk(device_data: dict) -> bool:
    return (
        not device_data['is_floppy_drive'] and
        not device_data['is_cdrom_drive']
    ) and device_data['type'] == 'disk'


def get_partitions2(physical_cdrom_drives, physical_floppy_drives) -> 'OrderedDict[str, dict]':
    lsblk_buf = StringIO()
    pattern = r'NAME="(\w*)" SIZE="(\d*)" TYPE="(\w*)" MOUNTPOINT="(.*)" LABEL="(.*)" PATH="(.*)" FSTYPE="(.*)" PTTYPE="(.*)" RO="(.*)"'
    ret: OrderedDict[str, dict] = OrderedDict()

    # lsblk -P -o name,size,type,mountpoint,label,path,fstype,pttype,ro -n -b
    sh.lsblk('-P', '-o', 'name,size,type,mountpoint,label,path,fstype,pttype,ro', '-n', '-b', _out=lsblk_buf)

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
            'device_basename': os.path.basename(full_path),
            'is_floppy_drive': False,
            'is_cdrom_drive': False,
            'is_disk_drive': False,
            'size': int(found[1]) if found[1] else 0,
            'type': found[2],
            'fstype': found[6],
            'pttype': found[7],
            'is_readable': True,    # in Linux device is reabable by default
            'is_writable': bool(int(found[8])) == False
        }

        device_data['is_floppy_drive'] = is_device_physical_floppy(
            full_path,
            device_data,
            physical_floppy_drives
        )
        device_data['is_cdrom_drive'] = is_device_physical_cdrom(
            full_path,
            device_data,
            physical_cdrom_drives
        )
        device_data['is_disk_drive'] = is_device_physical_disk(
            device_data
        )

        if device_data['is_cdrom_drive']:
            device_data['is_writable'] = False

            if is_unknown_disk(device_data):
                # do not add unknown cd/dvd
                continue

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
        print_log('  is_cdrom_drive: ' + str(value['is_cdrom_drive']))
        print_log('  is_disk_drive: ' + str(value['is_disk_drive']))
        print_log('  size: ' + str(value['size']))
        print_log('  type: ' + str(value['type']))

        print_log()


def device_get_public_name(ipart_data: dict):
    pathname = ipart_data['device'].replace(os.path.sep, '__')

    if ipart_data['amiga_device_type'] == AMIGA_DISK_DEVICE_TYPE_ADF:
        pathname += FLOPPY_ADF_EXTENSION
    elif ipart_data['amiga_device_type'] == AMIGA_DISK_DEVICE_TYPE_HDF_DISKIMAGE or \
        ipart_data['amiga_device_type'] == AMIGA_DISK_DEVICE_TYPE_HDF_HDFRDB:
        pathname += HD_HDF_EXTENSION
    if ipart_data['amiga_device_type'] == AMIGA_DISK_DEVICE_TYPE_ISO:
        pathname += CD_ISO_EXTENSION

    return pathname


def get_hdf_type(pathname: str) -> int:
    file_stat = os.stat(pathname)

    with open(pathname, 'rb') as file:
        data = array('B', file.read(512))

        char_0 = chr(data[0])
        char_1 = chr(data[1])
        char_2 = chr(data[2])
        char_3 = chr(data[3])

        first_4_chars = ''.join([char_0, char_1, char_2, char_3])

        if first_4_chars == 'RDSK':
            return AMIGA_DISK_DEVICE_TYPE_HDF_HDFRDB
        elif first_4_chars.startswith('DOS'):
            if file_stat.st_size < 4 * 1024 * 1024:
                return AMIGA_DISK_DEVICE_TYPE_HDF_DISKIMAGE
            else:
                return AMIGA_DISK_DEVICE_TYPE_HDF

    return None


def hdf_type_to_str(hdf_type: int):
    if hdf_type == AMIGA_DISK_DEVICE_TYPE_HDF_HDFRDB:
        return 'RDSK'
    elif hdf_type == AMIGA_DISK_DEVICE_TYPE_HDF_DISKIMAGE:
        return 'DISKIMAGE'
    elif hdf_type == AMIGA_DISK_DEVICE_TYPE_HDF:
        return 'HDF'

    return None


def fix_disk_devices(partitions: dict, disk_devices: dict):
    count_removed = 0

    for device_pathname, device_data in disk_devices.copy().items():
        if device_pathname not in partitions:
            continue

        ipart_data = partitions[device_pathname]

        if not is_unknown_disk(ipart_data) and not ipart_data['is_cdrom_drive']:
            print_log(device_pathname, 'removing incorrectly added device')

            del disk_devices[device_pathname]
            count_removed += 1

    return count_removed


def cleanup_disk_devices(partitions: dict, disk_devices: dict):
    for ipart_dev in list(disk_devices.keys()):
        if ipart_dev not in partitions:
            del disk_devices[ipart_dev]

            print_log(ipart_dev, 'ejected')


def add_adf_disk_device(ipart_dev: str, ipart_data: dict, disk_devices: dict):
    print_log('{filename} using as ADF'.format(
        filename=ipart_dev
    ))

    set_device_read_a_head_sectors(ipart_dev, 0)

    disk_devices[ipart_dev] = ipart_data.copy()
    disk_devices[ipart_dev]['amiga_device_type'] = AMIGA_DISK_DEVICE_TYPE_ADF
    disk_devices[ipart_dev]['public_name'] = device_get_public_name(disk_devices[ipart_dev])
    disk_devices[ipart_dev]['size'] = FLOPPY_ADF_SIZE


def add_hdf_disk_device(ipart_dev: str, ipart_data: dict, disk_devices: dict, _type: int):
    print_log('{filename} using as HDF'.format(
        filename=ipart_dev
    ))

    disk_devices[ipart_dev] = ipart_data.copy()
    disk_devices[ipart_dev]['amiga_device_type'] = _type
    disk_devices[ipart_dev]['public_name'] = device_get_public_name(disk_devices[ipart_dev])


def add_bigger_disk_device(ipart_dev: str, ipart_data: dict, disk_devices: dict):
    hdf_type = get_hdf_type(ipart_dev)

    if not hdf_type:
        # could be iso
        print_log('{filename} cannot determine disk device type, using DISKIMAGE by default'.format(
            filename=ipart_dev
        ))

        hdf_type = AMIGA_DISK_DEVICE_TYPE_HDF_DISKIMAGE

    if hdf_type != AMIGA_DISK_DEVICE_TYPE_HDF_DISKIMAGE and \
        hdf_type != AMIGA_DISK_DEVICE_TYPE_HDF_HDFRDB and \
        hdf_type != AMIGA_DISK_DEVICE_TYPE_HDF:
        print_log('{filename} {_type} is not supported'.format(
            filename=ipart_dev,
            _type=hdf_type_to_str(hdf_type)
        ))

        return

    add_hdf_disk_device(ipart_dev, ipart_data, disk_devices, hdf_type)


def add_iso_disk_device(ipart_dev: str, ipart_data: dict, disk_devices: dict):
    print_log('{filename} using as ISO'.format(
        filename=ipart_dev
    ))

    disk_devices[ipart_dev] = ipart_data.copy()
    disk_devices[ipart_dev]['amiga_device_type'] = AMIGA_DISK_DEVICE_TYPE_ISO
    disk_devices[ipart_dev]['public_name'] = device_get_public_name(disk_devices[ipart_dev])


def is_unknown_disk(ipart_data: dict) -> bool:
    return ipart_data['fstype'] == '' and ipart_data['pttype'] == ''


def add_disk_devices2(partitions: dict, disk_devices: dict):
    for ipart_dev, ipart_data in partitions.items():
        if ipart_dev in disk_devices:
            continue

        unknown = is_unknown_disk(ipart_data)

        if ipart_data['is_floppy_drive']:
            if not unknown:
                continue

            add_adf_disk_device(ipart_dev, ipart_data, disk_devices)
        elif ipart_data['is_disk_drive']:
            if not unknown:
                continue

            add_bigger_disk_device(ipart_dev, ipart_data, disk_devices)
        elif ipart_data['is_cdrom_drive']:
            add_iso_disk_device(ipart_dev, ipart_data, disk_devices)


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
    add_disk_devices2(partitions, disk_devices)


def run_fuse(disk_devices: dict):
    global fs_instance

    fs_instance = AmigaDiskDevicesFS(disk_devices)

    FUSE(
        fs_instance,
        TMP_PATH_PREFIX,
        foreground=True,
        allow_other=True,
        direct_io=True
    )


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


def mkdir_fuse_mountpoint():
    os.makedirs(TMP_PATH_PREFIX, exist_ok=True)


def affect_fs_disk_devices(disk_devices: dict):
    global fs_instance

    if not fs_instance:
        return

    fs_instance.set_disk_devices(disk_devices.copy())


def set_device_read_a_head_sectors(device: str, sectors: int):
    os.system('blockdev --setra {sectors} {device}'.format(
        sectors=sectors,
        device=device
    ))


def find_new_devices(partitions: dict, old_partitions: dict) -> List[str]:
    new_devices = []

    for ipart_dev, ipart_data in partitions.items():
        if not old_partitions or ipart_dev not in old_partitions:
            new_devices.append(ipart_dev)

    return new_devices


def is_ctrl_shift_pressed() -> bool:
    return key_ctrl_pressed and key_shift_pressed


def clear_pressed_keys():
    global key_ctrl_pressed
    global key_shift_pressed

    key_ctrl_pressed = False
    key_shift_pressed = False


def quick_format_single_device(device: str):
    try:
        with open(device, 'wb') as f:
            f.write(bytes(1024))
            f.flush()
    except OSError as ex:
        print_log(str(ex))

        return False

    return True


def rescan_device(device_basename: str):
    os.system('echo 1 > /sys/class/block/{device_basename}/device/rescan'.format(
        device_basename=device_basename
    ))


def format_devices(partitions: dict, old_partitions: dict, loop_counter: int):
    if not is_ctrl_shift_pressed():
        return

    clear_pressed_keys()

    if not loop_counter:
        # do not format on first iteration
        return

    new_devices = find_new_devices(partitions, old_partitions)

    if not new_devices:
        return

    to_format = []

    for ipart_dev in new_devices:
        ipart_data = partitions[ipart_dev]

        if ipart_data['type'] != 'disk':
            continue

        if not ipart_data['is_writable']:
            continue

        print_log(ipart_dev, 'new')
        print_log(ipart_dev, 'quick-formatting device')

        to_format.append(ipart_dev)

        # only one disk device at a time
        break

    if not to_format:
        return

    ipart_dev = to_format[0]

    if quick_format_single_device(ipart_dev):
        print_log(ipart_dev, 'scanning')

        rescan_device(ipart_data['device_basename'])

        del partitions[ipart_dev]


def on_key_press(key):
    global key_ctrl_pressed
    global key_shift_pressed

    if key == Key.ctrl:
        key_ctrl_pressed = True

    if key == Key.shift:
        key_shift_pressed = True


def on_key_release(key):
    global key_ctrl_pressed
    global key_shift_pressed

    if key == Key.ctrl:
        key_ctrl_pressed = False

    if key == Key.shift:
        key_shift_pressed = False


def init_keyboard_listener():
    keyboard_listener = Listener(
        on_press=on_key_press,
        on_release=on_key_release
    )
    keyboard_listener.start()


def sync_writes(sync_writes_ts):
    global fs_instance

    current_ts = time.time()

    if not sync_writes_ts:
        sync_writes_ts = current_ts

    if current_ts - sync_writes_ts < 1:
        return sync_writes_ts

    sync_writes_ts = current_ts
    last_write_ts = fs_instance.get_last_write_ts()

    if not last_write_ts:
        return sync_writes_ts

    if current_ts - last_write_ts < 1:
        return sync_writes_ts

    fs_instance.clear_last_write_ts()
    fs_instance.sync_handles()

    return sync_writes_ts


def find_physical_cdrom_drives():
    hwinfo_buf = StringIO()
    cdrom_data_started = False
    ret = []

    # hwinfo --cdrom --short
    sh.hwinfo('--cdrom', '--short', _out=hwinfo_buf)

    for line in hwinfo_buf.getvalue().splitlines():
        line = line.strip()

        if not line:
            continue

        if line == 'cdrom:':
            cdrom_data_started = True
            continue

        if not cdrom_data_started:
            continue

        if not line.startswith('/dev/'):
            continue

        parts = line.split(maxsplit=1)

        if len(parts) != 2:
            continue

        device = parts[0]

        if not os.path.exists(device) or not os.path.isfile(device):
            ret.append(device)

    return ret


def update_physical_cdrom_drives(physical_cdrom_drives):
    print_log('Getting information about physical cd-rom drives')

    index = 0

    for device in sorted(find_physical_cdrom_drives()):
        physical_cdrom_drives[device] = {
            'index': index,
            'device': device
        }

        index += 1


def print_physical_cdrom_drives(physical_cdrom_drives):
    print_log('Physical cd-rom drives:')

    for key, drive_data in physical_cdrom_drives.items():
        print_log(key)

        print_log('  index: ' + str(drive_data['index']))
        print_log('  device: ' + drive_data['device'])

        print_log()


def find_physical_floppy_drives():
    ufiformat_buf = StringIO()
    ret = []

    # ufiformat --inquire --quiet
    sh.ufiformat('--inquire', '--quiet', _out=ufiformat_buf)

    for line in ufiformat_buf.getvalue().splitlines():
        line = line.strip()

        if not line:
            continue

        parts = line.split()

        if len(parts) != 2:
            continue

        device = parts[0]

        if not os.path.exists(device) or not os.path.isfile(device):
            ret.append(device)

    return ret


def update_physical_floppy_drives(physical_floppy_drives):
    print_log('Getting information about physical floppy drives')

    index = 0

    for device in sorted(find_physical_floppy_drives()):
        physical_floppy_drives[device] = {
            'index': index,
            'device': device
        }

        index += 1


def print_physical_floppy_drives(physical_floppy_drives):
    print_log('Physical floppy drives:')

    for key, drive_data in physical_floppy_drives.items():
        print_log(key)

        print_log('  index: ' + str(drive_data['index']))
        print_log('  device: ' + drive_data['device'])

        print_log()


def main():
    partitions = None
    old_partitions = None
    sync_disks_ts = 0
    sync_process = None
    disk_devices = {}
    loop_counter = 0
    sync_writes_ts = 0
    physical_floppy_drives = OrderedDict()
    physical_cdrom_drives = OrderedDict()

    print_app_version()
    check_pre_requirements()
    init_logger()
    unmount_fuse_mountpoint()
    mkdir_fuse_mountpoint()
    # uncomment this to enable FUSE logging
    # logging.basicConfig(level=logging.DEBUG)
    configure_system()
    init_fuse(disk_devices)
    update_physical_floppy_drives(physical_floppy_drives)
    print_physical_floppy_drives(physical_floppy_drives)
    update_physical_cdrom_drives(physical_cdrom_drives)
    print_physical_cdrom_drives(physical_cdrom_drives)
    init_keyboard_listener()

    try:
        while True:
            if not MAIN_LOOP_MAX_COUNTER or loop_counter < MAIN_LOOP_MAX_COUNTER:
                partitions = get_partitions2(
                    physical_cdrom_drives,
                    physical_floppy_drives
                )

                if partitions != old_partitions:
                    # something changed
                    print_partitions(partitions)
                    format_devices(partitions, old_partitions, loop_counter)
                    update_disk_devices(partitions, disk_devices)
                    affect_fs_disk_devices(disk_devices)

                if fix_disk_devices(partitions, disk_devices):
                    affect_fs_disk_devices(disk_devices)

                sync_writes_ts = sync_writes(sync_writes_ts)

                old_partitions = partitions
                sync_disks_ts, sync_process = sync(sync_disks_ts, sync_process)
                loop_counter += 1

            time.sleep(100 / 1000)
            time.sleep(0)
    except KeyboardInterrupt as ex:
        print_log('KeyboardInterrupt')

    unmount_fuse_mountpoint()

    sys.exit()

if __name__ == '__main__':
    main()
