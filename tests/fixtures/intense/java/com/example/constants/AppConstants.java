package com.example.constants;

/**
 * アプリケーション全体で使用する定数クラス。
 * 注文タイプ・ステータス・設定値などを一元管理する。
 */
public final class AppConstants {

    private AppConstants() {}

    // ---- 注文タイプ ----
    public static final String ORDER_TYPE_NORMAL       = "01";
    public static final String ORDER_TYPE_EXPRESS      = "02";
    public static final String ORDER_TYPE_SUBSCRIPTION = "03";
    public static final String ORDER_TYPE_BULK         = "04";
    public static final String ORDER_TYPE_RETURN       = "05";

    // ---- 注文ステータス ----
    public static final String STATUS_PENDING    = "PENDING";
    public static final String STATUS_CONFIRMED  = "CONFIRMED";
    public static final String STATUS_SHIPPED    = "SHIPPED";
    public static final String STATUS_DELIVERED  = "DELIVERED";
    public static final String STATUS_CANCELLED  = "CANCELLED";

    // ---- 制限値 ----
    public static final int    MAX_ORDER_ITEMS   = 100;
    public static final int    MAX_RETRY_COUNT   = 3;
    public static final long   SESSION_TIMEOUT   = 1800L;

    // ---- 外部連携キー ----
    public static final String PAYMENT_GATEWAY_KEY = "PGW-PROD-001";
    public static final String SHIPPING_API_KEY    = "SHIP-API-KEY";

    // ---- フラグ ----
    public static final String FLAG_YES = "Y";
    public static final String FLAG_NO  = "N";
}
