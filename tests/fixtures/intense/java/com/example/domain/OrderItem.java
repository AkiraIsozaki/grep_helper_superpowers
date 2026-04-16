package com.example.domain;

import com.example.constants.AppConstants;

/**
 * 注文明細エンティティ。
 * ORDER_TYPE 定数を参照する場面を意図的に含む。
 */
public class OrderItem {

    private Long   itemId;
    private Long   orderId;
    private String productCode;
    private int    quantity;
    private String orderType;

    public OrderItem() {}

    public OrderItem(Long itemId, Long orderId, String productCode, int quantity) {
        this.itemId      = itemId;
        this.orderId     = orderId;
        this.productCode = productCode;
        this.quantity    = quantity;
    }

    public Long   getItemId()      { return itemId; }
    public Long   getOrderId()     { return orderId; }
    public String getProductCode() { return productCode; }
    public int    getQuantity()    { return quantity; }
    public String getOrderType()   { return orderType; }

    public void setOrderType(String orderType) {
        this.orderType = orderType;
    }

    /** 通常注文明細かどうか判定 */
    public boolean isNormalType() {
        return AppConstants.ORDER_TYPE_NORMAL.equals(this.orderType);
    }

    /** 速達注文明細かどうか判定 */
    public boolean isExpressType() {
        return AppConstants.ORDER_TYPE_EXPRESS.equals(this.orderType);
    }
}
