DECLARE
    v_status_code VARCHAR2(8) := '777';
    c_default_code CONSTANT VARCHAR2(8) := '777';
BEGIN
    SELECT code INTO v_status_code FROM master_table;
    IF v_status_code = '777' THEN
        INSERT INTO log_table (code, label) VALUES ('777', 'OK');
        UPDATE master SET code = '777';
        SELECT '777' INTO v_status_code FROM dual;
    END IF;
    IF DECODE(v_status_code, '777', 'OK', 'NG') = 'OK' THEN
        v_status_code := '777';
    END IF;
    SELECT count(*) INTO v_status_code FROM tab WHERE id = '777';
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(-20001, '777 が見つかりません');
END;
/

-- '777' のコメント — その他に分類されることを期待
