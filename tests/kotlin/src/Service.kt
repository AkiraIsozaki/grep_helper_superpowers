// Service.kt - Kotlin E2E test fixture
class Service {
    fun check(code: String): Boolean {
        if (code == Constants.STATUS) {
            return true
        }
        return false
    }

    fun checkAlias(code: String): Boolean {
        when (code) {
            Constants.ALIAS -> return true
            else -> return false
        }
    }
}
