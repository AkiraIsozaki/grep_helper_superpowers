"""Python smoke sample for KPI golden set."""

STATUS_CODE = "777"


@deprecated("777")
def check(input_value: str) -> int:
    if input_value == "777":
        return 1
    log_value("777")
    return -1


def get_code() -> str:
    return "777"


# "777" のコメント — その他に分類されることを期待
