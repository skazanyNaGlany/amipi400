#include <cstdio>
#include <string>
#include <unistd.h>
#include <sys/stat.h>
#include <time.h>
#include <fcntl.h>


#define BUFF_LEN 512


void read_all(FILE *f, size_t size) {
    char buff[BUFF_LEN];
    size_t off;
    size_t read_total = 0;
    size_t read_curr;

    printf("reading contents\n");

    while (1) {
        fflush(f);
        fsync(fileno(f));

        read_curr = read(fileno(f), buff, BUFF_LEN);

        // read_curr = fread(buff, 1, BUFF_LEN, f);
        // read_curr = fread(buff, BUFF_LEN, 1, f);

        printf("%zu\n", read_curr);

        sleep(1);
    }

    // while (!feof(f)) {
    //     fflush(f);
    //     fsync(fileno(f));

    //     fread(buff, 1, BUFF_LEN, f);

    //     off = ftell(f);
    //     printf("offset %zu\n", off);
    // }


    // while (fread(buff, 1, BUFF_LEN, f) == BUFF_LEN) {
    //     fflush(f);
    //     fsync(fileno(f));

    //     off = ftell(f);

    //     printf("offset %zu\n", off);

    //     fflush(f);
    //     fsync(fileno(f));
    // }
}


int main(int argc, char **argv) {
    size_t size;
    FILE *f;
    struct stat file_stat;

    if (argc != 2) {
        printf("Usage %s <file pathname>\n", argv[0]);

        return 1;
    }

    if (stat(argv[1], &file_stat) < 0) {
        perror("stat");

        return 1;
    }

    f = fopen(argv[0], "rb");

    if (f) {
        printf("file open\n");

        size = file_stat.st_size;

        printf("size %zu\n", size);

        setvbuf(f, NULL, _IONBF, 0);
        setbuf(f, NULL);
        posix_fadvise64(fileno(f), 0, size, POSIX_FADV_DONTNEED);

        rewind(f);

        read_all(f, size);

        fclose(f);
    }

    return 0;
}
