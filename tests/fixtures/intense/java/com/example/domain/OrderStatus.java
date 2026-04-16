package com.example.domain;

import com.example.constants.AppConstants;

/**
 * 注文ステータスの列挙型。
 * AppConstants のステータス定数に対応する。
 */
public enum OrderStatus {

    PENDING(AppConstants.STATUS_PENDING),
    CONFIRMED(AppConstants.STATUS_CONFIRMED),
    SHIPPED(AppConstants.STATUS_SHIPPED),
    DELIVERED(AppConstants.STATUS_DELIVERED),
    CANCELLED(AppConstants.STATUS_CANCELLED);

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown status code: " + code);
    }

    public boolean isFinal() {
        return this == DELIVERED || this == CANCELLED;
    }
}
