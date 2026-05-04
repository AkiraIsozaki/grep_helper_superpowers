package sample

object Constants {
    const val STATUS_CODE = "777"
}

@Deprecated("777")
class Sample {
    fun check(input: String): Int {
        var localCode = "777"
        if (input == "777") {
            return 1
        }
        if (input == Constants.STATUS_CODE) {
            return 0
        }
        logValue("777")
        return -1
    }

    fun getCode(): String {
        return "777"
    }

    // "777" のコメント — その他に分類されることを期待
}
