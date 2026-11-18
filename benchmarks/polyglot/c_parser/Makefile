CC ?= gcc
CFLAGS ?= -g -O0 -fno-omit-frame-pointer -fno-stack-protector -Wall -Wextra

all: parser

parser: parser.c
	$(CC) $(CFLAGS) -o parser parser.c

clean:
	rm -f parser
