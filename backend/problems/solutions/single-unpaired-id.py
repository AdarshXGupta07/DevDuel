import sys


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])

    # XOR cancels every pair (a ^ a == 0) and leaves the one that has no partner.
    # O(1) space, one pass, no hashing.
    answer = 0
    for token in data[1:1 + n]:
        answer ^= int(token)
    print(answer)


main()
