package com.example.constants;

/**
 * エラーコード定数クラス。
 * ビジネスエラー・システムエラーを分類して管理する。
 */
public final class ErrorCodes {

    private ErrorCodes() {}

    // ---- ビジネスエラー ----
    public static final String ERR_ORDER_NOT_FOUND      = "BIZ-001";
    public static final String ERR_STOCK_INSUFFICIENT   = "BIZ-002";
    public static final String ERR_INVALID_ORDER_TYPE   = "BIZ-003";
    public static final String ERR_PAYMENT_FAILED       = "BIZ-004";
    public static final String ERR_MAX_ITEMS_EXCEEDED   = "BIZ-005";

    // ---- システムエラー ----
    public static final String ERR_DB_TIMEOUT           = "SYS-001";
    public static final String ERR_EXTERNAL_API_FAIL    = "SYS-002";
    public static final String ERR_UNEXPECTED           = "SYS-999";

    // ---- バリデーションエラー ----
    public static final String ERR_REQUIRED_FIELD       = "VAL-001";
    public static final String ERR_INVALID_FORMAT       = "VAL-002";
    public static final String ERR_OUT_OF_RANGE         = "VAL-003";
}
