#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct PacketFrame {
    char payload[16];
    volatile uint32_t guard_magic;
};

static int hex_nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
    if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
    return -1;
}

int parse_packet(const uint8_t *buf, size_t total_len, char *out, size_t out_cap) {
    if (total_len < 2 || out_cap < 17) {
        return -1;
    }
    uint8_t tag = buf[0];
    uint8_t decl_len = buf[1];
    if ((size_t)decl_len + 2 > total_len) {
        return -2;
    }

    struct PacketFrame frame;
    memset(&frame, 0, sizeof(frame));
    frame.guard_magic = 0xCAFEBABEu;

    if (tag == 0x10) {
        if (decl_len > sizeof(frame.payload)) {
            return -3;
        }
        memcpy(frame.payload, buf + 2, decl_len);
    } else if (tag == 0x42) {
        /* BUG: checks 32 instead of sizeof(frame.payload) (16). */
        if (decl_len > 32) {
            return -3;
        }
        for (uint8_t i = 0; i < decl_len; i++) {
            ((volatile char *)frame.payload)[i] = (char)buf[2 + i];
        }
    } else {
        return -4;
    }

    if (frame.guard_magic != 0xCAFEBABEu) {
        fprintf(stderr, "FRAME_GUARD_CORRUPTED:0x%08x\n", frame.guard_magic);
        fflush(stderr);
        __builtin_trap();
    }

    size_t copy_n = decl_len < sizeof(frame.payload) ? decl_len : sizeof(frame.payload);
    memcpy(out, frame.payload, copy_n);
    out[copy_n] = '\0';
    return (int)copy_n;
}

static int run_selftest(void) {
    char out[32];
    const uint8_t ok1[] = {0x10, 0x04, 'p', 'i', 'n', 'g'};
    if (parse_packet(ok1, sizeof(ok1), out, sizeof(out)) != 4 || strcmp(out, "ping") != 0) {
        return 1;
    }
    const uint8_t ok2[] = {0x42, 0x05, 'h', 'e', 'l', 'l', 'o'};
    if (parse_packet(ok2, sizeof(ok2), out, sizeof(out)) != 5 || strcmp(out, "hello") != 0) {
        return 1;
    }
    const uint8_t short_pkt[] = {0x42, 0x08, 'a', 'b'};
    if (parse_packet(short_pkt, sizeof(short_pkt), out, sizeof(out)) != -2) {
        return 1;
    }
    const uint8_t over_tag10[] = {
        0x10, 0x14,
        '0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f','W','X','Y','Z'
    };
    if (parse_packet(over_tag10, sizeof(over_tag10), out, sizeof(out)) != -3) {
        return 1;
    }
    printf("SELFTEST_OK\n");
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--selftest") == 0) {
        return run_selftest();
    }
    if (argc == 3 && strcmp(argv[1], "--hex") == 0) {
        const char *hex = argv[2];
        size_t slen = strlen(hex);
        if (slen % 2 != 0 || slen > 256) {
            fprintf(stderr, "INVALID_HEX\n");
            return 2;
        }
        uint8_t raw[128];
        size_t blen = slen / 2;
        for (size_t i = 0; i < blen; i++) {
            int hi = hex_nibble(hex[2 * i]);
            int lo = hex_nibble(hex[2 * i + 1]);
            if (hi < 0 || lo < 0) {
                fprintf(stderr, "INVALID_HEX\n");
                return 2;
            }
            raw[i] = (uint8_t)((hi << 4) | lo);
        }
        char out[32];
        int rc = parse_packet(raw, blen, out, sizeof(out));
        if (rc < 0) {
            printf("REJECTED:%d\n", rc);
            return 0;
        }
        printf("PARSED:%d:%s\n", rc, out);
        return 0;
    }
    fprintf(stderr, "usage: %s [--selftest | --hex <bytes>]\n", argv[0]);
    return 2;
}
