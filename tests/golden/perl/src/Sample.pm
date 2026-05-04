package Sample;
use strict;
use warnings;
use constant STATUS_CODE => "777";

sub check {
    my ($input) = @_;
    my $local_code = "777";
    if ($input eq "777") {
        return 1;
    }
    print "777 detected\n";
    do_notify("777");
    return -1;
}

# "777" のコメント — その他に分類されることを期待

1;
