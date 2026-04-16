package com.example.util;

import com.example.constants.AppConstants;
import com.example.constants.ErrorCodes;
import com.example.constants.MessageKeys;

/**
 * コード変換ユーティリティ。
 * ローカル変数経由での定数参照を含む。
 */
public class CodeConverter {

    /**
     * 注文タイプコードを表示名に変換する。
     * ローカル変数に定数を代入してから使用。
     */
    public String toOrderTypeLabel(String code) {
        String normalType  = AppConstants.ORDER_TYPE_NORMAL;
        String expressType = AppConstants.ORDER_TYPE_EXPRESS;

        if (normalType.equals(code)) {
            return "通常注文";
        }
        if (expressType.equals(code)) {
            return "速達注文";
        }
        if (AppConstants.ORDER_TYPE_SUBSCRIPTION.equals(code)) {
            return "定期注文";
        }
        if (AppConstants.ORDER_TYPE_BULK.equals(code)) {
            return "一括注文";
        }
        if (AppConstants.ORDER_TYPE_RETURN.equals(code)) {
            return "返品";
        }
        return "不明";
    }

    /**
     * ステータスコードを日本語に変換する。
     * ローカル変数に定数を代入してからループで使用。
     */
    public String toStatusLabel(String statusCode) {
        String pending   = AppConstants.STATUS_PENDING;
        String confirmed = AppConstants.STATUS_CONFIRMED;
        String shipped   = AppConstants.STATUS_SHIPPED;

        if (pending.equals(statusCode)) {
            return "受付中";
        }
        if (confirmed.equals(statusCode)) {
            return "確定";
        }
        if (shipped.equals(statusCode)) {
            return "発送済";
        }
        if (AppConstants.STATUS_DELIVERED.equals(statusCode)) {
            return "配達済";
        }
        if (AppConstants.STATUS_CANCELLED.equals(statusCode)) {
            return "キャンセル";
        }
        return MessageKeys.MSG_ERROR_GENERIC;
    }

    /**
     * 有効な注文タイプか確認する。
     * ローカル変数に配列を代入して参照する。
     */
    public boolean isValidOrderType(String code) {
        String[] validTypes = {
            AppConstants.ORDER_TYPE_NORMAL,
            AppConstants.ORDER_TYPE_EXPRESS,
            AppConstants.ORDER_TYPE_SUBSCRIPTION,
            AppConstants.ORDER_TYPE_BULK,
            AppConstants.ORDER_TYPE_RETURN,
        };
        for (String type : validTypes) {
            if (type.equals(code)) {
                return true;
            }
        }
        return false;
    }

    /**
     * エラーコードからメッセージキーへのマッピング。
     */
    public String toMessageKey(String errorCode) {
        if (ErrorCodes.ERR_ORDER_NOT_FOUND.equals(errorCode)) {
            return MessageKeys.MSG_ERROR_NOT_FOUND;
        }
        if (ErrorCodes.ERR_MAX_ITEMS_EXCEEDED.equals(errorCode)) {
            return MessageKeys.MSG_MAX_EXCEEDED;
        }
        return MessageKeys.MSG_ERROR_GENERIC;
    }
}
