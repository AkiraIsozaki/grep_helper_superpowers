import { STATUS_CODE } from './sample';

export function check(input: string): boolean {
    if (input === STATUS_CODE) {
        return true;
    }
    return false;
}
