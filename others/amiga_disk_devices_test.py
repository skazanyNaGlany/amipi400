import sys
import os
import random

assert sys.platform == 'linux', 'This script must be run only on Linux'
assert sys.version_info.major >= 3 and sys.version_info.minor >= 5, 'This script requires Python 3.5+'
# assert os.geteuid() == 0, 'This script must be run as root'


ORIGINAL_FILE = 'Traps n Treasures (1993)(Starbyte)(En)[cr PSG](Disk 1 of 2).adf'
ADD_FILE = '/tmp/amiga_disk_devices/__dev__sda.adf'
# SDA_FILE = '/dev/sda'
SDA_FILE = '/tmp/amiga_disk_devices/__dev__sda.adf'

def test_read():
    test_counter = 0
    max_test_counter = 100

    original_file_size = os.path.getsize(ORIGINAL_FILE)
    add_file_size = os.path.getsize(ADD_FILE)

    assert original_file_size == add_file_size

    print('Files size in bytes:', original_file_size)

    original_file = open(ORIGINAL_FILE, 'rb')
    add_file = open(ADD_FILE, 'rb')

    assert original_file
    assert add_file

    while test_counter < max_test_counter:
        test_counter += 1

        percent = 0

        print('test_read() test', test_counter, 'of', max_test_counter)

        original_file.seek(0)
        add_file.seek(0)

        assert original_file.tell() == add_file.tell()

        while True:
            original_chunk = original_file.read(4096)

            if not original_chunk:
                break

            add_chunk = add_file.read(4096)

            assert add_chunk
            assert original_chunk == add_chunk
            assert original_file.tell() == add_file.tell()

            current_percent = int(add_file.tell() / add_file_size * 100)

            if percent != current_percent:
                print(current_percent, '%')

            percent = current_percent

    original_file.close()
    add_file.close()


def test_random_read():
    test_counter = 0
    max_test_counter = 1000

    original_file_size = os.path.getsize(ORIGINAL_FILE)
    add_file_size = os.path.getsize(ADD_FILE)

    assert original_file_size == add_file_size

    print('Files size in bytes:', original_file_size)

    original_file = open(ORIGINAL_FILE, 'rb')
    add_file = open(ADD_FILE, 'rb')

    assert original_file
    assert add_file

    while test_counter < max_test_counter:
        test_counter += 1

        random.seed()

        offset = random.randint(1, original_file_size - 1)
        size = random.randint(1, 1024 * 16)

        print('test_random_read() test', test_counter, 'of', max_test_counter, 'offset ' + str(offset) + ' size ' + str(size))

        original_file.seek(offset)
        add_file.seek(offset)

        assert original_file.tell() == add_file.tell()

        original_chunk = original_file.read(size)

        if not original_chunk:
            break

        add_chunk = add_file.read(size)

        assert add_chunk
        assert original_chunk == add_chunk
        assert original_file.tell() == add_file.tell()

    original_file.close()
    add_file.close()


def test_dev_sda_read():
    print('Reading:', SDA_FILE)

    original_file = open(SDA_FILE, 'rb')
    original_file_size = 901120
    percent = 0

    assert original_file

    original_file.seek(0)

    while True:
        original_chunk = original_file.read(512)

        if not original_chunk:
            break

        current_percent = int(original_file.tell() / original_file_size * 100)

        if percent != current_percent:
            print(current_percent, '%')

        percent = current_percent

        # print(len(original_chunk))

    original_file.close()


def main():
    # test_read()
    # test_random_read()
    # test_dev_sda_read()
    # test_dev_sda_read()
    # test_dev_sda_read()
    test_dev_sda_read()


if __name__ == '__main__':
    main()
