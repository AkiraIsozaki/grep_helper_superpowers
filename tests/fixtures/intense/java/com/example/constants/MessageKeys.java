package com.example.constants;

/**
 * メッセージキー定数クラス。
 * i18n リソースバンドルのキーを一元管理する。
 */
public final class MessageKeys {

    private MessageKeys() {}

    // ---- 注文関連メッセージ ----
    public static final String MSG_ORDER_CREATED    = "order.created";
    public static final String MSG_ORDER_CANCELLED  = "order.cancelled";
    public static final String MSG_ORDER_SHIPPED    = "order.shipped";
    public static final String MSG_ORDER_TYPE_LABEL = "order.type.label";

    // ---- エラーメッセージ ----
    public static final String MSG_ERROR_GENERIC    = "error.generic";
    public static final String MSG_ERROR_NOT_FOUND  = "error.notFound";

    // ---- バリデーションメッセージ ----
    public static final String MSG_REQUIRED         = "validation.required";
    public static final String MSG_MAX_EXCEEDED     = "validation.maxExceeded";
}
