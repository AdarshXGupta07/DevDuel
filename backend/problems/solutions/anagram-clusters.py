import sys


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])
    codes = data[1:1 + n]

    # The sorted letters are a canonical name for the family. Counting letters would
    # also work and is O(len) rather than O(len log len), but len <= 50 here.
    families = {bytes(sorted(code)) for code in codes}
    print(len(families))


main()
