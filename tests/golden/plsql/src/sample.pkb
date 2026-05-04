CREATE OR REPLACE PACKAGE BODY sample AS
    c_default_code CONSTANT VARCHAR2(8) := '777';
    CURSOR cur_codes IS SELECT code FROM master WHERE code = '777';
    PROCEDURE check_code(p_input IN VARCHAR2) IS
    BEGIN
        IF p_input = '777' THEN
            INSERT INTO log_table (code) VALUES ('777');
            SELECT code FROM master WHERE id = '777';
        END IF;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            v_msg := '777 not found';
            RAISE error_777;
    END check_code;

    -- '777' のコメント — その他に分類されることを期待
END sample;
/
