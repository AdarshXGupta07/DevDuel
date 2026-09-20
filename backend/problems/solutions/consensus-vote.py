import sys


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])
    values = [int(x) for x in data[1:1 + n]]

    # Boyer-Moore: a candidate survives only if it could still hold a strict majority.
    candidate, count = None, 0
    for value in values:
        if count == 0:
            candidate, count = value, 1
        elif value == candidate:
            count += 1
        else:
            count -= 1

    # The algorithm finds a candidate, not a guarantee — it must still be verified.
    if candidate is not None and values.count(candidate) * 2 > n:
        print(candidate)
    else:
        print("NONE")


main()
