package Worker;
use Sample qw(STATUS_CODE);

sub emit {
    do_notify(STATUS_CODE);
}

1;
