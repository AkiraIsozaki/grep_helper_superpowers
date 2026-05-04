package sample

class Caller {
    void invoke() {
        Sample s = new Sample()
        String t = s.getType()
        s.setType("777")
    }
}
