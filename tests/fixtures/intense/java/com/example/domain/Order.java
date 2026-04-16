package com.example.domain;

import com.example.constants.AppConstants;

/**
 * 注文エンティティ。
 * フィールド・標準 getter・非標準 getter を持つ。
 */
public class Order {

    private Long   orderId;
    private String orderType;
    private String orderStatus = null;
    private String customerId;
    private int    itemCount;
    private String paymentMethod;
    private String shippingAddress;

    public Order() {}

    public Order(Long orderId, String orderType, String orderStatus) {
        this.orderId      = orderId;
        this.orderType    = orderType;
        this.orderStatus  = orderStatus;
    }

    // ---- 標準 getter ----
    public Long getOrderId() {
        return orderId;
    }

    public String getOrderType() {
        return orderType;
    }

    public String getOrderStatus() {
        return orderStatus;
    }

    /** 非標準 getter: orderStatus を返す */
    public String fetchStatus() {
        return orderStatus;
    }

    /** 別名 getter: orderStatus を返す */
    public String retrieveCurrentStatus() {
        return orderStatus;
    }

    public String getCustomerId() {
        return customerId;
    }

    public int getItemCount() {
        return itemCount;
    }

    public String getPaymentMethod() {
        return paymentMethod;
    }

    public String getShippingAddress() {
        return shippingAddress;
    }

    // ---- setter ----
    public void setOrderType(String orderType) {
        this.orderType = orderType;
    }

    public void setOrderStatus(String orderStatus) {
        this.orderStatus = orderStatus;
    }

    // ---- ビジネスメソッド ----
    public boolean isNormalOrder() {
        return AppConstants.ORDER_TYPE_NORMAL.equals(orderType);
    }

    public boolean isExpressOrder() {
        return AppConstants.ORDER_TYPE_EXPRESS.equals(orderType);
    }

    public boolean isCancelled() {
        return AppConstants.STATUS_CANCELLED.equals(orderStatus);
    }
}
