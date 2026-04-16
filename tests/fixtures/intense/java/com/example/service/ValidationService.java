package com.example.service;

import com.example.constants.AppConstants;
import com.example.constants.ErrorCodes;
import com.example.domain.Order;

/**
 * バリデーションサービス。
 * 条件判定・return文での定数参照が中心。
 */
public class ValidationService {

    /**
     * 注文タイプが有効かチェックする。
     * @return エラーコードまたは null（正常時）
     */
    public String validateOrderType(String orderType) {
        if (orderType == null || orderType.isEmpty()) {
            return ErrorCodes.ERR_REQUIRED_FIELD;
        }
        if (!AppConstants.ORDER_TYPE_NORMAL.equals(orderType)
                && !AppConstants.ORDER_TYPE_EXPRESS.equals(orderType)
                && !AppConstants.ORDER_TYPE_SUBSCRIPTION.equals(orderType)
                && !AppConstants.ORDER_TYPE_BULK.equals(orderType)
                && !AppConstants.ORDER_TYPE_RETURN.equals(orderType)) {
            return ErrorCodes.ERR_INVALID_ORDER_TYPE;
        }
        return null;
    }

    /**
     * ステータス遷移が有効かチェックする。
     */
    public boolean isValidStatusTransition(String fromStatus, String toStatus) {
        if (AppConstants.STATUS_CANCELLED.equals(fromStatus)) {
            return false;
        }
        if (AppConstants.STATUS_DELIVERED.equals(fromStatus)) {
            return false;
        }
        if (AppConstants.STATUS_PENDING.equals(fromStatus)
                && AppConstants.STATUS_SHIPPED.equals(toStatus)) {
            return false;
        }
        return true;
    }

    /**
     * アイテム数が制限内かチェックする。
     */
    public String validateItemCount(int count) {
        if (count <= 0) {
            return ErrorCodes.ERR_OUT_OF_RANGE;
        }
        if (count > AppConstants.MAX_ORDER_ITEMS) {
            return ErrorCodes.ERR_MAX_ITEMS_EXCEEDED;
        }
        return null;
    }

    /**
     * 注文のステータスが有効な終了状態かチェックする。
     * getOrderStatus() 経由で orderStatus を参照する。
     */
    public boolean isTerminalStatus(Order order) {
        String status = order.getOrderStatus();
        return AppConstants.STATUS_DELIVERED.equals(status)
                || AppConstants.STATUS_CANCELLED.equals(status);
    }

    /**
     * 注文タイプのフラグを返す（return文で定数）。
     */
    public String getExpressFlag(String orderType) {
        if (AppConstants.ORDER_TYPE_EXPRESS.equals(orderType)) {
            return AppConstants.FLAG_YES;
        }
        return AppConstants.FLAG_NO;
    }
}
