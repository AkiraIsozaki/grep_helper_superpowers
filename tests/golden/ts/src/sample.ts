const STATUS_CODE = "777";

@Component("777")
class Sample {
    check(input: string): number {
        let localCode = "777";
        if (input === "777") {
            return 1;
        }
        logValue("777");
        return -1;
    }

    getCode(): string {
        return "777";
    }

    // "777" のコメント — その他に分類されることを期待
}
