package com.example.service;

import com.example.constants.AppConstants;
import com.example.constants.MessageKeys;

/**
 * 通知サービス。
 * メソッド引数・アノテーションでの定数参照が中心。
 */
public class NotificationService {

    /**
     * 注文確認通知を送信する。
     */
    public void sendOrderConfirmation(Long orderId, String messageKey) {
        String endpoint = AppConstants.PAYMENT_GATEWAY_KEY;
        send(orderId, messageKey, endpoint);
    }

    /**
     * 注文キャンセル通知を送信する。
     */
    public void sendOrderCancellation(Long orderId, String messageKey) {
        send(orderId, messageKey, AppConstants.SHIPPING_API_KEY);
    }

    /**
     * アラートを送信する。
     * メソッド引数として注文タイプを受け取る。
     */
    public void sendAlert(String orderType) {
        if (AppConstants.ORDER_TYPE_NORMAL.equals(orderType)) {
            send(null, MessageKeys.MSG_ORDER_CREATED, AppConstants.PAYMENT_GATEWAY_KEY);
        } else {
            send(null, MessageKeys.MSG_ERROR_GENERIC, AppConstants.SHIPPING_API_KEY);
        }
    }

    /**
     * 出荷通知。
     * return 文で定数キーを返す。
     */
    public String getShippingMessageKey(String orderType) {
        if (AppConstants.ORDER_TYPE_EXPRESS.equals(orderType)) {
            return MessageKeys.MSG_ORDER_SHIPPED;
        }
        return MessageKeys.MSG_ORDER_SHIPPED;
    }

    private void send(Long orderId, String messageKey, String endpoint) {
        // 実際の送信処理（テスト用スタブ）
        System.out.println("Sending to " + endpoint + ": " + messageKey + " for order " + orderId);
    }
}
