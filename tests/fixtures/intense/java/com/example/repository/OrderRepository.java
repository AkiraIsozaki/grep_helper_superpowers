package com.example.repository;

import com.example.constants.AppConstants;
import com.example.domain.Order;
import com.example.domain.OrderItem;

import java.util.List;

/**
 * 注文リポジトリ。
 * アノテーション・定数参照・メソッド引数が混在。
 */
public class OrderRepository {

    /**
     * 注文を保存する。
     */
    public void save(Order order) {
        // 実装省略
    }

    /**
     * 注文明細一覧を保存する。
     */
    public void saveItems(List<OrderItem> items) {
        // 実装省略
    }

    /**
     * ID で注文を取得する。
     */
    public Order findById(Long orderId) {
        // 実装省略
        return null;
    }

    /**
     * 注文タイプで検索する。
     * 定数を引数として渡す。
     */
    public List<Order> findByOrderType(String orderType) {
        // 実装省略
        return null;
    }

    /**
     * 通常注文を全件取得する。
     * 定数をメソッド引数に直接渡す。
     */
    public List<Order> findAllNormalOrders() {
        return findByOrderType(AppConstants.ORDER_TYPE_NORMAL);
    }

    /**
     * 速達注文を全件取得する。
     */
    public List<Order> findAllExpressOrders() {
        return findByOrderType(AppConstants.ORDER_TYPE_EXPRESS);
    }

    /**
     * キャンセル済み注文を全件取得する。
     */
    public List<Order> findCancelledOrders() {
        return findByStatus(AppConstants.STATUS_CANCELLED);
    }

    private List<Order> findByStatus(String status) {
        // 実装省略
        return null;
    }

    /**
     * 注文件数上限チェック。
     */
    public boolean isOverLimit(int count) {
        return count > AppConstants.MAX_ORDER_ITEMS;
    }
}
