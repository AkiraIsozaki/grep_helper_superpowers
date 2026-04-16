package com.example.service;

import com.example.constants.AppConstants;
import com.example.constants.ErrorCodes;
import com.example.constants.MessageKeys;
import com.example.domain.Order;
import com.example.domain.OrderItem;
import com.example.repository.OrderRepository;

import java.util.List;

/**
 * 注文サービス。
 * 定数・フィールド・getter・ローカル変数を複雑に参照するサービス層。
 */
public class OrderService {

    private OrderRepository orderRepository;
    private NotificationService notificationService;

    public OrderService(OrderRepository orderRepository, NotificationService notificationService) {
        this.orderRepository     = orderRepository;
        this.notificationService = notificationService;
    }

    /**
     * 注文を処理する中心メソッド。
     * 定数参照・ローカル変数経由・条件判定が混在する。
     */
    public String processOrder(Order order) {
        // 定数を直接参照（条件判定）
        if (AppConstants.ORDER_TYPE_NORMAL.equals(order.getOrderType())) {
            return handleNormalOrder(order);
        }
        if (AppConstants.ORDER_TYPE_EXPRESS.equals(order.getOrderType())) {
            return handleExpressOrder(order);
        }
        if (AppConstants.ORDER_TYPE_SUBSCRIPTION.equals(order.getOrderType())) {
            return handleSubscriptionOrder(order);
        }
        // ローカル変数に定数を代入（ローカル変数経由参照のトリガー）
        String unknownType = AppConstants.ORDER_TYPE_BULK;
        notificationService.sendAlert(unknownType);
        return ErrorCodes.ERR_INVALID_ORDER_TYPE;
    }

    private String handleNormalOrder(Order order) {
        order.setOrderStatus(AppConstants.STATUS_CONFIRMED);
        orderRepository.save(order);
        notificationService.sendOrderConfirmation(order.getOrderId(), MessageKeys.MSG_ORDER_CREATED);
        return AppConstants.FLAG_YES;
    }

    private String handleExpressOrder(Order order) {
        if (order.getItemCount() > AppConstants.MAX_ORDER_ITEMS) {
            order.setOrderStatus(AppConstants.STATUS_CANCELLED);
            return ErrorCodes.ERR_MAX_ITEMS_EXCEEDED;
        }
        order.setOrderStatus(AppConstants.STATUS_SHIPPED);
        orderRepository.save(order);
        return AppConstants.FLAG_YES;
    }

    private String handleSubscriptionOrder(Order order) {
        // getter 経由で orderStatus を参照
        String currentStatus = order.fetchStatus();
        if (AppConstants.STATUS_CANCELLED.equals(currentStatus)) {
            return ErrorCodes.ERR_ORDER_NOT_FOUND;
        }
        order.setOrderStatus(AppConstants.STATUS_CONFIRMED);
        return AppConstants.FLAG_YES;
    }

    /**
     * 注文タイプのラベルを返す。
     * return 文で定数を返す。
     */
    public String getOrderTypeLabel(String orderType) {
        if (AppConstants.ORDER_TYPE_NORMAL.equals(orderType)) {
            return MessageKeys.MSG_ORDER_TYPE_LABEL;
        }
        return MessageKeys.MSG_ERROR_GENERIC;
    }

    /**
     * キャンセル処理。
     * フィールド orderStatus を経由して状態チェック。
     */
    public boolean cancelOrder(Long orderId) {
        Order order = orderRepository.findById(orderId);
        if (order == null) {
            return false;
        }
        // getter 経由で orderStatus を参照（retrieveCurrentStatus は非標準getter）
        String status = order.retrieveCurrentStatus();
        if (AppConstants.STATUS_CANCELLED.equals(status)
                || AppConstants.STATUS_DELIVERED.equals(status)) {
            return false;
        }
        order.setOrderStatus(AppConstants.STATUS_CANCELLED);
        orderRepository.save(order);
        notificationService.sendOrderCancellation(orderId, MessageKeys.MSG_ORDER_CANCELLED);
        return true;
    }

    /**
     * アイテムリストの注文タイプを一括更新する。
     * ローカル変数に定数を代入してループ内で使用。
     */
    public void bulkUpdateOrderType(List<OrderItem> items) {
        String targetType = AppConstants.ORDER_TYPE_BULK;
        for (OrderItem item : items) {
            item.setOrderType(targetType);
        }
        orderRepository.saveItems(items);
    }
}
