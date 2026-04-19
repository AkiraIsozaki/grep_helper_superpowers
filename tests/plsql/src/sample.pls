-- sample.pls - PL/SQL E2E test fixture
CREATE OR REPLACE PROCEDURE check_status AS
    v_status CONSTANT VARCHAR2(10) := 'TARGET';
    v_code   VARCHAR2(10);
BEGIN
    IF v_code = 'TARGET' THEN
        RAISE_APPLICATION_ERROR(-20001, 'Invalid status');
    END IF;

    SELECT code INTO v_code FROM t WHERE code = 'TARGET';

    UPDATE t SET code = 'TARGET' WHERE id = 1;
END;
/
