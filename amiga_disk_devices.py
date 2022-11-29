from errno import EIO, ENOSPC, EROFS

import sys
import os
import subprocess
import traceback

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
    import threading
    import hashlib
    import ctypes

    from collections import OrderedDict
    from io import StringIO
    from typing import Optional, List, Dict
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
    from errno import ENOENT
    from stat import S_IFDIR, S_IFREG
    from pynput.keyboard import Key, Listener
    from array import array
    from utils import set_numlock_state, mute_system_sound, unmute_system_sound, enable_power_led, disable_power_led, init_simple_mixer_control, save_replace_file, get_dir_size, file_get_bytes_contents
except ImportError as xie:
    traceback.print_exc()
    sys.exit(1)


APP_UNIXNAME = 'amiga_disk_devices'
APP_VERSION = '0.1'
TMP_PATH_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
LOG_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'amiga_disk_devices.log')
ENABLE_LOGGER = False
ENABLE_REINIT_HANDLE_AFTER_SECS = 0
ENABLE_FLOPPY_DRIVE_READ_A_HEAD = True
ENABLE_SET_CACHE_PRESSURE = False
ENABLE_ADF_CACHING = True
DISABLE_SWAP = False
DEFAULT_READ_A_HEAD_SECTORS = 24      # 256 system default, 44 seems ok, 24 seems best
SYNC_DISKS_SECS = 60 * 3
AMIGA_DISK_DEVICE_TYPE_ADF = 1
AMIGA_DISK_DEVICE_TYPE_HDF_HDFRDB = 8
AMIGA_DISK_DEVICE_TYPE_HDF_DISKIMAGE = 2
AMIGA_DISK_DEVICE_TYPE_HDF = 5
AMIGA_DISK_DEVICE_TYPE_ISO = 10
FLOPPY_DEVICE_SIZE = 1474560
FLOPPY_ADF_SIZE = 901120
FLOPPY_DEVICE_LAST_SECTOR = 1474048
FLOPPY_ADF_EXTENSION = '.adf'
HD_HDF_EXTENSION = '.hdf'
CD_ISO_EXTENSION = '.iso'
ADF_BOOTBLOCK = numpy.dtype([
    ('DiskType',    numpy.byte,     (4, )   ),
    ('Chksum',      numpy.uint32            ),
    ('Rootblock',   numpy.uint32            )
])
SYSTEM_INTERNAL_SD_CARD_NAME = 'mmcblk0'
PHYSICAL_SECTOR_SIZE = 512
PHYSICAL_FLOPPY_SECTOR_READ_TIME_MS = 100
STATUS_FILE_NAME = 'status.log'
CACHE_DATA_BETWEEN_SECS = 3
CACHED_ADFS_MAX_DIR_SIZE = 1073741824       # 1GB
CACHED_ADFS_DIR = os.path.realpath('./cached_adfs')
CACHED_ADF_SIGN = 'AMIPI400'
CACHED_ADF_HEADER_TYPE = 'CachedADFHeader'
CACHED_ADF_STR_ENCODING = 'utf8'
MAIN_LOOP_MAX_COUNTER = 0


fs_instance = None
key_cmd_pressed = False
key_delete_pressed = False
key_shift_pressed = False
os_read_write_mutex = threading.Lock()
devices_read_a_head_sectors = {}


def os_read(handle, offset, size):
    with os_read_write_mutex:
        os.lseek(handle, offset, os.SEEK_SET)

        return os.read(handle, size)


def os_write(handle, offset, data):
    with os_read_write_mutex:
        os.lseek(handle, offset, os.SEEK_SET)

        return os.write(handle, data)


class CachedADFHeader(ctypes.Structure):
    _fields_ = [
        ('sign', ctypes.c_char * 32),
        ('header_type', ctypes.c_char * 32),
        ('sha512', ctypes.c_char * 129)
    ]


class DiskSpinner(threading.Thread):
    def __init__(self):
        self._running = False
        self._pathname_spinnings = {}
        self._handle_spinnings = {}
        self._cached_ranges = {}
        self._cached_ranges2 = {}

        threading.Thread.__init__(self)


    def _is_dd_running(self, dd_process) -> bool:
        if dd_process.poll() is None:
            return True

        return False


    def _run_dd(self, device: str, offset, size):
        if size <= 0:
            return None

        count_sectors = int(size / PHYSICAL_SECTOR_SIZE)

        if count_sectors <= 0:
            return None

        dd_str = 'dd iflag=skip_bytes,direct bs={bs} count={count} skip={skip} if=\"{_if}\" of=\"{of}\" status=none'.format(
            bs=PHYSICAL_SECTOR_SIZE,
            count=count_sectors,
            skip=offset,
            _if=device,
            of='/dev/null'
        )

        return subprocess.Popen(dd_str, shell=True)


    def _process_spinnings_by_pathname(self):
        for device in self._pathname_spinnings:
            if self._pathname_spinnings[device]['dd_process']:
                if not self._is_dd_running(self._pathname_spinnings[device]['dd_process']):
                    self._pathname_spinnings[device]['dd_process'] = None

            if not self._pathname_spinnings[device]['enable']:
                continue

            self._pathname_spinnings[device]['enable'] = False
            self._pathname_spinnings[device]['dd_process'] = self._run_dd(
                device,
                self._pathname_spinnings[device]['offset'],
                self._pathname_spinnings[device]['size']
            )


    def run(self):
        while self._running:
            self._process_spinnings_by_pathname()

            time.sleep(100 / 1000)
            time.sleep(0)


    def set_spinning_by_pathname(self, pathname: str, enable: bool, offset, size):
        if pathname in self._pathname_spinnings:
            if self._pathname_spinnings[pathname]['dd_process']:
                return

        if pathname not in self._pathname_spinnings:
            self._pathname_spinnings[pathname] = {
                'by_pathname': True,
                'enable': False,
                'offset': 0,
                'size': 0,
                'dd_process': None
            }

        self._pathname_spinnings[pathname]['enable'] = enable
        self._pathname_spinnings[pathname]['offset'] = offset
        self._pathname_spinnings[pathname]['size'] = size
        self._pathname_spinnings[pathname]['dd_process'] = None


    def start(self):
        self._running = True

        return super().start()


    def stop(self):
        self._running = False


class AmigaDiskDevicesFS(LoggingMixIn, Operations):
    _handles: Dict[str, int]
    _access_times: Dict[str, float]
    _modification_times: Dict[str, float]

    def __init__(self, disk_devices: dict, disk_spinner: DiskSpinner):
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
            ),
            '/' + STATUS_FILE_NAME: dict(
                st_mode=(S_IFREG | 0o444),
                st_ctime=self._instance_time,
                st_mtime=self._instance_time,
                st_atime=self._instance_time,
                st_nlink=1
            )
        }
        self._handles = {}
        self._mutex = threading.Lock()
        self._access_times = {}
        self._modification_times = {}
        self._last_write_ts = 0
        self._disk_spinner = disk_spinner
        self._status_log_content = None


    access = None
    flush = None
    getxattr = None
    listxattr = None
    open = None
    opendir = None
    release = None
    releasedir = None
    statfs = None


    def _add_defaults(self, ipart_data):
        if 'fully_cached' not in ipart_data:
            ipart_data['fully_cached'] = False

        if 'last_caching_ts' not in ipart_data:
            ipart_data['last_caching_ts'] = 0

        if 'enable_spinning' not in ipart_data:
            ipart_data['enable_spinning'] = True

        if 'cached_adf_pathname' not in ipart_data:
            ipart_data['cached_adf_pathname'] = ''


    def set_disk_devices(self, disk_devices: dict):
        with self._mutex:
            for ipart_dev, ipart_data in disk_devices.items():
                self._add_defaults(ipart_data)

            self._disk_devices = disk_devices
            self._status_log_content = None

            self._flush_handles()


    def _flush_handles(self):
        for device_pathname in list(self._handles.keys()):
            if device_pathname not in self._disk_devices:
                self._close_handle(device_pathname)


    def _close_handles(self):
        for device_pathname in list(self._handles.keys()):
            self._close_handle(device_pathname)


    def _close_handle(self, device_pathname: str):
        handle = None

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

        return handle


    def _open_handle(self, ipart_data: dict) -> Optional[int]:
        device_pathname = ipart_data['device']

        if device_pathname in self._handles:
            return self._handles[device_pathname]

        self._set_fully_cached(ipart_data, False)

        is_readable = ipart_data['is_readable']
        is_writable = ipart_data['is_writable']

        mode = os.O_SYNC | os.O_RSYNC

        if is_readable and is_writable:
            mode |= os.O_RDWR
        else:
            mode |= os.O_RDONLY

        try:
            self._handles[device_pathname] = os.open(device_pathname, mode)
        except:
            return None

        return self._handles[device_pathname]


    def _find_file(self, public_name: str) -> Optional[dict]:
        for ipart_dev, ipart_data in self._disk_devices.items():
            if ipart_data['public_name'] == public_name:
                return ipart_data

        return None


    def _save_file_access_time(self, device_pathname: str, _time: float = None) -> float:
        if _time is None:
            _time = time.time()

        self._access_times[device_pathname] = _time

        return _time


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
        with self._mutex:
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


    def _partial_read(
        self,
        handle,
        offset,
        size,
        max_read_size = None,
        min_total_read_time_ms = None,
        pre_read_callback = None,
        post_read_callback = None,
        callback_user_data = None
    ):
        ex = None
        to_read_size = size
        all_data = bytes()
        dynamic_offset = offset
        read_time_ms = 0
        total_read_time_ms = 0
        count_real_read_sectors = 0
        total_len_data = 0

        while True:
            try:
                if pre_read_callback:
                    pre_read_callback(
                        read_time_ms,
                        total_read_time_ms,
                        callback_user_data
                    )

                start_time = time.time()

                data = os_read(handle, dynamic_offset, PHYSICAL_SECTOR_SIZE)
                len_data = len(data)
                dynamic_offset += len_data
                total_len_data += len_data

                read_time_ms = int((time.time() - start_time) * 1000)
                total_read_time_ms += read_time_ms

                if post_read_callback:
                    post_read_callback(
                        read_time_ms,
                        total_read_time_ms,
                        callback_user_data
                    )

                if read_time_ms > PHYSICAL_FLOPPY_SECTOR_READ_TIME_MS:
                    count_real_read_sectors += 1

                all_data += data
                to_read_size -= len_data

                if len_data < PHYSICAL_SECTOR_SIZE:
                    break

                if max_read_size is not None:
                    if total_len_data >= max_read_size:
                        break

                if to_read_size <= 0:
                    if min_total_read_time_ms is not None:
                        if total_read_time_ms < min_total_read_time_ms:
                            continue

                    break
            except Exception as x:
                ex = x

                break

        all_data = all_data[:size]

        return {
            'all_data': all_data,
            'ex': ex,
            'total_read_time_ms': total_read_time_ms,
            'count_real_read_sectors': count_real_read_sectors
        }


    def _set_fully_cached(self, ipart_data, fully_cached_status):
        if ipart_data['fully_cached'] != fully_cached_status:
            ipart_data['fully_cached'] = fully_cached_status

            self._status_log_content = None


    def _pre_read_callback(self, read_time_ms, total_read_time_ms, callback_user_data):
        ipart_data = callback_user_data

        if not ipart_data['fully_cached']:
            mute_system_sound(4)

        self._save_file_access_time(ipart_data['device'])


    def _floppy_read(self, handle, offset, size, ipart_data):
        current_time = time.time()

        if not ipart_data['last_caching_ts']:
            ipart_data['last_caching_ts'] = current_time

        if not ipart_data['fully_cached']:
            mute_system_sound(4)

        read_result = self._partial_read(
            handle,
            offset,
            size,
            None,
            None,
            self._pre_read_callback,
            None,
            ipart_data
        )

        if read_result['total_read_time_ms'] > PHYSICAL_FLOPPY_SECTOR_READ_TIME_MS:
            self._set_fully_cached(ipart_data, False)

        # set_numlock_state(ipart_data['fully_cached'])

        if ipart_data['fully_cached']:
            if ipart_data['enable_spinning']:
                self._disk_spinner.set_spinning_by_pathname(
                    ipart_data['device'],
                    True,
                    offset,
                    PHYSICAL_SECTOR_SIZE
                )

            if read_result['ex'] is not None:
                raise read_result['ex']

            return read_result['all_data']

        if read_result['total_read_time_ms'] < PHYSICAL_FLOPPY_SECTOR_READ_TIME_MS \
            and not ipart_data['fully_cached']:

            if not ipart_data['fully_cached']:
                if current_time - ipart_data['last_caching_ts'] >= CACHE_DATA_BETWEEN_SECS:
                    read_result2 = self._partial_read(
                        handle,
                        0,
                        PHYSICAL_SECTOR_SIZE,
                        FLOPPY_ADF_SIZE,
                        PHYSICAL_FLOPPY_SECTOR_READ_TIME_MS,
                        self._pre_read_callback,
                        None,
                        ipart_data
                    )

                    ipart_data['last_caching_ts'] = current_time

                    if read_result2['total_read_time_ms'] < PHYSICAL_FLOPPY_SECTOR_READ_TIME_MS:
                        self._set_fully_cached(ipart_data, True)

                        self._floppy_cache_adf(handle, ipart_data)

        self._save_file_access_time(ipart_data['device'])

        if read_result['ex'] is not None:
            raise read_result['ex']

        return read_result['all_data']


    def _floppy_cache_adf(self, handle, ipart_data):
        # should be called only once when saving cached ADF
        # since read() and write() will not call
        # _floppy_read()

        if not ENABLE_ADF_CACHING:
            return

        # read whole ADF
        read_result3 = self._partial_read(
            handle,
            0,
            FLOPPY_ADF_SIZE,
            FLOPPY_ADF_SIZE,
            PHYSICAL_FLOPPY_SECTOR_READ_TIME_MS,
            self._pre_read_callback,
            None,
            ipart_data
        )

        # calculate sha512 hash from readed ADF
        adf_hash = hashlib.sha512()
        adf_hash.update(read_result3['all_data'])

        hexdigest = adf_hash.hexdigest()

        # save the CachedADFHeader at last sector of the device file
        header = CachedADFHeader()
        header.sign = bytes(CACHED_ADF_SIGN, CACHED_ADF_STR_ENCODING)
        header.header_type = bytes(CACHED_ADF_HEADER_TYPE, CACHED_ADF_STR_ENCODING)
        header.sha512 = bytes(hexdigest, CACHED_ADF_STR_ENCODING)

        os_write(handle, FLOPPY_DEVICE_LAST_SECTOR, bytes(header))

        cached_adf_pathname = os.path.join(CACHED_ADFS_DIR, hexdigest + FLOPPY_ADF_EXTENSION)

        if not os.path.exists(cached_adf_pathname) or os.path.getsize(cached_adf_pathname) != FLOPPY_ADF_SIZE:
            # save a copy of the ADF file in the cache dir
            # sha512 + '.adf'
            save_replace_file(
                cached_adf_pathname,
                read_result3['all_data'],
                CACHED_ADFS_MAX_DIR_SIZE
            )
            os.sync()

            # next call to read() or write() will be redirected to
            # _floppy_read_cached() or _floppy_write_cached()
            ipart_data['cached_adf_pathname'] = cached_adf_pathname

            # close the handle, it would not be needed anymore
            self._close_handle(ipart_data['device'])

            print_log('{filename} saved cached ADF as {cached_adf_pathname}'.format(
                filename=ipart_data['device'],
                cached_adf_pathname=cached_adf_pathname
            ))


    def _generate_status_log(self):
        if self._status_log_content:
            return self._status_log_content

        content = ''

        for ipart_dev, ipart_data in self._disk_devices.items():
            content += 'device:' + ipart_dev + ', '
            content += 'public_name:' + ipart_data['public_name'] + ', '
            content += 'fully_cached:' + str(int(ipart_data['fully_cached']))
            content += '\n'

        self._status_log_content = content

        return content


    def _status_log_read(self, offset, size):
        content = self._generate_status_log()

        return bytes(
            content[offset : offset + size],
            'utf-8'
        )


    def _generic_read(self, handle, offset, size, ipart_data):
        self._save_file_access_time(ipart_data['device'])

        if ipart_data['is_disk_drive']:
            disable_power_led()

        return os_read(handle, offset, size)


    def _floppy_read_cached(self, offset, size, ipart_data):
        self._save_file_access_time(ipart_data['device'])
        self._set_fully_cached(ipart_data, True)

        if ipart_data['enable_spinning']:
            self._disk_spinner.set_spinning_by_pathname(
                ipart_data['device'],
                True,
                offset,
                PHYSICAL_SECTOR_SIZE
            )

        return file_get_bytes_contents(
            ipart_data['cached_adf_pathname'],
            size,
            offset
        )


    def read(self, path, size, offset, fh):
        with self._mutex:
            self._flush_handles()

            name = self._clear_pathname(path)

            if name == STATUS_FILE_NAME:
                return self._status_log_read(offset, size)

            ipart_data = self._find_file(name)

            if not ipart_data:
                raise FuseOSError(ENOENT)

            file_size = ipart_data['size']

            if offset + size > file_size:
                size = file_size - offset

            if offset >= file_size or size <= 0:
                self._save_file_access_time(ipart_data['device'])

                return b''

            if ipart_data['is_floppy_drive'] and ipart_data['cached_adf_pathname']:
                return self._floppy_read_cached(offset, size, ipart_data)

            handle = self._open_handle(ipart_data)

            if handle is None:
                self._save_file_access_time(ipart_data['device'])

                raise FuseOSError(EIO)

            if ipart_data['is_floppy_drive']:
                return self._floppy_read(
                    handle,
                    offset,
                    size,
                    ipart_data
                )

            return self._generic_read(
                handle,
                offset,
                size,
                ipart_data
            )


    def truncate(self, path, length, fh=None):
        # block devices cannot be truncated, so just return
        return


    def write(self, path, data, offset, fh):
        with self._mutex:
            self._flush_handles()

            name = self._clear_pathname(path)
            ipart_data = self._find_file(name)

            if not ipart_data:
                raise FuseOSError(ENOENT)

            if not ipart_data['is_writable']:
                raise FuseOSError(EROFS)

            self._set_fully_cached(ipart_data, False)
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

            if ipart_data['is_floppy_drive']:
                mute_system_sound(4)

            if ipart_data['is_disk_drive']:
                disable_power_led()

            ex = None

            try:
                result = os_write(handle, offset, data)

                self._save_file_modification_time(ipart_data['device'])

                if ipart_data['is_floppy_drive']:
                    mute_system_sound(4)
            except Exception as x:
                ex = x

            self._save_file_modification_time(ipart_data['device'])

            if ex is not None:
                raise ex

            return result


    def readdir(self, path, fh):
        with self._mutex:
            self._flush_handles()

            entries = [
                '.',
                '..',
                STATUS_FILE_NAME
            ]

            if path != '/':
                return entries

            for ipart_dev, ipart_data in self._disk_devices.items():
                entries.append(
                    ipart_data['public_name']
                )

            return entries


    def destroy(self, path):
        with self._mutex:
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
    if not ENABLE_SET_CACHE_PRESSURE:
        return

    print_log('Set cache pressure')
    os.system('sysctl -q vm.vfs_cache_pressure=200')


def check_system_binaries():
    print_log('Checking system binaries')

    bins = [
        'lsblk',
        'sysctl',
        'swapoff',
        'blockdev',
        'umount',
        'hwinfo'
    ]

    for ibin in bins:
        if not sh.which(ibin):
            print_log(ibin + ': command not found')
            sys.exit(1)


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
        device_basename = os.path.basename(full_path)

        if device_basename.startswith(SYSTEM_INTERNAL_SD_CARD_NAME):
            continue

        device_data = {
            'mountpoint': found[3],
            'label': found[4],
            'config': None,
            'device': full_path,
            'device_basename': device_basename,
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
        print_log('  pttype: ' + str(value['pttype']))
        print_log('  fstype: ' + str(value['fstype']))

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
        data = array('B', file.read(PHYSICAL_SECTOR_SIZE))

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


def remove_known_disk_devices(partitions: dict, disk_devices: dict):
    count_removed = 0

    for device_pathname, device_data in disk_devices.copy().items():
        if device_pathname not in partitions:
            continue

        ipart_data = partitions[device_pathname]
        remove = not is_unknown_disk(ipart_data) and \
            not ipart_data['is_cdrom_drive'] and \
            not device_data['force_add']

        if remove:
            print_log(device_pathname, 'removing incorrectly added device')

            del disk_devices[device_pathname]
            count_removed += 1

    return count_removed


def cleanup_disk_devices(partitions: dict, disk_devices: dict):
    for ipart_dev in list(disk_devices.keys()):
        if ipart_dev not in partitions:
            del disk_devices[ipart_dev]

            print_log(ipart_dev, 'ejected')


def add_adf_disk_device(
    ipart_dev: str,
    ipart_data: dict,
    disk_devices: dict,
    force_add: bool = False
):
    print_log('{filename} using as ADF'.format(
        filename=ipart_dev
    ))

    if ENABLE_FLOPPY_DRIVE_READ_A_HEAD:
        set_device_read_a_head_sectors(ipart_dev, DEFAULT_READ_A_HEAD_SECTORS)
    else:
        set_device_read_a_head_sectors(ipart_dev, 0)

    disk_devices[ipart_dev] = ipart_data.copy()
    disk_devices[ipart_dev]['amiga_device_type'] = AMIGA_DISK_DEVICE_TYPE_ADF
    disk_devices[ipart_dev]['public_name'] = device_get_public_name(disk_devices[ipart_dev])
    disk_devices[ipart_dev]['size'] = FLOPPY_ADF_SIZE
    disk_devices[ipart_dev]['force_add'] = force_add
    disk_devices[ipart_dev]['cached_adf_pathname'] = ''

    update_cached_adf_flags(ipart_dev, disk_devices[ipart_dev])


def update_cached_adf_flags(ipart_dev: str, ipart_data: dict):
    if not ENABLE_ADF_CACHING:
        return

    last_sector_data = file_get_bytes_contents(ipart_dev, PHYSICAL_SECTOR_SIZE, FLOPPY_DEVICE_LAST_SECTOR)
    adf_header = CachedADFHeader.from_buffer_copy(last_sector_data)

    decoded_sign = str(adf_header.sign, CACHED_ADF_STR_ENCODING)
    decoded_header_type = str(adf_header.header_type, CACHED_ADF_STR_ENCODING)

    if decoded_sign != CACHED_ADF_SIGN or decoded_header_type != CACHED_ADF_HEADER_TYPE:
        # ADF not cached
        return

    decoded_sha512 = str(adf_header.sha512, CACHED_ADF_STR_ENCODING)
    cached_adf_pathname = os.path.join(CACHED_ADFS_DIR, decoded_sha512 + FLOPPY_ADF_EXTENSION)

    if not os.path.exists(cached_adf_pathname) or os.path.getsize(cached_adf_pathname) != FLOPPY_ADF_SIZE:
        return

    ipart_data['cached_adf_pathname'] = cached_adf_pathname

    print_log('{filename} is cached ADF (as {cached_adf_pathname})'.format(
        filename=ipart_dev,
        cached_adf_pathname=cached_adf_pathname
    ))


def add_hdf_disk_device(
    ipart_dev: str,
    ipart_data: dict,
    disk_devices: dict,
    _type: int,
    force_add: bool = False
):
    print_log('{filename} using as HDF'.format(
        filename=ipart_dev
    ))

    disk_devices[ipart_dev] = ipart_data.copy()
    disk_devices[ipart_dev]['amiga_device_type'] = _type
    disk_devices[ipart_dev]['public_name'] = device_get_public_name(disk_devices[ipart_dev])
    disk_devices[ipart_dev]['force_add'] = force_add


def add_bigger_disk_device(
    ipart_dev: str,
    ipart_data: dict,
    disk_devices: dict,
    force_add: bool = False
):
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

    add_hdf_disk_device(
        ipart_dev,
        ipart_data,
        disk_devices,
        hdf_type,
        force_add
    )


def add_iso_disk_device(ipart_dev: str, ipart_data: dict, disk_devices: dict):
    print_log('{filename} using as ISO'.format(
        filename=ipart_dev
    ))

    disk_devices[ipart_dev] = ipart_data.copy()
    disk_devices[ipart_dev]['amiga_device_type'] = AMIGA_DISK_DEVICE_TYPE_ISO
    disk_devices[ipart_dev]['public_name'] = device_get_public_name(disk_devices[ipart_dev])
    disk_devices[ipart_dev]['force_add'] = False


def is_unknown_disk(ipart_data: dict) -> bool:
    return ipart_data['fstype'] == '' and ipart_data['pttype'] == ''


def add_disk_devices2(partitions: dict, disk_devices: dict):
    force_add = is_cmd_shift_pressed()

    clear_pressed_keys()

    for ipart_dev, ipart_data in partitions.items():
        if ipart_dev in disk_devices:
            continue

        unknown = is_unknown_disk(ipart_data)

        if ipart_data['is_floppy_drive']:
            if not unknown and not force_add:
                continue

            add_adf_disk_device(
                ipart_dev,
                ipart_data,
                disk_devices,
                force_add
            )

            if not disk_devices[ipart_dev]['cached_adf_pathname']:
                # ADF is not cached, need to mute the system sound
                mute_system_sound(6)
        elif ipart_data['is_disk_drive']:
            if not unknown and not force_add:
                continue

            add_bigger_disk_device(
                ipart_dev,
                ipart_data,
                disk_devices,
                force_add
            )
        elif ipart_data['is_cdrom_drive']:
            add_iso_disk_device(
                ipart_dev,
                ipart_data,
                disk_devices
            )


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
        return f.read(PHYSICAL_SECTOR_SIZE)


def update_disk_devices(partitions: dict, disk_devices: dict):
    cleanup_disk_devices(partitions, disk_devices)
    add_disk_devices2(partitions, disk_devices)


def run_fuse(disk_devices: dict, disk_spinner: DiskSpinner):
    global fs_instance

    fs_instance = AmigaDiskDevicesFS(disk_devices, disk_spinner)

    FUSE(
        fs_instance,
        TMP_PATH_PREFIX,
        foreground=True,
        allow_other=True,
        direct_io=True
    )


def init_fuse(disk_devices: dict, disk_spinner: DiskSpinner):
    print_log('Init FUSE')

    fuse_instance_thread = threading.Thread(target=run_fuse, args=(disk_devices, disk_spinner,))
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
    global devices_read_a_head_sectors

    if device not in devices_read_a_head_sectors:
        devices_read_a_head_sectors[device] = None

    if devices_read_a_head_sectors[device] == sectors:
        return

    devices_read_a_head_sectors[device] = sectors

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


def quick_format_single_device(device: str):
    blank_dos = bytearray(1024)

    blank_dos[0] = ord('D')
    blank_dos[1] = ord('O')
    blank_dos[2] = ord('S')

    try:
        with open(device, 'wb') as f:
            f.write(blank_dos)
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
    if not is_cmd_delete_pressed():
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


def is_cmd_delete_pressed() -> bool:
    return key_cmd_pressed and key_delete_pressed


def is_cmd_shift_pressed() -> bool:
    return key_cmd_pressed and key_shift_pressed


def clear_pressed_keys():
    global key_cmd_pressed
    global key_delete_pressed
    global key_shift_pressed

    key_cmd_pressed = False
    key_delete_pressed = False
    key_shift_pressed = False


def on_key_press(key):
    global key_cmd_pressed
    global key_delete_pressed
    global key_shift_pressed

    if key == Key.cmd:
        key_cmd_pressed = True

    if key == Key.delete:
        key_delete_pressed = True

    if key == Key.shift:
        key_shift_pressed = True


def on_key_release(key):
    global key_cmd_pressed
    global key_delete_pressed
    global key_shift_pressed

    if key == Key.cmd:
        key_cmd_pressed = False

    if key == Key.delete:
        key_delete_pressed = False

    if key == Key.shift:
        key_shift_pressed = False


def init_keyboard_listener():
    keyboard_listener = Listener(
        on_press=on_key_press,
        on_release=on_key_release
    )
    keyboard_listener.start()


def init_disk_spinner():
    print_log('Init DiskSpinner')

    disk_spinner = DiskSpinner()
    disk_spinner.start()

    return disk_spinner


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
    disk_devices = {}
    loop_counter = 0
    physical_floppy_drives = OrderedDict()
    physical_cdrom_drives = OrderedDict()

    print_app_version()
    check_pre_requirements()
    init_logger()
    unmount_fuse_mountpoint()
    mkdir_fuse_mountpoint()
    # # uncomment this to enable FUSE logging
    # logging.basicConfig(level=logging.DEBUG)
    configure_system()
    init_simple_mixer_control()
    disk_spinner = init_disk_spinner()
    init_fuse(disk_devices, disk_spinner)
    update_physical_floppy_drives(physical_floppy_drives)
    print_physical_floppy_drives(physical_floppy_drives)
    update_physical_cdrom_drives(physical_cdrom_drives)
    print_physical_cdrom_drives(physical_cdrom_drives)
    init_keyboard_listener()
    os.makedirs(CACHED_ADFS_DIR, exist_ok=True)

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

                if remove_known_disk_devices(partitions, disk_devices):
                    affect_fs_disk_devices(disk_devices)

                old_partitions = partitions
                loop_counter += 1

            unmute_system_sound()
            enable_power_led()

            time.sleep(100 / 1000)
            time.sleep(0)
    except KeyboardInterrupt as ex:
        print_log('KeyboardInterrupt')

    unmute_system_sound()
    enable_power_led()
    unmount_fuse_mountpoint()
    disk_spinner.stop()

    sys.exit()

if __name__ == '__main__':
    main()
