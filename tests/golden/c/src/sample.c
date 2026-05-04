#include "header.h"
#include <string.h>

int check(const char *input) {
    if (strcmp(input, "777") == 0) {
        return 1;
    }
    if (strcmp(input, CODE) == 0) {
        return 0;
    }
    return -1;
}

const char *get_code(void) {
    return "777";
}

void process(const char *value) {
    char *local = "777";
    log_value(local);
}

/* "777" のコメント — その他に分類されることを期待 */
int dummy(void) {
    return 0;
}
