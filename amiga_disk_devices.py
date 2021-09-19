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
MAIN_LOOP_MAX_COUNTER = 1


class AmigaDiskDevicesFS(LoggingMixIn, Operations):
    def __init__(self, disk_devices: dict):
        self._now = time.time()
        self._disk_devices = disk_devices
        # self._static_files = {
        #     '/': {
        #         'real_pathname': TMP_PATH_PREFIX
        #     }
        # }
        self._static_files = {
            '/': dict(
                st_mode=(S_IFDIR | 0o444),
                st_ctime=self._now,
                st_mtime=self._now,
                st_atime=self._now,
                st_nlink=2,
                # st_gid=0,
                # st_uid=0,
                st_size=4096
            )
        }

    # Disable unused operations:
    access = None
    flush = None
    getxattr = None
    listxattr = None
    open = None
    opendir = None
    release = None
    releasedir = None
    statfs = None


    # def _transcode_device_pathname(self, ipart_data: dict):
    #     pathname = ipart_data['device'].replace(os.path.sep, '__')

    #     if ipart_data['amiga_device_type'] == AMIGA_DEV_TYPE_FLOPPY:
    #         pathname += '.adf'

    #     return pathname


    # def _transcode_disk_devices(self):
    #     transcoded = []

    #     for ipart_dev, ipart_data in self._disk_devices.items():
    #         transcoded.append(
    #             self._transcode_device_pathname(ipart_data)
    #         )

    #     return transcoded


    def _disk_device_exists(self, public_name: str):
        for ipart_dev, ipart_data in self._disk_devices.items():
            if ipart_data['public_name'] == public_name:
                return True

        return False


    def _find_file(self, public_name: str) -> Optional[dict]:
        for ipart_dev, ipart_data in self._disk_devices.items():
            if ipart_data['public_name'] == public_name:
                return ipart_data

        return None


    def _get_file_size(self, ipart_data: dict) -> int:
        if ipart_data['amiga_device_type'] == AMIGA_DEV_TYPE_FLOPPY:
            return 901120

        return 0


    # def _os_lstat(self, pathname: str):
    #     st = os.lstat(pathname)

    #     return dict((key, getattr(st, key)) for key in (
    #         'st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime',
    #         'st_nlink', 'st_size', 'st_uid'))


    # def chmod(self, path, mode):
    #     pass
    #     # print(locals())
    #     # raise Exception('chmod')


    # def chown(self, path, uid, gid):
    #     pass
    #     # print(locals())
    #     # raise Exception('chown')


    # def create(self, path, mode):
    #     pass
    #     # print(locals())
    #     # raise Exception('create')


    def getattr(self, path, fh=None):
        if path in self._static_files:
            return self._static_files[path]

        name = path

        if name.startswith(os.path.sep):
            name = name[1:]

        # if not self._disk_device_exists(name):
        #     raise FuseOSError(ENOENT)

        ipart_data = self._find_file(name)

        if not ipart_data:
            FuseOSError(ENOENT)

        now = time.time()

        return dict(st_mode=(S_IFREG | 0o666),
                    st_nlink=1,
                    st_size=self._get_file_size(ipart_data),
                    st_ctime=now,
                    st_mtime=now,
                    st_atime=now)


    # # def getxattr(self, path, name, position=0):
    # #     pass
    # #     # print(locals())
    # #     # raise Exception('getxattr')


    # def listxattr(self, path):
    #     pass
    #     # print(locals())
    #     # raise Exception('listxattr')


    # def mkdir(self, path, mode):
    #     pass
    #     # print(locals())
    #     # raise Exception('mkdir')


    # def open(self, path, flags):
    #     pass
    #     # print(locals())
    #     # raise Exception('open')


    # def read(self, path, size, offset, fh):
    #     pass
    #     # print(locals())
    #     # raise Exception('read')


    def readdir(self, path, fh):
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

        # print(locals())
        # print(self._disk_devices)
        # pass
        # print(locals())
        # raise Exception('readdir')


    # def readlink(self, path):
    #     pass
    #     # print(locals())
    #     # raise Exception('readlink')


    # def removexattr(self, path, name):
    #     pass
    #     # print(locals())
    #     # raise Exception('removexattr')


    # def rename(self, old, new):
    #     pass
    #     # print(locals())
    #     # raise Exception('rename')


    # def rmdir(self, path):
    #     pass
    #     # print(locals())
    #     # raise Exception('rmdir')


    # def setxattr(self, path, name, value, options, position=0):
    #     pass
    #     # print(locals())
    #     # raise Exception('setxattr')


    # def statfs(self, path):
    #     pass
    #     # print(locals())
    #     # print_log(locals())
    #     # raise Exception('statfs')

    #     # return dict(f_bsize=512, f_blocks=4096, f_bavail=2048)


    # def symlink(self, target, source):
    #     pass
    #     # print(locals())
    #     # raise Exception('symlink')


    # def truncate(self, path, length, fh=None):
    #     pass
    #     # print(locals())
    #     # raise Exception('truncate')


    # def unlink(self, path):
    #     pass
    #     # print(locals())
    #     # raise Exception('unlink')


    # def utimens(self, path, times=None):
    #     pass
    #     # print(locals())
    #     # raise Exception('utimens')


    # def write(self, path, data, offset, fh):
    #     pass
    #     # print(locals())
    #     # raise Exception('write')


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


def init_logging():
    logging.basicConfig(level=logging.DEBUG)


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


def run_fuse(disk_devices: dict):
    print('disk_devices', disk_devices)
    FUSE(AmigaDiskDevicesFS(disk_devices), TMP_PATH_PREFIX, foreground=True, **{'allow_other': True})


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


def flush_default_logger():
    handlers = logging.getLogger().handlers

    if handlers and len(handlers) > 1:
        print('DDDDDDDDDD2')
        handlers[0].flush()


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
    init_logging()
    check_pre_requirements()
    configure_system()
    init_fuse(disk_devices)

    try:
        while True:
            if loop_counter < MAIN_LOOP_MAX_COUNTER:
                partitions = get_partitions2()

                if partitions != old_partitions:
                    # something changed
                    print_partitions(partitions)
                    update_disk_devices(partitions, disk_devices)

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
