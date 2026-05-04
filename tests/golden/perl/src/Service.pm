package Service;
use Sample qw(STATUS_CODE);

sub check {
    my $input = shift;
    if ($input eq STATUS_CODE) {
        return 1;
    }
    return 0;
}

1;
